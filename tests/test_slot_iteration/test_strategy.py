"""SlotIterationStrategy 集成测试"""

import pytest

from steward_core.models import Operator, Skill, EfficiencyMap, RoomAssignment
from steward_core.solver.config import SolverConfig
from steward_core.solver.strategies.slot_iteration import SlotIterationStrategy

from tests.strategy_helpers import make_ops, assert_no_duplicate_operators


class TestSlotIterationStrategy:

    def test_basic_execution_with_small_pool(self):
        ops = make_ops(
            ("普通制造1", "mfg_001", "Mfg", {"efficiency": 25.0, "product": "CombatRecord"}),
            ("普通制造2", "mfg_002", "Mfg", {"efficiency": 20.0, "product": "CombatRecord"}),
            ("普通制造3", "mfg_003", "Mfg", {"efficiency": 15.0, "product": "CombatRecord"}),
            ("普通赤金1", "pg_001", "Mfg", {"efficiency": 25.0, "product": "PureGold"}),
            ("普通赤金2", "pg_002", "Mfg", {"efficiency": 20.0, "product": "PureGold"}),
            ("普通赤金3", "pg_003", "Mfg", {"efficiency": 15.0, "product": "PureGold"}),
            ("普通贸易1", "tr_001", "Trade", {"efficiency": 30.0, "product": "Money"}),
            ("普通贸易2", "tr_002", "Trade", {"efficiency": 25.0, "product": "Money"}),
            ("普通贸易3", "tr_003", "Trade", {"efficiency": 20.0, "product": "Money"}),
            ("普通发电1", "pw_001", "Power", {"efficiency": 15.0, "product": "Drone"}),
            ("普通发电2", "pw_002", "Power", {"efficiency": 10.0, "product": "Drone"}),
            ("普通发电3", "pw_003", "Power", {"efficiency": 5.0, "product": "Drone"}),
        )

        strategy = SlotIterationStrategy()
        config = SolverConfig(strategy=strategy)
        from steward_core.solver import solve_mvp
        result = solve_mvp(ops, config=config)

        assert len(result.plans) == 1
        assert_no_duplicate_operators(result)

    def test_deterministic_output(self):
        ops = make_ops(
            ("制造A", "mfg_a", "Mfg", {"efficiency": 30.0, "product": "CombatRecord"}),
            ("制造B", "mfg_b", "Mfg", {"efficiency": 25.0, "product": "CombatRecord"}),
            ("贸易A", "tr_a", "Trade", {"efficiency": 30.0, "product": "Money"}),
            ("发电A", "pw_a", "Power", {"efficiency": 20.0, "product": "Drone"}),
        )

        strategy = SlotIterationStrategy()
        config = SolverConfig(strategy=strategy)
        from steward_core.solver import solve_mvp

        result1 = solve_mvp(list(ops), config=config)
        result2 = solve_mvp(list(ops), config=config)

        names1 = sorted(
            n for a in result1.plans[0].assignments for n in a.operators
        )
        names2 = sorted(
            n for a in result2.plans[0].assignments for n in a.operators
        )
        assert names1 == names2

    def test_no_crash_on_minimal_pool(self):
        ops = make_ops(
            ("唯一制造", "only_mfg", "Mfg", {"efficiency": 10.0, "product": "CombatRecord"}),
        )

        strategy = SlotIterationStrategy()
        config = SolverConfig(strategy=strategy)
        from steward_core.solver import solve_mvp
        result = solve_mvp(ops, config=config)

        assert len(result.plans) == 1

    def test_hot_start_executes_without_crash(self):
        ops = make_ops(
            ("制造1", "mfg_1", "Mfg", {"efficiency": 30.0, "product": "CombatRecord"}),
            ("制造2", "mfg_2", "Mfg", {"efficiency": 25.0, "product": "CombatRecord"}),
            ("制造3", "mfg_3", "Mfg", {"efficiency": 20.0, "product": "CombatRecord"}),
            ("赤金1", "pg_1", "Mfg", {"efficiency": 30.0, "product": "PureGold"}),
            ("赤金2", "pg_2", "Mfg", {"efficiency": 25.0, "product": "PureGold"}),
            ("赤金3", "pg_3", "Mfg", {"efficiency": 20.0, "product": "PureGold"}),
            ("贸易1", "tr_1", "Trade", {"efficiency": 30.0, "product": "Money"}),
            ("贸易2", "tr_2", "Trade", {"efficiency": 25.0, "product": "Money"}),
            ("贸易3", "tr_3", "Trade", {"efficiency": 20.0, "product": "Money"}),
            ("发电1", "pw_1", "Power", {"efficiency": 20.0, "product": "Drone"}),
            ("发电2", "pw_2", "Power", {"efficiency": 15.0, "product": "Drone"}),
            ("发电3", "pw_3", "Power", {"efficiency": 10.0, "product": "Drone"}),
        )

        from steward_core.solver import solve_mvp
        from steward_core.solver.strategies.baseline import BaselineStrategy

        baseline_config = SolverConfig(strategy=BaselineStrategy())
        baseline_result = solve_mvp(ops, config=baseline_config)

        strategy = SlotIterationStrategy()
        slot_config = SolverConfig(strategy=strategy)
        slot_result = solve_mvp(ops, config=slot_config)

        assert len(slot_result.plans) == 1
        assert len(baseline_result.plans) == 1
        assert_no_duplicate_operators(slot_result)

    def test_cold_start_executes_without_crash(self):
        ops = make_ops(
            ("制造1", "mfg_1", "Mfg", {"efficiency": 30.0, "product": "CombatRecord"}),
            ("制造2", "mfg_2", "Mfg", {"efficiency": 25.0, "product": "CombatRecord"}),
            ("贸易1", "tr_1", "Trade", {"efficiency": 30.0, "product": "Money"}),
            ("发电1", "pw_1", "Power", {"efficiency": 20.0, "product": "Drone"}),
        )

        strategy = SlotIterationStrategy(cold_start=True)
        config = SolverConfig(strategy=strategy)
        from steward_core.solver import solve_mvp
        result = solve_mvp(ops, config=config)

        assert len(result.plans) == 1
        assert_no_duplicate_operators(result)

    def test_cold_start_no_baseline_dependency(self):
        ops = make_ops(
            ("发电1", "pw_1", "Power", {"efficiency": 20.0, "product": "Drone"}),
            ("发电2", "pw_2", "Power", {"efficiency": 15.0, "product": "Drone"}),
        )

        strategy = SlotIterationStrategy(cold_start=True)
        config = SolverConfig(strategy=strategy)
        from steward_core.solver import solve_mvp
        result = solve_mvp(ops, config=config)

        assert len(result.plans) == 1
