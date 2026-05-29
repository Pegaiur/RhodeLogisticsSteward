"""产出计算模块

基于 PRTS Wiki 公式计算各设施的精确日产出，含无人机加速：
  https://prts.wiki/w/罗德岛基建/制造站
  https://prts.wiki/w/罗德岛基建/贸易站
  https://prts.wiki/w/罗德岛基建/发电站

全部假设设施等级为 Lv3。
"""

from dataclasses import dataclass, field
from typing import Optional

from steward_core.models import Operator, ShiftPlan, LayoutConfig, RoomAssignment
from steward_core.synergy import (
    GlobalBonus, compute_control_global_bonus,
    compute_effective_power_count,
    control_per_operator_bonus,
)
from steward_core.constants import FIXED_CONTROL, BASE_POWER_COUNT
from steward_core.evaluate import evaluate_room

# ─── 制造站 Lv3 基础参数 ────────────────────────────────────────
# 作战记录：基础 1个/3h → 0.333 个/h，每中级经验书=1000经验
_RECORD_BASE_PER_HOUR = 1.0 / 3.0
_RECORD_EXP_PER_UNIT = 1000.0
# 赤金：基础 1个/1.2h → 0.833 个/h，每赤金=500龙门币
_GOLD_BASE_PER_HOUR = 1.0 / 1.2
_GOLD_LMD_PER_UNIT = 500.0

# ─── 贸易站 Lv3 基础参数（龙门商法） ────────────────────────────
# 订单概率与参数
#  2赤金/1000LMD: 30%, 2:24:00 = 144min
#  3赤金/1500LMD: 50%, 3:30:00 = 210min
#  4赤金/2000LMD: 20%, 4:36:00 = 276min
_TRADE_AVG_GOLD_PER_ORDER = 2.9
_TRADE_AVG_LMD_PER_ORDER = 1450.0
_TRADE_AVG_TIME_HOURS = (144 * 0.3 + 210 * 0.5 + 276 * 0.2) / 60.0  # 3.39h

_ORDER_TIME_2G = 144.0 / 60.0   # 2.4h
_ORDER_TIME_3G = 210.0 / 60.0   # 3.5h
_ORDER_TIME_4G = 276.0 / 60.0   # 4.6h

# ─── 发电站 / 无人机 基础参数 ──────────────────────────────────
# 基础恢复：6 min/架 → 240 架/天
_DRONE_BASE_PER_DAY = 240.0
# 加速效率：制造站每架 3 min，贸易站每架 1.5 min
_DRONE_MINUTES_MFG = 3.0
_DRONE_MINUTES_TRADE = 1.5
# 注: 游戏内贸易站加速效果为制造站的 1/2，PRTS Wiki 的 3 分钟指基础耗时非实际加速量

_LAYOUT_243 = LayoutConfig.layout_243()

# ─── 贸易站订单机制（A7 层）─ 文档倍数法 ────────────────────────
# 文档基准：Lv3 贸易站 100% 效率 24h
_TRADE_BASE_LMD_PER_DAY = 10265.0
_TRADE_BASE_GOLD_PER_DAY = 24.0 * _TRADE_AVG_GOLD_PER_ORDER / _TRADE_AVG_TIME_HOURS  # ≈ 20.53


