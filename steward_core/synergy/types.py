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


class BuffProducerEffect(NamedTuple):
    """B·buff池生产者条目 — 与 BuffConsumerEntry 对等"""
    buff_id: str
    facility: str                       # "Control"|"Mfg"|"Trade"|"Dormitory"|"Office"
    dimension: str                      # "yanhuo"|"perception"|"monster_cuisine"|"silent_resonance"
    amount_source: str                  # "fixed"|"dorm_count"|"dorm_level"|"suich_scaled"|"office_base"
    amount: int = 0                     # fixed amount (source="fixed") or base (source="office_base")
    amount_scale: float = 1.0           # multiplier for scaled sources
    amount_cap: int = 0                 # cap for scaled sources (0=no cap)
    condition: str | None = None        # "mood_gt_12"|"mood_le_12"|"xi_mood_ge_12"|"xi_mood_lt_12"|None
    exclusive_group: str | None = None  # mutual exclusion group (令)
    cascade: bool = False               # True if this is a cascade entry (second pass)


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


class OrderLimitEntry(NamedTuple):
    """A·贸易站订单上限贡献条目"""
    source: str
    value: int
    requires: str | None = None
    per_trade_level: bool = False


class TradePairEntry(NamedTuple):
    """A·贸易站配对条目"""
    holder: str
    target: str
    bonus: float
    buff_id: str


class TradeShareEntry(NamedTuple):
    """A·贸易站 per-operator 分享条目

    buff_id → 每名队友提供的固定效率加成。
    持有者自身不计入计数（游戏描述"除自身以外"）。
    """
    bonus_per_worker: float


class TradeEffAmpEntry(NamedTuple):
    """A·贸易站效率放大条目（效率→效率）

    buff_id → 每 step_size% 房间总效率额外 bonus_per_step%，
    上限 cap%。由 synergy_trade_efficiency_amplifier 消费。
    """
    bonus_per_step: float = 5.0
    step_size: float = 5.0
    cap: float = 0.0


class TradeConditionalEffEntry(NamedTuple):
    """A·贸易站条件型 per-operator 效率条目

    持有者技能 buff_id → 当 target_names 干员在特定位置时额外 bonus_per%。
    target_scope: "base"=基建任意位置, "workspace"=工作设施(Control/Mfg/Trade)。
    """
    bonus_per: float
    target_names: tuple[str, ...]
    target_scope: str  # "base" | "workspace"


class ControlTradeLimitEntry(NamedTuple):
    """C·中枢→贸易站订单上限条目

    中枢干员名 → 当 target_name 在贸易站时订单上限额外增加。
    bonus_e0: 精0/精1阶段加成, bonus_e2: 精2阶段加成。
    """
    target_name: str
    bonus_e0: int
    bonus_e2: int


class OrderOverrideEntry(NamedTuple):
    """A·贸易站订单覆盖条目"""
    prefix: str
    order_time_h: float
    lmd_per_order: float
    gold_per_order: float
    no_efficiency: bool = False
    no_drone: bool = False
    priority: int = 0


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
from .buff_pool import _B_BUFF_CONSUMER_TABLE, _OPERATOR_BUFF_PRODUCERS  # noqa: E402
from .global_linkages import _B_CROSS_ROOM_PAIR_TABLE, _B_GLOBAL_FACTION_TABLE  # noqa: E402
from .control_linkages import _C_CONTROL_GLOBAL_TABLE  # noqa: E402
from .trade_linkages import _ORDER_LIMIT_TABLE, _TRADE_PAIR_TABLE, _JIE_MECH_TABLE, _TRADE_TRIGGER_TABLE, _ORDER_OVERRIDE_TABLE, _TRADE_SHARE_TABLE, _TRADE_EFF_AMPLIFIER_TABLE, _TRADE_CONDITIONAL_EFF_TABLE  # noqa: E402
from .control_linkages import _CONTROL_TRADE_LIMIT_TABLE  # noqa: E402

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
    "A·订单上限贡献":    TableMeta(_ORDER_LIMIT_TABLE,        ["compute_trade_order_limit"],  "新增贸易站订单上限贡献 buff"),
    "A·贸易配对":        TableMeta(_TRADE_PAIR_TABLE,         ["synergy_trade_pair"],         "新增贸易站配对 buff"),
    "A·孑技能机制":      TableMeta(_JIE_MECH_TABLE,           ["synergy_jie_order", "compute_trade_order_limit"], "新增孑技能机制标识"),
    "A·贸易触发":        TableMeta(_TRADE_TRIGGER_TABLE,      ["_collect_mechs"],             "新增贸易站单buff触发标识"),
    "A·贸易分享":        TableMeta(_TRADE_SHARE_TABLE,         ["synergy_trade_share"],        "新增贸易站 per-operator 分享 buff"),
    "A·贸易效率放大":    TableMeta(_TRADE_EFF_AMPLIFIER_TABLE, ["synergy_trade_efficiency_amplifier"], "新增贸易站效率→效率放大 buff"),
    "A·贸易条件效率":    TableMeta(_TRADE_CONDITIONAL_EFF_TABLE, ["synergy_trade_conditional_eff"], "新增贸易站条件型 per-operator buff"),
    "A·订单覆盖":        TableMeta(_ORDER_OVERRIDE_TABLE,     ["get_active_override"],        "新增贸易站订单覆盖 entry"),
    "C·中枢→贸易上限":   TableMeta(_CONTROL_TRADE_LIMIT_TABLE, ["compute_trade_order_limit"],  "新增中枢→贸易站订单上限联动"),
    "B·buff消费者":      TableMeta(_B_BUFF_CONSUMER_TABLE,    ["synergy_buff_pool_consumer"], "新增 buff 池消费者"),
    "B·buff生产者":      TableMeta(_OPERATOR_BUFF_PRODUCERS,   ["compute_buff_pool"],          "新增 buff 池生产者"),
    "B·跨房间配对":      TableMeta(_B_CROSS_ROOM_PAIR_TABLE,  ["synergy_cross_room_pair"],    "新增跨设施干员条件配对 buff"),
    "B·全局阵营计数":    TableMeta(_B_GLOBAL_FACTION_TABLE,   ["synergy_global_faction"],     "新增全局阵营计数型 buff"),
    "C·中枢全局效率":    TableMeta(_C_CONTROL_GLOBAL_TABLE,   ["compute_control_global_bonus"], "新增中枢全局 buff"),
}
