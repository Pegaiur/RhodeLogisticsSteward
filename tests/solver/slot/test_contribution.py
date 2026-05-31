"""统一贡献评分单元测试"""

import pytest

from steward_core.models import EfficiencyMap, LayoutConfig, Operator, Skill
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext
from steward_core.solver.slot.contribution import contribution


def _dummy_op(char_id: str, name: str) -> Operator:
    return Operator(char_id=char_id, name=name, skills=[])


def _dorm_op(name: str, char_id: str, recovery: float) -> Operator:
    """构造宿舍恢复型干员（含 Dormitory/Rest 技能）"""
    return Operator(
        char_id=char_id, name=name,
        skills=[Skill(
            buff_id=f"dorm_rec_{char_id}",
            buff_name="宿舍恢复技能",
            skill_icon="test",
            room_type="Dormitory",
            efficient=EfficiencyMap(raw={"all": recovery}),
        )],
    )


class TestContribution:
    @pytest.fixture
    def ops(self):
        return [
            _dummy_op("char_001", "阿米娅"),
            _dummy_op("char_002", "凯尔希"),
        ]

    @pytest.fixture
    def ctx(self, ops):
        return SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )

    def test_unknown_op_returns_neg_inf(self, ctx):
        assert contribution(ctx, "不存在", "Control") == float("-inf")

    def test_unknown_facility_returns_neg_inf(self, ctx):
        assert contribution(ctx, "阿米娅", "Unknown") == float("-inf")

    def test_control_returns_finite(self, ctx):
        ctx.place(0, "control_0_0", "阿米娅")
        result = contribution(ctx, "凯尔希", "Control")
        assert result != float("-inf")
        assert isinstance(result, float)

    def test_power_returns_finite(self, ctx):
        result = contribution(ctx, "阿米娅", "Power")
        assert result != float("-inf")

    def test_reception_returns_finite(self, ctx):
        result = contribution(ctx, "阿米娅", "Reception")
        assert result != float("-inf")

    def test_office_returns_finite(self, ctx):
        result = contribution(ctx, "阿米娅", "Office")
        assert result != float("-inf")

    def test_dormitory_returns_finite(self, ctx):
        result = contribution(ctx, "阿米娅", "Dormitory")
        assert result != float("-inf")


class TestDormContributionWithLambdaK:
    """宿舍贡献使用标量 λ_k 的行为测试"""

    @pytest.fixture
    def dorm_recovery_op(self):
        """恢复型宿舍干员（如菲亚梅塔，+2.0/h 恢复速率）"""
        return _dorm_op("菲亚梅塔", "char_fia", 200.0)

    @pytest.fixture
    def ctx_with_lambda_k(self, dorm_recovery_op):
        """带 λ_k=500 的上下文，per-op λ_ops 全为 0"""
        ctx = SlotContext.from_layout(
            [dorm_recovery_op],
            LayoutConfig.layout_243(),
            SolverParams(),
        )
        ctx.lambda_k = 500.0
        return ctx

    def test_dorm_recovery_uses_lambda_k_not_per_op(self, ctx_with_lambda_k):
        """λ_k > 0 且 per-op λ_ops=0 时，宿舍贡献应为正

        旧代码行为：per-op λ=0 → dorm reward 不触发 → contribution 仅含
        type2 状态写入。修复后应使用标量 λ_k，reward 始终锚定。
        """
        result = contribution(ctx_with_lambda_k, "菲亚梅塔", "Dormitory")
        assert result > 0.0, (
            f"λ_k={ctx_with_lambda_k.lambda_k} 时宿舍贡献应为正，实际={result}"
        )

    def test_dorm_recovery_zero_when_lambda_k_zero(self, dorm_recovery_op):
        """λ_k=0 时宿舍贡献仅含 type2 状态写入（无恢复奖励）"""
        ctx = SlotContext.from_layout(
            [dorm_recovery_op],
            LayoutConfig.layout_243(),
            SolverParams(),
        )
        ctx.lambda_k = 0.0
        result = contribution(ctx, "菲亚梅塔", "Dormitory")
        # 无 type2 状态写入技能、无恢复奖励 → 贡献为 0
        assert result == 0.0, f"λ_k=0 时恢复奖励应为 0，实际={result}"

    def test_dorm_recovery_positive_when_lambda_k_set(self, dorm_recovery_op):
        """设置 λ_k 后宿舍恢复型干员获得正贡献"""
        ctx = SlotContext.from_layout(
            [dorm_recovery_op],
            LayoutConfig.layout_243(),
            SolverParams(),
        )
        ctx.lambda_k = 300.0
        result = contribution(ctx, "菲亚梅塔", "Dormitory")
        assert result > 0.0, "λ_k > 0 时恢复型干员应有正贡献"

    def test_lambda_k_independent_of_per_op_lambda_ops(self, dorm_recovery_op):
        """λ_k 锚定贡献不受 per-op λ_ops 干扰"""
        ctx = SlotContext.from_layout(
            [dorm_recovery_op],
            LayoutConfig.layout_243(),
            SolverParams(),
        )
        ctx.lambda_k = 500.0
        ctx.lambda_ops["菲亚梅塔"] = 0.0  # per-op 为 0
        result = contribution(ctx, "菲亚梅塔", "Dormitory")
        assert result > 0.0, "贡献应来自 λ_k 而非 per-op λ_ops"
