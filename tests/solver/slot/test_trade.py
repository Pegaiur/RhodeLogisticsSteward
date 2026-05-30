"""贸易站穷举与联合分配单元测试"""

import pytest

from steward_core.models import LayoutConfig, Operator
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext
from steward_core.solver.slot.trade import (
    phase_trade,
    _has_whisper,
    _joint_allocate,
    _apply_whisper_opportunity,
)


def _dummy_op(char_id: str, name: str) -> Operator:
    return Operator(char_id=char_id, name=name, skills=[])


class TestWhisperDetection:
    def test_no_whisper(self):
        ops = [_dummy_op("a", "A"), _dummy_op("b", "B")]
        assert not _has_whisper(ops)


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


class TestWhisperOpportunity:
    def test_no_whisper_no_change(self):
        evaluated = [(100.0, ["A", "B", "C"]), (90.0, ["D", "E", "F"])]
        whisper = []
        result = _apply_whisper_opportunity(evaluated, whisper, [], 12.0)
        assert result == evaluated


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
