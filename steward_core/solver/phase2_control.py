"""Phase 2: 中枢填充"""

from steward_core.models import Operator, RoomAssignment

from .config import SolverConfig


def _phase2_control(
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
