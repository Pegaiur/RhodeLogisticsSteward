"""支撑干员计算"""

from steward_core.constants import BASE_POWER_COUNT
from steward_core.evaluate import evaluate_room
from steward_core.models import Operator
from steward_core.synergy import (
    compute_control_global_bonus,
    compute_buff_pool, ROSEMARY_SUPPORT,
    _has_power_count_modifier,
    control_per_operator_bonus, _is_knight, _PINUS_GROUP,
    _B_ROSEMARY, _B_EBENHOLZ,
)

from .bundle import BUNDLES, SupportResult

T = 12.0


def compute_optimal_support(
    combo_ops: list[Operator],
) -> SupportResult:
    """计算制造站组合所需的最优支撑干员集

    按"加成包"概念：每种制造站 combo 类型决定性地对应一组支撑干员。
    如果 combo 含多种类型（如迷迭香+骑士），支撑集取并集。

    Returns:
        SupportResult(support_map, bundles)
    """
    support: dict[str, set[str]] = {
        "Control": set(),
        "Trade": set(),
        "Dormitory": set(),
        "Office": set(),
    }
    activated_bundles: list[str] = []

    names = {op.name for op in combo_ops}

    # 迷迭香包
    if _B_ROSEMARY in names:
        for facility, ops in ROSEMARY_SUPPORT.items():
            support[facility].update(ops)
        activated_bundles.append("迷迭香包")

    # 骑士包（含红松骑士团，游戏内骑士标签覆盖全体）
    has_knight = any(_is_knight(op) for op in combo_ops)
    if has_knight:
        support["Control"].add("薇薇安娜")
        support["Control"].add("焰尾")  # 骑士中枢天然伴随焰尾
        activated_bundles.append("骑士包")

    # 红松骑士团包（已包含在骑士包中，此处显式标注确保焰尾）
    has_pinus = any(op.group_id == _PINUS_GROUP for op in combo_ops)
    if has_pinus:
        support["Control"].add("焰尾")

    return SupportResult(
        support_map={k: sorted(v) for k, v in support.items()},
        bundles=activated_bundles,
    )


def compute_trade_support(
    combo_ops: list[Operator],
) -> dict[str, list[str]]:
    """计算贸易站组合所需的最优支撑干员集

    与 compute_optimal_support 对称：Trade combo → 锁定的支撑干员。
    孑 → 灵知(中枢)，叙拉古干员 → 八幡海铃(中枢)。

    Returns:
        {"Control": [names], "Trade": [names], "Dormitory": [names]}
    """
    support: dict[str, set[str]] = {
        "Control": set(),
        "Trade": set(),
        "Dormitory": set(),
    }

    names = {op.name for op in combo_ops}

    if "孑" in names:
        support["Control"].add("灵知")

    if any(op.nation_id == "siracusa" for op in combo_ops):
        support["Control"].add("八幡海铃")

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
    support_map = compute_optimal_support(combo_ops).support_map
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

    has_rosmontis = any(op.name == _B_ROSEMARY for op in combo_ops)
    has_ebnhlz = _B_EBENHOLZ in available_support.get("Trade", [])

    # 絮雨在办公室时提供 +20 感知信息（243 Lv3 Office: 2额外招募位×10=20）
    office_perception = 0
    if "絮雨" in available_support.get("Office", []):
        office_perception = 20

    buff_pool = compute_buff_pool(
        control_ops, suich_count=5,
        dorm_operators=dorm_ops, dorm_level=5,
        has_rosmontis_in_mfg=has_rosmontis,
        has_ebnhlz_in_trade=has_ebnhlz,
        ling_mood_below_12=has_rosmontis,
        perception_from_office=office_perception,
    )

    ctrl_bonus = control_per_operator_bonus(control_ops, combo_ops, product)

    # 计算有效发电站数：扫描所有可用干员中持有 power_count 修改器的
    effective_power = BASE_POWER_COUNT + sum(
        1 for op in all_operators
        if op.name not in assigned_ids and _has_power_count_modifier(op)
    )

    score = evaluate_room(
        combo_ops, room_type, product, effective_power, T, global_bonus, buff_pool,
        ctrl_per_op_bonus=ctrl_bonus,
        all_operators=all_operators,
        control_operators=control_ops,
    )

    return score, available_support
