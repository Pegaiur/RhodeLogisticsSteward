"""房间效率评估（共享模块）

合并 solver._evaluate_room_combo 与 production._room_efficiency_integral，
确保排班评分与产出报告使用完全一致的计算口径。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from steward_core.models import Operator, LayoutConfig
from steward_core.efficiency_fn import constant_efficiency, integrate_segments, stepped_efficiency
from steward_core.synergy import (
    synergy_pair, synergy_skill_count, synergy_skill_alias, synergy_automation,
    synergy_facility_count, synergy_buff_pool_consumer,
    operator_ramp_segments,
    synergy_capacity_to_eff, synergy_efficiency_amplifier,
    synergy_zeroing_variant, synergy_token_prod,
    synergy_faction_room, synergy_cross_room_pair,
    synergy_trade_gold_lines,
    synergy_whisper,
    synergy_global_faction,
    synergy_jie_order,
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
    power_platforms: dict[str, bool] | None = None,
    all_assignments: dict[str, list[Operator]] | None = None,
    all_operators: list[Operator] | None = None,
    control_operators: list[Operator] | None = None,
    mood_ctx: "MoodContext | None" = None,
) -> float:
    """评估一个房间组合的 T 小时总效率积分 Σ∫e(t)dt

    含联动(A1/A3/A4/A5/A6) + 个人效率 + B层消费(B1-B5) + 全局阵营计数(B6)
    + 跨房间配对(B7) + 全局加成(C1) + 中枢条件加成。
    mood_ctx 不为 None 时启用心情截断和铅踝梯级衰减。
    """
    if TYPE_CHECKING:
        from steward_core.mood_flow import MoodContext

    if not operators:
        return 0.0

    if global_bonus is None:
        global_bonus = GlobalBonus()
    if layout is None:
        layout = _LAYOUT_243

    # 心情截断参数
    mood_burn = 0.0
    mood_blue_face = 0.0
    qiangan_mood = None
    warmup_map: dict[str, float] = {}
    mood_map: dict[str, float] = {}
    if mood_ctx is not None:
        mood_burn = mood_ctx.room_burn(operators, room_type)
        mood_blue_face = mood_ctx.params.mood_blue_face if mood_ctx.params else 12.0
        qiangan_mood = mood_ctx.qiangan_decay_basis(operators, room_type)
        for op in operators:
            w = mood_ctx.warmup_hours.get(op.name, 0.0)
            if w > 0:
                warmup_map[op.name] = w
            mood_map[op.name] = mood_ctx.mood_of(op.name)

    # 第一步：计算所有归零来源（自动化/低语/归零变体），确定 zero_set
    # 必须在其他联动函数之前执行，避免被归零干员的效率加成泄漏到 total
    auto_segs, zero_set = synergy_automation(operators, room_type, power_count, T)

    whisper_segs, whisper_zero = synergy_whisper(operators, room_type, T)
    zero_set |= whisper_zero

    zero_segs, zero_set2 = synergy_zeroing_variant(operators, room_type, product, T)
    zero_set |= zero_set2

    non_zero_ops = [op for op in operators if op.name not in zero_set]

    # 第二步：房间组成型联动（不受归零影响，仅判定干员是否在场）
    # synergy_pair 仅 Mfg 生效，check 持有者与目标是否同房
    total = integrate_segments(synergy_pair(operators, room_type, product, T), T)

    # 技能类型别名（海沫等），基于完整房间组成判定
    alias = synergy_skill_alias(operators)

    # 第三步：效率加成型联动（仅非归零干员的效率参与计算）
    total += integrate_segments(synergy_faction_room(non_zero_ops, room_type, product, T), T)
    total += integrate_segments(synergy_skill_count(non_zero_ops, room_type, alias, T), T)
    total += integrate_segments(synergy_facility_count(
        non_zero_ops, room_type, product, layout, T=T,
    ), T)
    total += integrate_segments(synergy_trade_gold_lines(
        non_zero_ops, room_type, product, layout, T=T,
    ), T)

    # 第四步：归零加成自身的效率段
    total += integrate_segments(auto_segs, T)
    total += integrate_segments(whisper_segs, T)
    total += integrate_segments(zero_segs, T)

    total += ctrl_per_op_bonus * T

    for op in operators:
        if op.name in zero_set:
            continue
        t_init = warmup_map.get(op.name, 0.0)
        ramp_segs = operator_ramp_segments(op, room_type, product, T, t_initial=t_init)
        if ramp_segs is not None:
            total += integrate_segments(ramp_segs, T)
        elif op.name == "铅踝" and qiangan_mood is not None:
            qiangan_segs = stepped_efficiency(
                base=30, step_size=5, step_interval=4,
                mood_burn=mood_burn, T=T, mood_initial=qiangan_mood,
            )
            total += integrate_segments(qiangan_segs, T)
        else:
            eff = op.best_efficiency(room_type, product)
            if eff > 0:
                op_mood = mood_map.get(op.name, 24.0)
                total += integrate_segments(
                    constant_efficiency(
                        eff, mood_burn=mood_burn, T=T,
                        mood_initial=op_mood, mood_blue_face=mood_blue_face,
                    ), T,
                )

    # 容量→效率（仅未归零干员的容量参与计算）
    total += integrate_segments(synergy_capacity_to_eff(non_zero_ops, room_type, product, T), T)

    # 效率放大器（仅未归零干员的效率参与计算）
    total += integrate_segments(synergy_efficiency_amplifier(non_zero_ops, room_type, product, T), T)

    # 机械精通（作业平台在发电站）
    total += integrate_segments(synergy_token_prod(non_zero_ops, room_type, product, power_platforms, T), T)

    # A7 孑订单压缩机制
    if control_operators is not None and room_type == "Trade":
        total += integrate_segments(
            synergy_jie_order(non_zero_ops, room_type, control_operators, T), T,
        )

    # B7 跨房间配对
    if all_assignments is not None:
        total += integrate_segments(
            synergy_cross_room_pair(non_zero_ops, room_type, product, all_assignments, T), T,
        )

    # B6 全局阵营计数
    if all_operators is not None:
        total += integrate_segments(
            synergy_global_faction(non_zero_ops, room_type, product, all_operators, T), T,
        )

    if buff_pool is not None:
        total += integrate_segments(
            synergy_buff_pool_consumer(non_zero_ops, room_type, product, buff_pool, T), T,
        )

    if room_type == "Mfg":
        total += global_bonus.mfg_bonus * T
    elif room_type == "Trade":
        total += global_bonus.trade_bonus * T

    return total
