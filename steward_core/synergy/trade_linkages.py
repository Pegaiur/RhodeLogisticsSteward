"""A层·贸易站联动体系

含：订单压缩（孑）、鸿雪宣发（销路宣发+际崖居民）、
贸易配对（德克萨斯+拉普兰德、蕾缪安+能天使）、招商引资（琳琅诗怀雅）、
冠军风采（锏）、订单上限上下文（OrderLimitContext）。

全部 buff_id 到行为的映射通过表配置驱动，
逻辑层无 has_XXX 布尔守卫，无裸 buff_id 字符串匹配。
"""

from dataclasses import dataclass, field

from steward_core.models import LinearSegment, Operator, LayoutConfig
from steward_core.synergy.types import OrderLimitEntry, TradePairEntry
from .helpers import _DURIN_NAMES  # TODO: 际崖居民 durin_names 参数链待 evaluate_room 接入

# ─── 模块级常量 ─────────────────────────────────────────────────

@dataclass
class OrderLimitContext:
    """贸易站订单上限上下文，后续关联爆仓计算

    base 为游戏基础订单上限（10），contributions 为各技能贡献的实增量。
    total 属性返回 base + sum(contributions)。
    """
    base: int = 10
    contributions: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return self.base + sum(self.contributions.values())

    def add(self, source: str, delta: int) -> None:
        if delta != 0:
            self.contributions[source] = self.contributions.get(source, 0) + delta

_JIE_MECH_TABLE: dict[str, str] = {
    "trade_ord_limit_count[000]": "compression",
    "trade_ord_limit_diff[000]": "constant",
}
"""孑技能 → 机制标识

compression: 订单压缩（市井之道）
constant:    恒定 ceiling（摊贩经济，精2）
缺失 constant 则走 ramp 爬升路径（精1）
"""

_OBSERVE_BLACKLIST: tuple[str, ...] = (
    "trade_ord_law", "trade_ord_long", "trade_ord_closure",
)
"""孑订单压缩时排除的效率来源

合同法/投资/特别订单会改变订单类型机制，
其效率不计入 other_eff，否则干扰压缩计算。
仅在孑订单压缩上下文中使用，与 slot/trade.py 的
_ORDER_MECHANISM_PREFIXES 用途不同。
"""

_ORDER_LIMIT_TABLE: dict[str, OrderLimitEntry] = {
    "trade_ord_limit&cost[000]":    OrderLimitEntry("谈判", 5),
    "trade_ord_limit&cost_P[000]":  OrderLimitEntry("醉翁之意·α", 2, requires="德克萨斯"),
    "trade_ord_limit&cost_P[001]":  OrderLimitEntry("醉翁之意·β", 4, requires="德克萨斯"),
    "trade_ord_limit&trade&lv[000]": OrderLimitEntry("多面逢源", 1, per_trade_level=True),
    "trade_ord_limit&trade&lv[001]": OrderLimitEntry("钱不我待", 1, per_trade_level=True),
}
"""订单上限贡献表

buff_id → OrderLimitEntry
- requires: None=无条件，干员名=需此干员在场
- per_trade_level: value 是否需乘以贸易站等级
"""

_TRADE_PAIR_TABLE: dict[str, TradePairEntry] = {
    "trade_ord_spd&cost_P[000]": TradePairEntry(
        holder="德克萨斯", target="拉普兰德", bonus=65,
        buff_id="trade_ord_spd&cost_P[000]",
    ),
    "trade_ord_spd&multiPar[100]": TradePairEntry(
        holder="蕾缪安", target="能天使", bonus=25,
        buff_id="trade_ord_spd&multiPar[100]",
    ),
}
"""贸易站配对表

buff_id → TradePairEntry
holder 持有此 buff，target 在同房 Trade 时触发 bonus% 效率加成。
"""


