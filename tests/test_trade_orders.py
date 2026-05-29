"""贸易站订单机制测试模块

全部测试通过内存构造 Operator，验证 _get_trade_order_multiplier() 的订单倍数与等效产金。
遵循 TDD 3A 模式 (Arrange → Act → Assert)。
"""

import pytest

from steward_core.models import EfficiencyMap, Operator, Skill
from steward_core.production import DailyProduction, _get_trade_order_multiplier


def _mk_op(name: str, skills: list[Skill] | None = None) -> Operator:
    """构造测试用干员 (纯内存)"""
    return Operator(char_id=name, name=name, skills=skills or [])


def _mk_skill(room_type: str, efficient: dict[str, float], buff_id: str = "test_buff") -> Skill:
    """构造测试用技能 (纯内存)"""
    return Skill(
        buff_id=buff_id,
        buff_name="测试技能",
        skill_icon=f"test_{buff_id}",
        room_type=room_type,
        efficient=EfficiencyMap(raw=efficient),
    )


# ─── 贸易站订单机制（A7 层）─ 文档倍数法 ────────────────────────

# 文档基准：Lv3 贸易站 100% 效率 24h = 10265 LMD/天
_TRADE_BASE_LMD_PER_DAY = 10265.0


class TestTradeOrderMultiplier:
    """验证 _get_trade_order_multiplier() 返回正确的 (lmd_per_day, gold_per_day)"""

    def test_空干员列表_返回默认倍数(self):
        """无特殊干员 → (10265, 标准赤金消耗)"""
        # Act
        lmd_per_day, gold_per_day, _ = _get_trade_order_multiplier([])

        # Assert: 默认三级站日产
        assert lmd_per_day == 10265.0
        assert gold_per_day == pytest.approx(24 * 2.9 / 3.39, rel=0.01)

    def test_普通贸易干员_返回默认倍数(self):
        """仅有 Money=30 的普通贸易干员 → 默认倍数"""
        # Arrange
        op = _mk_op("商人", [_mk_skill("Trade", {"Money": 30})])

        # Act
        lmd_per_day, gold_per_day, _ = _get_trade_order_multiplier([op])

        # Assert
        assert lmd_per_day == 10265.0
        assert gold_per_day == pytest.approx(24 * 2.9 / 3.39, rel=0.01)

    def test_但书单干员_违约体系倍数(self):
        """但书合同法+违约索赔β → LMD 1.55×, 赤金消耗 4.9/2.9×"""
        # Arrange: 但书 buff_ids
        butler = _mk_op("但书", [
            Skill(buff_id="trade_ord_law[000]", buff_name="合同法", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
            Skill(buff_id="trade_ord_against[010]", buff_name="违约索赔·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        # Act
        lmd_per_day, gold_per_day, _ = _get_trade_order_multiplier([butler])

        # Assert: 2,3→违约+2, LMD=2250/订单; gold=4.9/订单
        expected_lmd_mult = 2250.0 / 1450.0  # 1.5517
        expected_gold_mult = 4.9 / 2.9  # 1.6897
        assert lmd_per_day == pytest.approx(10265 * expected_lmd_mult, rel=0.001)
        assert gold_per_day == pytest.approx(24 * 2.9 / 3.39 * expected_gold_mult, rel=0.001)

    def test_可露希尔_特别订单倍数(self):
        """可露希尔特别订单 → 固定 2赤金/1200LMD, 10单/天"""
        # Arrange
        closure = _mk_op("可露希尔", [
            Skill(buff_id="trade_ord_closure[000]", buff_name="特别订单", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 10})),
        ])

        # Act
        lmd_per_day, gold_per_day, _ = _get_trade_order_multiplier([closure])

        # Assert: 12000 LMD/天 (文档), 20 赤金消耗/天
        assert lmd_per_day == pytest.approx(12000.0, rel=0.01)
        assert gold_per_day == pytest.approx(24 / 2.4 * 2.0, rel=0.01)  # 20

    def test_龙舌兰加裁缝beta_高品质投资倍数(self):
        """龙舌兰投资β + 裁缝β → LMD 约12669，文档基准12740"""
        # Arrange
        tequila = _mk_op("龙舌兰", [
            Skill(buff_id="trade_ord_long[010]", buff_name="投资·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])
        tailor = _mk_op("柏喙", [
            Skill(buff_id="trade_ord_wt&cost[010]", buff_name="裁缝·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        # Act
        lmd_per_day, gold_per_day, _ = _get_trade_order_multiplier([tequila, tailor])

        # Assert: 24h 等效 P4≈0.816，加权平均订单耗时~4.32h
        assert lmd_per_day == pytest.approx(12669.2, rel=0.01)
        assert gold_per_day == pytest.approx(20.82, rel=0.01)

    def test_但书加龙舌兰_互动倍数(self):
        """但书+龙舌兰 → 2,3触发但书, 4触发龙舌兰"""
        # Arrange
        butler = _mk_op("但书", [
            Skill(buff_id="trade_ord_law[000]", buff_name="合同法", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
            Skill(buff_id="trade_ord_against[010]", buff_name="违约索赔·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])
        tequila = _mk_op("龙舌兰", [
            Skill(buff_id="trade_ord_long[010]", buff_name="投资·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        # Act
        lmd_per_day, gold_per_day, _ = _get_trade_order_multiplier([butler, tequila])

        # Assert: LMD=2350/订单(文档~16637), gold=4.5/订单
        expected_lmd_mult = 2350.0 / 1450.0
        expected_gold_mult = 4.5 / 2.9
        assert lmd_per_day == pytest.approx(10265 * expected_lmd_mult, rel=0.002)
        assert gold_per_day == pytest.approx(24 * 2.9 / 3.39 * expected_gold_mult, rel=0.002)

    def test_裁缝alpha_高品质小幅倍数(self):
        """裁缝·α 单独 → 24h等效P4≈0.509，加权平均耗时~3.86h"""
        # Arrange
        tailor_a = _mk_op("明椒", [
            Skill(buff_id="trade_ord_wt&cost[000]", buff_name="裁缝·α", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        # Act
        lmd_per_day, gold_per_day, _ = _get_trade_order_multiplier([tailor_a])

        # Assert: 时变模型 + 加权时间修正
        assert lmd_per_day == pytest.approx(10343.5, rel=0.002)
        assert gold_per_day == pytest.approx(20.69, rel=0.002)

    # ─── 可露希尔优先级与互斥 ──────────────────────────────

    def test_可露希尔加但书_但书机制失效(self):
        """可露希尔特别订单最高优先级，但书违约机制不生效"""
        closure = _mk_op("可露希尔", [
            Skill(buff_id="trade_ord_closure[000]", buff_name="特别订单", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 10})),
        ])
        butler = _mk_op("但书", [
            Skill(buff_id="trade_ord_law[000]", buff_name="合同法", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
            Skill(buff_id="trade_ord_against[010]", buff_name="违约索赔·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        lmd_per_day, gold_per_day, _ = _get_trade_order_multiplier([closure, butler])

        # 应与纯 可露希尔 相同（但书机制被覆盖）
        assert lmd_per_day == pytest.approx(12000.0, rel=0.01)
        assert gold_per_day == pytest.approx(20.0, rel=0.01)

    def test_可露希尔加龙舌兰_投资机制失效(self):
        """可露希尔特别订单下，龙舌兰投资不触发"""
        closure = _mk_op("可露希尔", [
            Skill(buff_id="trade_ord_closure[000]", buff_name="特别订单", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 10})),
        ])
        tequila = _mk_op("龙舌兰", [
            Skill(buff_id="trade_ord_long[010]", buff_name="投资·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        lmd_per_day, gold_per_day, _ = _get_trade_order_multiplier([closure, tequila])

        assert lmd_per_day == pytest.approx(12000.0, rel=0.01)
        assert gold_per_day == pytest.approx(20.0, rel=0.01)

    def test_可露希尔加裁缝_裁缝机制失效(self):
        """可露希尔特别订单下，裁缝P4品质不触发"""
        closure = _mk_op("可露希尔", [
            Skill(buff_id="trade_ord_closure[000]", buff_name="特别订单", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 10})),
        ])
        tailor = _mk_op("柏喙", [
            Skill(buff_id="trade_ord_wt&cost[010]", buff_name="裁缝·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        lmd_per_day, gold_per_day, _ = _get_trade_order_multiplier([closure, tailor])

        assert lmd_per_day == pytest.approx(12000.0, rel=0.01)
        assert gold_per_day == pytest.approx(20.0, rel=0.01)

    def test_可露希尔加但书加龙舌兰_全部被覆盖(self):
        """可露希尔+但书+龙舌兰 → 仅可露希尔机制生效"""
        closure = _mk_op("可露希尔", [
            Skill(buff_id="trade_ord_closure[000]", buff_name="特别订单", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 10})),
        ])
        butler = _mk_op("但书", [
            Skill(buff_id="trade_ord_law[000]", buff_name="合同法", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])
        tequila = _mk_op("龙舌兰", [
            Skill(buff_id="trade_ord_long[010]", buff_name="投资·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        lmd_per_day, gold_per_day, _ = _get_trade_order_multiplier([closure, butler, tequila])

        assert lmd_per_day == pytest.approx(12000.0, rel=0.01)
        assert gold_per_day == pytest.approx(20.0, rel=0.01)


# ─── 订单机制等效产金 ────────────────────────────────────────

class TestTradeEquivalentGold:
    """验证 _get_trade_order_multiplier 的等效赤金产出"""

    def test_无机制_等效产金为零(self):
        """普通贸易干员 → 等效赤金 = 0"""
        op = _mk_op("商人", [_mk_skill("Trade", {"Money": 30})])
        _, _, equiv_gold = _get_trade_order_multiplier([op])
        assert equiv_gold == 0.0

    def test_但书_等效产金为零(self):
        """但书以金换金 → 等效赤金 = 0"""
        butler = _mk_op("但书", [
            Skill(buff_id="trade_ord_law[000]", buff_name="合同法", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
            Skill(buff_id="trade_ord_against[010]", buff_name="违约索赔·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])
        _, _, equiv_gold = _get_trade_order_multiplier([butler])
        assert equiv_gold == 0.0

    def test_可露希尔_等效产金约4每天(self):
        """可露希尔 特别订单 → 等效赤金 ~4/天"""
        closure = _mk_op("可露希尔", [
            Skill(buff_id="trade_ord_closure[000]", buff_name="特别订单", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 10})),
        ])
        _, _, equiv_gold = _get_trade_order_multiplier([closure])
        assert equiv_gold == pytest.approx(4.0, rel=0.01)

    def test_龙舌兰加裁缝beta_等效产金(self):
        """龙舌兰+裁缝β → 等效赤金 = 4赤金订单×1赤金/单"""
        tequila = _mk_op("龙舌兰", [
            Skill(buff_id="trade_ord_long[010]", buff_name="投资·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])
        tailor = _mk_op("柏喙", [
            Skill(buff_id="trade_ord_wt&cost[010]", buff_name="裁缝·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])
        _, _, equiv_gold = _get_trade_order_multiplier([tequila, tailor])
        assert equiv_gold > 0
        assert equiv_gold == pytest.approx(4.53, rel=0.05)

    def test_DailyProduction_含等效产金字段(self):
        """DailyProduction 应有 equivalent_gold_from_mechanism 字段"""
        dp = DailyProduction()
        assert hasattr(dp, 'equivalent_gold_from_mechanism')
        assert dp.equivalent_gold_from_mechanism == 0.0

    def test_等效产金不影响物理盈余(self):
        """gold_surplus 保持物理语义，不受等效产金影响"""
        dp = DailyProduction(
            total_gold_produced_per_day=50.0,
            total_gold_consumed_per_day=40.0,
            gold_surplus=10.0,  # 传入值直接设置
        )
        assert dp.gold_surplus == 10.0
        dp.equivalent_gold_from_mechanism = 5.0
        assert dp.gold_surplus == 10.0  # 不因等效产金改变
