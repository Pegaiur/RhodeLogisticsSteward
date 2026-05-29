"""基线策略：Phase 贪心 + C(n,3) 穷举 + 局部搜索

等价于当前 solve_mvp() 的完整逻辑。Pipeline 是 BaselineStrategy 的内部编排器，
负责将 5 个 Phase 函数按固定顺序线性串联。其他策略（KBeam、Iterative）拥有
自己的控制流，不使用 Pipeline。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Protocol

from steward_core.models import Operator, ShiftPlan, SolveResult

from ..config import SolverConfig
from ..refine import local_search_refine
from ..strategy import PartialSolution, Strategy

if TYPE_CHECKING:
    from ..strategy import PartialSolution as PartialSolutionType


class PhaseFunction(Protocol):
    """Phase 函数签名协议 — BaselineStrategy 内部使用

    通过 partial 绑定额外参数后，各 Phase 统一为此签名：
    (operators, assigned_ids, assigned_names, assignments,
     op_lookup, locked_support, config) -> int
    """
    def __call__(
        self,
        operators: list,
        assigned_ids: set[str],
        assigned_names: set[str],
        assignments: list,
        op_lookup: dict[str, "Operator"],
        locked_support: dict[str, set[str]],
        config: "SolverConfig | None",
    ) -> int: ...


@dataclass
class Pipeline:
    """BaselineStrategy 的线性流水线编排器

    将 5 个 Phase 函数按固定顺序串联，不支持分叉、迭代或其他控制流。
    其他策略应自行实现编排逻辑，而非复用 Pipeline。
    """

    phases: list[tuple[str, PhaseFunction]] = field(default_factory=list)

    def run(
        self,
        operators: list,
        config: "SolverConfig | None",
        assigned_ids: set[str],
        assigned_names: set[str],
        assignments: list,
        op_lookup: dict[str, "Operator"],
        locked_support: dict[str, set[str]],
    ) -> int:
        """按 phases 顺序依次执行，累计 autofill_count"""
        total_autofill = 0
        for _name, phase_fn in self.phases:
            total_autofill += phase_fn(
                operators=operators,
                assigned_ids=assigned_ids,
                assigned_names=assigned_names,
                assignments=assignments,
                op_lookup=op_lookup,
                locked_support=locked_support,
                config=config,
            )
        return total_autofill

    def run_on_state(
        self,
        operators: list,
        config: "SolverConfig | None",
        state: "PartialSolutionType",
        op_lookup: dict[str, "Operator"],
    ) -> int:
        """等价于 run()，但接受 PartialSolution 作为状态载体"""
        return self.run(
            operators, config,
            state.assigned_ids, state.assigned_names, state.assignments,
            op_lookup, state.locked_support,
        )

    @classmethod
    def default(cls) -> "Pipeline":
        """默认流水线（mfg → trade → control → remaining → dorm）"""
        from ..exhaust_mfg import exhaust_mfg
        from ..fill_control import fill_control
        from ..exhaust_trade import exhaust_trade
        from ..fill_remaining import fill_remaining
        from ..fill_dorm import fill_dorm

        from steward_core.synergy import get_system_contributors
        from steward_core.synergy._derived import MFG_ANCHORS

        ANCHOR_NAMES = MFG_ANCHORS
        CTRL_GLOBAL_NAMES = set(get_system_contributors("Control", "global_bonus"))
        DORM_NAMES = get_system_contributors("Dormitory")
        POWER_NAMES = set(get_system_contributors("Power"))

        return cls(phases=[
            ("mfg", partial(exhaust_mfg, anchor_names=ANCHOR_NAMES)),
            ("trade", exhaust_trade),
            ("control", partial(
                fill_control,
                ctrl_global_names=CTRL_GLOBAL_NAMES,
            )),
            ("remaining", partial(fill_remaining, power_names=POWER_NAMES)),
            ("dorm", partial(fill_dorm, dorm_names_list=DORM_NAMES)),
        ])

    @classmethod
    def with_phases(cls, phases: list[tuple[str, PhaseFunction]]) -> "Pipeline":
        """从自定义 Phase 列表构造"""
        return cls(phases=phases)

    def describe(self) -> str:
        """人类可读的流水线描述"""
        return " → ".join(name for name, _ in self.phases)


class BaselineStrategy(Strategy):
    """当前生产行为——Phase 贪心 + 穷举 + 局部搜索

    五阶段执行：
      Phase 1: 制造站穷举（CR 2间 + PG 2间）→ 贪心分配
      Phase 2: 贸易站穷举 → 贪心分配
      Phase 3: 中枢填充（来自支撑干员）
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
