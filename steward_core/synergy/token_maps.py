"""TokenSource 数据表 — 注册列表 + buff_id→token 映射

与 steward_core.token_source 分离以保持引擎文件的纯逻辑属性。
新增注册仅需修改本文件，引擎逻辑不受影响。
"""

from __future__ import annotations

from steward_core.token_source import TokenSource

# ─── Phase A TokenSource 注册列表 ────────────────────────────────────────

# 以下 11 条覆盖 A 层同房阵营 4 + C 层 per-operator 条件加成 8，
# 用于 Phase A 原型验证：与旧函数 synergy_faction_room / _eval_per_op 输出对齐。

PHASE_A_SOURCES: list[TokenSource] = [
    # ── A 层同房阵营 ──
    TokenSource(token="reserve1_mfg", condition="team_id=reserve1"),
    TokenSource(token="glasgow_trade", condition="group_id=glasgow"),
    TokenSource(token="laterano_trade", condition="nation_id=laterano"),

    # ── C 层 per-operator ──
    TokenSource(token="pinus_cr", condition="group_id=pinus"),
    TokenSource(token="pinus_pg_penalty", condition="group_id=pinus"),
    TokenSource(token="knight_mfg", condition="is_knight"),
    TokenSource(token="blacksteel_mfg", condition="group_id=blacksteel"),
    TokenSource(token="siracusa_trade", condition="nation_id=siracusa"),
    TokenSource(token="karlan3_trade", condition="count_ge:karlan=3"),
    TokenSource(token="glasgow_trade_bonus", condition="group_id=glasgow"),
    TokenSource(token="karlan_trade_penalty", condition="group_id=karlan"),
]


# ─── Phase B TokenSource 注册列表 ────────────────────────────────────────

# A 层技能标签计数（A3）
# 水月/多萝西/苍苔 对同房内持有相同 skill_class 的干员计数 +5%/人
PHASE_B_SKILL_CLASS: list[TokenSource] = [
    TokenSource(token="standardization_count", condition="skill_class=标准化"),
    TokenSource(token="rhine_tech_count", condition="skill_class=莱茵科技"),
    TokenSource(token="metal_craft_count", condition="skill_class=金属工艺"),
]

# B 层全局阵营计数（B6）
# 缪尔赛思/杏仁/娜斯提 每名符合条件的全基建干员提供效率加成
PHASE_B_GLOBAL_FACTION: list[TokenSource] = [
    TokenSource(token="rhine_global", condition="group_id=rhine", scope="global", cap=5),
    TokenSource(token="blacksteel_global", condition="group_id=blacksteel", scope="global", cap=3),
    TokenSource(token="rhine_global_mfg", condition="group_id=rhine", scope="global", cap=5),
]

# B 层跨房间配对（B7）
# 烈夏↔古米 / 深巡↔乌尔比安 / 贝洛内↔伺夜 — 跨设施配对
# 注：当前 pair 值使用干员名作为 char_id 占位符（Phase E 全量 char_id 迁移时替换为真实 char_id）
PHASE_B_CROSS_PAIRS: list[TokenSource] = [
    TokenSource(token="liexia_gumi", condition="pair=烈夏:古米"),
    TokenSource(token="shenxun_wuerbian", condition="pair=深巡:乌尔比安"),
    TokenSource(token="beiluo_siye", condition="pair=贝洛内:伺夜"),
]

# 技能别名使能者（C3）
# 海沫在场时激活 skill_class 别名映射
PHASE_B_ALIAS: list[TokenSource] = [
    TokenSource(token="haimei_in_room", condition="char_id=海沫"),
]

# C 层集群狩猎
# 歌蕾蒂娅 每 Mfg 站内深海猎人提供 +10%/人
PHASE_B_CLUSTER: list[TokenSource] = [
    TokenSource(token="abyssal_mfg", condition="is_abyssal_hunter", scope="facility"),
]

# 全量 B 层注册（不含需要 depends_on="layout"/"facility" 的条目）
# 注：PHASE_B_A_PAIRS / TRADE_PAIRS / EFF_AMPLIFIER / CONDITIONAL_EFF / FACTORY_COUNT
# / FACILITY_GROUP 均已注册但未纳入本列表——它们按 Phase C 策略单独使用，避免
# evaluate_room() 首次接入时引入过多 token 增加性能开销。
PHASE_B_SOURCES: list[TokenSource] = (
    PHASE_B_SKILL_CLASS
    + PHASE_B_GLOBAL_FACTION
    + PHASE_B_CROSS_PAIRS
    + PHASE_B_CLUSTER
)


