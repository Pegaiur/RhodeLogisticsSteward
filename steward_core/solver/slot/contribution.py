"""统一贡献评分 — contribution(op, facility_type, ctx, window_idx) -> LMD等值/窗口

中枢/发电/会客/办公室/宿舍的干员选择统一通过边际贡献评分，
替代旧的 locked_support 累积 + best_efficiency 排序模式。

公式:
  contribution = type2 状态写入 * D[d]
               + type3 全局注入 * 受影响槽位数
               + type2 per-operator 条件加成
               - λ[op] × hours
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from steward_core.models import LayoutConfig
from steward_core.synergy import compute_control_global_bonus, control_per_operator_bonus
from .context import STATE_DIMS
from .partials import _product_base_rate, _product_lmd_per_unit

if TYPE_CHECKING:
    from steward_core.models import Operator
    from .context import SlotContext

_LAYOUT_243 = LayoutConfig.layout_243()

_TRADE_BASE_LMD_PER_HOUR = 10265.0 / 24.0

_RECEPTION_TO_MFG_RATIO = 0.10
_OFFICE_TO_MFG_RATIO = 1.10
_DRONE_TO_MFG_RATIO = 0.5

_MFG_CR_BASE_RATE = 1.0 / 3.0
_MFG_PG_BASE_RATE = 1.0 / 1.2

_RECEPTION_NON_DISPERSION = 5.0

_RECEPTION_RARITY_BONUS: dict[int, float] = {
    0: 0.0,
    1: 0.0,
    2: 0.0,
    3: 2.0,
    4: 4.0,
    5: 5.0,
}

_RECEPTION_ELITE_BONUS: dict[int, float] = {
    0: 0.0,
    1: 8.0,
    2: 16.0,
}

_RECEPTION_LEVEL_BONUS: dict[int, float] = {
    1: 7.0,
    2: 9.0,
    3: 11.0,
}

_RECEPTION_DORM_AMBIANCE_THRESHOLDS: list[tuple[int, float]] = [
    (4000, 15.0),
    (3000, 10.0),
    (2000, 5.0),
    (0, 0.0),
]


def contribution(
    ctx: "SlotContext",
    op_name: str,
    facility_type: str,
    window_idx: int = 0,
    D: dict[str, float] | None = None,
    room_index: int = 0,
) -> float:
    """统一贡献评分入口

    Returns:
        该干员在指定设施中的边际贡献（LMD 等值/窗口量纲）
    """
    op = ctx.op_lookup.get(op_name)
    if op is None:
        return float("-inf")

    if D is None:
        D = {d: 0.0 for d in STATE_DIMS}

    hours = ctx.params.shift_hours if ctx.params else 12.0

    if facility_type == "Control":
        base = _control_contribution(ctx, op, window_idx, D)
    elif facility_type == "Power":
        base = _power_contribution(ctx, op, window_idx, D)
    elif facility_type == "Reception":
        base = _reception_contribution(ctx, op, window_idx, D)
    elif facility_type == "Office":
        base = _office_contribution(ctx, op, window_idx, D)
    elif facility_type == "Dormitory":
        base = _dorm_contribution(ctx, op, window_idx, D, room_index)
    else:
        return float("-inf")

    return base - ctx.lambda_ops.get(op_name, 0.0) * hours


def _mfg_base_rate_lmd_avg() -> float:
    """Mfg CR/PG 加权平均单位小时 LMD 等值（243布局 0.5:0.5）"""
    return (
        0.5 * _MFG_CR_BASE_RATE * _product_lmd_per_unit("CombatRecord")
        + 0.5 * _MFG_PG_BASE_RATE * _product_lmd_per_unit("PureGold")
    )


def _compute_state_snapshot(
    ctx: "SlotContext",
    window_idx: int,
    ctrl_names: list[str],
    extra_dorm_names: list[str] | None = None,
    office_op_name: str | None = None,
) -> dict[str, float]:
    """计算给定中枢/宿舍/办公室组合下的状态向量快照"""
    from steward_core.synergy.buff_pool import compute_buff_pool
    from steward_core.synergy import compute_engineering_robots

    params = ctx.params
    suich_count = params.suich_count if params else 5
    dorm_level = params.dorm_level if params else 5
    layout = ctx.layout if ctx.layout else _LAYOUT_243

    dorm_names = list(ctx.ops_of_type(window_idx, "Dormitory"))
    if extra_dorm_names:
        dorm_names.extend(extra_dorm_names)
    dorm_ops = [ctx.op_lookup[n] for n in dorm_names if n in ctx.op_lookup]

    ctrl_ops = [ctx.op_lookup[n] for n in ctrl_names if n in ctx.op_lookup]

    office_operators_list = None
    if office_op_name and office_op_name in ctx.op_lookup:
        office_operators_list = [ctx.op_lookup[office_op_name]]

    mfg_names_list = ctx.ops_of_type(window_idx, "Mfg")
    trade_names_list = ctx.ops_of_type(window_idx, "Trade")
    mfg_ops = [ctx.op_lookup[n] for n in mfg_names_list if n in ctx.op_lookup]
    trade_ops = [ctx.op_lookup[n] for n in trade_names_list if n in ctx.op_lookup]

    bp = compute_buff_pool(
        ctrl_ops, suich_count=suich_count,
        dorm_operators=[o for o in dorm_ops if o],
        dorm_level=dorm_level, layout=layout,
        mfg_operators=mfg_ops,
        trade_operators=trade_ops,
        office_operators=office_operators_list,
        office_perception_base=params.office_perception_base if params else 20,
    )

    eng = compute_engineering_robots(layout)

    return {
        "yanhuo": bp.yanhuo,
        "perception": bp.perception,
        "engineering_robots": eng,
        "monster_cuisine": bp.monster_cuisine,
        "silent_resonance": bp.silent_resonance,
    }


def _control_contribution(
    ctx: "SlotContext",
    op: "Operator",
    window_idx: int,
    D: dict[str, float],
) -> float:
    """中枢贡献 = type2状态写入*D + type3全局注入 + per-op条件"""
    total = 0.0
    existing_names = ctx.ops_of_type(window_idx, "Control")

    with_sv = _compute_state_snapshot(ctx, window_idx, existing_names + [op.name])
    without_sv = _compute_state_snapshot(
        ctx, window_idx, [n for n in existing_names if n != op.name],
    )

    for d in STATE_DIMS:
        delta = with_sv[d] - without_sv[d]
        if delta != 0.0 and D.get(d, 0.0) > 0:
            total += delta * D[d]

    total += _type3_contribution(ctx, op, window_idx)
    total += _per_operator_contribution(ctx, op, window_idx)
    return total


def _type3_contribution(
    ctx: "SlotContext",
    op: "Operator",
    window_idx: int,
) -> float:
    """类型 3 全局注入的边际贡献（LMD 等值/窗口量纲）"""
    existing_names = ctx.ops_of_type(window_idx, "Control")

    def _bonus(ctrl_names):
        ctrl_ops = [ctx.op_lookup[n] for n in ctrl_names if n in ctx.op_lookup]
        return compute_control_global_bonus(ctrl_ops)

    with_bonus = _bonus(existing_names + [op.name])
    without_bonus = _bonus([n for n in existing_names if n != op.name])

    mfg_bonus = with_bonus.mfg_bonus - without_bonus.mfg_bonus
    trade_bonus = with_bonus.trade_bonus - without_bonus.trade_bonus

    hours = ctx.params.shift_hours if ctx.params else 12.0
    total = 0.0

    if mfg_bonus != 0:
        mfg_filled = len([a for a in ctx.slots_of_type(window_idx, "Mfg") if not a.is_empty])
        affected = max(mfg_filled, 1)
        base_lmd = _mfg_base_rate_lmd_avg()
        total += mfg_bonus * affected * base_lmd * hours / 100.0

    if trade_bonus != 0:
        trade_filled = len([a for a in ctx.slots_of_type(window_idx, "Trade") if not a.is_empty])
        affected = max(trade_filled, 1)
        total += trade_bonus * affected * _TRADE_BASE_LMD_PER_HOUR * hours / 100.0

    return total


def _per_operator_contribution(
    ctx: "SlotContext",
    op: "Operator",
    window_idx: int,
) -> float:
    """类型 2 per-operator 条件加成的边际贡献（LMD 等值/窗口量纲）"""
    existing_names = ctx.ops_of_type(window_idx, "Control")

    if op.name in existing_names:
        without = [n for n in existing_names if n != op.name]
        with_ctrl = existing_names
    else:
        without = existing_names
        with_ctrl = existing_names + [op.name]

    hours = ctx.params.shift_hours if ctx.params else 12.0
    total = 0.0
    for facility_type in ("Mfg", "Trade"):
        max_rooms = 4 if facility_type == "Mfg" else 2
        for room_idx in range(max_rooms):
            room_ops = ctx.room_ops(window_idx, facility_type, room_idx)
            if not room_ops:
                continue

            room_op_objects = [ctx.op_lookup[n] for n in room_ops if n in ctx.op_lookup]
            if not room_op_objects:
                continue

            without_ctrl_ops = [ctx.op_lookup[n] for n in without if n in ctx.op_lookup]
            with_ctrl_ops = [ctx.op_lookup[n] for n in with_ctrl if n in ctx.op_lookup]

            product = ""
            for a in ctx.slots_of_type(window_idx, facility_type):
                if a.room_index == room_idx and a.product:
                    product = a.product
                    break

            bonus_without = control_per_operator_bonus(
                without_ctrl_ops, room_op_objects, product, facility_type,
            )
            bonus_with = control_per_operator_bonus(
                with_ctrl_ops, room_op_objects, product, facility_type,
            )
            marginal = bonus_with - bonus_without
            if marginal == 0:
                continue

            if facility_type == "Trade":
                total += marginal * _TRADE_BASE_LMD_PER_HOUR * hours / 100.0
            else:
                rate = _product_base_rate(product)
                lmd = _product_lmd_per_unit(product)
                total += marginal * rate * hours * lmd / 100.0

    return total


def _power_contribution(
    ctx: "SlotContext",
    op: "Operator",
    window_idx: int,
    D: dict[str, float],
) -> float:
    """发电站贡献 = type2状态写入*D + 发电效率->无人机等价
    Power 干员不通过 BuffPool 写入全局状态，仅计算直接效率贡献。
    """
    total = 0.0

    eff = op.best_efficiency("Power", "")
    if eff <= 0:
        eff = 0.0
    hours = ctx.params.shift_hours if ctx.params else 12.0
    base_lmd = _mfg_base_rate_lmd_avg()
    total += eff * _DRONE_TO_MFG_RATIO / 100.0 * base_lmd * hours

    return total


def _reception_implicit_bonus(
    op: "Operator",
    reception_level: int,
    dorm_ambiance: int,
) -> float:
    """会客室隐式线索搜集速度加成（与技能无关的基础加成）

    来源: PRTS Wiki 会客室机制表，含 5 项:
      - 非涣散加成: 固定 +5%
      - 干员稀有度: 1-3★=0%, 4★=2%, 5★=4%, 6★=5%
      - 干员精英阶段: E0=0%, E1=8%, E2=16%
      - 会客室等级: Lv1=7%, Lv2=9%, Lv3=11%
      - 宿舍氛围累计: 阈值分段 0/2000/3000/4000 → 0/5/10/15%
    """
    total = _RECEPTION_NON_DISPERSION
    total += _RECEPTION_RARITY_BONUS.get(op.rarity, 0.0)
    total += _RECEPTION_ELITE_BONUS.get(op.elite_phase, 0.0)
    total += _RECEPTION_LEVEL_BONUS.get(reception_level, 11.0)

    for threshold, bonus in _RECEPTION_DORM_AMBIANCE_THRESHOLDS:
        if dorm_ambiance >= threshold:
            total += bonus
            break

    return total


def _reception_contribution(
    ctx: "SlotContext",
    op: "Operator",
    window_idx: int,
    D: dict[str, float],
) -> float:
    """会客室贡献 = 隐式加成 + 技能效率 → 等效Mfg
    Reception 干员不通过 BuffPool 写入全局状态。
    隐式加成包括: 非涣散/稀有度/精英阶段/会客室等级/宿舍氛围。
    """
    total = 0.0

    reception_level = ctx.params.reception_level if ctx.params else 3
    dorm_ambiance = ctx.params.dorm_ambiance if ctx.params else 5000
    implicit = _reception_implicit_bonus(op, reception_level, dorm_ambiance)
    skill_eff = max(op.best_efficiency("Reception", "General"), 0.0)
    eff = implicit + skill_eff

    hours = ctx.params.shift_hours if ctx.params else 12.0
    base_lmd = _mfg_base_rate_lmd_avg()
    total += eff * _RECEPTION_TO_MFG_RATIO / 100.0 * base_lmd * hours

    return total


def _office_contribution(
    ctx: "SlotContext",
    op: "Operator",
    window_idx: int,
    D: dict[str, float],
) -> float:
    """办公室贡献 = type2状态写入*D + 办公室效率->等效Mfg"""
    total = 0.0

    ctrl_names = ctx.ops_of_type(window_idx, "Control")

    with_sv = _compute_state_snapshot(
        ctx, window_idx, ctrl_names, office_op_name=op.name,
    )
    without_sv = _compute_state_snapshot(ctx, window_idx, ctrl_names)

    for d in STATE_DIMS:
        delta = with_sv[d] - without_sv[d]
        if delta != 0.0 and D.get(d, 0.0) > 0:
            total += delta * D[d]

    eff = max(op.best_efficiency("Office", "HR"), 0.0)
    hours = ctx.params.shift_hours if ctx.params else 12.0
    base_lmd = _mfg_base_rate_lmd_avg()
    total += eff * _OFFICE_TO_MFG_RATIO / 100.0 * base_lmd * hours

    return total


def _dorm_contribution(
    ctx: "SlotContext",
    op: "Operator",
    window_idx: int,
    D: dict[str, float],
    room_index: int,
) -> float:
    """宿舍贡献 = type2状态写入*D + 室友恢复增量 - 槽位机会成本

    按房间计算边际贡献，自然覆盖 C 类冗余（同房间第2个C类增量=0）、
    D 类累加、槽位稀缺性定价。无需硬编码守卫。
    """
    total = 0.0
    hours = ctx.params.shift_hours if ctx.params else 12.0

    # 部分1: 状态向量增量
    ctrl_names = ctx.ops_of_type(window_idx, "Control")
    with_sv = _compute_state_snapshot(
        ctx, window_idx, ctrl_names, extra_dorm_names=[op.name],
    )
    without_sv = _compute_state_snapshot(ctx, window_idx, ctrl_names)
    for d in STATE_DIMS:
        delta = with_sv[d] - without_sv[d]
        if delta != 0.0 and D.get(d, 0.0) > 0:
            total += delta * D[d]

    # 提取中枢修正参数（只算一次，Part 2 和 Part 3 共用）
    ctrl_ops = [ctx.op_lookup[n] for n in ctrl_names if n in ctx.op_lookup]
    dorm_bonus_all, dorm_bonus_elite, yanhuo_bonus = _dorm_modifiers_from_ctrl(
        ctrl_ops, with_sv.get("yanhuo", 0.0),
    )
    dorm_level = ctx.params.dorm_level if ctx.params else 5
    amb = ctx.params.dorm_ambiance_per_room if ctx.params else 5000

    # 部分2: 室友恢复增量
    room_ops_names = ctx.room_ops(window_idx, "Dormitory", room_index)
    existing_names = [n for n in room_ops_names if n]
    if existing_names:
        existing_ops = [ctx.op_lookup[n] for n in existing_names if n in ctx.op_lookup]
        for roommate_name in existing_names:
            roommate = ctx.op_lookup.get(roommate_name)
            if roommate is None:
                continue
            before = _evaluate_dorm_recovery_for(
                existing_ops, roommate, dorm_bonus_all, dorm_bonus_elite,
                yanhuo_bonus, dorm_level, amb,
            )
            after = _evaluate_dorm_recovery_for(
                existing_ops + [op], roommate, dorm_bonus_all, dorm_bonus_elite,
                yanhuo_bonus, dorm_level, amb,
            )
            delta_rec = after - before
            rmbda = ctx.lambda_ops.get(roommate_name, 0.0)
            if delta_rec > 0 and rmbda > 0:
                total += delta_rec * rmbda * hours / 24.0

    # 部分3: 槽位机会成本
    unassigned_theta = _avg_unassigned_worker_lambda(ctx, window_idx)
    if unassigned_theta > 0:
        existing_ops_for_baseline = [
            ctx.op_lookup[n] for n in existing_names if n in ctx.op_lookup
        ]
        baseline_rate = _baseline_dorm_recovery(
            existing_ops_for_baseline, dorm_bonus_all, dorm_bonus_elite,
            yanhuo_bonus, dorm_level, amb,
        )
        total -= baseline_rate * hours * unassigned_theta / 24.0

    return total


def _dorm_modifiers_from_ctrl(
    ctrl_ops: list,
    yanhuo: float,
) -> tuple[float, float, float]:
    """从中枢干员 skills 提取宿舍相关的全局修正量

    dorm_bonus 扫描复用 mood_flow._extract_dorm_ctrl_bonuses。
    yanhuo_bonus 从状态快照推导——与 mood_flow 的 BuffPool 来源不同。
    """
    from steward_core.mood_flow import _extract_dorm_ctrl_bonuses
    dorm_bonus_all, dorm_bonus_elite = _extract_dorm_ctrl_bonuses(ctrl_ops)

    yanhuo_bonus = 0.0
    if any(op.name == "重岳" for op in ctrl_ops):
        yanhuo_bonus = 0.05 + (int(yanhuo) // 20) * 0.05

    return dorm_bonus_all, dorm_bonus_elite, yanhuo_bonus


def _evaluate_dorm_recovery_for(
    dorm_ops: list,
    target_op,
    dorm_bonus_all: float,
    dorm_bonus_elite: float,
    yanhuo_bonus: float,
    dorm_level: int,
    dorm_ambiance: int,
) -> float:
    """包装 evaluate_dorm_recovery() 供宿舍贡献计算使用"""
    from steward_core.dorm_recovery import evaluate_dorm_recovery
    return evaluate_dorm_recovery(
        dorm_ops=dorm_ops,
        target_op=target_op,
        dorm_bonus_all=dorm_bonus_all,
        dorm_bonus_elite=dorm_bonus_elite,
        yanhuo_bonus=yanhuo_bonus,
        dorm_level=dorm_level,
        dorm_ambiance_per_room=dorm_ambiance,
    )


def _baseline_dorm_recovery(
    dorm_ops: list,
    dorm_bonus_all: float,
    dorm_bonus_elite: float,
    yanhuo_bonus: float,
    dorm_level: int,
    dorm_ambiance: int,
) -> float:
    """用虚拟干员评估基准恢复速率，供槽位机会成本定价

    将 baseline 纳入 dorm_ops 以确保 evaluate_dorm_recovery Rule 0
    基础恢复（1.5+0.1*level+0.0004*ambiance）始终参与计算。
    不纳入时若 dorm_ops 为空，空列表导致 if dorm_ops: 为 False，
    Rule 0 被跳过，机会成本低估约 4.0/h（Lv5 宿舍 5000 氛围）。
    """
    from steward_core.models import Operator
    baseline = Operator(char_id="", name="_baseline_")
    return _evaluate_dorm_recovery_for(
        dorm_ops + [baseline], baseline, dorm_bonus_all, dorm_bonus_elite,
        yanhuo_bonus, dorm_level, dorm_ambiance,
    )


def _avg_unassigned_worker_lambda(
    ctx: "SlotContext",
    window_idx: int,
    top_k: int = 3,
) -> float:
    """取未分配生产干员的 top-k lambda 平均值"""
    assigned_ids = ctx.assigned_ids(window_idx)
    lambdas = []
    for op in ctx.operators:
        if op.char_id in assigned_ids:
            continue
        if not (op.has_skill_for("Mfg") or op.has_skill_for("Trade")):
            continue
        lambdas.append(ctx.lambda_ops.get(op.name, ctx.lambda_k))
    if not lambdas:
        return ctx.lambda_k
    top = sorted(lambdas, reverse=True)[:top_k]
    return sum(top) / len(top)
