"""联动体系函数

每个体系一个独立函数。同层体系之间并行计算后线性叠加。
MVP 范围: A1/A3/A4/A5/A6/C1（A/C 层已完成）。
A2/A7/B 层在后续迭代补充。
"""

from dataclasses import dataclass

from steward_core.models import LinearSegment, Operator, LayoutConfig

T = 12.0  # MVP 固定 12h 排班

# ─── A1 干员配对 ─────────────────────────────────────────────────

# 配对表: (持有者名, 目标名, 产物, 加成%)
# 来自 buffs_infrastructure.json 中 efficiency=0 的条件型 buff
_A1_PAIR_TABLE: dict[tuple[str, str, str], float] = {
    ("阿兰娜", "温米", "PureGold"): 15.0,
    ("Miss.Christine", "酒神", "CombatRecord"): 30.0,
    ("怒潮凛冬", "乌萨斯学生自治团", "CombatRecord"): 10.0,
}


def synergy_pair(
    operators: list[Operator],
    room_type: str,
    product: str,
) -> list[LinearSegment]:
    """识别同房间干员配对组合，输出聚合常数段"""
    if room_type != "Mfg":
        return []

    names = {op.name for op in operators}
    segments = []

    for (holder_name, target_name, p_type), bonus in _A1_PAIR_TABLE.items():
        if product != p_type:
            continue
        if holder_name in names and target_name in names:
            segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))

    return segments


# ─── A3 技能类型计数 ─────────────────────────────────────────────

# 计数锚点: {干员名: 计数的技能类型}
_A3_COUNTER_TABLE: dict[str, str] = {
    "水月": "标准化",
    "多萝西": "莱茵科技",
    "苍苔": "金属工艺",
}
_A3_BONUS_PER = 5.0  # 每个该类技能 +5%


def _skill_class(buff_name: str) -> str | None:
    """从 buff 名称提取技能类别"""
    for cls_name in ("标准化", "莱茵科技", "金属工艺", "红松骑士团"):
        if cls_name in buff_name:
            return cls_name
    return None


def synergy_skill_count(
    operators: list[Operator],
    room_type: str,
    alias: dict[str, list[str]] | None = None,
) -> list[LinearSegment]:
    """统计同房间内技能类型数量，为持有者提供效率加成"""
    if room_type != "Mfg":
        return []

    if alias is None:
        alias = {}

    # 收集每个干员的 buff 类型标签
    op_classes: dict[str, set[str]] = {}
    for op in operators:
        classes: set[str] = set()
        for sk in op.skills:
            if sk.room_type != "Mfg":
                continue
            sc = _skill_class(sk.buff_name)
            if sc:
                classes.add(sc)
                for aliased in alias.get(sc, []):
                    classes.add(aliased)
        op_classes[op.name] = classes

    segments = []

    for op in operators:
        if op.name not in _A3_COUNTER_TABLE:
            continue
        target_cls = _A3_COUNTER_TABLE[op.name]

        # 统计同房所有干员（含自身）中持有 target_cls 类型的数量
        count = 0
        for other in operators:
            if target_cls in op_classes.get(other.name, set()):
                count += 1

        if count > 0:
            bonus = count * _A3_BONUS_PER
            segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))

    return segments


# ─── A4 技能类型别名 ─────────────────────────────────────────────

def synergy_skill_alias(
    operators: list[Operator],
) -> dict[str, list[str]]:
    """返回技能类型别名映射

    海沫(意识兼容): 莱茵科技 → 标准化, 红松骑士团 → 标准化
    """
    names = {op.name for op in operators}
    if "海沫" not in names:
        return {}
    return {
        "莱茵科技": ["标准化"],
        "红松骑士团": ["标准化"],
    }


# ─── A5 自动化 ───────────────────────────────────────────────────

# 自动化干员名集合（硬编码回退，技能数据可用时优先走 buff_id 版本检测）
_A5_AUTO_NAMES: set[str] = {"森蚺", "掠风", "异客", "温蒂"}

# 自动化 buff 版本 → 每发电站加成%: manu_prod_spd&power[000/010/020]
_POWER_BUFF_BONUS: dict[str, float] = {
    "manu_prod_spd&power[000]": 5.0,
    "manu_prod_spd&power[010]": 10.0,
    "manu_prod_spd&power[020]": 15.0,
}

