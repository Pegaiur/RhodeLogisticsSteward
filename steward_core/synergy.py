"""联动体系函数

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

from dataclasses import dataclass
from typing import NamedTuple

from steward_core.models import LinearSegment, Operator, LayoutConfig
from steward_core.efficiency_fn import ramping_efficiency

# ─── 硬编码表类型定义 ──────────────────────────────────────────────


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
    SystemContributor("灵知", ["Control"], "global_bonus"),
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
    # 贸易站联动锚点（A7 反馈型 + 配对型）
    SystemContributor("巫恋", ["Trade"], "anchor"),
    SystemContributor("火哨", ["Trade"], "anchor"),
    SystemContributor("吉星", ["Trade"], "anchor"),
    SystemContributor("雪雉", ["Trade"], "anchor"),
    SystemContributor("德克萨斯", ["Trade"], "anchor"),
    SystemContributor("摩根", ["Trade"], "anchor"),
    SystemContributor("新约能天使", ["Trade"], "anchor"),
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


def _is_glasgow(op: "Operator") -> bool:
    """判定干员是否属于格拉斯哥帮（通过 group_id）"""
    return getattr(op, "group_id", None) == "glasgow"


# ─── A·干员配对 ─────────────────────────────────────────────────

# 配对表: (持有者名, 目标名, 产物, 加成%)
# 来自 buffs_infrastructure.json 中 efficiency=0 的条件型 buff
_A_PAIR_TABLE: dict[tuple[str, str, str], float] = {
    ("阿兰娜", "温米", "PureGold"): 15.0,
    ("Miss.Christine", "酒神", "CombatRecord"): 30.0,
    ("怒潮凛冬", "乌萨斯学生自治团", "CombatRecord"): 10.0,
}


def synergy_pair(
    operators: list[Operator],
    room_type: str,
    product: str,
    T: float,
) -> list[LinearSegment]:
    """识别同房间干员配对组合，输出聚合常数段"""
    if room_type != "Mfg":
        return []

    names = {op.name for op in operators}
    segments = []

    for (holder_name, target_name, p_type), bonus in _A_PAIR_TABLE.items():
        if product != p_type:
            continue
        if holder_name in names and target_name in names:
            segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))

    return segments


# ─── A·订单压缩 ───────────────────────────────────────────

def synergy_jie_order(
    operators: list[Operator],
    room_type: str,
    control_operators: list[Operator],
    T: float,
) -> list[LinearSegment]:
    """孑市井之道/摊贩经济：订单上限压缩+每订单效率放大

    精2（市井之道+摊贩经济）: 效率恒定 = 压缩后上限 × 4%
    精1（仅市井之道）: ramp近似，订单随时间爬升
    灵知在中枢时：每名谢拉格贸易站干员 → 订单上限+6
    """
    if room_type != "Trade":
        return []

    names = {op.name for op in operators}
    if "孑" not in names:
        return []

    has_limit_count = False
    has_limit_diff = False
    for op in operators:
        if op.name != "孑":
            continue
        for sk in op.skills:
            if sk.buff_id == "trade_ord_limit_count[000]":
                has_limit_count = True
            if sk.buff_id == "trade_ord_limit_diff[000]":
                has_limit_diff = True

    if not has_limit_count:
        return []

    # 其他干员效率总和（用于压缩订单上限）
    # 排除持有订单机制 buff 的干员（但书/龙舌兰等），其效率为动态计算值
    _OBSERVE_BLACKLIST = ("trade_ord_law", "trade_ord_long", "trade_ord_closure")
    other_eff = 0.0
    for op in operators:
        if op.name == "孑":
            continue
        if any(s.buff_id.startswith(_OBSERVE_BLACKLIST) for s in op.skills if s.room_type == "Trade"):
            continue
        eff = op.best_efficiency(room_type, "Money")
        if eff > 0:
            other_eff += eff

    # 订单上限 = 10 - floor(其他干员效率/10)，最低为1
    order_limit = max(1, 10 - int(other_eff) // 10)

    # 灵知精密计算: 每名谢拉格贸易站干员 → 上限+6
    if control_operators:
        ctrl_names = {op.name for op in control_operators}
        if "灵知" in ctrl_names:
            karlan_count = sum(
                1 for op in operators
                if op.group_id == "karlan"
            )
            order_limit += karlan_count * 6

    ceiling = order_limit * 4.0

    if has_limit_diff:
        # 精2: 效率恒定
        return [LinearSegment(a=ceiling, b=0.0, t_start=0.0, dt=T)]

    # 精1: ramp近似，订单在3小时内线性爬升至稳态
    ramp = ceiling / 3.0
    if T <= 3.0:
        return [LinearSegment(a=0.0, b=ramp, t_start=0.0, dt=T)]
    return [
        LinearSegment(a=0.0, b=ramp, t_start=0.0, dt=3.0),
        LinearSegment(a=ceiling, b=0.0, t_start=3.0, dt=T - 3.0),
    ]


# ─── 仓库容量→效率 ─────────────────────────────────────────────────

def synergy_capacity_to_eff(
    operators: list[Operator],
    room_type: str,
    product: str,
    T: float,
) -> list[LinearSegment]:
    """房间内仓库容量转化为效率加成

    红云回收利用(每格+2%) / 泡泡大就是好！(≤16格 1%/格, >16格 3%/格)。
    大就是好！与回收利用互斥，优先生效。
    """
    if room_type != "Mfg":
        return []

    names = {op.name for op in operators}
    has_paopao = "泡泡" in names
    has_hongyun = "红云" in names
    if not has_paopao and not has_hongyun:
        return []

    total_cap = sum(sk.capacity_bonus for op in operators for sk in op.skills)

    if has_paopao:
        eff = min(total_cap, 16) * 1.0 + max(0, total_cap - 16) * 3.0
    else:
        eff = total_cap * 2.0

    return [LinearSegment(a=eff, b=0.0, t_start=0.0, dt=T)] if eff > 0 else []


# ─── 配合意识（效率放大器） ──────────────────────────────────────

def synergy_efficiency_amplifier(
    operators: list[Operator],
    room_type: str,
    product: str,
    T: float,
) -> list[LinearSegment]:
    """槐琥配合意识：其他干员每5%效率额外提供5%，上限40%

    计算房间内除槐琥外干员的效率总和后取整。
    """
    if room_type != "Mfg":
        return []

    names = {op.name for op in operators}
    if "槐琥" not in names:
        return []

    others_eff = sum(
        op.best_efficiency(room_type, product)
        for op in operators if op.name != "槐琥"
    )
    bonus = (int(others_eff) // 5) * 5
    bonus = min(bonus, 40.0)

    return [LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T)] if bonus > 0 else []


# ─── 归零变体 ─────────────────────────────────────────────────────

# 归零变体表: {buff_id前缀: (补偿效率%/人, 补偿容量/人, 归零他人)}
_ZEROING_VARIANT_TABLE: dict[str, tuple[float, int, bool]] = {
    "manu_prod_spd&manu[000]": (0.0, 0, True),   # 科学改造: 归零他人，每干员+5容量
    "manu_prod_spd&manu[100]": (10.0, 0, True),   # 流程优化: 归零他人，每干员+10%效率
}


def synergy_zeroing_variant(
    operators: list[Operator],
    room_type: str,
    product: str,
    T: float,
) -> tuple[list[LinearSegment], set[str]]:
    """归零变体：类似 A5 自动化但补偿机制不同

    Returns:
        (效率加成段列表, 需归零的干员名集合)
    """
    if room_type != "Mfg":
        return [], set()

    best_eff = 0.0
    has_zeroing = False

    for op in operators:
        for sk in op.skills:
            if sk.room_type != "Mfg":
                continue
            if sk.buff_id in _ZEROING_VARIANT_TABLE:
                has_zeroing = True
                peff, _, _ = _ZEROING_VARIANT_TABLE[sk.buff_id]
                if peff > best_eff:
                    best_eff = peff

    if not has_zeroing:
        return [], set()

    head_count = len(operators)
    bonus = best_eff * head_count
    segments = [LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T)] if bonus > 0 else []

    zero_names = set()
    for op in operators:
        has_holder = any(
            sk.buff_id in _ZEROING_VARIANT_TABLE for sk in op.skills if sk.room_type == "Mfg"
        )
        if not has_holder:
            zero_names.add(op.name)

    return segments, zero_names


# ─── 机械精通（作业平台） ──────────────────────────────────────────

_OP_PLATFORM_NAMES: set[str] = {
    "Lancet-2", "Castle-3", "THRM-EX", "正义骑士号",
}

# 机械精通表: {buff_id: 每台加成%}
_TOKEN_PROD_TABLE: dict[str, float] = {
    "manu_token_prod_spd[000]": 5.0,
    "manu_token_prod_spd[010]": 10.0,
}


def synergy_token_prod(
    operators: list[Operator],
    room_type: str,
    product: str,
    power_platforms: dict[str, bool] | None = None,
    T: float = 12.0,
) -> list[LinearSegment]:
    """阿兰娜机械精通：作业平台进驻发电站时提供贵金属加成

    power_platforms: {名称: 是否在发电站}
    """
    if room_type != "Mfg":
        return []
    if product != "PureGold":
        return []
    if power_platforms is None:
        power_platforms = {}

    platform_count = sum(1 for name in _OP_PLATFORM_NAMES if power_platforms.get(name))

    for op in operators:
        for sk in op.skills:
            if sk.room_type != "Mfg":
                continue
            if sk.buff_id in _TOKEN_PROD_TABLE:
                bonus = platform_count * _TOKEN_PROD_TABLE[sk.buff_id]
                if bonus > 0:
                    return [LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T)]

    return []


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


# ─── A·技能计数 ─────────────────────────────────────────────

# 计数锚点: {干员名: 计数的技能类型}
_A_SKILL_COUNT_TABLE: dict[str, str] = {
    "水月": "标准化",
    "多萝西": "莱茵科技",
    "苍苔": "金属工艺",
}
_A_SKILL_COUNT_BONUS = 5.0  # 每个该类技能 +5%


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
    T: float = 12.0,
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
        if op.name not in _A_SKILL_COUNT_TABLE:
            continue
        target_cls = _A_SKILL_COUNT_TABLE[op.name]

        # 统计同房所有干员（含自身）中持有 target_cls 类型的数量
        count = 0
        for other in operators:
            if target_cls in op_classes.get(other.name, set()):
                count += 1

        if count > 0:
            bonus = count * _A_SKILL_COUNT_BONUS
            segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))

    return segments


# ─── A·技能别名 ─────────────────────────────────────────────

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


# ─── A·自动化 ───────────────────────────────────────────────────

# 自动化 buff 版本 → 每发电站加成%: manu_prod_spd&power[000/010/020]
_POWER_BUFF_BONUS: dict[str, float] = {
    "manu_prod_spd&power[000]": 5.0,
    "manu_prod_spd&power[010]": 10.0,
    "manu_prod_spd&power[020]": 15.0,
}

# 名称→加成回退值（技能数据不可用时，如 building_data.json 缺失 buff_id 映射）
_A_AUTOMATION_FALLBACK: dict[str, float] = {
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
        best = _A_AUTOMATION_FALLBACK.get(op.name, 0.0)
    return best


def synergy_automation(
    operators: list[Operator],
    room_type: str,
    power_count: int,
    T: float,
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


# ─── A·低语（巫恋·归零反馈）───────────────────────────────

def synergy_whisper(
    operators: list[Operator],
    room_type: str,
    T: float,
) -> tuple[list[LinearSegment], set[str]]:
    """巫恋低语 (trade_ord_vodfox): 归零其他干员效率，自身每人+45%

    Returns:
        (效率加成段, 被归零的干员名集合)
    """
    if room_type != "Trade":
        return [], set()

    whisper_ops = []
    for op in operators:
        for sk in op.skills:
            if sk.buff_id.startswith("trade_ord_vodfox"):
                whisper_ops.append(op)
                break

    if not whisper_ops:
        return [], set()

    whisper_names = {op.name for op in whisper_ops}
    zero_set = {op.name for op in operators if op.name not in whisper_names}
    total_bonus = sum(len(operators) - 1 for _ in whisper_ops) * 45.0

    segments = [LinearSegment(a=total_bonus, b=0.0, t_start=0.0, dt=T)]
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


# ─── A·设施数量联动 ─────────────────────────────────────────────

# 设施数量联动表: {干员名: (计数对象, 每单位加成%, 设施类型, 产物, 上限或无)}
# buffs_infrastructure.json 中 efficiency=0 的条件型 buff，
# 按全基建设施数量统计后输出加成
_A_FACILITY_LINK_TABLE: dict[str, FacilityLinkEntry] = {
    "清流": FacilityLinkEntry("trade_count", 20.0, "Mfg", "PureGold", None),
    "引星棘刺": FacilityLinkEntry("trade_count", 3.0, "Mfg", "PureGold", None),
    "娜仁图亚": FacilityLinkEntry("dorm_levels", 1.0, "Mfg", "PureGold", None),
    "空弦": FacilityLinkEntry("dorm_levels", 2.0, "Trade", "Money", None),
    "伺夜": FacilityLinkEntry("meeting_level", 5.0, "Trade", "Money", 40.0),
    "渡桥": FacilityLinkEntry("meeting_level", 5.0, "Trade", "Money", 30.0),
    "石英": FacilityLinkEntry("mfg_recipe_types", 2.0, "Trade", "Money", None),
    "维伊": FacilityLinkEntry("train_level", 10.0, "Mfg", None, 30.0),
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
    T: float = 12.0,
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
        if name not in _A_FACILITY_LINK_TABLE:
            continue
        count_key, bonus_per, target_room, target_product, cap = _A_FACILITY_LINK_TABLE[name]

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


# ─── C·中枢全局效率 ─────────────────────────────────────────────

# 中枢全局效率表: {干员名: (制造加成%, 贸易加成%)}
# buffs_infrastructure.json 中 efficiency=0 的条件型 CONTROL buff
# 同种效果取最高（不叠加）
_C_CONTROL_GLOBAL_TABLE: dict[str, GlobalBonusEntry] = {
    "凯尔希": GlobalBonusEntry(2.0, 0.0),
    "Mon3tr": GlobalBonusEntry(2.0, 0.0),
    "望": GlobalBonusEntry(2.0, 7.0),
}

# 怪物猎人小队干员名（中枢条件型加成判定用）
_MH_NAMES: set[str] = {"麒麟R夜刀", "炼金术士"}

# 龙门近卫局干员名（中枢条件型加成判定用）
_LUNG_MEN_GUARD_NAMES: set[str] = {"陈", "星熊", "诗怀雅", "斩业星熊"}

# 黑钢国际 group_id 与持有者（老友相聚）
_BLACKSTEEL_GROUP = "blacksteel"
_BLACKSTEEL_HOLDERS: set[str] = {"涤火杰西卡"}

_GLASGOW_GROUP = "glasgow"

# Trade 订单机制型锚点的 buff_id 前缀（classify_trade_operators 内联检测）
_ORDER_ANCHOR_PREFIXES = ("trade_ord_law", "trade_ord_long", "trade_ord_closure", "trade_ord_limit_count")


@dataclass
class GlobalBonus:
    """中枢全局效率加成"""
    mfg_bonus: float = 0.0
    trade_bonus: float = 0.0


def compute_control_global_bonus(
    control_operators: list[Operator],
    power_platforms: dict[str, bool] | None = None,
) -> GlobalBonus:
    """计算中枢干员提供的全局制造/贸易加成

    同种效果取最高值（游戏内描述"同种效果取最高"）。
    """
    if power_platforms is None:
        power_platforms = {}

    names = {op.name for op in control_operators}
    best_mfg = 0.0
    best_trade = 0.0

    for name in names:
        if name in _C_CONTROL_GLOBAL_TABLE:
            m, t = _C_CONTROL_GLOBAL_TABLE[name]
            best_mfg = max(best_mfg, m)
            best_trade = max(best_trade, t)

    # 布丁超频: ≥2 作业平台在发电站 → 制造+2%
    if "布丁" in names:
        platform_count = sum(1 for n in _OP_PLATFORM_NAMES if power_platforms.get(n))
        if platform_count >= 2:
            best_mfg = max(best_mfg, 2.0)

    # 麒麟R夜刀以身作则: 怪物猎人小队同中枢 → 制造+2%
    if "麒麟R夜刀" in names:
        if any(n in _MH_NAMES and n != "麒麟R夜刀" for n in names):
            best_mfg = max(best_mfg, 2.0)

    # 炼金术士秘传交涉术: 怪物猎人小队同中枢 → 贸易+7%
    if "炼金术士" in names:
        if any(n in _MH_NAMES and n != "炼金术士" for n in names):
            best_trade = max(best_trade, 7.0)

    # 斩业星熊共事情谊: 龙门近卫局同中枢 → 制造+3%
    if "斩业星熊" in names:
        if any(n in _LUNG_MEN_GUARD_NAMES and n != "斩业星熊" for n in names):
            best_mfg = max(best_mfg, 3.0)

    return GlobalBonus(mfg_bonus=best_mfg, trade_bonus=best_trade)


# ─── C·中枢 per-operator 条件型加成 ───────────────────────

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
    room_type: str = "Mfg",
) -> float:
    """中枢干员对当前房间的条件型 per-operator 加成（百分值）

    焰尾: 每个红松骑士团 Mfg 干员 → CR+10%, PG-10%
    薇薇安娜: 每个骑士 Mfg 干员 → +7%
    老友相聚: 每黑钢国际 Mfg 干员 → +5%
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

    # 老友相聚: 每黑钢国际干员在制造站 → +5%
    if room_type == "Mfg":
        for name in control_names:
            if name in _BLACKSTEEL_HOLDERS:
                for op in room_ops:
                    if op.group_id == _BLACKSTEEL_GROUP:
                        bonus += 5.0
                break

    return bonus


