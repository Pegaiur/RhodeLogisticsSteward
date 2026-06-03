"""共享常量

排班求解器与产出计算共用的配置常量。
"""

# 固定中枢方案（社区最优）
FIXED_CONTROL = ["令", "重岳", "夕", "凯尔希", "焰尾"]

# 243 布局物理发电站数
BASE_POWER_COUNT = 3

# 设施槽位数
FACILITY_SLOTS: dict[str, int] = {
    "Control": 5,
    "Mfg": 3,
    "Trade": 3,
    "Power": 1,
    "Reception": 2,
    "Office": 1,
}

# 不消耗心情的设施类型
NON_WORK_FACILITIES: frozenset[str] = frozenset({"Dormitory", "Training", "Workshop"})

# ── 制造站 Lv3 经济常量 ──────────────────────────────────────────
# 基础产出率（个/小时）
MFG_CR_BASE_RATE = 1.0 / 3.0    # 作战记录: 1个/3h
MFG_PG_BASE_RATE = 1.0 / 1.2    # 赤金: 1个/1.2h

# 产品单位价值
CR_EXP_PER_UNIT = 1000.0         # 每中级经验书 = 1000 经验
PG_LMD_PER_UNIT = 500.0          # 每赤金 = 500 LMD
XP_LMD_RATIO = 1.3               # 经验→LMD 折算比

# ── 贸易站 Lv3 经济常量 ──────────────────────────────────────────
TRADE_BASE_LMD_PER_DAY = 10265.0  # 龙门商法基础日产 LMD
