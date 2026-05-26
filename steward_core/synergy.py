"""联动体系函数

每个体系一个独立函数。同层体系之间并行计算后线性叠加。
MVP 范围: A1(配对) / A3(技能计数) / A4(别名) / A5(自动化)。
A2 / A6 / A7 / B / C 层在后续迭代补充。
"""

from steward_core.models import LinearSegment, Operator

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

        # 统计同房其他干员中持有 target_cls 类型的数量
        count = 0
        for other in operators:
            if other.name == op.name:
                continue
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

# 自动化干员: {干员名: (等级, 每发电站加成%)}
# 来自 manu_prod_spd&power[000/010/020]
_A5_AUTO_TABLE: dict[str, tuple[int, float]] = {
    "森蚺": (5, 5.0),
    "掠风": (5, 5.0),
    "异客": (5, 5.0),
    "温蒂": (15, 15.0),
}


def synergy_automation(
    operators: list[Operator],
    room_type: str,
    power_count: int,
) -> tuple[list[LinearSegment], set[str]]:
    """若房间有自动化干员，返回 (自动化产出段, 需归零的干员名集合)"""
    if room_type != "Mfg":
        return [], set()

    # 找最高等级自动化干员
    best_level = 0
    best_bonus = 0.0
    auto_op_names = set()
    for op in operators:
        if op.name in _A5_AUTO_TABLE:
            auto_op_names.add(op.name)
            level, bonus = _A5_AUTO_TABLE[op.name]
            if bonus > best_bonus:
                best_level = level
                best_bonus = bonus

    if not auto_op_names:
        return [], set()

    total_bonus = power_count * best_bonus
    segments = [LinearSegment(a=total_bonus, b=0.0, t_start=0.0, dt=T)]

    zero_set = {op.name for op in operators if op.name not in auto_op_names}
    return segments, zero_set
