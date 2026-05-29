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
    has_rosmontis_in_mfg: bool = False,
    has_ebnhlz_in_trade: bool = False,
    ling_mood_below_12: bool = False,
    xi_mood_below_12: bool | None = None,
    layout: LayoutConfig | None = None,
    perception_from_office: int = 0,
    has_wuyou_in_trade: bool = False,
) -> BuffPool:
    """计算全局 buff 点数池（Phase 1 预计算）

    中枢源：
    - 令(mood>12): +15 烟火；令(mood≤12): +10 感知信息
    - 重岳: 每个外部岁干员 +5 烟火（默认 5 名）
    - 夕(mood>=12): +10 感知信息（xi_mood_below_12=None 时无条件+10，向后兼容）

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

    if has_rosmontis_in_mfg and dorm_operators:
        perception += len(dorm_operators)

    if has_ebnhlz_in_trade and dorm_operators:
        perception += len(dorm_operators)

    if _dorm_has_buff(dorm_operators, "dorm_rec_bd_n1_n2[000]"):
        perception += dorm_level

    if _dorm_has_buff(dorm_operators, "dorm_rec_bd_n1_n3[000]"):
        perception += dorm_level

    if has_wuyou_in_trade and dorm_operators:
        yanhuo += len(dorm_operators)

    perception += perception_from_office

    if _dorm_has_buff(dorm_operators, "dorm_rec_bd_dungeon[000]"):
        monster_cuisine += dorm_level

    eng_robots = compute_engineering_robots(layout) if layout is not None else 0

    silent_resonance = 0
    if has_ebnhlz_in_trade:
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
