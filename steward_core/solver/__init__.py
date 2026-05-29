"""排班求解器

Mfg 和 Trade 均使用 C(n,3) 穷举（含联动）+ 贪心分配。
剩余设施（Power/Reception/Office）用支配偏序贪心。
Control 由制造站 combo 的支撑需求动态决定。

求解策略由 Strategy 子类定义——见 solver/strategy.py。
可通过 SolverConfig.strategy 注入自定义策略进行 A/B 测试。
"""

from steward_core.models import Operator, SolveResult, ShiftPlan

from .config import SolverConfig
from .greed import _greedy_allocate, _generate_combos, _upper_bound_ok, _evaluate_trade_combo
from .refine import local_search_refine
from .strategies import BaselineStrategy


def solve_mvp(
    operators: list[Operator],
    config: SolverConfig | None = None,
) -> SolveResult:
    """MVP 完整求解——委托给 config.strategy 执行

    不传 strategy 时使用 BaselineStrategy（等价于当前生产行为）。
    可通过 SolverConfig.strategy 注入自定义策略进行 A/B 测试。
    需要自定义求解策略时，实现新的 Strategy 子类。
    """
    if config is None:
        config = SolverConfig()
    if config.strategy is None:
        config.strategy = BaselineStrategy()

    op_lookup = {op.name: op for op in operators}
    return config.strategy.execute(operators, config, op_lookup)


def solve_multi_shift(
    operators: list[Operator],
    config: SolverConfig | None = None,
) -> SolveResult:
    """多班次编排器 — 对任意 Strategy 透明

    Args:
        operators: 全部干员池
        config: 求解器配置（params.shift_count 控制班次数）

    Returns:
        SolveResult，plans 数组长度 = shift_count
    """
    if config is None:
        config = SolverConfig()

    from steward_core.mood_flow import MoodContext
    from .fill_dorm import fill_dorm_with_scheduling

    strategy = config.strategy or BaselineStrategy()
    params = config.params
    op_lookup = {op.name: op for op in operators}

    mood_ctx = MoodContext.fresh(operators, params)

    effective_threshold = params.mood_work_threshold
    if effective_threshold <= 0.0 and params.shift_count > 1:
        effective_threshold = params.mood_blue_face

    all_plans: list[ShiftPlan] = []
    mood_snapshots: list[dict[str, tuple[float, float]]] = []

    for shift_idx in range(params.shift_count):
        working_config = SolverConfig(
            strategy=strategy,
            exclusive_support_check=config.exclusive_support_check,
            local_search_enabled=config.local_search_enabled,
            global_state_scoring=config.global_state_scoring,
            mood_ctx=mood_ctx,
            params=params,
        )

        available = [op for op in operators
                     if mood_ctx.mood_of(op.name) >= effective_threshold]

        result = solve_mvp(available, working_config)

        if result.plans:
            plan = result.plans[0]
            half_hours = int(params.shift_hours / 2.0)
            offset = shift_idx * (int(params.shift_hours) + int(params.interval_hours))
            plan = ShiftPlan(
                name=f"Shift{shift_idx + 1}-{int(params.shift_hours)}h",
                assignments=list(plan.assignments),
                period_from=f"{(half_hours + offset):02d}:00",
                period_to=f"{(half_hours + offset + int(params.shift_hours) - 1):02d}:59",
            )

            mood_before = dict(mood_ctx.operator_moods)
            mood_ctx = _collect_control_from_plan(plan, mood_ctx)
            mood_ctx = _collect_working_from_plan(plan, mood_ctx)

            # 记录本班次心情变化快照
            snapshot: dict[str, tuple[float, float]] = {}
            for name, after in mood_ctx.operator_moods.items():
                before = mood_before.get(name, 24.0)
                if abs(before - after) > 0.005:
                    snapshot[name] = (before, after)
            mood_snapshots.append(snapshot)

            # 框架层覆盖宿舍分配
            fill_dorm_with_scheduling(
                operators=available,
                assignments=plan.assignments,
                op_lookup=op_lookup,
                config=working_config,
                mood_ctx=mood_ctx,
            )

            all_plans.append(plan)

            if shift_idx < params.shift_count - 1:
                mood_ctx = mood_ctx.after_recovery(params.interval_hours)

    return SolveResult(
        plans=all_plans,
        autofill_count=0,
        config_used=_build_output_config(config, mood_ctx),
        mood_snapshots=mood_snapshots,
    )


def _build_output_config(config: SolverConfig, mood_ctx) -> SolverConfig:
    """构造输出用 SolverConfig，携带最终 mood_ctx 供 output.py 读取 Fiammetta"""
    return SolverConfig(
        strategy=config.strategy,
        exclusive_support_check=config.exclusive_support_check,
        local_search_enabled=config.local_search_enabled,
        global_state_scoring=config.global_state_scoring,
        mood_ctx=mood_ctx,
        params=config.params,
    )


def _collect_control_from_plan(
    plan: ShiftPlan,
    mood_ctx: "MoodContext",
) -> "MoodContext":
    """从 plan 提取中枢干员，注入 mood_ctx 并重置 modifiers 缓存"""
    from dataclasses import replace

    control_names: list[str] = []
    for a in plan.assignments:
        if a.room_type == "Control":
            control_names.extend(a.operators)
    return replace(mood_ctx, control_operators=control_names, modifiers=None)


def _collect_working_from_plan(
    plan: ShiftPlan,
    mood_ctx: "MoodContext",
) -> "MoodContext":
    """从 plan 提取工作干员，应用 after_shift 心情消耗"""
    working_names: set[str] = set()
    for a in plan.assignments:
        if a.room_type in ("Mfg", "Trade", "Power", "Reception", "Office"):
            working_names.update(a.operators)
    return mood_ctx.after_shift(working_names, mood_ctx.shift_hours)
