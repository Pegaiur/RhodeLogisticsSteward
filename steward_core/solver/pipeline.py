"""可组合求解流水线

将 solve_mvp 硬编码的 Phase 执行顺序变为可配置的组合。
Phase 函数通过 partial 绑定额外参数，统一为 PhaseFunction 协议。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from steward_core.models import Operator
    from .config import SolverConfig
    from .strategy import PartialSolution


class PhaseFunction(Protocol):
    """Phase 函数签名协议

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
    """可组合的求解流水线

    默认流水线等价于当前 solve_mvp 的 Phase 执行顺序。
    实验时可通过 Pipeline 构造新的 phases 列表来改变顺序或插入新 Phase。

    用法:
        # 标准流水线
        pipe = Pipeline.default()

        # 实验: 先排 Trade 再排 Mfg
        pipe = Pipeline.with_phases([
            ("trade", exhaust_trade),
            ("mfg", exhaust_mfg),
            ("control", fill_control),
            ("remaining", fill_remaining),
            ("dorm", fill_dorm),
        ])
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
        """按 phases 顺序依次执行，累计 autofill_count

        以关键字参数调用各 Phase，使其不依赖参数顺序。
        """
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
        state: "PartialSolution",
        op_lookup: dict[str, "Operator"],
    ) -> int:
        """等价于 run()，但接受 PartialSolution 作为状态载体

        用于 Strategy 子类——比手动解包 6 个参数更清晰。
        """
        return self.run(
            operators, config,
            state.assigned_ids, state.assigned_names, state.assignments,
            op_lookup, state.locked_support,
        )

    @classmethod
    def default(cls) -> "Pipeline":
        """默认流水线（等价于当前 solve_mvp 行为）"""
        from .exhaust_mfg import exhaust_mfg
        from .fill_control import fill_control
        from .exhaust_trade import exhaust_trade
        from .fill_remaining import fill_remaining
        from .fill_dorm import fill_dorm

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
