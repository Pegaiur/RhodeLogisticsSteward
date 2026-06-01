"""A层·贸易站联动体系

含：订单压缩（孑）、鸿雪宣发（销路宣发+际崖居民）、
恩怨（德克萨斯+拉普兰德配对）、招商引资（琳琅诗怀雅）、
冠军风采（锏）、订单上限上下文（OrderLimitContext）。

已建模技能（2026-06-01）：
- 孑 trade_ord_limit_count/diff: 订单压缩+效率放大
- 鸿雪 trade_ord_limit&trade&lv: 销路宣发（含际崖居民）
- 德克萨斯 trade_ord_spd&cost_P: 恩怨 +65%（配对拉普兰德）
- 琳琅诗怀雅 trade_ord_spd_variable: 招商引资（每订单上限 4%）
- 锏 trade_ord_spd_variable3: 冠军风采（每5订单上限 25%，上限 100%）
- 桃金娘/史都华德/暗索 trade_ord_limit&cost: 谈判（订单上限+5）
- 拉普兰德 trade_ord_limit&cost_P: 醉翁之意（订单上限+2/+4，配对德克萨斯）
- 瑰盐 trade_ord_limit&trade&lv: 多面逢源（订单上限+等级）

未建模技能：
- 赫德雷 trade_ord_par&per: per-operator 缩放（需跨房间扫描）
- 铎铃 trade_cost&bd2: 烟火联动心情减免（mood 系统）
- 火哨 trade_cost: 心情消耗减免（mood 系统）
- 佩佩 trade_ord_pepe: 独占订单（改变订单模型根基）
- 雪雉 trade_ord_spd_variable2: 高效率放大器（需后计算）
"""

from dataclasses import dataclass, field

from steward_core.models import LinearSegment, Operator, LayoutConfig
from .helpers import _DURIN_NAMES  # TODO: 际崖居民 durin_names 参数链待 evaluate_room 接入


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


_ORDER_LIMIT_TABLE: dict[str, tuple[str, int]] = {
    "trade_ord_limit&cost[000]":    ("谈判", 5),
    "trade_ord_limit&cost_P[000]":  ("醉翁之意·α", 2),
    "trade_ord_limit&cost_P[001]":  ("醉翁之意·β", 4),
    "trade_ord_limit&trade&lv[000]": ("多面逢源", 1),
    "trade_ord_limit&trade&lv[001]": ("钱不我待", 1),
}
"""订单上限贡献表

buff_id → (来源名称, 基础贡献值)
- 醉翁之意·α/β 需德克萨斯配对（compute 函数中检查条件）
- 多面逢源/钱不我待 值 × 贸易站等级（compute 函数中处理乘法）
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

    if order_ctx is not None:
        order_limit = order_ctx.total
    else:
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
        order_limit = max(1, 10 - int(other_eff) // 10)
        if "贝洛内" in names and "伺夜" in names:
            order_limit += 2
        if control_operators:
            ctrl_names = {op.name for op in control_operators}
            if "灵知" in ctrl_names:
                karlan_count = sum(1 for op in operators if op.group_id == "karlan")
                order_limit += karlan_count * 6

    ceiling = order_limit * 4.0

    if has_limit_diff:
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
        has_limit = any(
            sk.buff_id == "trade_ord_limit_count[000]"
            for op in operators if op.name == "孑"
            for sk in op.skills
        )
        if has_limit:
            _OBSERVE_BLACKLIST = ("trade_ord_law", "trade_ord_long", "trade_ord_closure")
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

    for op in operators:
        for sk in op.skills:
            if sk.room_type != "Trade":
                continue
            entry = _ORDER_LIMIT_TABLE.get(sk.buff_id)
            if entry is None:
                continue
            source, value = entry
            if source.startswith("醉翁之意") and "德克萨斯" not in names:
                continue
            if source in ("多面逢源", "钱不我待"):
                trade_level = max(
                    (r.level for r in layout.rooms if r.room_type == "Trade"),
                    default=3,
                )
                ctx.add(source, value * trade_level)
                continue
            ctx.add(source, value)

    if "贝洛内" in names and "伺夜" in names:
        ctx.add("贝洛内+伺夜", 2)

    if control_operators:
        ctrl_names = {op.name for op in control_operators}
        if "灵知" in ctrl_names:
            count = sum(1 for op in operators if op.group_id == "karlan")
            if count > 0:
                ctx.add("灵知·喀兰贸易", count * 6)

    return ctx


def synergy_texas_lappland(
    operators: list[Operator],
    room_type: str,
    T: float,
) -> list[LinearSegment]:
    """恩怨：德克萨斯与拉普兰德同房 Trade → +65% 效率

    德克萨斯持有 trade_ord_spd&cost_P[000]（恩怨），
    心情消耗 +0.3/h 由 mood 系统单独处理。
    """
    if room_type != "Trade":
        return []
    names = {op.name for op in operators}
    if "德克萨斯" not in names or "拉普兰德" not in names:
        return []
    return [LinearSegment(a=65.0, b=0.0, t_start=0.0, dt=T)]


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
