"""solve_slot() 端到端测试 (solver/slot/solver.py)

纯内存测试：验证槽位加工求解引擎完整管线不崩溃、满足基本结构约束。
"""

import pytest

from steward_core.models import LayoutConfig
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.solver import solve_slot
from tests.helpers import mk_op, mk_simple_skill, dummy_op


def _make_minimal_ops(mfg_count: int = 15, trade_count: int = 10) -> list:
    """构造最小可求解干员池"""
    ops = []
    for i in range(mfg_count):
        ops.append(mk_op(f"制造{i}", [
            mk_simple_skill("Mfg", 30.0, f"mfg_{i}"),
        ]))
    for i in range(trade_count):
        ops.append(mk_op(f"贸易{i}", [
            mk_simple_skill("Trade", 30.0, f"trade_{i}"),
        ]))
    ops.append(mk_op("中枢A", [mk_simple_skill("Control", 0.0, "ctrl_a")]))
    ops.append(mk_op("中枢B", [mk_simple_skill("Control", 0.0, "ctrl_b")]))
    ops.append(mk_op("发电A", [mk_simple_skill("Power", 10.0, "pw_a")]))
    ops.append(mk_op("会客A", [mk_simple_skill("Reception", 10.0, "rc_a")]))
    ops.append(mk_op("办公A", [mk_simple_skill("Office", 10.0, "of_a")]))
    ops.append(mk_op("宿舍A", [mk_simple_skill("Dormitory", 10.0, "dm_a")]))
    ops.append(mk_op("宿舍B", [mk_simple_skill("Dormitory", 10.0, "dm_b")]))
    return ops


class TestSolveSlotSingleWindow:
    """单窗口 solve_slot 端到端"""

    @pytest.fixture
    def ops(self):
        return _make_minimal_ops()

    def test_returns_solve_result(self, ops):
        params = SolverParams(shift_count=1, shift_hours=12)
        result = solve_slot(ops, params)
        from steward_core.models import SolveResult
        assert isinstance(result, SolveResult)

    def test_has_plans(self, ops):
        params = SolverParams(shift_count=1, shift_hours=12)
        result = solve_slot(ops, params)
        assert len(result.plans) >= 1

    def test_mfg_rooms_filled(self, ops):
        params = SolverParams(shift_count=1, shift_hours=12)
        result = solve_slot(ops, params)
        mfg_assignments = [
            a for a in result.plans[0].assignments
            if a.room_type == "Mfg"
        ]
        assert len(mfg_assignments) >= 1

    def test_trade_rooms_filled(self, ops):
        params = SolverParams(shift_count=1, shift_hours=12)
        result = solve_slot(ops, params)
        trade_assignments = [
            a for a in result.plans[0].assignments
            if a.room_type == "Trade"
        ]
        assert len(trade_assignments) >= 1

    def test_no_duplicate_operators(self, ops):
        params = SolverParams(shift_count=1, shift_hours=12)
        result = solve_slot(ops, params)
        all_names = []
        for a in result.plans[0].assignments:
            all_names.extend(a.operators)
        assert len(all_names) == len(set(all_names))

    def test_empty_pool_no_crash(self):
        params = SolverParams(shift_count=1, shift_hours=12)
        result = solve_slot([], params)
        from steward_core.models import SolveResult
        assert isinstance(result, SolveResult)
        assert len(result.plans) >= 1

    def test_single_window_no_refine_crash(self):
        """单窗口 → 执行 local_search_refine 后处理"""
        ops = _make_minimal_ops()
        params = SolverParams(shift_count=1, shift_hours=12)
        result = solve_slot(ops, params)
        assert result.plans is not None

    def test_with_explicit_layout(self, ops):
        layout = LayoutConfig.layout_243()
        params = SolverParams(shift_count=1, shift_hours=12)
        result = solve_slot(ops, params, layout=layout)
        assert len(result.plans) >= 1


class TestSolveSlotMultiWindow:
    """多窗口 solve_slot 端到端"""

    @pytest.fixture
    def ops(self):
        return _make_minimal_ops(mfg_count=20, trade_count=15)

    def test_two_windows_no_crash(self, ops):
        params = SolverParams(shift_count=2, shift_hours=12, interval_hours=0)
        result = solve_slot(ops, params)
        from steward_core.models import SolveResult
        assert isinstance(result, SolveResult)
        assert len(result.plans) == 2

    def test_each_window_has_assignments(self, ops):
        params = SolverParams(shift_count=2, shift_hours=12, interval_hours=0)
        result = solve_slot(ops, params)
        for plan in result.plans:
            assert len(plan.assignments) >= 1

    def test_no_window_uses_same_op_twice(self, ops):
        """同一窗口内无重复干员"""
        params = SolverParams(shift_count=2, shift_hours=12, interval_hours=0)
        result = solve_slot(ops, params)
        for plan in result.plans:
            names = []
            for a in plan.assignments:
                names.extend(a.operators)
            assert len(names) == len(set(names)), f"重复: {names}"

    def test_max_iterations_limit(self, ops):
        params = SolverParams(shift_count=2, shift_hours=12, interval_hours=0)
        result = solve_slot(ops, params, max_iterations=3)
        assert len(result.plans) == 2
