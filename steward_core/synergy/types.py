"""硬编码表类型定义与集中索引"""

from typing import NamedTuple


class FacilityLinkEntry(NamedTuple):
    """A·设施数量联动条目"""
    count_source: str
    bonus_per_unit: float
    target_room: str
    target_product: str | None
    cap: float | None


class BuffConsumerEntry(NamedTuple):
    """B·buff池消费者条目"""
    target_room: str
    pool_key: str
    per_unit: int
    bonus_per: float


class FactionEntry(NamedTuple):
    """A·同房阵营计数条目"""
    field: str
    value: str
    bonus_per: float
    target_product: str | None
    target_room: str | None


class ExtraFactionEntry(NamedTuple):
    """A·同房阵营额外加成条目"""
    extra_name: str
    extra_bonus: float
    target_product: str | None
    target_room: str | None


class GlobalFactionEntry(NamedTuple):
    """B·全局阵营计数条目"""
    field: str
    value: str
    bonus_per: float
    target_product: str | None
    target_room: str
    cap: int
    exclude_self: bool


class CrossRoomPairEntry(NamedTuple):
    """B·跨房间配对条目"""
    target_name: str
    target_facility: str | None
    bonus_per: float
    target_product: str | None
    target_room: str | None


class ZeroingVariantEntry(NamedTuple):
    """A·归零变体条目"""
    buff_id: str
    room_type: str
    bonus_per: float


class RampingSkillEntry(NamedTuple):
    """A·爬升型技能条目"""
    buff_id: str
    room_type: str
    base_rate: float


class GlobalBonusEntry(NamedTuple):
    """C·中枢全局效率条目"""
    mfg_bonus: float
    trade_bonus: float


class TableMeta(NamedTuple):
    """硬编码表元信息"""
    table: object
    consumers: list[str]
    trigger: str


# ─── 硬编码表集中索引 ──────────────────────────────────────────────
# 放在文件末尾以避免循环导入（TABLES 引用的子模块会导入 types 中的 NamedTuple 类，
# 而此处从子模块导入表数据时，types 中的所有类定义已完成）

from .mfg_linkages import _A_PAIR_TABLE, _A_ROOM_FACTION_TABLE, _A_ROOM_FACTION_EXTRA, _A_SKILL_COUNT_TABLE, _A_AUTOMATION_FALLBACK, _ZEROING_VARIANT_TABLE, _TOKEN_PROD_TABLE, _RAMPING_SKILL_TABLE  # noqa: E402
from .facility_linkages import _A_FACILITY_LINK_TABLE  # noqa: E402
from .buff_pool import _B_BUFF_CONSUMER_TABLE  # noqa: E402
from .global_linkages import _B_CROSS_ROOM_PAIR_TABLE, _B_GLOBAL_FACTION_TABLE  # noqa: E402
from .control_linkages import _C_CONTROL_GLOBAL_TABLE  # noqa: E402

TABLES: dict[str, TableMeta] = {
    "A·干员配对":        TableMeta(_A_PAIR_TABLE,             ["synergy_pair"],              "新增配对型联动 buff"),
    "A·同房阵营计数":    TableMeta(_A_ROOM_FACTION_TABLE,     ["synergy_faction_room", "get_synergy_enablers"], "新增同房阵营计数型 buff"),
    "A·同房阵营额外":    TableMeta(_A_ROOM_FACTION_EXTRA,     ["synergy_faction_room"],       "新增同房阵营额外加成"),
    "A·技能计数":        TableMeta(_A_SKILL_COUNT_TABLE,      ["synergy_skill_count"],        "新增技能计数锚点"),
    "A·自动化回退":      TableMeta(_A_AUTOMATION_FALLBACK,    ["synergy_automation"],         "新增自动化干员或 buff 变更"),
    "A·归零变体":        TableMeta(_ZEROING_VARIANT_TABLE,    ["synergy_whisper"],             "新增归零型变体 buff"),
    "A·机械精通":        TableMeta(_TOKEN_PROD_TABLE,         ["synergy_token_prod"],          "新增作业平台联动 buff"),
    "A·爬升型技能":      TableMeta(_RAMPING_SKILL_TABLE,      ["synergy_ramping"],             "新增 manu_prod_spd_addition[*] 爬升型技能"),
    "A·设施数量联动":    TableMeta(_A_FACILITY_LINK_TABLE,    ["synergy_facility_count"],     "新增设施数量联动 buff"),
    "B·buff消费者":      TableMeta(_B_BUFF_CONSUMER_TABLE,    ["synergy_buff_pool_consumer"], "新增 buff 池消费者"),
    "B·跨房间配对":      TableMeta(_B_CROSS_ROOM_PAIR_TABLE,  ["synergy_cross_room_pair"],    "新增跨设施干员条件配对 buff"),
    "B·全局阵营计数":    TableMeta(_B_GLOBAL_FACTION_TABLE,   ["synergy_global_faction"],     "新增全局阵营计数型 buff"),
    "C·中枢全局效率":    TableMeta(_C_CONTROL_GLOBAL_TABLE,   ["compute_control_global_bonus"], "新增中枢全局 buff"),
}
