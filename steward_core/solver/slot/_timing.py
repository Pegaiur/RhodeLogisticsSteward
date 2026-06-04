"""求解器内部计时（轻量、共享）

提供 `timed()` context manager 用于声明式计时，同 label 多次进入自动累加。
`dump()` 输出两级摘要：顶层阶段 + mfg/trade 细分。

通过环境变量 RHO_TIMING=0 关闭，关闭时 `timed()` 退化为零开销空操作。
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager

_TIMINGS: dict[str, float] = {}
_ENABLED = os.environ.get("RHO_TIMING", "1") == "1"


@contextmanager
def timed(label: str):
    """计时块：同 label 多次进入自动累加

    关闭状态（RHO_TIMING=0）时退化为空操作，零开销。
    """
    if not _ENABLED:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _TIMINGS[label] = _TIMINGS.get(label, 0.0) + (time.perf_counter() - t0)


# ── dump 输出顺序定义 ──────────────────────────────────────────

_TOP_LABELS = [
    "init",
    "ctx_to_result",
]

_SUB_LABELS = [
    "mfg.pool_build", "mfg.setup", "mfg.buff_pool", "mfg.evaluate_room",
    "mfg.opportunity", "mfg.combo_other", "mfg.allocate",
    "trade.pool_build", "trade.setup", "trade.buff_pool",
    "trade.evaluate_room", "trade.order_lmd", "trade.combo_other", "trade.allocate",
]


def dump(iterations: int, windows: int, file=None):
    """打印两级计时摘要 + 清空累积数据"""
    if not _ENABLED or not _TIMINGS:
        return

    total = sum(_TIMINGS.values())
    print(f"\n[计时] solve_slot 各阶段耗时 ({iterations}轮 × {windows}窗):", file=file)
    for label in _TOP_LABELS:
        elapsed = _TIMINGS.get(label, 0.0)
        pct = elapsed / total * 100 if total > 0 else 0
        print(f"  {label:25s} {elapsed:8.3f}s ({pct:5.1f}%)", file=file)
    print(f"  {'─' * 25}", file=file)
    print(f"  {'-- 细分 (mfg/trade) --':25s}", file=file)
    for label in _SUB_LABELS:
        elapsed = _TIMINGS.get(label, 0.0)
        pct = elapsed / total * 100 if total > 0 else 0
        print(f"  {label:25s} {elapsed:8.3f}s ({pct:5.1f}%)", file=file)
    print(f"  {'─' * 25}", file=file)
    print(f"  {'合计':25s} {total:8.3f}s", file=file)
    _TIMINGS.clear()
