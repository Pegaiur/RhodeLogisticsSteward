"""排班求解器

Mfg 和 Trade 均使用 C(n,3) 穷举（含联动）+ 贪心分配。
剩余设施（Power/Reception/Office）用支配偏序贪心。
Control 由制造站 combo 的支撑需求动态决定。

Phase 执行顺序由 Pipeline 组合，支持 A/B 测试不同流水线。
"""

from steward_core.models import Operator, ShiftPlan, SolveResult

from .config import SolverConfig
# 以下 re-export 保留以兼容 test_end_to_end.py 等下游 import
from .greed import _greedy_allocate, _generate_combos, _upper_bound_ok, _evaluate_trade_combo
from .pipeline import Pipeline
from .refine import local_search_refine


def solve_mvp(
    operators: list[Operator],
    config: SolverConfig | None = None,
    pipeline: Pipeline | None = None,
) -> SolveResult:
    """MVP 完整求解

    中枢不再固定——由制造站 combo 的支撑需求动态决定。
    可通过 pipeline 参数注入自定义 Phase 顺序进行 A/B 测试，
    不传则使用默认流水线（等价于当前生产行为）。

    Returns:
        SolveResult，含一个 ShiftPlan 和使用的配置。
    """
    if config is None:
        config = SolverConfig()
    params = config.params

    assigned_ids: set[str] = set()
    assigned_names: set[str] = set()
    assignments: list = []
    op_lookup = {op.name: op for op in operators}
    locked_support: dict[str, set[str]] = {
        "Control": set(), "Trade": set(), "Dormitory": set(), "Office": set(),
    }

    if pipeline is None:
        pipeline = Pipeline.default()

    autofill_count = pipeline.run(
        operators, config,
        assigned_ids, assigned_names, assignments,
        op_lookup, locked_support,
    )

    half_hours = int(params.shift_hours / 2.0)
    plan = ShiftPlan(
        name=f"MVP-{int(params.shift_hours)}h",
        assignments=assignments,
        period_from=f"{half_hours:02d}:00",
        period_to=f"{half_hours + int(params.shift_hours) - 1:02d}:59",
    )
    result = SolveResult(plans=[plan], autofill_count=autofill_count, config_used=config)
    result = local_search_refine(result, operators, config)
    return result
