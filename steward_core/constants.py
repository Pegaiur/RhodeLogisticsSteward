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
