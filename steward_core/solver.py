"""排班求解器

MV3: 制造站穷举(含联动) + 剪枝 + 贪心分配。
剩余设施（Trade/Power/Reception/Office）用支配偏序贪心。
Control 固定为社区最优方案。
"""

import itertools
from dataclasses import dataclass, field

from steward_core.models import LayoutConfig, Operator, RoomAssignment, ShiftPlan, SolveResult
from steward_core.efficiency_fn import constant_efficiency, rank_by_dominance
from steward_core.synergy import (
    synergy_facility_count, skill_class,
    compute_control_global_bonus,
    compute_buff_pool, ROSEMARY_SUPPORT,
    compute_effective_power_count,
    _B_LAYER_CONSUMER_TABLE, _A6_FACILITY_TABLE,
)
from steward_core.evaluate import evaluate_room

T = 12.0
_BASE_POWER_COUNT = 3  # 243 布局物理发电站数

ANCHOR_NAMES = {
    "水月", "多萝西", "苍苔", "海沫",
    "森蚺", "温蒂", "掠风", "异客",
    "阿兰娜", "Miss.Christine", "怒潮凛冬",
}


# ─── 角色分类 ───────────────────────────────────────────────────

# C1 全局加成提供者，中枢填充时优先选取
_C1_PRIORITY_CONTROL: set[str] = {"凯尔希"}

# 宿舍填充优先级（B 层感知/魔物料理/无声共鸣生成者）
_DORM_PRIORITY: list[str] = ["森西", "爱丽丝", "车尔尼", "塑心"]

# 发电站优先级（设施数量修改器持有者，个人效率为0但影响全局）
_POWER_PRIORITY: set[str] = {"承曦格雷伊"}


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
            if skill_class(sk.buff_name):
                has_skill_label = True
                break

        if is_anchor:
            result.anchors.append(op)
        elif has_skill_label:
            result.providers.append(op)
        elif op.name in _B_LAYER_CONSUMER_TABLE and _B_LAYER_CONSUMER_TABLE[op.name][0] == "Mfg":
            result.providers.append(op)
        elif op.name in _A6_FACILITY_TABLE and _A6_FACILITY_TABLE[op.name][2] == "Mfg":
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

def control_per_operator_bonus(
    control_ops: list[Operator],
    room_ops: list[Operator],
    product: str,
) -> float:
    """中枢干员对当前房间的条件型 per-operator 加成（百分值）

    焰尾: 每个红松骑士团 Mfg 干员 → CR+10%, PG-10%
    薇薇安娜: 每个骑士 Mfg 干员 → +7%
    """
    bonus = 0.0
    control_names = {op.name for op in control_ops}

    # 焰尾: 红松骑士团
    if "焰尾" in control_names:
        for op in room_ops:
            if op.group_id == _PINUS_GROUP:
                if product == "CombatRecord":
                    bonus += 10.0
                elif product == "PureGold":
                    bonus -= 10.0

    # 薇薇安娜: 骑士（含红松骑士团）
    if "薇薇安娜" in control_names:
        for op in room_ops:
            if _is_knight(op):
                bonus += 7.0

    return bonus


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
    priority_names: set[str] | None = None,
) -> list[RoomAssignment]:
    """剩余设施（Trade/Power/Reception/Office）支配偏序贪心

    priority_names: 锁定的支撑干员名集合，即使已在 assigned_ids 中也会被强制分配
    """
    if priority_names is None:
        priority_names = set()
    priority_ids = {op.char_id for op in operators if op.name in priority_names}

    results = []
    for room in _LAYOUT_243.rooms:
        if room.room_type in ("Mfg", "Control", "Dormitory"):
            continue

        taken = []

        # 优先分配 locked 支撑干员（绕过 assigned_ids + 不验证效率）
        # 注意：支撑干员的价值已在 Phase 1 跨设施联动评估中计入（如 B5 黑键→Trade），
        # 此处仅执行放置，不重复验证效率值（该值可能为 0，因贡献来自 buff 池消费）
        for op in operators:
            if len(taken) >= room.slots:
                break
            if op.char_id not in priority_ids:
                continue
            if op.char_id in assigned_ids:
                continue
            if not op.has_skill_for(room.room_type, room.product):
                continue
            taken.append(op.name)
            assigned_ids.add(op.char_id)

        # 剩余工位走正常支配偏序贪心
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

        if not candidates and not taken:
            results.append(RoomAssignment(
                room_type=room.room_type, room_index=room.room_index,
                operators=[], product=room.product, autofill=True,
            ))
            continue

        if candidates:
            ranked = rank_by_dominance(candidates, T)
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

