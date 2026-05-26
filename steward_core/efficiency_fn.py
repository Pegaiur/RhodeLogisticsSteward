"""效率函数模块

统一 e(t) 模型：LinearSegment、构造器、积分、支配偏序。
MV1 实现完整逻辑，MV0 仅提供 integrate_segments 占位。
"""

from steward_core.models import LinearSegment


def integrate_segments(segments: list[LinearSegment], T: float) -> float:
    """对段列表在 [0, T] 上积分求和

    MV0 占位：当前 T 参数未生效（所有段均取自身的 dt），
    因为 MV0 阶段所有段的 t_start+dt 均在 [0, T] 内。
    MV1 实现完整截断逻辑后 T 将用于裁剪超出班次的段尾。
    """
    total = 0.0
    for seg in segments:
        end = seg.t_start + seg.dt
        if end > T:
            # 段超出 T → 裁剪
            clipped = LinearSegment(a=seg.a, b=seg.b, t_start=seg.t_start, dt=T - seg.t_start)
            total += clipped.integrate()
        else:
            total += seg.integrate()
    return total