# 默认加成表（技能数据不可用时的回退值）
_A5_AUTO_FALLBACK: dict[str, float] = {
    "森蚺": 5.0,
    "掠风": 5.0,
    "异客": 5.0,
    "温蒂": 15.0,
}


def _automation_bonus_from_skills(skills: list) -> float:
    """从干员技能列表中检测 automation buff 的最高版本加成"""
    best = 0.0
    for sk in skills:
        if sk.buff_id in _POWER_BUFF_BONUS:
            b = _POWER_BUFF_BONUS[sk.buff_id]
            if b > best:
                best = b
    return best


def synergy_automation(
    operators: list[Operator],
    room_type: str,
    power_count: int,
) -> tuple[list[LinearSegment], set[str]]:
    """若房间有自动化干员，返回 (自动化产出段, 需归零的干员名集合)"""
    if room_type != "Mfg":
        return [], set()

    best_bonus = 0.0
    auto_op_names = set()
    for op in operators:
        if op.name not in _A5_AUTO_NAMES:
            continue
        auto_op_names.add(op.name)

        skill_bonus = _automation_bonus_from_skills(op.skills)
        if skill_bonus > 0:
            bonus = skill_bonus
        else:
            bonus = _A5_AUTO_FALLBACK.get(op.name, 0.0)

        if bonus > best_bonus:
            best_bonus = bonus

    if not auto_op_names:
        return [], set()

    total_bonus = power_count * best_bonus
    segments = [LinearSegment(a=total_bonus, b=0.0, t_start=0.0, dt=T)]

    zero_set = {op.name for op in operators if op.name not in auto_op_names}
    return segments, zero_set


# ─── A6 设施数量联动 ─────────────────────────────────────────────

# 设施数量联动表: {干员名: (计数对象, 每单位加成%, 设施类型, 产物, 上限或无)}
# buffs_infrastructure.json 中 efficiency=0 的条件型 buff，
# 按全基建设施数量统计后输出加成
_A6_FACILITY_TABLE: dict[str, tuple[str, float, str, str | None, float | None]] = {
    "清流": ("trade_count", 20.0, "Mfg", "PureGold", None),
    "引星棘刺": ("trade_count", 3.0, "Mfg", "PureGold", None),
    "娜仁图亚": ("dorm_levels", 1.0, "Mfg", "PureGold", None),
    "空弦": ("dorm_levels", 2.0, "Trade", "Money", None),
    "伺夜": ("meeting_level", 5.0, "Trade", "Money", 40.0),
    "渡桥": ("meeting_level", 5.0, "Trade", "Money", 30.0),
    "石英": ("mfg_recipe_types", 2.0, "Trade", "Money", None),
}

# 设施等级 Lv3
_FACILITY_LEVEL = 3
# 243 布局默认宿舍等级（4 间 × Lv3）
_DEFAULT_DORM_LEVELS = 12


def synergy_facility_count(
    operators: list[Operator],
    room_type: str,
    product: str,
    layout: LayoutConfig,
    dorm_levels: int = _DEFAULT_DORM_LEVELS,
) -> list[LinearSegment]:
    """根据全基建设施数量/等级为当前房间提供联动加成

    Returns:
        联动加成段列表，每个非零加成对应一个常数段
    """
    names = {op.name for op in operators}
    segments = []

    # 从 LayoutConfig 提取设施统计
    trade_count = sum(1 for r in layout.rooms if r.room_type == "Trade")
    meeting_level = sum(
        _FACILITY_LEVEL for r in layout.rooms if r.room_type == "Reception"
    )
    mfg_products = {
        r.product for r in layout.rooms
        if r.room_type == "Mfg" and r.product is not None
    }
    mfg_recipe_types = len(mfg_products)

    for name in names:
        if name not in _A6_FACILITY_TABLE:
            continue
        count_key, bonus_per, target_room, target_product, cap = _A6_FACILITY_TABLE[name]

        if room_type != target_room:
            continue
        if target_product is not None and product != target_product:
            continue

        if count_key == "trade_count":
            count = trade_count
        elif count_key == "dorm_levels":
            count = dorm_levels
        elif count_key == "meeting_level":
            count = meeting_level
        elif count_key == "mfg_recipe_types":
            count = mfg_recipe_types
        else:
            continue

        bonus = count * bonus_per
        if cap is not None:
            bonus = min(bonus, cap)

        if bonus > 0:
            segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))

    return segments