# ─── B·人间烟火 / 感知信息 / 巫术结晶 ──────────────────────────

@dataclass
class BuffPool:
    """全局 buff 点数池"""
    yanhuo: int = 0            # 人间烟火
    perception: int = 0        # 感知信息
    wushu_crystal: int = 0     # 巫术结晶
    thought_chains: int = 0    # 思维链环 (B3)
    silent_resonance: int = 0  # 无声共鸣 (B5) — 由塑心宿舍 + 黑键感知转化生成
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
    layout: LayoutConfig | None = None,
    perception_from_office: int = 0,
    has_wuyou_in_trade: bool = False,
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

    贸易源（B1 烟火）：
    - 乌有（在贸易站）: 宿舍每有1名干员→烟火+1

    办公室源（B1 感知/烟火）：
    - 絮雨巡游+追忆: 每额外招募位+10记忆碎片→感知（243布局 Lv3=+20）
    - 桑葚: 每招募位+10烟火（当迷迭香在Mfg时絮雨占用唯一Office工位，桑葚排除）

    宿舍源（B4 魔物料理）：
    - 森西大食堂: 宿舍每级→1魔物料理

    宿舍源（B5 无声共鸣）：
    - 塑心: 宿舍每有1名干员→无声共鸣+1
    - 黑键（在贸易站）: 感知信息→无声共鸣 1:1

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

    # ─── 贸易源烟火 ───

    # 乌有: 宿舍每有1名干员→烟火+1
    if has_wuyou_in_trade and dorm_operators:
        yanhuo += len(dorm_operators)

    # ─── 办公室源感知 ───

    # 絮雨巡游+追忆: 每额外招募位+10记忆碎片→感知（243 Lv3: 2额外招募位=20）
    perception += perception_from_office

    # ─── 宿舍源魔物料理 ───

    # 森西大食堂: 宿舍每级→1魔物料理
    if _dorm_has_buff(dorm_operators, "dorm_rec_bd_dungeon[000]"):
        monster_cuisine += dorm_level

    # 12h 班次 mood 不衰减（令杯莫停消除岁干员消耗）
    wushu_crystal = yanhuo // 5  # 烟火→巫术结晶（截云消费）
    thought_chains = perception  # B3: 感知信息→思维链环（1:1，迷迭香消费）
    eng_robots = compute_engineering_robots(layout) if layout is not None else 0

    # ─── B·无声共鸣 ───

    silent_resonance = 0
    # 黑键在贸易站: 感知信息→无声共鸣 1:1
    if has_ebnhlz_in_trade:
        silent_resonance += perception
    # 塑心在宿舍: 每名干员→无声共鸣+1
    if dorm_operators:
        suxin_names = {op.name for op in dorm_operators}
        if "塑心" in suxin_names:
            silent_resonance += len(dorm_operators)

    return BuffPool(
        yanhuo=yanhuo, perception=perception,
        wushu_crystal=wushu_crystal, thought_chains=thought_chains,
        monster_cuisine=monster_cuisine,
        engineering_robots=eng_robots,
        silent_resonance=silent_resonance,
    )


