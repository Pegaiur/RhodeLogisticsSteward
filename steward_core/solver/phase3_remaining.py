"""Phase 3b: 剩余设施贪心"""

from steward_core.models import Operator

from .greed import _greedy_remaining


def _phase3_remaining(
    operators: list[Operator],
    assigned_ids: set[str],
    assigned_names: set[str],
    assignments: list,
    op_lookup: dict[str, Operator],
    locked_support: dict[str, set[str]],
    power_names: set[str],
) -> int:
    """Phase 3b: 剩余设施（Power/Reception/Office）贪心

    返回本阶段新增的 autofill_count。
    """
    autofill_count = 0

    # 释放 Office 锁定干员（Phase 1 锁入 assigned_ids，需释放后由 _greedy_remaining 分配）
    for name in locked_support["Office"]:
        if name in op_lookup:
            assigned_ids.discard(op_lookup[name].char_id)
            assigned_names.discard(name)
    priority = power_names | locked_support["Office"]
    remaining = _greedy_remaining(assigned_ids, operators, priority)
    assignments.extend(remaining)
    autofill_count += sum(1 for a in remaining if a.autofill)

    return autofill_count
