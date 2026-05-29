"""中枢心情恢复计算 — 委托至 mood_flow.py 的 MoodModifiers"""

from steward_core.models import Operator
from steward_core.mood_flow import compute_global_burn as _compute_global_burn


def compute_global_burn(
    control_operators: list[Operator],
    buff_pool: "BuffPool",
    worker_count: int = 3,
) -> float:
    """计算工作干员的心情消耗率净值 — 委托至 mood_flow"""
    return _compute_global_burn(control_operators, buff_pool, worker_count)
