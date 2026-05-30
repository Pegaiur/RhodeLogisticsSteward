"""槽位迭代求解器核心模块

统一槽位加工模型的求解器实现——提取全局状态向量 S，
计算产能偏导数 D = partial P / partial S，
正向计算 contribution = Delta S[d] × D[d]，
使得 Control/Dorm/Power/Reception/Office 干员在同一量纲下可比。

依赖：仅 models, synergy/__init__, 标准库
禁止导入：solver/ 下任何模块（模块边界规则 §1.3）
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from steward_core.models import LayoutConfig
from steward_core.synergy import (
    BuffPool,
    _B_BUFF_CONSUMER_TABLE,
    compute_buff_pool,
    compute_engineering_robots,
)

if TYPE_CHECKING:
    from steward_core.models import Operator, RoomAssignment
    from steward_core.mood_flow import MoodContext

STATE_DIMENSIONS = (
    "perception",
    "yanhuo",
    "engineering_robots",
    "monster_cuisine",
    "silent_resonance",
)

_LAYOUT_243 = LayoutConfig.layout_243()

_MFG_CR_BASE_RATE = 1.0 / 3.0
_MFG_PG_BASE_RATE = 1.0 / 1.2
_TRADE_BASE_LMD_PER_HOUR = 10265.0 / 24.0
_CR_EXP_PER_UNIT = 1000.0
_PG_LMD_PER_UNIT = 500.0

_DEFAULT_SUICH_COUNT = 5
_DEFAULT_DORM_LEVEL = 5
_DEFAULT_OFFICE_PERCEPTION_BASE = 20

_BUFF_CONSUMER_DIMENSION: dict[str, str] = {}
for _name, _entry in _B_BUFF_CONSUMER_TABLE.items():
    pool_key = _entry.pool_key
    if pool_key == "wushu_crystal":
        _BUFF_CONSUMER_DIMENSION[_name] = "yanhuo"
    elif pool_key == "thought_chains":
        _BUFF_CONSUMER_DIMENSION[_name] = "perception"
    else:
        _BUFF_CONSUMER_DIMENSION[_name] = pool_key


@dataclass(frozen=True)
class _Ratios:
    reception_to_mfg: float = 0.10
    office_to_mfg: float = 1.10
    drone_to_mfg: float = 0.5
    xp_lmd: float = 1.3


@dataclass(frozen=True)
class IterationContext:
    """单窗口迭代上下文（不可变，防止副作用）"""

    window_index: int
    window_hours: float
    S: dict[str, float]
    D: dict[str, float]
    lambda_op: dict[str, float]
    ratios: _Ratios = field(default_factory=_Ratios)


def _room_ops_by_type(
    assignments: list["RoomAssignment"],
    room_type: str,
    op_lookup: dict[str, "Operator"],
) -> list["Operator"]:
    names: list[str] = []
    for a in assignments:
        if a.room_type == room_type:
            names.extend(a.operators)
    return [op_lookup[n] for n in names if n in op_lookup]


def _room_has_operator(
    assignments: list["RoomAssignment"],
    room_type: str,
    op_name: str,
) -> bool:
    for a in assignments:
        if a.room_type == room_type and op_name in a.operators:
            return True
    return False


def extract_state_vector(
    assignments: list["RoomAssignment"],
    operators: dict[str, "Operator"],
    layout: LayoutConfig | None = None,
    mood_ctx: "MoodContext | None" = None,
) -> dict[str, float]:
    """从分配方案提取全局状态向量 S 的 5 个维度值

    mood_ctx=None 时走乐观假设（令/夕取最优门控区间），
    与 compute_buff_pool 的默认行为一致。

    Returns:
        {dimension: value}，维度名见 STATE_DIMENSIONS
    """
    if layout is None:
        layout = _LAYOUT_243

    control_ops = _room_ops_by_type(assignments, "Control", operators)
    dorm_ops = _room_ops_by_type(assignments, "Dormitory", operators)
    office_ops = _room_ops_by_type(assignments, "Office", operators)

    has_rosmontis = _room_has_operator(assignments, "Mfg", "迷迭香")
    has_ebnhlz = _room_has_operator(assignments, "Trade", "黑键")
    has_wuyou = _room_has_operator(assignments, "Trade", "乌有")

    office_perception = 0
    office_names = {op.name for op in office_ops}
    if "絮雨" in office_names:
        office_perception = _DEFAULT_OFFICE_PERCEPTION_BASE

    ling_mood_below_12 = False
    xi_mood_below_12: bool | None = None
    if mood_ctx is not None:
        ling_mood_below_12 = mood_ctx.is_below("令", 12.0)
        xi_mood_below_12 = mood_ctx.is_below("夕", 12.0)

    pool = compute_buff_pool(
        control_operators=control_ops,
        suich_count=_DEFAULT_SUICH_COUNT,
        dorm_operators=dorm_ops if dorm_ops else None,
        dorm_level=_DEFAULT_DORM_LEVEL,
        has_rosmontis_in_mfg=has_rosmontis,
        has_ebnhlz_in_trade=has_ebnhlz,
        has_wuyou_in_trade=has_wuyou,
        ling_mood_below_12=ling_mood_below_12,
        xi_mood_below_12=xi_mood_below_12,
        perception_from_office=office_perception,
        layout=layout,
    )

    eng_robots = compute_engineering_robots(layout)
    lancet_in_power = any(
        a.room_type == "Power" and "Lancet-2" in a.operators
        for a in assignments
    )
    if lancet_in_power:
        for op in control_ops:
            if any(s.buff_id == "control_pow_bot[000]" for s in op.skills):
                eng_robots += 2
                break

    return {
        "perception": pool.perception,
        "yanhuo": pool.yanhuo,
        "engineering_robots": eng_robots,
        "monster_cuisine": pool.monster_cuisine,
        "silent_resonance": pool.silent_resonance,
    }


def _get_S_readers(
    assignments: list["RoomAssignment"],
) -> dict[str, set[str]]:
    """返回 {dimension: {reader_names}}，标识当前分配中哪些干员在读取各状态维度

    从 _B_BUFF_CONSUMER_TABLE 获取类型 1f 技能映射。
    """
    readers: dict[str, set[str]] = {d: set() for d in STATE_DIMENSIONS}

    for a in assignments:
        if a.room_type not in ("Mfg", "Trade"):
            continue
        if not a.operators:
            continue
        for name in a.operators:
            if name not in _B_BUFF_CONSUMER_TABLE:
                continue
            entry = _B_BUFF_CONSUMER_TABLE[name]
            if entry.bonus_per <= 0:
                continue
            dim = _BUFF_CONSUMER_DIMENSION.get(name)
            if dim is None:
                continue
            readers[dim].add(name)

    return readers


def _product_base_rate(product: str | None) -> float:
    """产品基础产出率（个/h）"""
    if product == "CombatRecord":
        return _MFG_CR_BASE_RATE
    if product == "PureGold":
        return _MFG_PG_BASE_RATE
    return _TRADE_BASE_LMD_PER_HOUR / _PG_LMD_PER_UNIT


def _product_lmd_per_unit(product: str | None) -> float:
    """产品单位价值（LMD 等值/个），战斗记录通过 xp_lmd_ratio 折算"""
    if product == "CombatRecord":
        return _CR_EXP_PER_UNIT / 1.3
    if product == "PureGold":
        return _PG_LMD_PER_UNIT
    return 1.0


def compute_partial_derivatives(
    assignments: list["RoomAssignment"],
    window_hours: float,
    operators: dict[str, "Operator"],
    drone_multiplier: float = 1.0,
) -> dict[str, float]:
    """计算 P 对各状态维度的偏导数 D[d] = partial P / partial S[d]

    仅遍历有类型 1f 技能的干员（通过 _get_S_readers 判定）。
    D[d] 以 LMD 等值为量纲。

    对于每位类型 1f 读取者 r：
      D[d] += base_rate × window_hours × (bonus_per / per_unit) / 100
            × product_LMD_per_unit × drone_multiplier
    """
    D: dict[str, float] = {d: 0.0 for d in STATE_DIMENSIONS}

    for a in assignments:
        if a.room_type not in ("Mfg", "Trade"):
            continue
        if not a.operators:
            continue

        base_rate = _product_base_rate(a.product)
        unit_lmd = _product_lmd_per_unit(a.product)

        for name in a.operators:
            if name not in _B_BUFF_CONSUMER_TABLE:
                continue
            entry = _B_BUFF_CONSUMER_TABLE[name]
            if entry.target_room not in ("Mfg", "Trade"):
                continue
            if entry.bonus_per <= 0:
                continue
            dim = _BUFF_CONSUMER_DIMENSION.get(name)
            if dim is None:
                continue

            rate = entry.bonus_per / entry.per_unit
            marginal = base_rate * window_hours * rate / 100.0 * unit_lmd * drone_multiplier
            D[dim] += marginal

    return D


def _op_eff_for_room(op: "Operator", room_type: str, product: str | None = None) -> float:
    """干员对指定设施的有效效率值（取最高技能效率）"""
    best = -999.0
    for skill in op.skills:
        if skill.room_type != room_type:
            continue
        if product is not None and product not in skill.efficient.raw and "all" not in skill.efficient.raw:
            continue
        eff = skill.efficient.get(product) if product else skill.efficient.max_value()
        if eff > best:
            best = eff
    return max(best, 0.0)


def _compute_state_delta_for_control(
    op: "Operator",
    assignments: list["RoomAssignment"],
    operators: dict[str, "Operator"],
    mood_ctx: "MoodContext | None" = None,
) -> dict[str, float]:
    """计算干员在 Control 中对各状态维度的预期写入量

    通过差分模拟：将 op 加入当前中枢后重新计算 S 向量，
    返回增量。已在中枢的干员返回全零。
    """
    control_ops = _room_ops_by_type(assignments, "Control", operators)
    control_names = {o.name for o in control_ops}
    if op.name in control_names:
        return {d: 0.0 for d in STATE_DIMENSIONS}

    S_before = extract_state_vector(assignments, operators, mood_ctx=mood_ctx)

    simulated_op_names = [o.name for o in control_ops] + [op.name]
    simulated_ctrl = [operators[n] for n in simulated_op_names if n in operators]
    new_ctrl_names = set(simulated_op_names)

    dorm_ops = _room_ops_by_type(assignments, "Dormitory", operators)
    has_rosmontis = _room_has_operator(assignments, "Mfg", "迷迭香")
    has_ebnhlz = _room_has_operator(assignments, "Trade", "黑键")
    has_wuyou = _room_has_operator(assignments, "Trade", "乌有")

    office_ops = _room_ops_by_type(assignments, "Office", operators)
    office_perception = 0
    if any(o.name == "絮雨" for o in office_ops):
        office_perception = 20

    ling_mood_below_12 = False
    xi_mood_below_12: bool | None = None
    if mood_ctx is not None:
        ling_mood_below_12 = mood_ctx.is_below("令", 12.0)
        xi_mood_below_12 = mood_ctx.is_below("夕", 12.0)

    pool_after = compute_buff_pool(
        control_operators=simulated_ctrl,
        suich_count=_DEFAULT_SUICH_COUNT,
        dorm_operators=dorm_ops if dorm_ops else None,
        dorm_level=_DEFAULT_DORM_LEVEL,
        has_rosmontis_in_mfg=has_rosmontis,
        has_ebnhlz_in_trade=has_ebnhlz,
        has_wuyou_in_trade=has_wuyou,
        ling_mood_below_12=ling_mood_below_12,
        xi_mood_below_12=xi_mood_below_12,
        perception_from_office=office_perception,
        layout=_LAYOUT_243,
    )

    S_after: dict[str, float] = {
        "perception": pool_after.perception,
        "yanhuo": pool_after.yanhuo,
        "engineering_robots": compute_engineering_robots(_LAYOUT_243),
        "monster_cuisine": pool_after.monster_cuisine,
        "silent_resonance": pool_after.silent_resonance,
    }

    return {d: S_after[d] - S_before[d] for d in STATE_DIMENSIONS}


def _compute_state_delta_for_dorm(
    op: "Operator",
    assignments: list["RoomAssignment"],
    operators: dict[str, "Operator"],
) -> dict[str, float]:
    """计算干员在 Dormitory 中对各状态维度的预期写入量（差分模拟）"""
    dorm_ops = _room_ops_by_type(assignments, "Dormitory", operators)
    dorm_names = {o.name for o in dorm_ops}
    if op.name in dorm_names:
        return {d: 0.0 for d in STATE_DIMENSIONS}

    S_before = extract_state_vector(assignments, operators)

    simulated_dorm = dorm_ops + [op]
    control_ops = _room_ops_by_type(assignments, "Control", operators)
    has_rosmontis = _room_has_operator(assignments, "Mfg", "迷迭香")
    has_ebnhlz = _room_has_operator(assignments, "Trade", "黑键")
    has_wuyou = _room_has_operator(assignments, "Trade", "乌有")

    office_ops = _room_ops_by_type(assignments, "Office", operators)
    office_perception = 0
    if any(o.name == "絮雨" for o in office_ops):
        office_perception = 20

    pool_after = compute_buff_pool(
        control_operators=control_ops,
        suich_count=_DEFAULT_SUICH_COUNT,
        dorm_operators=simulated_dorm,
        dorm_level=_DEFAULT_DORM_LEVEL,
        has_rosmontis_in_mfg=has_rosmontis,
        has_ebnhlz_in_trade=has_ebnhlz,
        has_wuyou_in_trade=has_wuyou,
        perception_from_office=office_perception,
        layout=_LAYOUT_243,
    )

    S_after: dict[str, float] = {
        "perception": pool_after.perception,
        "yanhuo": pool_after.yanhuo,
        "engineering_robots": compute_engineering_robots(_LAYOUT_243),
        "monster_cuisine": pool_after.monster_cuisine,
        "silent_resonance": pool_after.silent_resonance,
    }

    return {d: S_after[d] - S_before[d] for d in STATE_DIMENSIONS}


def _compute_type3_contribution(
    op: "Operator",
    assignments: list["RoomAssignment"],
) -> float:
    """计算类型 3 全局注入的贡献值

    按"受影响槽位数 × 槽位均值"估算。
    首期简化：仅处理阿米娅和杜宾这种有明确全局注入的干员。
    """
    from steward_core.synergy import compute_control_global_bonus

    mfg_slots = sum(
        len(a.operators) for a in assignments
        if a.room_type == "Mfg" and a.operators
    )
    trade_slots = sum(
        len(a.operators) for a in assignments
        if a.room_type == "Trade" and a.operators
    )

    control_ops = _room_ops_by_type(assignments, "Control", {op.name: op})
    if op.name not in {o.name for o in control_ops}:
        simulated = [op]
    else:
        simulated = control_ops

    bonus = compute_control_global_bonus(simulated)

    mfg_base_avg = (
        0.5 * _MFG_CR_BASE_RATE * _CR_EXP_PER_UNIT / 1.3
        + 0.5 * _MFG_PG_BASE_RATE * _PG_LMD_PER_UNIT
    )

    value = 0.0
    value += bonus.mfg_bonus * mfg_slots * mfg_base_avg * 24.0 / 100.0
    value += bonus.trade_bonus * trade_slots * _TRADE_BASE_LMD_PER_HOUR * 24.0 / 100.0

    return value


def contribution(
    op_name: str,
    facility: str,
    ctx: IterationContext,
    operators: dict[str, "Operator"],
    assignments: list["RoomAssignment"],
) -> float:
    """统一的 contribution 计算入口，按 facility 分派到内部 helper

    首期 lambda ≡ 0，公式中不含 -lambda × hours 项（留待第二期添加）。

    Returns:
        该干员在指定设施中的预期边际贡献值（LMD 等值/天量纲）。
    """
    op = operators.get(op_name)
    if op is None:
        return float("-inf")

    if facility == "Control":
        return _contribution_control(op, ctx, operators, assignments)
    elif facility == "Power":
        return _contribution_power(op, ctx)
    elif facility == "Reception":
        return _contribution_reception(op, ctx)
    elif facility == "Office":
        return _contribution_office(op, ctx)
    elif facility == "Dormitory":
        return _contribution_dorm(op, ctx, assignments, operators)
    else:
        return float("-inf")


def _contribution_control(
    op: "Operator",
    ctx: IterationContext,
    operators: dict[str, "Operator"],
    assignments: list["RoomAssignment"],
) -> float:
    """Control 干员 contribution = 类型 2 状态写入 × D + 类型 3 全局注入"""
    state_delta = _compute_state_delta_for_control(op, assignments, operators)
    state_value = sum(
        state_delta.get(d, 0.0) * ctx.D.get(d, 0.0)
        for d in STATE_DIMENSIONS
    )
    type3_value = _compute_type3_contribution(op, assignments)
    return state_value + type3_value


def _contribution_power(
    op: "Operator",
    ctx: IterationContext,
) -> float:
    """Power 干员 contribution = power_eff × drone_to_mfg_ratio × mfg_base_rate_avg / xp_lmd_ratio × 24h"""
    eff = _op_eff_for_room(op, "Power")
    if eff <= 0:
        return 0.0

    mfg_base_avg_lmd_hourly = (
        0.5 * _MFG_CR_BASE_RATE * _CR_EXP_PER_UNIT / ctx.ratios.xp_lmd
        + 0.5 * _MFG_PG_BASE_RATE * _PG_LMD_PER_UNIT
    )

    return eff * ctx.ratios.drone_to_mfg * mfg_base_avg_lmd_hourly * 24.0


def _contribution_reception(
    op: "Operator",
    ctx: IterationContext,
) -> float:
    """Reception 干员 contribution = reception_eff × reception_to_mfg_ratio × mfg_base_rate_avg / xp_lmd_ratio × 24h"""
    eff = _op_eff_for_room(op, "Reception")
    if eff <= 0:
        return 0.0

    mfg_base_avg_lmd_hourly = (
        0.5 * _MFG_CR_BASE_RATE * _CR_EXP_PER_UNIT / ctx.ratios.xp_lmd
        + 0.5 * _MFG_PG_BASE_RATE * _PG_LMD_PER_UNIT
    )

    return eff * ctx.ratios.reception_to_mfg * mfg_base_avg_lmd_hourly * 24.0


def _contribution_office(
    op: "Operator",
    ctx: IterationContext,
) -> float:
    """Office 干员 contribution = office_eff × office_to_mfg_ratio × mfg_base_rate_avg / xp_lmd_ratio × 24h"""
    eff = _op_eff_for_room(op, "Office")
    if eff <= 0:
        return 0.0

    mfg_base_avg_lmd_hourly = (
        0.5 * _MFG_CR_BASE_RATE * _CR_EXP_PER_UNIT / ctx.ratios.xp_lmd
        + 0.5 * _MFG_PG_BASE_RATE * _PG_LMD_PER_UNIT
    )

    return eff * ctx.ratios.office_to_mfg * mfg_base_avg_lmd_hourly * 24.0


def _contribution_dorm(
    op: "Operator",
    ctx: IterationContext,
    assignments: list["RoomAssignment"],
    operators: dict[str, "Operator"],
) -> float:
    """Dormitory 干员 contribution = 类型 2 状态写入 × D + recovery_rate × hours × lambda

    首期 lambda ≡ 0，恢复贡献简化为仅计算状态写入部分。
    """
    state_delta = _compute_state_delta_for_dorm(op, assignments, operators)
    state_value = sum(
        state_delta.get(d, 0.0) * ctx.D.get(d, 0.0)
        for d in STATE_DIMENSIONS
    )

    return state_value