def synergy_jie_order(
    operators: list[Operator],
    room_type: str,
    control_operators: list[Operator],
    T: float,
    order_ctx: OrderLimitContext | None = None,
) -> list[LinearSegment]:
    """孑市井之道/摊贩经济：订单上限压缩+每订单效率放大

    精2（市井之道+摊贩经济）: 效率恒定 = 压缩后上限 × 4%
    精1（仅市井之道）: ramp近似，订单随时间爬升
    灵知在中枢时：每名谢拉格贸易站干员 → 订单上限+6
    贝洛内+伺夜同房时：订单上限+2
    """
    if room_type != "Trade":
        return []

    names = {op.name for op in operators}
    if "孑" not in names:
        return []

    jie_mechs: set[str] = set()
    for op in operators:
        if op.name != "孑":
            continue
        for sk in op.skills:
            mech = _JIE_MECH_TABLE.get(sk.buff_id)
            if mech:
                jie_mechs.add(mech)

    if "compression" not in jie_mechs:
        return []

    if order_ctx is not None:
        order_limit = order_ctx.total
    else:
        other_eff = 0.0
        for op in operators:
            if op.name == "孑":
                continue
            if any(s.buff_id.startswith(_OBSERVE_BLACKLIST) for s in op.skills if s.room_type == "Trade"):
                continue
            eff = op.best_efficiency(room_type, "Money")
            if eff > 0:
                other_eff += eff
        order_limit = max(1, 10 - int(other_eff) // 10)
        if "贝洛内" in names and "伺夜" in names:
            order_limit += 2
        if control_operators:
            ctrl_names = {op.name for op in control_operators}
            if "灵知" in ctrl_names:
                karlan_count = sum(1 for op in operators if op.group_id == "karlan")
                order_limit += karlan_count * 6

    ceiling = order_limit * 4.0

    if "constant" in jie_mechs:
        return [LinearSegment(a=ceiling, b=0.0, t_start=0.0, dt=T)]

    ramp = ceiling / 3.0
    if T <= 3.0:
        return [LinearSegment(a=0.0, b=ramp, t_start=0.0, dt=T)]
    return [
        LinearSegment(a=0.0, b=ramp, t_start=0.0, dt=3.0),
        LinearSegment(a=ceiling, b=0.0, t_start=3.0, dt=T - 3.0),
    ]


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


def compute_trade_order_limit(
    operators: list[Operator],
    layout: LayoutConfig,
    control_operators: list[Operator],
) -> OrderLimitContext:
    """计算贸易站房间的订单上限，供后续爆仓计算及各 synergy 消费

    订单上限 = 基础10 + 表驱动贡献 + 孑压缩 + 贝洛内+伺夜 + 灵知中枢。
    孑压缩使用 raw best_efficiency（非 synergy 叠加后效率）近似，
    与 synergy_jie_order 回退路径口径一致。
    """
    ctx = OrderLimitContext()
    names = {op.name for op in operators}

    if "孑" in names:
        jie_has_compression = any(
            _JIE_MECH_TABLE.get(sk.buff_id) == "compression"
            for op in operators if op.name == "孑"
            for sk in op.skills
        )
        if jie_has_compression:
            other_eff = 0.0
            for op in operators:
                if op.name == "孑":
                    continue
                if any(
                    s.buff_id.startswith(_OBSERVE_BLACKLIST)
                    for s in op.skills if s.room_type == "Trade"
                ):
                    continue
                eff = op.best_efficiency("Trade", "Money")
                if eff > 0:
                    other_eff += eff
            compressed = max(1, 10 - int(other_eff) // 10)
            ctx.add("孑·订单压缩", compressed - 10)

    trade_level = max(
        (r.level for r in layout.rooms if r.room_type == "Trade"),
        default=3,
    )

    for op in operators:
        for sk in op.skills:
            if sk.room_type != "Trade":
                continue
            entry = _ORDER_LIMIT_TABLE.get(sk.buff_id)
            if entry is None:
                continue
            if entry.requires and entry.requires not in names:
                continue
            value = entry.value
            if entry.per_trade_level:
                value *= trade_level
            ctx.add(entry.source, value)

    if "贝洛内" in names and "伺夜" in names:
        ctx.add("贝洛内+伺夜", 2)

    if control_operators:
        ctrl_names = {op.name for op in control_operators}
        if "灵知" in ctrl_names:
            count = sum(1 for op in operators if op.group_id == "karlan")
            if count > 0:
                ctx.add("灵知·喀兰贸易", count * 6)

    return ctx


def synergy_trade_pair(
    operators: list[Operator],
    room_type: str,
    T: float,
) -> list[LinearSegment]:
    """贸易配对表驱动联动

    遍历 _TRADE_PAIR_TABLE，检测 holder 与 target 是否同房，
    且 holder 持有对应 buff_id 技能时，返回加成效率段。
    """
    if room_type != "Trade":
        return []
    names = {op.name for op in operators}
    segments: list[LinearSegment] = []

    for buff_id, entry in _TRADE_PAIR_TABLE.items():
        if entry.holder not in names or entry.target not in names:
            continue
        for op in operators:
            if op.name != entry.holder:
                continue
            if any(sk.buff_id == buff_id for sk in op.skills):
                segments.append(LinearSegment(a=entry.bonus, b=0.0, t_start=0.0, dt=T))
                break

    return segments


def synergy_swires_order_limit(
    operators: list[Operator],
    room_type: str,
    order_ctx: OrderLimitContext | None,
    T: float,
) -> list[LinearSegment]:
    """招商引资：琳琅诗怀雅 每订单上限 +4% 效率

    消费 OrderLimitContext.total，无效率上限。
    """
    if room_type != "Trade" or order_ctx is None:
        return []
    names = {op.name for op in operators}
    if "琳琅诗怀雅" not in names:
        return []
    bonus = order_ctx.total * 4.0
    return [LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T)] if bonus > 0 else []


def synergy_degenbrecher_order_limit(
    operators: list[Operator],
    room_type: str,
    order_ctx: OrderLimitContext | None,
    T: float,
) -> list[LinearSegment]:
    """冠军风采：锏 每5订单上限 +25% 效率，最高 100%

    消费 OrderLimitContext.total，floor(total/5) × 25，上限 100%。
    """
    if room_type != "Trade" or order_ctx is None:
        return []
    names = {op.name for op in operators}
    if "锏" not in names:
        return []
    bonus = min(int(order_ctx.total / 5) * 25, 100)
    return [LinearSegment(a=float(bonus), b=0.0, t_start=0.0, dt=T)] if bonus > 0 else []
