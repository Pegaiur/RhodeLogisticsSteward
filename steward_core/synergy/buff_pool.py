"""B层·全局 buff 点数池与消费者"""

from dataclasses import dataclass, field, fields, replace

from steward_core.models import LinearSegment, Operator, LayoutConfig
from .types import BuffConsumerEntry, BuffProducerEffect


@dataclass
class BuffPool:
    """全局 buff 点数池

    新增 int 字段后 __add__ 自动遍历 dataclasses.fields() 求和（无需手动更新）。
    若新增非数值字段，需在 __add__ 中排除。
    """
    yanhuo: int = 0            # 人间烟火 (B1)
    perception: int = 0        # 感知信息 (B1)
    wushu_crystal: int = 0     # 巫术结晶 (B1)
    thought_chains: int = 0    # 思维链环 (B3)
    silent_resonance: int = 0  # 无声共鸣 (B5) — 由塑心宿舍 + 黑键感知转化生成
    engineering_robots: int = 0  # 工程机器人 (B2)
    monster_cuisine: int = 0     # 魔物料理 (B4)

    def __add__(self, other: "BuffPool") -> "BuffPool":
        return BuffPool(**{
            f.name: getattr(self, f.name) + getattr(other, f.name)
            for f in fields(self)
        })

    def __sub__(self, other: "BuffPool") -> "BuffPool":
        """逐字段相减，负值归零（用于外溢diff：只关心增量）"""
        return BuffPool(**{
            f.name: max(getattr(self, f.name) - getattr(other, f.name), 0)
            for f in fields(self)
        })

    def clone(self) -> "BuffPool":
        return replace(self)

    def derive(self) -> None:
        """原地更新派生字段：烟火→巫术结晶（//5），感知→思维链环（1:1）"""
        self.wushu_crystal = self.yanhuo // 5
        self.thought_chains = self.perception

    def apply_delta(self, delta: "BuffPool") -> "BuffPool":
        """返回 self + delta 的新池（含派生字段更新）

        封装 clone → __add__ → derive 三步，消除调用侧重复代码。
        """
        result = self.clone() + delta
        result.derive()
        return result


def _derive_pool(pool: BuffPool) -> None:
    """原地更新派生字段，委托给 BuffPool.derive()"""
    pool.derive()


def compute_buff_pool(
    control_operators: list[Operator],
    dorm_operators: list[Operator] | None = None,
    dorm_level: int = 5,
    mfg_operators: list[Operator] | None = None,
    trade_operators: list[Operator] | None = None,
    office_operators: list[Operator] | None = None,
    office_perception_base: int = 20,
    office_yanhuo_base: int = 20,
    office_silent_base: int = 30,
    ling_mood_below_12: bool = False,
    xi_mood_below_12: bool | None = None,
    layout: LayoutConfig | None = None,
) -> BuffPool:
    """计算全局 buff 点数池

    所有生产源通过 _OPERATOR_BUFF_PRODUCERS 表驱动检测。
    """
    if dorm_operators is None:
        dorm_operators = []

    yanhuo = 0
    perception = 0
    monster_cuisine = 0
    silent_resonance = 0

    dorm_count = len(dorm_operators)
    # 岁阵营计数：从 control_operators 实际统计（替代原先硬编码 suich_count=5）
    sui_count = sum(1 for op in control_operators if op.has_group("sui"))

    _office_bases = {
        "perception": office_perception_base,
        "yanhuo": office_yanhuo_base,
        "silent_resonance": office_silent_base,
    }

    exclusive_triggered: set[str] = set()

    # ── 段①② 首遍：非 cascade 条目 ──
    for e in _OPERATOR_BUFF_PRODUCERS:
        if e.cascade:
            continue
        if e.exclusive_group and e.exclusive_group in exclusive_triggered:
            continue
        if not _condition_met(e, ling_mood_below_12, xi_mood_below_12):
            continue

        ops = _facility_ops(e.facility, control_operators, mfg_operators,
                            trade_operators, dorm_operators, office_operators)
        if not any(_op_has_buff(op, e.buff_id) for op in ops):
            continue

        office_base = _office_bases.get(e.dimension, 0)
        amount = _eval_producer_amount(e, dorm_count, dorm_level, sui_count,
                                       office_base, perception)
        if amount <= 0:
            continue

        if e.dimension == "yanhuo":
            yanhuo += amount
        elif e.dimension == "perception":
            perception += amount
        elif e.dimension == "monster_cuisine":
            monster_cuisine += amount

        if e.exclusive_group:
            exclusive_triggered.add(e.exclusive_group)

    eng_robots = compute_engineering_robots(layout) if layout is not None else 0

    # ── 段③ 次遍：cascade 条目（依赖首遍完成的 perception 值）──
    for e in _OPERATOR_BUFF_PRODUCERS:
        if not e.cascade:
            continue

        ops = _facility_ops(e.facility, control_operators, mfg_operators,
                            trade_operators, dorm_operators, office_operators)
        if not any(_op_has_buff(op, e.buff_id) for op in ops):
            continue

        if e.amount_source == "perception_cascade":
            silent_resonance += perception
        else:
            office_base = _office_bases.get(e.dimension, 0)
            amount = _eval_producer_amount(e, dorm_count, dorm_level, sui_count,
                                           office_base, perception)
            silent_resonance += amount

    pool = BuffPool(
        yanhuo=yanhuo, perception=perception,
        monster_cuisine=monster_cuisine,
        engineering_robots=eng_robots,
        silent_resonance=silent_resonance,
    )
    _derive_pool(pool)
    return pool


