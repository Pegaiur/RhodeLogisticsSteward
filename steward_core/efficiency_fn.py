"""效率函数模块

统一 e(t) 模型：LinearSegment、构造器、积分、支配偏序。
"""

from typing import Any

from steward_core.models import LinearSegment


def integrate_segments(segments: list[LinearSegment], T: float) -> float:
    """对段列表在 [0, T] 上积分求和

    超过 T 的段尾会被裁剪。
    单段常数快速路径：消除 integrate() 方法调用和循环开销。
    """
    # ── 单段常数快速路径 ──
    if len(segments) == 1:
        seg = segments[0]
        if seg.b == 0.0 and seg.t_start == 0.0:
            return seg.a * min(seg.dt, T)

    total = 0.0
    for seg in segments:
        end = seg.t_start + seg.dt
        if end > T:
            clipped = LinearSegment(a=seg.a, b=seg.b, t_start=seg.t_start, dt=T - seg.t_start)
            total += clipped.integrate()
        else:
            total += seg.integrate()
    return total


def constant_efficiency(
    value: float,
    mood_burn: float = 0.0,
    T: float = 12.0,
    mood_initial: float = 24.0,
) -> list[LinearSegment]:
    """常数效率技能 → 分段表示

    value: 技能效率值（百分值，如 30 表示 +30%）
    mood_burn: 净心情消耗率（/h），0 表示不截断
    T: 排班时长（h）
    mood_initial: 干员初始心情值，默认 24

    mood > 0: 满效率
    mood <= 0: 效率归零（红脸截断）
    """
    if mood_burn <= 0:
        return [LinearSegment(a=value, b=0.0, t_start=0.0, dt=T)]

    t_red = mood_initial / mood_burn
    if t_red >= T:
        return [LinearSegment(a=value, b=0.0, t_start=0.0, dt=T)]

    segments = [LinearSegment(a=value, b=0.0, t_start=0.0, dt=t_red)]
    segments.append(LinearSegment(a=0.0, b=0.0, t_start=t_red, dt=T - t_red))
    return segments


def ramping_efficiency(
    k0: float, r: float, ceiling: float,
    mood_burn: float = 0.0, T: float = 12.0,
    t_initial: float = 0.0,
    mood_initial: float = 24.0,
) -> list[LinearSegment]:
    """时变效率技能 → 分段表示（5 条 manu_prod_spd_addition[*] + 发电站爬升预留）

    k0: 首小时效率值
    r: 每小时增量（百分值/h）
    ceiling: 效率上限
    mood_burn: 净心情消耗率
    T: 排班时长
    t_initial: 已连续工作小时数（暖机偏移，默认 0 = 从零爬升）
    mood_initial: 干员初始心情值，默认 24
    """
    segments: list[LinearSegment] = []
    t_start = 0.0

    t_sat = (ceiling - k0) / r if r > 0 else float("inf")
    remaining_sat = max(0.0, t_sat - t_initial)

    if t_initial >= t_sat:
        segments.append(LinearSegment(a=ceiling, b=0.0, t_start=0.0, dt=T))
    elif remaining_sat < T:
        start_eff = k0 + r * t_initial
        segments.append(LinearSegment(a=start_eff, b=r, t_start=0.0, dt=remaining_sat))
        segments.append(LinearSegment(a=ceiling, b=0.0, t_start=remaining_sat, dt=T - remaining_sat))
    else:
        start_eff = k0 + r * t_initial
        segments.append(LinearSegment(a=start_eff, b=r, t_start=0.0, dt=T))

    if mood_burn <= 0:
        return segments

    t_red = mood_initial / mood_burn
    if t_red >= T:
        return segments

    final: list[LinearSegment] = []
    for seg in segments:
        seg_end = seg.t_start + seg.dt
        if seg_end <= t_red:
            final.append(seg)
        elif seg.t_start >= t_red:
            pass
        else:
            clipped = LinearSegment(a=seg.a, b=seg.b, t_start=seg.t_start, dt=t_red - seg.t_start)
            final.append(clipped)

    final.append(LinearSegment(a=0.0, b=0.0, t_start=t_red, dt=T - t_red))
    return final


def _key_values(segments: list[LinearSegment], T: float) -> tuple[float, float]:
    """提取 e(t) 的有效常数值和有效时长

    用于 O(1) 支配简化：对常数型技能退化为值+时长二维比较。
    取首个非零段的值作为 k，取最后一个非零段的终点作为 t_end。
    """
    if not segments:
        return 0.0, 0.0
    k = segments[0].a
    t_end = 0.0
    for s in segments:
        if s.a > 0 or s.b > 0:
            t_end = s.t_start + s.dt
    return k, min(t_end, T)


