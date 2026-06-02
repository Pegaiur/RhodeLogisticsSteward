"""A层·贸易站联动体系

含：订单压缩（孑）、鸿雪宣发（销路宣发+际崖居民）、
贸易配对（德克萨斯+拉普兰德、蕾缪安+能天使）、招商引资（琳琅诗怀雅）、
冠军风采（锏）、订单上限上下文（OrderLimitContext）。

全部 buff_id 到行为的映射通过表配置驱动，
逻辑层无 has_XXX 布尔守卫，无裸 buff_id 字符串匹配。
"""

from dataclasses import dataclass, field

from steward_core.models import LinearSegment, Operator, LayoutConfig
from steward_core.synergy.types import (
    OrderLimitEntry, TradePairEntry, OrderOverrideEntry,
    TradeShareEntry, TradeEffAmpEntry, TradeConditionalEffEntry,
)
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

_OBSERVE_BLACKLIST_BASE: tuple[str, ...] = (
    "trade_ord_law", "trade_ord_long",
)
"""孑订单压缩时排除的订单机制基础列表

合同法/投资会改变订单类型，其效率不计入 other_eff。
trade_ord_closure 等 override 类型通过 _ORDER_OVERRIDE_TABLE 动态追加。
"""


def _observe_blacklist() -> tuple[str, ...]:
    """返回完整的订单机制排除列表 = 基础列表 + override keys"""
    return _OBSERVE_BLACKLIST_BASE + tuple(_ORDER_OVERRIDE_TABLE.keys())

