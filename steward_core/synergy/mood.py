"""中枢心情恢复计算"""

from steward_core.models import Operator
from .helpers import _BASE_BURN_3


def compute_global_burn(
    control_operators: list[Operator],
    buff_pool: "BuffPool",
    worker_count: int = 3,
) -> float:
    """计算工作干员的心情消耗率净值 (mood_burn)

    基础值 0.75/h（3人工位），中枢每名干员提供 +0.05/h 恢复。
    重岳孤光共照：+0.05/h，每 20 烟火额外 +0.05。
    """
    control_count = len(control_operators)
    recovery = control_count * 0.05

    names = {op.name for op in control_operators}
    if "重岳" in names:
        recovery += 0.05
        recovery += (buff_pool.yanhuo // 20) * 0.05

    burn = max(0.0, _BASE_BURN_3 - recovery)
    return burn