def _dorm_has_buff(dorm_operators: list[Operator], buff_id: str) -> bool:
    """检查宿舍干员列表中是否存在持有指定 buff_id 的干员"""
    for op in dorm_operators:
        for sk in op.skills:
            if sk.buff_id == buff_id:
                return True
    return False


def compute_engineering_robots(layout: LayoutConfig) -> int:
    """计算工程机器人总数 = Σ(每间设施 × 等级)，上限 64

    243 布局 14 间设施 Lv3 → 42 机器人
    """
    return sum(_FACILITY_LEVEL for _ in layout.rooms)


# B 层 buff 池消费者表: {干员名: (设施类型, pool_key, 每单位, 每单位加成%)}
_B_BUFF_CONSUMER_TABLE: dict[str, BuffConsumerEntry] = {
    # B1 烟火消费者
    "黍": BuffConsumerEntry("Mfg", "yanhuo", 3, 1.0),
    "桑葚": BuffConsumerEntry("Mfg", "yanhuo", 3, 1.0),
    "乌有": BuffConsumerEntry("Trade", "yanhuo", 1, 1.0),
    "截云": BuffConsumerEntry("Mfg", "wushu_crystal", 1, 2.0),
    "铎铃": BuffConsumerEntry("Trade", "yanhuo", 10, 0.0),
    # B2 工程机器人消费者
    "至简": BuffConsumerEntry("Mfg", "engineering_robots", 8, 5.0),
    # B3 思维链环消费者
    "迷迭香": BuffConsumerEntry("Mfg", "thought_chains", 1, 1.0),
    # B4 魔物料理消费者
    "玛露西尔": BuffConsumerEntry("Mfg", "monster_cuisine", 1, 1.0),
    # B5 无声共鸣消费者
    "黑键": BuffConsumerEntry("Trade", "silent_resonance", 2, 1.0),
}


