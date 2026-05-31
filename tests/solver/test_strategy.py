"""求解策略抽象层单元测试 (solver/strategy.py)

测试 PartialSolution 状态快照与 Strategy ABC 接口契约。
"""

import pytest

from steward_core.solver.strategy import PartialSolution, Strategy
from steward_core.models import Operator, SolveResult


class TestPartialSolution:
    """PartialSolution: 排班状态快照"""

    def test_默认构造_空状态(self):
        ps = PartialSolution()
        assert ps.assigned_ids == set()
        assert ps.assigned_names == set()
        assert ps.assignments == []
        assert ps.locked_support == {}

    def test_empty_类方法_含默认键(self):
        ps = PartialSolution.empty()
        assert "Control" in ps.locked_support
        assert "Trade" in ps.locked_support
        assert "Dormitory" in ps.locked_support
        assert "Office" in ps.locked_support
        for v in ps.locked_support.values():
            assert isinstance(v, set)
            assert len(v) == 0

    def test_clone_独立副本(self):
        ps = PartialSolution(assigned_names={"迷迭香", "泡泡"})
        clone = ps.clone()

        assert clone.assigned_names == {"迷迭香", "泡泡"}
        clone.assigned_names.add("阿米娅")
        assert "阿米娅" not in ps.assigned_names

    def test_clone_locked_support_独立副本(self):
        ps = PartialSolution(locked_support={"Control": {"A"}})
        clone = ps.clone()

        clone.locked_support["Control"].add("B")
        assert "B" not in ps.locked_support["Control"]

    def test_clone_assignments_独立副本(self):
        ps = PartialSolution(assignments=[{"type": "Mfg"}])
        clone = ps.clone()

        clone.assignments.append({"type": "Trade"})
        assert len(ps.assignments) == 1
        assert len(clone.assignments) == 2


class TestStrategyABC:
    """Strategy ABC: 抽象基类接口"""

    def test_不可直接实例化(self):
        with pytest.raises(TypeError):
            Strategy()  # type: ignore[abstract]

    def test_子类可实例化(self):
        class DummyStrategy(Strategy):
            name = "dummy"

            def execute(
                self,
                operators: list[Operator],
                config,  # type: ignore[override]
                op_lookup: dict[str, Operator],
            ) -> SolveResult:
                return SolveResult(plans=[])

        s = DummyStrategy()
        assert s.name == "dummy"

    def test_子类execute_返回SolveResult(self):
        class DummyStrategy(Strategy):
            name = "dummy"

            def execute(
                self,
                operators: list[Operator],
                config,  # type: ignore[override]
                op_lookup: dict[str, Operator],
            ) -> SolveResult:
                return SolveResult(plans=[])

        result = DummyStrategy().execute([], None, {})
        assert isinstance(result, SolveResult)
