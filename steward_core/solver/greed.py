"""贪心分配与组合评估"""

import itertools

from steward_core.efficiency_fn import constant_efficiency, rank_by_dominance
from steward_core.models import LayoutConfig, Operator, RoomAssignment
from steward_core.synergy import synergy_facility_count

T = 12.0

_LAYOUT_243 = LayoutConfig.layout_243()


def _upper_bound_ok(total_eff: float, best_known: float, threshold: float = 0.95) -> bool:
    """规则3: 上界预判 — 总效率不低于 best_known × threshold"""
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

        if bid.startswith("trade_ord_spd_par[000]"):
            # 摩根：格拉斯哥帮计数加成。摩根本人即格帮成员，条件总是满足
            return True

        if bid.startswith("trade_ord_spd&cost_P[000]"):
            # 德克萨斯：需要拉普兰德同房
            existing = sum(1 for n in taken_names if n == "拉普兰德")
            if existing > 0:
                return True
            available = sum(1 for c in remaining if c.name == "拉普兰德")
            return available >= 1 and remaining_slots >= 1

        if bid.startswith("trade_ord_spd_par[001]"):
            # 新约能天使：拉特兰计数加成。新约能天使本人 nation_id=laterano，条件总是满足
            return True

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

        if bid.startswith("trade_ord_spd_par[000]"):
            # 摩根：格帮计数含自身，条件总是满足
            return True

        if bid.startswith("trade_ord_spd&cost_P[000]"):
            return "拉普兰德" in taken_names

        if bid.startswith("trade_ord_spd_par[001]"):
            # 新约能天使：拉特兰计数含自身，条件总是满足
            return True

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
) -> list[RoomAssignment]:
    """剩余设施（Trade/Power/Reception/Office）支配偏序贪心

    priority_names: 锁定的支撑干员名集合，即使已在 assigned_ids 中也会被强制分配
    """
    if priority_names is None:
        priority_names = set()
    priority_ids = {op.char_id for op in operators if op.name in priority_names}

    results = []
    for room in _LAYOUT_243.rooms:
        if room.room_type not in ("Power", "Reception", "Office"):
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
            remaining = [op for op in ranked if op.char_id not in assigned_ids]

            # 迭代填充：每个槽位"尝试→验证条件→接受或跳过"
            while len(taken) < room.slots and remaining:
                op = remaining.pop(0)
                if op.char_id in assigned_ids:
                    continue
                if not _room_conditions_satisfiable(op, taken, remaining, room.slots, operators):
                    continue  # 条件不可满足 → 跳过此候选人，试下一个
                taken.append(op.name)
                assigned_ids.add(op.char_id)

            # 后验验证：确认条件型干员的机制实际兑现
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
) -> list[tuple[list[str], dict[str, list[str]]]]:
    """从排序组合中贪心取无冲突的 N 间（含支撑干员冲突检查 + 中枢容量限制）

    evaluated: [(score, combo_names, all_support_names, support_map), ...]
    initial_control: 已占用的中枢支撑干员集合（跨产物轮次传递容量状态）
    容量不足时跳过当前组合，尝试下一个。
    """
    assigned: set[str] = set()
    control_assigned: set[str] = set(initial_control) if initial_control else set()
    result = []
    for _score, combo_names, all_support_names, support_map in evaluated:
        if any(n in assigned for n in combo_names):
            continue
        if any(n in assigned for n in all_support_names):
            continue
        new_control = set(support_map.get("Control", []))
        if len(control_assigned | new_control) > max_control_slots:
            continue
        result.append((combo_names, support_map))
        assigned.update(combo_names)
        assigned.update(all_support_names)
        control_assigned.update(new_control)
        if len(result) >= room_count:
            break
    return result
