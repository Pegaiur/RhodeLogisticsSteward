"""剩余设施贪心"""

from steward_core.models import Operator
from steward_core.synergy import _B_GLOBAL_FACTION_TABLE

from .config import SolverConfig
from .greed import _greedy_remaining


def fill_remaining(
    operators: list[Operator],
    assigned_ids: set[str],
    assigned_names: set[str],
    assignments: list,
    op_lookup: dict[str, Operator],
    locked_support: dict[str, set[str]],
    *,
    power_names: set[str],
    config: SolverConfig | None = None,
) -> int:
    """Phase 3b: 剩余设施（Power/Reception/Office）贪心

    返回本阶段新增的 autofill_count。
    """
    if config is None:
        config = SolverConfig()
    autofill_count = 0

    for name in locked_support["Office"]:
        if name in op_lookup:
            assigned_ids.discard(op_lookup[name].char_id)
            assigned_names.discard(name)
    priority = power_names | locked_support["Office"]
    remaining = _greedy_remaining(
        assigned_ids, operators, priority,
        params=config.params, mood_ctx=config.mood_ctx,
    )
    assignments.extend(remaining)
    autofill_count += sum(1 for a in remaining if a.autofill)

    for a in remaining:
        for name in a.operators:
            entry = _B_GLOBAL_FACTION_TABLE.get(name)
            if entry is None:
                continue
            if entry.target_room is not None and a.room_type != entry.target_room:
                continue
            assigned_faction = sum(
                1 for op in operators
                if getattr(op, entry.field, None) == entry.value
                and op.char_id in assigned_ids
            )
            if entry.exclude_self:
                assigned_faction = max(0, assigned_faction - 1)
            needed = entry.cap - assigned_faction
            if needed <= 0:
                continue
            faction_candidates = [
                op for op in operators
                if getattr(op, entry.field, None) == entry.value
                and op.char_id not in assigned_ids
            ]
            for op in faction_candidates[:needed]:
                locked_support["Dormitory"].add(op.name)

    return autofill_count
