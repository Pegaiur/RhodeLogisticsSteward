"""共享求解管道

提供从求解到产出计算的完整管道，供 run_solver.py 和 report.py 复用。
两个入口脚本的差异仅在输出格式，求解逻辑完全一致。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from steward_core.solver import solve_mvp
from steward_core.solver.config import SolverConfig
from steward_core.mood_flow import MoodContext
from steward_core import production
from steward_core.production import _GOLD_LMD_PER_UNIT

if TYPE_CHECKING:
    from steward_core.models import Operator, SolveResult
    from steward_core.solver.params import SolverParams
    from steward_core.production import DailyProduction


@dataclass
class PipelineResult:
    """管道执行结果：求解 + 产出 + 上下文"""
    solve_result: "SolveResult"
    productions: list["DailyProduction"]
    params: "SolverParams"
    config: SolverConfig
    operators: list["Operator"]
    mood_ctx: MoodContext


def run(
    operators: list["Operator"],
    params: "SolverParams",
) -> PipelineResult:
    """执行求解管道：心情上下文 → 求解 → 计算产出

    Args:
        operators: 全量干员列表
        params: 求解参数（已完成覆盖合并的最终参数）

    Returns:
        PipelineResult 包含求解结果、每日产出和所有上下文
    """
    mood_ctx = MoodContext.fresh(operators, params)
    config = SolverConfig(params=params, mood_ctx=mood_ctx)
    solve_result = solve_mvp(operators, config=config)

    external_gold_per_day = params.daily_task_lmd / _GOLD_LMD_PER_UNIT

    productions = []
    for plan in solve_result.plans:
        dp = production.calculate(
            plan, operators,
            hours=params.shift_hours,
            external_gold_per_day=external_gold_per_day,
            mood_ctx=mood_ctx,
        )
        productions.append(dp)

    return PipelineResult(
        solve_result=solve_result,
        productions=productions,
        params=params,
        config=config,
        operators=operators,
        mood_ctx=mood_ctx,
    )
