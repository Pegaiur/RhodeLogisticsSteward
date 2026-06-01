"""SlotSolver — 槽位加工模型求解引擎

直接实现 slot-processing-model.md §9.5 混合状态迭代策略。
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from steward_core.models import LayoutConfig, SolveResult
from steward_core.solver.config import SolverConfig
from steward_core.solver.refine import local_search_refine
from steward_core.solver.slot.context import SlotContext
from steward_core.solver.slot.mfg import phase_mfg
from steward_core.solver.slot.trade import phase_trade
from steward_core.solver.slot.control import phase_control
from steward_core.solver.slot.remaining import phase_remaining
from steward_core.solver.slot.partials import compute_partial_derivatives
from steward_core.mood_flow import _compute_self_mp_cost

if TYPE_CHECKING:
    from steward_core.models import Operator
    from steward_core.solver.params import SolverParams
    from steward_core.mood_flow import MoodContext


_MAX_ITERATIONS = 10
"""默认最大迭代轮数"""

_NON_WORK_FACILITIES = frozenset({"Dormitory", "Training", "Workshop"})
"""不消耗心情的设施类型集合"""

_FACILITY_SLOTS: dict[str, int] = {
    "Control": 5,
    "Mfg": 3,
    "Trade": 3,
    "Power": 1,
    "Reception": 1,
    "Office": 1,
}
"""每种设施类型的标准槽位数"""


def solve_slot(
    operators: list["Operator"],
    params: "SolverParams",
    layout: LayoutConfig | None = None,
    mood_ctx: "MoodContext | None" = None,
    max_iterations: int = _MAX_ITERATIONS,
) -> SolveResult:
    """槽位加工模型求解入口

    1. 初始化 SlotContext（num_windows = params.shift_count）
    2. 自动创建 MoodContext（若未传入且多窗口）
    3. 迭代：Phase A/B/C/D + D[d]反馈 + 记忆收敛
    4. 多窗口心情流转：after_shift 消耗
    5. λ 影子乘子更新：工作时长池稀缺性传导
    6. 后处理：局部搜索
    7. 输出多 ShiftPlan SolveResult
    """
    if layout is None:
        layout = LayoutConfig.layout_243()

    num_windows = max(1, params.shift_count if params else 1)

    if mood_ctx is None and num_windows > 1:
        from steward_core.mood_flow import MoodContext
        mood_ctx = MoodContext.fresh(operators, params)

    ctx = SlotContext.from_layout(operators, layout, params, num_windows=num_windows)

    shift_hours = params.shift_hours if params else 12.0

    visited = set()
    best_ctx = None
    best_P = 0.0
    prev_max_lambda = -1.0

    for iteration in range(max_iterations):
        if iteration > 0:
            _reset_ctx(ctx)
        mc = mood_ctx
        for w in range(num_windows):
            phase_mfg(ctx, w, mood_ctx=mc)
            phase_trade(ctx, w, mood_ctx=mc)

            D = compute_partial_derivatives(ctx, w)
            ctx.windows[w].D = D

            phase_control(ctx, w, D, mood_ctx=mc)
            ctx.lambda_k = _compute_lambda_k(ctx, w, shift_hours, mood_ctx=mc)
            phase_remaining(ctx, w, D, mood_ctx=mc)

            if mc is not None:
                mc.control_operators = ctx.ops_of_type(w, "Control")
                ctx.control_operators = list(mc.control_operators)
                working_names = {
                    a.operator_name for a in ctx.windows[w].assignments
                    if a.operator_name and a.facility_type not in _NON_WORK_FACILITIES
                }
                working_slots = {}
                for a in ctx.windows[w].assignments:
                    if a.operator_name and a.facility_type not in _NON_WORK_FACILITIES:
                        ft = a.facility_type
                        ri = a.room_index
                        room_ops = ctx.room_ops(w, ft, ri)
                        from steward_core.mood_flow import RoomBurnContext
                        working_slots[a.operator_name] = RoomBurnContext(
                            room_type=ft,
                            room_slots=_FACILITY_SLOTS.get(ft, 3),
                            room_index=ri,
                            co_workers=room_ops,
                        )
                mc = mc.after_shift(working_names, working_slots=working_slots)

                dorm_map = _build_dorm_assignments(ctx, w)
                if dorm_map:
                    mc = replace(mc, dorm_assignments=dorm_map)
                    new_moods = dict(mc.operator_moods)
                    for name in dorm_map:
                        rate = mc.dorm_recovery(name)
                        if rate > 0:
                            new_moods[name] = min(24.0, new_moods.get(name, 24.0) + rate * shift_hours)
                    mc = replace(mc, operator_moods=new_moods)

            _track_hours_used(ctx, w, shift_hours)

        max_lambda = 0.0
        if num_windows > 1:
            max_lambda = _update_lambda_shadow(ctx, operators, params, shift_hours, mood_ctx=mood_ctx)

        sig = "||".join(ctx.signature(w) for w in range(ctx.num_windows))
        if sig in visited:
            break
        visited.add(sig)

        P = _estimate_total_production(ctx, mood_ctx=mood_ctx)
        if num_windows > 1 and iteration == 0:
            pass
        elif best_ctx is None:
            best_ctx = ctx.clone()
            best_P = P
        elif P > best_P:
            best_P = P
            best_ctx = ctx.clone()
        ctx.prev_P = P

        if num_windows > 1 and max_lambda < 0.001 and iteration > 0:
            if prev_max_lambda >= 0 and abs(max_lambda - prev_max_lambda) < 0.001:
                break
        prev_max_lambda = max_lambda

    if best_ctx is None:
        best_ctx = ctx

    result = _ctx_to_multi_result(best_ctx, operators, params)
    if num_windows > 1:
        return result

    config = SolverConfig(params=params)
    result = local_search_refine(result, operators, config)
    return result


def _build_dorm_assignments(ctx: SlotContext, window_idx: int) -> dict[str, str]:
    """从槽位上下文提取宿舍分配映射 {干员名 → 宿舍编号}"""
    dorm_map: dict[str, str] = {}
    for a in ctx.windows[window_idx].assignments:
        if a.facility_type == "Dormitory" and a.operator_name:
            dorm_map[a.operator_name] = str(a.room_index)
    return dorm_map


def _reset_ctx(ctx: SlotContext) -> None:
    """清空所有窗口槽位用于迭代重新求解

    保留 lambda_ops（跨迭代持久化，离散 bisection 需要历史累积）、
    control_operators（供 _update_lambda_shadow 计算逐干员 pool）。
    仅清空 operator_name、hours_used。
    """
    for w in range(ctx.num_windows):
        for a in ctx.windows[w].assignments:
            a.operator_name = ""
    ctx.hours_used.clear()
    ctx.lambda_k = 0.0


def _track_hours_used(ctx: SlotContext, window_idx: int, hours: float) -> None:
    """累加窗口 w 中工作干员的工作时长（λ 算力准备）"""
    for a in ctx.windows[window_idx].assignments:
        if not a.operator_name:
            continue
        if a.facility_type in _NON_WORK_FACILITIES:
            continue
        ctx.hours_used[a.operator_name] = ctx.hours_used.get(a.operator_name, 0.0) + hours


def _update_lambda_shadow(
    ctx: SlotContext,
    operators: list,
    params: "SolverParams",
    shift_hours: float,
    mood_ctx: "MoodContext | None" = None,
) -> float:
    """更新影子乘子 lambda_op（离散 bisection）

    对每名干员：
      pool[op] = mood_full / mood_burn(op)  ← 跨周期可持续性硬约束上限（H6）
      若 hours_used > pool:  lambda <- lambda * 2（收紧）
      若 hours_used <= pool: lambda <- lambda / 2（释放）

    lambda 跨迭代保持（_reset_ctx 不清零），逐步收敛至约束恰满足的水平。
    恢复不纳入 pool——宿舍恢复是独立资源，由 lambda 奖励传导（dorm contribution）。
    返回最大 lambda 值（用于收敛判断）。
    """
    mood_full = params.mood_full if params else 24.0

    hourly_value = _MFG_CR_BASE_RATE * _CR_LMD_PER_UNIT
    lambda_cap = hourly_value * 10.0

    max_lambda = 0.0

    for op in operators:
        pool = _pool_for(op, params, ctx, mood_ctx)
        used = ctx.hours_used.get(op.name, 0.0)
        old_lambda = ctx.lambda_ops.get(op.name, 0.0)

        if used > pool:
            if old_lambda <= 0.0:
                jump = params.lambda_jump_ratio if params else 0.25
                new_lambda = hourly_value * jump
            else:
                new_lambda = old_lambda * 2.0
            new_lambda = min(new_lambda, lambda_cap)
        else:
            new_lambda = old_lambda / 2.0

        ctx.lambda_ops[op.name] = new_lambda
        if new_lambda > max_lambda:
            max_lambda = new_lambda

    return max_lambda


_MFG_CR_BASE_RATE = 1.0 / 3.0
_CR_LMD_PER_UNIT = 1000.0 / 1.3



def _pool_for(
    op: "Operator",
    params: "SolverParams",
    ctx: SlotContext,
    mood_ctx: "MoodContext | None",
) -> float:
    """逐干员跨周期可持续工作时长上限

    pool[op] = mood_full / base_burn(op)

    base_burn 仅含房间工位数修正 + 干员自身 mp_cost buff，
    不含控制中枢 mood modifier（中枢阵容跨窗口变化，不应污染 pool）。
    固定 5 人中枢假设已包含在 base_burn_rate3 的 (3-1) 工位修正中，
    其余算力由 λ bisection 承担。
    """
    mood_full = params.mood_full if params else 24.0
    base_burn_per_hour = params.base_burn_per_hour if params else 1.0
    recovery_per_op = params.control_recovery_per_op if params else 0.05
    _, slots = _facility_slots_for(op)

    burn = base_burn_per_hour - recovery_per_op * max(0, slots - 1)
    burn = max(0.0, burn + _compute_self_mp_cost(op.name, ctx.op_lookup))

    if burn <= 0.0:
        burn = 0.01
    return mood_full / burn


def _facility_slots_for(op: "Operator") -> tuple[str, int]:
    """根据干员技能确定其 pool 计算用的设施类型和槽位数

    取所有可能设施类型中的最小槽位数（对应最高 burn 率、最小 pool）——
    确保 H6 跨周期可持续性约束始终保守。
    """
    facility_types = {sk.room_type for sk in op.skills}
    if not facility_types:
        return "Mfg", 3
    slots_map = _FACILITY_SLOTS
    min_type = min(facility_types, key=lambda t: slots_map.get(t, 3))
    return min_type, min(slots_map.get(min_type, 3), 3)


def _compute_lambda_k(
    ctx: SlotContext,
    window_idx: int,
    shift_hours: float,
    *,
    mood_ctx: "MoodContext | None" = None,
) -> float:
    """计算窗口 w 的标量 λ_k

    λ_k = median(Phase A/B 已分配 Mfg/Trade 槽位的每小时边际 LMD 等值)

    遍历窗口 w 中已分配的 Mfg/Trade 房间，对每间房调用 evaluate_room
    计算效率积分，按 production.py 的产出公式换算为 hourly LMD，取中位数。
    """
    from steward_core.evaluate import evaluate_room
    from steward_core.synergy import (
        compute_control_global_bonus,
        control_per_operator_bonus,
    )
    from steward_core.synergy.buff_pool import compute_buff_pool
    from steward_core.production import _get_trade_order_multiplier
    from steward_core.constants import BASE_POWER_COUNT
    from steward_core.models import LayoutConfig
    from ._cold_start import cold_start_ctrl_ops, cold_start_dorm_ops

    params = ctx.params
    layout = ctx.layout if ctx.layout else LayoutConfig.layout_243()
    suich_count = params.suich_count if params else 5
    dorm_level = params.dorm_level if params else 5

    ctrl_names = ctx.ops_of_type(window_idx, "Control")
    ctrl_ops = [ctx.op_lookup[n] for n in ctrl_names if n in ctx.op_lookup]
    if not ctrl_ops:
        ctrl_ops = cold_start_ctrl_ops(ctx, window_idx)
    global_bonus = compute_control_global_bonus(ctrl_ops)

    dorm_names = ctx.ops_of_type(window_idx, "Dormitory")
    dorm_ops = [ctx.op_lookup[n] for n in dorm_names if n in ctx.op_lookup]
    if not dorm_ops:
        dorm_ops = cold_start_dorm_ops(ctx, window_idx)

    buff_pool = compute_buff_pool(
        ctrl_ops,
        suich_count=suich_count,
        dorm_operators=[o for o in dorm_ops if o],
        dorm_level=dorm_level,
        layout=layout,
    )

    hourly_values: list[float] = []

    for facility_type in ("Mfg", "Trade"):
        rooms_done: set[tuple[str, int]] = set()
        for a in ctx.windows[window_idx].assignments:
            if a.facility_type != facility_type:
                continue
            key = (facility_type, a.room_index)
            if key in rooms_done:
                continue
            rooms_done.add(key)

            room_names = ctx.room_ops(window_idx, facility_type, a.room_index)
            if not room_names:
                continue
            room_ops = [ctx.op_lookup[n] for n in room_names if n in ctx.op_lookup]
            if not room_ops:
                continue

            product = a.product
            ctrl_bonus = control_per_operator_bonus(
                ctrl_ops, room_ops, product, room_type=facility_type,
            )
            eff_int = evaluate_room(
                room_ops, facility_type, product,
                BASE_POWER_COUNT, shift_hours, global_bonus, buff_pool,
                ctrl_per_op_bonus=ctrl_bonus,
                all_operators=ctx.operators,
                control_operators=ctrl_ops,
                mood_ctx=mood_ctx,
            )
            n = len(room_ops)

            if facility_type == "Mfg":
                productivity_int = shift_hours * (1.0 + 0.01 * n) + eff_int / 100.0
                if product == "CombatRecord":
                    base_rate = 1.0 / 3.0
                    unit_lmd = 1000.0 / 1.3
                else:
                    base_rate = 1.0 / 1.2
                    unit_lmd = 500.0
                hourly_lmd = base_rate * unit_lmd * (productivity_int / shift_hours)
            else:
                efficiency_integrated = shift_hours * (1.0 + 0.01 * n) + eff_int / 100.0
                lmd_per_day = _get_trade_order_multiplier(room_ops, shift_hours)[0]
                hourly_lmd = efficiency_integrated / 24.0 * lmd_per_day / shift_hours

            hourly_values.append(hourly_lmd)

    if not hourly_values:
        return 0.0

    hourly_values.sort()
    mid = len(hourly_values) // 2
    if len(hourly_values) % 2 == 1:
        return hourly_values[mid]
    return (hourly_values[mid - 1] + hourly_values[mid]) / 2.0


def _estimate_total_production(
    ctx: SlotContext,
    mood_ctx: "MoodContext | None" = None,
) -> float:
    """估算总产能（遍历所有窗口加权求和，用于收敛检测）"""
    from steward_core.evaluate import evaluate_room
    from steward_core.synergy import (
        compute_control_global_bonus,
        control_per_operator_bonus,
    )
    from steward_core.synergy.buff_pool import compute_buff_pool

    total = 0.0
    params = ctx.params
    hours = params.shift_hours if params else 12.0
    suich_count = params.suich_count if params else 5
    dorm_level = params.dorm_level if params else 5
    layout = ctx.layout if ctx.layout else LayoutConfig.layout_243()

    for w in range(ctx.num_windows):
        ctrl_names = ctx.ops_of_type(w, "Control")
        ctrl_ops = [ctx.op_lookup[n] for n in ctrl_names if n in ctx.op_lookup]
        global_bonus = compute_control_global_bonus(ctrl_ops)

        dorm_names = ctx.ops_of_type(w, "Dormitory")
        dorm_ops = [ctx.op_lookup[n] for n in dorm_names if n in ctx.op_lookup]

        mfg_names = ctx.ops_of_type(w, "Mfg")
        trade_names = ctx.ops_of_type(w, "Trade")
        office_names = ctx.ops_of_type(w, "Office")
        mfg_ops = [ctx.op_lookup[n] for n in mfg_names if n in ctx.op_lookup]
        trade_ops = [ctx.op_lookup[n] for n in trade_names if n in ctx.op_lookup]
        office_ops = [ctx.op_lookup[n] for n in office_names if n in ctx.op_lookup]

        pool = compute_buff_pool(
            ctrl_ops,
            suich_count=suich_count,
            dorm_operators=[o for o in dorm_ops if o],
            dorm_level=dorm_level,
            layout=layout,
            mfg_operators=mfg_ops,
            trade_operators=trade_ops,
            office_operators=office_ops,
            office_perception_base=params.office_perception_base if params else 20,
        )

        window_total = 0.0
        for facility_type in ("Mfg", "Trade"):
            rooms_done = set()
            for a in ctx.windows[w].assignments:
                if a.facility_type != facility_type:
                    continue
                key = (a.facility_type, a.room_index)
                if key in rooms_done:
                    continue
                rooms_done.add(key)

                room_names = ctx.room_ops(w, a.facility_type, a.room_index)
                if not room_names:
                    continue
                room_ops = [ctx.op_lookup[n] for n in room_names if n in ctx.op_lookup]

                ctrl_bonus = control_per_operator_bonus(
                    ctrl_ops, room_ops, a.product, a.facility_type,
                )
                score = evaluate_room(
                    room_ops, a.facility_type, a.product,
                    3, hours, global_bonus, pool,
                    ctrl_per_op_bonus=ctrl_bonus,
                    mood_ctx=mood_ctx,
                )
                window_total += score

        total += window_total

    return total


def _ctx_to_multi_result(
    ctx: SlotContext,
    operators: list,
    params: "SolverParams",
) -> SolveResult:
    """将 SlotContext 所有窗口转换为多 ShiftPlan SolveResult"""
    from steward_core.models import RoomAssignment, ShiftPlan

    hours = params.shift_hours if params else 12.0
    plans = []

    for w in range(ctx.num_windows):
        assignments = []
        rooms_done = set()
        for a in ctx.windows[w].assignments:
            key = (a.facility_type, a.room_index)
            if key in rooms_done:
                continue
            rooms_done.add(key)
            names = ctx.room_ops(w, a.facility_type, a.room_index)
            assignments.append(RoomAssignment(
                room_type=a.facility_type,
                room_index=a.room_index,
                operators=names,
                product=a.product,
            ))

        plan = ShiftPlan(
            name=f"Slot-S{w}-{int(hours)}h",
            assignments=assignments,
            period_from=f"{w * int(hours):02d}:00",
            period_to=f"{min((w + 1) * int(hours) - 1, 23):02d}:59",
        )
        plans.append(plan)

    return SolveResult(plans=plans, autofill_count=0, config_used=SolverConfig(params=params))