def _extract_tailor_level(ops: list[Operator]) -> int:
    """从裁缝/手工艺品系列 buff_id 提取等级

    裁缝·α (trade_ord_wt&cost[x0x]): 小幅提升4-gold概率
    裁缝·β (trade_ord_wt&cost[x1x]): 提升4-gold概率
    手工艺品·α (trade_ord_wt&cost[x0x]): 小幅提升（同α）
    手工艺品·β (trade_ord_wt&cost[x1x]): 提升（同β）

    buff_id 格式为 trade_ord_wt&cost[ABC]，B=0表示α级，B=1表示β级。

    Returns:
        0: 无裁缝
        1: 仅α（一个或多个）
        2: 仅β（一个或多个）
        3: α+β 叠加
    """
    has_alpha = False
    has_beta = False
    for op in ops:
        for s in op.skills:
            bid = s.buff_id
            if not bid.startswith("trade_ord_wt&cost"):
                continue
            lb = bid.rfind("[")
            if lb < 0 or lb + 3 >= len(bid):
                continue
            tier = bid[lb + 2]  # [ABC] 第二位
            if tier == "1":
                has_beta = True
            elif tier == "0":
                has_alpha = True
    if has_beta and has_alpha:
        return 3
    if has_beta:
        return 2
    if has_alpha:
        return 1
    return 0


# ─── 裁缝时变P4参数 ────────────────────────────────────────────
# 裁缝技能机制：权重0-3h线性爬升，3h后饱和。4赤金订单触发权重清零，
# 稳态下P4呈爬升→震荡模式。以下取班次时间的加权平均等效P4。
# 数据来源：裁缝时变.md 实验数据拟合

_TAILOR_STEADY_P4 = {
    0: 0.20,   # 无裁缝 = 基准概率
    1: 0.53,   # 裁缝α：3h+ 稳态P4（裁缝时变.md 实验数据均值，单α爬升基线0.20）
    2: 0.85,   # 裁缝β：3h+ 稳态P4（龙舌兰相关.md 确认值85%，裁缝时变.md 实验均值83%）
    3: 0.88,   # α+β叠加：裁缝时变.md 6h单点88.1%（N=134），稳态天花板
}
_TAILOR_P4_FLOOR = {
    0: 0.20,
    1: 0.20,   # α从基线0.20开始爬升
    2: 0.30,   # β有地板加成，起点0.30
    3: 0.30,   # α+β：β地板主导
}
_RAMP_HOURS = 3.0  # 裁缝权重爬升上限（小时）


def _effective_tailor_p4(hours: float, tailor_level: int) -> float:
    """裁缝技能的等效4-gold概率（班次时间平均）

    0-3h线性爬升，3h后饱和。取爬升段（梯形面积）+ 稳态段（矩形面积）
    的加权平均，等价于匀化后的班次期望值。

    Args:
        hours: 班次持续时间（小时）
        tailor_level: _extract_tailor_level 返回值 (0/1/2/3)
    """
    p4_floor = _TAILOR_P4_FLOOR.get(tailor_level, 0.20)
    p4_max = _TAILOR_STEADY_P4.get(tailor_level, 0.20)

    if p4_max <= p4_floor:
        return p4_floor

    if hours <= _RAMP_HOURS:
        return p4_floor + (p4_max - p4_floor) * hours / (2.0 * _RAMP_HOURS)

    ramp_area = (p4_floor + p4_max) / 2.0 * _RAMP_HOURS
    steady_area = p4_max * (hours - _RAMP_HOURS)
    return (ramp_area + steady_area) / hours


def _weighted_avg_order_time(p2: float, p3: float, p4: float) -> float:
    """根据实际P2/P3/P4分布计算加权平均订单耗时（小时）"""
    return _ORDER_TIME_2G * p2 + _ORDER_TIME_3G * p3 + _ORDER_TIME_4G * p4