# ─── C1 中枢全局效率 ─────────────────────────────────────────────

# 中枢全局效率表: {干员名: (制造加成%, 贸易加成%)}
# buffs_infrastructure.json 中 efficiency=0 的条件型 CONTROL buff
# 同种效果取最高（不叠加）
_C1_GLOBAL_TABLE: dict[str, tuple[float, float]] = {
    "凯尔希": (2.0, 0.0),
    "Mon3tr": (2.0, 0.0),
}


@dataclass
class GlobalBonus:
    """中枢全局效率加成"""
    mfg_bonus: float = 0.0
    trade_bonus: float = 0.0


def compute_control_global_bonus(
    control_operators: list[Operator],
) -> GlobalBonus:
    """计算中枢干员提供的全局制造/贸易加成

    同种效果取最高值（游戏内描述"同种效果取最高"）。
    """
    names = {op.name for op in control_operators}
    best_mfg = 0.0
    best_trade = 0.0
    for name in names:
        if name in _C1_GLOBAL_TABLE:
            m, t = _C1_GLOBAL_TABLE[name]
            best_mfg = max(best_mfg, m)
            best_trade = max(best_trade, t)
    return GlobalBonus(mfg_bonus=best_mfg, trade_bonus=best_trade)


# ─── B1 人间烟火 / 感知信息 / 巫术结晶 ──────────────────────────

@dataclass
class BuffPool:
    """全局 buff 点数池"""
    yanhuo: int = 0            # 人间烟火
    perception: int = 0        # 感知信息
    wushu_crystal: int = 0     # 巫术结晶
    thought_chains: int = 0    # 思维链环 (B3)
    silent_resonance: int = 0  # 无声共鸣 (B5)
    engineering_robots: int = 0  # 工程机器人 (B2)
    monster_cuisine: int = 0     # 魔物料理 (B4)


def compute_buff_pool(
    control_operators: list[Operator],
    suich_count: int = 5,
    dorm_operators: list[Operator] | None = None,
    dorm_level: int = 3,
    has_rosmontis_in_mfg: bool = False,
    has_ebnhlz_in_trade: bool = False,
) -> BuffPool:
    """计算全局 buff 点数池（Phase 1 预计算）

    中枢源：
    - 令(mood>12): +15 烟火
    - 重岳: 每个外部岁干员 +5 烟火（默认 5 名）
    - 夕(mood>12): +10 感知信息

    宿舍源（B1 感知信息）：
    - 迷迭香超感（在制造站）: 宿舍每有1名干员→感知+1
    - 黑键乐感（在贸易站）: 宿舍每有1名干员→感知+1
    - 爱丽丝梦境呓语: 宿舍每级→1梦境→1感知
    - 车尔尼琴键漫步: 宿舍每级→1小节→1感知

    宿舍源（B4 魔物料理）：
    - 森西大食堂: 宿舍每级→1魔物料理

    烟火→巫术结晶: yanhuo // 5（截云消费链路）
    感知信息→思维链环: 1:1（迷迭香超感）
    """
    if dorm_operators is None:
        dorm_operators = []

    names = {op.name for op in control_operators}
    yanhuo = 0
    perception = 0
    monster_cuisine = 0

    # 令: mood>12 → +15 烟火
    if "令" in names:
        yanhuo += 15

    # 重岳: 每个外部岁干员 +5 烟火（上限 5 名）
    if "重岳" in names:
        yanhuo += min(suich_count, 5) * 5

    # 夕: mood>12 → +10 感知信息
    if "夕" in names:
        perception += 10

    # ─── 宿舍源感知信息 ───

    # 迷迭香超感: 宿舍每有1名干员→感知+1
    if has_rosmontis_in_mfg and dorm_operators:
        perception += len(dorm_operators)

    # 黑键乐感: 宿舍每有1名干员→感知+1
    if has_ebnhlz_in_trade and dorm_operators:
        perception += len(dorm_operators)

    # 爱丽丝梦境呓语: 每梦境→1感知（梦境=宿舍等级）
    if _dorm_has_buff(dorm_operators, "dorm_rec_bd_n1_n2[000]"):
        perception += dorm_level

    # 车尔尼琴键漫步: 每小节→1感知（小节=宿舍等级）
    if _dorm_has_buff(dorm_operators, "dorm_rec_bd_n1_n3[000]"):
        perception += dorm_level

    # ─── 宿舍源魔物料理 ───

    # 森西大食堂: 宿舍每级→1魔物料理
    if _dorm_has_buff(dorm_operators, "dorm_rec_bd_dungeon[000]"):
        monster_cuisine += dorm_level

    # 12h 班次 mood 不衰减（令杯莫停消除岁干员消耗）
    wushu_crystal = yanhuo // 5  # 烟火→巫术结晶（截云消费）
    thought_chains = perception  # B3: 感知信息→思维链环（1:1，迷迭香消费）
    return BuffPool(
        yanhuo=yanhuo, perception=perception,
        wushu_crystal=wushu_crystal, thought_chains=thought_chains,
        monster_cuisine=monster_cuisine,
    )


