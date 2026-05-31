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


def contribution(
    ctx: "SlotContext",
    op_name: str,
    facility_type: str,
    window_idx: int = 0,
    D: dict[str, float] | None = None,
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
        base = _dorm_contribution(ctx, op, window_idx, D)
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

    office_perception = 0
    if office_op_name and office_op_name in ctx.op_lookup:
        office_op = ctx.op_lookup[office_op_name]
        if any(sk.buff_id == "hire_spd_bd_n1[000]" for sk in office_op.skills):
            office_perception = params.office_perception_base if params else 20

    bp = compute_buff_pool(
        ctrl_ops, suich_count=suich_count,
        dorm_operators=[o for o in dorm_ops if o],
        dorm_level=dorm_level, layout=layout,
        perception_from_office=office_perception,
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


def _reception_contribution(
    ctx: "SlotContext",
    op: "Operator",
    window_idx: int,
    D: dict[str, float],
) -> float:
    """会客室贡献 = type2状态写入*D + 会客效率->等效Mfg
    Reception 干员不通过 BuffPool 写入全局状态，仅计算直接效率贡献。
    """
    total = 0.0

    eff = max(op.best_efficiency("Reception", "General"), 0.0)
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
) -> float:
    """宿舍贡献 = type2状态写入*D + 恢复速率*lambda"""
    total = 0.0

    ctrl_names = ctx.ops_of_type(window_idx, "Control")

    with_sv = _compute_state_snapshot(
        ctx, window_idx, ctrl_names, extra_dorm_names=[op.name],
    )
    without_sv = _compute_state_snapshot(ctx, window_idx, ctrl_names)

    for d in STATE_DIMS:
        delta = with_sv[d] - without_sv[d]
        if delta != 0.0 and D.get(d, 0.0) > 0:
            total += delta * D[d]

    hours = ctx.params.shift_hours if ctx.params else 12.0
    lambda_val = ctx.lambda_ops.get(op.name, 0.0)
    recovery = op.best_efficiency("Dormitory", "Rest")
    if recovery > 0 and lambda_val > 0:
        total += recovery * hours * lambda_val / 24.0

    return total
