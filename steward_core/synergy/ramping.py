"""爬升型效率 — 通用爬升技能建模

含 _RAMPING_SKILL_TABLE（全设施通用）、operator_ramp_segments、operator_estimated_efficiency。
原在 mfg_linkages.py，随 Reception（会客室）爬升技能加入后独立为通用模块。
"""

from steward_core.models import LinearSegment, Operator
from steward_core.efficiency_fn import ramping_efficiency, integrate_segments

# ─── 爬升型技能表（全设施通用） ─────────────────────────────────────

_RAMPING_SKILL_TABLE: dict[str, tuple[float, float, float]] = {
    "manu_prod_spd_addition[100]": (0.0, 2.0, 20.0),  # 例行清扫 (阿罗玛): 0→20%@2%/h
    "manu_prod_spd_addition[030]": (20.0, 1.0, 25.0),  # 急性子 (芬): 20→25%@1%/h
    "manu_prod_spd_addition[031]": (20.0, 1.0, 25.0),  # "等不及" (刻俄柏): 20→25%@1%/h
    "manu_prod_spd_addition[040]": (15.0, 2.0, 25.0),  # 慢性子 (克洛丝): 15→25%@2%/h
    "manu_prod_spd_addition[041]": (15.0, 2.0, 25.0),  # 延时摄影 (稀音): 15→25%@2%/h
    "meet_spd_hast[000]": (20.0, 2.0, 30.0),  # 聚影 (伊内丝 会客室): 20→30%@2%/h
}


def operator_ramp_segments(
    op: Operator,
    room_type: str,
    product: str,
    T: float = 12.0,
    t_initial: float = 0.0,
    mood_burn: float = 0.0,
    mood_initial: float = 24.0,
) -> list[LinearSegment] | None:
    """检查干员是否持有爬升型技能，返回 ramping_efficiency 段

    返回值约定: 有爬升技能 → 分段列表，无 → None（由调用方回退到 constant_efficiency）。
    t_initial: 已连续工作小时数（暖机偏移，默认 0）。
    mood_burn/mood_initial: 心情衰减参数，透传至 ramping_efficiency。
    """
    for sk in op.skills:
        if sk.room_type != room_type:
            continue
        if sk.buff_id in _RAMPING_SKILL_TABLE:
            k0, r, ceiling = _RAMPING_SKILL_TABLE[sk.buff_id]
            return ramping_efficiency(
                k0=k0, r=r, ceiling=ceiling,
                mood_burn=mood_burn, T=T, t_initial=t_initial,
                mood_initial=mood_initial,
            )
    return None


def operator_estimated_efficiency(
    op: Operator,
    room_type: str,
    product: str | None = None,
    T: float = 12.0,
) -> float:
    """获取干员在指定设施下的预期平均效率（含爬升）

    对爬升型技能计算 T 小时 ramp 积分后的平均效率，
    非爬升技能回退到 skill.efficient 字段最高值，
    无匹配技能返回 0。

    用于排序/比较场景——槐琥配合意识、孑订单压缩等游戏公式
    中"效率"是全口径概念，包含爬升增量。

    T: 排班时长（h），默认 12.0。多班次调用应传入实际班次时长。
    """
    ramp = operator_ramp_segments(op, room_type, product or "", T)
    if ramp is not None:
        return integrate_segments(ramp, T) / T
    # 回退：直接取 skill.efficient 最高值，无 misleading 命名
    best = -999.0
    for sk in op.skills:
        if sk.effective_for(room_type, product):
            eff = sk.efficient.get(product) if product else sk.efficient.max_value()
            if eff > best:
                best = eff
    return best if best > -999.0 else 0.0
