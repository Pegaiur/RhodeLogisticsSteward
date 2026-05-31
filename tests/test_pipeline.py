"""共享求解管道单元测试 (pipeline.py)

测试 PipelineResult 数据结构 + run() 管道编排。
"""

import pytest

from steward_core.pipeline import PipelineResult, run
from steward_core.solver.params import SolverParams
from tests.helpers import mk_op, mk_simple_skill


def _make_minimal_ops(mfg_count: int = 15, trade_count: int = 10) -> list:
    ops = []
    for i in range(mfg_count):
        ops.append(mk_op(f"制造{i}", [mk_simple_skill("Mfg", 30.0, f"mfg_{i}")]))
    for i in range(trade_count):
        ops.append(mk_op(f"贸易{i}", [mk_simple_skill("Trade", 30.0, f"trade_{i}")]))
    ops.append(mk_op("中枢A", [mk_simple_skill("Control", 0.0, "ctrl_a")]))
    ops.append(mk_op("发电A", [mk_simple_skill("Power", 10.0, "pw_a")]))
    ops.append(mk_op("会客A", [mk_simple_skill("Reception", 10.0, "rc_a")]))
    ops.append(mk_op("办公A", [mk_simple_skill("Office", 10.0, "of_a")]))
    return ops


# ─── PipelineResult ──────────────────────────────────────────────

class TestPipelineResult:
    def test_字段可赋值(self):
        from steward_core.models import SolveResult
        pr = PipelineResult(
            solve_result=SolveResult(plans=[]),
            productions=[],
            params=SolverParams(),
            config=None,  # type: ignore[arg-type]
            operators=[],
            mood_ctx=None,  # type: ignore[arg-type]
        )
        assert pr.solve_result is not None
        assert pr.productions == []


# ─── PipelineRun ─────────────────────────────────────────────────

class TestPipelineRun:
    @pytest.fixture
    def ops(self):
        return _make_minimal_ops()

    def test_返回PipelineResult(self, ops):
        params = SolverParams(shift_count=1, shift_hours=12)
        result = run(ops, params)
        assert isinstance(result, PipelineResult)

    def test_求解结果含排班计划(self, ops):
        params = SolverParams(shift_count=1, shift_hours=12)
        result = run(ops, params)
        assert len(result.solve_result.plans) >= 1

    def test_产出与计划数量匹配(self, ops):
        params = SolverParams(shift_count=1, shift_hours=12)
        result = run(ops, params)
        assert len(result.productions) == len(result.solve_result.plans)

    def test_config保持引用(self, ops):
        params = SolverParams(shift_count=1, shift_hours=12)
        result = run(ops, params)
        assert result.config is not None
        assert result.params is params

    def test_operators保持引用(self, ops):
        params = SolverParams(shift_count=1, shift_hours=12)
        result = run(ops, params)
        assert result.operators is ops

    def test_创建MoodContext(self, ops):
        params = SolverParams(shift_count=1, shift_hours=12)
        result = run(ops, params)
        from steward_core.mood_flow import MoodContext
        assert isinstance(result.mood_ctx, MoodContext)

    def test_空池不崩溃(self):
        params = SolverParams(shift_count=1, shift_hours=12)
        result = run([], params)
        assert isinstance(result, PipelineResult)