# ─── 加成包（跨设施联动的最优支撑干员集） ───────────────────────

# 迷迭香联动链所需支撑干员
# 迷迭香超感(B3) → 需要 B1 感知信息生成者（令/夕/爱丽丝/车尔尼/黑键）+ 宿舍满员
ROSEMARY_SUPPORT: dict[str, list[str]] = {
    "Control": ["令", "夕"],
    "Trade": ["黑键"],
    "Dormitory": ["爱丽丝", "车尔尼", "森西", "塑心"],
    "Office": ["絮雨"],
}

# B 层关键干员名称（避免多处字符串硬编码）
_B_ROSEMARY = "迷迭香"
_B_EBENHOLZ = "黑键"


def synergy_buff_pool_consumer(
    operators: list[Operator],
    room_type: str,
    product: str,
    buff_pool: BuffPool,
    T: float,
) -> list[LinearSegment]:
    """B 层消费者：将 BuffPool 中的点数转化为房间效率加成

    覆盖 B1(烟火/巫术结晶)/B2(工程机器人)/B3(思维链环)/B4(魔物料理)/B5(无声共鸣)。
    """
    names = {op.name for op in operators}
    segments = []

    for name in names:
        if name not in _B_BUFF_CONSUMER_TABLE:
            continue
        target_room, pool_key, per_unit, bonus_per = _B_BUFF_CONSUMER_TABLE[name]
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