def _get_trade_order_multiplier(ops: list[Operator], hours: float = 24.0) -> tuple[float, float, float]:
    """贸易站订单机制倍数查询

    检测干员组合中的特殊订单机制，返回加强后的每日产出。

    优先级: 可露希尔特别订单 > 但书违约 > 龙舌兰投资 > 裁缝品质
    可露希尔在场时，但书/龙舌兰/裁缝机制均不生效。

    Args:
        ops: 贸易站干员列表
        hours: 班次持续时间（小时），用于裁缝时变P4计算

    Returns:
        (lmd_per_day, gold_per_day, equiv_gold_per_day):
        100%效率 24h 的 LMD 日产、赤金消耗、等效赤金产出（赤金/天）
    """
    # P0: 可露希尔特别订单 — 最高优先级，独占全部订单
    # 固定 2赤金/1200LMD, 2.4h/单, 10单/天, 等效产金=4赤金/天
    if any(s.buff_id.startswith("trade_ord_closure") for op in ops for s in op.skills):
        orders = 24.0 / 2.4
        equiv_gold = orders * (1200.0 - 1000.0) / 500.0
        return (12000.0, orders * 2.0, equiv_gold)

    # P1: 但书/龙舌兰/裁缝 — 可露希尔不在场时检测
    has_law = any(s.buff_id.startswith("trade_ord_law") for op in ops for s in op.skills)
    has_tequila_beta = any(s.buff_id == "trade_ord_long[010]" for op in ops for s in op.skills)
    has_tequila_alpha = any(s.buff_id == "trade_ord_long[000]" for op in ops for s in op.skills)
    has_tequila = has_tequila_beta or has_tequila_alpha
    tailor_level = _extract_tailor_level(ops)
    tequila_bonus = 500 if has_tequila_beta else 250 if has_tequila_alpha else 0

    # 裁缝时变等效P4（仅在有效时计算）
    p4 = _effective_tailor_p4(hours, tailor_level) if has_tequila or tailor_level > 0 else 0.20

    # 等效产金通用公式: tequila_bonus × p4 × orders_per_day / 500
    def _equiv_gold(orders_per_day: float) -> float:
        return orders_per_day * p4 * tequila_bonus / 500.0

    if has_law and has_tequila:
        # 但书+龙舌兰：2,3→但书(+2gold), 4→龙舌兰(+bonus LMD)
        # 但书部分以金换金净值为0，仅龙舌兰投资产生等效产金
        p2 = (1 - p4) * 3 / 8
        p3 = (1 - p4) * 5 / 8
        lmd_per_order = 2000 * p2 + 2500 * p3 + (2000 + tequila_bonus) * p4
        gold_per_order = 4 * p2 + 5 * p3 + 4 * p4
        avg_order_hours = _weighted_avg_order_time(p2, p3, p4)
        orders = 24.0 / avg_order_hours
        return (orders * lmd_per_order, orders * gold_per_order, _equiv_gold(orders))

    if has_tequila:
        # 龙舌兰（可能+裁缝）：仅4-gold订单触发投资
        p2 = (1 - p4) * 3 / 8
        p3 = (1 - p4) * 5 / 8
        lmd_per_order = 1000 * p2 + 1500 * p3 + (2000 + tequila_bonus) * p4
        gold_per_order = 2 * p2 + 3 * p3 + 4 * p4
        avg_order_hours = _weighted_avg_order_time(p2, p3, p4)
        orders = 24.0 / avg_order_hours
        return (orders * lmd_per_order, orders * gold_per_order, _equiv_gold(orders))

    if has_law:
        # 但书：2,3-gold → 违约+2, LMD加倍，以金换金净值为0
        if tailor_level > 0:
            p2 = (1 - p4) * 3 / 8
            p3 = (1 - p4) * 5 / 8
            lmd_per_order = 2000 * p2 + 2500 * p3 + 2000 * p4
            gold_per_order = 4 * p2 + 5 * p3 + 4 * p4
        else:
            lmd_per_order = 2250.0
            gold_per_order = 4.9
        avg_order_hours = _weighted_avg_order_time(p2, p3, p4) if tailor_level > 0 else _TRADE_AVG_TIME_HOURS
        return (24.0 / avg_order_hours * lmd_per_order,
                24.0 / avg_order_hours * gold_per_order,
                0.0)

    if tailor_level > 0:
        # 裁缝单独（无投资）：提升4-gold概率，无等效产金
        p2 = (1 - p4) * 3 / 8
        p3 = (1 - p4) * 5 / 8
        lmd_per_order = 1000 * p2 + 1500 * p3 + 2000 * p4
        gold_per_order = 2 * p2 + 3 * p3 + 4 * p4
        avg_order_hours = _weighted_avg_order_time(p2, p3, p4)
        return (24.0 / avg_order_hours * lmd_per_order,
                24.0 / avg_order_hours * gold_per_order,
                0.0)

    return (_TRADE_BASE_LMD_PER_DAY, _TRADE_BASE_GOLD_PER_DAY, 0.0)


