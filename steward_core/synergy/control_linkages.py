"""C层·中枢全局效率与 per-operator 加成

表驱动设计——无条件/条件型全局/PerOp 三表分离，
替代散落 if 分支。新增干员只需加表数据。
"""

from dataclasses import dataclass

from steward_core.models import Operator
from .types import ControlConditionalEntry, ControlPerOpEntry, ControlReceptionEntry, ControlTradeLimitEntry, ClusterHuntingEntry, GlobalBonusEntry
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
    "灵知": [
        ControlPerOpEntry("Trade", "per_op", "group_id", "karlan", -15.0, None),
    ],
}
"""per-operator 条件加成 — 中枢干员名 → 加成条目列表"""

# ─── 表 E: 集群狩猎 ──────────────────────────────────────────────

_CLUSTER_HUNTING_TABLE: dict[str, ClusterHuntingEntry] = {
    "歌蕾蒂娅": ClusterHuntingEntry(
        buff_ids=frozenset({"control_mp_aegir2[000]", "control_mp_aegir2[010]"}),
        bonus_per=10.0,
        max_bonus=90.0,
        group_id="abyssal",
    ),
}
"""集群狩猎加成表 — 中枢干员名 → (buff_ids, bonus_per, max_bonus, group_id)

每有 1 个 group_id 干员进驻 Mfg 站，每个有该 group_id 的 Mfg 站 +bonus_per%，
上限 max_bonus%，与其他归零自动化互斥。
"""


def compute_cluster_hunting_bonus(
    control_ops: list["Operator"],
    all_mfg_assignments: dict[int, list[str]],
    op_lookup: dict[str, "Operator"],
    this_room_index: int,
) -> float:
    """计算集群狩猎对该 Mfg 站的加成（百分值）

    Args:
        control_ops: 中枢干员列表
        all_mfg_assignments: {room_index: [operator_names]} 全 Mfg 站分配
        op_lookup: 干员名 → Operator 查找表
        this_room_index: 当前房间索引

    Returns:
        百分加成值（0 表示该站无深海猎人或中枢无集群狩猎提供者）
    """
    if not all_mfg_assignments:
        return 0.0

    # 该房间无深海猎人 → 0
    this_room_ops = all_mfg_assignments.get(this_room_index, [])
    if not any(op_lookup.get(n) and op_lookup[n].has_group("abyssal") for n in this_room_ops):
        return 0.0

    # 检测中枢是否有集群狩猎提供者
    ctrl_names = {op.name for op in control_ops}
    bonus_per = 0.0
    max_bonus = 0.0
    found = False

    for name in ctrl_names:
        entry = _CLUSTER_HUNTING_TABLE.get(name)
        if entry is None:
            continue
        op = op_lookup.get(name)
        if op is None:
            continue
        if not any(sk.buff_id in entry.buff_ids for sk in op.skills):
            continue
        bonus_per = entry.bonus_per
        max_bonus = entry.max_bonus
        found = True
        break

    if not found:
        return 0.0

    # 全基建 Mfg 站统计深海猎人数
    total_abyssal = 0
    for room_idx, names in all_mfg_assignments.items():
        for n in names:
            op = op_lookup.get(n)
            if op and op.has_group("abyssal"):
                total_abyssal += 1

    return min(total_abyssal * bonus_per, max_bonus)


def has_cluster_hunting(control_ops: list["Operator"]) -> bool:
    """中枢是否存在集群狩猎提供者"""
    for op in control_ops:
        entry = _CLUSTER_HUNTING_TABLE.get(op.name)
        if entry is None:
            continue
        if any(sk.buff_id in entry.buff_ids for sk in op.skills):
            return True
    return False


def get_disabled_mfg_mechs(control_ops: list["Operator"]) -> "frozenset[str]":
    """返回因中枢 buff 存在而被禁用的 Mfg 效率机制名集合

    当前: 集群狩猎激活 → 配合意识 (combo_amplify) 被禁用
    """
    disabled: set[str] = set()
    if has_cluster_hunting(control_ops):
        disabled.add("combo_amplify")
    return frozenset(disabled)


