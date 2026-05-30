"""剩余设施 + 中枢 单元测试"""

import pytest

from steward_core.models import LayoutConfig, Operator
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext
from steward_core.solver.slot.control import phase_control
from steward_core.solver.slot.remaining import phase_remaining


def _dummy_op(char_id: str, name: str) -> Operator:
    return Operator(char_id=char_id, name=name, skills=[])


class TestPhaseControl:
    @pytest.fixture
    def ops(self):
        return [
            _dummy_op("char_a", "A"),
            _dummy_op("char_b", "B"),
            _dummy_op("char_c", "C"),
            _dummy_op("char_d", "D"),
            _dummy_op("char_e", "E"),
        ]

    def test_no_control_skill_no_fill(self, ops):
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_control(ctx)
        assert ctx.ops_of_type(0, "Control") == []

    def test_no_crash_empty_d(self, ops):
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_control(ctx, 0, {})


class TestPhaseRemaining:
    @pytest.fixture
    def ops(self):
        return [
            _dummy_op("char_a", "A"),
            _dummy_op("char_b", "B"),
            _dummy_op("char_c", "C"),
        ]

    def test_no_crash_empty_skills(self, ops):
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_remaining(ctx)
        assert isinstance(ctx.ops_of_type(0, "Power"), list)
        assert isinstance(ctx.ops_of_type(0, "Reception"), list)
        assert isinstance(ctx.ops_of_type(0, "Office"), list)
        assert isinstance(ctx.ops_of_type(0, "Dormitory"), list)
