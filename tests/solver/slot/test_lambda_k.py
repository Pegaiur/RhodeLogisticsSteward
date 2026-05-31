"""λ_k 标量计算单元测试

验证 _compute_lambda_k 的三种行为：
1. 空分配 → 返回 0.0
2. Mfg/Trade 有分配 → 返回正标量（锚定到槽位边际 LMD 中位数）
3. 标量 λ_k 与 per-op λ_ops 独立（前者由槽位产值锚定，后者由 bisection 驱动）
"""

import pytest

from steward_core.models import EfficiencyMap, LayoutConfig, Operator, Skill
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext


def _mk_mfg_op(name: str, char_id: str, eff: float) -> Operator:
    return Operator(
        char_id=char_id, name=name,
        skills=[Skill(
            buff_id=f"test_mfg_{char_id}",
            buff_name="测试技能",
            skill_icon="test",
            room_type="Mfg",
            efficient=EfficiencyMap(raw={"all": eff}),
        )],
    )


def _mk_trade_op(name: str, char_id: str, eff: float) -> Operator:
    return Operator(
        char_id=char_id, name=name,
        skills=[Skill(
            buff_id=f"test_trade_{char_id}",
            buff_name="测试技能",
            skill_icon="test",
            room_type="Trade",
            efficient=EfficiencyMap(raw={"all": eff}),
        )],
    )


