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
    _B_LAYER_CONSUMER_TABLE,
)

T = 12.0
POWER_COUNT = 3

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
        elif op.name in _B_LAYER_CONSUMER_TABLE and _B_LAYER_CONSUMER_TABLE[op.name][0] == "Mfg":
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
                a6_segs = synergy_facility_count([op], room.room_type, room.product, _LAYOUT_243)
                eff = sum(s.a for s in a6_segs)
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


# ─── 最优支撑函数 ─────────────────────────────────────────────────

# 制造站干员类型 → 所需支撑干员映射
# 支撑集格式: {设施类型: [干员名, ...]}
_ROSEMARY_SUPPORT: dict[str, list[str]] = {
    "Control": ["令", "夕"],
    "Trade": ["黑键"],
    "Dormitory": ["爱丽丝", "车尔尼", "森西"],
}

# 红松骑士团 group_id
_PINUS_GROUP = "pinus"

# 骑士标签持有者（name 推导，后期改为 nation/group 查询）
_KNIGHT_NAMES: set[str] = {
    "砾", "野鬃", "白金", "鞭刃", "暴雨", "耀骑士临光",
    "瑕光", "临光", "远牙", "灰毫", "焰尾", "薇薇安娜",
}


def compute_optimal_support(
    combo_ops: list[Operator],
) -> dict[str, list[str]]:
    """计算制造站组合所需的最优支撑干员集

    按"加成包"概念：每种制造站 combo 类型决定性地对应一组支撑干员。
    如果 combo 含多种类型（如迷迭香+骑士），支撑集取并集。

    Returns:
        {"Control": [names], "Trade": [names], "Dormitory": [names]}
    """
    support: dict[str, set[str]] = {
        "Control": set(),
        "Trade": set(),
        "Dormitory": set(),
    }

    names = {op.name for op in combo_ops}

    # 迷迭香包
    if "迷迭香" in names:
        for facility, ops in _ROSEMARY_SUPPORT.items():
            support[facility].update(ops)

    # 骑士包
    has_knight = any(
        op.name in _KNIGHT_NAMES or op.group_id == "pinus"
        for op in combo_ops
    )
    if has_knight:
        support["Control"].add("薇薇安娜")

    # 红松骑士团包
    has_pinus = any(op.group_id == _PINUS_GROUP for op in combo_ops)
    if has_pinus:
        support["Control"].add("焰尾")

    return {k: sorted(v) for k, v in support.items()}


def _evaluate_with_support(
    combo_ops: list[Operator],
    room_type: str,
    product: str,
    all_operators: list[Operator],
    assigned_ids: set[str],
) -> tuple[float, dict[str, list[str]]]:
    """评估 combo 含最优支撑的完整评分

    1. 计算 combo 所需支撑干员
    2. 过滤已被分配的支撑干员
    3. 用可用支撑构建 global_bonus + buff_pool
    4. 评估房间效率积分

    Returns:
        (score, support_map) — support_map 仅含可用的支撑干员
    """
    support_map = compute_optimal_support(combo_ops)
    op_lookup = {op.name: op for op in all_operators}

    # 过滤已分配的支撑干员
    available_support: dict[str, list[str]] = {}
    for facility, names in support_map.items():
        available = [n for n in names if n not in assigned_ids]
        if available:
            available_support[facility] = available

    # 构建全局上下文
    control_names = available_support.get("Control", [])
    control_ops = [op_lookup[n] for n in control_names if n in op_lookup]
    global_bonus = compute_control_global_bonus(control_ops)

    dorm_names = available_support.get("Dormitory", [])
    dorm_ops = [op_lookup[n] for n in dorm_names if n in op_lookup]

    has_rosmontis = any(op.name == "迷迭香" for op in combo_ops)
    has_ebnhlz = "黑键" in available_support.get("Trade", [])

    buff_pool = compute_buff_pool(
        control_ops, suich_count=5,
        dorm_operators=dorm_ops, dorm_level=5,
        has_rosmontis_in_mfg=has_rosmontis,
        has_ebnhlz_in_trade=has_ebnhlz,
        ling_mood_below_12=True,
    )

    score = _evaluate_room_combo(
        combo_ops, room_type, product, POWER_COUNT, global_bonus, buff_pool,
    )

    return score, available_support


def _greedy_allocate_with_support(
    evaluated: list,
    room_count: int,
) -> list[tuple[list[str], dict[str, list[str]]]]:
    """从排序组合中贪心取无冲突的 N 间（含支撑干员冲突检查）

    evaluated: [(score, combo_names, all_support_names, support_map), ...]
    """
    assigned = set()
    result = []
    for _score, combo_names, all_support_names, support_map in evaluated:
        if any(n in assigned for n in combo_names):
            continue
        if any(n in assigned for n in all_support_names):
            continue
        result.append((combo_names, support_map))
        assigned.update(combo_names)
        assigned.update(all_support_names)
        if len(result) >= room_count:
            break
    return result


# ─── 主入口 ─────────────────────────────────────────────────────

def solve_mvp(operators: list[Operator]) -> SolveResult:
    """MVP 完整求解：制造站穷举 + 支撑干员锁 + 剩余设施贪心

    中枢不再固定——由制造站 combo 的支撑需求动态决定。
    返回 SolveResult，含一个 12h ShiftPlan。
    """
    assigned_ids: set[str] = set()
    assigned_names: set[str] = set()  # 用于支撑干员冲突检测
    assignments: list[RoomAssignment] = []
    autofill_count = 0
    op_lookup = {op.name: op for op in operators}
    # 累计所有已选中 combo 的支撑干员（用于最终填充 Control/Trade/Dorm）
    locked_support: dict[str, set[str]] = {
        "Control": set(), "Trade": set(), "Dormitory": set(),
    }

    # Phase 1: 制造站穷举（CR 2间 + PG 2间）—— 共享 assigned_ids 防跨产物冲突
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
        pool = [op for op in pool if op.char_id not in assigned_ids]
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

        # 贪心分配（含支撑干员锁）
        allocated = _greedy_allocate_with_support(evaluated, room_count=count)
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

    # Phase 2: 填充中枢（来自累计支撑干员）
    ctrl_names = sorted(locked_support["Control"])
    for n in ctrl_names:
        if n in op_lookup:
            assigned_ids.add(op_lookup[n].char_id)

    # 补满中枢至 5 人：从未分配的 Control 技能持有者中贪心选取
    if len(ctrl_names) < 5:
        remaining_ctrl = []
        for op in operators:
            if op.char_id in assigned_ids:
                continue
            if not op.has_skill_for("Control"):
                continue
            eff = op.best_efficiency("Control")
            remaining_ctrl.append((eff, op))
        remaining_ctrl.sort(key=lambda x: -x[0])
        for _eff, op in remaining_ctrl:
            if len(ctrl_names) >= 5:
                break
            if op.char_id not in assigned_ids:
                ctrl_names.append(op.name)
                assigned_ids.add(op.char_id)

    assignments.append(RoomAssignment(
        room_type="Control", room_index=0, operators=ctrl_names,
    ))

    # Phase 3: 剩余设施贪心
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
