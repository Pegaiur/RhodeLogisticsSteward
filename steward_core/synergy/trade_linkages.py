"""A层·贸易站联动体系

含：订单压缩（孑）、鸿雪宣发（销路宣发+际崖居民）。

未建模技能（2026-06-01 扫描统计，详见 docs/inbox.md）：

=== 效率有但特殊加成未建模 ===
- 赫德雷 trade_ord_par&per: per-operator 缩放 (+25~30% / 每名特定阵营)
- 琳琅诗怀雅 trade_ord_spd_variable: 每订单上限 +4% 效率
- 锏 trade_ord_spd_variable3: 同上，可变系数
- 瑰盐 trade_ord_limit&trade&lv: 订单上限 + 设施等级联动 + 30% eff

=== 0 效率仅特殊效果 ===
- 铎铃 trade_cost&bd2: 烟火联动心情减免
- 火哨 trade_cost: 心情消耗减免 + share
- 史都华德/暗索/桃金娘 trade_ord_limit&cost: 订单上限+心情配对
- 拉普兰德 trade_ord_limit&cost_P: 订单上限+德克萨斯配对
- 德克萨斯 trade_ord_limit&cost_P + trade_ord_spd&cost_P: 配对+心情
- 佩佩 trade_ord_limit&trade&lv + trade_ord_pepe: 订单上限+等级
- 雪雉 trade_ord_spd_variable2: 可变效率(0基础)

=== 候选池质量问题（非建模缺口） ===
- 塑心: 无 TRADING buff，仅 Dormitory 技能 → has_skill_for 误判
- 芳汀: 无 TRADING buff → has_skill_for 误判
"""

from steward_core.models import LinearSegment, Operator, LayoutConfig
from .helpers import _ORDER_ANCHOR_PREFIXES, _DURIN_NAMES


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
            karlan_count = sum(
                1 for op in operators
                if op.group_id == "karlan"
            )
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
