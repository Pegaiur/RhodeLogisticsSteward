"""贸易站穷举"""

from steward_core.constants import BASE_POWER_COUNT
from steward_core.models import Operator, RoomAssignment, LayoutConfig
from steward_core.synergy import (
    compute_control_global_bonus,
    compute_buff_pool,
    _has_power_count_modifier,
    classify_trade_operators, build_candidate_pool,
    control_per_operator_bonus,
    get_synergy_enablers,
)
from steward_core.synergy._derived import TRADE_ANCHORS

from .config import SolverConfig
from .greed import _generate_combos, _greedy_allocate, _evaluate_trade_combo
from .support import compute_trade_support


def exhaust_trade(
    operators: list[Operator],
    assigned_ids: set[str],
    assigned_names: set[str],
    assignments: list,
    op_lookup: dict[str, Operator],
    locked_support: dict[str, set[str]],
    *,
    config: SolverConfig | None = None,
    override_pool=None,
    score_extra_fn=None,
) -> int:
    """Phase 3a: Trade 穷举（使用 locked_support 估计中枢，中枢尚未填充）

    中枢后置于 Trade 之后——此处用 Mfg 锁定的中枢支撑干员做评估估计。
    分配完毕后，将 Trade combo 自身的中枢支撑需求合并到 locked_support。
    score_extra_fn(combo_ops, product) -> float: 贡献信用回调，返回值须与 combo 评分同量纲(LMD/天)。

    返回本阶段新增的 autofill_count。
    """
    if config is None:
        config = SolverConfig()
    params = config.params
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
        classification = classify_trade_operators(trade_ops, TRADE_ANCHORS)
        pool = build_candidate_pool(trade_ops, classification, room_type="Trade", product="Money")
        pool = [op for op in pool if op.char_id not in assigned_ids]
        # 补充 Trade 联动使能者（无 Trade 技能但能提升 A2 阵营计数的干员，如推王→摩根）
        existing = {op.char_id for op in pool}
        for enabler in get_synergy_enablers(operators, "Trade", "Money"):
            if enabler.char_id not in existing and enabler.char_id not in assigned_ids:
                pool.append(enabler)
        combos = _generate_combos(pool, min(3, len(pool)))

        # 用 locked_support 中的 Control 名称估计中枢（中枢尚未实际填充）
        ctrl_names = list(locked_support["Control"])
        ctrl_ops = [op_lookup[n] for n in ctrl_names if n in op_lookup]
        global_bonus = compute_control_global_bonus(ctrl_ops)
        effective_power = BASE_POWER_COUNT + sum(
            1 for op in operators if op.name not in assigned_names
            and _has_power_count_modifier(op)
        )

        # 评估所有组合（含宿舍估计用于乌有烟火/黑键感知等B1生成）
        dorm_est = [Operator(char_id=f"_dorm_{i}", name=f"填位宿舍{i}", skills=[])
                    for i in range(params.dorm_estimated_count)]
        base_pool = compute_buff_pool(
            ctrl_ops, suich_count=params.suich_count,
            dorm_operators=dorm_est, dorm_level=params.dorm_level,
            layout=LayoutConfig.layout_243(),
        )
        if override_pool is not None:
            base_pool = override_pool
        evaluated = []
        for combo_ops in combos:
            combo_names = [op.name for op in combo_ops]
            has_wuyou = "乌有" in combo_names
            has_ebnhlz = "黑键" in combo_names
            ctrl_bonus = control_per_operator_bonus(
                ctrl_ops, combo_ops, "Money", room_type="Trade",
            )
            if override_pool is not None:
                bp = override_pool
            elif has_wuyou or has_ebnhlz:
                bp = compute_buff_pool(
                    ctrl_ops, suich_count=params.suich_count,
                    dorm_operators=dorm_est, dorm_level=params.dorm_level,
                    has_ebnhlz_in_trade=has_ebnhlz,
                    has_wuyou_in_trade=has_wuyou,
                    layout=LayoutConfig.layout_243(),
                )
            else:
                bp = base_pool
            lmd = _evaluate_trade_combo(
                combo_ops, effective_power, params.shift_hours, global_bonus,
                bp, ctrl_bonus,
                all_operators=operators,
                control_operators=ctrl_ops,
                mood_ctx=config.mood_ctx,
            )
            if score_extra_fn is not None:
                lmd += score_extra_fn(combo_ops, "Money")
            evaluated.append((lmd, combo_names))
        evaluated.sort(key=lambda x: -x[0])

        # 强制放置 locked Trade 支撑干员：将含支撑干员的组合排到前面
        # Phase 1 已基于"该干员在 Trade 中"的假设评估制造站得分，此处强制执行
        if locked_support["Trade"]:
            locked_combos = [(s, n) for s, n in evaluated
                             if any(name in locked_support["Trade"] for name in n)]
            normal_combos = [(s, n) for s, n in evaluated
                             if not any(name in locked_support["Trade"] for name in n)]
            locked_combos.sort(key=lambda x: -x[0])
            normal_combos.sort(key=lambda x: -x[0])
            evaluated = locked_combos + normal_combos

        # 贪心分配（2 间 Trade）
        allocated = _greedy_allocate(evaluated, room_count=2)
        for names in allocated:
            for op in pool:
                if op.name in names:
                    assigned_ids.add(op.char_id)
                    assigned_names.add(op.name)
            # 计算该 combo 的 trade support 并合并到 locked_support（中枢容量受限）
            combo_ops = [op_lookup[n] for n in names if n in op_lookup]
            ts = compute_trade_support(combo_ops)
            for facility, support_names in ts.items():
                if facility == "Control":
                    remaining = params.control_max_slots - len(locked_support["Control"])
                    if remaining > 0:
                        locked_support["Control"].update(list(support_names)[:remaining])
                else:
                    locked_support[facility].update(support_names)
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
