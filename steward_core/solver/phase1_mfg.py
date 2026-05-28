"""Phase 1: 制造站穷举（CR 2间 + PG 2间）"""

from steward_core.models import Operator, RoomAssignment
from steward_core.synergy import classify_mfg_operators, build_candidate_pool, get_synergy_enablers

from .greed import _generate_combos, _greedy_allocate_with_support
from .support import _evaluate_with_support


def _phase1_mfg(
    operators: list[Operator],
    assigned_ids: set[str],
    assigned_names: set[str],
    assignments: list,
    op_lookup: dict[str, Operator],
    locked_support: dict[str, set[str]],
    anchor_names: set[str],
) -> int:
    """Phase 1: 制造站穷举（CR 2间 + PG 2间）

    共享 assigned_ids 防跨产物冲突。
    返回本阶段新增的 autofill_count。
    """
    autofill_count = 0

    for product, count in [("CombatRecord", 2), ("PureGold", 2)]:
        mfg_ops = [op for op in operators if op.has_skill_for("Mfg", product)]
        if not mfg_ops:
            for i in range(count):
                assignments.append(RoomAssignment(
                    room_type="Mfg", room_index=len(assignments),
                    operators=[], product=product, autofill=True,
                ))
                autofill_count += 1
            continue

        classification = classify_mfg_operators(mfg_ops, product, anchor_names)
        pool = build_candidate_pool(mfg_ops, classification, room_type="Mfg", product=product)
        pool = [op for op in pool if op.char_id not in assigned_ids]
        # 补充 Mfg 联动使能者（无 Mfg 技能但能提升 A2 阵营计数的干员，如芙蓉→历阵锐枪芬）
        existing = {op.char_id for op in pool}
        for enabler in get_synergy_enablers(operators, "Mfg", product):
            if enabler.char_id not in existing and enabler.char_id not in assigned_ids:
                pool.append(enabler)
        combos = _generate_combos(pool, 3)

        # 评估所有组合（含最优支撑）
        evaluated = []
        for combo_ops in combos:
            score, support_map = _evaluate_with_support(
                combo_ops, "Mfg", product, operators, assigned_names,
            )
            combo_names = [op.name for op in combo_ops]
            all_support_names = [n for names in support_map.values() for n in names]
            evaluated.append((score, combo_names, all_support_names, support_map))
        evaluated.sort(key=lambda x: -x[0])

        # 贪心分配（含支撑干员锁，中枢容量跨产物轮次共享）
        allocated = _greedy_allocate_with_support(
            evaluated, room_count=count,
            initial_control=locked_support["Control"].copy(),
        )
        for names, support_map in allocated:
            for op in pool:
                if op.name in names:
                    assigned_ids.add(op.char_id)
                    assigned_names.add(op.name)
            # 锁定支撑干员
            for facility, s_names in support_map.items():
                locked_support[facility].update(s_names)
                for n in s_names:
                    if n in op_lookup:
                        assigned_ids.add(op_lookup[n].char_id)
                        assigned_names.add(n)
            assignments.append(RoomAssignment(
                room_type="Mfg",
                room_index=len([a for a in assignments if a.room_type == "Mfg"]),
                operators=names, product=product,
            ))

        if len(allocated) < count:
            for _ in range(count - len(allocated)):
                assignments.append(RoomAssignment(
                    room_type="Mfg",
                    room_index=len([a for a in assignments if a.room_type == "Mfg"]),
                    operators=[], product=product, autofill=True,
                ))
                autofill_count += 1

    return autofill_count
