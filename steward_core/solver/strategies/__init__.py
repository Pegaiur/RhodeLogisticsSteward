"""策略实现子包"""

from ..slot.strategy import SlotStrategy

__all__ = ["SlotStrategy"]

STRATEGY_REGISTRY: dict[str, tuple[type, dict]] = {
    "slot": (SlotStrategy, {}),
}
