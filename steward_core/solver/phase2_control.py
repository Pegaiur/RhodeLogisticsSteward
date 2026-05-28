"""Phase 2: 中枢填充"""

from steward_core.models import Operator, RoomAssignment


def _phase2_control(
    operators: list[Operator],
    assigned_ids: set[str],
    assignments: list,
    locked_support: dict[str, set[str]],
    op_lookup: dict[str, Operator],
    ctrl_global_names: set[str],
    ctrl_global_sort_bias: float,
) -> list[str]:
    """Phase 2: 填充中枢（来自累计支撑干员）

    返回 ctrl_names 供 Phase 3a 使用。
    """
    ctrl_names = sorted(locked_support["Control"])
    for n in ctrl_names:
        if n in op_lookup:
            assigned_ids.add(op_lookup[n].char_id)

    # 补满中枢至 5 人：从未分配的 Control 技能持有者中贪心选取
    if len(ctrl_names) < 5:
        remaining_ctrl = []
        for op in operators:
            if op.char_id in assigned_ids:
                continue
            if not op.has_skill_for("Control"):
                continue
            eff = max(op.best_efficiency("Control"), 0.0)
            if op.name in ctrl_global_names:
                eff += ctrl_global_sort_bias
            remaining_ctrl.append((eff, op))
        remaining_ctrl.sort(key=lambda x: -x[0])
        for _eff, op in remaining_ctrl:
            if len(ctrl_names) >= 5:
                break
            if op.char_id not in assigned_ids:
                ctrl_names.append(op.name)
                assigned_ids.add(op.char_id)

    assignments.append(RoomAssignment(
        room_type="Control", room_index=0, operators=ctrl_names,
    ))

    return ctrl_names