# ─── C·中枢心情恢复 ─────────────────────────────────────────────

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
        elif op.name in _B_BUFF_CONSUMER_TABLE and _B_BUFF_CONSUMER_TABLE[op.name][0] == "Mfg":
            result.providers.append(op)
        elif op.name in _A_FACILITY_LINK_TABLE and _A_FACILITY_LINK_TABLE[op.name][2] == "Mfg":
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
    room_type: str | None = None,
    product: str | None = None,
) -> list:
    """锚点池筛选 — anchors + providers + top_k 纯效率

    锚点按 best_efficiency 降序排列，确保高产能锚点优先参与组合生成。
    """
    seen = {op.char_id for op in classification.anchors}
    if room_type is not None:
        anchors = sorted(classification.anchors, key=lambda op: -op.best_efficiency(room_type, product))
    else:
        anchors = list(classification.anchors)
    pool = list(anchors)

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


def classify_trade_operators(
    operators: list, anchor_names: set[str],
) -> "MfgClassification":
    """将 Trade 干员分类为 纯效率/联动锚点/技能提供者

    与 Mfg 同架构，复用 MfgClassification。
    锚点包含注册锚点（反馈型/配对型）+ 订单机制型（但书/龙舌兰/可露希尔）。
    裁缝 (trade_ord_wt&cost) 不视为锚点——裁缝是支撑工具人。
    """
    result = MfgClassification()

    for op in operators:
        is_registered = op.name in anchor_names
        is_order_anchor = any(
            s.room_type == "Trade" and s.buff_id.startswith(_ORDER_ANCHOR_PREFIXES)
            for s in op.skills
        )

        if is_registered or is_order_anchor:
            result.anchors.append(op)
        elif op.name in _B_BUFF_CONSUMER_TABLE and _B_BUFF_CONSUMER_TABLE[op.name][0] == "Trade":
            result.providers.append(op)
        elif op.name in _A_FACILITY_LINK_TABLE and _A_FACILITY_LINK_TABLE[op.name][2] == "Trade":
            result.providers.append(op)
        else:
            result.pure_efficiency.append(op)

    return result


