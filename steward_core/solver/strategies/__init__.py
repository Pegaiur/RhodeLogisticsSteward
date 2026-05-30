"""策略实现子包"""

from .baseline import BaselineStrategy
from .iterative import IterativeStrategy
from .kbeam import KBeamStrategy
from .slot_iteration import SlotIterationStrategy

__all__ = ["BaselineStrategy", "IterativeStrategy", "KBeamStrategy", "SlotIterationStrategy"]

STRATEGY_REGISTRY: dict[str, tuple[type, dict]] = {
    "baseline":        (BaselineStrategy,       {}),
    "kbeam3":          (KBeamStrategy,          {"beam_width": 3}),
    "kbeam5":          (KBeamStrategy,          {"beam_width": 5}),
    "iterative":       (IterativeStrategy,      {"max_rounds": 5}),
    "iterative3":      (IterativeStrategy,      {"max_rounds": 3}),
    "slot_iter":       (SlotIterationStrategy,  {}),
    "slot_iter_cold":  (SlotIterationStrategy,  {"cold_start": True}),
}
