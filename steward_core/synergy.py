"""联动体系函数

每个体系一个独立函数。同层体系之间并行计算后线性叠加。
MVP 范围: A1/A3/A4/A5/A6/C1（A/C 层已完成）。
A2/A7/B 层在后续迭代补充。
"""

from dataclasses import dataclass

from steward_core.models import LinearSegment, Operator, LayoutConfig
from steward_core.efficiency_fn import ramping_efficiency

T = 12.0  # MVP 固定 12h 排班

# ─── 系统贡献者注册表 ────────────────────────────────────────────

@dataclass
class SystemContributor:
    """个人效率为0但对排班系统有非零贡献的干员"""
    name: str
    facility_types: list[str]      # 贡献的目标设施
    contribution_type: str          # "global_bonus" | "b_generator" | "facility_modifier" | "anchor"


_SYSTEM_CONTRIBUTORS: list[SystemContributor] = [
    # 中枢全局加成（C1）
    SystemContributor("凯尔希", ["Control"], "global_bonus"),
    # 宿舍 B 层生成者（B1 感知/B4 魔物料理/B5 无声共鸣）
    SystemContributor("森西", ["Dormitory"], "b_generator"),
    SystemContributor("爱丽丝", ["Dormitory"], "b_generator"),
    SystemContributor("车尔尼", ["Dormitory"], "b_generator"),
    SystemContributor("塑心", ["Dormitory"], "b_generator"),
    # 发电站设施数量修改器
    SystemContributor("承曦格雷伊", ["Power"], "facility_modifier"),
    # 制造站联动锚点（A1/A3/A5）
    SystemContributor("水月", ["Mfg"], "anchor"),
    SystemContributor("多萝西", ["Mfg"], "anchor"),
    SystemContributor("苍苔", ["Mfg"], "anchor"),
    SystemContributor("海沫", ["Mfg"], "anchor"),
    SystemContributor("森蚺", ["Mfg"], "anchor"),
    SystemContributor("温蒂", ["Mfg"], "anchor"),
    SystemContributor("掠风", ["Mfg"], "anchor"),
    SystemContributor("异客", ["Mfg"], "anchor"),
    SystemContributor("阿兰娜", ["Mfg"], "anchor"),
    SystemContributor("Miss.Christine", ["Mfg"], "anchor"),
    SystemContributor("怒潮凛冬", ["Mfg"], "anchor"),
]


def get_system_contributors(
    facility: str,
    contribution_type: str | None = None,
) -> list[str]:
    """获取指定设施的系统贡献者名称列表"""
    result: list[str] = []
    for c in _SYSTEM_CONTRIBUTORS:
        if facility in c.facility_types:
            if contribution_type is None or c.contribution_type == contribution_type:
                result.append(c.name)
    return result


