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

    # 心情截断参数 — 多班次启用时逐干员计算 burn 以支持 per-operator mp_cost buff
    warmup_map: dict[str, float] = {}
    mood_map: dict[str, float] = {}
    co_worker_names: list[str] | None = None
    qianhuai_mood = None
    if mood_ctx is not None:
        co_worker_names = [op.name for op in operators]  # 包含自身：mp_cost buff 作用于全房含持有者
        qianhuai_mood = mood_ctx.qianhuai_decay_basis(operators, room_type)
        for op in operators:
            w = mood_ctx.warmup_hours.get(op.name, 0.0)
            if w > 0:
                warmup_map[op.name] = w
            mood_map[op.name] = mood_ctx.mood_of(op.name)

    # 第一步：计算所有归零来源（自动化/低语/归零变体），确定 zero_set
    # 必须在其他联动函数之前执行，避免被归零干员的效率加成泄漏到 total
    # 冲突解析：订单机制在场时禁用对应效率联动（如 Closure 覆盖 whisper）
    from steward_core.synergy.conflicts import resolve_efficiency_conflicts

    disabled_mechs = resolve_efficiency_conflicts(operators, room_type)

    auto_segs: list = []
    zero_set: set[str] = set()
    if "automation" not in disabled_mechs:
        # automation 暂无禁用方，此分支当前恒真（预留扩展点）
        auto_segs, zero_set = synergy_automation(operators, room_type, power_count, T)

    whisper_segs: list = []
    if "whisper" not in disabled_mechs:
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

    # ── 贸易站订单上限上下文 ──
    order_ctx = None
    if room_type == "Trade" and layout is not None:
        order_ctx = compute_trade_order_limit(
            operators, layout, control_operators or [],
        )

    # 第三步：效率加成型联动（仅非归零干员的个人效率参与计算）
    total += integrate_segments(synergy_faction_room(non_zero_ops, room_type, product, T), T)
    total += integrate_segments(synergy_skill_count(non_zero_ops, room_type, alias, T), T)

    # 设施属性类联动不受归零影响——游戏描述"不包含根据设施数量提供加成的生产力"
    total += integrate_segments(synergy_trade_gold_lines(
        operators, room_type, product, layout, T=T,
    ), T)
    total += integrate_segments(synergy_facility_count(
        operators, room_type, product, layout, T=T,
    ), T)

    # Trade 站专属联动
    total += integrate_segments(synergy_trade_pair(operators, room_type, T), T)
    total += integrate_segments(synergy_trade_share(operators, room_type, T), T)
    if order_ctx is not None:
        total += integrate_segments(
            synergy_swires_order_limit(operators, room_type, order_ctx, T), T,
        )
        total += integrate_segments(
            synergy_degenbrecher_order_limit(operators, room_type, order_ctx, T), T,
        )

    # 第四步：归零加成自身的效率段
    total += integrate_segments(auto_segs, T)
    total += integrate_segments(whisper_segs, T)
    total += integrate_segments(zero_segs, T)

    total += ctrl_per_op_bonus * T

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
    # 仓库容量→效率：容量是房间属性，不受归零影响
    total += integrate_segments(synergy_capacity_to_eff(operators, room_type, product, T), T)

    # 效率放大器（仅未归零干员的效率参与计算）
    total += integrate_segments(synergy_efficiency_amplifier(non_zero_ops, room_type, product, T), T)

    # 贸易站效率→效率放大器（雪雉天道酬勤）
    if room_type == "Trade":
        total += integrate_segments(
            synergy_trade_efficiency_amplifier(operators, room_type, total / T, T), T,
        )

    # 机械精通：作业平台数量是设施属性，不受归零影响
    total += integrate_segments(synergy_token_prod(operators, room_type, product, power_platforms, T), T)

    # A7 孑订单压缩机制
    if control_operators is not None and room_type == "Trade":
        total += integrate_segments(
            synergy_jie_order(non_zero_ops, room_type, control_operators, T, order_ctx=order_ctx), T,
        )

    # B7 跨房间配对
    if all_assignments is not None:
        total += integrate_segments(
            synergy_cross_room_pair(non_zero_ops, room_type, product, all_assignments, T), T,
        )
        if room_type == "Trade":
            total += integrate_segments(
                synergy_trade_conditional_eff(operators, room_type, all_assignments, T), T,
            )

    # B8 设施 group 计数加成（真言精英小队/凯尔希异格/风絮岁等）
    if all_assignments is not None:
        total += integrate_segments(
            synergy_facility_group(non_zero_ops, room_type, all_assignments, T), T,
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
