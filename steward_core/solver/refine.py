"""局部搜索后处理

在 solve_mvp() 完成后对排班方案做轻量级局部优化。
包含全量排班评估与房间级替换搜索。
"""

from steward_core.constants import BASE_POWER_COUNT
from steward_core.evaluate import evaluate_room
from steward_core.models import Operator, RoomAssignment, ShiftPlan, SolveResult
from steward_core.synergy import (
    compute_control_global_bonus,
    compute_buff_pool,
    _has_power_count_modifier,
    control_per_operator_bonus,
    _B_ROSEMARY, _B_EBENHOLZ,
)

T = 12.0


def evaluate_full_plan(plan: ShiftPlan, operators: list[Operator]) -> float:
    """评估完整排班方案的总效率积分

    重建全局上下文（中枢/宿舍/buff_pool）后逐间调用 evaluate_room。
    结果用于局部搜索中的方案比较。
    """
    if not plan.assignments:
        return 0.0

    op_lookup = {op.name: op for op in operators}

    # 提取各设施的干员
    def _room_ops(room_type: str) -> list[Operator]:
        names = []
        for a in plan.assignments:
            if a.room_type == room_type:
                names.extend(a.operators)
        return [op_lookup[n] for n in names if n in op_lookup]

    control_ops = _room_ops("Control")
    dorm_ops = _room_ops("Dormitory")

    # 全局上下文
    global_bonus = compute_control_global_bonus(control_ops)

    has_rosmontis = any(
        a.room_type == "Mfg" and "迷迭香" in a.operators
        for a in plan.assignments
    )
    has_ebnhlz = any(
        a.room_type == "Trade" and "黑键" in a.operators
        for a in plan.assignments
    )

    office_perception = 0
    if any(
        a.room_type == "Office" and "絮雨" in a.operators
        for a in plan.assignments
    ):
        office_perception = 20

    buff_pool = compute_buff_pool(
        control_ops, suich_count=5,
        dorm_operators=dorm_ops, dorm_level=5,
        has_rosmontis_in_mfg=has_rosmontis,
        has_ebnhlz_in_trade=has_ebnhlz,
        ling_mood_below_12=has_rosmontis,
        perception_from_office=office_perception,
    )

    effective_power = BASE_POWER_COUNT + sum(
        1 for op in operators
        if _has_power_count_modifier(op)
    )

    # 构建 all_assignments（B7 跨房间配对用）
    all_assignments: dict[str, list[Operator]] = {}
    for a in plan.assignments:
        ops = _room_ops(a.room_type)
        if a.room_type not in all_assignments:
            all_assignments[a.room_type] = []
        all_assignments[a.room_type].extend(ops)

    total = 0.0
    for a in plan.assignments:
        room_ops = _room_ops(a.room_type)
        if not room_ops:
            continue
        product = a.product or "General"
        ctrl_bonus = control_per_operator_bonus(
            control_ops, room_ops, product,
            room_type=a.room_type,
        )
        score = evaluate_room(
            room_ops, a.room_type, product, effective_power, T,
            global_bonus, buff_pool,
            ctrl_per_op_bonus=ctrl_bonus,
            all_operators=operators,
            control_operators=control_ops,
            all_assignments=all_assignments,
        )
        total += score

    return total


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

    plan = result.plans[0]
    best_plan = plan
    best_score = evaluate_full_plan(best_plan, operators)
    op_lookup = {op.name: op for op in operators}

    for _round in range(config.local_search_max_rounds):
        improved = False

        for i, assignment in enumerate(best_plan.assignments):
            if assignment.autofill:
                continue

            # 收集已被其他房间占用的干员
            used_names: set[str] = set()
            for j, a in enumerate(best_plan.assignments):
                if j == i:
                    continue
                used_names.update(a.operators)

            # 构造此房间的可用候选池
            room_type = assignment.room_type
            product = assignment.product
            candidates = [
                op for op in operators
                if op.name not in used_names
                and op.has_skill_for(room_type, product)
            ]

            if len(candidates) < 1:
                continue

            # 尝试不同槽位数量的组合
            slots = len(assignment.operators)
            if slots == 0:
                continue

            # 简单贪心：从候选人中按 best_efficiency 取 top-k 尝试替换
            sorted_candidates = sorted(
                candidates,
                key=lambda op: -op.best_efficiency(room_type, product),
            )

            new_operators = [op.name for op in sorted_candidates[:slots]]
            if new_operators == assignment.operators:
                continue

            # 构造新排班并评估
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
            new_score = evaluate_full_plan(new_plan, operators)

            if new_score > best_score:
                best_plan = new_plan
                best_score = new_score
                improved = True
                break  # first-improvement

        if not improved:
            break

    return SolveResult(
        plans=[best_plan],
        autofill_count=result.autofill_count,
        config_used=config,
    )
