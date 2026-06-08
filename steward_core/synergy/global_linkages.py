"""B层·跨房间配对与全局阵营计数"""

from steward_core.models import LinearSegment, Operator
from .types import CrossRoomPairEntry, GlobalFactionEntry


_B_CROSS_ROOM_PAIR_TABLE: dict[str, CrossRoomPairEntry] = {
    "烈夏": CrossRoomPairEntry("古米", "Trade", 35.0, "CombatRecord", "Mfg"),
    "深巡": CrossRoomPairEntry("乌尔比安", None, 10.0, "Money", "Trade"),
    "贝洛内": CrossRoomPairEntry("伺夜", None, 10.0, "Money", "Trade"),
}


def synergy_cross_room_pair(
    operators: list[Operator],
    room_type: str,
    product: str,
    all_assignments: dict[str, list[Operator]],
    T: float,
    *,
    _all_names: set[str] | None = None,
    _facility_names: dict[str, set[str]] | None = None,
) -> list[LinearSegment]:
    """检查跨设施干员条件配对，为持有者提供效率加成

    B7 体系：干员 A 在某设施时，若干员 B 在另一设施则触发加成。

    _all_names / _facility_names 为可选的预计算结果，
    传入时跳过 all_assignments 遍历。
    """
    names = {op.name for op in operators}
    segments = []

    for holder_name, e in _B_CROSS_ROOM_PAIR_TABLE.items():
        if holder_name not in names:
            continue
        if e.target_room is not None and room_type != e.target_room:
            continue
        if e.target_product is not None and product != e.target_product:
            continue

        if e.target_facility is None:
            if _all_names is not None:
                target_names = _all_names
            else:
                target_names = set()
                for ops in all_assignments.values():
                    target_names.update(op.name for op in ops)
        else:
            if _facility_names is not None:
                target_names = _facility_names.get(e.target_facility, set())
            else:
                target_ops = all_assignments.get(e.target_facility, [])
                target_names = {op.name for op in target_ops}

        if e.target_name in target_names:
            segments.append(LinearSegment(a=e.bonus_per, b=0.0, t_start=0.0, dt=T))

    return segments


_B_GLOBAL_FACTION_TABLE: dict[str, GlobalFactionEntry] = {
    "缪尔赛思": GlobalFactionEntry("group_id", "rhine", 3.0, None, "Power", 5, True),
    "杏仁": GlobalFactionEntry("group_id", "blacksteel", 2.0, "PureGold", "Mfg", 3, False),
    "娜斯提": GlobalFactionEntry("group_id", "rhine", 3.0, "PureGold", "Mfg", 5, False),
}


def synergy_global_faction(
    operators: list[Operator],
    room_type: str,
    product: str,
    all_operators: list[Operator],
    T: float,
    room_tokens: dict[str, float] | None = None,
) -> list[LinearSegment]:
    """B6: 统计全基建范围内特定阵营的干员数量"""
    names = {op.name for op in operators}
    segments = []

    if room_tokens is not None:
        _GLOBAL_TOKEN_MAP = {
            ("group_id", "rhine"): ("rhine_global", "rhine_global_mfg"),
            ("group_id", "blacksteel"): ("blacksteel_global", "blacksteel_global_mfg"),
        }
        for holder_name, e in _B_GLOBAL_FACTION_TABLE.items():
            if holder_name not in names:
                continue
            if room_type != e.target_room:
                continue
            if e.target_product is not None and product != e.target_product:
                continue
            token_pair = _GLOBAL_TOKEN_MAP.get((e.field, e.value))
            if token_pair is None:
                continue
            token_name = token_pair[1] if e.target_product else token_pair[0]
            count = int(room_tokens.get(token_name, 0))
            if e.exclude_self:
                count = max(0, count - 1)
            count = min(count, e.cap)
            bonus = count * e.bonus_per
            if bonus > 0:
                segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))
        return segments

    for holder_name, e in _B_GLOBAL_FACTION_TABLE.items():
        if holder_name not in names:
            continue
        if room_type != e.target_room:
            continue
        if e.target_product is not None and product != e.target_product:
            continue

        count = sum(1 for op in all_operators if getattr(op, e.field, None) == e.value)
        if e.exclude_self:
            count = max(0, count - 1)
        count = min(count, e.cap)
        bonus = count * e.bonus_per
        if bonus > 0:
            segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))

    return segments
