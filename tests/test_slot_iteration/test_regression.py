"""回归测试——零破坏验证"""

import ast
import pytest

from steward_core.solver.config import SolverConfig
from steward_core.solver.strategies.baseline import BaselineStrategy
from steward_core.solver.strategies.kbeam import KBeamStrategy
from steward_core.solver.strategies.iterative import IterativeStrategy

from tests.strategy_helpers import make_ops, assert_no_duplicate_operators


_STRATEGY_POOL = make_ops(
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


class TestBaselineUnchanged:

    def test_baseline_executes(self):
        from steward_core.solver import solve_mvp
        config = SolverConfig(strategy=BaselineStrategy())
        result = solve_mvp(_STRATEGY_POOL, config=config)
        assert len(result.plans) == 1
        assert_no_duplicate_operators(result)

    def test_baseline_unique_assignment(self):
        from steward_core.solver import solve_mvp
        config = SolverConfig(strategy=BaselineStrategy())
        result1 = solve_mvp(list(_STRATEGY_POOL), config=config)
        result2 = solve_mvp(list(_STRATEGY_POOL), config=config)

        names1 = sorted(n for a in result1.plans[0].assignments for n in a.operators)
        names2 = sorted(n for a in result2.plans[0].assignments for n in a.operators)
        assert names1 == names2


class TestKBeamUnchanged:

    def test_kbeam3_executes(self):
        from steward_core.solver import solve_mvp
        config = SolverConfig(strategy=KBeamStrategy(beam_width=3))
        result = solve_mvp(_STRATEGY_POOL, config=config)
        assert len(result.plans) == 1
        assert_no_duplicate_operators(result)


class TestIterativeUnchanged:

    def test_iterative_executes(self):
        from steward_core.solver import solve_mvp
        config = SolverConfig(strategy=IterativeStrategy(max_rounds=3))
        result = solve_mvp(_STRATEGY_POOL, config=config)
        assert len(result.plans) == 1
        assert_no_duplicate_operators(result)


class TestSlotIterationModuleBoundary:

    def test_no_solver_imports(self):
        """验证 slot_iteration.py 不导入 solver/ 下任何模块"""
        with open("steward_core/solver/slot_iteration.py", "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "solver" not in alias.name, f"禁止导入: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert "solver" not in node.module or "synergy" in node.module, (
                        f"禁止导入 solver 子模块: {node.module}"
                    )

    def test_no_wildcard_imports(self):
        import subprocess
        try:
            result = subprocess.run(
                ["python", "-m", "ruff", "check", "--select", "F403", "steward_core/"],
                capture_output=True, text=True, cwd=".",
            )
        except FileNotFoundError:
            pytest.skip("ruff 未安装")
        for line in result.stdout.strip().split("\n"):
            if line.strip() and "slot_iteration" in line:
                pytest.fail(f"检测到 import *: {line}")


class TestExhaustMfgDefaultUnchanged:

    def test_default_callable(self):
        """不传 precomputed_support 时 exhaust_mfg 可正常调用"""
        from steward_core.solver.exhaust_mfg import exhaust_mfg
        from steward_core.synergy._derived import MFG_ANCHORS

        ops = _STRATEGY_POOL
        assigned_ids = set()
        assigned_names = set()
        assignments = []
        op_lookup = {op.name: op for op in ops}
        locked_support = {"Control": set(), "Trade": set(), "Dormitory": set(), "Office": set()}

        config = SolverConfig()
        count = exhaust_mfg(
            ops, assigned_ids, assigned_names, assignments,
            op_lookup, locked_support,
            anchor_names=MFG_ANCHORS,
            config=config,
        )
        assert isinstance(count, int)


class TestExhaustTradeDefaultUnchanged:

    def test_default_callable(self):
        """不传 precomputed_support 时 exhaust_trade 可正常调用"""
        from steward_core.solver.exhaust_trade import exhaust_trade

        ops = _STRATEGY_POOL
        assigned_ids = set()
        assigned_names = set()
        assignments = []
        op_lookup = {op.name: op for op in ops}
        locked_support = {"Control": set(), "Trade": set(), "Dormitory": set(), "Office": set()}

        config = SolverConfig()
        count = exhaust_trade(
            ops, assigned_ids, assigned_names, assignments,
            op_lookup, locked_support,
            config=config,
        )
        assert isinstance(count, int)