_ORDER_LIMIT_TABLE: dict[str, OrderLimitEntry] = {
    "trade_ord_limit&cost[000]":    OrderLimitEntry("谈判", 5),
    "trade_ord_limit&cost_P[000]":  OrderLimitEntry("醉翁之意·α", 2, requires="德克萨斯"),
    "trade_ord_limit&cost_P[001]":  OrderLimitEntry("醉翁之意·β", 4, requires="德克萨斯"),
    "trade_ord_limit&trade&lv[000]": OrderLimitEntry("多面逢源", 1, per_trade_level=True),
    "trade_ord_limit&trade&lv[001]": OrderLimitEntry("钱不我待", 1, per_trade_level=True),
    "trade_ord_spd&limit[000]":    OrderLimitEntry("订单管理·α", 2),
    "trade_ord_spd&limit[001]":    OrderLimitEntry("订单管理·β", 4),
    "trade_ord_spd&limit[010]":    OrderLimitEntry("供应管理", 1),
    "trade_ord_spd&limit[020]":    OrderLimitEntry("喀兰贸易·α", 2),
    "trade_ord_spd&limit[022]":    OrderLimitEntry("喀兰之主", 4),
    "trade_ord_spd&limit[036]":    OrderLimitEntry("半身人公会代表", 1),
    "trade_ord_limit&cost_P[020]": OrderLimitEntry("未偿还的债务", 2, requires="伺夜"),
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
holder 字段在检测时由 buff_id 驱动（非 name 匹配），仅保留用于文档可读性。
"""

_TRADE_TRIGGER_TABLE: dict[str, str] = {
    "trade_ord_spd&gold[100]": "gold_lines",
    "trade_ord_spd_variable[000]": "swires_limit",
    "trade_ord_spd_variable3[000]": "degenbrecher_limit",
}
"""单 buff 触发标识表

buff_id → 机制标签
- gold_lines: 鸿雪 销路宣发
- swires_limit: 琳琅诗怀雅 招商引资
- degenbrecher_limit: 锏 冠军风采
"""

_ORDER_OVERRIDE_TABLE: dict[str, OrderOverrideEntry] = {
    "trade_ord_closure": OrderOverrideEntry(
        prefix="trade_ord_closure",
        order_time_h=2.4, lmd_per_order=1200, gold_per_order=2,
        priority=1,
    ),
    "trade_ord_pepe": OrderOverrideEntry(
        prefix="trade_ord_pepe",
        order_time_h=4.5, lmd_per_order=1000, gold_per_order=0,
        no_efficiency=True, no_drone=True, priority=2,
    ),
}
"""订单覆盖表 — buff_id 前缀 → OrderOverrideEntry

priority 决定同房冲突时高优先级胜出。
"""


def get_active_override(operators: list[Operator]) -> OrderOverrideEntry | None:
    """返回房间内最高优先级的活跃订单 override"""
    best: OrderOverrideEntry | None = None
    for prefix, entry in _ORDER_OVERRIDE_TABLE.items():
        if any(sk.buff_id.startswith(prefix) for op in operators for sk in op.skills):
            if best is None or entry.priority > best.priority:
                best = entry
    return best

_TRADE_SHARE_TABLE: dict[str, TradeShareEntry] = {
    "trade_ord_spd&share[000]": TradeShareEntry(bonus_per_worker=15.0),
    "trade_ord_spd&share[001]": TradeShareEntry(bonus_per_worker=10.0),
    "trade_ord_spd&share[002]": TradeShareEntry(bonus_per_worker=20.0),
}
"""贸易站 per-operator 分享表 — 火哨代为说项、吉星勤俭经营

buff_id → TradeShareEntry
持有者自身不计入计数。
"""

_TRADE_EFF_AMPLIFIER_TABLE: dict[str, TradeEffAmpEntry] = {
    "trade_ord_spd_variable2[000]": TradeEffAmpEntry(cap=25.0),
    "trade_ord_spd_variable2[001]": TradeEffAmpEntry(cap=35.0),
}
"""贸易站效率→效率放大表 — 雪雉天道酬勤

buff_id → TradeEffAmpEntry
每 5% 房间总效率额外 +5%，上限由 cap 约束。
"""

_TRADE_CONDITIONAL_EFF_TABLE: dict[str, TradeConditionalEffEntry] = {
    "trade_ord_spd_ext[020]": TradeConditionalEffEntry(5.0, ("伺夜",), "base"),
    "trade_ord_spd_ext[021]": TradeConditionalEffEntry(10.0, ("伺夜",), "base"),
    "trade_ord_par&per[000]": TradeConditionalEffEntry(5.0, ("伊内丝",), "workspace"),
    "trade_ord_par&per[001]": TradeConditionalEffEntry(5.0, ("伊内丝", "W"), "workspace"),
}
"""贸易站条件型 per-operator 效率表 — 贝洛内家族经营、赫德雷白手起家

buff_id → TradeConditionalEffEntry
target_scope: "base"=基建任意位置 "workspace"=Control/Mfg/Trade
"""


def _collect_mechs(
    operators: list[Operator],
    table: dict[str, str],
) -> set[str]:
    """扫描 operators 的 Trade skills，返回命中的机制标识集合

    仅扫描 room_type=="Trade" 的技能，匹配 table 中的 buff_id key。
    """
    mechs: set[str] = set()
    for op in operators:
        for sk in op.active_skills_for("Trade"):
            mech = table.get(sk.buff_id)
            if mech:
                mechs.add(mech)
    return mechs


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

    jie_mechs = _collect_mechs(operators, _JIE_MECH_TABLE)
    if "compression" not in jie_mechs:
        return []

    if order_ctx is not None:
        order_limit = order_ctx.total
    else:
        names = {op.name for op in operators}
        other_eff = 0.0
        for op in operators:
            if any(s.buff_id.startswith(_observe_blacklist()) for s in op.skills if s.room_type == "Trade"):
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
    + 绮良订单流可视化(每N条赤金线额外+M条)

    赤金线 = Mfg PureGold 房间数 + min(杜林族干员数, 4) + 绮良追加。
    """
    if room_type != "Trade":
        return []

    if "gold_lines" not in _collect_mechs(operators, _TRADE_TRIGGER_TABLE):
        return []

    gold_lines = sum(1 for r in layout.rooms if r.room_type == "Mfg" and r.product == "PureGold")

    if durin_names:
        durin_count = len(durin_names)
        gold_lines += min(durin_count, 4)

    for op in operators:
        for sk in op.active_skills_for("Trade"):
            if sk.buff_id == "trade_ord_line_gold[000]":
                gold_lines += (gold_lines // 4) * 2
            elif sk.buff_id == "trade_ord_line_gold[010]":
                gold_lines += (gold_lines // 2) * 2

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

    jie_mechs = _collect_mechs(operators, _JIE_MECH_TABLE)
    if "compression" in jie_mechs:
        other_eff = 0.0
        for op in operators:
            if any(
                s.buff_id.startswith(_observe_blacklist())
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
        for sk in op.active_skills_for("Trade"):
            entry = _ORDER_LIMIT_TABLE.get(sk.buff_id)
            if entry is None:
                continue
            if entry.requires and entry.requires not in names:
                continue
            value = entry.value
            if entry.per_trade_level:
                value *= trade_level
            ctx.add(entry.source, value)

    if control_operators:
        from .control_linkages import _CONTROL_TRADE_LIMIT_TABLE
        ctrl_names = {op.name for op in control_operators}
        for ctrl_name, entry in _CONTROL_TRADE_LIMIT_TABLE.items():
            if ctrl_name in ctrl_names and entry.target_name in names:
                e2_count = sum(
                    1 for op in control_operators
                    if op.name == ctrl_name and op.elite_phase >= 2
                )
                bonus = entry.bonus_e2 if e2_count > 0 else entry.bonus_e0
                ctx.add(f"{ctrl_name}->{entry.target_name}", bonus)
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

    遍历 _TRADE_PAIR_TABLE，holder 侧通过 buff_id 检测，
    target 侧通过 name 集合检测。
    """
    if room_type != "Trade":
        return []
    names = {op.name for op in operators}
    segments: list[LinearSegment] = []

    for buff_id, entry in _TRADE_PAIR_TABLE.items():
        if entry.target not in names:
            continue
        if any(sk.buff_id == buff_id for op in operators for sk in op.skills if sk.room_type == "Trade"):
            segments.append(LinearSegment(a=entry.bonus, b=0.0, t_start=0.0, dt=T))

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
    if "swires_limit" not in _collect_mechs(operators, _TRADE_TRIGGER_TABLE):
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
    if "degenbrecher_limit" not in _collect_mechs(operators, _TRADE_TRIGGER_TABLE):
        return []
    bonus = min(int(order_ctx.total / 5) * 25, 100)
    return [LinearSegment(a=float(bonus), b=0.0, t_start=0.0, dt=T)] if bonus > 0 else []


def synergy_trade_share(
    operators: list[Operator],
    room_type: str,
    T: float,
) -> list[LinearSegment]:
    """贸易站 per-operator 分享效率：火哨代为说项、吉星勤俭经营

    遍历 _TRADE_SHARE_TABLE，持有者自身不计入计数。
    """
    if room_type != "Trade":
        return []
    bonus = 0.0
    for op in operators:
        for sk in op.active_skills_for("Trade"):
            entry = _TRADE_SHARE_TABLE.get(sk.buff_id)
            if entry is not None:
                bonus += (len(operators) - 1) * entry.bonus_per_worker
    return [LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T)] if bonus > 0 else []


def synergy_trade_efficiency_amplifier(
    operators: list[Operator],
    room_type: str,
    room_total_eff: float,
    T: float,
) -> list[LinearSegment]:
    """贸易站效率→效率放大器：雪雉天道酬勤

    room_total_eff 为房间当前总效率（百分值），
    每 step_size% 额外 bonus_per_step%，上限 cap%。
    """
    if room_type != "Trade":
        return []
    bonus = 0.0
    for op in operators:
        for sk in op.active_skills_for("Trade"):
            entry = _TRADE_EFF_AMPLIFIER_TABLE.get(sk.buff_id)
            if entry is not None:
                steps = int(room_total_eff / entry.step_size)
                local = min(steps * entry.bonus_per_step, entry.cap)
                bonus += local
    return [LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T)] if bonus > 0 else []


def synergy_trade_conditional_eff(
    operators: list[Operator],
    room_type: str,
    all_assignments: dict[str, list[Operator]],
    T: float,
) -> list[LinearSegment]:
    """贸易站条件型 per-operator 效率加成：贝洛内家族经营、赫德雷白手起家

    all_assignments: facility_type → operator_list
    target_scope 枚举:
      "base"    — 基建任意位置（遍历 all_assignments 全量）
      "workspace" — 工作设施 Control/Mfg/Trade
    """
    if room_type != "Trade":
        return []
    bonus = 0.0
    for op in operators:
        for sk in op.active_skills_for("Trade"):
            entry = _TRADE_CONDITIONAL_EFF_TABLE.get(sk.buff_id)
            if entry is None:
                continue
            for target in entry.target_names:
                if entry.target_scope == "base":
                    target_found = any(
                        any(o.name == target for o in ops)
                        for ops in all_assignments.values()
                    )
                else:
                    target_found = any(
                        any(o.name == target for o in all_assignments.get(fac, []))
                        for fac in ("Control", "Mfg", "Trade")
                    )
                if target_found:
                    bonus += entry.bonus_per
    return [LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T)] if bonus > 0 else []
