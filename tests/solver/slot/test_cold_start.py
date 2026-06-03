"""冷启动消费者 D 计算单元测试

测试 compute_consumer_D：基于可用干员池中 type-1f 消费者的
边际贡献直接计算 D_cold，替代旧 {d:1.0} 均匀权重。
"""

from __future__ import annotations

import pytest

from steward_core.constants import TRADE_BASE_LMD_PER_DAY
from steward_core.models import LayoutConfig, Operator
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext, STATE_DIMS
from steward_core.solver.slot._cold_start import (
    compute_consumer_D,
    _MFG_AVG_BASE_LMD,
)


def _mock_op(char_id: str, name: str) -> Operator:
    return Operator(char_id=char_id, name=name, skills=[])


class TestComputeConsumerD:
    """消费者 D 直接计算"""

    @pytest.fixture
    def params(self) -> SolverParams:
        return SolverParams(shift_hours=12.0)

    @pytest.fixture
    def layout(self) -> LayoutConfig:
        return LayoutConfig.layout_243()

    # ── 正常路径 ────────────────────────────────────────────────

    def test_empty_pool_returns_zeros(self, params, layout):
        """无消费者干员时所有维度 D 为 0"""
        ops = [_mock_op("c001", "阿米娅"), _mock_op("c002", "凯尔希")]
        ctx = SlotContext.from_layout(ops, layout, params)
        D = compute_consumer_D(ctx)
        assert set(D.keys()) == set(STATE_DIMS)
        assert all(v == 0.0 for v in D.values())

    def test_rosmontis_yields_perception_d(self, params, layout):
        """迷迭香在池 → D[perception] > 0"""
        ops = [_mock_op("c001", "迷迭香")]
        ctx = SlotContext.from_layout(ops, layout, params)
        D = compute_consumer_D(ctx)
        assert D["perception"] > 0.0
        # 迷迭香: Mfg CR/PG 平均 base_rate × hours × (1%/1) / 100 × unit_lmd
        expected = _MFG_AVG_BASE_LMD * 12.0 * 0.01
        assert D["perception"] == pytest.approx(expected, rel=1e-4)

    def test_shu_yields_yanhuo_d(self, params, layout):
        """黍在池 → D[yanhuo] > 0（bonus_per=1, per_unit=3）"""
        ops = [_mock_op("c002", "黍")]
        ctx = SlotContext.from_layout(ops, layout, params)
        D = compute_consumer_D(ctx)
        assert D["yanhuo"] > 0.0
        expected = _MFG_AVG_BASE_LMD * 12.0 * (1.0 / 3.0) / 100.0
        assert D["yanhuo"] == pytest.approx(expected, rel=1e-4)

    def test_crow_trade_yields_yanhuo_d(self, params, layout):
        """乌有在池 → D[yanhuo] > 0（Trade 消费者）"""
        ops = [_mock_op("c003", "乌有")]
        ctx = SlotContext.from_layout(ops, layout, params)
        D = compute_consumer_D(ctx)
        assert D["yanhuo"] > 0.0
        base_lmd_h = TRADE_BASE_LMD_PER_DAY / 24.0
        expected = base_lmd_h * 12.0 * (1.0 / 1.0) / 100.0
        assert D["yanhuo"] == pytest.approx(expected, rel=1e-4)

    def test_jieyun_wushu_crystal_conversion(self, params, layout):
        """截云 wushu_crystal → yanhuo 含 1/5 转换系数"""
        ops = [_mock_op("c004", "截云")]
        ctx = SlotContext.from_layout(ops, layout, params)
        D = compute_consumer_D(ctx)
        assert D["yanhuo"] > 0.0
        # wushu_crystal: bonus_per=2, per_unit=1, conv=1/5
        expected = _MFG_AVG_BASE_LMD * 12.0 * (2.0 / 1.0) * (1.0 / 5.0) / 100.0
        assert D["yanhuo"] == pytest.approx(expected, rel=1e-4)

    def test_to_simple_yields_engineering_d(self, params, layout):
        """至简 → D[engineering_robots] > 0"""
        ops = [_mock_op("c005", "至简")]
        ctx = SlotContext.from_layout(ops, layout, params)
        D = compute_consumer_D(ctx)
        assert D["engineering_robots"] > 0.0
        expected = _MFG_AVG_BASE_LMD * 12.0 * (5.0 / 8.0) / 100.0
        assert D["engineering_robots"] == pytest.approx(expected, rel=1e-4)

    def test_accumulates_multiple_dimensions(self, params, layout):
        """多个消费者各自累加到对应维度（不同维度互不干扰）"""
        ops = [
            _mock_op("c001", "迷迭香"),
            _mock_op("c006", "黑键"),
        ]
        ctx = SlotContext.from_layout(ops, layout, params)
        D = compute_consumer_D(ctx)
        # 迷迭香 → perception, 黑键 → silent_resonance
        ros_expected = _MFG_AVG_BASE_LMD * 12.0 * 0.01
        base_lmd_h = TRADE_BASE_LMD_PER_DAY / 24.0
        key_expected = base_lmd_h * 12.0 * (1.0 / 2.0) / 100.0
        assert D["perception"] == pytest.approx(ros_expected, rel=1e-4)
        assert D["silent_resonance"] == pytest.approx(key_expected, rel=1e-4)
        # 没消费者参与的维度保持 0
        assert D["yanhuo"] == 0.0

    def test_shu_sangwine_both_yanhuo_accumulates(self, params, layout):
        """同维度两个消费者（黍+桑葚）→ D[yanhuo] 累加"""
        ops = [
            _mock_op("c002", "黍"),
            _mock_op("c007", "桑葚"),
        ]
        ctx = SlotContext.from_layout(ops, layout, params)
        D = compute_consumer_D(ctx)
        per_consumer = _MFG_AVG_BASE_LMD * 12.0 * (1.0 / 3.0) / 100.0
        assert D["yanhuo"] == pytest.approx(per_consumer * 2, rel=1e-4)

    def test_multiple_dimensions_accumulate_independently(self, params, layout):
        """多维度消费者各自累加"""
        ops = [
            _mock_op("c001", "迷迭香"),
            _mock_op("c002", "黍"),
        ]
        ctx = SlotContext.from_layout(ops, layout, params)
        D = compute_consumer_D(ctx)
        assert D["perception"] > 0.0
        assert D["yanhuo"] > 0.0
        # 其他维度仍未 0
        assert D["engineering_robots"] == 0.0
        assert D["monster_cuisine"] == 0.0
