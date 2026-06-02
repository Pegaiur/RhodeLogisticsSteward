"""效率机制冲突解析 + 订单层竞争声明

订单机制在场时禁用特定效率联动函数（Layer 1: 布尔禁用）。
同时声明订单机制间的覆盖/稀释/增益关系（Layer 2 + Layer 3: 数值竞争）。
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
    "whisper": {"trade_ord_closure", "trade_ord_pepe"},
}

# ─── 订单层竞争关系（Phase B） ───────────────────────────────────────
# 三层模型中的 Layer 2：声明订单机制间的覆盖/稀释/增益关系。
#
# 消费关系：
#   cover 条目 → has_order_override() 判断是否存在覆盖型机制在场
#   dilute/boost 条目 → _decompose_trade_order() 分解时引用
#   具体数值计算 → production.py _compute_trade_distribution() 中 P4 分布
#
# 类型：cover（完全覆盖）| dilute（概率稀释）| boost（概率增益）

_ORDER_LAYER_COMPETITION: dict[tuple[str, str], dict] = {
    ("trade_ord_closure", "trade_ord_law"):        {"type": "cover",  "desc": "可露希尔特别订单覆盖但书违约"},
    ("trade_ord_closure", "trade_ord_long"):       {"type": "cover",  "desc": "可露希尔覆盖龙舌兰投资"},
    ("trade_ord_closure", "trade_ord_wt"):         {"type": "cover",  "desc": "可露希尔覆盖裁缝品质"},
    ("trade_ord_pepe", "trade_ord_law"):          {"type": "cover",  "desc": "佩佩独占订单覆盖但书违约"},
    ("trade_ord_pepe", "trade_ord_long"):         {"type": "cover",  "desc": "佩佩覆盖龙舌兰投资"},
    ("trade_ord_pepe", "trade_ord_wt"):           {"type": "cover",  "desc": "佩佩覆盖裁缝品质"},
    ("trade_ord_pepe", "trade_ord_closure"):      {"type": "cover",  "desc": "佩佩覆盖可露希尔特别订单"},
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


def has_order_override(
    operators: "list[Operator]",
) -> bool:
    """是否存在覆盖型订单机制（Closure 特别订单等）

    遍历 _ORDER_LAYER_COMPETITION 中 type="cover" 的条目，
    若房间内存在覆盖方 → 被覆盖方机制不生效。

    production.py 和 evaluate.py 应统一通过此函数检测覆盖型机制，
    而非各自硬编码 startswith("trade_ord_closure")。

    Args:
        operators: 干员列表

    Returns:
        True 若存在覆盖型订单机制
    """
    # 收集所有覆盖方前缀（type="cover" 的 source）
    override_prefixes: set[str] = set()
    for (source, _victim), meta in _ORDER_LAYER_COMPETITION.items():
        if meta["type"] == "cover":
            override_prefixes.add(source)

    if not override_prefixes:
        return False

    for op in operators:
        for sk in op.skills:
            if sk.room_type != "Trade":
                continue
            for prefix in override_prefixes:
                if sk.buff_id.startswith(prefix):
                    return True
    return False
