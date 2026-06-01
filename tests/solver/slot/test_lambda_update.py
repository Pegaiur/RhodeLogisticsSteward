"""_update_lambda_shadow 单元测试（改动 A：delta 模型 + 改动 B：比例缩放）

验证从 shift-based pool 模型迁移到 mood-delta 比例缩放后的全部行为：
1. 心情净消耗 → lambda 按比例收紧
2. 心情净恢复 → lambda 按比例释放
3. 心情稳态 → lambda 不动
4. 冷启动（old_lambda=0）→ 按消耗比例起步
5. lambda_cap 上限裁剪
6. 短/长班次比例自适配
7. 阻尼因子 scaling
8. 无 mood 数据时的 pool 回退
"""

import pytest

from steward_core.models import LayoutConfig, Operator
from steward_core.mood_flow import MoodContext
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext
from steward_core.solver.slot.solver import _update_lambda_shadow
from tests.helpers import mk_op, mk_simple_skill


def _make_test_ops(count: int = 3) -> list[Operator]:
    """构造测试用 Mfg 干员池"""
    ops = []
    for i in range(count):
        ops.append(mk_op(f"测试干员{i}", [
            mk_simple_skill("Mfg", 30.0, f"mfg_{i}"),
        ]))
    return ops


def _make_ctx(ops: list[Operator], params: SolverParams | None = None) -> SlotContext:
    if params is None:
        params = SolverParams()
    return SlotContext.from_layout(ops, LayoutConfig.layout_243(), params)


def _make_mood_ctx(ops: list[Operator], moods: dict[str, float],
                   params: SolverParams | None = None) -> MoodContext:
    if params is None:
        params = SolverParams()
    mc = MoodContext.fresh(ops, params)
    object.__setattr__(mc, "operator_moods", moods)
    return mc


