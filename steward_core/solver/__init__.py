"""排班求解器

槽位加工模型求解器（SlotSolver）为唯一求解路径。
通过 SolverConfig.strategy 注入自定义策略进行 A/B 测试。
"""

from steward_core.models import Operator, SolveResult

from .config import SolverConfig
from .slot.strategy import SlotStrategy


def solve_mvp(
    operators: list[Operator],
    config: SolverConfig | None = None,
) -> SolveResult:
    """完整求解——委托给 config.strategy 执行

    默认使用 SlotStrategy（槽位加工模型）。
    """
    if config is None:
        config = SolverConfig()
    if config.strategy is None:
        config.strategy = SlotStrategy()

    op_lookup = {op.name: op for op in operators}
    return config.strategy.execute(operators, config, op_lookup)
