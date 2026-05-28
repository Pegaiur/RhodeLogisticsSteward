"""Phase 4: 宿舍填充"""

from steward_core.models import Operator, RoomAssignment


def _phase4_dorm(
    operators: list[Operator],
    assigned_ids: set[str],
    assignments: list,
    op_lookup: dict[str, Operator],
    locked_support: dict[str, set[str]],
    dorm_names_list: list[str],
) -> int:
    """Phase 4: 宿舍填充（优先B层生成者 → 任意填充至20人）

    返回本阶段新增的 autofill_count。
    """
    autofill_count = 0

    dorm_names: list[str] = list(locked_support["Dormitory"])

    for name in dorm_names_list:
        if name not in dorm_names and name in op_lookup and op_lookup[name].char_id not in assigned_ids:
            dorm_names.append(name)
            assigned_ids.add(op_lookup[name].char_id)

    for op in operators:
        if len(dorm_names) >= 20:
            break
        if op.char_id not in assigned_ids:
            dorm_names.append(op.name)
            assigned_ids.add(op.char_id)

    for room_idx in range(4):
        start = room_idx * 5
        room_ops = dorm_names[start:start + 5] if start < len(dorm_names) else []
        assignments.append(RoomAssignment(
            room_type="Dormitory", room_index=room_idx,
            operators=room_ops, autofill=(len(room_ops) < 5),
        ))
        if len(room_ops) < 5:
            autofill_count += 1

    return autofill_count
