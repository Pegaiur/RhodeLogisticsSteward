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
    GlobalBonus, compute_control_global_bonus, compute_buff_pool,
    compute_effective_power_count,
    control_per_operator_bonus,
    _B3_ROSEMARY, _B5_EBNHLZ,
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
    """从裁缝/手工艺品系列 buff_id 提取最高等级

    裁缝·α (trade_ord_wt&cost[x0x]): 小幅提升4-gold概率
    裁缝·β (trade_ord_wt&cost[x1x]): 提升4-gold概率
    手工艺品·α (trade_ord_wt&cost[x0x]): 小幅提升（同α）
    手工艺品·β (trade_ord_wt&cost[x1x]): 提升（同β）

    buff_id 格式为 trade_ord_wt&cost[ABC]，B=0表示α级，B=1表示β级。
    """
    max_level = 0
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
                max_level = 2
            elif tier == "0" and max_level < 1:
                max_level = 1
    return max_level


def _get_trade_order_multiplier(ops: list[Operator]) -> tuple[float, float]:
    """贸易站订单机制倍数查询

    检测干员组合中的特殊订单机制（但书违约、龙舌兰投资、
    裁缝品质、可露希尔独占），返回加强后的每日产出。

    Returns:
        (lmd_per_day, gold_per_day): 100%效率 24h 的 LMD 日产和赤金消耗
    """
    has_law = any(s.buff_id.startswith("trade_ord_law") for op in ops for s in op.skills)
    has_closure = any(s.buff_id.startswith("trade_ord_closure") for op in ops for s in op.skills)
    has_tequila_beta = any(s.buff_id == "trade_ord_long[010]" for op in ops for s in op.skills)
    has_tequila_alpha = any(s.buff_id == "trade_ord_long[000]" for op in ops for s in op.skills)
    has_tequila = has_tequila_beta or has_tequila_alpha
    tailor_level = _extract_tailor_level(ops)
    tequila_bonus = 500 if has_tequila_beta else 250 if has_tequila_alpha else 0

    if has_closure:
        # 可露希尔特别订单：固定 2赤金/1200LMD, 2.4h/单
        return (12000.0, 24.0 / 2.4 * 2.0)

    if has_law and has_tequila:
        # 但书+龙舌兰：2,3→但书(+2gold), 4→龙舌兰(+bonus LMD)
        # 裁缝同时影响4-gold概率
        p4 = 0.20 + tailor_level * 0.05
        p2 = (1 - p4) * 3 / 8
        p3 = (1 - p4) * 5 / 8
        lmd_per_order = 2000 * p2 + 2500 * p3 + (2000 + tequila_bonus) * p4
        gold_per_order = 4 * p2 + 5 * p3 + 4 * p4
        base_orders = 24.0 / _TRADE_AVG_TIME_HOURS
        return (base_orders * lmd_per_order, base_orders * gold_per_order)

    if has_tequila:
        # 龙舌兰（可能+裁缝）：仅4-gold订单触发投资
        p4 = 0.20 + tailor_level * 0.05
        p2 = (1 - p4) * 3 / 8
        p3 = (1 - p4) * 5 / 8
        lmd_per_order = 1000 * p2 + 1500 * p3 + (2000 + tequila_bonus) * p4
        gold_per_order = 2 * p2 + 3 * p3 + 4 * p4
        base_orders = 24.0 / _TRADE_AVG_TIME_HOURS
        return (base_orders * lmd_per_order, base_orders * gold_per_order)

    if has_law:
        # 但书：2,3-gold → 违约+2, LMD加倍
        lmd_per_order = 2250.0
        gold_per_order = 4.9
        base_orders = 24.0 / _TRADE_AVG_TIME_HOURS
        return (base_orders * lmd_per_order, base_orders * gold_per_order)

    if tailor_level > 0:
        # 裁缝单独（无投资）：提升4-gold概率
        p4 = 0.20 + tailor_level * 0.05
        p2 = (1 - p4) * 3 / 8
        p3 = (1 - p4) * 5 / 8
        lmd_per_order = 1000 * p2 + 1500 * p3 + 2000 * p4
        gold_per_order = 2 * p2 + 3 * p3 + 4 * p4
        base_orders = 24.0 / _TRADE_AVG_TIME_HOURS
        return (base_orders * lmd_per_order, base_orders * gold_per_order)

    return (_TRADE_BASE_LMD_PER_DAY, _TRADE_BASE_GOLD_PER_DAY)


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

    def summary(self) -> str:
        lines = [
            f"发电站: {self.power_operators} → {self.daily_drones:.0f} 架/天",
        ]
        if self.drone_target:
            lines.append(f"无人机加速目标: {self.drone_target}")
        lines.extend([
            f"作战记录产出: {self.total_records_per_day * _RECORD_EXP_PER_UNIT:,.0f} 经验/天 ({self.total_records_per_day:.1f} 个)",
            f"赤金制造: {self.total_gold_produced_per_day * _GOLD_LMD_PER_UNIT:,.0f} LMD等值/天 ({self.total_gold_produced_per_day:.1f} 个)",
            f"赤金消耗: {self.total_gold_consumed_per_day * _GOLD_LMD_PER_UNIT:,.0f} LMD等值/天 ({self.total_gold_consumed_per_day:.1f} 个)",
            f"龙门币产出: {self.effective_lmd_per_day:,.0f} /天",
        ])
        if self.gold_surplus > 0:
            lines.append(f"赤金盈余: +{self.gold_surplus:.1f} 个 ({self.gold_surplus * _GOLD_LMD_PER_UNIT:,.0f} LMD等值)")
        elif self.gold_surplus < 0:
            lines.append(f"赤金缺口: {abs(self.gold_surplus):.1f} 个 ({abs(self.gold_surplus) * _GOLD_LMD_PER_UNIT:,.0f} LMD等值)（贸易站开工率 {self.effective_lmd_per_day/self.total_lmd_per_day:.0%}）")
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
                            ctx.global_bonus, ctx.buff_pool, ctrl_per_op_bonus=ctrl_bonus)
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
                            ctx.global_bonus, ctx.buff_pool, ctrl_per_op_bonus=ctrl_bonus)
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
    ctrl_bonus = control_per_operator_bonus(ctx.plan_ctrl_ops, ops, "Money")
    eff_int = evaluate_room(ops, "Trade", "Money", ctx.power_count, ctx.hours,
                            ctx.global_bonus, ctx.buff_pool, ctrl_per_op_bonus=ctrl_bonus)
    efficiency_integrated = ctx.hours * (1.0 + 0.01 * n) + eff_int / 100.0
    display_productivity = 1.0 + eff_int / (100.0 * ctx.hours)
    drone_boost = _drone_boost(assignment, ctx, _DRONE_MINUTES_TRADE)

    lmd_per_day, gold_per_day = _get_trade_order_multiplier(ops)
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


