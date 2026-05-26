"""排班求解器

核心算法：单班次贪心求解。

设计原则：
- 求解器只依赖 Operator + LayoutConfig，不绑定具体数据源
- 通过可注入的 OpFilter 协议支持后续扩展（Phase 过滤、box 过滤等）
- 求解器本身不处理联动，联动作为后校验由外部模块完成
"""

from typing import Optional, Protocol

from steward_core.models import (
    LayoutConfig,
    Operator,
    RoomAssignment,
    RoomConfig,
    ShiftPlan,
    SolveResult,
)


class OpFilter(Protocol):
    """干员过滤器协议

    后续 Step 2-4 可通过实现此协议注入不同的过滤逻辑：
    - Step 2: 心情/已使用班次过滤
    - Step 3: box 抽样过滤
    - Step 4: 练度（phase）过滤
    """

    def __call__(self, operator: Operator, room: RoomConfig) -> bool: ...


def _always_pass(operator: Operator, room: RoomConfig) -> bool:
    """默认过滤器：不过滤任何干员"""
    return True


def solve_single_shift(
    operators: list[Operator],
    layout: LayoutConfig,
    shift_name: str = "单班次",
    filter_op: Optional[OpFilter] = None,
) -> SolveResult:
    """单班次贪心求解

    按 layout.rooms 的顺序逐个设施分配，每个设施取 candidate 池中效率最高的 N 人。
    先到先得——已被分配的干员后续设施不能再使用。

    Args:
        operators: 全量干员池
        layout: 设施布局配置（含求解优先级顺序）
        shift_name: 班次名称
        filter_op: 可选的干员过滤器，用于注入额外约束

    Returns:
        SolveResult，含一个 ShiftPlan
    """
    if filter_op is None:
        filter_op = _always_pass

    assigned_ids: set[str] = set()
    results: list[RoomAssignment] = []
    autofill_count: int = 0

    for room in layout.rooms:
        # 1. 过滤候选：有该设施技能 + 产物匹配 + 未被占用 + 通过额外过滤器
        candidates: list[tuple[float, Operator]] = []
        for op in operators:
            if op.char_id in assigned_ids:
                continue
            if not op.has_skill_for(room.room_type, room.product):
                continue
            if not filter_op(op, room):
                continue
            eff = op.best_efficiency(room.room_type, room.product)
            candidates.append((eff, op))

        # 2. 按效率降序排列
        candidates.sort(key=lambda x: x[0], reverse=True)

        # 3. 填槽
        taken_names: list[str] = []
        for i in range(room.slots):
            if i < len(candidates):
                _, op = candidates[i]
                taken_names.append(op.name)
                assigned_ids.add(op.char_id)
            else:
                autofill_count += room.slots - i
                break

        assignment = RoomAssignment(
            room_type=room.room_type,
            room_index=room.room_index,
            operators=taken_names,
            product=room.product,
            autofill=len(taken_names) < room.slots,
        )
        results.append(assignment)

    plan = ShiftPlan(name=shift_name, assignments=results)
    return SolveResult(plans=[plan], autofill_count=autofill_count)