def get_trade_order_equivalent_efficiency(
    op: "Operator",
    assigned_ids: set | None = None,
    op_lookup: dict | None = None,
) -> float:
    """A7 订单机制干员的贪心排序等效个人效率（自动量化 + 配对验证）

    核心假设：该体系核心以自身机制最大化效率（类比迷迭香≈70%），
    偏置用于贪心排序，实际回落在 _calc_trade() 完成。
    如果最优配置不可兑现（配对目标被占用等），偏置归零→自然回溯。

    三类处理：
    1. 订单倍数型（但书/龙舌兰/可露希尔/裁缝）：_get_trade_order_multiplier 自动算
    2. 配对型（德克萨斯/摩根/新约能天使）：验证配对目标可用性
    3. 同室人数/效率反馈型（巫恋/火哨/吉星/雪雉）：假设最优室友配置
    """
    if assigned_ids is None:
        assigned_ids = set()
    if op_lookup is None:
        op_lookup = {}

    # 1. 订单倍数型 — 自动量化
    has_multiplier = any(
        s.buff_id.startswith(("trade_ord_law", "trade_ord_closure",
                              "trade_ord_long", "trade_ord_wt&cost"))
        for s in op.skills
    )
    if has_multiplier:
        from steward_core.production import _get_trade_order_multiplier
        lmd_per_day, _ = _get_trade_order_multiplier([op])
        multiplier = lmd_per_day / 10265.0
        if multiplier <= 1.001:
            return 0.0
        return (multiplier - 1.0) * 1.63 * 100

    # 2. 配对型 — 验证配对目标
    for sk in op.skills:
        bid = sk.buff_id

        if bid.startswith("trade_ord_spd&cost_P"):
            # 德克萨斯(+65% w/ 拉普兰德) — 验证拉普兰德可用
            partner = "拉普兰德"
            if _partner_available(partner, assigned_ids, op_lookup):
                return 30.0  # 配对可兑现，但贪心无房间内回溯 → 保守偏置
            return 0.0

        if bid.startswith("trade_ord_limit&cost_P"):
            # 拉普兰德(+4 limit w/ 德克萨斯) — 验证德克萨斯可用
            partner = "德克萨斯"
            if _partner_available(partner, assigned_ids, op_lookup):
                return 10.0  # 上限修改器，保守偏置
            return 0.0

        if bid.startswith("trade_ord_spd_par"):
            if "par[001]" in bid:
                return 30.0  # 新约能天使: 3拉特兰×15%，但有配对风险
            if "par[000]" in bid:
                return 20.0  # 摩根: 需格帮室友，贪心无法保证房间内配对 → 保守

    # 3. 同室人数/效率反馈型 — 假设最优室友
    for sk in op.skills:
        bid = sk.buff_id

        if bid.startswith("trade_ord_vodfox"):
            # 巫恋低语: 归零他人，每人+45% → 3人房=135%
            return 75.0

        if bid.startswith("trade_ord_spd&share"):
            # 火哨/吉星: 除自身外每人+15%/+20%
            if "share[002]" in bid:
                return 40.0  # 吉星β: 2人×20%
            if "share[001]" in bid:
                return 20.0  # 吉星α: 2人×10%
            if "share[000]" in bid:
                return 30.0  # 火哨: 2人×15%

        if bid.startswith("trade_ord_spd_variable2"):
            # 雪雉天道酬勤: 他人每5%→额外+5%, 上限25%/35%
            if "variable2[001]" in bid:
                return 35.0  # β: 上限35%
            return 25.0      # α: 上限25%

    return 0.0


def _partner_available(name: str, assigned_ids: set, op_lookup: dict) -> bool:
    """检查配对目标是否在干员池中且未被其他设施占用"""
    for op in op_lookup.values():
        if op.name == name and op.char_id not in assigned_ids:
            return True
    return False


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


# ─── 爬升型效率 ───────────────────────────────────────────────────

# 爬升型技能表: {buffId: (首小时%, 增量%/h, 上限%)}
_RAMPING_SKILL_TABLE: dict[str, tuple[float, float, float]] = {
    "manu_prod_spd_addition[100]": (0.0, 2.0, 20.0),  # 例行清扫: 0→20%@2%/h
}


def operator_ramp_segments(
    op: Operator,
    room_type: str,
    product: str,
    T: float = 12.0,
) -> list[LinearSegment] | None:
    """检查干员是否持有爬升型技能，返回 ramping_efficiency 段

    返回值约定: 有爬升技能 → 分段列表，无 → None（由调用方回退到 constant_efficiency）。
    """
    for sk in op.skills:
        if sk.room_type != room_type:
            continue
        if sk.buff_id in _RAMPING_SKILL_TABLE:
            k0, r, ceiling = _RAMPING_SKILL_TABLE[sk.buff_id]
            return ramping_efficiency(k0=k0, r=r, ceiling=ceiling, mood_burn=0.0, T=T)
    return None


# ─── A3 技能类型计数 ─────────────────────────────────────────────

# 计数锚点: {干员名: 计数的技能类型}
_A3_COUNTER_TABLE: dict[str, str] = {
    "水月": "标准化",
    "多萝西": "莱茵科技",
    "苍苔": "金属工艺",
}
_A3_BONUS_PER = 5.0  # 每个该类技能 +5%


def skill_class(buff_name: str) -> str | None:
    """从 buff 名称提取技能类别，供 solver 制造站干员分类和 A3 体系使用"""
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
            sc = skill_class(sk.buff_name)
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

