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
            ("trade", _phase3_trade),
            ("mfg", _phase1_mfg),
            ("control", _phase2_control),
            ("remaining", _phase3_remaining),
            ("dorm", _phase4_dorm),
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

    @classmethod
    def default(cls) -> "Pipeline":
        """默认流水线（等价于当前 solve_mvp 行为）"""
        from .phase1_mfg import _phase1_mfg
        from .phase2_control import _phase2_control
        from .phase3_trade import _phase3_trade
        from .phase3_remaining import _phase3_remaining
        from .phase4_dorm import _phase4_dorm

        from steward_core.synergy import get_system_contributors
        from steward_core.synergy._derived import MFG_ANCHORS

        ANCHOR_NAMES = MFG_ANCHORS
        CTRL_GLOBAL_NAMES = set(get_system_contributors("Control", "global_bonus"))
        DORM_NAMES = get_system_contributors("Dormitory")
        POWER_NAMES = set(get_system_contributors("Power"))

        return cls(phases=[
            ("mfg", partial(_phase1_mfg, anchor_names=ANCHOR_NAMES)),
            ("trade", _phase3_trade),
            ("control", partial(
                _phase2_control,
                ctrl_global_names=CTRL_GLOBAL_NAMES,
            )),
            ("remaining", partial(_phase3_remaining, power_names=POWER_NAMES)),
            ("dorm", partial(_phase4_dorm, dorm_names_list=DORM_NAMES)),
        ])

    @classmethod
    def with_phases(cls, phases: list[tuple[str, PhaseFunction]]) -> "Pipeline":
        """从自定义 Phase 列表构造"""
        return cls(phases=phases)

    def describe(self) -> str:
        """人类可读的流水线描述"""
        return " → ".join(name for name, _ in self.phases)
