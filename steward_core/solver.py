"""排班求解器

MV3: 制造站穷举(含联动) + 剪枝 + 贪心分配。
剩余设施（Trade/Power/Reception/Office）用支配偏序贪心。
Control 固定为社区最优方案。
"""

import itertools
from dataclasses import dataclass, field
from typing import Optional

from steward_core.models import LayoutConfig, Operator, RoomAssignment, RoomConfig, ShiftPlan, SolveResult
from steward_core.efficiency_fn import constant_efficiency, integrate_segments, rank_by_dominance
from steward_core.synergy import (
    synergy_pair, synergy_skill_count, synergy_skill_alias, synergy_automation,
    synergy_facility_count, synergy_buff_pool_consumer, _skill_class,
    GlobalBonus, compute_control_global_bonus,
    compute_buff_pool,
)

T = 12.0
POWER_COUNT = 3
FIXED_CONTROL = ["令", "重岳", "夕", "凯尔希", "焰尾"]

ANCHOR_NAMES = {
    "水月", "多萝西", "苍苔", "海沫",
    "森蚺", "温蒂", "掠风", "异客",
    "阿兰娜", "Miss.Christine", "怒潮凛冬",
}


# ─── 角色分类 ───────────────────────────────────────────────────

@dataclass
class MfgClassification:
    pure_efficiency: list[Operator] = field(default_factory=list)
    anchors: list[Operator] = field(default_factory=list)
    providers: list[Operator] = field(default_factory=list)


def _classify_mfg_operators(
    operators: list[Operator], product: str,
) -> MfgClassification:
    """将制造站干员分类为 纯效率/联动锚点/技能提供者"""
    result = MfgClassification()
    for op in operators:
        is_anchor = op.name in ANCHOR_NAMES

        has_skill_label = False
        for sk in op.skills:
            if sk.room_type != "Mfg":
                continue
            if _skill_class(sk.buff_name):
                has_skill_label = True
                break

        if is_anchor:
            result.anchors.append(op)
        elif has_skill_label:
            result.providers.append(op)
        else:
            result.pure_efficiency.append(op)

    return result


def _prune_equivalent(pure_ops: list[Operator], top_k: int = 3) -> list[Operator]:
    """规则1: 等价类合并 — 纯效率只保留 top_k 名"""
    sorted_ops = sorted(pure_ops, key=lambda op: -op.best_efficiency("Mfg"))
    return sorted_ops[:top_k]


def _build_candidate_pool(
    all_ops: list[Operator], classification: MfgClassification,
) -> list[Operator]:
    """规则2: 锚点池筛选 — anchors + providers + top_k 纯效率"""
    seen = {op.char_id for op in classification.anchors}
    pool = list(classification.anchors)

    for op in classification.providers:
        if op.char_id not in seen:
            seen.add(op.char_id)
            pool.append(op)

    top_pure = _prune_equivalent(classification.pure_efficiency, top_k=5)
    for op in top_pure:
        if op.char_id not in seen:
            seen.add(op.char_id)
            pool.append(op)

    return pool


def _upper_bound_ok(total_eff: float, best_known: float, threshold: float = 0.95) -> bool:
    """规则3: 上界预判 — 总效率不低于 best_known × threshold"""
    return total_eff >= best_known * threshold


# ─── 房间评估 ───────────────────────────────────────────────────

def _evaluate_room_combo(
    operators: list[Operator],
    room_type: str,
    product: str,
    power_count: int = POWER_COUNT,
    global_bonus: GlobalBonus | None = None,
    buff_pool = None,
) -> float:
    """评估一个房间组合的 12h 总积分（含联动+全局加成+烟火）"""
    if not operators:
        return 0.0

    if global_bonus is None:
        global_bonus = GlobalBonus()

    total = 0.0

    alias = synergy_skill_alias(operators)
    total += integrate_segments(synergy_pair(operators, room_type, product), T)
    total += integrate_segments(synergy_skill_count(operators, room_type, alias), T)
    total += integrate_segments(synergy_facility_count(
        operators, room_type, product, _LAYOUT_243,
    ), T)
    auto_segs, zero_set = synergy_automation(operators, room_type, power_count)
    total += integrate_segments(auto_segs, T)

    for op in operators:
        if op.name in zero_set:
            continue
        eff = op.best_efficiency(room_type, product)
        if eff > 0:
            seg = constant_efficiency(eff, mood_burn=0.0, T=T)
            total += integrate_segments(seg, T)

    if buff_pool is not None:
        total += integrate_segments(
            synergy_buff_pool_consumer(operators, room_type, product, buff_pool), T,
        )

    if room_type == "Mfg":
        total += global_bonus.mfg_bonus * T
    elif room_type == "Trade":
        total += global_bonus.trade_bonus * T

    return total


