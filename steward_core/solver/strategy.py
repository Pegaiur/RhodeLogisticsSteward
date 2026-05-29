"""求解策略抽象层

Strategy 封装完整的求解流水线——从干员池到最终排班方案。
子类通过不同的 Phase 编排、分配策略、后处理组合实现不同的算法行为。

PartialSolution 是排班过程中的状态快照，使 K-Beam 等多路径策略
能够克隆和分叉求解状态。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from steward_core.models import Operator, SolveResult
    from .config import SolverConfig


@dataclass
class PartialSolution:
    """排班求解过程中的状态快照——可在 Phase 间传递和克隆"""

    assigned_ids: set[str] = field(default_factory=set)
    assigned_names: set[str] = field(default_factory=set)
    assignments: list = field(default_factory=list)
    locked_support: dict[str, set[str]] = field(default_factory=dict)

    def clone(self) -> "PartialSolution":
        """深拷贝当前状态，供 K-Beam 等多路径策略分叉使用"""
        return PartialSolution(
            assigned_ids=set(self.assigned_ids),
            assigned_names=set(self.assigned_names),
            assignments=list(self.assignments),
            locked_support={k: set(v) for k, v in self.locked_support.items()},
        )

    @classmethod
    def empty(cls) -> "PartialSolution":
        """创建带默认 locked_support 键的空状态"""
        return cls(locked_support={
            "Control": set(), "Trade": set(),
            "Dormitory": set(), "Office": set(),
        })


class Strategy(ABC):
    """求解策略基类

    每个子类实现 execute() 定义自己的排班求解流程。
    策略之间互相独立——一个策略的实现变更不影响其他策略。

    子类应通过 PartialSolution 管理状态快照，
    通过效率模型层的公开 API 进行评估和分类。
    """

    name: str = "abstract"

    @abstractmethod
    def execute(
        self,
        operators: list["Operator"],
        config: "SolverConfig",
        op_lookup: dict[str, "Operator"],
    ) -> "SolveResult":
        """执行排班求解

        Args:
            operators: 全量干员列表
            config: 求解器配置（含 params 和 strategy 自身引用）
            op_lookup: {name → Operator} 查找表（由 solve_mvp 预构建）

        Returns:
            完整的 SolveResult，含至少一个 ShiftPlan
        """
        ...
