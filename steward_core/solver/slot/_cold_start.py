"""冷启动 BuffPool 估计 — 供 Phase A/B 在 Control/Dorm 为空时使用

槽位加工模型管线: phase_mfg/trade → phase_control → phase_remaining
Phase A/B 执行时 Control/Dorm/Office 尚未填充，compute_buff_pool 拿到空输入，
导致 type1f 消费者的 BuffPool 加成恒为 0。

compute_consumer_D() 遍历可用干员池中的 type-1f 消费者，
按真实边际贡献公式计算 D_cold，替代旧 {d:1.0} 均匀权重。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from steward_core.constants import (
    MFG_CR_BASE_RATE, MFG_PG_BASE_RATE,
    CR_EXP_PER_UNIT, PG_LMD_PER_UNIT,
    XP_LMD_RATIO, TRADE_BASE_LMD_PER_DAY,
)
from steward_core.synergy.types import _B_BUFF_CONSUMER_TABLE
from .context import STATE_DIMS
from .contribution import contribution

if TYPE_CHECKING:
    from .context import SlotContext
    from steward_core.models import Operator

# Mfg 加权平均 base_rate × unit_lmd（243 布局 CR:PG = 0.5:0.5）
_MFG_AVG_BASE_LMD = (
    0.5 * MFG_CR_BASE_RATE * CR_EXP_PER_UNIT / XP_LMD_RATIO
    + 0.5 * MFG_PG_BASE_RATE * PG_LMD_PER_UNIT
)

# Trade 单位小时基础 LMD 产出
_TRADE_BASE_LMD_PER_H = TRADE_BASE_LMD_PER_DAY / 24.0


def compute_consumer_D(ctx: "SlotContext") -> dict[str, float]:
    """基于可用干员池中的 type-1f 消费者直接计算 D_cold

    遍历 _B_BUFF_CONSUMER_TABLE，检查每位消费者是否在 ctx.operators 中，
    按公式累加各维度的边际贡献（LMD 等值/状态单位）：

        D[d] += base_rate × hours × (bonus_per / per_unit) × conv / 100 × unit_lmd

    wushu_crystal → yanhuo 含 1/5 转换系数。
    """
    hours = ctx.params.shift_hours if ctx.params else 12.0
    D: dict[str, float] = {d: 0.0 for d in STATE_DIMS}

    for op in ctx.operators:
        entry = _B_BUFF_CONSUMER_TABLE.get(op.name)
        if entry is None or entry.bonus_per <= 0:
            continue

        # 基础产出率与单位 LMD
        if entry.target_room == "Trade":
            base_rate_unit_lmd = _TRADE_BASE_LMD_PER_H
        else:
            base_rate_unit_lmd = _MFG_AVG_BASE_LMD

        # 维度映射
        pk = entry.pool_key
        if pk == "wushu_crystal":
            dim = "yanhuo"
            conv = 1.0 / 5.0
        elif pk == "thought_chains":
            dim = "perception"
            conv = 1.0
        else:
            dim = pk
            conv = 1.0

        rate = entry.bonus_per / entry.per_unit
        D[dim] += base_rate_unit_lmd * hours * rate * conv / 100.0

    return D


def cold_start_ctrl_ops(ctx: "SlotContext", window_idx: int) -> list["Operator"]:
    """冷启动预估：按 contribution 取前 max_slots 个中枢干员"""
    params = ctx.params
    max_slots = params.control_max_slots if params else 5
    D_cold = compute_consumer_D(ctx)
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
    D_cold = compute_consumer_D(ctx)
    candidates = []
    for op in ctx.operators:
        if not op.has_skill_for("Dormitory", "Rest"):
            continue
        score = contribution(ctx, op.name, "Dormitory", window_idx, D_cold)
        candidates.append((score, op))
    candidates.sort(key=lambda x: -x[0])
    return [op for _score, op in candidates[:dorm_max]]