def _generate_combos(pool: list[Operator], k: int = 3) -> list[list[Operator]]:
    """生成 k 人组合"""
    if len(pool) < k:
        return [list(pool)]
    return [list(combo) for combo in itertools.combinations(pool, k)]


# ─── 跨间贪心分配 ──────────────────────────────────────────────

def _greedy_allocate(
    evaluated: list[tuple[float, list[str]]],
    room_count: int,
) -> list[list[str]]:
    """从排序组合中贪心取无冲突的 N 间"""
    assigned = set()
    result = []
    for _score, names in evaluated:
        if any(n in assigned for n in names):
            continue
        result.append(names)
        assigned.update(names)
        if len(result) >= room_count:
            break
    return result


# ─── 剩余设施贪心 ──────────────────────────────────────────────

_LAYOUT_243 = LayoutConfig.layout_243()


def _greedy_remaining(
    assigned_ids: set[str],
    operators: list[Operator],
) -> list[RoomAssignment]:
    """剩余设施（Trade/Power/Reception/Office）支配偏序贪心"""
    results = []
    for room in _LAYOUT_243.rooms:
        if room.room_type in ("Mfg", "Control"):
            continue

        candidates = []
        for op in operators:
            if op.char_id in assigned_ids:
                continue
            if not op.has_skill_for(room.room_type, room.product):
                continue
            eff = op.best_efficiency(room.room_type, room.product)
            if eff <= 0:
                continue
            seg = constant_efficiency(eff, mood_burn=0.0, T=T)
            candidates.append((seg, op))

        if not candidates:
            results.append(RoomAssignment(
                room_type=room.room_type, room_index=room.room_index,
                operators=[], product=room.product, autofill=True,
            ))
            continue

        ranked = rank_by_dominance(candidates, T)
        taken = []
        for op in ranked:
            if len(taken) >= room.slots:
                break
            if op.char_id not in assigned_ids:
                taken.append(op.name)
                assigned_ids.add(op.char_id)

        results.append(RoomAssignment(
            room_type=room.room_type, room_index=room.room_index,
            operators=taken, product=room.product,
            autofill=len(taken) < room.slots,
        ))

    return results


# ─── 主入口 ─────────────────────────────────────────────────────

def solve_mvp(operators: list[Operator]) -> SolveResult:
    """MVP 完整求解：制造站穷举 + 剩余设施贪心

    返回 SolveResult，含一个 12h ShiftPlan。
    """
    assigned_ids: set[str] = set()
    assignments: list[RoomAssignment] = []
    autofill_count = 0

    # C1: 全局效率加成（固定中枢方案预计算）
    control_ops = [op for op in operators if op.name in FIXED_CONTROL]
    global_bonus = compute_control_global_bonus(control_ops)

    # B1: 人间烟火预计算（Phase 1 保守估计）
    buff_pool = compute_buff_pool(control_ops, suich_count=5)

    # Phase 2: 制造站穷举（CR 2间 + PG 2间）—— 共享 assigned_ids 防跨产物冲突
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

        classification = _classify_mfg_operators(mfg_ops, product)
        pool = _build_candidate_pool(mfg_ops, classification)
        # 排除已分配干员
        pool = [op for op in pool if op.char_id not in assigned_ids]
        combos = _generate_combos(pool, 3)

        # 评估所有组合
        evaluated = []
        for combo_ops in combos:
            score = _evaluate_room_combo(combo_ops, "Mfg", product, POWER_COUNT, global_bonus, buff_pool)
            evaluated.append((score, [op.name for op in combo_ops]))
        evaluated.sort(key=lambda x: -x[0])

        # 贪心分配
        allocated = _greedy_allocate(evaluated, room_count=count)
        for names in allocated:
            for op in pool:
                if op.name in names:
                    assigned_ids.add(op.char_id)
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

    # Phase 3: Control 固定
    ctrl_names = []
    for name in FIXED_CONTROL:
        for op in operators:
            if op.name == name:
                assigned_ids.add(op.char_id)
                ctrl_names.append(name)
                break
    assignments.append(RoomAssignment(
        room_type="Control", room_index=0, operators=ctrl_names,
    ))

    # Phase 4: 剩余设施贪心
    remaining = _greedy_remaining(assigned_ids, operators)
    assignments.extend(remaining)
    autofill_count += sum(1 for a in remaining if a.autofill)

    plan = ShiftPlan(
        name="MVP-12h",
        assignments=assignments,
        period_from="00:00",
        period_to="11:59",
    )
    return SolveResult(plans=[plan], autofill_count=autofill_count)
