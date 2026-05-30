"""制造站穷举单元测试"""

import pytest

from steward_core.models import LayoutConfig, Operator
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext
from steward_core.solver.slot.mfg import phase_mfg


def _dummy_op(char_id: str, name: str) -> Operator:
    return Operator(char_id=char_id, name=name, skills=[])


class TestPhaseMfg:
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
        """候选池无 Mfg 技能干员时不崩溃"""
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_mfg(ctx)
        assert ctx.ops_of_type(0, "Mfg") == []

    def test_no_error_on_small_pool(self, ops):
        """小候选池能正常执行"""
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_mfg(ctx)
        mfg_ops = ctx.ops_of_type(0, "Mfg")
        assert isinstance(mfg_ops, list)