def is_cluster_hunting_zeroed(room_ops: list["Operator"], room_type: str) -> bool:
    """检测房间内是否存在归零者（自动化/仿生海龙）清零集群狩猎

    manu_prod_spd&power[*] buff 持有者在房间内 → 集群狩猎加成归零。
    """
    if room_type != "Mfg":
        return False
    from .mfg_linkages import _POWER_BUFF_BONUS
    for op in room_ops:
        for sk in op.skills:
            if sk.buff_id in _POWER_BUFF_BONUS:
                return True
    return False


_CONTROL_TRADE_LIMIT_TABLE: dict[str, ControlTradeLimitEntry] = {
    "维什戴尔": ControlTradeLimitEntry(target_name="赫德雷", bonus_e0=1, bonus_e2=2),
}
"""中枢→贸易站订单上限联动表

中枢干员名 → ControlTradeLimitEntry
当 target_name 在贸易站时，根据中枢干员精英阶段提供订单上限加成。
"""

# ─── 表 D: 中枢→会客室加成 ────────────────────────────────────────

_CONTROL_RECEPTION_TABLE: dict[str, ControlReceptionEntry | list[ControlReceptionEntry]] = {
    "老鲤": ControlReceptionEntry("unconditional", "", 0, 25.0),
    "魔王": ControlReceptionEntry("unconditional", "", 0, 15.0),
    "摆渡人": ControlReceptionEntry("per_nation", "minos", 25.0, 5.0),
    "维什戴尔": ControlReceptionEntry("per_faction_room", "伊内丝", 0, 5.0),
    "怒潮凛冬": ControlReceptionEntry("per_nation", "ursus", 0, 10.0),
}
"""中枢→会客室全局加成 — 干员名 → ControlReceptionEntry"""


def compute_control_reception_bonus(
    control_ops: list["Operator"],
    ctx: "SlotContext",
    window_idx: int,
    *,
    reception_names: set[str] | None = None,
) -> float:
    """计算中枢干员对会客室的全局速度加成（%）

    无条件类: 同种取最高
    per_nation 类: 全基建统计 nation_id 干员数 × bonus%, 不超过 cap
    per_faction_room 类: 目标干员在 Reception 时 +bonus%
    reception_names: 会客室干员名集合; 若为 None 则从 ctx 读取
    """
    names = {op.name for op in control_ops}
    best_uncond = 0.0
    total_cond = 0.0

    if reception_names is None:
        reception_names = set(ctx.ops_of_type(window_idx, "Reception"))

    for name in names:
        entry_raw = _CONTROL_RECEPTION_TABLE.get(name)
        if not entry_raw:
            continue
        entries = entry_raw if isinstance(entry_raw, list) else [entry_raw]
        for e in entries:
            if e.condition == "unconditional":
                best_uncond = max(best_uncond, e.bonus_per)
            elif e.condition == "per_nation":
                count = sum(
                    1 for op in ctx.op_lookup.values()
                    if getattr(op, "nation_id", None) == e.condition_value
                )
                val = min(count * e.bonus_per, e.cap) if e.cap > 0 else count * e.bonus_per
                total_cond += val
            elif e.condition == "per_faction_room":
                if e.condition_value in reception_names:
                    total_cond += e.bonus_per

    return best_uncond + total_cond


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
            count = sum(1 for op in room_ops if op.has_group(e.condition_value))
        elif e.condition_field == "nation_id":
            count = sum(1 for op in room_ops if op.has_nation(e.condition_value))
        elif e.condition_field == "is_knight":
            count = sum(1 for op in room_ops if _is_knight(op))
        else:
            return 0.0
        return count * e.bonus_per
    elif e.scope == "per_room":
        if e.condition_field == "count_ge":
            required = int(e.condition_value)
            karlan_count = sum(1 for op in room_ops if op.has_group("karlan"))
            if karlan_count >= required:
                return e.bonus_per
        return 0.0
    return 0.0