# ─── 鸿雪销路宣发 + 际崖居民 ────────────────────────────────────

# 杜林族干员名（硬编码，character_identity.json 无 raceId 字段）
_DURIN_NAMES: set[str] = {"杜林", "桃金娘", "褐果", "至简"}


def synergy_trade_gold_lines(
    operators: list[Operator],
    room_type: str,
    product: str,
    layout: LayoutConfig,
    durin_names: set[str] | None = None,
    T: float = 12.0,
) -> list[LinearSegment]:
    """鸿雪销路宣发(每赤金线+5%) + 际崖居民(杜林族→额外赤金线，上限4)

    赤金线 = Mfg PureGold 房间数 + min(杜林族干员数, 4)
    """
    if room_type != "Trade":
        return []

    names = {op.name for op in operators}
    if "鸿雪" not in names:
        return []

    gold_lines = sum(1 for r in layout.rooms if r.room_type == "Mfg" and r.product == "PureGold")

    if durin_names:
        durin_count = len(durin_names)
        gold_lines += min(durin_count, 4)

    bonus = gold_lines * 5.0
    return [LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T)] if bonus > 0 else []


# ─── A·阵营计数（同房） ─────────────────────────────────────────

# 阵营计数表: {持有者名: (字段名, 匹配值, 每人加成%, 产物或None, 设施类型)}
_A_ROOM_FACTION_TABLE: dict[str, FactionEntry] = {
    "历阵锐枪芬": FactionEntry("team_id", "reserve1", 10.0, None, "Mfg"),
    "摩根": FactionEntry("group_id", "glasgow", 20.0, "Money", "Trade"),
    "新约能天使": FactionEntry("nation_id", "laterano", 15.0, "Money", "Trade"),
}

