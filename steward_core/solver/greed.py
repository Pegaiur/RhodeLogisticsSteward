"""贪心分配与组合评估"""

import itertools

from steward_core.efficiency_fn import constant_efficiency, rank_by_dominance
from steward_core.models import LayoutConfig, Operator, RoomAssignment
from steward_core.synergy import synergy_facility_count
from steward_core.synergy.trade_linkages import _TRADE_PAIR_TABLE

_LAYOUT_243 = LayoutConfig.layout_243()

_SELF_SAT_CONDITIONS: frozenset[str] = frozenset({
    "trade_ord_spd_par[000]",  # 摩根：格拉斯哥帮计数含自身
    "trade_ord_spd_par[001]",  # 新约能天使：拉特兰计数含自身
})
"""自满足条件：buff_id 前缀匹配且 holder 自身即满足计数条件"""


def _upper_bound_ok(total_eff: float, best_known: float, threshold: float = 0.95) -> bool:
    """规则3: 上界预判 — 总效率不低于 best_known × threshold

    threshold 建议从 SolverParams.combo_upper_bound_threshold 读取，默认 0.95。
    """
    return total_eff >= best_known * threshold


def _generate_combos(pool: list[Operator], k: int = 3) -> list[list[Operator]]:
    """生成 k 人组合"""
    if len(pool) < k:
        return [list(pool)]
    return [list(combo) for combo in itertools.combinations(pool, k)]


def _evaluate_trade_combo(
    combo_ops: list[Operator],
    power_count: int,
    hours: float,
    global_bonus,
    buff_pool,
    ctrl_per_op_bonus: float = 0.0,
    all_operators: list[Operator] | None = None,
    control_operators: list[Operator] | None = None,
    mood_ctx=None,
) -> float:
    """评估 Trade 三人组合的 LMD 日产

    evaluate_room（效率积分） + _get_trade_order_multiplier（订单机制）双通道精确计算。
    返回该组合在给定条件下的一日 LMD 产出。
    """
    from steward_core.production import _get_trade_order_multiplier

    n = len(combo_ops)
    from steward_core.evaluate import evaluate_room
    eff_int = evaluate_room(
        combo_ops, "Trade", "Money", power_count, hours,
        global_bonus, buff_pool, ctrl_per_op_bonus=ctrl_per_op_bonus,
        all_operators=all_operators,
        control_operators=control_operators,
        mood_ctx=mood_ctx,
    )
    efficiency_integrated = hours * (1.0 + 0.01 * n) + eff_int / 100.0
    lmd_per_day, _gold, _equiv = _get_trade_order_multiplier(combo_ops, hours)
    return efficiency_integrated / 24.0 * lmd_per_day


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


def _greedy_allocate_with_support_excluding(
    evaluated: list,
    room_count: int,
    exclude_sets: list[frozenset] | None = None,
    **kwargs,
) -> list[tuple[list[str], dict[str, list[str]]]] | None:
    """贪心分配，排除与 exclude_sets 完全相同的分配结果

    用于 K-Beam 迭代排斥——每次排斥上一次完整分配的 combo 集合，
    迫使算法找到不同的房间组合。
    """
    if not exclude_sets:
        return _greedy_allocate_with_support(evaluated, room_count, **kwargs)

    result = _greedy_allocate_with_support(evaluated, room_count, **kwargs)
    if result is None:
        return None
    result_set = frozenset(tuple(names) for names, _ in result)
    if result_set not in exclude_sets:
        return result

    for skip_idx, (_, skip_names, _, _) in enumerate(evaluated):
        if skip_names not in [names for names, _ in result]:
            continue
        trimmed = [e for i, e in enumerate(evaluated) if i != skip_idx]
        alt = _greedy_allocate_with_support(trimmed, room_count, **kwargs)
        if alt is None or len(alt) < room_count:
            continue
        alt_set = frozenset(tuple(names) for names, _ in alt)
        if alt_set not in exclude_sets:
            return alt
    return None


def _room_conditions_satisfiable(
    op: Operator,
    taken_names: list[str],
    remaining: list[Operator],
    room_slots: int,
    all_operators: list[Operator],
) -> bool:
    """迭代验证：将此干员加入后，剩余槽位能否满足其机制条件"""
    remaining_slots = room_slots - len(taken_names) - 1
    if remaining_slots < 0:
        return False

    op_lookup = {o.name: o for o in all_operators}

    for sk in op.skills:
        bid = sk.buff_id

        if any(bid.startswith(prefix) for prefix in _SELF_SAT_CONDITIONS):
            return True

        pair_entry = _TRADE_PAIR_TABLE.get(bid)
        if pair_entry is not None:
            existing = sum(1 for n in taken_names if n == pair_entry.target)
            if existing > 0:
                return True
            available = sum(1 for c in remaining if c.name == pair_entry.target)
            return available >= 1 and remaining_slots >= 1

    return True  # 无条件限制


