"""Phase B: 贸易站穷举 + 联合分配

从 exhaust_trade.py 提取核心逻辑，适配 SlotContext。
whisper 机会成本修正已迁移至 opportunity.py，在评分循环内联调用。
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from steward_core.constants import BASE_POWER_COUNT
from steward_core.models import LayoutConfig
from steward_core.production import _get_trade_order_multiplier
from steward_core.synergy import (
    classify_trade_operators,
    build_candidate_pool,
    get_synergy_enablers,
    compute_control_global_bonus,
    control_per_operator_bonus,
)
from steward_core.synergy.facility_linkages import _has_power_count_modifier
from steward_core.synergy.buff_pool import compute_buff_pool
from steward_core.evaluate import evaluate_room
from steward_core.synergy._derived import TRADE_ANCHORS
from .context import SlotContext, mood_is_viable
from ._cold_start import cold_start_ctrl_ops, cold_start_dorm_ops
from .opportunity import compute_opportunity_cost_lmd

if TYPE_CHECKING:
    from steward_core.models import Operator
    from steward_core.mood_flow import MoodContext

_LAYOUT_243 = LayoutConfig.layout_243()

_ORDER_MECHANISM_PREFIXES = (
    "trade_ord_law", "trade_ord_long", "trade_ord_closure",
    "trade_ord_vodfox", "trade_ord_limit_count",
    "trade_ord_pepe",
)


def phase_trade(
    ctx: "SlotContext",
    window_idx: int = 0,
    mood_ctx: "MoodContext | None" = None,
) -> None:
    """执行贸易站穷举分配

    1. 构建候选池（含订单机制干员 + 联动使能者）
    2. 生成 C(n,3) 组合并评分（含机会成本）
    3. 联合最优分配（2间 × 3人 非重叠配对）
    4. 写入 ctx
    """
    assigned_ids = ctx.assigned_ids(window_idx)
    assigned_names = ctx.assigned_names(window_idx)

    params = ctx.params
    mood_threshold = params.mood_work_threshold if params else 0.0

    trade_ops = [
        op for op in ctx.operators
        if op.char_id not in assigned_ids
        and op.has_skill_for("Trade", "Money")
        and mood_is_viable(op.name, mood_ctx, mood_threshold)
    ]
    for op in ctx.operators:
        if op.char_id in assigned_ids or op in trade_ops:
            continue
        if not mood_is_viable(op.name, mood_ctx, mood_threshold):
            continue
        if any(
            s.buff_id.startswith(_ORDER_MECHANISM_PREFIXES) for s in op.skills
        ):
            trade_ops.append(op)

    if not trade_ops:
        return

    classification = classify_trade_operators(trade_ops, TRADE_ANCHORS)
    pool = build_candidate_pool(
        trade_ops, classification, room_type="Trade", product="Money",
    )
    pool = [op for op in pool if op.char_id not in assigned_ids]

    existing = {op.char_id for op in pool}
    for enabler in get_synergy_enablers(ctx.operators, "Trade", "Money"):
        if enabler.char_id not in existing and enabler.char_id not in assigned_ids:
            pool.append(enabler)

    if not pool:
        return

    combos = [list(c) for c in itertools.combinations(pool, min(3, len(pool)))]
    if not combos:
        return

    shift_hours = params.shift_hours if params else 12.0

    ctrl_names = ctx.ops_of_type(window_idx, "Control")
    ctrl_ops = [ctx.op_lookup[n] for n in ctrl_names if n in ctx.op_lookup]
    if not ctrl_ops:
        ctrl_ops = cold_start_ctrl_ops(ctx, window_idx)
    global_bonus = compute_control_global_bonus(ctrl_ops)

    dorm_names = ctx.ops_of_type(window_idx, "Dormitory")
    dorm_ops_list = [ctx.op_lookup[n] for n in dorm_names if n in ctx.op_lookup]
    if not dorm_ops_list:
        dorm_ops_list = cold_start_dorm_ops(ctx, window_idx)

    mfg_names = ctx.ops_of_type(window_idx, "Mfg")
    mfg_combo_ops = [ctx.op_lookup[n] for n in mfg_names if n in ctx.op_lookup]

    office_names = ctx.ops_of_type(window_idx, "Office")
    office_ops = [ctx.op_lookup[n] for n in office_names if n in ctx.op_lookup]

    power_modifier_names = {
        op.name for op in ctx.operators if _has_power_count_modifier(op)
    }
    effective_power = BASE_POWER_COUNT + len(
        power_modifier_names - assigned_names
    )

    evaluated = []

    for combo_ops in combos:
        combo_names = [op.name for op in combo_ops]
        combo_pool = compute_buff_pool(
            ctrl_ops,
            suich_count=params.suich_count if params else 5,
            dorm_operators=[o for o in dorm_ops_list if o],
            dorm_level=params.dorm_level if params else 5,
            layout=ctx.layout if ctx.layout else _LAYOUT_243,
            mfg_operators=mfg_combo_ops,
            trade_operators=combo_ops,
            office_operators=office_ops,
            office_perception_base=params.office_perception_base if params else 20,
        )

        ctrl_bonus = control_per_operator_bonus(
            ctrl_ops, combo_ops, "Money", room_type="Trade",
        )
        eff_int = evaluate_room(
            combo_ops, "Trade", "Money", effective_power,
            shift_hours, global_bonus, combo_pool,
            ctrl_per_op_bonus=ctrl_bonus,
            all_operators=ctx.operators,
            control_operators=ctrl_ops,
            all_assignments=ctx.build_all_assignments(window_idx),
            mood_ctx=mood_ctx,
        )
        n = len(combo_ops)
        efficiency_integrated = shift_hours * (1.0 + 0.01 * n) + eff_int / 100.0
        lmd_per_day, _gold, _equiv = _get_trade_order_multiplier(
            combo_ops, shift_hours,
        )

        from steward_core.synergy.trade_linkages import get_active_override
        override = get_active_override(combo_ops)
        if override is not None and override.no_efficiency:
            lmd = shift_hours / 24.0 * lmd_per_day
        else:
            lmd = efficiency_integrated / 24.0 * lmd_per_day

        if override is None:
            lmd -= compute_opportunity_cost_lmd(combo_ops, "Trade", "Money", shift_hours)

        evaluated.append((lmd, combo_names))

        for combo_op in combo_ops:
            eff_pct = max((sk.efficient.raw.get("all", 0) for sk in combo_op.skills), default=0.0)
            if eff_pct > 0:
                ctx.op_peak_eff[combo_op.name] = max(ctx.op_peak_eff.get(combo_op.name, 0.0), eff_pct)

    evaluated.sort(key=lambda x: -x[0])

    allocated = _joint_allocate(evaluated, room_count=2)

    trade_room_indices = [
        room.room_index
        for room in ctx.layout.rooms
        if room.room_type == "Trade"
    ]

    for room_idx, names in enumerate(allocated):
        actual_idx = trade_room_indices[room_idx]
        for i, name in enumerate(names):
            slot_id = f"trade_{actual_idx}_{i}"
            ctx.place(window_idx, slot_id, name)


def _joint_allocate(
    evaluated: list[tuple[float, list[str]]],
    room_count: int,
) -> list[list[str]]:
    """联合最优分配：枚举所有非重叠房间配对，取总分最高

    对于 room_count=2 的场景，枚举所有 C(n,3)×C(n-3,3) 配对取最优。
    若组合数过大则退化为贪心。
    """
    if len(evaluated) <= 100:
        best_total = -1.0
        best_pair = None
        for i in range(len(evaluated)):
            s1, n1 = evaluated[i]
            n1_set = set(n1)
            for j in range(i + 1, len(evaluated)):
                s2, n2 = evaluated[j]
                if n1_set.isdisjoint(n2):
                    total = s1 + s2
                    if total > best_total:
                        best_total = total
                        best_pair = (n1, n2)
        if best_pair:
            return [list(best_pair[0]), list(best_pair[1])]

    taken = set()
    result = []
    for _score, names in evaluated:
        if any(n in taken for n in names):
            continue
        result.append(names)
        taken.update(names)
        if len(result) >= room_count:
            break
    return result