# 自动化 buff 版本 → 每发电站加成%: manu_prod_spd&power[000/010/020]
_POWER_BUFF_BONUS: dict[str, float] = {
    "manu_prod_spd&power[000]": 5.0,
    "manu_prod_spd&power[010]": 10.0,
    "manu_prod_spd&power[020]": 15.0,
}

# 名称→加成回退值（技能数据不可用时，如 building_data.json 缺失 buff_id 映射）
_A5_AUTO_FALLBACK: dict[str, float] = {
    "森蚺": 5.0,
    "掠风": 5.0,
    "异客": 5.0,
    "温蒂": 15.0,
}


def _automation_bonus(op: Operator) -> float:
    """获取干员的自动化加成（优先从技能 buff_id 检测，回退到名称查找）"""
    best = 0.0
    for sk in op.skills:
        if sk.buff_id in _POWER_BUFF_BONUS:
            b = _POWER_BUFF_BONUS[sk.buff_id]
            if b > best:
                best = b
    if best <= 0:
        best = _A5_AUTO_FALLBACK.get(op.name, 0.0)
    return best


def synergy_automation(
    operators: list[Operator],
    room_type: str,
    power_count: int,
) -> tuple[list[LinearSegment], set[str]]:
    """若房间有自动化干员，返回 (自动化产出段, 需归零的干员名集合)

    自动化干员的加成直接叠加（森蚺+温蒂共存时两者均生效）。
    检测方式：从干员技能中扫描 manu_prod_spd&power[*] buff_id，回退到名称查找。
    """
    if room_type != "Mfg":
        return [], set()

    total_bonus = 0.0
    auto_op_names = set()
    for op in operators:
        bonus = _automation_bonus(op)
        if bonus <= 0:
            continue
        auto_op_names.add(op.name)
        total_bonus += power_count * bonus

    if not auto_op_names:
        return [], set()

    segments = [LinearSegment(a=total_bonus, b=0.0, t_start=0.0, dt=T)]

    zero_set = {op.name for op in operators if op.name not in auto_op_names}
    return segments, zero_set


def compute_effective_power_count(
    power_operators: list[Operator],
    physical_count: int,
) -> int:
    """计算有效发电站数量（含设施数量修改器）

    承曦格雷伊"晨曦"（power_count[000]）：发电站额外+1（仅影响设施数量）。
    TODO: Lancet-2 + 森蚺中枢"我寻思能行"（control_pow_bot[000]）：发电站额外+2。
    """
    count = physical_count
    for op in power_operators:
        if _has_power_count_modifier(op):
            count += 1
    return count


def _has_power_count_modifier(op: Operator) -> bool:
    """检查干员是否持有发电站数量修改器（如承曦格雷伊"晨曦"）"""
    for sk in op.skills:
        if sk.buff_id == "power_count[000]":
            return True
    return False


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
    "维伊": ("train_level", 10.0, "Mfg", None, 30.0),
}

# 设施等级 （Mfg/Trade/Meeting 默认 Lv3，宿舍 Lv5 见 _DEFAULT_DORM_LEVELS）
_FACILITY_LEVEL = 3
# 243 布局默认宿舍等级总和（4 间 × Lv5 = 20）
_DEFAULT_DORM_LEVELS = 20  # 4 间 Lv5 宿舍


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
    train_level = sum(
        _FACILITY_LEVEL for r in layout.rooms if r.room_type == "Training"
    )

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
        elif count_key == "train_level":
            count = train_level
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


# ─── C1 扩展：中枢 per-operator 条件型加成 ───────────────────────

# 红松骑士团 group_id
_PINUS_GROUP = "pinus"

# 骑士标签持有者（name 集合作为数据驱动判定的安全网）
_KNIGHT_NAMES: set[str] = {
    "砾", "野鬃", "白金", "鞭刃", "暴雨", "耀骑士临光",
    "瑕光", "临光", "远牙", "灰毫", "焰尾", "薇薇安娜",
}


