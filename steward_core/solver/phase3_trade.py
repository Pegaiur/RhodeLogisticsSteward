"""Phase 3a: 贸易站穷举"""

from steward_core.constants import BASE_POWER_COUNT
from steward_core.models import Operator, RoomAssignment
from steward_core.synergy import (
    compute_control_global_bonus,
    compute_buff_pool,
    _has_power_count_modifier,
    get_system_contributors,
    classify_trade_operators, build_candidate_pool,
    control_per_operator_bonus,
    get_synergy_enablers,
)

from .greed import _generate_combos, _greedy_allocate, _evaluate_trade_combo, T


def _phase3_trade(
    operators: list[Operator],
    assigned_ids: set[str],
    assigned_names: set[str],
    assignments: list,
    op_lookup: dict[str, Operator],
    locked_support: dict[str, set[str]],
    ctrl_names: list[str],
) -> int:
    """Phase 3a: Trade 穷举（与 Mfg 同架构）

    返回本阶段新增的 autofill_count。
    """
    autofill_count = 0

    # 释放 locked Trade 支撑干员（已在 Phase 1 锁入 assigned_ids 但尚未写入房间）
    for name in locked_support["Trade"]:
        if name in op_lookup:
            assigned_ids.discard(op_lookup[name].char_id)
            assigned_names.discard(name)

    trade_ops = [op for op in operators if op.char_id not in assigned_ids
                 and op.has_skill_for("Trade", "Money")]
    # 订单机制干员 has_skill_for 可能为 False，补充加入
    for op in operators:
        if op.char_id in assigned_ids:
            continue
        if op in trade_ops:
            continue
        if any(s.buff_id.startswith(("trade_ord_law", "trade_ord_long",
                                      "trade_ord_closure", "trade_ord_vodfox", "trade_ord_limit_count"))
               for s in op.skills):
            trade_ops.append(op)

    if trade_ops:
        TRADE_ANCHOR_NAMES = set(get_system_contributors("Trade", "anchor"))
        classification = classify_trade_operators(trade_ops, TRADE_ANCHOR_NAMES)
        pool = build_candidate_pool(trade_ops, classification, room_type="Trade", product="Money")
        pool = [op for op in pool if op.char_id not in assigned_ids]
        # 补充 Trade 联动使能者（无 Trade 技能但能提升 A2 阵营计数的干员，如推王→摩根）
        existing = {op.char_id for op in pool}
        for enabler in get_synergy_enablers(operators, "Trade", "Money"):
            if enabler.char_id not in existing and enabler.char_id not in assigned_ids:
                pool.append(enabler)
        combos = _generate_combos(pool, min(3, len(pool)))

        # 构建全局上下文（Phase 2 中枢已确定）
        ctrl_ops = [op_lookup[n] for n in ctrl_names if n in op_lookup]
        global_bonus = compute_control_global_bonus(ctrl_ops)
        effective_power = BASE_POWER_COUNT + sum(
            1 for op in operators if op.name not in assigned_names
            and _has_power_count_modifier(op)
        )

        # 评估所有组合（含宿舍估计用于乌有烟火/黑键感知等B1生成）
        estimated_dorm_count = 20
        dorm_est = [Operator(char_id=f"_dorm_{i}", name=f"填位宿舍{i}", skills=[])
                    for i in range(estimated_dorm_count)]
        has_ebnhlz_any = "黑键" in locked_support["Trade"]

        evaluated = []
        for combo_ops in combos:
            combo_names = [op.name for op in combo_ops]
            has_wuyou = "乌有" in combo_names
            has_ebnhlz = has_ebnhlz_any or "黑键" in combo_names
            ctrl_bonus = control_per_operator_bonus(
                ctrl_ops, combo_ops, "Money", room_type="Trade",
            )
            lmd = _evaluate_trade_combo(
                combo_ops, effective_power, T, global_bonus,
                compute_buff_pool(
                    ctrl_ops, suich_count=5,
                    dorm_operators=dorm_est, dorm_level=5,
                    has_ebnhlz_in_trade=has_ebnhlz,
                    has_wuyou_in_trade=has_wuyou,
                ), ctrl_bonus,
                all_operators=operators,
                control_operators=ctrl_ops,
            )
            evaluated.append((lmd, combo_names))
        evaluated.sort(key=lambda x: -x[0])

        # 贪心分配（2 间 Trade）
        allocated = _greedy_allocate(evaluated, room_count=2)
        for names in allocated:
            for op in pool:
                if op.name in names:
                    assigned_ids.add(op.char_id)
                    assigned_names.add(op.name)
            room_idx = len([a for a in assignments if a.room_type == "Trade"])
            assignments.append(RoomAssignment(
                room_type="Trade", room_index=room_idx,
                operators=names, product="Money",
            ))
        if len(allocated) < 2:
            for _ in range(2 - len(allocated)):
                assignments.append(RoomAssignment(
                    room_type="Trade",
                    room_index=len([a for a in assignments if a.room_type == "Trade"]),
                    operators=[], product="Money", autofill=True,
                ))
                autofill_count += 1
    else:
        for i in range(2):
            assignments.append(RoomAssignment(
                room_type="Trade", room_index=i,
                operators=[], product="Money", autofill=True,
            ))
            autofill_count += 1

    return autofill_count
