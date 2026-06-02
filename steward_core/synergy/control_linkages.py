"""C层·中枢全局效率与 per-operator 加成

表驱动设计——无条件/条件型全局/PerOp 三表分离，
替代散落 if 分支。新增干员只需加表数据。
"""

from dataclasses import dataclass

from steward_core.models import Operator
from .types import ControlConditionalEntry, ControlPerOpEntry, ControlTradeLimitEntry, GlobalBonusEntry
from .helpers import _OP_PLATFORM_NAMES, _is_knight

# ─── 表 A: 无条件全局效率 ─────────────────────────────────────────

_C_CONTROL_GLOBAL_TABLE: dict[str, GlobalBonusEntry] = {
    "凯尔希":   GlobalBonusEntry(2.0, 0.0),
    "Mon3tr":   GlobalBonusEntry(2.0, 0.0),
    "阿米娅":   GlobalBonusEntry(0.0, 7.0),
    "诗怀雅":   GlobalBonusEntry(0.0, 7.0),
    "阿斯卡纶": GlobalBonusEntry(0.0, 7.0),
    "明椒":     GlobalBonusEntry(0.0, 7.0),
}
"""无条件全局制造/贸易加成 — 同种取最高"""

# ─── 表 B: 条件型全局效率 ─────────────────────────────────────────

_CONTROL_CONDITIONAL_TABLE: dict[str, ControlConditionalEntry | list[ControlConditionalEntry]] = {
    "望": [
        ControlConditionalEntry(
            condition="望_trade", condition_names=frozenset(),
            mfg_bonus=0.0, trade_bonus=7.0,
        ),
        ControlConditionalEntry(
            condition="望_mfg", condition_names=frozenset(),
            mfg_bonus=2.0, trade_bonus=0.0,
        ),
    ],
    "布丁": ControlConditionalEntry(
        condition="作业平台", condition_names=frozenset(),
        mfg_bonus=2.0, trade_bonus=0.0,
    ),
    "麒麟R夜刀": ControlConditionalEntry(
        condition="MH队友", condition_names=frozenset({"火龙S黑角"}),
        mfg_bonus=2.0, trade_bonus=0.0,
    ),
    "火龙S黑角": ControlConditionalEntry(
        condition="MH队友", condition_names=frozenset({"麒麟R夜刀"}),
        mfg_bonus=0.0, trade_bonus=7.0,
    ),
    "斩业星熊": ControlConditionalEntry(
        condition="龙门近卫局队友",
        condition_names=frozenset({"陈", "星熊", "诗怀雅"}),
        mfg_bonus=3.0, trade_bonus=0.0,
    ),
}
"""条件型全局效率 — 中枢干员名 → ControlConditionalEntry"""

# ─── 表 C: Per-operator 条件加成 ──────────────────────────────────

_CONTROL_PER_OP_TABLE: dict[str, list[ControlPerOpEntry]] = {
    "焰尾": [
        ControlPerOpEntry("Mfg", "per_op", "group_id", "pinus", 10.0, "CombatRecord"),
        ControlPerOpEntry("Mfg", "per_op", "group_id", "pinus", -10.0, "PureGold"),
    ],
    "薇薇安娜": [
        ControlPerOpEntry("Mfg", "per_op", "is_knight", "", 7.0, None),
    ],
    "涤火杰西卡": [
        ControlPerOpEntry("Mfg", "per_op", "group_id", "blacksteel", 5.0, None),
    ],
    "八幡海铃": [
        ControlPerOpEntry("Trade", "per_op", "nation_id", "siracusa", 5.0, None),
    ],
    "凛御银灰": [
        ControlPerOpEntry("Trade", "per_room", "count_ge", "3", 10.0, None),
    ],
    "戴菲恩": [
        ControlPerOpEntry("Trade", "per_op", "group_id", "glasgow", 10.0, None),
    ],
}
"""per-operator 条件加成 — 中枢干员名 → 加成条目列表"""


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
    """
    if power_platforms is None:
        power_platforms = {}

    names = {op.name for op in control_operators}
    best_mfg = 0.0
    best_trade = 0.0

    for name in names:
        entry = _C_CONTROL_GLOBAL_TABLE.get(name)
        if entry:
            best_mfg = max(best_mfg, entry.mfg_bonus)
            best_trade = max(best_trade, entry.trade_bonus)

    for name in names:
        ce_raw = _CONTROL_CONDITIONAL_TABLE.get(name)
        if not ce_raw:
            continue
        ces = ce_raw if isinstance(ce_raw, list) else [ce_raw]
        for ce in ces:
            if _eval_global_condition(ce, names, power_platforms, mfg_rooms, trade_rooms, power_rooms):
                best_mfg = max(best_mfg, ce.mfg_bonus)
                best_trade = max(best_trade, ce.trade_bonus)

    return GlobalBonus(mfg_bonus=best_mfg, trade_bonus=best_trade)


def _eval_global_condition(
    ce: ControlConditionalEntry,
    ctrl_names: set[str],
    platforms: dict[str, bool],
    mfg: int,
    trade: int,
    power: int,
) -> bool:
    """评估条件型全局效率条目是否满足"""
    cond = ce.condition
    if cond == "望_trade":
        return (trade + power) >= mfg
    elif cond == "望_mfg":
        return mfg > (trade + power)
    elif cond == "作业平台":
        count = sum(1 for n in _OP_PLATFORM_NAMES if platforms.get(n))
        return count >= 2
    elif cond == "MH队友":
        return bool(ctrl_names & ce.condition_names)
    elif cond == "龙门近卫局队友":
        return bool(ctrl_names & ce.condition_names)
    return False


def control_per_operator_bonus(
    control_ops: list["Operator"],
    room_ops: list["Operator"],
    product: str,
    room_type: str = "Mfg",
) -> float:
    """中枢干员对当前房间的条件型 per-operator 加成（百分值）

    表 C 驱动：焰尾/薇薇安娜/涤火杰西卡/八幡海铃/凛御银灰/戴菲恩。
    """
    bonus = 0.0
    ctrl_names = {op.name for op in control_ops}

    for name in ctrl_names:
        entries = _CONTROL_PER_OP_TABLE.get(name)
        if not entries:
            continue
        for e in entries:
            if e.room_type != room_type:
                continue
            if e.product is not None and e.product != product:
                continue
            bonus += _eval_per_op(e, room_ops)

    return bonus


def _eval_per_op(e: ControlPerOpEntry, room_ops: list["Operator"]) -> float:
    """计算单条 per-operator 条目的加成值"""
    if e.scope == "per_op":
        count = 0
        if e.condition_field == "group_id":
            count = sum(1 for op in room_ops if op.group_id == e.condition_value)
        elif e.condition_field == "nation_id":
            count = sum(1 for op in room_ops if op.nation_id == e.condition_value)
        elif e.condition_field == "is_knight":
            count = sum(1 for op in room_ops if _is_knight(op))
        else:
            return 0.0
        return count * e.bonus_per
    elif e.scope == "per_room":
        if e.condition_field == "count_ge":
            required = int(e.condition_value)
            karlan_count = sum(1 for op in room_ops if op.group_id == "karlan")
            if karlan_count >= required:
                return e.bonus_per
        return 0.0
    return 0.0
