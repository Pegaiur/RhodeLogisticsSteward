"""贸易站穷举与联合分配单元测试"""

import pytest

from steward_core.models import LayoutConfig, Operator
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext, STATE_DIMS
from steward_core.solver.slot.trade import (
    phase_trade,
    _joint_allocate,
)
from steward_core.synergy import BuffPool


def _dummy_op(char_id: str, name: str) -> Operator:
    return Operator(char_id=char_id, name=name, skills=[])


class TestJointAllocate:
    def test_basic(self):
        evaluated = [
            (100.0, ["A", "B", "C"]),
            (90.0, ["D", "E", "F"]),
            (80.0, ["A", "D", "G"]),
        ]
        result = _joint_allocate(evaluated, room_count=2)
        assert len(result) == 2
        flat = set()
        for names in result:
            for n in names:
                flat.add(n)
        assert len(flat) == 6

    def test_optimal_pair_avoids_conflict(self):
        evaluated = [
            (100.0, ["A", "B", "C"]),
            (90.0, ["A", "D", "E"]),
            (80.0, ["F", "G", "H"]),
        ]
        result = _joint_allocate(evaluated, room_count=2)
        flat = set()
        for names in result:
            for n in names:
                flat.add(n)
        assert len(flat) == 6

    def test_fallback_to_greedy_with_large_list(self):
        evaluated = [(float(i), [f"X{i}"]) for i in range(200)]
        result = _joint_allocate(evaluated, room_count=2)
        assert len(result) == 2

    def test_empty_returns_empty(self):
        assert _joint_allocate([], 2) == []


class TestPhaseTrade:
    @pytest.fixture
    def ops(self):
        return [
            _dummy_op("char_a", "A"),
            _dummy_op("char_b", "B"),
            _dummy_op("char_c", "C"),
            _dummy_op("char_d", "D"),
            _dummy_op("char_e", "E"),
        ]

    def test_empty_pool_no_crash(self, ops):
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_trade(ctx)
        assert isinstance(ctx.ops_of_type(0, "Trade"), list)


class TestSpillover:
    """Trade 外溢收益计算 — BuffPool 增量 × D_mfg"""

    def test_zero_delta_returns_zero(self):
        """delta 为全零 → spillover = 0"""
        D_mfg = {"perception": 30.0}
        delta = BuffPool()
        from steward_core.solver.slot.trade import _compute_spillover
        assert _compute_spillover(D_mfg, delta) == 0.0

    def test_perception_spillover(self):
        """perception +20, D[perception]=30 → spillover=600"""
        D_mfg = {"perception": 30.0, "yanhuo": 50.0}
        delta = BuffPool(perception=20)
        from steward_core.solver.slot.trade import _compute_spillover
        result = _compute_spillover(D_mfg, delta)
        assert result == pytest.approx(30.0 * 20.0)

    def test_multiple_dimensions_spillover(self):
        """perception+20 + yanhuo+10 → Σ D[d]×delta"""
        D_mfg = {"perception": 30.0, "yanhuo": 50.0, "silent_resonance": 0.0}
        delta = BuffPool(perception=20, yanhuo=10)
        from steward_core.solver.slot.trade import _compute_spillover
        result = _compute_spillover(D_mfg, delta)
        assert result == pytest.approx(30.0 * 20.0 + 50.0 * 10.0)

    def test_delta_negative_clamped_to_zero(self):
        """delta 负值字段被归零（BuffPool.__sub__ 已做负值归零）"""
        D_mfg = {"perception": 30.0}
        delta = BuffPool(perception=0, yanhuo=0)
        from steward_core.solver.slot.trade import _compute_spillover
        assert _compute_spillover(D_mfg, delta) == 0.0

    def test_empty_d_returns_zero(self):
        """D_mfg 为空 → 任何 delta 都产生 0 spillover"""
        D_mfg: dict[str, float] = {}
        delta = BuffPool(perception=20, yanhuo=10)
        from steward_core.solver.slot.trade import _compute_spillover
        assert _compute_spillover(D_mfg, delta) == 0.0