@dataclass
class RoomOutput:
    """单个房间的日产出"""
    room_type: str
    room_index: int
    product: Optional[str]
    operators: list[str] = field(default_factory=list)
    head_count: int = 0
    productivity: float = 0.0
    output_per_day: float = 0.0
    drone_boost_pct: float = 0.0
    output_unit: str = ""

    def __repr__(self) -> str:
        drone_str = f" (含无人机+{self.drone_boost_pct:.0%})" if self.drone_boost_pct > 0 else ""
        head_base = 100 + self.head_count
        skill_pct = (self.productivity - 1.0) * 100
        eff_str = f"基础{head_base}%+{skill_pct:.0f}%"
        return (
            f"{self.room_type}[{self.room_index}]"
            f"({self.product}): {self.operators}"
            f" → {self.output_per_day:.1f} {self.output_unit}/天"
            f" (效率{eff_str}){drone_str}"
        )


@dataclass
class DailyProduction:
    """基建全局日产出汇总"""
    record_rooms: list[RoomOutput] = field(default_factory=list)
    gold_rooms: list[RoomOutput] = field(default_factory=list)
    trade_rooms: list[RoomOutput] = field(default_factory=list)

    daily_drones: float = 0.0
    power_operators: list[str] = field(default_factory=list)
    drone_target: str = ""

    total_records_per_day: float = 0.0
    total_gold_produced_per_day: float = 0.0
    total_gold_consumed_per_day: float = 0.0
    total_lmd_per_day: float = 0.0
    effective_lmd_per_day: float = 0.0
    gold_surplus: float = 0.0
    equivalent_gold_from_mechanism: float = 0.0  # 订单机制等效赤金产出（赤金/天）
    external_gold_per_day: float = 0.0  # 外部来源赤金（赤金/天）

    def summary(self) -> str:
        lines = [
            f"发电站: {self.power_operators} → {self.daily_drones:.0f} 架/天",
        ]
        if self.drone_target:
            lines.append(f"无人机加速目标: {self.drone_target}")
        lines.extend([
            f"作战记录产出: {self.total_records_per_day * _RECORD_EXP_PER_UNIT:,.0f} 经验/天 ({self.total_records_per_day:.1f} 个)",
            f"赤金制造: {self.total_gold_produced_per_day * _GOLD_LMD_PER_UNIT:,.0f} LMD等值/天 ({self.total_gold_produced_per_day:.1f} 个)",
        ])
        if self.external_gold_per_day > 0:
            lines.append(f"外部赤金: +{self.external_gold_per_day:.1f} 个/天 ({self.external_gold_per_day * _GOLD_LMD_PER_UNIT:,.0f} LMD等值)")
        lines.append(f"赤金消耗: {self.total_gold_consumed_per_day * _GOLD_LMD_PER_UNIT:,.0f} LMD等值/天 ({self.total_gold_consumed_per_day:.1f} 个)")
        if self.equivalent_gold_from_mechanism > 0:
            lines.append(f"订单等效赤金: +{self.equivalent_gold_from_mechanism:.1f} 个/天 ({self.equivalent_gold_from_mechanism * _GOLD_LMD_PER_UNIT:,.0f} LMD等值)")
        lines.append(f"龙门币产出: {self.effective_lmd_per_day:,.0f} /天")
        if self.gold_surplus > 0:
            lines.append(f"赤金盈余: +{self.gold_surplus:.1f} 个 ({self.gold_surplus * _GOLD_LMD_PER_UNIT:,.0f} LMD等值)")
        elif self.gold_surplus < 0:
            total_available = self.total_gold_produced_per_day + self.external_gold_per_day
            lines.append(f"赤金缺口: {abs(self.gold_surplus):.1f} 个 ({abs(self.gold_surplus) * _GOLD_LMD_PER_UNIT:,.0f} LMD等值)（贸易站开工率 {total_available/self.total_gold_consumed_per_day:.0%}）")
        return "\n".join(lines)


