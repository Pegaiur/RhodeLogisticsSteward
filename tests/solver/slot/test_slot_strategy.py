"""SlotStrategy 槽位加工策略单元测试 (solver/slot/strategy.py)"""

import pytest

from steward_core.models import LayoutConfig, Operator
from steward_core.solver.config import SolverConfig
from steward_core.solver.slot.strategy import SlotStrategy
from tests.helpers import dummy_op


class TestSlotStrategy:
    """SlotStrategy: 基于 D[d] 反馈迭代的槽位加工求解策略"""

    @pytest.fixture
    def ops(self):
        return [
            dummy_op("char_001", "阿米娅"),
            dummy_op("char_002", "凯尔希"),
            dummy_op("char_003", "令"),
            dummy_op("char_004", "迷迭香"),
            dummy_op("char_005", "泡泡"),
            dummy_op("char_006", "槐琥"),
        ]

    def test_name_is_slot(self):
        s = SlotStrategy()
        assert s.name == "slot"

    def test_is_strategy_subclass(self):
        from steward_core.solver.strategy import Strategy
        assert issubclass(SlotStrategy, Strategy)

    def test_execute_returns_solve_result(self, ops):
        s = SlotStrategy()
        config = SolverConfig()
        op_lookup = {op.name: op for op in ops}

        result = s.execute(ops, config, op_lookup)

        from steward_core.models import SolveResult
        assert isinstance(result, SolveResult)

    def test_execute_no_crash_minimal_ops(self, ops):
        s = SlotStrategy()
        config = SolverConfig()
        op_lookup = {op.name: op for op in ops}

        result = s.execute(ops, config, op_lookup)
        assert result.plans is not None