def compute_buff_pool_delta(
    facility: str,
    operators: list[Operator],
    dorm_count: int,
    *,
    base_perception: int = 0,
) -> BuffPool:
    """计算可变设施干员对 buff_pool 的增量贡献

    遍历 _OPERATOR_BUFF_PRODUCERS 表，仅处理 facility 对应的条目（含 cascade）。
    返回只含增量字段的 BuffPool（其他字段为 0），可与 base_pool 做 __add__ 后 derive()。

    正确性约束：base_pool 必须以相同的 dorm/office/control 干员但 facility 对应的
    operators 为空列表计算。级联条目（perception_cascade）依赖 base_perception +
    本轮 delta.perception。

    Args:
        facility: 设施类型，如 "Trade" / "Mfg"
        operators: 该设施当前 combo 的干员列表（可为空）
        dorm_count: 宿舍干员数
        base_perception: 底池的感知信息值（用于级联项 perception_cascade 的正确计算）
    """
    delta = BuffPool()

    # ── 非 cascade 条目 ──
    for e in _OPERATOR_BUFF_PRODUCERS:
        if e.cascade or e.facility != facility:
            continue
        if not any(_op_has_buff(op, e.buff_id) for op in operators):
            continue
        amount = _eval_producer_amount(e, dorm_count, 0, 0, 0, 0)
        if amount <= 0:
            continue
        if e.dimension == "yanhuo":
            delta.yanhuo += amount
        elif e.dimension == "perception":
            delta.perception += amount
        elif e.dimension == "monster_cuisine":
            delta.monster_cuisine += amount

    # ── cascade 条目（依赖本轮 delta.perception + base_perception）──
    for e in _OPERATOR_BUFF_PRODUCERS:
        if not e.cascade or e.facility != facility:
            continue
        if not any(_op_has_buff(op, e.buff_id) for op in operators):
            continue
        if e.amount_source == "perception_cascade":
            delta.silent_resonance += base_perception + delta.perception
        else:
            amount = _eval_producer_amount(e, dorm_count, 0, 0, 0, 0)
            delta.silent_resonance += amount

    return delta


def _op_has_buff(op: Operator, buff_id: str) -> bool:
    """检查单个干员是否持有指定 buff_id"""
    return any(sk.buff_id == buff_id for sk in op.skills)


def compute_engineering_robots(layout: LayoutConfig) -> int:
    """计算工程机器人总数 = Σ(每间设施 × 等级)，上限 64

    243 布局 13 间工作设施 Lv3(39) + 中枢 Lv5(5) + 4 间宿舍 Lv5(20) = 64 → 触及上限。
    """
    return min(sum(r.level for r in layout.rooms), 64)


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