# A·同房阵营额外加成: {持有者名: (目标名, 额外加成%, 产物或None, 设施类型)}
# 特例：摩根帮派指南针——当推进之王同在贸易站时，除每人+20%外额外+35%
_A_ROOM_FACTION_EXTRA: dict[str, ExtraFactionEntry] = {
    "摩根": ExtraFactionEntry("推进之王", 35.0, "Money", "Trade"),
}


def synergy_faction_room(
    operators: list[Operator],
    room_type: str,
    product: str,
    T: float,
) -> list[LinearSegment]:
    """统计同房间内特定阵营/队伍干员数量，为持有者提供效率加成

    A2 体系：持有者根据同房间内匹配阵营的干员数量获得加成。
    """
    names = {op.name for op in operators}
    segments = []

    for holder_name, (field, value, bonus_per, target_product, target_room) in _A_ROOM_FACTION_TABLE.items():
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

    # A2 专属额外加成（如摩根+推王同在贸易站→额外+35%）
    for holder_name, (extra_name, extra_bonus, target_product, target_room) in _A_ROOM_FACTION_EXTRA.items():
        if holder_name not in names:
            continue
        if target_room is not None and room_type != target_room:
            continue
        if target_product is not None and product != target_product:
            continue
        if extra_name in names:
            segments.append(LinearSegment(a=extra_bonus, b=0.0, t_start=0.0, dt=T))

    return segments