def _operator_conditions_met(
    name: str,
    taken_names: list[str],
    op_lookup: dict[str, Operator],
) -> bool:
    """后验：已入槽干员的机制条件是否在房间内实际兑现"""
    op = op_lookup.get(name)
    if op is None:
        return True

    for sk in op.skills:
        bid = sk.buff_id

        if any(bid.startswith(prefix) for prefix in _SELF_SAT_CONDITIONS):
            return True

        pair_entry = _TRADE_PAIR_TABLE.get(bid)
        if pair_entry is not None:
            return pair_entry.target in taken_names

    return True


def _post_fill_verify(
    taken_names: list[str],
    all_operators: list[Operator],
    assigned_ids: set[str],
) -> None:
    """后验验证：填充完毕后，确认条件型干员的机制实际兑现。
    未兑现的干员从房间中移除，释放槽位（autofill 兜底）。
    """
    op_lookup = {o.name: o for o in all_operators}
    for name in list(taken_names):
        if not _operator_conditions_met(name, taken_names, op_lookup):
            taken_names.remove(name)
            op = op_lookup.get(name)
            if op:
                assigned_ids.discard(op.char_id)


def _greedy_remaining(
    assigned_ids: set[str],
    operators: list[Operator],
    priority_names: set[str] | None = None,
    params=None,
    mood_ctx=None,
) -> list[RoomAssignment]:
    """剩余设施（Trade/Power/Reception/Office）支配偏序贪心

    priority_names: 锁定的支撑干员名集合，即使已在 assigned_ids 中也会被强制分配
    mood_ctx: 多班次心情上下文，非 None 时从 work_burn 计算 mood_burn 截断
    """
    if priority_names is None:
        priority_names = set()
    priority_ids = {op.char_id for op in operators if op.name in priority_names}
    T = params.shift_hours if params is not None else 12.0

    results = []
    for room in _LAYOUT_243.rooms:
        if room.room_type not in ("Power", "Reception", "Office"):
            continue

        taken = []

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

        op_lookup = {op.char_id: op for op in operators}
        candidates = []
        for op in operators:
            if op.char_id in assigned_ids:
                continue
            if not op.has_skill_for(room.room_type, room.product):
                continue
            eff = op.best_efficiency(room.room_type, room.product)
            if eff <= 0:
                a6_segs = synergy_facility_count([op], room.room_type, room.product, _LAYOUT_243, T=T)
                eff = sum(s.a for s in a6_segs)
            if eff <= 0:
                continue
            burn = 0.0
            if mood_ctx is not None:
                burn = mood_ctx.work_burn(op.name, room.room_type, room.slots)
            seg = constant_efficiency(eff, mood_burn=burn, T=T)
            candidates.append((seg, op))

        if not candidates and not taken:
            results.append(RoomAssignment(
                room_type=room.room_type, room_index=room.room_index,
                operators=[], product=room.product, autofill=True,
            ))
            continue

        if candidates:
            ranked = rank_by_dominance(candidates, T)
            remaining = [op for op in ranked if op.char_id not in assigned_ids]

            while len(taken) < room.slots and remaining:
                op = remaining.pop(0)
                if op.char_id in assigned_ids:
                    continue
                if not _room_conditions_satisfiable(op, taken, remaining, room.slots, operators):
                    continue
                taken.append(op.name)
                assigned_ids.add(op.char_id)

            _post_fill_verify(taken, operators, assigned_ids)

        results.append(RoomAssignment(
            room_type=room.room_type, room_index=room.room_index,
            operators=taken, product=room.product,
            autofill=len(taken) < room.slots,
        ))

    return results


def _greedy_allocate_with_support(
    evaluated: list,
    room_count: int,
    max_control_slots: int = 5,
    initial_control: set[str] | None = None,
    config=None,
) -> list[tuple[list[str], dict[str, list[str]]]]:
    """从排序组合中贪心取无冲突的 N 间（含支撑干员冲突检查）

    evaluated: [(score, combo_names, all_support_names, support_map), ...]
    config: SolverConfig，exclusive_support_check=True 时仅检查独占支撑冲突
    中枢容量不再在贪心阶段限制，超出部分由 fill_control 阶段统一择优。
    """
    use_exclusive = config is not None and config.exclusive_support_check
    assigned: set[str] = set()
    exclusive_assigned: set[str] = set()
    result = []
    for _score, combo_names, all_support_names, support_map in evaluated:
        if any(n in assigned for n in combo_names):
            continue
        if use_exclusive:
            # 独占检查：仅 Trade + Office 支撑产生跨房间冲突
            exclusive_names = set(support_map.get("Trade", [])) | set(support_map.get("Office", []))
            if any(n in exclusive_assigned for n in exclusive_names):
                continue
        else:
            # 旧逻辑：全部支撑扁平冲突检查
            if any(n in assigned for n in all_support_names):
                continue
        result.append((combo_names, support_map))
        assigned.update(combo_names)
        if use_exclusive:
            exclusive_assigned.update(exclusive_names)
        else:
            assigned.update(all_support_names)
        if len(result) >= room_count:
            break
    return result
