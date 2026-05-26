"""产出计算模块

基于 PRTS Wiki 公式计算各设施的精确日产出，含无人机加速：
  https://prts.wiki/w/罗德岛基建/制造站
  https://prts.wiki/w/罗德岛基建/贸易站
  https://prts.wiki/w/罗德岛基建/发电站

全部假设设施等级为 Lv3。
"""

from dataclasses import dataclass, field
from typing import Optional

from steward_core.models import Operator, ShiftPlan, LayoutConfig
from steward_core.efficiency_fn import constant_efficiency, integrate_segments
from steward_core.synergy import (
    synergy_pair, synergy_skill_count, synergy_skill_alias, synergy_automation,
    synergy_facility_count, synergy_buff_pool_consumer,
    GlobalBonus, compute_control_global_bonus, compute_buff_pool,
)
from steward_core.constants import FIXED_CONTROL

# ─── 制造站 Lv3 基础参数 ────────────────────────────────────────
# 作战记录：基础 1个/3h → 0.333 个/h
_RECORD_BASE_PER_HOUR = 1.0 / 3.0
# 赤金：基础 1个/1.2h → 0.833 个/h
_GOLD_BASE_PER_HOUR = 1.0 / 1.2

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


@dataclass
class RoomOutput:
    """单个房间的日产出"""
    room_type: str
    room_index: int
    product: Optional[str]
    operators: list[str] = field(default_factory=list)
    productivity: float = 0.0
    output_per_day: float = 0.0
    drone_boost_pct: float = 0.0
    output_unit: str = ""

    def __repr__(self) -> str:
        drone_str = f" (含无人机+{self.drone_boost_pct:.0%})" if self.drone_boost_pct > 0 else ""
        return (
            f"{self.room_type}[{self.room_index}]"
            f"({self.product}): {self.operators}"
            f" → {self.output_per_day:.1f} {self.output_unit}/天"
            f"{drone_str}"
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
            f"作战记录产出: {self.total_records_per_day:.1f} 个/天",
            f"赤金制造: {self.total_gold_produced_per_day:.1f} 个/天",
            f"赤金消耗: {self.total_gold_consumed_per_day:.1f} 个/天",
            f"龙门币产出: {self.effective_lmd_per_day:,.0f} /天",
        ])
        if self.gold_surplus > 0:
            lines.append(f"赤金盈余: +{self.gold_surplus:.1f} 个/天")
        elif self.gold_surplus < 0:
            lines.append(f"赤金缺口: {self.gold_surplus:.1f} 个/天（贸易站开工率 {self.effective_lmd_per_day/self.total_lmd_per_day:.0%}）")
        return "\n".join(lines)


def _operator_lookup(operators: list[Operator]) -> dict[str, Operator]:
    return {op.name: op for op in operators}


def _room_efficiency_integral(
    operators: list[Operator],
    room_type: str,
    product: str,
    power_count: int = 3,
    T: float = 12.0,
    global_bonus: GlobalBonus | None = None,
    buff_pool = None,
) -> float:
    """返回房间总效率积分 Σ∫e(t)dt（含联动+全局加成+烟火）

    与 solver._evaluate_room_combo 使用相同的积分逻辑，
    确保排班评分与产出报告一致。
    """
    if not operators:
        return 0.0

    if global_bonus is None:
        global_bonus = GlobalBonus()

    total = integrate_segments(synergy_pair(operators, room_type, product), T)

    alias = synergy_skill_alias(operators)
    total += integrate_segments(synergy_skill_count(operators, room_type, alias), T)
    total += integrate_segments(synergy_facility_count(
        operators, room_type, product, _LAYOUT_243,
    ), T)

    auto_segs, zero_set = synergy_automation(operators, room_type, power_count)
    total += integrate_segments(auto_segs, T)

    for op in operators:
        if op.name in zero_set:
            continue
        eff = op.best_efficiency(room_type, product)
        if eff > 0:
            total += integrate_segments(constant_efficiency(eff, mood_burn=0.0, T=T), T)

    if buff_pool is not None:
        total += integrate_segments(
            synergy_buff_pool_consumer(operators, room_type, product, buff_pool), T,
        )

    if room_type == "Mfg":
        total += global_bonus.mfg_bonus * T
    elif room_type == "Trade":
        total += global_bonus.trade_bonus * T

    return total


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