# ─── buff_id → Token 映射表 ──────────────────────────────────────────────

# 每个 buff_id 可能生产多个 token（如黑键同时生产 perception + silent_resonance）
# 替代 _OPERATOR_BUFF_PRODUCERS 的 dimension + cascade 字段组合
_BUFF_TO_TOKENS: dict[str, list[str]] = {
    # ── 中枢源 ──
    "control_costToBD[000]": ["yanhuo", "perception"],
    "control_mp_cost&bd_up[000]": ["yanhuo"],
    "control_mp_cost&bd1[000]": ["yanhuo"],
    "control_mp_cost&bd2[000]": ["perception"],
    # ── 代理源 ──
    "manu_prod_spd_bd_n1[000]": ["perception"],
    "trade_ord_spd_bd_n1[000]": ["perception", "silent_resonance"],
    "trade_ord_spd_bd_n2[000]": ["yanhuo"],
    "dorm_rec_bd_n1_n2[000]": ["perception"],
    "dorm_rec_bd_n1_n3[000]": ["perception"],
    "hire_spd_bd_n1[000]": ["perception"],
    "hire_spd_bd_n1_n1[200]": ["yanhuo"],
    "dorm_rec_bd_dungeon[000]": ["monster_cuisine"],
    # ── 无声共鸣源 ──
    "dorm_bd_num[000]": ["silent_resonance"],
    "hire_spd_bd_n1_n1[300]": ["silent_resonance"],
}


# ─── Phase B6: layout/facility 依赖的 TokenSource 注册 ──────────────────

# 工厂数量联动（A5）
# 依赖 depends_on="layout" 查询 ctx.layout.rooms
PHASE_B_FACTORY_COUNT: list[TokenSource] = [
    TokenSource(token="trade_rooms", depends_on="layout", target_room="Trade"),
    TokenSource(token="mfg_rooms", depends_on="layout", target_room="Mfg"),
    TokenSource(token="power_rooms", depends_on="layout", target_room="Power"),
]

# 设施 group 计数（B4）
# 依赖 depends_on="facility" 查询 ctx.build_all_assignments()
# 注：当前按 facility_type 分组（非按房间），与 SlotContext 接口一致
PHASE_B_FACILITY_GROUP: list[TokenSource] = [
    TokenSource(token="sui_facilities", depends_on="facility", condition="group_id=sui"),
    TokenSource(token="elite_facilities", depends_on="facility", condition="group_id=elite"),
]


# ─── B7 补充：可立即完成的剩余注册（用当前引擎能力）───────────────

# A 层配对（_A_PAIR_TABLE）+ 同房阵营额外（_A_ROOM_FACTION_EXTRA）
PHASE_B_A_PAIRS: list[TokenSource] = [
    TokenSource(token="alanna_wenmi", condition="pair=阿兰娜:温米"),
    TokenSource(token="christine_jiujiu", condition="pair=Miss.Christine:酒神"),
    TokenSource(token="nuchao_ursus", condition="pair=怒潮凛冬:乌萨斯学生自治团"),
    TokenSource(token="morgan_siege", condition="pair=摩根:推进之王"),
]

# 贸易配对（_TRADE_PAIR_TABLE）
PHASE_B_TRADE_PAIRS: list[TokenSource] = [
    TokenSource(token="texas_lappland", condition="pair=德克萨斯:拉普兰德"),
    TokenSource(token="lemuel_exusiai", condition="pair=蕾缪安:能天使"),
]

# 贸易效率放大（_TRADE_EFF_AMPLIFIER_TABLE）
# 雪雉：房间总效率 / 5 * 5%（alpha cap=25, beta cap=35）
PHASE_B_EFF_AMPLIFIER: list[TokenSource] = [
    TokenSource(token="trade_eff_total", aggregate="efficiency_sum", target_room="Trade"),
]

# 贸易条件效率（_TRADE_CONDITIONAL_EFF_TABLE）
# 贝洛内家族经营：伺夜在 base 则 +5%/+10%
PHASE_B_CONDITIONAL_EFF: list[TokenSource] = [
    TokenSource(token="siye_in_base", condition="char_id=伺夜", scope="global"),
]
