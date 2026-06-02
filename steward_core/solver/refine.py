"""局部搜索后处理

在 solve_mvp() 完成后对排班方案做轻量级局部优化。
包含全量排班评估与房间级替换搜索。

目标函数使用 production.calculate() 的真实经济产出（经验+LMD），
而非 evaluate_room() 的效率积分——后者不经过订单机制和赤金供需。
"""

from steward_core.evaluate import evaluate_room
from steward_core.models import Operator, RoomAssignment, ShiftPlan, SolveResult
from steward_core.synergy import control_per_operator_bonus, operator_expected_12h_efficiency

from .context import GlobalContext


def evaluate_full_plan(plan: ShiftPlan, operators: list[Operator], params=None, mood_ctx=None) -> float:
    """评估完整排班方案的总效率积分（用于 A/B 对比）"""
    if params is None:
        from .params import SolverParams
        params = SolverParams()
    T = params.shift_hours

    if not plan.assignments:
        return 0.0

    ctx = GlobalContext.from_plan(plan, operators, params, mood_ctx=mood_ctx)
    op_lookup = {op.name: op for op in operators}

    def _room_ops(room_type: str) -> list[Operator]:
        names = []
        for a in plan.assignments:
            if a.room_type == room_type:
                names.extend(a.operators)
        return [op_lookup[n] for n in names if n in op_lookup]

    total = 0.0
    for a in plan.assignments:
        room_ops = _room_ops(a.room_type)
        if not room_ops:
            continue
        product = a.product or "General"
        ctrl_bonus = control_per_operator_bonus(
            ctx.control_operators, room_ops, product,
            room_type=a.room_type,
        )
        score = evaluate_room(
            room_ops, a.room_type, product, ctx.effective_power, T,
            ctx.global_bonus, ctx.buff_pool,
            ctrl_per_op_bonus=ctrl_bonus,
            all_operators=operators,
            control_operators=ctx.control_operators,
            all_assignments=ctx.all_assignments,
            mood_ctx=mood_ctx,
        )
        total += score

    return total


def _production_score(plan: ShiftPlan, operators: list[Operator], params, mood_ctx=None) -> float:
    """用真实经济产出作为局部搜索的目标函数

    综合经验产出与有效 LMD（已处理赤金供需平衡），
    避免 evaluate_room 效率积分与实际产出脱节的问题。
    """
    from steward_core import production
    from steward_core.production import _RECORD_EXP_PER_UNIT

    dp = production.calculate(
        plan, operators, hours=params.shift_hours,
        external_gold_per_day=params.daily_task_lmd / production._GOLD_LMD_PER_UNIT,
        mood_ctx=mood_ctx,
    )
    exp_value = dp.total_records_per_day * _RECORD_EXP_PER_UNIT
    lmd_value = dp.effective_lmd_per_day
    return exp_value + lmd_value


def local_search_refine(
    result: SolveResult,
    operators: list[Operator],
    config,
) -> SolveResult:
    """对 SolveResult 做局部搜索优化

    算子：逐房间尝试从剩余池中重新生成组合，若全局产出更高则替换。
    接受策略：first-improvement（当前最佳）。
    """
    if config is None or not config.local_search_enabled:
        return result

    params = config.params
    plan = result.plans[0]
    best_plan = plan
    best_score = _production_score(best_plan, operators, params, mood_ctx=config.mood_ctx)
    op_lookup = {op.name: op for op in operators}

    for _round in range(params.local_search_max_rounds):
        improved = False

        for i, assignment in enumerate(best_plan.assignments):
            if assignment.autofill:
                continue

            used_names: set[str] = set()
            for j, a in enumerate(best_plan.assignments):
                if j == i:
                    continue
                used_names.update(a.operators)

            room_type = assignment.room_type
            product = assignment.product
            candidates = [
                op for op in operators
                if op.name not in used_names
                and op.has_skill_for(room_type, product)
            ]

            if len(candidates) < 1:
                continue

            slots = len(assignment.operators)
            if slots == 0:
                continue

            sorted_candidates = sorted(
                candidates,
                key=lambda op: -operator_expected_12h_efficiency(op, room_type, product),
            )

            new_operators = [op.name for op in sorted_candidates[:slots]]
            if new_operators == assignment.operators:
                continue

            new_assignments = list(best_plan.assignments)
            new_assignments[i] = RoomAssignment(
                room_type=assignment.room_type,
                room_index=assignment.room_index,
                operators=new_operators,
                product=assignment.product,
            )
            new_plan = ShiftPlan(
                name=best_plan.name,
                assignments=new_assignments,
                period_from=best_plan.period_from,
                period_to=best_plan.period_to,
            )
            new_score = _production_score(new_plan, operators, params, mood_ctx=config.mood_ctx)

            if new_score > best_score:
                best_plan = new_plan
                best_score = new_score
                improved = True
                break

        if not improved:
            break

    return SolveResult(
        plans=[best_plan],
        autofill_count=result.autofill_count,
        config_used=config,
    )