def _operator_lookup(operators: list[Operator]) -> dict[str, Operator]:
    return {op.name: op for op in operators}


def _calc_drone_daily(
    power_op_names: list[str],
    op_lookup: dict[str, Operator],
) -> float:
    """计算每日无人机产量

    PRTS: 基础 6 min/架 → 240 架/天
    发电站干员 efficient.all 值 ≥1 的为百分比加成
    公式: daily = 240 × (1 + Σ(bonus/100))
    """
    bonus_sum = 0.0
    for name in power_op_names:
        op = op_lookup.get(name)
        if op is None:
            continue
        best = op.best_efficiency("Power", "Drone")
        if best >= 1.0:
            bonus_sum += best
    return _DRONE_BASE_PER_DAY * (1.0 + bonus_sum / 100.0)


def _drone_multiplier(daily_drones: float, minutes_per_drone: float, hours: float) -> float:
    """无人机加速倍率

    公式: (工期分钟 + 无人机加速分钟) / 工期分钟
    """
    period_minutes = hours * 60.0
    accelerated_minutes = period_minutes + daily_drones * minutes_per_drone
    return accelerated_minutes / period_minutes


# ─── 房间产出计算上下文 ──────────────────────────────────────────

@dataclass
class _CalcCtx:
    """房间产出计算所需的全局上下文（避免参数传递冗长）"""
    op_lookup: dict[str, Operator]
    plan_ctrl_ops: list[Operator]
    global_bonus: "GlobalBonus"
    buff_pool: object
    power_count: int
    hours: float
    daily_drones: float
    drone_room_type: str
    drone_room_index: int
    all_operators: list[Operator] = field(default_factory=list)
    mood_ctx: "MoodContext | None" = None


def _drone_boost(assignment: RoomAssignment, ctx: _CalcCtx, minutes_per_drone: float) -> float:
    """计算该房间的无人机加速倍率"""
    if assignment.room_type == ctx.drone_room_type and assignment.room_index == ctx.drone_room_index:
        return _drone_multiplier(ctx.daily_drones, minutes_per_drone, ctx.hours) - 1.0
    return 0.0


def _calc_mfg_record(
    ctx: _CalcCtx, assignment: RoomAssignment, ops: list[Operator], production: DailyProduction,
) -> None:
    """制造站作战记录产出计算"""
    n = len(ops)
    ctrl_bonus = control_per_operator_bonus(ctx.plan_ctrl_ops, ops, "CombatRecord")
    eff_int = evaluate_room(ops, "Mfg", "CombatRecord", ctx.power_count, ctx.hours,
                            ctx.global_bonus, ctx.buff_pool, ctrl_per_op_bonus=ctrl_bonus,
                            all_operators=ctx.all_operators,
                            control_operators=ctx.plan_ctrl_ops,
                            mood_ctx=ctx.mood_ctx)
    productivity_int = ctx.hours * (1.0 + 0.01 * n) + eff_int / 100.0
    display_productivity = 1.0 + eff_int / (100.0 * ctx.hours)
    drone_boost = _drone_boost(assignment, ctx, _DRONE_MINUTES_MFG)
    output_per_day = _RECORD_BASE_PER_HOUR * productivity_int * (1.0 + drone_boost)
    production.record_rooms.append(RoomOutput(
        room_type="Mfg", room_index=assignment.room_index,
        product="CombatRecord", operators=assignment.operators,
        head_count=n, productivity=display_productivity,
        output_per_day=output_per_day,
        drone_boost_pct=drone_boost, output_unit="个",
    ))
    production.total_records_per_day += output_per_day