class TestUpdateLambdaShadowDelta:
    """改动 A+B：净心情 delta 驱动比例缩放 lambda 更新"""

    @pytest.fixture
    def ops(self):
        return _make_test_ops(3)

    @pytest.fixture
    def params(self):
        return SolverParams(mood_full=24.0, backpressure_damping=1.0, lambda_jump_ratio=0.25)

    @pytest.fixture
    def ctx(self, ops, params):
        return _make_ctx(ops, params)

    # ==================== 正常路径 ====================

    def test_delta_negative_full_depletion(self, ops, params, ctx):
        """心情从 24 消耗至 0 → 节制率 1.0 → 乘子 2.0 → lambda 翻倍（damping=1.0）"""
        mood_start = {"测试干员0": 24.0, "测试干员1": 24.0, "测试干员2": 24.0}
        mood_end = {"测试干员0": 0.0, "测试干员1": 24.0, "测试干员2": 24.0}
        mc = _make_mood_ctx(ops, mood_end, params)

        ctx.lambda_ops["测试干员0"] = 100.0

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        # delta = 0-24 = -24, ratio = 24/24 = 1.0
        # multiplier = 1.0 + 1.0 * 1.0 = 2.0
        # new_lambda = 100 * 2.0 = 200
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(200.0)

    def test_delta_negative_partial_depletion(self, ops, params, ctx):
        """心情从 24 消耗至 12 → 节制率 0.5 → 乘子 1.5（damping=1.0）"""
        mood_start = {"测试干员0": 24.0}
        mood_end = {"测试干员0": 12.0}
        mc = _make_mood_ctx(ops, mood_end, params)

        ctx.lambda_ops["测试干员0"] = 100.0

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        # delta = 12-24 = -12, ratio = 12/24 = 0.5
        # multiplier = 1.0 + 1.0 * 0.5 = 1.5
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(150.0)

    def test_delta_positive_recovery(self, ops, params, ctx):
        """心情从 12 恢复至 24 → 恢复率 0.5 → 除数 1.5（damping=1.0）"""
        mood_start = {"测试干员0": 12.0}
        mood_end = {"测试干员0": 24.0}
        mc = _make_mood_ctx(ops, mood_end, params)

        ctx.lambda_ops["测试干员0"] = 150.0

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        # delta = 24-12 = +12, ratio = 12/24 = 0.5
        # divisor = 1.0 + 1.0 * 0.5 = 1.5
        # new_lambda = 150 / 1.5 = 100
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(100.0)

    def test_delta_zero_steady_state(self, ops, params, ctx):
        """心情不变（delta ≈ 0）→ lambda 不调整"""
        mood_start = {"测试干员0": 24.0}
        mood_end = {"测试干员0": 24.0}
        mc = _make_mood_ctx(ops, mood_end, params)

        ctx.lambda_ops["测试干员0"] = 100.0

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        # delta = 0, steady → no change
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(100.0)

    def test_delta_near_zero_epsilon(self, ops, params, ctx):
        """极小 delta（0.005）应视作稳态不调整"""
        mood_start = {"测试干员0": 24.0}
        mood_end = {"测试干员0": 23.995}
        mc = _make_mood_ctx(ops, mood_end, params)

        ctx.lambda_ops["测试干员0"] = 100.0

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        assert ctx.lambda_ops["测试干员0"] == pytest.approx(100.0)

    def test_delta_slightly_below_zero(self, ops, params, ctx):
        """小幅消耗（-0.5）→ 节制率 0.5/24 ≈ 0.0208 → 乘子 ≈ 1.02"""
        mood_start = {"测试干员0": 24.0}
        mood_end = {"测试干员0": 23.5}
        mc = _make_mood_ctx(ops, mood_end, params)

        ctx.lambda_ops["测试干员0"] = 100.0

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        # delta = -0.5, ratio = 0.0208, multiplier = 1.0208
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(102.083, rel=0.01)

    def test_delta_slightly_above_zero(self, ops, params, ctx):
        """小幅恢复（+0.5）→ 恢复率 0.0208 → 除数 ≈ 1.02"""
        mood_start = {"测试干员0": 23.5}
        mood_end = {"测试干员0": 24.0}
        mc = _make_mood_ctx(ops, mood_end, params)

        ctx.lambda_ops["测试干员0"] = 102.083

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        assert ctx.lambda_ops["测试干员0"] == pytest.approx(100.0, rel=0.02)

    # ==================== 冷启动 ====================

    def test_cold_start_first_penalty(self, ops, params, ctx):
        """首次超支（old_lambda=0）→ 按比例起步"""
        mood_start = {"测试干员0": 24.0}
        mood_end = {"测试干员0": 0.0}
        mc = _make_mood_ctx(ops, mood_end, params)

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        # delta = -24, ratio = 1.0. damping = 1.0
        # hourly_value = (1/3) * (1000/1.3) ≈ 256.41
        # jump = 0.25
        # new_lambda = 256.41 * 0.25 * (1.0 + 1.0 * 1.0) = 256.41 * 0.25 * 2.0
        expected = (1.0 / 3.0) * (1000.0 / 1.3) * 0.25 * 2.0
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(expected)

    def test_cold_start_partial_depletion(self, ops, params, ctx):
        """首次部分超支（delta=-12）→ 温和起步"""
        mood_start = {"测试干员0": 24.0}
        mood_end = {"测试干员0": 12.0}
        mc = _make_mood_ctx(ops, mood_end, params)

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        # ratio = 0.5, multiplier = 1.5
        expected = (1.0 / 3.0) * (1000.0 / 1.3) * 0.25 * 1.5
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(expected)

    # ==================== 上限裁剪 ====================

    def test_lambda_cap(self, ops, params, ctx):
        """超大消耗应裁剪至 lambda_cap"""
        mood_start = {"测试干员0": 24.0}
        mood_end = {"测试干员0": -100.0}
        mc = _make_mood_ctx(ops, mood_end, params)

        ctx.lambda_ops["测试干员0"] = 5000.0

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        hourly_value = (1.0 / 3.0) * (1000.0 / 1.3)
        cap = hourly_value * 10.0
        assert ctx.lambda_ops["测试干员0"] <= cap

    # ==================== 时长自适配 ====================

    def test_short_shift_proportional(self, ops, params, ctx):
        """4h 班次 delta=-8 → 节制率 0.333 → 乘子 1.333（damping=1.0）"""
        mood_start = {"测试干员0": 24.0}
        mood_end = {"测试干员0": 16.0}
        mc = _make_mood_ctx(ops, mood_end, params)

        ctx.lambda_ops["测试干员0"] = 100.0

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        # delta = 16-24 = -8, ratio = 8/24 = 1/3
        # multiplier = 1.0 + 1.0 * 1/3 = 1.333
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(133.33, rel=0.1)

    def test_long_shift_proportional(self, ops, params, ctx):
        """12h 班次 delta=-24 → 节制率 1.0 → 乘子 2.0（damping=1.0）"""
        mood_start = {"测试干员0": 24.0}
        mood_end = {"测试干员0": 0.0}
        mc = _make_mood_ctx(ops, mood_end, params)

        ctx.lambda_ops["测试干员0"] = 100.0

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        assert ctx.lambda_ops["测试干员0"] == pytest.approx(200.0)

    def test_same_total_different_windows(self, ops, params, ctx):
        """相同总 mood 消耗 → 相同乘子（2×8h 与 1×16h 消耗相同）"""
        mood_start = {"测试干员0": 24.0}
        # 模拟 16h 总消耗: delta = -16
        mood_end = {"测试干员0": 8.0}
        mc = _make_mood_ctx(ops, mood_end, params)

        ctx.lambda_ops["测试干员0"] = 100.0

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        # delta = 8-24 = -16, ratio = 16/24 = 2/3
        expected = 100.0 * (1.0 + 2.0 / 3.0)
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(expected)

    # ==================== 阻尼因子 ====================

    def test_damping_half(self, ops, ctx):
        """damping=0.5 → 节制率 1.0 → 乘子 = 1.0 + 0.5*1.0 = 1.5（半速）"""
        p = SolverParams(mood_full=24.0, backpressure_damping=0.5, lambda_jump_ratio=0.25)
        mood_start = {"测试干员0": 24.0}
        mood_end = {"测试干员0": 0.0}
        mc = _make_mood_ctx(ops, mood_end, p)

        ctx.lambda_ops["测试干员0"] = 100.0

        _update_lambda_shadow(ctx, ops, p,
                              mood_start=mood_start, mood_ctx=mc)

        # delta = -24, ratio = 1.0, damping = 0.5
        # multiplier = 1.0 + 0.5 * 1.0 = 1.5
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(150.0)

    def test_damping_zero_no_change(self, ops, ctx):
        """damping=0 → lambda 不调整（阻尼完全关闭）"""
        p = SolverParams(mood_full=24.0, backpressure_damping=0.0, lambda_jump_ratio=0.25)
        mood_start = {"测试干员0": 24.0}
        mood_end = {"测试干员0": 0.0}
        mc = _make_mood_ctx(ops, mood_end, p)

        ctx.lambda_ops["测试干员0"] = 100.0

        _update_lambda_shadow(ctx, ops, p,
                              mood_start=mood_start, mood_ctx=mc)

        assert ctx.lambda_ops["测试干员0"] == pytest.approx(100.0)

    def test_damping_full_doubles(self, ops, ctx):
        """damping=1.0 → 节制率 1.0 → 乘子 = 2.0（与原 ×2 行为兼容）"""
        p = SolverParams(mood_full=24.0, backpressure_damping=1.0, lambda_jump_ratio=0.25)
        mood_start = {"测试干员0": 24.0}
        mood_end = {"测试干员0": 0.0}
        mc = _make_mood_ctx(ops, mood_end, p)

        ctx.lambda_ops["测试干员0"] = 100.0

        _update_lambda_shadow(ctx, ops, p,
                              mood_start=mood_start, mood_ctx=mc)

        assert ctx.lambda_ops["测试干员0"] == pytest.approx(200.0)

    # ==================== 多干员 ====================

    def test_multiple_operators_independent(self, ops, params, ctx):
        """多名干员各自独立更新（delta 不同则乘子不同）"""
        mood_start = {"测试干员0": 24.0, "测试干员1": 24.0, "测试干员2": 24.0}
        mood_end = {"测试干员0": 4.0, "测试干员1": 24.0, "测试干员2": 0.0}
        mc = _make_mood_ctx(ops, mood_end, params)

        ctx.lambda_ops["测试干员0"] = 100.0
        ctx.lambda_ops["测试干员1"] = 50.0
        ctx.lambda_ops["测试干员2"] = 200.0

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        # 测试干员0: delta = 4-24 = -20, ratio = 20/24 = 0.833
        # multiplier = 1.833, new = 183.3
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(100.0 * 1.833, rel=0.1)

        # 测试干员1: delta = 24-24 = 0, steady → no change
        assert ctx.lambda_ops["测试干员1"] == pytest.approx(50.0)

        # 测试干员2: delta = 0-24 = -24, ratio = 1.0, multiplier = 2.0
        assert ctx.lambda_ops["测试干员2"] == pytest.approx(400.0)

    def test_returns_max_lambda(self, ops, params, ctx):
        """返回本轮最大 lambda 值"""
        mood_start = {"测试干员0": 24.0, "测试干员1": 24.0}
        mood_end = {"测试干员0": 0.0, "测试干员1": 12.0}
        mc = _make_mood_ctx(ops, mood_end, params)

        ctx.lambda_ops["测试干员0"] = 100.0
        ctx.lambda_ops["测试干员1"] = 200.0

        result = _update_lambda_shadow(ctx, ops, params,
                                       mood_start=mood_start, mood_ctx=mc)

        # 测试干员0: 100 * 2.0 = 200
        # 测试干员1: 200 * 1.5 = 300
        assert result == pytest.approx(300.0)

    # ==================== 缺失干员（mood 快照中不存在） ====================

    def test_operator_not_in_mood_snapshot(self, ops, params, ctx):
        """mood_start 中不存在的干员 → 默认满心情 24.0"""
        mood_start = {"测试干员0": 24.0}
        mood_end = {"测试干员0": 12.0, "测试干员1": 24.0}
        mc = _make_mood_ctx(ops, mood_end, params)

        ctx.lambda_ops["测试干员1"] = 100.0

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=mc)

        # 测试干员1 不在 mood_start 中 → mood_start = mood_full = 24.0
        # delta = 24 - 24 = 0 → steady → no change
        assert ctx.lambda_ops["测试干员1"] == pytest.approx(100.0)

    # ==================== 回退到 pool 逻辑 ====================

    def test_fallback_pool_when_no_mood_data(self, ops, params, ctx):
        """mood_start 为 None 时回退到 pool 逻辑"""
        ctx.lambda_ops["测试干员0"] = 100.0

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=None, mood_ctx=None)

        # pool 逻辑：hours_used=0 → used=0 ≤ pool → lambda /= 2
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(50.0)

    def test_fallback_pool_with_mood_ctx_none(self, ops, params, ctx):
        """mood_ctx 为 None 时回退到 pool 逻辑"""
        ctx.lambda_ops["测试干员0"] = 100.0
        mood_start = {"测试干员0": 24.0}

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=mood_start, mood_ctx=None)

        # mood_ctx is None → fallback to pool logic
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(50.0)

    def test_fallback_pool_with_hours_used(self, ops, params, ctx):
        """pool 回退逻辑中 hours_used > pool → lambda *= 2"""
        ctx.hours_used["测试干员0"] = 100.0
        ctx.lambda_ops["测试干员0"] = 100.0

        _update_lambda_shadow(ctx, ops, params,
                              mood_start=None, mood_ctx=None)

        # hours_used=100 > pool(~24) → lambda *= 2
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(200.0)

    # ==================== 恢复侧对称性 ====================

    def test_roundtrip_symmetric(self, ops, ctx):
        """消耗+恢复一轮后 lambda 应回到原值（无阻尼时）"""
        p = SolverParams(mood_full=24.0, backpressure_damping=1.0, lambda_jump_ratio=0.25)

        # 第一轮：消耗
        mood_start_1 = {"测试干员0": 24.0}
        mood_end_1 = {"测试干员0": 12.0}
        mc_1 = _make_mood_ctx(ops, mood_end_1, p)

        ctx.lambda_ops["测试干员0"] = 100.0
        _update_lambda_shadow(ctx, ops, p,
                              mood_start=mood_start_1, mood_ctx=mc_1)

        # delta = -12, ratio = 0.5, multiplier = 1.5 → 150
        after_penalty = ctx.lambda_ops["测试干员0"]
        assert after_penalty == pytest.approx(150.0)

        # 第二轮：恢复
        mood_start_2 = {"测试干员0": 12.0}
        mood_end_2 = {"测试干员0": 24.0}
        mc_2 = _make_mood_ctx(ops, mood_end_2, p)

        _update_lambda_shadow(ctx, ops, p,
                              mood_start=mood_start_2, mood_ctx=mc_2)

        # delta = +12, ratio = 0.5, divisor = 1.5 → 150/1.5 = 100
        assert ctx.lambda_ops["测试干员0"] == pytest.approx(100.0)
