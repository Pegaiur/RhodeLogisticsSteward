"""机会成本模块单元测试

覆盖 compute_opportunity_cost_lmd 对 whisper / automation / zeroing_variant
三类归零机制的公式正确性 + 换算常量一致性验证。
"""

from unittest.mock import patch

from steward_core.models import Operator
from steward_core.solver.slot.opportunity import compute_opportunity_cost_lmd


def _mk_op(name: str, char_id: str, buff_ids: list[str] | None = None) -> Operator:
    from steward_core.models import Skill
    skills = []
    if buff_ids:
        for bid in buff_ids:
            skills.append(Skill(
                buff_id=bid, buff_name="", skill_icon="",
                room_type=_room_for(bid), efficient=None,
            ))
    return Operator(name=name, char_id=char_id, skills=skills, rarity=5)


def _room_for(buff_id: str) -> str:
    if buff_id.startswith("trade_"):
        return "Trade"
    return "Mfg"


_EFF_MAP: dict[str, float] = {}


def _fake_estimated_efficiency(op, room_type, product=None, T=12.0):
    return _EFF_MAP.get(op.name, 0.0)


class TestNoZeroing:
    def test_plain_combo_returns_zero(self):
        ops = [_mk_op("A", "a"), _mk_op("B", "b"), _mk_op("C", "c")]
        assert compute_opportunity_cost_lmd(ops, "Trade", "Money", 12.0) == 0.0

    def test_plain_mfg_returns_zero(self):
        ops = [_mk_op("A", "a"), _mk_op("B", "b"), _mk_op("C", "c")]
        assert compute_opportunity_cost_lmd(ops, "Mfg", "CombatRecord", 12.0) == 0.0


class TestWhisperFormula:
    """whisper 公式数值验证"""

    @patch("steward_core.solver.slot.opportunity.operator_estimated_efficiency", _fake_estimated_efficiency)
    def test_low_eff_below_45_no_cost(self):
        _EFF_MAP.clear()
        _EFF_MAP["A"] = 30.0
        _EFF_MAP["B"] = 25.0
        shamare = _mk_op("巫恋", "char_254_vodfox", ["trade_ord_vodfox[000]"])
        ops = [shamare, _mk_op("A", "a"), _mk_op("B", "b")]
        assert compute_opportunity_cost_lmd(ops, "Trade", "Money", 12.0) == 0.0

    @patch("steward_core.solver.slot.opportunity.operator_estimated_efficiency", _fake_estimated_efficiency)
    def test_high_eff_above_45_has_cost(self):
        _EFF_MAP.clear()
        _EFF_MAP["A"] = 75.0
        _EFF_MAP["B"] = 60.0
        shamare = _mk_op("巫恋", "char_254_vodfox", ["trade_ord_vodfox[000]"])
        ops = [shamare, _mk_op("A", "a"), _mk_op("B", "b")]
        cost = compute_opportunity_cost_lmd(ops, "Trade", "Money", 12.0)
        expected_pct = (75.0 - 45.0) + (60.0 - 45.0)
        expected_lmd = expected_pct * (10265.0 / 24.0) * 12.0 / 100.0
        assert abs(cost - expected_lmd) < 0.01
        assert cost > 0.0

    @patch("steward_core.solver.slot.opportunity.operator_estimated_efficiency", _fake_estimated_efficiency)
    def test_exactly_45_no_cost(self):
        _EFF_MAP.clear()
        _EFF_MAP["A"] = 45.0
        shamare = _mk_op("巫恋", "char_254_vodfox", ["trade_ord_vodfox[000]"])
        ops = [shamare, _mk_op("A", "a"), _mk_op("B", "b")]
        assert compute_opportunity_cost_lmd(ops, "Trade", "Money", 12.0) == 0.0

    @patch("steward_core.solver.slot.opportunity.operator_estimated_efficiency", _fake_estimated_efficiency)
    def test_mfg_whisper_still_zero(self):
        _EFF_MAP.clear()
        _EFF_MAP["A"] = 75.0
        shamare = _mk_op("巫恋", "char_254_vodfox", ["trade_ord_vodfox[000]"])
        ops = [shamare, _mk_op("A", "a"), _mk_op("B", "b")]
        assert compute_opportunity_cost_lmd(ops, "Mfg", "CombatRecord", 12.0) == 0.0


