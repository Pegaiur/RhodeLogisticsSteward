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
    synergy_trade_pair,
    synergy_trade_share,
    synergy_swires_order_limit,
    synergy_degenbrecher_order_limit,
    synergy_trade_efficiency_amplifier,
    synergy_trade_conditional_eff,
    synergy_facility_group,
    compute_trade_order_limit,
    GlobalBonus,
    operator_estimated_efficiency,
)

_LAYOUT_243 = LayoutConfig.layout_243()


def _resolve_zeroing(
    operators: list[Operator],
    room_type: str,
    product: str,
    power_count: int,
    T: float,
) -> tuple[list, list, list, set[str], list[Operator]]:
    """归零解析：计算所有归零来源并确定 zero_set

    必须在其他联动函数之前执行，避免被归零干员的效率加成泄漏。
    """
    from steward_core.synergy.conflicts import resolve_efficiency_conflicts

    disabled_mechs = resolve_efficiency_conflicts(operators, room_type)

    auto_segs: list = []
    zero_set: set[str] = set()
    if "automation" not in disabled_mechs:
        auto_segs, zero_set = synergy_automation(operators, room_type, power_count, T)

    whisper_segs: list = []
    if "whisper" not in disabled_mechs:
        whisper_segs, whisper_zero = synergy_whisper(operators, room_type, T)
        zero_set |= whisper_zero

    zero_segs, zero_set2 = synergy_zeroing_variant(operators, room_type, product, T)
    zero_set |= zero_set2

    non_zero_ops = [op for op in operators if op.name not in zero_set]
    return auto_segs, whisper_segs, zero_segs, zero_set, non_zero_ops


def _eval_per_operator_efficiency(
    operators: list[Operator],
    room_type: str,
    product: str,
    T: float,
    *,
    zero_set: set[str],
    warmup_map: dict[str, float],
    mood_map: dict[str, float],
    mood_ctx,
    co_worker_names: list[str] | None,
    qianhuai_mood: float | None,
) -> float:
    """逐干员个人效率累加

    对非归零干员依次计算爬升/梯级衰减/常数效率段。
    """
    total = 0.0
    for op in operators:
        if op.name in zero_set:
            continue
        t_init = warmup_map.get(op.name, 0.0)
        op_mood = mood_map.get(op.name, 24.0)
        op_burn = 0.0
        if mood_ctx is not None:
            op_burn = mood_ctx.work_burn(
                op.name, room_type, len(operators),
                co_workers=co_worker_names,
            )
        ramp_segs = operator_ramp_segments(
            op, room_type, product, T, t_initial=t_init,
            mood_burn=op_burn, mood_initial=op_mood,
        )
        if ramp_segs is not None:
            total += integrate_segments(ramp_segs, T)
        elif op.name == "铅踝" and qianhuai_mood is not None:
            qianhuai_segs = stepped_efficiency(
                base=30, step_size=5, step_interval=4,
                mood_burn=op_burn, T=T, mood_initial=qianhuai_mood,
            )
            total += integrate_segments(qianhuai_segs, T)
        else:
            eff = operator_estimated_efficiency(op, room_type, product)
            if eff > 0:
                total += integrate_segments(
                    constant_efficiency(
                        eff, mood_burn=op_burn, T=T,
                        mood_initial=op_mood,
                    ), T,
                )
    return total


