"""C层·中枢全局效率与 per-operator 加成"""

from dataclasses import dataclass

from steward_core.models import LinearSegment, Operator
from .types import GlobalBonusEntry, ControlTradeLimitEntry
from .helpers import (
    _MH_NAMES, _LUNG_MEN_GUARD_NAMES, _BLACKSTEEL_HOLDERS,
    _BLACKSTEEL_GROUP, _PINUS_GROUP, _KNIGHT_NAMES, _OP_PLATFORM_NAMES,
    _is_knight,
)


_C_CONTROL_GLOBAL_TABLE: dict[str, GlobalBonusEntry] = {
    "凯尔希": GlobalBonusEntry(2.0, 0.0),
    "Mon3tr": GlobalBonusEntry(2.0, 0.0),
    "阿米娅": GlobalBonusEntry(0.0, 7.0),
    "诗怀雅": GlobalBonusEntry(0.0, 7.0),
    "佩佩": GlobalBonusEntry(0.0, 7.0),
    "阿斯卡纶": GlobalBonusEntry(0.0, 7.0),
}

_CONTROL_TRADE_LIMIT_TABLE: dict[str, ControlTradeLimitEntry] = {
    "维什戴尔": ControlTradeLimitEntry(target_name="赫德雷", bonus_e0=1, bonus_e2=2),
}
"""中枢→贸易站订单上限联动表

中枢干员名 → ControlTradeLimitEntry
当 target_name 在贸易站时，根据中枢干员精英阶段提供订单上限加成。
"""


@dataclass
class GlobalBonus:
    """中枢全局效率加成"""
    mfg_bonus: float = 0.0
    trade_bonus: float = 0.0


def compute_control_global_bonus(
    control_operators: list[Operator],
    power_platforms: dict[str, bool] | None = None,
    mfg_rooms: int = 0,
    trade_rooms: int = 0,
    power_rooms: int = 0,
) -> GlobalBonus:
    """计算中枢干员提供的全局制造/贸易加成

    同种效果取最高值（游戏内描述"同种效果取最高"）。

    望的技能为条件型——外势(trade_rooms + power_rooms) >= 实地(mfg_rooms)
    时仅提供贸易 +7%，实地 > 外势时仅提供制造 +2%，二者不共存。
    """
    if power_platforms is None:
        power_platforms = {}

    names = {op.name for op in control_operators}
    best_mfg = 0.0
    best_trade = 0.0

    for name in names:
        if name in _C_CONTROL_GLOBAL_TABLE:
            entry = _C_CONTROL_GLOBAL_TABLE[name]
            m, t = entry.mfg_bonus, entry.trade_bonus
            best_mfg = max(best_mfg, m)
            best_trade = max(best_trade, t)

    if "望" in names:
        waishi = trade_rooms + power_rooms
        shidi = mfg_rooms
        if waishi >= shidi:
            best_trade = max(best_trade, 7.0)
        else:
            best_mfg = max(best_mfg, 2.0)

    if "布丁" in names:
        platform_count = sum(1 for n in _OP_PLATFORM_NAMES if power_platforms.get(n))
        if platform_count >= 2:
            best_mfg = max(best_mfg, 2.0)

    if "麒麟R夜刀" in names:
        if any(n in _MH_NAMES and n != "麒麟R夜刀" for n in names):
            best_mfg = max(best_mfg, 2.0)

    if "炼金术士" in names:
        if any(n in _MH_NAMES and n != "炼金术士" for n in names):
            best_trade = max(best_trade, 7.0)

    if "斩业星熊" in names:
        if any(n in _LUNG_MEN_GUARD_NAMES and n != "斩业星熊" for n in names):
            best_mfg = max(best_mfg, 3.0)

    return GlobalBonus(mfg_bonus=best_mfg, trade_bonus=best_trade)


def control_per_operator_bonus(
    control_ops: list["Operator"],
    room_ops: list["Operator"],
    product: str,
    room_type: str = "Mfg",
) -> float:
    """中枢干员对当前房间的条件型 per-operator 加成（百分值）

    焰尾: 每个红松骑士团 Mfg 干员 → CR+10%, PG-10%
    薇薇安娜: 每个骑士 Mfg 干员 → +7%
    老友相聚: 每黑钢国际 Mfg 干员 → +5%
    八幡海铃: 每个叙拉古 Trade 干员 → +5%
    银灰异格: Trade 房间含 ≥3 谢拉格干员 → +10%
    戴菲恩: Trade 房间每名格拉斯哥帮干员 → +10%
    """
    bonus = 0.0
    control_names = {op.name for op in control_ops}

    if "焰尾" in control_names:
        for op in room_ops:
            if op.group_id == _PINUS_GROUP:
                if product == "CombatRecord":
                    bonus += 10.0
                elif product == "PureGold":
                    bonus -= 10.0

    if "薇薇安娜" in control_names:
        for op in room_ops:
            if _is_knight(op):
                bonus += 7.0

    if room_type == "Mfg":
        for name in control_names:
            if name in _BLACKSTEEL_HOLDERS:
                for op in room_ops:
                    if op.group_id == _BLACKSTEEL_GROUP:
                        bonus += 5.0
                break

    if "八幡海铃" in control_names and room_type == "Trade":
        for op in room_ops:
            if op.nation_id == "siracusa":
                bonus += 5.0

    if "银灰异格" in control_names and room_type == "Trade":
        karlan_count = sum(1 for op in room_ops if op.group_id == "karlan")
        if karlan_count >= 3:
            bonus += 10.0

    if "戴菲恩" in control_names and room_type == "Trade":
        for op in room_ops:
            if op.group_id == "glasgow":
                bonus += 10.0

    return bonus
