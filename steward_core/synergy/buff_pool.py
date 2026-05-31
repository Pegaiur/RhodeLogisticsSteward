"""B层·全局 buff 点数池与消费者"""

from dataclasses import dataclass, field

from steward_core.models import LinearSegment, Operator, LayoutConfig
from .types import BuffConsumerEntry
from .helpers import ROSEMARY_SUPPORT, _B_ROSEMARY, _B_EBENHOLZ


@dataclass
class BuffPool:
    """全局 buff 点数池

    新增字段时需同步更新 __add__、clone 方法的字段列表。
    """
    yanhuo: int = 0            # 人间烟火
    perception: int = 0        # 感知信息
    wushu_crystal: int = 0     # 巫术结晶
    thought_chains: int = 0    # 思维链环 (B3)
    silent_resonance: int = 0  # 无声共鸣 (B5) — 由塑心宿舍 + 黑键感知转化生成
    engineering_robots: int = 0  # 工程机器人 (B2)
    monster_cuisine: int = 0     # 魔物料理 (B4)

    def __add__(self, other: "BuffPool") -> "BuffPool":
        return BuffPool(
            yanhuo=self.yanhuo + other.yanhuo,
            perception=self.perception + other.perception,
            wushu_crystal=self.wushu_crystal + other.wushu_crystal,
            thought_chains=self.thought_chains + other.thought_chains,
            silent_resonance=self.silent_resonance + other.silent_resonance,
            engineering_robots=self.engineering_robots + other.engineering_robots,
            monster_cuisine=self.monster_cuisine + other.monster_cuisine,
        )

    def clone(self) -> "BuffPool":
        return BuffPool(
            yanhuo=self.yanhuo, perception=self.perception,
            wushu_crystal=self.wushu_crystal, thought_chains=self.thought_chains,
            silent_resonance=self.silent_resonance, engineering_robots=self.engineering_robots,
            monster_cuisine=self.monster_cuisine,
        )


def _derive_pool(pool: BuffPool) -> None:
    """原地更新派生字段：烟火→巫术结晶（//5），感知→思维链环（1:1）"""
    pool.wushu_crystal = pool.yanhuo // 5
    pool.thought_chains = pool.perception


def compute_buff_pool(
    control_operators: list[Operator],
    suich_count: int = 5,
    dorm_operators: list[Operator] | None = None,
    dorm_level: int = 5,
    mfg_operators: list[Operator] | None = None,
    trade_operators: list[Operator] | None = None,
    office_operators: list[Operator] | None = None,
    office_perception_base: int = 20,
    ling_mood_below_12: bool = False,
    xi_mood_below_12: bool | None = None,
    layout: LayoutConfig | None = None,
) -> BuffPool:
    """计算全局 buff 点数池

    所有生产源的干员通过 Operator 列表 + buff_id 扫描检测，
    不再使用 bool 代理参数。中枢干员暂保留名字硬编码（TODO: 统一到 buff_id）。
    """
    if dorm_operators is None:
        dorm_operators = []

    names = {op.name for op in control_operators}
    yanhuo = 0
    perception = 0
    monster_cuisine = 0

    # ── 段① 中枢源 ──────────────────────────────────────────────

    if "令" in names:
        if ling_mood_below_12:
            perception += 10
        else:
            yanhuo += 15

    if "重岳" in names:
        yanhuo += min(suich_count, 5) * 5

    if "夕" in names:
        if xi_mood_below_12 is not None:
            if not xi_mood_below_12:
                perception += 10
        else:
            perception += 10

    # ── 段② 宿舍/代理源（Mfg/Trade/Office → 感知 + 烟火）──

    for op in (mfg_operators or []):
        if _op_has_buff(op, "manu_prod_spd_bd_n1[000]"):
            perception += len(dorm_operators)

    for op in (trade_operators or []):
        if _op_has_buff(op, "trade_ord_spd_bd_n1[000]"):
            perception += len(dorm_operators)
        if _op_has_buff(op, "trade_ord_spd_bd_n2[000]"):
            yanhuo += len(dorm_operators)

    if _dorm_has_buff(dorm_operators, "dorm_rec_bd_n1_n2[000]"):
        perception += dorm_level

    if _dorm_has_buff(dorm_operators, "dorm_rec_bd_n1_n3[000]"):
        perception += dorm_level

    for op in (office_operators or []):
        if _op_has_buff(op, "hire_spd_bd_n1[000]"):
            perception += office_perception_base

    if _dorm_has_buff(dorm_operators, "dorm_rec_bd_dungeon[000]"):
        monster_cuisine += dorm_level

    eng_robots = compute_engineering_robots(layout) if layout is not None else 0

    # ── 段③ 无声共鸣级联（依赖段①② 完成的 perception 值）──

    silent_resonance = 0
    if any(_op_has_buff(op, "trade_ord_spd_bd_n1[000]") for op in (trade_operators or [])):
        silent_resonance += perception
    if dorm_operators:
        suxin_names = {op.name for op in dorm_operators}
        if "塑心" in suxin_names:
            silent_resonance += len(dorm_operators)

    pool = BuffPool(
        yanhuo=yanhuo, perception=perception,
        monster_cuisine=monster_cuisine,
        engineering_robots=eng_robots,
        silent_resonance=silent_resonance,
    )
    _derive_pool(pool)
    return pool


def _dorm_has_buff(dorm_operators: list[Operator], buff_id: str) -> bool:
    """检查宿舍干员列表中是否存在持有指定 buff_id 的干员"""
    for op in dorm_operators:
        for sk in op.skills:
            if sk.buff_id == buff_id:
                return True
    return False


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
