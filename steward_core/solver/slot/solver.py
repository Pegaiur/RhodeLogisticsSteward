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
    4. 多窗口心情流转：after_shift + dorm recovery
    5. 后处理：局部搜索
    6. 输出多 ShiftPlan SolveResult
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
    """清空所有窗口槽位用于迭代重新求解"""
    for w in range(ctx.num_windows):
        for a in ctx.windows[w].assignments:
            a.operator_name = ""



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
