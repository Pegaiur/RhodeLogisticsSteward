"""统一贡献评分单元测试"""

import pytest

from steward_core.models import LayoutConfig, Operator
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext
from steward_core.solver.slot.contribution import contribution


def _dummy_op(char_id: str, name: str) -> Operator:
    return Operator(char_id=char_id, name=name, skills=[])


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

    def test_lambda_penalty_reduces_contribution(self, ctx):
        ctx.lambda_ops["阿米娅"] = 100.0
        result_with_lambda = contribution(ctx, "阿米娅", "Power")
        ctx.lambda_ops["阿米娅"] = 0.0
        result_without_lambda = contribution(ctx, "阿米娅", "Power")
        assert result_with_lambda < result_without_lambda
