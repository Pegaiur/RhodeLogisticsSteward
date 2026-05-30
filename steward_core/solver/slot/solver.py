"""SlotSolver — 槽位加工模型求解引擎

直接实现 slot-processing-model-draft.md §9.5 混合状态迭代策略。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from steward_core.models import LayoutConfig, SolveResult
from steward_core.solver.config import SolverConfig
from steward_core.solver.refine import local_search_refine
from steward_core.solver.slot.context import SlotContext, StateVector
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


def solve_slot(
    operators: list["Operator"],
    params: "SolverParams",
    layout: LayoutConfig | None = None,
    mood_ctx: "MoodContext | None" = None,
    max_iterations: int = _MAX_ITERATIONS,
) -> SolveResult:
    """槽位加工模型求解入口

    1. 初始化 SlotContext（冷启动或空分配）
    2. 迭代：Phase A/B/C/D + D[d]反馈 + 记忆收敛
    3. 后处理：局部搜索
    4. 输出 SolveResult
    """
    if layout is None:
        layout = LayoutConfig.layout_243()

    ctx = SlotContext.from_layout(operators, layout, params)

    visited = set()
    best_ctx = None
    best_P = 0.0

    for iteration in range(max_iterations):
        for w in range(ctx.num_windows):
            phase_mfg(ctx, w, mood_ctx=mood_ctx)
            phase_trade(ctx, w, mood_ctx=mood_ctx)

            D = compute_partial_derivatives(ctx, w)
            ctx.windows[w].D = D

            phase_control(ctx, w, D)
            phase_remaining(ctx, w, D)

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

    if best_ctx is None:
        best_ctx = ctx

    result = _ctx_to_result(best_ctx, operators, params)
    config = SolverConfig(params=params)
    result = local_search_refine(result, operators, config)
    return result


def _estimate_total_production(
    ctx: SlotContext,
    mood_ctx: "MoodContext | None" = None,
) -> float:
    """估算总产能（用于收敛检测的近似值）"""
    from steward_core.evaluate import evaluate_room
    from steward_core.synergy import (
        compute_control_global_bonus,
        control_per_operator_bonus,
    )

    total = 0.0
    params = ctx.params
    hours = params.shift_hours if params else 12.0

    from steward_core.synergy.buff_pool import compute_buff_pool
    ctrl_names = ctx.ops_of_type(0, "Control")
    ctrl_ops = [ctx.op_lookup[n] for n in ctrl_names if n in ctx.op_lookup]
    global_bonus = compute_control_global_bonus(ctrl_ops)

    dorm_names = ctx.ops_of_type(0, "Dormitory")
    dorm_ops = [ctx.op_lookup[n] for n in dorm_names if n in ctx.op_lookup]

    pool = compute_buff_pool(
        ctrl_ops,
        suich_count=params.suich_count if params else 5,
        dorm_operators=[o for o in dorm_ops if o],
        dorm_level=params.dorm_level if params else 5,
        layout=ctx.layout if ctx.layout else LayoutConfig.layout_243(),
    )

    for facility_type in ("Mfg", "Trade"):
        rooms_done = set()
        for a in ctx.windows[0].assignments:
            if a.facility_type != facility_type:
                continue
            key = (a.facility_type, a.room_index)
            if key in rooms_done:
                continue
            rooms_done.add(key)

            room_names = ctx.room_ops(0, a.facility_type, a.room_index)
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
            total += score

    return total


def _ctx_to_result(
    ctx: SlotContext,
    operators: list,
    params: "SolverParams",
) -> SolveResult:
    """将 SlotContext 转换为 SolveResult（兼容旧接口）"""
    from steward_core.models import RoomAssignment, ShiftPlan

    assignments = []
    rooms_done = set()
    for a in ctx.windows[0].assignments:
        key = (a.facility_type, a.room_index)
        if key in rooms_done:
            continue
        rooms_done.add(key)
        names = ctx.room_ops(0, a.facility_type, a.room_index)
        assignments.append(RoomAssignment(
            room_type=a.facility_type,
            room_index=a.room_index,
            operators=names,
            product=a.product,
        ))

    hours = params.shift_hours if params else 12.0
    half_hours = int(hours / 2.0)
    plan = ShiftPlan(
        name=f"Slot-{int(hours)}h",
        assignments=assignments,
        period_from=f"{half_hours:02d}:00",
        period_to=f"{half_hours + int(hours) - 1:02d}:59",
    )

    return SolveResult(plans=[plan], autofill_count=0, config_used=None)
