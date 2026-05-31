"""归零组合的机会成本计算

所有归零类联动（whisper / automation / zeroing_variant）的机会成本
均通过本模块的 compute_opportunity_cost_lmd() 计算，
在穷举评分循环中作为减项内联使用。

whisper（巫恋低语）:
  归零室友，自身 +45%/人。补偿存在 → max(own_eff - 45%, 0)

automation（森蚺/温蒂/异客/掠风）:
  归零室友，自身获发电加成。无补偿 → own_eff 全额 × sensitivity

zeroing_variant（科学改造/流程优化）:
  归零室友。无补偿 → 同 automation

这是"机会成本补充覆盖方案"(time-slot-scheduling-model.md) 的 Phase 1：
组合级求值修正。Phase 2 的 lambda_mood + swap_cost 跨窗口定价
将在本模块之上叠加。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .partials import _CR_EXP_PER_UNIT, _PG_LMD_PER_UNIT, _TRADE_BASE_LMD_PER_HOUR

if TYPE_CHECKING:
    from steward_core.models import Operator

# ─── 换算常量 ─────────────────────────────────────────────────────────
# 产品单位基础产出率（单位/h），与 partials._product_base_rate() 保持一致
_MFG_CR_BASE = 1.0 / 3.0
_MFG_PG_BASE = 1.0 / 1.2

# ─── 归零检测 ─────────────────────────────────────────────────────────

_WHISPER_PREFIX = "trade_ord_vodfox"

# ─── 缩放参数 ─────────────────────────────────────────────────────────

_AUTOMATION_SENSITIVITY = 0.5
"""自动化/归零变体敏感度缩放。

归零室友无等价补偿，全额 own_eff 扣减会导致组合从不被选中。
0.5 使自动化组合在室友效率较低时仍有机会参与排序。
Phase 2 可升级为 SolverParams 可调参数。
"""


def compute_opportunity_cost_lmd(
    combo_ops: list,
    room_type: str,
    product: str,
    shift_hours: float,
) -> float:
    """计算归零组合中被归零干员的机会成本（LMD 等值）

    自动检测组合中的归零机制类型并应用对应公式。

    Returns:
        机会成本 LMD 等值（非负值，调用方从评分中扣除）。
        无归零机制时返回 0.0。
    """
    mode, zeroer_names = _detect_mode(combo_ops, room_type)
    if mode is None:
        return 0.0

    zeroed_ops = [op for op in combo_ops if op.name not in zeroer_names]
    if not zeroed_ops:
        return 0.0

    cost_pct = _cost_pct(zeroed_ops, mode, room_type, product)
    if cost_pct <= 0.0:
        return 0.0

    return _pct_to_lmd(cost_pct, room_type, product, shift_hours)


def _detect_mode(
    combo_ops: list,
    room_type: str,
) -> tuple[str | None, set[str]]:
    """检测组合中的归零机制类型

    Returns:
        (mode, zeroer_names)
        mode: "whisper" | "automation" | "zeroing" | None
        zeroer_names: 归零者干员名集合（用于从 combo 中排除）
    """
    # 优先级: whisper > automation > zeroing_variant
    # 同房不可能同时存在两种归零机制（互斥），此处仅按优先级短路

    if room_type == "Trade":
        for op in combo_ops:
            for sk in op.skills:
                if sk.buff_id.startswith(_WHISPER_PREFIX):
                    return "whisper", {op.name}

    if room_type == "Mfg":
        auto_names: set[str] = set()
        from steward_core.synergy.mfg_linkages import _POWER_BUFF_BONUS, _A_AUTOMATION_FALLBACK
        for op in combo_ops:
            if op.name in _A_AUTOMATION_FALLBACK:
                auto_names.add(op.name)
                continue
            for sk in op.skills:
                if sk.buff_id in _POWER_BUFF_BONUS:
                    auto_names.add(op.name)
                    break
        if auto_names:
            return "automation", auto_names

        from steward_core.synergy import _ZEROING_VARIANT_TABLE
        for op in combo_ops:
            for sk in op.skills:
                if sk.room_type == "Mfg" and sk.buff_id in _ZEROING_VARIANT_TABLE:
                    return "zeroing", {op.name}

    return None, set()


def _cost_pct(
    zeroed_ops: list,
    mode: str,
    room_type: str,
    product: str,
) -> float:
    """逐干员计算被归零的效率百分比机会成本汇总"""
    total = 0.0
    for op in zeroed_ops:
        own_eff = max(op.best_efficiency(room_type, product), 0.0)
        if mode == "whisper":
            total += max(own_eff - 45.0, 0.0)
        else:
            total += own_eff
    if mode != "whisper":
        total *= _AUTOMATION_SENSITIVITY
    return total


def _pct_to_lmd(
    cost_pct: float,
    room_type: str,
    product: str,
    shift_hours: float,
) -> float:
    """效率百分比 → LMD 等值换算"""
    if room_type == "Trade":
        return cost_pct * _TRADE_BASE_LMD_PER_HOUR * shift_hours / 100.0
    if product == "CombatRecord":
        return cost_pct * _MFG_CR_BASE * (_CR_EXP_PER_UNIT / 1.3) * shift_hours / 100.0
    return cost_pct * _MFG_PG_BASE * _PG_LMD_PER_UNIT * shift_hours / 100.0
