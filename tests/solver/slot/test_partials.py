"""偏导数计算单元测试"""

import pytest

from steward_core.models import LayoutConfig, Operator
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext, STATE_DIMS
from steward_core.solver.slot.partials import (
    compute_partial_derivatives,
    _product_base_rate,
    _product_lmd_per_unit,
)


def _dummy_op(char_id: str, name: str) -> Operator:
    return Operator(char_id=char_id, name=name, skills=[])


class TestProductRates:
    def test_cr_base_rate(self):
        assert _product_base_rate("CombatRecord") == pytest.approx(1.0 / 3.0)

    def test_pg_base_rate(self):
        assert _product_base_rate("PureGold") == pytest.approx(1.0 / 1.2)

    def test_trade_base_rate(self):
        rate = _product_base_rate("Money")
        assert rate > 0

    def test_unknown_base_rate(self):
        assert _product_base_rate("Unknown") == 1.0

    def test_cr_lmd_per_unit(self):
        assert _product_lmd_per_unit("CombatRecord") == pytest.approx(1000.0 / 1.3)

    def test_pg_lmd_per_unit(self):
        assert _product_lmd_per_unit("PureGold") == 500.0

    def test_trade_lmd_per_unit(self):
        assert _product_lmd_per_unit("Money") == 1.0


class TestComputePartials:
    @pytest.fixture
    def ops(self):
        return [
            _dummy_op("char_001", "阿米娅"),
            _dummy_op("char_002", "凯尔希"),
        ]

    def test_empty_context_returns_zeros(self, ops):
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        D = compute_partial_derivatives(ctx)
        assert len(D) == 5
        assert all(d in D for d in STATE_DIMS)
        assert all(v == 0.0 for v in D.values())

    def test_no_reader_in_mfg_yields_zeros(self, ops):
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        ctx.place(0, "mfg_0_0", "阿米娅")
        ctx.place(0, "mfg_0_1", "凯尔希")
        D = compute_partial_derivatives(ctx)
        assert all(v == 0.0 for v in D.values())

    def test_result_has_all_dimensions(self, ops):
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        D = compute_partial_derivatives(ctx)
        assert set(D.keys()) == set(STATE_DIMS)