def get_synergy_enablers(
    all_operators: list[Operator],
    room_type: str,
    product: str | None = None,
) -> list[Operator]:
    """从 _A_ROOM_FACTION_TABLE 反查联动使能者

    返回无目标设施技能、但属于 A2 阵营计数范围、能提升同房持有者效率的干员。
    特例：推进之王（无 Trade 技能，但能触发摩根帮派指南针额外+35%+A2计数）。

    这些干员被 Phase 1/Phase 3a 的 has_skill_for 门禁阻挡，需单独补充入池。
    """
    enablers: list[Operator] = []
    seen: set[str] = set()

    for holder_name, (field, value, bonus_per, target_product, target_room) in _A_ROOM_FACTION_TABLE.items():
        if target_room is not None and room_type != target_room:
            continue
        if target_product is not None and product is not None and product != target_product:
            continue

        for op in all_operators:
            if op.name in seen:
                continue
            if getattr(op, field, None) != value:
                continue
            # 已在普通池中的不重复
            if room_type == "Trade":
                if op.has_skill_for("Trade", "Money"):
                    continue
                if any(s.buff_id.startswith(("trade_ord_law", "trade_ord_long",
                                              "trade_ord_closure", "trade_ord_vodfox",
                                              "trade_ord_limit_count"))
                       for s in op.skills):
                    continue
            elif room_type == "Mfg":
                if op.has_skill_for("Mfg", product):
                    continue
            seen.add(op.name)
            enablers.append(op)

    return enablers


# ─── B·跨房间配对 ───────────────────────────────────────────────

# 跨房间配对表: {持有者名: (目标名, 目标设施, 加成%, 产物或None, 当前设施)}
_B_CROSS_ROOM_PAIR_TABLE: dict[str, CrossRoomPairEntry] = {
    "烈夏": CrossRoomPairEntry("古米", "Trade", 35.0, "CombatRecord", "Mfg"),
    "深巡": CrossRoomPairEntry("乌尔比安", None, 10.0, "Money", "Trade"),
    "贝洛内": CrossRoomPairEntry("伺夜", None, 10.0, "Money", "Trade"),
}


def synergy_cross_room_pair(
    operators: list[Operator],
    room_type: str,
    product: str,
    all_assignments: dict[str, list[Operator]],
    T: float,
) -> list[LinearSegment]:
    """检查跨设施干员条件配对，为持有者提供效率加成

    B7 体系：干员 A 在某设施时，若干员 B 在另一设施则触发加成。
    """
    names = {op.name for op in operators}
    segments = []

    for holder_name, (target_name, target_facility, bonus_per, target_product, target_room) in _B_CROSS_ROOM_PAIR_TABLE.items():
        if holder_name not in names:
            continue
        if target_room is not None and room_type != target_room:
            continue
        if target_product is not None and product != target_product:
            continue

        if target_facility is None:
            # 任意设施：扫描所有设施
            target_names: set[str] = set()
            for ops in all_assignments.values():
                target_names.update(op.name for op in ops)
        else:
            target_ops = all_assignments.get(target_facility, [])
            target_names = {op.name for op in target_ops}

        if target_name in target_names:
            segments.append(LinearSegment(a=bonus_per, b=0.0, t_start=0.0, dt=T))

    return segments


# ─── B·全局阵营计数 ─────────────────────────────────────────────

# 全局阵营计数表: {持有者名: (字段名, 匹配值, 每人加成%, 产物, 设施, 上限, 是否除自身)}
_B_GLOBAL_FACTION_TABLE: dict[str, GlobalFactionEntry] = {
    "缪尔赛思": GlobalFactionEntry("group_id", "rhine", 3.0, None, "Power", 5, True),
    "杏仁": GlobalFactionEntry("group_id", "blacksteel", 2.0, "PureGold", "Mfg", 3, False),
    "娜斯提": GlobalFactionEntry("group_id", "rhine", 3.0, "PureGold", "Mfg", 5, False),
}


def synergy_global_faction(
    operators: list[Operator],
    room_type: str,
    product: str,
    all_operators: list[Operator],
    T: float,
) -> list[LinearSegment]:
    """B6: 统计全基建范围内特定阵营的干员数量，为持有者提供效率加成"""
    names = {op.name for op in operators}
    segments = []

    for holder_name, (field, value, bonus_per, target_product, target_room, cap, exclude_self) in _B_GLOBAL_FACTION_TABLE.items():
        if holder_name not in names:
            continue
        if room_type != target_room:
            continue
        if target_product is not None and product != target_product:
            continue

        count = sum(1 for op in all_operators if getattr(op, field, None) == value)
        if exclude_self:
            count = max(0, count - 1)
        count = min(count, cap)
        bonus = count * bonus_per
        if bonus > 0:
            segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))

    return segments
