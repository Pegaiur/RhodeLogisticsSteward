"""房间效率评估（共享模块）

合并 solver._evaluate_room_combo 与 production._room_efficiency_integral，
确保排班评分与产出报告使用完全一致的计算口径。
"""

from steward_core.models import Operator, LayoutConfig
from steward_core.efficiency_fn import constant_efficiency, integrate_segments
from steward_core.synergy import (
    synergy_pair, synergy_skill_count, synergy_skill_alias, synergy_automation,
    synergy_facility_count, synergy_buff_pool_consumer,
    GlobalBonus,
)

_LAYOUT_243 = LayoutConfig.layout_243()


def evaluate_room(
    operators: list[Operator],
    room_type: str,
    product: str,
    power_count: int = 3,
    T: float = 12.0,
    global_bonus: GlobalBonus | None = None,
    buff_pool = None,
    ctrl_per_op_bonus: float = 0.0,
    layout: LayoutConfig | None = None,
) -> float:
    """评估一个房间组合的 T 小时总效率积分 Σ∫e(t)dt

    含联动(A1/A3/A4/A5/A6) + 个人效率 + B层消费 + 全局加成(C1) + 中枢条件加成。

    solver 与 production 统一调用此函数，确保排班评分与产出报告一致。
    """
    if not operators:
        return 0.0

    if global_bonus is None:
        global_bonus = GlobalBonus()
    if layout is None:
        layout = _LAYOUT_243

    total = integrate_segments(synergy_pair(operators, room_type, product), T)

    alias = synergy_skill_alias(operators)
    total += integrate_segments(synergy_skill_count(operators, room_type, alias), T)
    total += integrate_segments(synergy_facility_count(
        operators, room_type, product, layout,
    ), T)

    auto_segs, zero_set = synergy_automation(operators, room_type, power_count)
    total += integrate_segments(auto_segs, T)

    total += ctrl_per_op_bonus * T

    for op in operators:
        if op.name in zero_set:
            continue
        eff = op.best_efficiency(room_type, product)
        if eff > 0:
            total += integrate_segments(constant_efficiency(eff, mood_burn=0.0, T=T), T)

    if buff_pool is not None:
        # 自动化归零也适用于 B 层消费者（B3/B4 等非设施数量型加成）
        non_zero_ops = [op for op in operators if op.name not in zero_set]
        total += integrate_segments(
            synergy_buff_pool_consumer(non_zero_ops, room_type, product, buff_pool), T,
        )

    if room_type == "Mfg":
        total += global_bonus.mfg_bonus * T
    elif room_type == "Trade":
        total += global_bonus.trade_bonus * T

    return total