def calculate(plan: ShiftPlan, operators: list[Operator], hours: float = 24.0) -> DailyProduction:
    """计算排班方案的精确产出（含无人机加速）

    Args:
        plan: 排班计划
        operators: 全量干员池
        hours: 该班次覆盖的小时数（默认 24h 即全天）
    """
    op_lookup = _operator_lookup(operators)
    production = DailyProduction()

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

    # 收集宿舍干员
    dorm_ops: list[Operator] = []
    for assignment in plan.assignments:
        if assignment.room_type in ("Dormitory", "Dorm"):
            for n in assignment.operators:
                if n in op_lookup:
                    dorm_ops.append(op_lookup[n])

    # 检测 B1 感知信息生成者是否在工作设施中
    has_rosmontis_in_mfg = any(
        _B3_ROSEMARY in a.operators and a.room_type == "Mfg"
        for a in plan.assignments
    )
    has_ebnhlz_in_trade = any(
        _B5_EBNHLZ in a.operators and a.room_type == "Trade"
        for a in plan.assignments
    )

    # B1: 人间烟火 + 宿舍感知信息预计算（使用实际中枢干员）
    # 当迷迭香在制造站时，求解器假设令 mood<12 以产出感知信息（非烟火）
    ling_mood_below_12 = has_rosmontis_in_mfg
    buff_pool = compute_buff_pool(
        plan_ctrl_ops, suich_count=5,
        dorm_operators=dorm_ops, dorm_level=5,
        has_rosmontis_in_mfg=has_rosmontis_in_mfg,
        has_ebnhlz_in_trade=has_ebnhlz_in_trade,
        ling_mood_below_12=ling_mood_below_12,
    )

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

    # 4. 赤金供需平衡
    production.gold_surplus = (
        production.total_gold_produced_per_day - production.total_gold_consumed_per_day
    )
    if production.gold_surplus < 0:
        ratio = production.total_gold_produced_per_day / max(production.total_gold_consumed_per_day, 0.001)
        production.effective_lmd_per_day = production.total_lmd_per_day * ratio
    else:
        production.effective_lmd_per_day = production.total_lmd_per_day

    return production
