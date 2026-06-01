"""λ_k 种子化单元测试

验证:
1. λ 种子化使 lambda_ops 不为空
2. θ = lambda_k 语义正确
"""
import pytest

from steward_core.models import EfficiencyMap, LayoutConfig, Operator, Skill
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext


def _mk_mfg_op(name: str, char_id: str, eff: float) -> Operator:
    return Operator(
        char_id=char_id, name=name,
        skills=[Skill(
            buff_id=f"test_mfg_{char_id}", buff_name="测试",
            skill_icon="test", room_type="Mfg",
            efficient=EfficiencyMap(raw={"all": eff}),
        )],
    )


def _mk_dorm_op(name: str, char_id: str) -> Operator:
    return Operator(
        char_id=char_id, name=name,
        skills=[Skill(
            buff_id=f"dorm_rec_all[{char_id}]", buff_name="测试",
            skill_icon="test", room_type="Dormitory",
            efficient=EfficiencyMap(raw={"all": 0.25}),
        )],
    )


class TestTheta:
    """θ = lambda_k 单元测试"""

    def test_theta_equals_lambda_k(self):
        """θ 始终等于 lambda_k，不依赖 assigned_ids"""
        from steward_core.solver.slot.contribution import _avg_unassigned_worker_lambda

        ops = [
            _mk_mfg_op("制造A", "mfg_a", 30.0),
            _mk_mfg_op("制造B", "mfg_b", 30.0),
        ]
        ctx = SlotContext.from_layout(ops, LayoutConfig.layout_243(), SolverParams())
        ctx.lambda_k = 500.0

        result = _avg_unassigned_worker_lambda(ctx, 0)
        assert result == 500.0

    def test_theta_independent_of_assigned(self):
        """已分配状态不影响 θ"""
        from steward_core.solver.slot.contribution import _avg_unassigned_worker_lambda

        ops = [
            _mk_mfg_op("制造A", "mfg_a", 30.0),
            _mk_mfg_op("制造B", "mfg_b", 30.0),
        ]
        ctx = SlotContext.from_layout(ops, LayoutConfig.layout_243(), SolverParams())
        ctx.lambda_k = 300.0
        ctx.lambda_ops = {"制造A": 9999.0, "制造B": 5000.0}
        ctx.place(0, "mfg_0_0", "制造A")

        result = _avg_unassigned_worker_lambda(ctx, 0)
        assert result == 300.0  # θ = lambda_k，不受已分配高 λ 影响


class TestLambdaSeeding:
    """λ 种子化测试"""

    def test_no_lambda_no_candidate(self):
        """未种子化时，纯生产干员候选池过滤必然失败"""
        ops = [
            _mk_mfg_op("制造A", "mfg_a", 30.0),
            _mk_dorm_op("宿管A", "dm_a"),
        ]
        ctx = SlotContext.from_layout(ops, LayoutConfig.layout_243(), SolverParams())
        ctx.lambda_k = 300.0

        assert ctx.lambda_ops.get("制造A", 0.0) == 0.0
        assert ctx.op_lookup["宿管A"].has_skill_for("Dormitory", "Rest")
        assert ctx.op_lookup["制造A"].has_skill_for("Mfg")
        assert not ctx.op_lookup["制造A"].has_skill_for("Dormitory", "Rest")

    def test_seeded_lambda_enables_candidate(self):
        """种子化后，λ>0 使生产干员通过候选池"""
        ops = [
            _mk_mfg_op("制造A", "mfg_a", 30.0),
        ]
        ctx = SlotContext.from_layout(ops, LayoutConfig.layout_243(), SolverParams())
        ctx.lambda_k = 300.0

        for op in ops:
            if op.has_skill_for("Mfg") or op.has_skill_for("Trade"):
                ctx.lambda_ops[op.name] = ctx.lambda_k

        assert ctx.lambda_ops.get("制造A", 0.0) == 300.0
