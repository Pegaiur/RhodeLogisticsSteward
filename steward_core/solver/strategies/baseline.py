"""基线策略：Phase 贪心 + C(n,3) 穷举 + 局部搜索

等价于当前 solve_mvp() 的完整逻辑，纯搬迁，零行为变更。
"""

from steward_core.models import Operator, ShiftPlan, SolveResult

from ..config import SolverConfig
from ..pipeline import Pipeline
from ..refine import local_search_refine
from ..strategy import PartialSolution, Strategy


class BaselineStrategy(Strategy):
    """当前生产行为——Phase 贪心 + 穷举 + 局部搜索

    四阶段执行：
      Phase 1: 制造站穷举（CR 2间 + PG 2间）→ 贪心分配
      Phase 2: 中枢填充（来自支撑干员）
      Phase 3: 贸易站穷举 → 贪心分配
      Phase 4: 剩余设施（Power/Reception/Office）贪心
      Phase 5: 宿舍填充
      Post: 局部搜索后处理
    """

    name = "baseline"

    def execute(
        self,
        operators: list[Operator],
        config: SolverConfig,
        op_lookup: dict[str, Operator],
    ) -> SolveResult:
        params = config.params

        state = PartialSolution.empty()

        pipeline = Pipeline.default()
        autofill_count = pipeline.run(
            operators, config,
            state.assigned_ids, state.assigned_names, state.assignments,
            op_lookup, state.locked_support,
        )

        half_hours = int(params.shift_hours / 2.0)
        plan = ShiftPlan(
            name=f"MVP-{int(params.shift_hours)}h",
            assignments=state.assignments,
            period_from=f"{half_hours:02d}:00",
            period_to=f"{half_hours + int(params.shift_hours) - 1:02d}:59",
        )
        result = SolveResult(
            plans=[plan],
            autofill_count=autofill_count,
            config_used=config,
        )
        result = local_search_refine(result, operators, config)
        return result