def _is_knight(op: "Operator") -> bool:
    """游戏内骑士 = kazimierz 势力 + 红松骑士团 + 硬编码补全"""
    return op.name in _KNIGHT_NAMES or op.nation_id == "kazimierz" or op.group_id == _PINUS_GROUP


def control_per_operator_bonus(
    control_ops: list["Operator"],
    room_ops: list["Operator"],
    product: str,
) -> float:
    """中枢干员对当前房间的条件型 per-operator 加成（百分值）

    焰尾: 每个红松骑士团 Mfg 干员 → CR+10%, PG-10%
    薇薇安娜: 每个骑士 Mfg 干员 → +7%
    """
    bonus = 0.0
    control_names = {op.name for op in control_ops}

    if "焰尾" in control_names:
        for op in room_ops:
            if op.group_id == _PINUS_GROUP:
                if product == "CombatRecord":
                    bonus += 10.0
                elif product == "PureGold":
                    bonus -= 10.0

    if "薇薇安娜" in control_names:
        for op in room_ops:
            if _is_knight(op):
                bonus += 7.0

    return bonus


# ─── B1 人间烟火 / 感知信息 / 巫术结晶 ──────────────────────────

@dataclass
class BuffPool:
    """全局 buff 点数池"""
    yanhuo: int = 0            # 人间烟火
    perception: int = 0        # 感知信息
    wushu_crystal: int = 0     # 巫术结晶
    thought_chains: int = 0    # 思维链环 (B3)
    silent_resonance: int = 0  # 无声共鸣 (B5) TODO: B5 生成待实现
    engineering_robots: int = 0  # 工程机器人 (B2)
    monster_cuisine: int = 0     # 魔物料理 (B4)


def compute_buff_pool(
    control_operators: list[Operator],
    suich_count: int = 5,
    dorm_operators: list[Operator] | None = None,
    dorm_level: int = 5,
    has_rosmontis_in_mfg: bool = False,
    has_ebnhlz_in_trade: bool = False,
    ling_mood_below_12: bool = False,
) -> BuffPool:
    """计算全局 buff 点数池（Phase 1 预计算）

    中枢源：
    - 令(mood>12): +15 烟火；令(mood≤12): +10 感知信息
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

    注：宿舍最高等级为 Lv5，默认以此计算。
    """
    if dorm_operators is None:
        dorm_operators = []

    names = {op.name for op in control_operators}
    yanhuo = 0
    perception = 0
    monster_cuisine = 0

    # 令: mood>12 → +15 烟火；mood≤12 → +10 感知信息
    if "令" in names:
        if ling_mood_below_12:
            perception += 10
        else:
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
    # B5 无声共鸣消费者 TODO: B5 生成待实现（塑心宿舍 → 无声共鸣 → 黑键贸易消费）
    "黑键": ("Trade", "silent_resonance", 2, 1.0),    # β: 每2共鸣+1%
}


# ─── 加成包（跨设施联动的最优支撑干员集） ───────────────────────

# 迷迭香联动链所需支撑干员
# 迷迭香超感(B3) → 需要 B1 感知信息生成者（令/夕/爱丽丝/车尔尼/黑键）+ 宿舍满员
ROSEMARY_SUPPORT: dict[str, list[str]] = {
    "Control": ["令", "夕"],
    "Trade": ["黑键"],
    "Dormitory": ["爱丽丝", "车尔尼", "森西"],
}

# B 层关键干员名称（避免多处字符串硬编码）
_B3_ROSEMARY = "迷迭香"
_B5_EBNHLZ = "黑键"


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


# ─── 制造站干员分类（供 solver 使用） ────────────────────────────

from dataclasses import dataclass as dc_field, field
from steward_core.models import Operator as OpModel


@dataclass
class MfgClassification:
    """制造站干员分类结果"""
    pure_efficiency: list = field(default_factory=list)
    anchors: list = field(default_factory=list)
    providers: list = field(default_factory=list)