class TestAutomationFormula:
    """automation 公式数值验证（全额扣减，无 sensitivity）"""

    @patch("steward_core.solver.slot.opportunity.operator_estimated_efficiency", _fake_estimated_efficiency)
    def test_basic_cost_full(self):
        _EFF_MAP.clear()
        _EFF_MAP["A"] = 30.0
        _EFF_MAP["B"] = 20.0
        saria = _mk_op("森蚺", "saria", ["manu_prod_spd&power[000]"])
        ops = [saria, _mk_op("A", "a"), _mk_op("B", "b")]
        cost = compute_opportunity_cost_lmd(ops, "Mfg", "CombatRecord", 12.0)
        expected_pct = 30.0 + 20.0
        expected_lmd = expected_pct * (1.0 / 3.0) * (1000.0 / 1.3) * 12.0 / 100.0
        assert abs(cost - expected_lmd) < 0.01
        assert cost > 0.0

    @patch("steward_core.solver.slot.opportunity.operator_estimated_efficiency", _fake_estimated_efficiency)
    def test_fallback_name_detection(self):
        _EFF_MAP.clear()
        _EFF_MAP["A"] = 25.0
        wenti = _mk_op("温蒂", "wenti", [])
        ops = [wenti, _mk_op("A", "a"), _mk_op("B", "b")]
        cost = compute_opportunity_cost_lmd(ops, "Mfg", "PureGold", 12.0)
        expected_pct = 25.0
        expected_lmd = expected_pct * (1.0 / 1.2) * 500.0 * 12.0 / 100.0
        assert abs(cost - expected_lmd) < 0.01
        assert cost > 0.0

    @patch("steward_core.solver.slot.opportunity.operator_estimated_efficiency", _fake_estimated_efficiency)
    def test_trade_ignored(self):
        _EFF_MAP.clear()
        _EFF_MAP["A"] = 50.0
        saria = _mk_op("森蚺", "saria", ["manu_prod_spd&power[000]"])
        ops = [saria, _mk_op("A", "a"), _mk_op("B", "b")]
        assert compute_opportunity_cost_lmd(ops, "Trade", "Money", 12.0) == 0.0


class TestZeroingVariantFormula:
    """归零变体公式数值验证（全额扣减）"""

    @patch("steward_core.solver.slot.opportunity.operator_estimated_efficiency", _fake_estimated_efficiency)
    def test_basic_cost_full(self):
        _EFF_MAP.clear()
        _EFF_MAP["A"] = 30.0
        _EFF_MAP["B"] = 20.0
        holder = _mk_op("Z", "z", ["manu_prod_spd&manu[100]"])
        ops = [holder, _mk_op("A", "a"), _mk_op("B", "b")]
        cost = compute_opportunity_cost_lmd(ops, "Mfg", "CombatRecord", 12.0)
        expected_pct = 30.0 + 20.0
        assert cost > 0.0
        assert abs(cost - expected_pct * (1.0 / 3.0) * (1000.0 / 1.3) * 12.0 / 100.0) < 0.01


class TestEdgeCases:
    """边界条件"""

    @patch("steward_core.solver.slot.opportunity.operator_estimated_efficiency", _fake_estimated_efficiency)
    def test_single_zeroer_only(self):
        _EFF_MAP.clear()
        saria = _mk_op("森蚺", "saria", ["manu_prod_spd&power[000]"])
        ops = [saria, _mk_op("A", "a"), _mk_op("B", "b")]
        assert compute_opportunity_cost_lmd(ops, "Mfg", "CombatRecord", 12.0) == 0.0

    @patch("steward_core.solver.slot.opportunity.operator_estimated_efficiency", _fake_estimated_efficiency)
    def test_all_same_eff_single_roommate(self):
        _EFF_MAP.clear()
        _EFF_MAP["A"] = 40.0
        saria = _mk_op("森蚺", "saria", ["manu_prod_spd&power[000]"])
        ops = [saria, _mk_op("A", "a"), _mk_op("B", "b")]
        cost = compute_opportunity_cost_lmd(ops, "Mfg", "CombatRecord", 12.0)
        assert cost > 0.0

    def test_empty_combo(self):
        assert compute_opportunity_cost_lmd([], "Mfg", "CombatRecord", 12.0) == 0.0


class TestConversionConsistency:
    """验证换算常量与 partials.py 一致"""

    def test_trade_lmd_per_hour(self):
        from steward_core.solver.slot.partials import _TRADE_BASE_LMD_PER_HOUR
        from steward_core.solver.slot.contribution import _TRADE_BASE_LMD_PER_HOUR as c_val
        assert abs(_TRADE_BASE_LMD_PER_HOUR - c_val) < 0.001

    def test_mfg_cr_constants(self):
        from steward_core.solver.slot.partials import _CR_EXP_PER_UNIT
        from steward_core.solver.slot.contribution import _MFG_CR_BASE_RATE as c_base
        from steward_core.solver.slot.opportunity import _MFG_CR_BASE
        assert abs(_MFG_CR_BASE - c_base) < 0.001
        assert abs(_CR_EXP_PER_UNIT - 1000.0) < 0.001

    def test_mfg_pg_constants(self):
        from steward_core.solver.slot.partials import _PG_LMD_PER_UNIT
        from steward_core.solver.slot.contribution import _MFG_PG_BASE_RATE as c_base
        from steward_core.solver.slot.opportunity import _MFG_PG_BASE
        assert abs(_MFG_PG_BASE - c_base) < 0.001
        assert abs(_PG_LMD_PER_UNIT - 500.0) < 0.001
