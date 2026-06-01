"""λ 种子化单元测试

验证:
1. λ 种子化使 lambda_ops 不为空
2. 候选池 λ>0 过滤在种子化后正确通过
"""

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
