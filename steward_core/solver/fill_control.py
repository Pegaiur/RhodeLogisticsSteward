"""中枢填充"""

from steward_core.models import Operator, RoomAssignment

from .config import SolverConfig


def fill_control(
    operators: list[Operator],
    assigned_ids: set[str],
    assigned_names: set[str],
    assignments: list,
    op_lookup: dict[str, Operator],
    locked_support: dict[str, set[str]],
    *,
    ctrl_global_names: set[str],
    config: SolverConfig | None = None,
) -> int:
    """Phase 2: 填充中枢（来自累计支撑干员）

    中枢容量和排序偏置从 config.params 读取，支持 JSON 覆盖。
    返回 0（无 autofill 产生）。
    """
    if config is None:
        config = SolverConfig()
    params = config.params

    ctrl_names = sorted(locked_support["Control"])

    if len(ctrl_names) > params.control_max_slots:
        ranked = []
        for n in ctrl_names:
            if n in op_lookup:
                eff = max(op_lookup[n].best_efficiency("Control"), 0.0)
                ranked.append((eff, n))
            else:
                ranked.append((0.0, n))
        ranked.sort(key=lambda x: -x[0])
        selected = [n for _, n in ranked[:params.control_max_slots]]
        for n in ctrl_names:
            if n not in selected and n in op_lookup:
                assigned_ids.discard(op_lookup[n].char_id)
                assigned_names.discard(n)
        ctrl_names = selected
        locked_support["Control"] = set(selected)

    for n in ctrl_names:
        if n in op_lookup:
            assigned_ids.add(op_lookup[n].char_id)

    if len(ctrl_names) < params.control_max_slots:
        remaining_ctrl = []
        for op in operators:
            if op.char_id in assigned_ids:
                continue
            if not op.has_skill_for("Control"):
                continue
            eff = max(op.best_efficiency("Control"), 0.0)
            if op.name in ctrl_global_names:
                eff += params.control_global_sort_bias
            remaining_ctrl.append((eff, op))
        remaining_ctrl.sort(key=lambda x: -x[0])
        for _eff, op in remaining_ctrl:
            if len(ctrl_names) >= params.control_max_slots:
                break
            if op.char_id not in assigned_ids:
                ctrl_names.append(op.name)
                assigned_ids.add(op.char_id)
                assigned_names.add(op.name)

    assignments.append(RoomAssignment(
        room_type="Control", room_index=0, operators=ctrl_names,
    ))

    return 0
