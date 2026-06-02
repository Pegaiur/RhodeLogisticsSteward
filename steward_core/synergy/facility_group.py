"""B层·设施 group 计数加成

统计基建中至少有一名指定 group_id 干员进驻的设施数量，
为持有对应 buff 的干员提供效率加成。

覆盖 buff: trade_ord_spd&tag[010]（真言精英小队）、
         hire_spd_tag[000]（凯尔希异格泰拉的方舟）、
         trade_ord_spd&tag[020]（风絮岁干员）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from steward_core.models import LinearSegment
from .types import FacilityGroupEntry

if TYPE_CHECKING:
    from steward_core.models import Operator

_FACILITY_GROUP_TABLE: dict[str, FacilityGroupEntry] = {
    "trade_ord_spd&tag[010]": FacilityGroupEntry(
        "trade_ord_spd&tag[010]", "elite", 2.0, 10, "Trade",
    ),
    "hire_spd_tag[000]": FacilityGroupEntry(
        "hire_spd_tag[000]", "elite", 4.0, 5, "Office",
    ),
    "trade_ord_spd&tag[020]": FacilityGroupEntry(
        "trade_ord_spd&tag[020]", "sui", 4.0, 5, "Trade",
    ),
}


def count_facilities_with_group(
    all_assignments: dict[str, list["Operator"]],
    group_id: str,
) -> int:
    """统计至少有一名 group_id 干员进驻的设施数量"""
    count = 0
    for ops in all_assignments.values():
        if any(op.group_id == group_id for op in ops):
            count += 1
    return count


def compute_facility_group_bonus(
    op: "Operator",
    all_assignments: dict[str, list["Operator"]],
    room_type: str = "",
) -> float:
    """计算单个干员的 facility_group 条件加成 (%)

    供 contribution.py _office_contribution() 使用。
    room_type 用于过滤仅匹配当前设施的 entry，空字符串则不过滤。
    """
    bonus = 0.0
    for sk in op.skills:
        entry = _FACILITY_GROUP_TABLE.get(sk.buff_id)
        if entry is None:
            continue
        if room_type and entry.target_room != room_type:
            continue
        n = count_facilities_with_group(all_assignments, entry.group_id)
        bonus += min(n, entry.cap_facilities) * entry.bonus_per_facility
    return bonus


def synergy_facility_group(
    operators: list["Operator"],
    room_type: str,
    all_assignments: dict[str, list["Operator"]],
    T: float = 12.0,
) -> list[LinearSegment]:
    """评估房间的 facility_group 加成段

    供 evaluate.py 使用。遍历房间中每个干员，匹配 _FACILITY_GROUP_TABLE，
    按 target_room 过滤，返回常数加成段。
    """
    segments: list[LinearSegment] = []
    for op in operators:
        bonus = 0.0
        for sk in op.skills:
            entry = _FACILITY_GROUP_TABLE.get(sk.buff_id)
            if entry is None:
                continue
            if entry.target_room and entry.target_room != room_type:
                continue
            n = count_facilities_with_group(all_assignments, entry.group_id)
            bonus += min(n, entry.cap_facilities) * entry.bonus_per_facility
        if bonus > 0:
            segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))
    return segments
