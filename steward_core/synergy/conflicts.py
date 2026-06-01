"""效率机制冲突解析

订单机制在场时禁用特定效率联动函数。
与 Phase B 的机会成本表互补：本模块处理布尔"是否调用"，机会成本表处理数值"扣多少"。

仅使用 _ORDER_ANCHOR_PREFIXES（不含 vodfox）——冲突检测只需识别禁用方
（如 Closure）而非被禁用方（如 whisper）。trade.py 的 _ORDER_MECHANISM_PREFIXES
额外包含 vodfox 是为了识别候选池成员，与本模块用途不同。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from steward_core.synergy.helpers import _ORDER_ANCHOR_PREFIXES

if TYPE_CHECKING:
    from steward_core.models import Operator

_ORDER_PREFIXES = tuple(sorted(_ORDER_ANCHOR_PREFIXES))

# 效率机制名 → 导致其被禁用的订单机制 buff 前缀集合
# Phase B 扩展点：新增覆盖型订单机制时在此表追加条目
_EFF_MECH_DISABLERS: dict[str, set[str]] = {
    "whisper": {"trade_ord_closure"},
}

# ─── 订单层竞争关系（Phase B） ───────────────────────────────────────
# 语义与 _EFF_MECH_DISABLERS 正交：
#   _EFF_MECH_DISABLERS → 布尔"是否禁用效率联动"
#   _ORDER_LAYER_COMPETITION → 数值"订单机制间竞争/增益"
#
# 类型：cover（完全覆盖）| dilute（概率稀释）| boost（概率增益）
# 消费者：production.py _compute_order_layer_competition()

_ORDER_LAYER_COMPETITION: dict[tuple[str, str], dict] = {
    ("trade_ord_closure", "trade_ord_law"):        {"type": "cover",  "desc": "可露希尔特别订单覆盖但书违约"},
    ("trade_ord_closure", "trade_ord_long"):       {"type": "cover",  "desc": "可露希尔覆盖龙舌兰投资"},
    ("trade_ord_closure", "trade_ord_wt"):         {"type": "cover",  "desc": "可露希尔覆盖裁缝品质"},
    ("trade_ord_wt", "trade_ord_law"):             {"type": "dilute", "desc": "裁缝P4↑降低但书2/3金订单池份额"},
    ("trade_ord_wt", "trade_ord_long"):            {"type": "boost",  "desc": "裁缝P4↑扩大龙舌兰4金投资触发率"},
}


def resolve_efficiency_conflicts(
    operators: "list[Operator]",
    room_type: str,
) -> "frozenset[str]":
    """返回因订单机制在场而被禁用的效率机制名集合

    检测房间内是否存在覆盖型订单机制（如 Closure 特别订单），
    若存在则对应的效率联动（如 whisper 低语）不应激活。

    Args:
        operators: 房间内干员列表
        room_type: 房间类型

    Returns:
        被禁用的效率机制名集合（当前仅含 "whisper" 或无）
    """
    if room_type != "Trade":
        return frozenset()

    active_order_prefixes: set[str] = set()
    for op in operators:
        for sk in op.skills:
            if sk.room_type != "Trade":
                continue
            bid = sk.buff_id
            for prefix in _ORDER_PREFIXES:
                if bid.startswith(prefix):
                    active_order_prefixes.add(prefix)
                    break

    disabled: set[str] = set()
    for eff_mech, disablers in _EFF_MECH_DISABLERS.items():
        if active_order_prefixes & disablers:
            disabled.add(eff_mech)
    return frozenset(disabled)
