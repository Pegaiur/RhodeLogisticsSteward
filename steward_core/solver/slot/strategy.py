"""SlotStrategy — 槽位加工模型策略"""

from __future__ import annotations

from typing import TYPE_CHECKING

from steward_core.models import Operator, SolveResult
from steward_core.solver.strategy import Strategy
from steward_core.solver.slot.solver import solve_slot

if TYPE_CHECKING:
    from steward_core.solver.config import SolverConfig


class SlotStrategy(Strategy):
    """基于 D[d] 反馈迭代的槽位加工求解策略

    核心差异：
    - 中枢/宿舍/发电/会客/办公室通过 contribution 评分选出
    - D[d] 偏导数连接 Mfg/Trade 产出与 Control/Dorm 写入
    - 迭代至邻域局部最优收敛
    """

    name = "slot"

    def execute(
        self,
        operators: list[Operator],
        config: "SolverConfig",
        op_lookup: dict[str, Operator],
    ) -> SolveResult:
        return solve_slot(
            operators=operators,
            params=config.params,
            mood_ctx=config.mood_ctx,
            max_iterations=config.params.slot_max_rounds if config.params.slot_max_rounds > 0 else 5,
        )
