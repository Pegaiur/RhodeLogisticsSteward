"""K-Beam Strategy 测试

TDD 三层：单元（排斥分配器） → 集成（KBeamStrategy） → 对比（vs Baseline）
"""

import pytest
from steward_core.solver.greed import (
    _greedy_allocate_with_support,
    _greedy_allocate_with_support_excluding,
)
from tests.strategy_helpers import make_op, strategy_runner, assert_plan_structure


# ─── 4b.1 单元测试：排斥分配器 ────────────────────────────────────

def _build_evaluated(n: int) -> list:
    """构造 n 个互不冲突的评分元组，分数递减"""
    return [
        (float(100 - i), [f"op_{i}_a", f"op_{i}_b"], [], {})
        for i in range(n)
    ]


class TestGreedyAllocateExcluding:

    def test_无排斥_等价于原贪心(self):
        """exclude_sets=None → 与原函数输出一致"""
        ev = _build_evaluated(10)
        r1 = _greedy_allocate_with_support(ev, room_count=2)
        r2 = _greedy_allocate_with_support_excluding(ev, room_count=2)
        assert r1 == r2

    def test_排斥唯一解_返回None(self):
        """只有 2 个可用 combo → 排斥后无解"""
        ev = _build_evaluated(2)
        forbidden = frozenset({("op_0_a", "op_0_b"), ("op_1_a", "op_1_b")})
        result = _greedy_allocate_with_support_excluding(
            ev, room_count=2, exclude_sets=[forbidden],
        )
        assert result is None

    def test_排斥首选_返回次优(self):
        """排斥最高分分配 → 贪心被迫取次优集合"""
        ev = _build_evaluated(6)
        # 原贪心取 combo 0 + combo 1
        r1 = _greedy_allocate_with_support(ev, room_count=2)
        first_set = frozenset(tuple(names) for names, _ in r1)

        r2 = _greedy_allocate_with_support_excluding(
            ev, room_count=2, exclude_sets=[first_set],
        )
        # 次优应为 combo 0 + combo 2（被排斥的恰好是 {0,1}）
        assert r2 is not None
        assert r2 != r1

    def test_多轮排斥_每条路径不同(self):
        """迭代 K=3 次，3 条路径的 combo 集合互不相同"""
        ev = _build_evaluated(10)
        used = []
        results = []
        for _ in range(3):
            r = _greedy_allocate_with_support_excluding(
                ev, room_count=2, exclude_sets=used,
            )
            if r is None:
                break
            results.append(r)
            used.append(frozenset(tuple(names) for names, _ in r))
        assert len(results) >= 2
        # 所有路径互不相同
        for i in range(len(results)):
            for j in range(i + 1, len(results)):
                assert results[i] != results[j]

    def test_排斥耗尽_提前终止(self):
        """C(3,2)=3 种分配，K=5 → 返回 3 条后终止"""
        ev = _build_evaluated(3)
        used = []
        results = []
        for _ in range(5):
            r = _greedy_allocate_with_support_excluding(
                ev, room_count=2, exclude_sets=used,
            )
            if r is None:
                break
            results.append(r)
            used.append(frozenset(tuple(names) for names, _ in r))
        # C(3,2)=3 种互不冲突的分配
        assert len(results) == 3
