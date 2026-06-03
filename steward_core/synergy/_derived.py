"""自动生成的硬编码数据

由 scripts/derive.py 生成，请勿手动编辑。
运行: python scripts/derive.py
"""

# ── 制造站锚点 ──
# 来源：_A_PAIR_TABLE / _A_SKILL_COUNT_TABLE / _A_AUTOMATION_FALLBACK
#       _A_ROOM_FACTION_TABLE / _A_FACILITY_LINK_TABLE
#       _B_BUFF_CONSUMER_TABLE / _B_CROSS_ROOM_PAIR_TABLE
#       _B_GLOBAL_FACTION_TABLE / 硬编码特殊干员
MFG_ANCHORS: set[str] = {
    "Miss.Christine",
    "历阵锐枪芬",
    "多萝西",
    "娜仁图亚",
    "娜斯提",
    "异客",
    "引星棘刺",
    "怒潮凛冬",
    "截云",
    "掠风",
    "摩根",
    "杏仁",
    "桑葚",
    "森蚺",
    "槐琥",
    "水月",
    "泡泡",
    "海沫",
    "清流",
    "温蒂",
    "烈夏",
    "玛露西尔",
    "红云",
    "维伊",
    "至简",
    "苍苔",
    "迷迭香",
    "阿兰娜",
    "黍",
}

# ── 贸易站锚点 ──
# 来源：_A_ROOM_FACTION_TABLE / _A_FACILITY_LINK_TABLE
#       _B_BUFF_CONSUMER_TABLE / _B_CROSS_ROOM_PAIR_TABLE
#       _B_GLOBAL_FACTION_TABLE / 手工注册
TRADE_ANCHORS: set[str] = {
    "乌有",
    "伺夜",
    "吉星",
    "巫恋",
    "德克萨斯",
    "摩根",
    "新约能天使",
    "深巡",
    "渡桥",
    "火哨",
    "石英",
    "空弦",
    "贝洛内",
    "铎铃",
    "雪雉",
    "黑键",
}

# ── KNIGHT_NAMES ──
# 推导规则：骑士：nationId==kazimierz OR groupId==pinus OR 硬编码
KNIGHT_NAMES: set[str] = {
    "临光",
    "但书",
    "暴雨",
    "正义骑士号",
    "流星",
    "灰毫",
    "焰尾",
    "玛恩纳",
    "瑕光",
    "白金",
    "砾",
    "耀骑士临光",
    "薇薇安娜",
    "远牙",
    "野鬃",
    "鞭刃",
}

# ── DURIN_NAMES ──
# 推导规则：杜林族：硬编码（character_identity.json 无 raceId 字段）
DURIN_NAMES: set[str] = {
    "杜林",
    "桃金娘",
    "至简",
    "褐果",
}

# ── OP_PLATFORM_NAMES ──
# 推导规则：作业平台：硬编码（机器人 profession 无特殊标识）
OP_PLATFORM_NAMES: set[str] = {
    "Castle-3",
    "Lancet-2",
    "THRM-EX",
    "正义骑士号",
}

# ── MH_NAMES ──
# 推导规则：怪物猎人小队：硬编码
MH_NAMES: set[str] = {
    "炼金术士",
    "麒麟R夜刀",
}

# ── LUNG_MEN_GUARD_NAMES ──
# 推导规则：龙门近卫局：硬编码
LUNG_MEN_GUARD_NAMES: set[str] = {
    "斩业星熊",
    "星熊",
    "诗怀雅",
    "陈",
}