# 红松骑士团 group_id。游戏内"骑士"标签覆盖红松骑士团全体。
_PINUS_GROUP = "pinus"

# 骑士标签持有者（name 推导 + kazimierz 势力 + 红松骑士团）
# 游戏内骑士 = kazimierz 势力干员 + 红松骑士团干员，但 character_identity
# 无独立骑士 tag 字段，部分骑士（如薇薇安娜）不属于 kazimierz 也不属于 pinus，
# 因此 name 集合作为安全网补全数据驱动判定的缺口。
_KNIGHT_NAMES: set[str] = {
    "砾", "野鬃", "白金", "鞭刃", "暴雨", "耀骑士临光",
    "瑕光", "临光", "远牙", "灰毫", "焰尾", "薇薇安娜",
}


def _is_knight(op: Operator) -> bool:
    """游戏内骑士 = kazimierz 势力干员 + 红松骑士团干员"""
    return op.name in _KNIGHT_NAMES or op.nation_id == "kazimierz" or op.group_id == _PINUS_GROUP


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
        for facility, ops in ROSEMARY_SUPPORT.items():
            support[facility].update(ops)

    # 骑士包（含红松骑士团，游戏内骑士标签覆盖全体）
    has_knight = any(_is_knight(op) for op in combo_ops)
    if has_knight:
        support["Control"].add("薇薇安娜")
        support["Control"].add("焰尾")  # 骑士中枢天然伴随焰尾

    # 红松骑士团包（已包含在骑士包中，此处显式标注确保焰尾）
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
        ling_mood_below_12=has_rosmontis,
    )

    ctrl_bonus = control_per_operator_bonus(control_ops, combo_ops, product)

    # 计算有效发电站数（承曦格雷伊"晨曦"使发电站+1）
    effective_power = _BASE_POWER_COUNT
    if "承曦格雷伊" not in assigned_ids and "承曦格雷伊" in op_lookup:
        effective_power += 1

    score = evaluate_room(
        combo_ops, room_type, product, effective_power, T, global_bonus, buff_pool,
        ctrl_per_op_bonus=ctrl_bonus,
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
    # C1 全局加成提供者优先
    if len(ctrl_names) < 5:
        remaining_ctrl = []
        for op in operators:
            if op.char_id in assigned_ids:
                continue
            if not op.has_skill_for("Control"):
                continue
            eff = max(op.best_efficiency("Control"), 0.0)
            if op.name in _C1_PRIORITY_CONTROL:
                eff += 1000.0
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
    # 释放 locked Trade 支撑干员（已在 Phase 1 锁入 assigned_ids 但尚未写入房间）
    for name in locked_support["Trade"]:
        if name in op_lookup:
            assigned_ids.discard(op_lookup[name].char_id)
    # 合并 Trade 支撑 + Power 优先级（设施数量修改器持有者）
    priority = locked_support["Trade"] | _POWER_PRIORITY
    remaining = _greedy_remaining(assigned_ids, operators, priority)
    assignments.extend(remaining)
    autofill_count += sum(1 for a in remaining if a.autofill)

    # Phase 4: 宿舍填充（优先B层生成者 → 任意填充至20人）
    # locked_support["Dormitory"] 中的干员已在 Phase 1 锁入 assigned_ids
    dorm_names: list[str] = list(locked_support["Dormitory"])

    for name in _DORM_PRIORITY:
        if name not in dorm_names and name in op_lookup and op_lookup[name].char_id not in assigned_ids:
            dorm_names.append(name)
            assigned_ids.add(op_lookup[name].char_id)

    for op in operators:
        if len(dorm_names) >= 20:
            break
        if op.char_id not in assigned_ids:
            dorm_names.append(op.name)
            assigned_ids.add(op.char_id)

    for room_idx in range(4):
        start = room_idx * 5
        room_ops = dorm_names[start:start + 5] if start < len(dorm_names) else []
        assignments.append(RoomAssignment(
            room_type="Dormitory", room_index=room_idx,
            operators=room_ops, autofill=(len(room_ops) < 5),
        ))
        if len(room_ops) < 5:
            autofill_count += 1

    plan = ShiftPlan(
        name="MVP-12h",
        assignments=assignments,
        period_from="00:00",
        period_to="11:59",
    )
    return SolveResult(plans=[plan], autofill_count=autofill_count)