def calculate(plan: ShiftPlan, operators: list[Operator], hours: float = 24.0) -> DailyProduction:
    """计算排班方案的精确产出（含无人机加速）

    Args:
        plan: 排班计划
        operators: 全量干员池
        hours: 该班次覆盖的小时数（默认 24h 即全天）
    """
    op_lookup = _operator_lookup(operators)
    production = DailyProduction()

    # C1: 全局效率加成
    control_ops = [op for op in operators if op.name in FIXED_CONTROL]
    global_bonus = compute_control_global_bonus(control_ops)

    # B1: 人间烟火预计算
    buff_pool = compute_buff_pool(control_ops, suich_count=5)

    # 1. 收集发电站干员，计算无人机产量（按工期比例缩放）
    for assignment in plan.assignments:
        if assignment.room_type == "Power":
            production.power_operators.extend(assignment.operators)
    daily_drones_full = _calc_drone_daily(production.power_operators, op_lookup)
    production.daily_drones = daily_drones_full * (hours / 24.0)

    # 2. 确定无人机加速目标设施
    drone_room_type = plan.drone_room
    drone_room_index = plan.drone_index
    production.drone_target = f"{drone_room_type}[{drone_room_index}]"

    # 3. 计算各设施产出（走 efficiency_fn 积分，含联动）
    power_count = sum(1 for a in plan.assignments if a.room_type == "Power" and a.operators)
    for assignment in plan.assignments:
        ops = [op_lookup[n] for n in assignment.operators if n in op_lookup]
        if not ops:
            continue
        n = len(ops)

        if assignment.room_type == "Mfg" and assignment.product == "CombatRecord":
            eff_int = _room_efficiency_integral(ops, "Mfg", "CombatRecord", power_count, hours, global_bonus, buff_pool)
            productivity_int = hours * (1.0 + 0.01 * n) + eff_int / 100.0
            avg_prod = productivity_int / hours
            drone_boost = 0.0
            if assignment.room_type == drone_room_type and assignment.room_index == drone_room_index:
                drone_boost = _drone_multiplier(production.daily_drones, _DRONE_MINUTES_MFG, hours) - 1.0
            output_per_day = _RECORD_BASE_PER_HOUR * productivity_int * (1.0 + drone_boost)
            room = RoomOutput(
                room_type="Mfg", room_index=assignment.room_index,
                product="CombatRecord", operators=assignment.operators,
                productivity=avg_prod, output_per_day=output_per_day,
                drone_boost_pct=drone_boost, output_unit="个",
            )
            production.record_rooms.append(room)
            production.total_records_per_day += output_per_day

        elif assignment.room_type == "Mfg" and assignment.product == "PureGold":
            eff_int = _room_efficiency_integral(ops, "Mfg", "PureGold", power_count, hours, global_bonus, buff_pool)
            productivity_int = hours * (1.0 + 0.01 * n) + eff_int / 100.0
            avg_prod = productivity_int / hours
            drone_boost = 0.0
            if assignment.room_type == drone_room_type and assignment.room_index == drone_room_index:
                drone_boost = _drone_multiplier(production.daily_drones, _DRONE_MINUTES_MFG, hours) - 1.0
            output_per_day = _GOLD_BASE_PER_HOUR * productivity_int * (1.0 + drone_boost)
            room = RoomOutput(
                room_type="Mfg", room_index=assignment.room_index,
                product="PureGold", operators=assignment.operators,
                productivity=avg_prod, output_per_day=output_per_day,
                drone_boost_pct=drone_boost, output_unit="个",
            )
            production.gold_rooms.append(room)
            production.total_gold_produced_per_day += output_per_day

        elif assignment.room_type == "Trade":
            eff_int = _room_efficiency_integral(ops, "Trade", "Money", power_count, hours, global_bonus, buff_pool)
            efficiency_integrated = hours * (1.0 + 0.01 * n) + eff_int / 100.0
            avg_eff = efficiency_integrated / hours
            drone_boost = 0.0
            if assignment.room_type == drone_room_type and assignment.room_index == drone_room_index:
                drone_boost = _drone_multiplier(production.daily_drones, _DRONE_MINUTES_TRADE, hours) - 1.0
            orders_per_day = efficiency_integrated / _TRADE_AVG_TIME_HOURS * (1.0 + drone_boost)
            gold_consumed = orders_per_day * _TRADE_AVG_GOLD_PER_ORDER
            lmd_output = orders_per_day * _TRADE_AVG_LMD_PER_ORDER
            room = RoomOutput(
                room_type="Trade", room_index=assignment.room_index,
                product="Money", operators=assignment.operators,
                productivity=avg_eff, output_per_day=lmd_output,
                drone_boost_pct=drone_boost, output_unit="LMD",
            )
            production.trade_rooms.append(room)
            production.total_gold_consumed_per_day += gold_consumed
            production.total_lmd_per_day += lmd_output

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
