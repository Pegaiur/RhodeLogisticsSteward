"""偏导数 D[d] = partial P / partial S[d] 计算

遍历 Mfg/Trade 分配中的类型 1f 读取者，
按公式 base_rate × hours × (bonus_per/per_unit) / 100 × unit_lmd 累加。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from steward_core.synergy.types import _B_BUFF_CONSUMER_TABLE
from .context import STATE_DIMS

if TYPE_CHECKING:
    from .context import SlotContext

_CR_EXP_PER_UNIT = 1000.0
_PG_LMD_PER_UNIT = 500.0
_TRADE_BASE_LMD_PER_HOUR = 10265.0 / 24.0

_BUFF_CONSUMER_DIMENSION: dict[str, str] = {}
"""干员名 → 消费的状态维度名"""

for _name, _entry in _B_BUFF_CONSUMER_TABLE.items():
    pk = _entry.pool_key
    if pk == "wushu_crystal":
        _BUFF_CONSUMER_DIMENSION[_name] = "yanhuo"
    elif pk == "thought_chains":
        _BUFF_CONSUMER_DIMENSION[_name] = "perception"
    else:
        _BUFF_CONSUMER_DIMENSION[_name] = pk


def _product_base_rate(product: str) -> float:
    """产品单位小时基础产出率（个/h）"""
    if product == "CombatRecord":
        return 1.0 / 3.0
    if product == "PureGold":
        return 1.0 / 1.2
    if product == "Money":
        return _TRADE_BASE_LMD_PER_HOUR
    return 1.0


def _product_lmd_per_unit(product: str) -> float:
    """产品单位 LMD 等值（战斗记录通过 xp_lmd_ratio=1.3 折算）"""
    if product == "CombatRecord":
        return _CR_EXP_PER_UNIT / 1.3
    if product == "PureGold":
        return _PG_LMD_PER_UNIT
    if product == "Money":
        return 1.0
    return 1.0


def compute_partial_derivatives(
    ctx: "SlotContext",
    window_idx: int = 0,
    drone_multiplier: float = 1.0,
) -> dict[str, float]:
    """计算产能对各状态维度的偏导数 D[d]

    遍历当前窗口 Mfg/Trade 槽位的 type1f 读取者，
    按公式累加每位读取者的边际产能贡献。
    D[d] 以 LMD 等值为量纲。

    对于迷迭香在 Mfg CR 槽位（12h 班次）:
      D[perception] = 0.333 卡/h × 12h × 0.01 × drone = 40 经验等值
    """
    hours = ctx.params.shift_hours if ctx.params else 12.0
    D: dict[str, float] = {d: 0.0 for d in STATE_DIMS}

    for facility_type in ("Mfg", "Trade"):
        rooms_processed = set()
        for a in ctx.windows[window_idx].assignments:
            if a.facility_type != facility_type:
                continue
            if a.is_empty:
                continue

            room_key = (a.facility_type, a.room_index)
            if room_key in rooms_processed:
                continue

            room_ops = ctx.room_ops(window_idx, a.facility_type, a.room_index)
            rooms_processed.add(room_key)

            base_rate = _product_base_rate(a.product)
            unit_lmd = _product_lmd_per_unit(a.product)

            for name in room_ops:
                if name not in _B_BUFF_CONSUMER_TABLE:
                    continue
                entry = _B_BUFF_CONSUMER_TABLE[name]
                if entry.target_room not in ("Mfg", "Trade"):
                    continue
                if entry.bonus_per <= 0:
                    continue

                dim = _BUFF_CONSUMER_DIMENSION.get(name)
                if dim is None:
                    continue

                rate = entry.bonus_per / entry.per_unit
                marginal = base_rate * hours * rate / 100.0 * unit_lmd * drone_multiplier
                D[dim] += marginal

    return D
