"""统一贡献评分 — contribution(op, facility_type, ctx, window_idx) -> LMD等值/窗口

中枢/发电/会客/办公室/宿舍的干员选择统一通过边际贡献评分。
Control 干员贡献含 mood 截断（与 evaluate_room t_red 等价），
宿舍恢复价值由 mood_deficit × recovery_rate × eff_weight 驱动。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from steward_core.models import LayoutConfig
from steward_core.constants import (
    MFG_CR_BASE_RATE, MFG_PG_BASE_RATE, TRADE_BASE_LMD_PER_DAY,
    CR_EXP_PER_UNIT, PG_LMD_PER_UNIT,
)
from steward_core.synergy import compute_control_global_bonus, control_per_operator_bonus, compute_control_reception_bonus
from steward_core.synergy import _OP_PLATFORM_NAMES, compute_facility_group_bonus, operator_estimated_efficiency
from .context import STATE_DIMS, mood_is_viable
from .partials import _product_base_rate, _product_lmd_per_unit

if TYPE_CHECKING:
    from steward_core.models import Operator
    from steward_core.mood_flow import MoodContext
    from .context import SlotContext

_LAYOUT_243 = LayoutConfig.layout_243()

_TRADE_BASE_LMD_PER_HOUR = TRADE_BASE_LMD_PER_DAY / 24.0

_RECEPTION_TO_MFG_RATIO = 0.10
_OFFICE_TO_MFG_RATIO = 1.10
_DRONE_TO_MFG_RATIO = 0.5

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

# ─── Reception 条件型 buff 表 ────────────────────────────────────

class ReceptionCondition:
    """会客室条件型 buff 条目"""
    __slots__ = ("cond_type", "bonus", "target")

    def __init__(self, cond_type: str, bonus: float, target: str | None = None):
        self.cond_type = cond_type
        self.bonus = bonus
        self.target = target

# buff_id → ReceptionCondition
# cond_type: "solo"=仅自身, "pair"=指定干员同房, "faction"=同阵营, "dorm_has"=目标在宿舍,
#            "office_slots"=额外招募位驱动(bonus=每格%), "monster_cuisine"=魔物料理驱动(bonus=每点%)
_RECEPTION_CONDITIONAL: dict[str, ReceptionCondition] = {
    "meet_spd_condChar[000]":          ReceptionCondition("solo", 35),
    "meet_spd&cost_condChar[000]":     ReceptionCondition("solo", 50),
    "meet_spd&cost_condChar[001]":     ReceptionCondition("solo", 15),
    "meet_spd&cost_condChar[011]":     ReceptionCondition("solo", 35),
    "meet_spd&cost_condChar[020]":     ReceptionCondition("solo", 15),
    "meet_spd&cost_condChar[021]":     ReceptionCondition("solo", 35),
    "meet_spd&bd[000]":                ReceptionCondition("pair", 15, "提丰"),
    "meet_spd&bd[010]":                ReceptionCondition("pair", 15, "提丰"),
    "meet_spd&bd[100]":                ReceptionCondition("pair", 30, "铃兰"),
    "meet_spd&sami[000]":              ReceptionCondition("faction", 5, "sami"),
    "meet_spd&sami[100]":              ReceptionCondition("faction", 15, "blacksteel"),
    "meet_spd&sami[110]":              ReceptionCondition("faction", 20, "blacksteel"),
    "meet_spd_ext&P[000]":             ReceptionCondition("dorm_has", 10, "菲亚梅塔"),
    # 动态加成（bonus 为乘数，不依赖同房间组合）
    "meet_spd&clue[000]":              ReceptionCondition("office_slots", 5),
    "meet_spd_bd[001]":                ReceptionCondition("monster_cuisine", 2),
}

# ─── 会客室/办公室 故意不建模的机制性 buff ───────────────────────
# 以下 buff 效率=0，效果为线索派系倾向/未拥有偏向/必定获得等，
# 与求解器优化目标（Mfg/Trade 产值最大化）无关，故意不建模。
#
# 【会客室 — 线索派系倾向 (meet_team)】
#   meet_team[020]     梅      更容易获得企鹅物流线索
#   meet_team[050]     苦艾    更容易获得乌萨斯学生自治团线索
#   meet_team[060]     极境    更容易获得罗德岛制药线索
#   meet_team[070]     柏喙    更容易获得格拉斯哥帮线索
#   meet_team&char[000] 哈罗德  提升另一干员所属派系的线索倾向
#
# 【会客室 — 线索派系补偿 (meet_flag)】
#   meet_flag[010]     巡林者  非莱茵生命时 ↑莱茵生命概率
#   meet_flag[040]     耶拉    非喀兰贸易时 ↑喀兰贸易概率
#   meet_flag[050]     苦艾    非乌萨斯时 ↑乌萨斯概率
#   meet_flag[060]     极境    非罗德岛制药时 ↑罗德岛制药概率
#   meet_flag[070]     柏喙    非格拉斯哥帮时 ↑格拉斯哥帮概率
#
# 【会客室 — 线索拥有偏向】
#   meet_spd_notOwned[000] 车尔尼  易获未拥有线索
#   meet_spd_notOwned[001] 谜图    同上
#   meet_spd_notOwned[002] 玛吉莉  同上
#   meet_spd_notOwned[003] 陈(假日) 同上
#   meet_spd_notOwned&exchange[000] 维荻  线索交流时易获未拥有
#   meet_spd_Owned[000]    尤丽卡  易获已拥有线索
#
# 【会客室 — 线索交流期间加速】
#   meet_spd&exchange[000] 凯珀    线索交流时搜集速度+30%
#   meet_spd&exchange[001] 凯恩    同上
#   （需要感知线索交流状态，当前无此上下文）
#
# 【会客室 — 必定获得 (solo 耗尽心情后)】
#   meet_spd&condChar_mustget[000] 赫雅克  solo 连续消耗>16心情，下次必定莱茵生命
#   meet_spd&condChar_mustget[100] 奥达    solo 连续消耗>16心情，下次必定罗德岛制药
#
# 【办公室 — 无产值影响的机制性 buff】
#   （全部 43 条 HIRE buff 中仅 hire_spd_cost&extra[000] 效率=0 且无产值影响，
#    已在 _office_contribution() 中建模）


def contribution(
    ctx: "SlotContext",
    op_name: str,
    facility_type: str,
    window_idx: int = 0,
    D: dict[str, float] | None = None,
    room_index: int = 0,
    mood_ctx: "MoodContext | None" = None,
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
        if mood_ctx is not None:
            burn = _mood_burn_for_control(ctx, mood_ctx, op_name)
            if burn > 0:
                current = mood_ctx.mood_of(op_name)
                effective = min(current / max(burn * hours, 0.01), 1.0)
                base *= effective
    elif facility_type == "Power":
        base = _power_contribution(ctx, op, window_idx, D)
    elif facility_type == "Reception":
        base = _reception_contribution(ctx, op, window_idx, D)
    elif facility_type == "Office":
        base = _office_contribution(ctx, op, window_idx, D)
    elif facility_type == "Dormitory":
        return _dorm_contribution(ctx, op, window_idx, D, room_index, mood_ctx=mood_ctx)
    else:
        return float("-inf")

    return base


def _mfg_base_rate_lmd_avg() -> float:
    """Mfg CR/PG 加权平均单位小时 LMD 等值（243布局 0.5:0.5）"""
    return (
        0.5 * MFG_CR_BASE_RATE * _product_lmd_per_unit("CombatRecord")
        + 0.5 * MFG_PG_BASE_RATE * _product_lmd_per_unit("PureGold")
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
    total += _recovery_marginal(ctx, op.name, existing_names, window_idx)
    return total


_WORK_FACILITIES = ("Mfg", "Trade", "Office", "Power", "Reception")


def _compute_recovery_value(
    ctx: "SlotContext",
    control_names: list[str],
    window_idx: int,
) -> float:
    """给定中枢配置的心情恢复贡献总值（LMD 等值/窗口）

    mood_saved_per_op = recovery_rate × hours
    value = Σ mood_saved × eff_weight × base_LMD_rate

    recovery_rate = mp_cost_count × 0.05（仅持有 control_mp_cost* 技能的干员）
                  + Σ per-operator global recovery buffs（玛恩纳 +0.1 + spread）
    """
    hours = ctx.params.shift_hours if ctx.params else 12.0
    base_lmd = _mfg_base_rate_lmd_avg()
    work_names = ctx.ops_of_type(window_idx, "Mfg") + ctx.ops_of_type(window_idx, "Trade")

    if not work_names:
        return 0.0

    # 仅统计持有 control_mp_cost* 技能的干员（+0.05/h），非全员
    mp_cost_count = 0
    has_mlynar = False
    for cname in control_names:
        cop = ctx.op_lookup.get(cname)
        if cop is None:
            continue
        if any(s.buff_id.startswith("control_mp_cost[") for s in cop.skills):
            mp_cost_count += 1
        if any(s.buff_id == "control_mp_lonely[000]" for s in cop.skills):
            has_mlynar = True

    recovery = mp_cost_count * 0.05
    if has_mlynar:
        recovery += 0.1 + mp_cost_count * 0.05  # global + spread

    if recovery <= 0:
        return 0.0

    mood_saved_per_op = recovery * hours
    total = 0.0
    for name in work_names:
        eff = ctx.op_peak_eff.get(name, 0.0)
        eff_weight = max(eff / 30.0, 0.1)
        total += mood_saved_per_op * eff_weight * base_lmd

    return total


def _recovery_marginal(
    ctx: "SlotContext",
    candidate_name: str,
    existing_names: list[str],
    window_idx: int,
) -> float:
    """该中枢候选的边际恢复贡献 = value(with) - value(without)"""
    with_val = _compute_recovery_value(ctx, existing_names + [candidate_name], window_idx)
    without_val = _compute_recovery_value(
        ctx, [n for n in existing_names if n != candidate_name], window_idx,
    )
    return with_val - without_val


def _reception_conditional_bonus(
    combo: list["Operator"],
    ctx: "SlotContext",
    window_idx: int,
    monster_cuisine: float | None = None,
) -> float:
    """计算会客室组合的条件型 buff 加成总和

    遍历 combo 中每个干员的活跃技能，匹配 _RECEPTION_CONDITIONAL 表：
    - solo:           len(combo)==1 时激活
    - pair:           目标干员在 combo 中时激活
    - faction:        combo 中有同 nation_id 的干员时激活
    - dorm_has:       目标干员在宿舍时激活（乐观假设：宿舍阶段会保证该干员入宿）
    - office_slots:   额外招募位 × bonus%（bonus=每格%）
    - monster_cuisine: 魔物料理 × bonus%（bonus=每点%），mc 由调用方传入
    """
    names = {op.name for op in combo}
    bonus = 0.0

    params = ctx.params
    office_level = params.office_level if params else 3
    extra_slots = max(office_level - 1, 0)

    if monster_cuisine is None:
        monster_cuisine = 0.0

    for op in combo:
        for sk in op.active_skills_for("Reception"):
            entry = _RECEPTION_CONDITIONAL.get(sk.buff_id)
            if entry is None:
                continue
            ct = entry.cond_type
            if ct == "solo":
                if len(combo) == 1:
                    bonus += entry.bonus
            elif ct == "pair":
                if entry.target in names:
                    bonus += entry.bonus
            elif ct == "faction":
                faction_nations = _FACTION_NATION_MAP.get(entry.target, entry.target)
                if any(getattr(o, "nation_id", None) == faction_nations
                       for o in combo if o.name != op.name):
                    bonus += entry.bonus
            elif ct == "dorm_has":
                dorm_names = set(ctx.ops_of_type(window_idx, "Dormitory"))
                if entry.target in dorm_names:
                    bonus += entry.bonus
                else:
                    assigned_all = {
                        n for t in ["Control", "Mfg", "Trade", "Power",
                                     "Reception", "Office", "Training", "Workshop"]
                        for n in ctx.ops_of_type(window_idx, t)
                    }
                    if entry.target not in assigned_all:
                        bonus += entry.bonus
            elif ct == "office_slots":
                bonus += entry.bonus * extra_slots
            elif ct == "monster_cuisine":
                bonus += entry.bonus * monster_cuisine

    return bonus


_FACTION_NATION_MAP: dict[str, str] = {
    "sami": "sami",
    "blacksteel": "blacksteel",
}


def _build_reception_pool(
    ctx: "SlotContext",
    window_idx: int,
    mood_ctx: "MoodContext | None" = None,
    mood_threshold: float = 0.0,
) -> list["Operator"]:
    """构建会客室候选池，含使能者（无 Reception 技能但被 pair 条件引用的干员）"""
    assigned_ids = ctx.assigned_ids(window_idx)
    pool = [op for op in ctx.operators
            if op.char_id not in assigned_ids
            and op.has_skill_for("Reception", "General")
            and mood_is_viable(op.name, mood_ctx, mood_threshold)]

    existing = {op.name for op in pool}
    for op in pool:
        for sk in op.active_skills_for("Reception"):
            entry = _RECEPTION_CONDITIONAL.get(sk.buff_id)
            if entry and entry.cond_type == "pair" and entry.target:
                enabler = ctx.op_lookup.get(entry.target)
                if enabler and enabler.name not in existing \
                        and enabler.char_id not in assigned_ids \
                        and mood_is_viable(enabler.name, mood_ctx, mood_threshold):
                    pool.append(enabler)
                    existing.add(enabler.name)

    return pool


def _snapshot_for_reception(
    ctx: "SlotContext",
    window_idx: int,
    ctrl_names: list[str],
) -> float:
    """获取当前窗口的魔物料理值，供会客室条件型 buff 使用"""
    sv = _compute_state_snapshot(ctx, window_idx, ctrl_names)
    return sv.get("monster_cuisine", 0.0)


def _select_reception_combo(
    ctx: "SlotContext",
    window_idx: int,
    D: dict[str, float],
    mood_ctx: "MoodContext | None" = None,
    mood_threshold: float = 0.0,
) -> list[str]:
    """枚举会客室组合 (C(N,1)+C(N,2))，取总分最高的组合

    Reception 仅 2 槽位，候选池 ≤25 人，穷举开销可忽略。
    需要组合评估的原因：条件型 buff（solo/pair/faction/dorm_has）
    的单点效率取决于同房间配置，贪心单点无法感知。
    """
    import itertools

    pool = _build_reception_pool(ctx, window_idx, mood_ctx, mood_threshold)
    if not pool:
        return []

    max_slots = 2
    combos = []
    for r in range(1, min(max_slots, len(pool)) + 1):
        combos.extend(itertools.combinations(pool, r))

    if not combos:
        return []

    best_score = float("-inf")
    best_combo: list[str] = []

    reception_level = ctx.params.reception_level if ctx.params else 3
    dorm_ambiance = ctx.params.dorm_ambiance if ctx.params else 5000
    hours = ctx.params.shift_hours if ctx.params else 12.0
    base_lmd = _mfg_base_rate_lmd_avg()

    ctrl_names = ctx.ops_of_type(window_idx, "Control")
    mc_snapshot = _snapshot_for_reception(ctx, window_idx, ctrl_names)

    ctrl_ops_objects = [ctx.op_lookup[n] for n in ctrl_names if n in ctx.op_lookup]

    for combo in combos:
        combo_list = list(combo)
        combo_names = {op.name for op in combo_list}
        total = 0.0

        for op in combo_list:
            implicit = _reception_implicit_bonus(op, reception_level, dorm_ambiance)
            skill_eff = max(operator_estimated_efficiency(op, "Reception", "General"), 0.0)
            total += (implicit + skill_eff) * _RECEPTION_TO_MFG_RATIO / 100.0 * base_lmd * hours

        total += _reception_conditional_bonus(combo_list, ctx, window_idx, mc_snapshot) \
            * _RECEPTION_TO_MFG_RATIO / 100.0 * base_lmd * hours

        ctrl_rec_bonus = compute_control_reception_bonus(
            ctrl_ops_objects, ctx, window_idx, reception_names=combo_names,
        )
        total += ctrl_rec_bonus * _RECEPTION_TO_MFG_RATIO / 100.0 * base_lmd * hours

        if total > best_score:
            best_score = total
            best_combo = [op.name for op in combo_list]

    return best_combo


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
        mfg_rooms = len({a.room_index for a in ctx.slots_of_type(window_idx, "Mfg") if not a.is_empty})
        affected = max(mfg_rooms, 1)
        base_lmd = _mfg_base_rate_lmd_avg()
        total += mfg_bonus * affected * base_lmd * hours / 100.0

    if trade_bonus != 0:
        trade_rooms = len({a.room_index for a in ctx.slots_of_type(window_idx, "Trade") if not a.is_empty})
        affected = max(trade_rooms, 1)
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


def _power_dynamic_bonus(
    op: "Operator",
    ctx: "SlotContext",
) -> float:
    """不依赖同房间组合的发电站动态加成

    覆盖 drone_cap（Greyy2 巡线框架）和 dorm_levels（Philae 灵河共鸣）。
    """
    bonus = 0.0
    params = ctx.params

    for sk in op.active_skills_for("Power"):
        if sk.buff_id == "power_rec_drone[000]":
            drone_cap = params.drone_cap if params else 235
            bonus += min(drone_cap // 10, 25)
        elif sk.buff_id == "power_rec_spd&dorm&lv[000]":
            dorm_levels = params.dorm_levels_sum if params else 20
            bonus += dorm_levels * 0.5

    return bonus


def _power_conditional_bonus(
    op: "Operator",
    ctx: "SlotContext",
    window_idx: int,
) -> float:
    """检查跨房间/同房间条件，返回条件型无人机充能加成

    power_rec_spd_P[001]（Phonor 咒文共鸣：逻各斯在训练室）故意不建模——
    Training 是 NON_WORK_FACILITY，求解器不分配干员到训练室。
    """
    bonus = 0.0

    for sk in op.active_skills_for("Power"):
        if sk.buff_id == "power_rec_spd_P[000]":
            if "凯尔希" in ctx.ops_of_type(window_idx, "Control"):
                bonus += 5.0
        elif sk.buff_id == "power_rec_spd_ext&faction[000]":
            power_ops = ctx.ops_of_type(window_idx, "Power")
            if any(
                pn != op.name
                and (other := ctx.op_lookup.get(pn))
                and getattr(other, "nation_id", "") == "laterano"
                for pn in power_ops
            ):
                bonus += 5.0
        elif sk.buff_id == "power_rec_spd_ext&tag[000]":
            power_ops = ctx.ops_of_type(window_idx, "Power")
            if any(pn in _OP_PLATFORM_NAMES for pn in power_ops if pn != op.name):
                bonus += 5.0

    return bonus


def _power_contribution(
    ctx: "SlotContext",
    op: "Operator",
    window_idx: int,
    D: dict[str, float],
) -> float:
    """发电站贡献 = (发电效率 + 动态加成 + 条件型加成) × 无人机折算 + Mfg直接加成

    Power 干员不通过 BuffPool 写入全局状态。
    动态加成：drone_cap（巡线框架）、dorm_levels（灵河共鸣）。
    条件型加成：凯尔希中枢联动、拉特兰/作业平台同房。
    power_prod_spd_P[000] 野鬃 Mfg +5% 为直接 Mfg 加成，不经无人机折算。
    """
    total = 0.0

    eff = max(operator_estimated_efficiency(op, "Power", ""), 0.0)
    eff += _power_dynamic_bonus(op, ctx)
    eff += _power_conditional_bonus(op, ctx, window_idx)

    hours = ctx.params.shift_hours if ctx.params else 12.0
    base_lmd = _mfg_base_rate_lmd_avg()
    total += eff * _DRONE_TO_MFG_RATIO / 100.0 * base_lmd * hours

    # power_prod_spd_P[000]（Justice Knight "滴滴，启动！"）：野鬃在 Mfg 时直接 +5%
    for sk in op.active_skills_for("Power"):
        if sk.buff_id == "power_prod_spd_P[000]":
            if "野鬃" in ctx.ops_of_type(window_idx, "Mfg"):
                total += 5.0 * base_lmd * hours / 100.0

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


def _reception_individual_bonus(
    op: "Operator",
    ctx: "SlotContext",
    window_idx: int,
) -> float:
    """计算不依赖同房间组合的个人条件型 buff 加成

    覆盖 office_slots（维荻广交义友）和 monster_cuisine（莱欧斯饱餐的干劲）。
    这些 buff 的加成与同房间是否有其他干员无关。
    """
    bonus = 0.0
    params = ctx.params
    office_level = params.office_level if params else 3
    extra_slots = max(office_level - 1, 0)

    for sk in op.active_skills_for("Reception"):
        entry = _RECEPTION_CONDITIONAL.get(sk.buff_id)
        if entry is None:
            continue
        if entry.cond_type == "office_slots":
            bonus += entry.bonus * extra_slots
        elif entry.cond_type == "monster_cuisine":
            ctrl_names = ctx.ops_of_type(window_idx, "Control")
            mc = _snapshot_for_reception(ctx, window_idx, ctrl_names)
            bonus += entry.bonus * mc

    return bonus


def _reception_contribution(
    ctx: "SlotContext",
    op: "Operator",
    window_idx: int,
    D: dict[str, float],
) -> float:
    """会客室贡献 = 隐式加成 + 技能效率 + 个人条件型 buff → 等效Mfg
    Reception 干员不通过 BuffPool 写入全局状态。
    隐式加成包括: 非涣散/稀有度/精英阶段/会客室等级/宿舍氛围。
    个人条件型 buff 包括: office_slots（维荻广交义友）、monster_cuisine（莱欧斯饱餐的干劲）。
    """
    total = 0.0

    reception_level = ctx.params.reception_level if ctx.params else 3
    dorm_ambiance = ctx.params.dorm_ambiance if ctx.params else 5000
    implicit = _reception_implicit_bonus(op, reception_level, dorm_ambiance)
    skill_eff = max(operator_estimated_efficiency(op, "Reception", "General"), 0.0)
    dynamic = _reception_individual_bonus(op, ctx, window_idx)
    eff = implicit + skill_eff + dynamic

    hours = ctx.params.shift_hours if ctx.params else 12.0
    base_lmd = _mfg_base_rate_lmd_avg()
    ctrl_names = ctx.ops_of_type(window_idx, "Control")
    if ctrl_names:
        ctrl_ops_list = [ctx.op_lookup[n] for n in ctrl_names if n in ctx.op_lookup]
        ctrl_rec_bonus = compute_control_reception_bonus(ctrl_ops_list, ctx, window_idx)
        eff += ctrl_rec_bonus
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

    eff = max(operator_estimated_efficiency(op, "Office", "HR"), 0.0)
    office_level = ctx.params.office_level if ctx.params else 3
    extra_slots = max(office_level - 1, 0)
    if any(sk.buff_id == "hire_spd_cost&extra[000]" for sk in op.active_skills_for("Office")):
        eff += extra_slots * 10.0
    all_assignments = ctx.build_all_assignments(window_idx)
    if all_assignments:
        eff += compute_facility_group_bonus(op, all_assignments, "Office")
    if "琴柳" in ctrl_names:
        if 5.0 + eff < 30.0:
            eff += 20.0
    hours = ctx.params.shift_hours if ctx.params else 12.0
    base_lmd = _mfg_base_rate_lmd_avg()
    total += eff * _OFFICE_TO_MFG_RATIO / 100.0 * base_lmd * hours

    return total


def _mood_burn_for_control(
    ctx: "SlotContext",
    mood_ctx: "MoodContext",
    op_name: str,
) -> float:
    """估算控制中枢干员的心情消耗率

    应使用 _control_burn 精确计算，但其依赖 control_operators 列表
    （Phase C 期间尚未设置）。此处用 work_burn 近似——
    对绝大多数干员无差异（wisdel/mlynar 边际情况除外）。
    """
    slots = ctx.params.control_max_slots if ctx.params else 5
    return mood_ctx.work_burn(op_name, "Control", slots)


def _dorm_contribution(
    ctx: "SlotContext",
    op: "Operator",
    window_idx: int,
    D: dict[str, float],
    room_index: int,
    mood_ctx: "MoodContext | None" = None,
) -> float:
    """宿舍贡献 = type2状态写入*D + 自恢复价值 + 室友恢复增量

    恢复价值不再依赖 lambda——改用 mood deficit × recovery_rate × base_lmd × eff_weight。
    """
    total = 0.0
    hours = ctx.params.shift_hours if ctx.params else 12.0
    mood_full = ctx.params.mood_full if ctx.params else 24.0

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

    room_ops_names = ctx.room_ops(window_idx, "Dormitory", room_index)
    existing_names = [n for n in room_ops_names if n]
    existing_ops = [ctx.op_lookup[n] for n in existing_names if n in ctx.op_lookup]

    # 部分1.5: 被恢复者自身恢复价值
    if mood_ctx is not None:
        current = mood_ctx.mood_of(op.name)
        if current < mood_full - 0.01:
            all_dorm_ops = existing_ops + [op]
            recovery_rate = _evaluate_dorm_recovery_for(
                all_dorm_ops, op, dorm_bonus_all, dorm_bonus_elite,
                yanhuo_bonus, dorm_level, amb,
            )
            mood_deficit = mood_full - current
            recoverable = min(mood_deficit, recovery_rate * hours)
            eff = ctx.op_peak_eff.get(op.name, 0.0)
            eff_weight = max(eff / 30.0, 0.1)
            total += recoverable * _mfg_base_rate_lmd_avg() * eff_weight

    # 部分2: 室友恢复增量
    if mood_ctx is not None and existing_names:
        for roommate_name in existing_names:
            roommate = ctx.op_lookup.get(roommate_name)
            if roommate is None:
                continue
            rm_mood = mood_ctx.mood_of(roommate_name)
            if rm_mood >= mood_full - 0.01:
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
            if delta_rec > 0:
                rm_eff = ctx.op_peak_eff.get(roommate_name, 0.0)
                rm_eff_weight = max(rm_eff / 30.0, 0.1)
                total += delta_rec * hours * _mfg_base_rate_lmd_avg() * rm_eff_weight

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