_OPERATOR_BUFF_PRODUCERS: list[BuffProducerEffect] = [
    # ── 中枢源（段①）──
    BuffProducerEffect("control_costToBD[000]", "Control", "yanhuo",
                       "fixed", amount=15,
                       condition="mood_gt_12", exclusive_group="ling_gate"),
    BuffProducerEffect("control_costToBD[000]", "Control", "perception",
                       "fixed", amount=10,
                       condition="mood_le_12", exclusive_group="ling_gate"),
    BuffProducerEffect("control_mp_cost&bd_up[000]", "Control", "yanhuo",
                       "suich_scaled", amount_scale=5, amount_cap=5),
    BuffProducerEffect("control_mp_cost&bd1[000]", "Control", "yanhuo",
                       "fixed", amount=15, condition="xi_mood_lt_12"),
    BuffProducerEffect("control_mp_cost&bd2[000]", "Control", "perception",
                       "fixed", amount=10, condition="xi_mood_ge_12_or_default"),
    # ── 代理源（段②）──
    BuffProducerEffect("manu_prod_spd_bd_n1[000]", "Mfg", "perception", "dorm_count"),
    BuffProducerEffect("trade_ord_spd_bd_n1[000]", "Trade", "perception", "dorm_count"),
    BuffProducerEffect("trade_ord_spd_bd_n2[000]", "Trade", "yanhuo", "dorm_count"),
    BuffProducerEffect("dorm_rec_bd_n1_n2[000]", "Dormitory", "perception", "dorm_level"),
    BuffProducerEffect("dorm_rec_bd_n1_n3[000]", "Dormitory", "perception", "dorm_level"),
    BuffProducerEffect("hire_spd_bd_n1[000]", "Office", "perception", "office_base"),
    BuffProducerEffect("hire_spd_bd_n1_n1[200]", "Office", "yanhuo", "office_base"),
    BuffProducerEffect("dorm_rec_bd_dungeon[000]", "Dormitory", "monster_cuisine", "dorm_level"),
    # ── 无声共鸣源（段③，cascade=True）──
    BuffProducerEffect("dorm_bd_num[000]", "Dormitory", "silent_resonance", "dorm_count",
                       cascade=True),
    BuffProducerEffect("hire_spd_bd_n1_n1[300]", "Office", "silent_resonance", "office_base",
                       cascade=True),
    # 黑键感知→无声级联
    BuffProducerEffect("trade_ord_spd_bd_n1[000]", "Trade", "silent_resonance", "perception_cascade",
                       cascade=True),
]
"""BuffPool 生产侧能力表 — 与消费侧 _B_BUFF_CONSUMER_TABLE 对等"""


def _eval_producer_amount(
    e: BuffProducerEffect,
    dorm_count: int,
    dorm_level: int,
    sui_count: int,
    office_base: int,
    perception: int,
) -> int:
    """根据 amount_source 计算生产量"""
    if e.amount_source == "fixed":
        return e.amount
    if e.amount_source == "dorm_count":
        val = int(dorm_count * e.amount_scale)
        return min(val, e.amount_cap) if e.amount_cap > 0 else val
    if e.amount_source == "dorm_level":
        val = int(dorm_level * e.amount_scale)
        return min(val, e.amount_cap) if e.amount_cap > 0 else val
    if e.amount_source == "suich_scaled":
        val = int(min(sui_count, e.amount_cap) * e.amount_scale)
        return val
    if e.amount_source == "office_base":
        return office_base
    if e.amount_source == "perception_cascade":
        return perception
    return 0


def _condition_met(e: BuffProducerEffect, ling_mood_below_12: bool,
                   xi_mood_below_12: bool | None) -> bool:
    """检查条件是否满足"""
    if e.condition is None:
        return True
    if e.condition == "mood_gt_12":
        return not ling_mood_below_12
    if e.condition == "mood_le_12":
        return ling_mood_below_12
    if e.condition == "xi_mood_lt_12":
        return xi_mood_below_12 is not None and xi_mood_below_12
    if e.condition == "xi_mood_ge_12_or_default":
        return xi_mood_below_12 is None or not xi_mood_below_12
    return False


def _facility_ops(facility: str, control_operators, mfg_operators,
                  trade_operators, dorm_operators, office_operators) -> list[Operator]:
    """根据设施类型返回对应的 Operator 列表"""
    mapping = {
        "Control": control_operators,
        "Mfg": mfg_operators or [],
        "Trade": trade_operators or [],
        "Dormitory": dorm_operators,
        "Office": office_operators or [],
    }
    return mapping.get(facility, [])


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
        entry = _B_BUFF_CONSUMER_TABLE[name]
        target_room = entry.target_room
        pool_key = entry.pool_key
        per_unit = entry.per_unit
        bonus_per = entry.bonus_per
        if room_type != target_room:
            continue
        if bonus_per <= 0:
            continue

        pool_value = getattr(buff_pool, pool_key, 0)
        if pool_value <= 0:
            continue

        units = pool_value // per_unit
        if units > 0:
            bonus = units * bonus_per
            segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))

    return segments
