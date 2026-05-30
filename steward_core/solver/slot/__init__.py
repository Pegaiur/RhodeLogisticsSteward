"""槽位加工模型求解器

SlotSolver 直接实现 slot-processing-model-draft.md §9.5 混合状态迭代策略。
"""

from .context import SlotContext, StateVector, SlotAssignment, WindowState, STATE_DIMS
from .partials import compute_partial_derivatives
from .contribution import contribution
from .mfg import phase_mfg
from .trade import phase_trade

__all__ = [
    "SlotContext",
    "StateVector",
    "SlotAssignment",
    "WindowState",
    "STATE_DIMS",
    "compute_partial_derivatives",
    "contribution",
    "phase_mfg",
    "phase_trade",
]
