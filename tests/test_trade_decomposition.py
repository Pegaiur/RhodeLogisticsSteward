"""订单层机会成本分解测试（Phase B）

验证 _decompose_trade_order 对 Tailor→Law 稀释 / Tailor→Long 增益的数值正确性。
"""

import pytest

from steward_core.models import EfficiencyMap, Operator, Skill
from steward_core.production import (
    _decompose_trade_order,
    _get_trade_order_multiplier,
    _effective_tailor_p4,
)


def _mk_op(name: str, skills: list[Skill] | None = None) -> Operator:
    return Operator(char_id=name, name=name, skills=skills or [])


def _law_op(name: str = "但书") -> Operator:
    return _mk_op(name, [
        Skill(buff_id="trade_ord_law[000]", buff_name="合同法", skill_icon="test",
              room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        Skill(buff_id="trade_ord_against[010]", buff_name="违约索赔·β", skill_icon="test",
              room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
    ])


def _tequila_op(name: str = "龙舌兰") -> Operator:
    return _mk_op(name, [
        Skill(buff_id="trade_ord_long[010]", buff_name="投资·β", skill_icon="test",
              room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
    ])


def _tailor_alpha_op(name: str = "明椒") -> Operator:
    return _mk_op(name, [
        Skill(buff_id="trade_ord_wt&cost[000]", buff_name="裁缝·α", skill_icon="test",
              room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
    ])


def _tailor_beta_op(name: str = "柏喙") -> Operator:
    return _mk_op(name, [
        Skill(buff_id="trade_ord_wt&cost[010]", buff_name="裁缝·β", skill_icon="test",
              room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
    ])


class TestDecomposeBaseline:
    def test_无特殊机制_仅有_base(self):
        ops = [_mk_op("A")]
        result = _decompose_trade_order(ops, 24.0, False, 0, 0, 0.20)
        total_lmd = _get_trade_order_multiplier(ops)[0]
        assert total_lmd == pytest.approx(10265.0, rel=0.01)
        assert result["solo"]["base"] == pytest.approx(10265.0, rel=0.01)
        assert result["solo"]["law"] == 0.0
        assert result["solo"]["long"] == 0.0

    def test_但书_solo_贡献独立(self):
        ops = [_law_op()]
        result = _decompose_trade_order(ops, 24.0, False, 0, 0, 0.20)
        assert result["solo"]["law"] > 5000  # 但书显著提升 LMD
        assert result["solo"]["long"] == 0.0
        assert result["opportunity"]["tailor_to_law"] == 0.0

    def test_龙舌兰_solo_贡献独立(self):
        ops = [_tequila_op()]
        result = _decompose_trade_order(ops, 24.0, True, 500, 0, 0.20)
        assert result["solo"]["long"] > 0  # 龙舌兰有投资 bonus
        assert result["solo"]["law"] == 0.0


class TestTailorOpportunityCost:
    """裁缝 P4 偏移对但书和龙舌兰的边际效应"""

    def test_tailor_alpha_dilutes_law(self):
        """裁缝α(P4≈0.51) 降低但书操作空间 → 机会成本 > 0"""
        ops = [_law_op(), _tailor_alpha_op()]
        p4 = _effective_tailor_p4(24.0, 1)
        total = _get_trade_order_multiplier(ops)[0]
        result = _decompose_trade_order(ops, 24.0, False, 0, 1, p4)
        solo_sum = result["solo"]["base"] + result["solo"]["law"]
        opp = result["opportunity"]["tailor_to_law"]
        assert opp > 0, "裁缝对但书应产生正机会成本"
        assert solo_sum > total, "solo 总和应大于实际值（机会成本未扣）"
        assert solo_sum - opp == pytest.approx(total, rel=0.005)

    def test_tailor_beta_dilutes_law_more_than_alpha(self):
        """裁缝β(P4≈0.82) 比α更严重地削弱但书"""
        law = _law_op()
        p4_a = _effective_tailor_p4(24.0, 1)
        p4_b = _effective_tailor_p4(24.0, 2)
        alpha_result = _decompose_trade_order([law, _tailor_alpha_op()], 24.0, False, 0, 1, p4_a)
        beta_result = _decompose_trade_order([law, _tailor_beta_op()], 24.0, False, 0, 2, p4_b)
        assert beta_result["opportunity"]["tailor_to_law"] > alpha_result["opportunity"]["tailor_to_law"]

    def test_tailor_boosts_tequila(self):
        """裁缝β扩充龙舌兰触发池 → 机会成本为负（增益）"""
        ops = [_tequila_op(), _tailor_beta_op()]
        p4 = _effective_tailor_p4(24.0, 2)
        total = _get_trade_order_multiplier(ops)[0]
        result = _decompose_trade_order(ops, 24.0, True, 500, 2, p4)
        opp_long = result["opportunity"]["tailor_to_long"]
        assert opp_long > 0, "裁缝应对龙舌兰产生正增益"
        solo_sum = (
            result["solo"]["base"] + result["solo"]["long"]
        )
        assert solo_sum + opp_long == pytest.approx(total, rel=0.005)

    def test_no_tailor_zero_opportunity(self):
        """无裁缝时机会成本全为零"""
        ops = [_law_op()]
        result = _decompose_trade_order(ops, 24.0, False, 0, 0, 0.20)
        assert result["opportunity"]["tailor_to_law"] == 0.0
        assert result["opportunity"]["tailor_to_long"] == 0.0
