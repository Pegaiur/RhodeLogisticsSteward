"""效率函数模块

统一 e(t) 模型：LinearSegment、构造器、积分、支配偏序。
MV1 实现完整逻辑，MV0 仅提供 integrate_segments 占位。
"""

from steward_core.models import LinearSegment


def integrate_segments(segments: list[LinearSegment], T: float) -> float:
    """对段列表在 [0, T] 上积分求和"""
    return sum(seg.integrate() for seg in segments)
