"""联动体系函数包

A层（同设施内联动）:
  PAIR          — 干员配对（阿兰娜↔温米 等）
  ROOM_FACTION  — 同房阵营计数（摩根/新约能天使 等）
  SKILL_COUNT   — 技能类型计数（水月/多萝西/苍苔）
  SKILL_ALIAS   — 技能别名（海沫·意识兼容）
  AUTOMATION    — 自动化（森蚺/温蒂/异客 等）
  WHISPER       — 巫恋·低语（归零反馈型）
  FACILITY_LINK — 设施数量联动（清流/空弦/伺夜 等）
  ORDER         — 订单压缩（孑）

B层（跨设施 buff 消费链）:
  BUFF_POOL     — 感知信息/烟火/巫术结晶/机器人/思维链环/魔物料理/无声共鸣
  GLOBAL_FACTION — 全局阵营计数（缪尔赛思/杏仁/娜斯提）
  CROSS_ROOM    — 跨房间配对（烈夏↔古米 等）

C层（中枢全局）:
  CONTROL_GLOBAL — 中枢全局效率（凯尔希/望/布丁 等）
  MOOD_BURN      — 中枢心情恢复（重岳·孤光共照）

每个体系一个独立函数，同层并行计算后线性叠加。
"""

from steward_core.synergy.types import (
    FacilityLinkEntry,
    BuffConsumerEntry,
    BuffProducerEffect,
    FactionEntry,
    ExtraFactionEntry,
    GlobalFactionEntry,
    CrossRoomPairEntry,
    ZeroingVariantEntry,
    RampingSkillEntry,
    GlobalBonusEntry,
    ControlConditionalEntry,
    ControlPerOpEntry,
    TradeShareEntry,
    TradeEffAmpEntry,
    TradeConditionalEffEntry,
    ControlTradeLimitEntry,
    FacilityGroupEntry,
    TableMeta,
    TABLES,
)

from steward_core.synergy.helpers import (
    _KNIGHT_NAMES,
    _MH_NAMES,
    _LUNG_MEN_GUARD_NAMES,
    _BLACKSTEEL_HOLDERS,
    _OP_PLATFORM_NAMES,
    _DURIN_NAMES,
    _PINUS_GROUP,
    _BLACKSTEEL_GROUP,
    _GLASGOW_GROUP,
    _FACILITY_LEVEL,
    _DEFAULT_DORM_LEVELS,
    _ORDER_ANCHOR_PREFIXES,
    ROSEMARY_SUPPORT,
    _B_ROSEMARY,
    _B_EBENHOLZ,
    _is_glasgow,
    _is_knight,
)

from steward_core.synergy.registry import (
    SystemContributor,
    get_system_contributors,
    _SYSTEM_CONTRIBUTORS,
)

from steward_core.synergy.mood import (
    compute_global_burn,
)

from steward_core.synergy.mfg_linkages import (
    synergy_pair,
    synergy_capacity_to_eff,
    synergy_efficiency_amplifier,
    synergy_zeroing_variant,
    synergy_token_prod,
    operator_ramp_segments,
    skill_class,
    synergy_skill_count,
    synergy_skill_alias,
    synergy_automation,
    synergy_whisper,
    synergy_faction_room,
    get_synergy_enablers,
    _A_PAIR_TABLE,
    _A_ROOM_FACTION_TABLE,
    _A_ROOM_FACTION_EXTRA,
    _A_SKILL_COUNT_TABLE,
    _A_AUTOMATION_FALLBACK,
    _POWER_BUFF_BONUS,
    _ZEROING_VARIANT_TABLE,
    _RAMPING_SKILL_TABLE,
    _TOKEN_PROD_TABLE,
)

from steward_core.synergy.trade_linkages import (
    synergy_jie_order,
    synergy_trade_gold_lines,
    synergy_trade_pair,
    synergy_trade_share,
    synergy_swires_order_limit,
    synergy_degenbrecher_order_limit,
    synergy_trade_efficiency_amplifier,
    synergy_trade_conditional_eff,
    OrderLimitContext,
    compute_trade_order_limit,
    get_active_override,
    _TRADE_PAIR_TABLE,
    _TRADE_SHARE_TABLE,
    _TRADE_EFF_AMPLIFIER_TABLE,
    _TRADE_CONDITIONAL_EFF_TABLE,
)

from steward_core.synergy.facility_linkages import (
    synergy_facility_count,
    compute_effective_power_count,
    _has_power_count_modifier,
    _A_FACILITY_LINK_TABLE,
)

from steward_core.synergy.facility_group import (
    count_facilities_with_group,
    compute_facility_group_bonus,
    synergy_facility_group,
    _FACILITY_GROUP_TABLE,
)

from steward_core.synergy.control_linkages import (
    compute_control_global_bonus,
    control_per_operator_bonus,
    GlobalBonus,
    _C_CONTROL_GLOBAL_TABLE,
    _CONTROL_CONDITIONAL_TABLE,
    _CONTROL_PER_OP_TABLE,
    _CONTROL_TRADE_LIMIT_TABLE,
)

from steward_core.synergy.global_linkages import (
    synergy_cross_room_pair,
    synergy_global_faction,
    _B_CROSS_ROOM_PAIR_TABLE,
    _B_GLOBAL_FACTION_TABLE,
)

from steward_core.synergy.buff_pool import (
    BuffPool,
    compute_buff_pool,
    synergy_buff_pool_consumer,
    compute_engineering_robots,
    _B_BUFF_CONSUMER_TABLE,
)

from steward_core.synergy.classification import (
    MfgClassification,
    classify_mfg_operators,
    prune_equivalent,
    build_candidate_pool,
    classify_trade_operators,
)

from steward_core.synergy._derived import (
    MFG_ANCHORS,
    TRADE_ANCHORS,
)

from steward_core.synergy.conflicts import (
    resolve_efficiency_conflicts,
    has_order_override,
)
