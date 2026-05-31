"""Phase B: 贸易站穷举 + 联合分配 + 机会成本

从 exhaust_trade.py 提取核心逻辑，适配 SlotContext。
新增：whisper 机会成本修正、双房间联合最优分配（替代贪心）。
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

if TYPE_CHECKING:
    from steward_core.models import Operator
    from steward_core.mood_flow import MoodContext

_LAYOUT_243 = LayoutConfig.layout_243()

_WHISPER_BUFF_PREFIX = "trade_ord_vodfox"
_ORDER_MECHANISM_PREFIXES = (
    "trade_ord_law", "trade_ord_long", "trade_ord_closure",
    _WHISPER_BUFF_PREFIX, "trade_ord_limit_count",
)


def phase_trade(
    ctx: "SlotContext",
    window_idx: int = 0,
    mood_ctx: "MoodContext | None" = None,
) -> None:
    """执行贸易站穷举分配

    1. 构建候选池（含订单机制干员 + 联动使能者）
    2. 生成 C(n,3) 组合并评分
    3. whisper 组合扣除机会成本
    4. 联合最优分配（2间 × 3人 非重叠配对）
    5. 写入 ctx
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

    office_perception = params.office_perception_base if params else 20

    base_buff_pool = compute_buff_pool(
        ctrl_ops,
        suich_count=params.suich_count if params else 5,
        dorm_operators=[o for o in dorm_ops_list if o],
        dorm_level=params.dorm_level if params else 5,
        layout=ctx.layout if ctx.layout else _LAYOUT_243,
        perception_from_office=office_perception,
    )

    _EBEN_NAME = "黑键"
    _WUYOU_NAME = "乌有"
    _ROS_NAME = "迷迭香"

    mfg_names = ctx.ops_of_type(window_idx, "Mfg")
    has_rosmontis_in_mfg = _ROS_NAME in mfg_names

    power_modifier_names = {
        op.name for op in ctx.operators if _has_power_count_modifier(op)
    }
    effective_power = BASE_POWER_COUNT + len(
        power_modifier_names - assigned_names
    )

    evaluated = []
    whisper_combos = []

    for combo_ops in combos:
        combo_names = [op.name for op in combo_ops]
        has_eben = any(op.name == _EBEN_NAME for op in combo_ops)
        has_wuyou = any(op.name == _WUYOU_NAME for op in combo_ops)
        if has_eben or has_wuyou:
            combo_pool = compute_buff_pool(
                ctrl_ops,
                suich_count=params.suich_count if params else 5,
                dorm_operators=[o for o in dorm_ops_list if o],
                dorm_level=params.dorm_level if params else 5,
                layout=ctx.layout if ctx.layout else _LAYOUT_243,
                perception_from_office=office_perception,
                has_rosmontis_in_mfg=has_rosmontis_in_mfg,
                has_ebnhlz_in_trade=has_eben,
                has_wuyou_in_trade=has_wuyou,
            )
        else:
            combo_pool = base_buff_pool

        ctrl_bonus = control_per_operator_bonus(
            ctrl_ops, combo_ops, "Money", room_type="Trade",
        )
        eff_int = evaluate_room(
            combo_ops, "Trade", "Money", effective_power,
            shift_hours, global_bonus, combo_pool,
            ctrl_per_op_bonus=ctrl_bonus,
            all_operators=ctx.operators,
            control_operators=ctrl_ops,
            mood_ctx=mood_ctx,
        )
        n = len(combo_ops)
        efficiency_integrated = shift_hours * (1.0 + 0.01 * n) + eff_int / 100.0
        lmd_per_day, _gold, _equiv = _get_trade_order_multiplier(
            combo_ops, shift_hours,
        )
        lmd = efficiency_integrated / 24.0 * lmd_per_day

        lambda_penalty = sum(
            ctx.lambda_ops.get(name, 0.0) for name in combo_names
        ) * shift_hours
        lmd -= lambda_penalty

        is_whisper = _has_whisper(combo_ops)
        if is_whisper:
            whisper_combos.append((lmd, combo_names, _zeroed_efficiency_sum(combo_ops)))

        evaluated.append((lmd, combo_names))

    if whisper_combos:
        evaluated = _apply_whisper_opportunity(evaluated, whisper_combos, pool, shift_hours)

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


def _has_whisper(combo_ops: list) -> bool:
    """检查组合中是否含低语技能干员（巫恋）"""
    for op in combo_ops:
        for sk in op.skills:
            if sk.buff_id.startswith(_WHISPER_BUFF_PREFIX):
                return True
    return False


def _zeroed_efficiency_sum(combo_ops: list) -> float:
    """被归零干员的个人效率总和（Trade）"""
    total = 0.0
    for op in combo_ops:
        has_whisper = any(
            sk.buff_id.startswith(_WHISPER_BUFF_PREFIX) for sk in op.skills
        )
        if has_whisper:
            continue
        total += max(op.best_efficiency("Trade", "Money"), 0.0)
    return total


def _apply_whisper_opportunity(
    evaluated: list,
    whisper_combos: list,
    pool: list,
    shift_hours: float,
) -> list:
    """对 whisper 组合应用机会成本扣减

    归零干员的替代价值正比于其个人最佳 Trade 效率。
    公式: adjusted_cost * TRADE_BASE_LMD_PER_HOUR * shift_hours / 100
    TRADE_BASE_LMD_PER_HOUR = 10265/24 ≈ 427.7 LMD/h（日 LMD 基准 ÷ 24）
    """
    _TRADE_BASE = 10265.0 / 24.0

    whisper_min_cost = min(cost for _, _, cost in whisper_combos) if whisper_combos else 0.0

    result = []
    for i, (lmd, names) in enumerate(evaluated):
        is_whisper = False
        for _, w_names, cost in whisper_combos:
            if w_names == names:
                adjusted_cost = max(cost - whisper_min_cost, 0.0)
                penalty = adjusted_cost * _TRADE_BASE * shift_hours / 100.0
                lmd = lmd - penalty
                is_whisper = True
                break
        result.append((lmd, names))

    return result


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