def _dominates_simple(
    seg_a: list[LinearSegment], seg_b: list[LinearSegment], T: float,
) -> bool:
    """O(1) 支配关系：A 支配 B ⇔ k_A >= k_B AND 有效时长_A >= 有效时长_B

    仅适用于常数型技能（b=0）。ramp 技能退回到通版 _dominates()。
    """
    if any(s.b != 0 for s in seg_a) or any(s.b != 0 for s in seg_b):
        return _dominates(seg_a, seg_b, T)

    k_a, t_a = _key_values(seg_a, T)
    k_b, t_b = _key_values(seg_b, T)
    return k_a >= k_b and t_a >= t_b


def _dominates(
    seg_a: list[LinearSegment], seg_b: list[LinearSegment], T: float,
) -> bool:
    """通版支配判定：在全部端点处逐点比较"""
    breakpoints = {0.0, T}
    for s in seg_a + seg_b:
        bp = s.t_start
        if bp <= T:
            breakpoints.add(bp)
        bp = s.t_start + s.dt
        if bp <= T:
            breakpoints.add(bp)
    breakpoints_sorted = sorted(breakpoints)

    def eval_at(segs: list[LinearSegment], t: float) -> float:
        for s in segs:
            if s.t_start <= t < s.t_start + s.dt:
                return s.a + s.b * (t - s.t_start)
        return 0.0

    return all(
        eval_at(seg_a, t) >= eval_at(seg_b, t)
        for t in breakpoints_sorted
    )


def rank_by_dominance(
    candidates: list[tuple[list[LinearSegment], Any]], T: float,
) -> list[Any]:
    """支配偏序排序：多趟 Kahn 拓扑

    candidates: [(segments, label), ...]
    返回按支配偏序排列的 label 列表。
    互不支配时退化到全积分比较。
    """
    n = len(candidates)
    if n == 0:
        return []
    if n == 1:
        return [candidates[0][1]]

    graph = {i: set() for i in range(n)}
    in_degree = {i: 0 for i in range(n)}

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            a_dom_b = _dominates_simple(candidates[i][0], candidates[j][0], T)
            b_dom_a = _dominates_simple(candidates[j][0], candidates[i][0], T)
            if a_dom_b and not b_dom_a:
                graph[i].add(j)
                in_degree[j] += 1

    remaining = set(range(n))
    result = []

    while remaining:
        maximal = [i for i in remaining if in_degree[i] == 0]
        if not maximal:
            break
        if len(maximal) == 1:
            best = maximal[0]
        else:
            best = max(maximal, key=lambda i: integrate_segments(candidates[i][0], T))
        result.append(candidates[best][1])
        remaining.remove(best)
        for j in graph[best] & remaining:
            in_degree[j] -= 1

    return result


def stepped_efficiency(
    base: float,
    step_size: float = 5.0,
    step_interval: float = 4.0,
    mood_burn: float = 0.0,
    T: float = 12.0,
    mood_initial: float = 24.0,
) -> list[LinearSegment]:
    """梯级衰减效率：e(t) = base - step_size × ⌊(24 - mood(t)) / step_interval⌋

    mood(t) = mood_initial - burn × t
    每 step_interval 点心情落差触发一级衰减，每段内效率为常数。

    Args:
        base: 基础效率值（百分值）
        step_size: 每级衰减量（百分值）
        step_interval: 心情间隔（h）
        mood_burn: 净心情消耗率（/h）
        T: 排班时长（h）
        mood_initial: 初始心情值
    """
    if mood_burn <= 0:
        return [LinearSegment(a=base, b=0.0, t_start=0.0, dt=T)]

    segments: list[LinearSegment] = []
    t = 0.0
    while t < T:
        current_mood = mood_initial - mood_burn * t
        if current_mood <= 0:
            segments.append(LinearSegment(a=0.0, b=0.0, t_start=t, dt=T - t))
            break
        steps_down = int((24.0 - current_mood) / step_interval)
        eff = max(0.0, base - max(0, steps_down) * step_size)

        next_step_mood = max(0.0, 24.0 - (steps_down + 1) * step_interval)
        if mood_burn > 0 and mood_initial - mood_burn * t > next_step_mood:
            dt_to_next = min(
                T - t,
                max(0.0, (current_mood - next_step_mood) / mood_burn),
            )
        else:
            dt_to_next = T - t

        segments.append(LinearSegment(a=eff, b=0.0, t_start=t, dt=dt_to_next))
        t += dt_to_next

    return segments