def _calc_mfg_gold(
    ctx: _CalcCtx, assignment: RoomAssignment, ops: list[Operator], production: DailyProduction,
) -> None:
    """制造站赤金产出计算"""
    n = len(ops)
    ctrl_bonus = control_per_operator_bonus(ctx.plan_ctrl_ops, ops, "PureGold")
    eff_int = evaluate_room(ops, "Mfg", "PureGold", ctx.power_count, ctx.hours,
                            ctx.global_bonus, ctx.buff_pool, ctrl_per_op_bonus=ctrl_bonus,
                            all_operators=ctx.all_operators,
                            control_operators=ctx.plan_ctrl_ops,
                            mood_ctx=ctx.mood_ctx)
    productivity_int = ctx.hours * (1.0 + 0.01 * n) + eff_int / 100.0
    display_productivity = 1.0 + eff_int / (100.0 * ctx.hours)
    drone_boost = _drone_boost(assignment, ctx, _DRONE_MINUTES_MFG)
    output_per_day = _GOLD_BASE_PER_HOUR * productivity_int * (1.0 + drone_boost)
    production.gold_rooms.append(RoomOutput(
        room_type="Mfg", room_index=assignment.room_index,
        product="PureGold", operators=assignment.operators,
        head_count=n, productivity=display_productivity,
        output_per_day=output_per_day,
        drone_boost_pct=drone_boost, output_unit="个",
    ))
    production.total_gold_produced_per_day += output_per_day


def _calc_trade(
    ctx: _CalcCtx, assignment: RoomAssignment, ops: list[Operator], production: DailyProduction,
) -> None:
    """贸易站产出计算（文档倍数法）

    lmd_output = efficiency_factor × hours/24 × lmd_per_day × (1 + drone)
    """
    n = len(ops)
    ctrl_bonus = control_per_operator_bonus(ctx.plan_ctrl_ops, ops, "Money", room_type="Trade")
    eff_int = evaluate_room(ops, "Trade", "Money", ctx.power_count, ctx.hours,
                            ctx.global_bonus, ctx.buff_pool, ctrl_per_op_bonus=ctrl_bonus,
                            all_operators=ctx.all_operators,
                            control_operators=ctx.plan_ctrl_ops,
                            mood_ctx=ctx.mood_ctx)
    efficiency_integrated = ctx.hours * (1.0 + 0.01 * n) + eff_int / 100.0
    display_productivity = 1.0 + eff_int / (100.0 * ctx.hours)
    drone_boost = _drone_boost(assignment, ctx, _DRONE_MINUTES_TRADE)

    lmd_per_day, gold_per_day, equiv_gold_per_day = _get_trade_order_multiplier(ops, ctx.hours)
    base_factor = efficiency_integrated / 24.0
    lmd_output = base_factor * lmd_per_day * (1.0 + drone_boost)
    gold_consumed = base_factor * gold_per_day * (1.0 + drone_boost)

    production.trade_rooms.append(RoomOutput(
        room_type="Trade", room_index=assignment.room_index,
        product="Money", operators=assignment.operators,
        head_count=n, productivity=display_productivity,
        output_per_day=lmd_output,
        drone_boost_pct=drone_boost, output_unit="LMD",
    ))
    production.total_gold_consumed_per_day += gold_consumed
    production.total_lmd_per_day += lmd_output
    production.equivalent_gold_from_mechanism += base_factor * equiv_gold_per_day * (1.0 + drone_boost)


