"""冷启动 BuffPool 估计 — 供 Phase A/B 在 Control/Dorm 为空时使用

槽位加工模型管线: phase_mfg/trade → phase_control → phase_remaining
Phase A/B 执行时 Control/Dorm/Office 尚未填充，compute_buff_pool 拿到空输入，
导致 type1f 消费者的 BuffPool 加成恒为 0。

本模块按 contribution 评分（非 best_efficiency）预估中枢和宿舍干员，
使冷启动 BuffPool 接近真实值，让迷迭香/黑键/乌有等消费者获得合理评分。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .context import STATE_DIMS
from .contribution import contribution

if TYPE_CHECKING:
    from .context import SlotContext
    from steward_core.models import Operator


def cold_start_ctrl_ops(ctx: "SlotContext", window_idx: int) -> list["Operator"]:
    """冷启动预估：按 contribution 取前 max_slots 个中枢干员"""
    params = ctx.params
    max_slots = params.control_max_slots if params else 5
    D_cold: dict[str, float] = {d: 1.0 for d in STATE_DIMS if d != "silent_resonance"}
    candidates = []
    for op in ctx.operators:
        if not op.has_skill_for("Control"):
            continue
        score = contribution(ctx, op.name, "Control", window_idx, D_cold)
        candidates.append((score, op))
    candidates.sort(key=lambda x: -x[0])
    return [op for _score, op in candidates[:max_slots]]


def cold_start_dorm_ops(ctx: "SlotContext", window_idx: int) -> list["Operator"]:
    """冷启动预估：按 contribution 取前 dorm_max 个宿舍干员"""
    params = ctx.params
    dorm_max = params.dorm_max_operators if params else 20
    D_cold: dict[str, float] = {d: 1.0 for d in STATE_DIMS if d != "silent_resonance"}
    candidates = []
    for op in ctx.operators:
        if not op.has_skill_for("Dormitory", "Rest"):
            continue
        score = contribution(ctx, op.name, "Dormitory", window_idx, D_cold)
        candidates.append((score, op))
    candidates.sort(key=lambda x: -x[0])
    return [op for _score, op in candidates[:dorm_max]]
