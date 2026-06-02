"""全局去 lambda + mood-driven 宿舍 TDD 测试"""

import pytest

from steward_core.models import LayoutConfig
from steward_core.mood_flow import MoodContext
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext
from steward_core.solver.slot.contribution import contribution
from steward_core.solver.slot.remaining import phase_remaining
from steward_core.solver.slot.control import phase_control
from tests.helpers import mk_op, mk_simple_skill


def _make_ctx(ops, params=None):
    if params is None:
        params = SolverParams()
    return SlotContext.from_layout(ops, LayoutConfig.layout_243(), params)


def _make_mc(ops, moods, params=None):
    if params is None:
        params = SolverParams()
    mc = MoodContext.fresh(ops, params)
    object.__setattr__(mc, "operator_moods", moods)
    return mc


class TestDormGate:
    def test_dorm_gate_allows_non_rest_mood_depleted(self):
        ops = [
            mk_op("W", [mk_simple_skill("Mfg", 30.0)]),
            mk_op("D", [mk_simple_skill("Dormitory", 10.0, buff_id="d1", buff_name="Rest")]),
        ]
        ctx = _make_ctx(ops)
        mc = _make_mc(ops, {"W": 10.0, "D": 24.0})
        from steward_core.solver.slot.partials import compute_partial_derivatives
        D = compute_partial_derivatives(ctx, 0)
        phase_remaining(ctx, 0, D, mood_ctx=mc)
        dorm_ops = ctx.ops_of_type(0, "Dormitory")
        assert "W" in dorm_ops or "D" in dorm_ops


class TestDormScoring:
    def test_recovery_value_positive(self):
        ops = [mk_op("A", [mk_simple_skill("Mfg", 30.0)])]
        ctx = _make_ctx(ops)
        mc = _make_mc(ops, {"A": 12.0})
        ctx.op_peak_eff["A"] = 30.0
        score = contribution(ctx, "A", "Dormitory", 0, mood_ctx=mc, room_index=0)
        assert score > 0, f"恢复价值应为正: {score}"

    def test_full_mood_zero_recovery_value(self):
        ops = [mk_op("A", [mk_simple_skill("Mfg", 30.0)])]
        ctx = _make_ctx(ops)
        mc = _make_mc(ops, {"A": 24.0})
        ctx.op_peak_eff["A"] = 30.0
        score = contribution(ctx, "A", "Dormitory", 0, mood_ctx=mc, room_index=0)
        assert score == 0.0 or score < 10.0, f"满 mood 恢复价值应接近零: {score}"

    def test_higher_eff_higher_recovery_value(self):
        ops = [
            mk_op("High", [mk_simple_skill("Mfg", 30.0)]),
            mk_op("Low", [mk_simple_skill("Mfg", 10.0)]),
        ]
        ctx = _make_ctx(ops)
        mc_high = _make_mc(ops, {"High": 12.0, "Low": 24.0})
        mc_low = _make_mc(ops, {"High": 24.0, "Low": 12.0})
        ctx.op_peak_eff["High"] = 30.0
        ctx.op_peak_eff["Low"] = 10.0
        score_high = contribution(ctx, "High", "Dormitory", 0, mood_ctx=mc_high, room_index=0)
        score_low = contribution(ctx, "Low", "Dormitory", 0, mood_ctx=mc_low, room_index=0)
        assert score_high > score_low, f"High({score_high:.1f}) 应 > Low({score_low:.1f})"

    def test_no_lambda_in_dorm_score(self):
        ops = [mk_op("A", [mk_simple_skill("Mfg", 30.0)])]
        ctx = _make_ctx(ops)
        mc = _make_mc(ops, {"A": 12.0})
        ctx.op_peak_eff["A"] = 30.0
        ctx.lambda_ops["A"] = 9999.0
        score_with = contribution(ctx, "A", "Dormitory", 0, mood_ctx=mc, room_index=0)
        ctx.lambda_ops["A"] = 0.0
        score_without = contribution(ctx, "A", "Dormitory", 0, mood_ctx=mc, room_index=0)
        assert score_with == pytest.approx(score_without)


class TestContributionNoLambda:
    def test_control_contribution_no_lambda_deduction(self):
        ops = [
            mk_op("A", [mk_simple_skill("Control", 0.0)]),
        ]
        ctx = _make_ctx(ops)
        mc = _make_mc(ops, {"A": 24.0})
        ctx.lambda_ops["A"] = 9999.0
        score = contribution(ctx, "A", "Control", 0, mood_ctx=mc)
        assert score >= 0, f"不应因 lambda 变负: {score}"


class TestPhaseCMoodTruncation:
    def test_control_full_mood_no_truncation(self):
        ops = [mk_op("A", [mk_simple_skill("Control", 0.0)])]
        ctx = _make_ctx(ops)
        mc = _make_mc(ops, {"A": 24.0})
        score_full = contribution(ctx, "A", "Control", 0, mood_ctx=mc)
        score_no_mc = contribution(ctx, "A", "Control", 0, mood_ctx=None)
        assert score_full == pytest.approx(score_no_mc)

    def test_phase_control_passes_mood_ctx(self):
        ops = [
            mk_op("A", [mk_simple_skill("Control", 0.0)]),
            mk_op("B", [mk_simple_skill("Control", 0.0)]),
        ]
        ctx = _make_ctx(ops)
        mc = _make_mc(ops, {"A": 24.0, "B": 24.0})
        phase_control(ctx, 0, mood_ctx=mc)
        ctrl = ctx.ops_of_type(0, "Control")
        assert len(ctrl) >= 1


class TestNoLambdaE2E:
    def test_single_window_no_crash(self):
        from steward_core.solver.slot.solver import solve_slot
        from steward_core.models import SolveResult
        ops = []
        for i in range(15):
            ops.append(mk_op(f"M{i:02d}", [mk_simple_skill("Mfg", 30.0)]))
        for i in range(10):
            ops.append(mk_op(f"T{i:02d}", [mk_simple_skill("Trade", 30.0)]))
        ops.append(mk_op("C", [mk_simple_skill("Control", 0.0)]))
        for i in range(4):
            ops.append(mk_op(f"D{i:02d}", [mk_simple_skill("Dormitory", 10.0)]))
        params = SolverParams(shift_count=1, shift_hours=12, backpressure_damping=0.0)
        result = solve_slot(ops, params)
        assert isinstance(result, SolveResult)
        assert len(result.plans) >= 1

    def test_multi_window_no_crash(self):
        from steward_core.solver.slot.solver import solve_slot
        from steward_core.models import SolveResult
        ops = []
        for i in range(20):
            ops.append(mk_op(f"M{i:02d}", [mk_simple_skill("Mfg", 30.0)]))
        for i in range(12):
            ops.append(mk_op(f"T{i:02d}", [mk_simple_skill("Trade", 30.0)]))
        ops.append(mk_op("C1", [mk_simple_skill("Control", 0.0)]))
        ops.append(mk_op("C2", [mk_simple_skill("Control", 0.0)]))
        for i in range(4):
            ops.append(mk_op(f"D{i:02d}", [mk_simple_skill("Dormitory", 10.0)]))
        params = SolverParams(shift_count=3, shift_hours=12, backpressure_damping=0.0)
        result = solve_slot(ops, params)
        assert isinstance(result, SolveResult)
        assert len(result.plans) == 3