def _dorm_has_buff(dorm_operators: list[Operator], buff_id: str) -> bool:
    """检查宿舍干员列表中是否存在持有指定 buff_id 的干员"""
    for op in dorm_operators:
        for sk in op.skills:
            if sk.buff_id == buff_id:
                return True
    return False


# B 层 buff 池消费者表: {干员名: (设施类型, pool_key, 每单位, 每单位加成%)}
_B_LAYER_CONSUMER_TABLE: dict[str, tuple[str, str, int, float]] = {
    # B1 烟火消费者
    "黍": ("Mfg", "yanhuo", 3, 1.0),
    "桑葚": ("Mfg", "yanhuo", 3, 1.0),
    "乌有": ("Trade", "yanhuo", 1, 1.0),
    "截云": ("Mfg", "wushu_crystal", 1, 2.0),
    "铎铃": ("Trade", "yanhuo", 10, 0.0),
    # B2 工程机器人消费者
    "至简": ("Mfg", "engineering_robots", 8, 5.0),  # β: 每8机器人+5%
    # B3 思维链环消费者
    "迷迭香": ("Mfg", "thought_chains", 1, 1.0),      # β: 每1链环+1%
    # B4 魔物料理消费者
    "玛露西尔": ("Mfg", "monster_cuisine", 1, 1.0),
    # B5 无声共鸣消费者
    "黑键": ("Trade", "silent_resonance", 2, 1.0),    # β: 每2共鸣+1%
}


def synergy_buff_pool_consumer(
    operators: list[Operator],
    room_type: str,
    product: str,
    buff_pool: BuffPool,
) -> list[LinearSegment]:
    """B 层消费者：将 BuffPool 中的点数转化为房间效率加成

    覆盖 B1(烟火/巫术结晶)/B2(工程机器人)/B3(思维链环)/B4(魔物料理)/B5(无声共鸣)。
    """
    names = {op.name for op in operators}
    segments = []

    for name in names:
        if name not in _B_LAYER_CONSUMER_TABLE:
            continue
        target_room, pool_key, per_unit, bonus_per = _B_LAYER_CONSUMER_TABLE[name]
        if room_type != target_room:
            continue
        if bonus_per <= 0:  # 铎铃影响心情而非效率
            continue

        pool_value = getattr(buff_pool, pool_key, 0)
        if pool_value <= 0:
            continue

        units = pool_value // per_unit
        if units > 0:
            bonus = units * bonus_per
            segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))

    return segments


# ─── C2 中枢全局恢复 ─────────────────────────────────────────────

_BASE_BURN_3 = 0.75


def compute_global_burn(
    control_operators: list[Operator],
    buff_pool: "BuffPool",
    worker_count: int = 3,
) -> float:
    """计算工作干员的心情消耗率净值 (mood_burn)

    基础值 0.75/h（3人工位），中枢每名干员提供 +0.05/h 恢复。
    重岳孤光共照：+0.05/h，每 20 烟火额外 +0.05。
    """
    control_count = len(control_operators)
    recovery = control_count * 0.05

    names = {op.name for op in control_operators}
    if "重岳" in names:
        recovery += 0.05
        recovery += (buff_pool.yanhuo // 20) * 0.05

    burn = max(0.0, _BASE_BURN_3 - recovery)
    return burn
