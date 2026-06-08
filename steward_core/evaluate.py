"""房间效率评估（共享模块）

合并 solver._evaluate_room_combo 与 production._room_efficiency_integral，
确保排班评分与产出报告使用完全一致的计算口径。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from steward_core.models import Operator, LayoutConfig
from steward_core.token_source import compute_room_tokens
from steward_core.efficiency_fn import constant_efficiency, integrate_segments, stepped_efficiency
from steward_core.synergy import (
    synergy_pair, synergy_skill_count, synergy_automation,
    synergy_facility_count, synergy_buff_pool_consumer,
    operator_ramp_segments,
    synergy_capacity_to_eff, synergy_efficiency_amplifier,
    synergy_zeroing_variant, synergy_token_prod,
    synergy_faction_room, synergy_cross_room_pair,
    synergy_trade_gold_lines,
    synergy_whisper,
    synergy_global_faction,
    synergy_jie_order,
    synergy_trade_pair,
    synergy_trade_share,
    synergy_swires_order_limit,
    synergy_degenbrecher_order_limit,
    synergy_trade_efficiency_amplifier,
    synergy_trade_conditional_eff,
    synergy_facility_group,
    compute_trade_order_limit,
    GlobalBonus,
    operator_estimated_efficiency,
    _WORKSPACE_FACILITIES,
    _FACILITY_GROUP_TABLE,
    count_facilities_with_group,
)

_LAYOUT_243 = LayoutConfig.layout_243()

# ── all_assignments 预计算缓存 ──
# 键: id(all_assignments)，值: 预计算的查询结果集合
_PRECOMPUTED_CACHE: dict[int, dict] = {}


def _resolve_zeroing(
    operators: list[Operator],
    room_type: str,
    product: str,
    power_count: int,
    T: float,
) -> tuple[list, list, list, set[str], list[Operator]]:
    """归零解析：计算所有归零来源并确定 zero_set

    必须在其他联动函数之前执行，避免被归零干员的效率加成泄漏。
    """
    from steward_core.synergy.conflicts import resolve_efficiency_conflicts

    disabled_mechs = resolve_efficiency_conflicts(operators, room_type)

    auto_segs: list = []
    zero_set: set[str] = set()
    if "automation" not in disabled_mechs:
        auto_segs, zero_set = synergy_automation(operators, room_type, power_count, T)

    whisper_segs: list = []
    if "whisper" not in disabled_mechs:
        whisper_segs, whisper_zero = synergy_whisper(operators, room_type, T)
        zero_set |= whisper_zero

    zero_segs, zero_set2 = synergy_zeroing_variant(operators, room_type, product, T)
    zero_set |= zero_set2

    non_zero_ops = [op for op in operators if op.name not in zero_set]
    return auto_segs, whisper_segs, zero_segs, zero_set, non_zero_ops


def _eval_per_operator_efficiency(
    operators: list[Operator],
    room_type: str,
    product: str,
    T: float,
    *,
    zero_set: set[str],
    warmup_map: dict[str, float],
    mood_map: dict[str, float],
    mood_ctx,
    co_worker_names: list[str] | None,
    qianhuai_mood: float | None,
) -> float:
    """逐干员个人效率累加

    对非归零干员依次计算爬升/梯级衰减/常数效率段。
    """
    total = 0.0
    for op in operators:
        if op.name in zero_set:
            continue
        t_init = warmup_map.get(op.name, 0.0)
        op_mood = mood_map.get(op.name, 24.0)
        op_burn = 0.0
        if mood_ctx is not None:
            op_burn = mood_ctx.work_burn(
                op.name, room_type, len(operators),
                co_workers=co_worker_names,
            )
        ramp_segs = operator_ramp_segments(
            op, room_type, product, T, t_initial=t_init,
            mood_burn=op_burn, mood_initial=op_mood,
        )
        if ramp_segs is not None:
            total += integrate_segments(ramp_segs, T)
        elif op.name == "铅踝" and qianhuai_mood is not None:
            qianhuai_segs = stepped_efficiency(
                base=30, step_size=5, step_interval=4,
                mood_burn=op_burn, T=T, mood_initial=qianhuai_mood,
            )
            total += integrate_segments(qianhuai_segs, T)
        else:
            eff = operator_estimated_efficiency(op, room_type, product)
            if eff > 0:
                total += integrate_segments(
                    constant_efficiency(
                        eff, mood_burn=op_burn, T=T,
                        mood_initial=op_mood,
                    ), T,
                )
    return total


def _eval_cross_room_effects(
    operators: list[Operator],
    non_zero_ops: list[Operator],
    room_type: str,
    product: str,
    T: float,
    *,
    room_tokens: dict[str, float] | None = None,
    buff_pool,
    all_assignments: dict[str, list[Operator]] | None,
    all_operators: list[Operator] | None,
) -> float:
    """B 层跨房间效果：B6(全局阵营) + B7(跨房间配对) + B8(设施 group) + BuffPool 消费

    all_assignments 预计算结果通过模块级缓存 _PRECOMPUTED_CACHE 懒加载，
    首次遇到给定 all_assignments 时计算 all_names / facility_names / workspace_names /
    facility_group_counts，后续 combo 直接复用。
    """
    total = 0.0

    # ── 预计算缓存 ──
    pre = None
    if all_assignments is not None:
        cache_key = id(all_assignments)
        pre = _PRECOMPUTED_CACHE.get(cache_key)
        if pre is None:
            all_names = {op.name for ops in all_assignments.values() for op in ops}
            facility_names = {
                fac: {op.name for op in ops}
                for fac, ops in all_assignments.items()
            }
            workspace_names = set().union(*(
                facility_names.get(f, set()) for f in _WORKSPACE_FACILITIES
            ))

            group_ids = {entry.group_id for entry in _FACILITY_GROUP_TABLE.values()}
            facility_group_counts = {
                gid: count_facilities_with_group(all_assignments, gid)
                for gid in group_ids
            }

            pre = {
                "all_names": all_names,
                "facility_names": facility_names,
                "workspace_names": workspace_names,
                "facility_group_counts": facility_group_counts,
            }
            _PRECOMPUTED_CACHE[cache_key] = pre

    if all_assignments is not None:
        total += integrate_segments(
            synergy_cross_room_pair(
                non_zero_ops, room_type, product, all_assignments, T,
                _all_names=pre["all_names"] if pre else None,
                _facility_names=pre["facility_names"] if pre else None,
            ), T,
        )
        if room_type == "Trade":
            total += integrate_segments(
                synergy_trade_conditional_eff(
                    operators, room_type, all_assignments, T,
                    _all_names=pre["all_names"] if pre else None,
                    _workspace_names=pre["workspace_names"] if pre else None,
                ), T,
            )

    if all_assignments is not None:
        total += integrate_segments(
            synergy_facility_group(
                non_zero_ops, room_type, all_assignments, T,
                _facility_group_counts=pre["facility_group_counts"] if pre else None,
            ), T,
        )

    if all_operators is not None:
        total += integrate_segments(
            synergy_global_faction(non_zero_ops, room_type, product, all_operators, T, room_tokens=room_tokens), T,
        )

    if buff_pool is not None:
        total += integrate_segments(
            synergy_buff_pool_consumer(non_zero_ops, room_type, product, buff_pool, T), T,
        )

    return total


def evaluate_room(
    operators: list[Operator],
    room_type: str,
    product: str,
    power_count: int = 3,
    T: float = 12.0,
    global_bonus: GlobalBonus | None = None,
    buff_pool = None,
    ctrl_per_op_bonus: float = 0.0,
    cluster_hunting_bonus: float = 0.0,
    layout: LayoutConfig | None = None,
    power_platforms: dict[str, bool] | None = None,
    all_assignments: dict[str, list[Operator]] | None = None,
    all_operators: list[Operator] | None = None,
    control_operators: list[Operator] | None = None,
    mood_ctx: "MoodContext | None" = None,
) -> float:
    """评估一个房间组合的 T 小时总效率积分 Σ∫e(t)dt

    含联动(A1/A3/A4/A5/A6) + 个人效率 + B层消费(B1-B5) + 全局阵营计数(B6)
    + 跨房间配对(B7) + 全局加成(C1) + 中枢条件加成。
    mood_ctx 不为 None 时启用心情截断和铅踝梯级衰减。
    """
    if TYPE_CHECKING:
        from steward_core.mood_flow import MoodContext

    if not operators:
        return 0.0

    if global_bonus is None:
        global_bonus = GlobalBonus()
    if layout is None:
        layout = _LAYOUT_243

    # ── 心情截断参数 ──
    warmup_map: dict[str, float] = {}
    mood_map: dict[str, float] = {}
    co_worker_names: list[str] | None = None
    qianhuai_mood = None
    if mood_ctx is not None:
        co_worker_names = [op.name for op in operators]
        qianhuai_mood = mood_ctx.qianhuai_decay_basis(operators, room_type)
        for op in operators:
            w = mood_ctx.warmup_hours.get(op.name, 0.0)
            if w > 0:
                warmup_map[op.name] = w
            mood_map[op.name] = mood_ctx.mood_of(op.name)

    # ── 一、归零解析 ──
    auto_segs, whisper_segs, zero_segs, zero_set, non_zero_ops = _resolve_zeroing(
        operators, room_type, product, power_count, T,
    )

    # ── TokenSource 接入（Phase C1）：预计算全部 token 值 ──
    room_tokens = compute_room_tokens(operators)
    # 补充 layout 依赖 token（ctx=None 时 depends_on="layout" 源返回 0.0，
    # 此处用 evaluate_room 已有的 layout 参数直接计算）
    if layout is not None:
        dorm_rooms = [r for r in layout.rooms if r.room_type == "Dormitory"]
        reception_rooms = [r for r in layout.rooms if r.room_type == "Reception"]
        training_rooms = [r for r in layout.rooms if r.room_type == "Training"]
        mfg_rooms_list = [r for r in layout.rooms if r.room_type == "Mfg"]
        room_tokens["dorm_levels"] = float(sum(r.level for r in dorm_rooms))
        room_tokens["meeting_level"] = float(sum(r.level for r in reception_rooms))
        room_tokens["train_level"] = float(sum(r.level for r in training_rooms))
        room_tokens["trade_rooms"] = float(sum(1 for r in layout.rooms if r.room_type == "Trade"))
        room_tokens["mfg_rooms"] = float(len(mfg_rooms_list))
        room_tokens["power_rooms"] = float(sum(1 for r in layout.rooms if r.room_type == "Power"))
        mfg_products = {r.product for r in mfg_rooms_list if r.product is not None}
        room_tokens["mfg_recipe_types"] = float(len(mfg_products))

    # 补充 global scope 令牌（compute_room_tokens 只接收 room operators，
    # scope="global" 的源在 ctx=None 下统计 room ops 而非全基建 ops——用 all_operators 修正）
    if all_operators is not None:
        from steward_core.synergy.token_maps import (
            PHASE_B_GLOBAL_FACTION, PHASE_B_CONDITIONAL_EFF,
        )
        from steward_core.token_source import evaluate_tokens
        global_sources = PHASE_B_GLOBAL_FACTION + [s for s in PHASE_B_CONDITIONAL_EFF if s.scope == "global"]
        global_tokens = evaluate_tokens(global_sources, all_operators)
        room_tokens.update(global_tokens)

    # ── 不替换声明（C5）：以下路径保留旧函数，非计数层 ──
    # - 爬升 e(t)：operator_ramp_segments 是时间函数，非计数
    # - synergy_automation：per-op buff_id 扫描 + 归零集合语义，不适合纯计数 token 化
    # - 菲亚梅塔自律：非计数，经 contribution.py 独立计算
    # - 冲突互斥：resolve_efficiency_conflicts 是消费侧逻辑
    # - 订单覆盖/裁缝豁免：trade_linkages 内部机制，非计数
    # - compute_buff_pool：级联逻辑复杂，B2 映射表已就位但暂不接入

    # ── 二、房间组成型联动 ──
    total = integrate_segments(synergy_pair(operators, room_type, product, T, room_tokens=room_tokens), T)
    # alias 从 TokenSource 预计算值构造（替代 synergy_skill_alias 的 operator 遍历）
    alias = {"莱茵科技": ["标准化"], "红松骑士团": ["标准化"]} if room_tokens.get("haimei_in_room", 0) > 0 else {}

    order_ctx = None
    if room_type == "Trade" and layout is not None:
        order_ctx = compute_trade_order_limit(
            operators, layout, control_operators or [],
        )

    # ── 三、效率加成型联动 ──
    total += integrate_segments(synergy_faction_room(non_zero_ops, room_type, product, T, room_tokens=room_tokens), T)
    total += integrate_segments(synergy_skill_count(non_zero_ops, room_type, alias, T, room_tokens=room_tokens), T)
    total += integrate_segments(synergy_trade_gold_lines(
        operators, room_type, product, layout, T=T,
    ), T)
    total += integrate_segments(synergy_facility_count(
        non_zero_ops, room_type, product, layout, T=T,
    ), T)

    total += integrate_segments(synergy_trade_pair(non_zero_ops, room_type, T, room_tokens=room_tokens), T)
    total += integrate_segments(synergy_trade_share(non_zero_ops, room_type, T), T)
    if order_ctx is not None:
        total += integrate_segments(
            synergy_swires_order_limit(non_zero_ops, room_type, order_ctx, T), T,
        )
        total += integrate_segments(
            synergy_degenbrecher_order_limit(non_zero_ops, room_type, order_ctx, T), T,
        )

    # ── 四、归零加成自身效率段 ──
    total += integrate_segments(auto_segs, T)
    total += integrate_segments(whisper_segs, T)
    total += integrate_segments(zero_segs, T)
    total += ctrl_per_op_bonus * T

    # 集群狩猎加成（C4）— 受自动化/仿生海龙清零
    if room_type == "Mfg" and cluster_hunting_bonus > 0:
        from .synergy.control_linkages import is_cluster_hunting_zeroed, has_cluster_hunting as _has_ch
        if not is_cluster_hunting_zeroed(operators, room_type):
            total += cluster_hunting_bonus * T
        ch_active = control_operators and _has_ch(control_operators)
    else:
        ch_active = False

    # ── 五、逐干员个人效率 ──
    total += _eval_per_operator_efficiency(
        operators, room_type, product, T,
        zero_set=zero_set, warmup_map=warmup_map, mood_map=mood_map,
        mood_ctx=mood_ctx, co_worker_names=co_worker_names,
        qianhuai_mood=qianhuai_mood,
    )

    # ── 六、房间属性加成 ──
    # 配合意识：集群狩猎激活时禁用
    total += integrate_segments(synergy_capacity_to_eff(operators, room_type, product, T), T)
    if not ch_active:
        total += integrate_segments(synergy_efficiency_amplifier(non_zero_ops, room_type, product, T), T)

    # 贸易站效率→效率放大器（雪雉天道酬勤）— 必须在 per-operator + 房间属性之后，
    # 因为 total/T 是所有前置效率的平均值。
    if room_type == "Trade":
        total += integrate_segments(
            synergy_trade_efficiency_amplifier(non_zero_ops, room_type, total / T, T), T,
        )

    total += integrate_segments(synergy_token_prod(operators, room_type, product, power_platforms, T), T)

    if control_operators is not None and room_type == "Trade":
        total += integrate_segments(
            synergy_jie_order(non_zero_ops, room_type, control_operators, T, order_ctx=order_ctx), T,
        )

    # ── 七、B 层跨房间效果 ──
    total += _eval_cross_room_effects(
        operators, non_zero_ops, room_type, product, T,
        room_tokens=room_tokens,
        buff_pool=buff_pool, all_assignments=all_assignments,
        all_operators=all_operators,
    )

    # ── 八、全局加成 ──
    if room_type == "Mfg":
        total += global_bonus.mfg_bonus * T
    elif room_type == "Trade":
        total += global_bonus.trade_bonus * T

    return total