def calculate(
    plan: ShiftPlan,
    operators: list[Operator],
    hours: float = 24.0,
    external_gold_per_day: float = 0.0,
    mood_ctx=None,
) -> DailyProduction:
    """计算排班方案的精确产出（含无人机加速）

    Args:
        plan: 排班计划
        operators: 全量干员池
        hours: 该班次覆盖的小时数（默认 24h 即全天）
        external_gold_per_day: 外部来源赤金（赤金/天），如日常任务等效赤金收入
        mood_ctx: 多班次心情上下文，非 None 时传入 evaluate_room 以激活心情截断
    """
    op_lookup = _operator_lookup(operators)
    production = DailyProduction()
    production.external_gold_per_day = external_gold_per_day

    # 从 plan 获取中枢干员（若未指定则回退 FIXED_CONTROL）
    plan_ctrl_ops: list[Operator] = []
    for assignment in plan.assignments:
        if assignment.room_type == "Control":
            plan_ctrl_ops = [op_lookup[n] for n in assignment.operators if n in op_lookup]
            break
    if not plan_ctrl_ops:
        plan_ctrl_ops = [op_lookup[n] for n in FIXED_CONTROL if n in op_lookup]

    # C1: 全局效率加成（使用实际中枢干员）
    global_bonus = compute_control_global_bonus(plan_ctrl_ops)

    from steward_core.solver.context import GlobalContext
    from steward_core.solver.params import SolverParams
    params = SolverParams(shift_hours=hours, dorm_level=5)
    gctx = GlobalContext.from_plan(plan, operators, params, mood_ctx=mood_ctx)
    buff_pool = gctx.buff_pool

    # 1. 收集发电站干员，计算无人机产量（按工期比例缩放）
    power_ops: list[Operator] = []
    for assignment in plan.assignments:
        if assignment.room_type == "Power":
            production.power_operators.extend(assignment.operators)
            for n in assignment.operators:
                if n in op_lookup:
                    power_ops.append(op_lookup[n])
    daily_drones_full = _calc_drone_daily(production.power_operators, op_lookup)
    production.daily_drones = daily_drones_full * (hours / 24.0)

    # 2. 确定无人机加速目标设施
    drone_room_type = plan.drone_room
    drone_room_index = plan.drone_index
    production.drone_target = f"{drone_room_type}[{drone_room_index}]"

    # 3. 计算各设施产出（走 efficiency_fn 积分，含联动）
    power_count = compute_effective_power_count(power_ops, BASE_POWER_COUNT)
    ctx = _CalcCtx(
        op_lookup=op_lookup,
        plan_ctrl_ops=plan_ctrl_ops,
        global_bonus=global_bonus,
        buff_pool=buff_pool,
        power_count=power_count,
        hours=hours,
        daily_drones=production.daily_drones,
        drone_room_type=drone_room_type,
        drone_room_index=drone_room_index,
        all_operators=operators,
        mood_ctx=mood_ctx,
    )

    for assignment in plan.assignments:
        if not assignment.operators:
            continue
        ops = [op_lookup[n] for n in assignment.operators if n in op_lookup]
        if not ops:
            continue

        if assignment.room_type == "Mfg" and assignment.product == "CombatRecord":
            _calc_mfg_record(ctx, assignment, ops, production)
        elif assignment.room_type == "Mfg" and assignment.product == "PureGold":
            _calc_mfg_gold(ctx, assignment, ops, production)
        elif assignment.room_type == "Trade":
            _calc_trade(ctx, assignment, ops, production)

    # 4. 赤金供需平衡（含外部来源赤金，外部赤金按班次时长折算）
    shift_external = production.external_gold_per_day * (ctx.hours / 24.0)
    total_available_gold = production.total_gold_produced_per_day + shift_external
    production.gold_surplus = total_available_gold - production.total_gold_consumed_per_day
    if production.gold_surplus < 0:
        ratio = total_available_gold / max(production.total_gold_consumed_per_day, 0.001)
        production.effective_lmd_per_day = production.total_lmd_per_day * ratio
    else:
        production.effective_lmd_per_day = production.total_lmd_per_day

    return production
