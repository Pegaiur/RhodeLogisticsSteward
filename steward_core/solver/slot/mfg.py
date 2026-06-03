"""Phase A: 制造站穷举（CR 2间 + PG 2间）

从 exhaust_mfg.py 提取核心穷举逻辑，适配 SlotContext。
支撑需求不再在此阶段计算——改由 D[d]-based contribution 在 Phase C/D 处理。
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from steward_core.constants import BASE_POWER_COUNT, MFG_CR_BASE_RATE, MFG_PG_BASE_RATE, CR_EXP_PER_UNIT, PG_LMD_PER_UNIT, XP_LMD_RATIO
from steward_core.models import LayoutConfig
from steward_core.synergy import (
    classify_mfg_operators,
    build_candidate_pool,
    get_synergy_enablers,
    compute_control_global_bonus,
    control_per_operator_bonus,
)
from steward_core.synergy._derived import MFG_ANCHORS
from steward_core.synergy.facility_linkages import _has_power_count_modifier
from steward_core.synergy.buff_pool import compute_buff_pool
from steward_core.evaluate import evaluate_room
from .context import SlotContext, mood_is_viable
from ._cold_start import cold_start_ctrl_ops, cold_start_dorm_ops
from .opportunity import compute_opportunity_cost_lmd

if TYPE_CHECKING:
    from steward_core.models import Operator
    from steward_core.mood_flow import MoodContext

_LAYOUT_243 = LayoutConfig.layout_243()

_CR_LMD_PER_UNIT = CR_EXP_PER_UNIT / XP_LMD_RATIO
_PG_LMD_PER_UNIT = PG_LMD_PER_UNIT

_LAMBDA_EFF_SCALE = {
    "CombatRecord": MFG_CR_BASE_RATE * _CR_LMD_PER_UNIT / 100.0,
    "PureGold": MFG_PG_BASE_RATE * _PG_LMD_PER_UNIT / 100.0,
}
"""机会成本从 LMD 到效率积分域的换算系数（原用于 lambda 惩罚，现仅用于机会成本）"""


def phase_mfg(
    ctx: "SlotContext",
    window_idx: int = 0,
    mood_ctx: "MoodContext | None" = None,
) -> None:
    """执行制造站穷举分配

    对 CombatRecord(2间) 和 PureGold(2间) 分别：
    1. 构建候选池（含联动使能者）
    2. 生成 C(n,3) 组合
    3. 基于当前 ctx 中的 Control/Dorm 计算 buff_pool
    4. evaluate_room 评分 + 机会成本扣减
    5. 贪心分配并写入 ctx
    """
    assigned_ids = ctx.assigned_ids(window_idx)
    assigned_names = ctx.assigned_names(window_idx)

    power_modifier_names = {
        op.name for op in ctx.operators if _has_power_count_modifier(op)
    }

    params = ctx.params
    shift_hours = params.shift_hours if params else 12.0
    mood_threshold = params.mood_work_threshold if params else 0.0

    for product, count in [("CombatRecord", 2), ("PureGold", 2)]:
        effective_power = (params.base_power_count if params else BASE_POWER_COUNT) + len(
            power_modifier_names - assigned_names
        )

        mfg_ops = [
            op for op in ctx.operators
            if op.char_id not in assigned_ids
            and op.has_skill_for("Mfg", product)
            and mood_is_viable(op.name, mood_ctx, mood_threshold)
        ]
        if not mfg_ops:
            continue

        classification = classify_mfg_operators(mfg_ops, product, MFG_ANCHORS)
        pool = build_candidate_pool(
            mfg_ops, classification, room_type="Mfg", product=product,
        )
        pool = [op for op in pool if op.char_id not in assigned_ids]

        existing = {op.char_id for op in pool}
        for enabler in get_synergy_enablers(ctx.operators, "Mfg", product):
            if enabler.char_id not in existing and enabler.char_id not in assigned_ids:
                pool.append(enabler)

        combos = [list(c) for c in itertools.combinations(pool, min(3, len(pool)))]
        if not combos:
            continue

        ctrl_names = ctx.ops_of_type(window_idx, "Control")
        ctrl_ops = [ctx.op_lookup[n] for n in ctrl_names if n in ctx.op_lookup]
        if not ctrl_ops:
            ctrl_ops = cold_start_ctrl_ops(ctx, window_idx)
        global_bonus = compute_control_global_bonus(ctrl_ops)

        dorm_names = ctx.ops_of_type(window_idx, "Dormitory")
        dorm_ops_list = [ctx.op_lookup[n] for n in dorm_names if n in ctx.op_lookup]
        if not dorm_ops_list:
            dorm_ops_list = cold_start_dorm_ops(ctx, window_idx)

        office_names = ctx.ops_of_type(window_idx, "Office")
        office_ops = [ctx.op_lookup[n] for n in office_names if n in ctx.op_lookup]

        evaluated = []
        for combo_ops in combos:
            combo_pool = compute_buff_pool(
                ctrl_ops,
                suich_count=params.suich_count if params else 5,
                dorm_operators=[o for o in dorm_ops_list if o],
                dorm_level=params.dorm_level if params else 5,
                layout=ctx.layout if ctx.layout else _LAYOUT_243,
                mfg_operators=combo_ops,
                office_operators=office_ops,
                office_perception_base=params.office_perception_base if params else 20,
            )

            ctrl_bonus = control_per_operator_bonus(
                ctrl_ops, combo_ops, product, room_type="Mfg",
            )
            score = evaluate_room(
                combo_ops, "Mfg", product, effective_power,
                shift_hours, global_bonus, combo_pool,
                ctrl_per_op_bonus=ctrl_bonus,
                all_operators=ctx.operators,
                control_operators=ctrl_ops,
                all_assignments=ctx.build_all_assignments(window_idx),
                mood_ctx=mood_ctx,
            )
            combo_names = [op.name for op in combo_ops]
            # LMD 往返对消：opportunity.py LMD ÷ _LAMBDA_EFF_SCALE = cost_pct × shift_hours
            score -= compute_opportunity_cost_lmd(
                combo_ops, "Mfg", product, shift_hours,
            ) / _LAMBDA_EFF_SCALE.get(product, 2.5)

            evaluated.append((score, combo_names))

            for combo_op in combo_ops:
                eff_pct = max((sk.efficient.raw.get("all", 0) for sk in combo_op.skills), default=0.0)
                if eff_pct > 0:
                    ctx.op_peak_eff[combo_op.name] = max(ctx.op_peak_eff.get(combo_op.name, 0.0), eff_pct)

        evaluated.sort(key=lambda x: -x[0])

        mfg_room_indices = [
            room.room_index
            for room in ctx.layout.rooms
            if room.room_type == "Mfg" and room.product == product
        ]
        allocated_rooms = 0
        taken_names: set[str] = set()

        for _score, names in evaluated:
            if any(n in taken_names for n in names):
                continue
            if allocated_rooms >= count:
                break

            room_idx = mfg_room_indices[allocated_rooms]
            for i, name in enumerate(names):
                slot_id = f"mfg_{room_idx}_{i}"
                ctx.place(window_idx, slot_id, name)

            taken_names.update(names)
            assigned_ids.update(
                ctx.op_lookup[n].char_id for n in names if n in ctx.op_lookup
            )
            assigned_names.update(names)
            allocated_rooms += 1