class TestComputeLambdaK:
    """_compute_lambda_k 单元测试"""

    @pytest.fixture
    def cr_ops(self):
        """3 名 Mfg CR 干员，各 50% 效率"""
        return [
            _mk_mfg_op("测试CR_A", "char_cr_a", 50.0),
            _mk_mfg_op("测试CR_B", "char_cr_b", 50.0),
            _mk_mfg_op("测试CR_C", "char_cr_c", 50.0),
        ]

    def test_empty_context_returns_zero(self):
        """无 Mfg/Trade 分配时应返回 0.0"""
        from steward_core.solver.slot.solver import _compute_lambda_k

        ctx = SlotContext.from_layout(
            [], LayoutConfig.layout_243(), SolverParams(),
        )
        result = _compute_lambda_k(ctx, 0, 12.0)
        assert result == 0.0, "空分配时 λ_k 应为 0"

    def test_single_mfg_room_positive(self, cr_ops):
        """单间 Mfg CR 分配后 λ_k 应为正数（锚定到该房间的 hourly LMD）"""
        from steward_core.solver.slot.solver import _compute_lambda_k

        ctx = SlotContext.from_layout(
            cr_ops, LayoutConfig.layout_243(), SolverParams(),
        )
        ctx.place(0, "mfg_0_0", "测试CR_A")
        ctx.place(0, "mfg_0_1", "测试CR_B")
        ctx.place(0, "mfg_0_2", "测试CR_C")

        result = _compute_lambda_k(ctx, 0, 12.0)
        assert result > 0.0, "有 Mfg 分配时 λ_k 应为正"
        assert result < 10000.0, f"λ_k 不应异常巨大: {result}"

    def test_single_trade_room_positive(self):
        """单间 Trade 分配后 λ_k 应为正数"""
        from steward_core.solver.slot.solver import _compute_lambda_k

        ops = [
            _mk_trade_op("测试Trade_A", "char_tr_a", 30.0),
            _mk_trade_op("测试Trade_B", "char_tr_b", 30.0),
            _mk_trade_op("测试Trade_C", "char_tr_c", 30.0),
        ]
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        ctx.place(0, "trade_0_0", "测试Trade_A")
        ctx.place(0, "trade_0_1", "测试Trade_B")
        ctx.place(0, "trade_0_2", "测试Trade_C")

        result = _compute_lambda_k(ctx, 0, 12.0)
        assert result > 0.0, "有 Trade 分配时 λ_k 应为正"
        assert result < 10000.0, f"λ_k 不应异常巨大: {result}"

    def test_median_of_multiple_rooms(self, cr_ops):
        """多房间时 λ_k 为中位数（两间 CR 不同效率 → 取均值）"""
        from steward_core.solver.slot.solver import _compute_lambda_k

        # 第二间：低效率干员
        low_ops = [
            _mk_mfg_op("测试CR_D", "char_cr_d", 20.0),
            _mk_mfg_op("测试CR_E", "char_cr_e", 20.0),
            _mk_mfg_op("测试CR_F", "char_cr_f", 20.0),
        ]
        all_ops = cr_ops + low_ops

        ctx = SlotContext.from_layout(
            all_ops, LayoutConfig.layout_243(), SolverParams(),
        )
        # 房间 0: 150% 总效率
        ctx.place(0, "mfg_0_0", "测试CR_A")
        ctx.place(0, "mfg_0_1", "测试CR_B")
        ctx.place(0, "mfg_0_2", "测试CR_C")
        # 房间 1: 60% 总效率
        ctx.place(0, "mfg_1_0", "测试CR_D")
        ctx.place(0, "mfg_1_1", "测试CR_E")
        ctx.place(0, "mfg_1_2", "测试CR_F")

        result = _compute_lambda_k(ctx, 0, 12.0)
        assert result > 0.0, "多房间时 λ_k 应为正"
        # 两间房的中位数 = 均值，应在两者之间
        assert 200.0 < result < 2000.0, f"λ_k 应在合理范围: {result}"

    def test_lambda_k_independent_of_per_op_lambda_ops(self, cr_ops):
        """λ_k 与 per-op λ_ops 独立——前者按槽位产值锚定，后者按 pool 约束 bisection"""
        from steward_core.solver.slot.solver import _compute_lambda_k

        ctx = SlotContext.from_layout(
            cr_ops, LayoutConfig.layout_243(), SolverParams(),
        )
        ctx.place(0, "mfg_0_0", "测试CR_A")
        ctx.place(0, "mfg_0_1", "测试CR_B")
        ctx.place(0, "mfg_0_2", "测试CR_C")

        # 设置 per-op λ（模拟 bisection 惩罚值）
        ctx.lambda_ops["测试CR_A"] = 9999.0
        ctx.lambda_ops["测试CR_B"] = 9999.0

        result = _compute_lambda_k(ctx, 0, 12.0)
        # λ_k 由槽位产值决定，不受 per-op λ_ops 影响
        assert result > 0.0, "λ_k 应与 per-op λ_ops 独立"
        assert result < 5000.0, f"λ_k 不应被 per-op λ_ops 污染: {result}"

    def test_mfg_and_trade_mixed_median(self):
        """Mfg 和 Trade 混合时 λ_k 取全量槽位的中位数（不区分设施类型）"""
        from steward_core.solver.slot.solver import _compute_lambda_k

        mfg_ops = [
            _mk_mfg_op("测试CR_G", "char_cr_g", 50.0),
            _mk_mfg_op("测试CR_H", "char_cr_h", 50.0),
            _mk_mfg_op("测试CR_I", "char_cr_i", 50.0),
        ]
        trade_ops = [
            _mk_trade_op("测试Trade_D", "char_tr_d", 30.0),
            _mk_trade_op("测试Trade_E", "char_tr_e", 30.0),
            _mk_trade_op("测试Trade_F", "char_tr_f", 30.0),
        ]
        all_ops = mfg_ops + trade_ops

        ctx = SlotContext.from_layout(
            all_ops, LayoutConfig.layout_243(), SolverParams(),
        )
        ctx.place(0, "mfg_0_0", "测试CR_G")
        ctx.place(0, "mfg_0_1", "测试CR_H")
        ctx.place(0, "mfg_0_2", "测试CR_I")
        ctx.place(0, "trade_0_0", "测试Trade_D")
        ctx.place(0, "trade_0_1", "测试Trade_E")
        ctx.place(0, "trade_0_2", "测试Trade_F")

        result = _compute_lambda_k(ctx, 0, 12.0)
        assert result > 0.0, "Mfg+Trade 混合时 λ_k 应为正"
        assert 200.0 < result < 2000.0, f"λ_k 应在合理范围: {result}"
