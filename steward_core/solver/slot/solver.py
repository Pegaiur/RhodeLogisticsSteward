"""SlotSolver — 槽位加工模型求解引擎

直接实现 slot-processing-model-draft.md §9.5 混合状态迭代策略。
"""

from __future__ import annotations

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

if TYPE_CHECKING:
    from steward_core.models import Operator
    from steward_core.solver.params import SolverParams
    from steward_core.mood_flow import MoodContext


_MAX_ITERATIONS = 10
"""默认最大迭代轮数"""

_NON_WORK_FACILITIES = frozenset({"Dormitory", "Training", "Workshop"})
"""不消耗心情的设施类型集合"""


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
    4. 多窗口心情流转：after_shift 消耗 → after_recovery 恢复
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

    interval_hours = params.interval_hours if params else 8.0
    shift_hours = params.shift_hours if params else 12.0

    visited = set()
    best_ctx = None
    best_P = 0.0

    for iteration in range(max_iterations):
        if iteration > 0:
            _reset_ctx(ctx)
        mc = mood_ctx
        lambda_init = 0.0
        for w in range(num_windows):
            phase_mfg(ctx, w, mood_ctx=mc)
            phase_trade(ctx, w, mood_ctx=mc)

            D = compute_partial_derivatives(ctx, w)
            ctx.windows[w].D = D

            if mc is not None and num_windows > 1:
                lambda_w = _update_lambda_shadow(ctx, operators, params)
                if lambda_w > lambda_init:
                    lambda_init = lambda_w

            phase_control(ctx, w, D, mood_ctx=mc)
            phase_remaining(ctx, w, D, mood_ctx=mc)

            if mc is not None:
                mc.control_operators = ctx.ops_of_type(w, "Control")
                working_names = {
                    a.operator_name for a in ctx.windows[w].assignments
                    if a.operator_name and a.facility_type not in _NON_WORK_FACILITIES
                }
                mc = mc.after_shift(working_names)
                if w < num_windows - 1:
                    mc = mc.after_recovery(interval_hours)

            _track_hours_used(ctx, w, shift_hours)

        if best_ctx is None:
            best_ctx = ctx.clone()

        sig = ctx.signature()
        if sig in visited:
            break
        visited.add(sig)

        P = _estimate_total_production(ctx, mood_ctx=mood_ctx)
        if P > best_P:
            best_P = P
            best_ctx = ctx.clone()
        ctx.prev_P = P

        if num_windows > 1 and lambda_init < 0.001 and iteration > 0:
            break

    if best_ctx is None:
        best_ctx = ctx

    result = _ctx_to_multi_result(best_ctx, operators, params)
    if num_windows > 1:
        return result

    config = SolverConfig(params=params)
    result = local_search_refine(result, operators, config)
    return result


def _reset_ctx(ctx: SlotContext) -> None:
    """清空所有窗口槽位用于迭代重新求解

    保留 op_lookup/operators/params/layout/windows 结构，
    仅清空 operator_name、hours_used 和 lambda_ops。
    """
    for w in range(ctx.num_windows):
        for a in ctx.windows[w].assignments:
            a.operator_name = ""
    ctx.hours_used.clear()
    ctx.lambda_ops.clear()


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
) -> float:
    """更新影子乘子 λ_op：工作时长池稀缺性传导

    对每个干员:
      pool = mood_full/base_burn + (num_windows-1)*interval*avg_recovery
      used = ctx.hours_used[op]
      overflow_ratio = max(0, used - 0.35*pool) / pool

    λ_op = overflow_ratio * base_hourly_value * lambda_damping
    其中 base_hourly_value 为 Mfg CR 槽位的每小时 LMD 等值。
    lambda_damping 在 SolverParams 中可调（默认 0.5），用于控制 λ 敏感度。
    0.35 阈值使 2 班次×12h 的中枢干员（24h > 0.35×50.7≈17.7h）触发惩罚。

    返回最大 λ 值（用于判断收敛——全 0 时终止迭代）。
    """
    mood_full = params.mood_full if params else 24.0
    base_burn = params.base_burn_rate if params else 0.90
    interval = params.interval_hours if params else 8.0
    damping = params.lambda_damping if params else 0.5

    avg_recovery = _estimate_avg_recovery(operators, params)
    pool_base = mood_full / base_burn + (ctx.num_windows - 1) * interval * avg_recovery
    hourly_value = _MFG_CR_BASE_RATE * _CR_LMD_PER_UNIT

    max_lambda = 0.0

    for op in operators:
        used = ctx.hours_used.get(op.name, 0.0)
        if used <= 0.35 * pool_base:
            ctx.lambda_ops[op.name] = 0.0
            continue

        overflow_ratio = max(0.0, used - 0.35 * pool_base) / pool_base
        lambda_val = max(0.0, overflow_ratio * hourly_value * damping)
        if lambda_val > max_lambda:
            max_lambda = lambda_val
        ctx.lambda_ops[op.name] = lambda_val

    return max_lambda


_MFG_CR_BASE_RATE = 1.0 / 3.0
_CR_LMD_PER_UNIT = 1000.0 / 1.3


def _estimate_avg_recovery(
    operators: list,
    params: "SolverParams",
) -> float:
    """估算平均宿舍恢复速率（/h）"""
    from steward_core.mood_flow import MoodContext

    mood_full = params.mood_full if params else 24.0
    sample_size = min(20, len(operators))
    recovery_samples = []

    mock_mc = MoodContext(
        operator_moods={op.name: mood_full for op in operators},
        _op_lookup={op.name: op for op in operators},
    )

    for op in operators[:sample_size]:
        try:
            r = mock_mc.dorm_recovery(op.name, dorm_mates=[op])
            if r > 0:
                recovery_samples.append(r)
        except Exception:
            pass

    return sum(recovery_samples) / max(len(recovery_samples), 1) if recovery_samples else 1.5


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

        pool = compute_buff_pool(
            ctrl_ops,
            suich_count=suich_count,
            dorm_operators=[o for o in dorm_ops if o],
            dorm_level=dorm_level,
            layout=layout,
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
            period_from=f"{w * int(hours + (params.interval_hours if params else 8)):02d}:00",
            period_to=f"{min(w * int(hours + (params.interval_hours if params else 8)) + int(hours) - 1, 23):02d}:59",
        )
        plans.append(plan)

    return SolveResult(plans=plans, autofill_count=0, config_used=SolverConfig(params=params))
