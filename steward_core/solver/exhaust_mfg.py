"""制造站穷举（CR 2间 + PG 2间）"""

from steward_core.constants import BASE_POWER_COUNT
from steward_core.models import Operator, RoomAssignment, LayoutConfig
from steward_core.synergy import classify_mfg_operators, build_candidate_pool, get_synergy_enablers
from steward_core.synergy.facility_linkages import _has_power_count_modifier
from steward_core.synergy.helpers import _is_knight, _PINUS_GROUP, _B_ROSEMARY, _DURIN_NAMES
from steward_core.synergy.buff_pool import compute_buff_pool

from .config import SolverConfig
from .global_state import GlobalState
from .greed import _generate_combos, _greedy_allocate_with_support
from .support import _evaluate_with_support, compute_optimal_support


def _rough_mfg_score(combo_ops: list[Operator], product: str) -> float:
    """制造站组合快速粗评分：个人基础效率 + 关键联动红利

    仅扫描 combo 内部成员（O(3)），不涉及全量干员或联动链展开。
    用于在精评前过滤掉绝大多数低潜力组合。
    """
    score = 0.0
    names = {op.name for op in combo_ops}

    for op in combo_ops:
        score += op.best_efficiency("Mfg", product)

    if _B_ROSEMARY in names:
        score += 200
    if any(_is_knight(op) for op in combo_ops):
        score += 100
    if any(op.group_id == _PINUS_GROUP for op in combo_ops):
        score += 40
    if any(op.name in _DURIN_NAMES for op in combo_ops):
        score += 50

    return score


def exhaust_mfg(
    operators: list[Operator],
    assigned_ids: set[str],
    assigned_names: set[str],
    assignments: list,
    op_lookup: dict[str, Operator],
    locked_support: dict[str, set[str]],
    *,
    anchor_names: set[str],
    config: SolverConfig | None = None,
    override_pool=None,
) -> int:
    """Phase 1: 制造站穷举（CR 2间 + PG 2间）

    共享 assigned_ids 防跨产物冲突。
    返回本阶段新增的 autofill_count。
    """
    autofill_count = 0

    # 全局状态跨产物共享——CR 消耗的包余量在 PG 评分中体现为惩罚
    use_global = config.global_state_scoring if config else False
    gs = GlobalState.for_layout_243() if use_global else None

    # 预计算：发电站修改器干员名集合（避免每组合全量扫描 ~300 干员）
    power_modifier_names = {op.name for op in operators if _has_power_count_modifier(op)}

    for product, count in [("CombatRecord", 2), ("PureGold", 2)]:
        # 预计算有效发电站数（本产物阶段 assigned_names 不变，一次计算即可）
        effective_power = BASE_POWER_COUNT + len(power_modifier_names - assigned_names)
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

        keep_top = config.params.rough_score_keep_top if config else 0
        if keep_top > 0 and len(combos) > keep_top:
            rough_scored = [(_rough_mfg_score(c, product), i) for i, c in enumerate(combos)]
            rough_scored.sort(key=lambda x: -x[0])
            combos_to_eval = [combos[i] for _, i in rough_scored[:keep_top]]
        else:
            combos_to_eval = combos

        # 评估所有组合（含最优支撑）
        # 预计算不含 combo 特定标志的 base_pool（多数组合共享）
        base_pool = compute_buff_pool(
            [], suich_count=config.params.suich_count,
            dorm_operators=[], dorm_level=config.params.dorm_level,
            has_rosmontis_in_mfg=False,
            layout=LayoutConfig.layout_243(),
        )
        evaluated = []
        for combo_ops in combos_to_eval:
            has_rosmontis = any(op.name == _B_ROSEMARY for op in combo_ops)
            score, support_map = _evaluate_with_support(
                combo_ops, "Mfg", product, operators, assigned_names,
                params=config.params,
                op_lookup=op_lookup,
                effective_power=effective_power,
                override_pool=override_pool if override_pool is not None else (
                    base_pool if not has_rosmontis else None
                ),
                mood_ctx=config.mood_ctx,
            )
            combo_names = [op.name for op in combo_ops]
            all_support_names = [n for names in support_map.values() for n in names]

            # 全局状态评分修正：稀缺包消耗越多惩罚越重
            if use_global:
                bundles = compute_optimal_support(combo_ops).bundles
                alpha = config.params.global_state_alpha if config else 0.3
                penalty = gs.scarcity_penalty(bundles, alpha=alpha)
                score -= penalty

            evaluated.append((score, combo_names, all_support_names, support_map))
        evaluated.sort(key=lambda x: -x[0])

        # 贪心分配（含支撑干员锁，中枢容量跨产物轮次共享）
        allocated = _greedy_allocate_with_support(
            evaluated, room_count=count,
            initial_control=locked_support["Control"].copy(),
            config=config,
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
            # 全局状态：消耗已分配 combo 的包余量
            if use_global:
                allocated_bundles = compute_optimal_support(
                    [op_lookup[n] for n in names if n in op_lookup]
                ).bundles
                gs.allocate(allocated_bundles)
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