def _eval_cross_room_effects(
    operators: list[Operator],
    non_zero_ops: list[Operator],
    room_type: str,
    product: str,
    T: float,
    *,
    buff_pool,
    all_assignments: dict[str, list[Operator]] | None,
    all_operators: list[Operator] | None,
) -> float:
    """B 层跨房间效果：B6(全局阵营) + B7(跨房间配对) + B8(设施 group) + BuffPool 消费"""
    total = 0.0

    if all_assignments is not None:
        total += integrate_segments(
            synergy_cross_room_pair(non_zero_ops, room_type, product, all_assignments, T), T,
        )
        if room_type == "Trade":
            total += integrate_segments(
                synergy_trade_conditional_eff(operators, room_type, all_assignments, T), T,
            )

    if all_assignments is not None:
        total += integrate_segments(
            synergy_facility_group(non_zero_ops, room_type, all_assignments, T), T,
        )

    if all_operators is not None:
        total += integrate_segments(
            synergy_global_faction(non_zero_ops, room_type, product, all_operators, T), T,
        )

    if buff_pool is not None:
        total += integrate_segments(
            synergy_buff_pool_consumer(non_zero_ops, room_type, product, buff_pool, T), T,
        )

    return total


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

    # ── 心情截断参数 ──
    warmup_map: dict[str, float] = {}
    mood_map: dict[str, float] = {}
    co_worker_names: list[str] | None = None
    qianhuai_mood = None
    if mood_ctx is not None:
        co_worker_names = [op.name for op in operators]
        qianhuai_mood = mood_ctx.qianhuai_decay_basis(operators, room_type)
        for op in operators:
            w = mood_ctx.warmup_hours.get(op.name, 0.0)
            if w > 0:
                warmup_map[op.name] = w
            mood_map[op.name] = mood_ctx.mood_of(op.name)

    # ── 一、归零解析 ──
    auto_segs, whisper_segs, zero_segs, zero_set, non_zero_ops = _resolve_zeroing(
        operators, room_type, product, power_count, T,
    )

    # ── 二、房间组成型联动 ──
    total = integrate_segments(synergy_pair(operators, room_type, product, T), T)
    alias = synergy_skill_alias(operators)

    order_ctx = None
    if room_type == "Trade" and layout is not None:
        order_ctx = compute_trade_order_limit(
            operators, layout, control_operators or [],
        )

    # ── 三、效率加成型联动 ──
    total += integrate_segments(synergy_faction_room(non_zero_ops, room_type, product, T), T)
    total += integrate_segments(synergy_skill_count(non_zero_ops, room_type, alias, T), T)
    total += integrate_segments(synergy_trade_gold_lines(
        operators, room_type, product, layout, T=T,
    ), T)
    total += integrate_segments(synergy_facility_count(
        operators, room_type, product, layout, T=T,
    ), T)

    total += integrate_segments(synergy_trade_pair(non_zero_ops, room_type, T), T)
    total += integrate_segments(synergy_trade_share(non_zero_ops, room_type, T), T)
    if order_ctx is not None:
        total += integrate_segments(
            synergy_swires_order_limit(non_zero_ops, room_type, order_ctx, T), T,
        )
        total += integrate_segments(
            synergy_degenbrecher_order_limit(non_zero_ops, room_type, order_ctx, T), T,
        )

    # ── 四、归零加成自身效率段 ──
    total += integrate_segments(auto_segs, T)
    total += integrate_segments(whisper_segs, T)
    total += integrate_segments(zero_segs, T)
    total += ctrl_per_op_bonus * T

    # ── 五、逐干员个人效率 ──
    total += _eval_per_operator_efficiency(
        operators, room_type, product, T,
        zero_set=zero_set, warmup_map=warmup_map, mood_map=mood_map,
        mood_ctx=mood_ctx, co_worker_names=co_worker_names,
        qianhuai_mood=qianhuai_mood,
    )

    # ── 六、房间属性加成 ──
    total += integrate_segments(synergy_capacity_to_eff(operators, room_type, product, T), T)
    total += integrate_segments(synergy_efficiency_amplifier(non_zero_ops, room_type, product, T), T)

    # 贸易站效率→效率放大器（雪雉天道酬勤）— 必须在 per-operator + 房间属性之后，
    # 因为 total/T 是所有前置效率的平均值。
    if room_type == "Trade":
        total += integrate_segments(
            synergy_trade_efficiency_amplifier(non_zero_ops, room_type, total / T, T), T,
        )

    total += integrate_segments(synergy_token_prod(operators, room_type, product, power_platforms, T), T)

    if control_operators is not None and room_type == "Trade":
        total += integrate_segments(
            synergy_jie_order(non_zero_ops, room_type, control_operators, T, order_ctx=order_ctx), T,
        )

    # ── 七、B 层跨房间效果 ──
    total += _eval_cross_room_effects(
        operators, non_zero_ops, room_type, product, T,
        buff_pool=buff_pool, all_assignments=all_assignments,
        all_operators=all_operators,
    )

    # ── 八、全局加成 ──
    if room_type == "Mfg":
        total += global_bonus.mfg_bonus * T
    elif room_type == "Trade":
        total += global_bonus.trade_bonus * T

    return total
