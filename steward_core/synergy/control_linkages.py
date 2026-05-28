"""C层·中枢全局效率与 per-operator 加成"""

from dataclasses import dataclass

from steward_core.models import LinearSegment, Operator
from .types import GlobalBonusEntry
from .helpers import (
    _MH_NAMES, _LUNG_MEN_GUARD_NAMES, _BLACKSTEEL_HOLDERS,
    _BLACKSTEEL_GROUP, _PINUS_GROUP, _KNIGHT_NAMES, _OP_PLATFORM_NAMES,
    _is_knight,
)


_C_CONTROL_GLOBAL_TABLE: dict[str, GlobalBonusEntry] = {
    "凯尔希": GlobalBonusEntry(2.0, 0.0),
    "Mon3tr": GlobalBonusEntry(2.0, 0.0),
    "望": GlobalBonusEntry(2.0, 7.0),
}


@dataclass
class GlobalBonus:
    """中枢全局效率加成"""
    mfg_bonus: float = 0.0
    trade_bonus: float = 0.0


def compute_control_global_bonus(
    control_operators: list[Operator],
    power_platforms: dict[str, bool] | None = None,
) -> GlobalBonus:
    """计算中枢干员提供的全局制造/贸易加成

    同种效果取最高值（游戏内描述"同种效果取最高"）。
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

    return bonus
