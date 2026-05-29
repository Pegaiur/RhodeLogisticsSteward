"""IterativeStrategy 不动点迭代测试"""

from steward_core.solver.strategies import BaselineStrategy, IterativeStrategy
from tests.strategy_helpers import (
    make_op, strategy_runner, assert_plan_structure,
    assert_no_duplicate_operators, assert_operator_in_room,
)


def _minimal_pool() -> list:
    """构造含所有设施的最小干员池"""
    ops = []
    for i in range(9):
        ops.append(make_op(f"cr_{i}", f"cr_{i}", "Mfg",
                           efficiency=25.0, product="CombatRecord"))
    for i in range(9):
        ops.append(make_op(f"pg_{i}", f"pg_{i}", "Mfg",
                           efficiency=25.0, product="PureGold"))
    for i in range(9):
        ops.append(make_op(f"trade_{i}", f"trade_{i}", "Trade",
                           efficiency=30.0, product="Money"))
    for i in range(5):
        ops.append(make_op(f"ctrl_{i}", f"ctrl_{i}", "Control", efficiency=0.0))
    for i in range(3):
        ops.append(make_op(f"power_{i}", f"power_{i}", "Power", efficiency=20.0))
    for i in range(2):
        ops.append(make_op(f"rec_{i}", f"rec_{i}", "Reception", efficiency=25.0))
    ops.append(make_op("off_0", "off_0", "Office", efficiency=0.0))
    return ops


class TestIterativeCorrectness:
    """IterativeStrategy 正确性与约束"""

    def test_产出有效排班方案(self):
        ops = _minimal_pool()
        result = strategy_runner(IterativeStrategy, ops, max_rounds=3)
        plan = result.plans[0]
        mfg_count = sum(1 for a in plan.assignments if a.room_type == "Mfg")
        assert mfg_count >= 1
        for rt in ["Control", "Power", "Reception", "Office"]:
            assert any(a.room_type == rt for a in plan.assignments), f"缺少 {rt}"

    def test_无重复干员(self):
        ops = _minimal_pool()
        result = strategy_runner(IterativeStrategy, ops, max_rounds=3)
        assert_no_duplicate_operators(result)

    def test_产物类型正确(self):
        ops = _minimal_pool()
        result = strategy_runner(IterativeStrategy, ops, max_rounds=3)
        plan = result.plans[0]
        mfg_products = {a.product for a in plan.assignments if a.room_type == "Mfg"}
        assert "CombatRecord" in mfg_products
        assert "PureGold" in mfg_products

    def test_中枢五人上限(self):
        ops = _minimal_pool()
        result = strategy_runner(IterativeStrategy, ops, max_rounds=3)
        plan = result.plans[0]
        for a in plan.assignments:
            if a.room_type == "Control":
                assert len(a.operators) <= 5

    def test_单轮max_rounds_1(self):
        """max_rounds=1 不崩溃"""
        ops = _minimal_pool()
        result = strategy_runner(IterativeStrategy, ops, max_rounds=1)
        assert result.plans[0].assignments


class TestIterativeVsBaseline:
    """IterativeStrategy vs BaselineStrategy 回归对比"""

    def test_纯效率池_vs_baseline_产出不退化(self):
        """无 BuffPool 消费者的纯效率池：Iterative ≥ Baseline"""
        ops = _minimal_pool()
        base_result = strategy_runner(BaselineStrategy, ops)
        iter_result = strategy_runner(IterativeStrategy, ops, max_rounds=3)

        from steward_core.solver.refine import _production_score
        from steward_core.solver.params import SolverParams
        params = SolverParams()
        base_score = _production_score(base_result.plans[0], ops, params)
        iter_score = _production_score(iter_result.plans[0], ops, params)
        assert iter_score >= base_score * 0.99, \
            f"Iterative {iter_score:.1f} < Baseline {base_score:.1f}"
