"""排班求解器

Mfg 和 Trade 均使用 C(n,3) 穷举（含联动）+ 贪心分配。
剩余设施（Power/Reception/Office）用支配偏序贪心。
Control 由制造站 combo 的支撑需求动态决定。

求解策略由 Strategy 子类定义——见 solver/strategy.py。
可通过 SolverConfig.strategy 注入自定义策略进行 A/B 测试。
"""

from steward_core.models import Operator, SolveResult

from .config import SolverConfig
# 以下 re-export 保留以兼容 test_end_to_end.py 等下游 import
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
    需要自定义 Phase 顺序时，通过 Strategy 子类组合 Pipeline 实现。
    """
    if config is None:
        config = SolverConfig()
    if config.strategy is None:
        config.strategy = BaselineStrategy()

    op_lookup = {op.name: op for op in operators}
    return config.strategy.execute(operators, config, op_lookup)