def classify_mfg_operators(
    operators: list, product: str, anchor_names: set[str],
) -> "MfgClassification":
    """将制造站干员分类为 纯效率/联动锚点/技能提供者"""
    result = MfgClassification()
    for op in operators:
        is_anchor = op.name in anchor_names

        has_skill_label = False
        for sk in op.skills:
            if sk.room_type != "Mfg":
                continue
            if skill_class(sk.buff_name):
                has_skill_label = True
                break

        if is_anchor:
            result.anchors.append(op)
        elif has_skill_label:
            result.providers.append(op)
        elif op.name in _B_LAYER_CONSUMER_TABLE and _B_LAYER_CONSUMER_TABLE[op.name][0] == "Mfg":
            result.providers.append(op)
        elif op.name in _A6_FACILITY_TABLE and _A6_FACILITY_TABLE[op.name][2] == "Mfg":
            result.providers.append(op)
        else:
            result.pure_efficiency.append(op)

    return result


def prune_equivalent(pure_ops: list, top_k: int = 3) -> list:
    """等价类合并 — 纯效率只保留 top_k 名"""
    sorted_ops = sorted(pure_ops, key=lambda op: -op.best_efficiency("Mfg"))
    return sorted_ops[:top_k]


def build_candidate_pool(
    all_ops: list, classification: "MfgClassification",
) -> list:
    """锚点池筛选 — anchors + providers + top_k 纯效率"""
    seen = {op.char_id for op in classification.anchors}
    pool = list(classification.anchors)

    for op in classification.providers:
        if op.char_id not in seen:
            seen.add(op.char_id)
            pool.append(op)

    top_pure = prune_equivalent(classification.pure_efficiency, top_k=5)
    for op in top_pure:
        if op.char_id not in seen:
            seen.add(op.char_id)
            pool.append(op)

    return pool


# ─── A2 阵营计数（同房） ─────────────────────────────────────────

# 阵营计数表: {持有者名: (字段名, 匹配值, 每人加成%, 产物或None, 设施类型)}
_A2_FACTION_TABLE: dict[str, tuple[str, str, float, str | None, str | None]] = {
    "历阵锐枪芬": ("team_id", "reserve1", 10.0, None, "Mfg"),
}


def synergy_faction_room(
    operators: list[Operator],
    room_type: str,
    product: str,
) -> list[LinearSegment]:
    """统计同房间内特定阵营/队伍干员数量，为持有者提供效率加成

    A2 体系：持有者根据同房间内匹配阵营的干员数量获得加成。
    """
    names = {op.name for op in operators}
    segments = []

    for holder_name, (field, value, bonus_per, target_product, target_room) in _A2_FACTION_TABLE.items():
        if holder_name not in names:
            continue
        if target_room is not None and room_type != target_room:
            continue
        if target_product is not None and product != target_product:
            continue

        count = sum(1 for op in operators if getattr(op, field, None) == value)
        bonus = count * bonus_per
        if bonus > 0:
            segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))

    return segments


# ─── B7 跨房间配对 ───────────────────────────────────────────────

# 跨房间配对表: {持有者名: (目标名, 目标设施, 加成%, 产物或None, 当前设施)}
_B7_CROSS_PAIR_TABLE: dict[str, tuple[str, str, float, str | None, str | None]] = {
    "烈夏": ("古米", "Trade", 35.0, "CombatRecord", "Mfg"),
}


def synergy_cross_room_pair(
    operators: list[Operator],
    room_type: str,
    product: str,
    all_assignments: dict[str, list[Operator]],
) -> list[LinearSegment]:
    """检查跨设施干员条件配对，为持有者提供效率加成

    B7 体系：干员 A 在某设施时，若干员 B 在另一设施则触发加成。
    """
    names = {op.name for op in operators}
    segments = []

    for holder_name, (target_name, target_facility, bonus_per, target_product, target_room) in _B7_CROSS_PAIR_TABLE.items():
        if holder_name not in names:
            continue
        if target_room is not None and room_type != target_room:
            continue
        if target_product is not None and product != target_product:
            continue

        target_ops = all_assignments.get(target_facility, [])
        target_names = {op.name for op in target_ops}
        if target_name in target_names:
            segments.append(LinearSegment(a=bonus_per, b=0.0, t_start=0.0, dt=T))

    return segments
