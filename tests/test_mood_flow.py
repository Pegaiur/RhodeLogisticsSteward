"""心情流转引擎单元测试 (mood_flow.py)

测试 MoodContext / MoodModifiers / compute_mood_modifiers / _apply_mp_cost。
全部通过内存构造，不依赖磁盘文件。
"""

import pytest

from steward_core.models import Operator
from steward_core.solver.params import SolverParams
from steward_core.mood_flow import (
    MoodContext,
    MoodModifiers,
    RoomBurnContext,
    compute_mood_modifiers,
    _apply_mp_cost,
    _compute_self_mp_cost,
)
from tests.helpers import mk_op, mk_skill


# ─── MoodContext 基础操作 ─────────────────────────────────────────

class TestMoodContextFresh:
    """MoodContext.fresh() 构造与查询"""

    def test_fresh_all_full(self):
        ops = [
            mk_op("阿米娅"),
            mk_op("凯尔希"),
            mk_op("令"),
        ]
        mc = MoodContext.fresh(ops)
        assert mc.mood_of("阿米娅") == 24.0
        assert mc.mood_of("凯尔希") == 24.0

    def test_mood_of_unknown_returns_full(self):
        mc = MoodContext()
        assert mc.mood_of("未知") == 24.0

    def test_is_below_threshold(self):
        mc = MoodContext(operator_moods={"阿米娅": 10.0})
        assert mc.is_below("阿米娅", 12.0) is True
        assert mc.is_below("阿米娅", 8.0) is False

    def test_fresh_preserves_op_lookup(self):
        ops = [mk_op("阿米娅")]
        mc = MoodContext.fresh(ops)
        assert "阿米娅" in mc._op_lookup
        assert mc._op_lookup["阿米娅"].name == "阿米娅"


# ─── work_burn ────────────────────────────────────────────────────

class TestWorkBurn:
    """MoodContext.work_burn() 消耗率计算"""

    @pytest.fixture
    def mc(self):
        return MoodContext(
            operator_moods={"阿米娅": 24.0, "测试": 24.0},
            params=SolverParams(),
        )

    def test_default_burn_positive(self, mc):
        burn = mc.work_burn("阿米娅", "Mfg", 3)
        assert burn > 0.0
        assert burn < 3.0

    def test_more_slots_lower_burn(self, mc):
        """槽位越多 → 中枢减免越多 → burn 越低"""
        burn_3 = mc.work_burn("阿米娅", "Mfg", 3)
        burn_5 = mc.work_burn("阿米娅", "Control", 5)
        assert burn_5 < burn_3

    def test_with_control_operators(self, mc):
        mc.control_operators = ["中枢A"]
        burn = mc.work_burn("阿米娅", "Mfg", 3)
        assert burn > 0.0

    def test_mp_cost_zero_buff(self):
        """槐琥团队精神：同房干员的自身技能消耗被消除"""
        huaiku = mk_op("槐琥", [
            mk_skill("manu_cost_all[000]", "Mfg", "团队精神",
                     efficient={"all": 0.0}),
        ])
        # 泡泡有 -0.25 的自身消耗减免
        paopao = mk_op("泡泡", [
            mk_skill("manu_prod_limit&cost[010]", "Mfg", efficient={"all": 0.0}),
        ])
        mc = MoodContext(
            operator_moods={"泡泡": 24.0, "槐琥": 24.0},
            params=SolverParams(),
            _op_lookup={"泡泡": paopao, "槐琥": huaiku},
        )
        burn_without_huaiku = mc.work_burn("泡泡", "Mfg", 3)
        burn_with_huaiku = mc.work_burn("泡泡", "Mfg", 3, co_workers=["槐琥"])
        # 槐琥在场时消除泡泡的自身减免，burn 应回到标准值
        assert burn_without_huaiku < burn_with_huaiku
        # 无自身 buff 的干员，槐琥在场不影响 burn
        mc_plain = MoodContext(
            operator_moods={"阿米娅": 24.0, "槐琥": 24.0},
            params=SolverParams(),
            _op_lookup={"阿米娅": mk_op("阿米娅"), "槐琥": huaiku},
        )
        burn_plain_no_huaiku = mc_plain.work_burn("阿米娅", "Mfg", 3)
        burn_plain_with_huaiku = mc_plain.work_burn("阿米娅", "Mfg", 3, co_workers=["槐琥"])
        assert burn_plain_no_huaiku == burn_plain_with_huaiku


# ─── after_shift ──────────────────────────────────────────────────

class TestAfterShift:
    """MoodContext.after_shift() 不可变操作"""

    @pytest.fixture
    def mc(self):
        return MoodContext(
            operator_moods={"阿米娅": 24.0, "凯尔希": 24.0},
            params=SolverParams(),
        )

    def test_working_op_mood_decreases(self, mc):
        mc2 = mc.after_shift({"阿米娅"})
        assert mc2.mood_of("阿米娅") < 24.0

    def test_non_working_op_unchanged(self, mc):
        mc2 = mc.after_shift({"阿米娅"})
        assert mc2.mood_of("凯尔希") == 24.0

    def test_original_unchanged(self, mc):
        mc.after_shift({"阿米娅"})
        assert mc.mood_of("阿米娅") == 24.0

    def test_warmup_hours_accumulated(self, mc):
        mc2 = mc.after_shift({"阿米娅"})
        assert mc2.warmup_hours.get("阿米娅", 0.0) == 12.0

    def test_non_working_warmup_reset(self, mc):
        mc_with_warmup = MoodContext(
            operator_moods={"阿米娅": 24.0, "凯尔希": 24.0},
            warmup_hours={"凯尔希": 8.0},
            params=SolverParams(),
        )
        mc2 = mc_with_warmup.after_shift({"阿米娅"})
        assert "凯尔希" not in mc2.warmup_hours

    def test_custom_shift_hours(self, mc):
        mc2 = mc.after_shift({"阿米娅"}, shift_hours_override=6.0)
        assert mc2.warmup_hours.get("阿米娅", 0.0) == 6.0


# ─── RoomBurnContext ──────────────────────────────────────────────

class TestRoomBurnContext:
    def test_default_no_co_workers(self):
        rbc = RoomBurnContext(room_type="Mfg", room_slots=3, room_index=0)
        assert rbc.co_workers == []

    def test_with_co_workers(self):
        rbc = RoomBurnContext(
            room_type="Mfg", room_slots=3, room_index=1,
            co_workers=["泡泡", "迷迭香"],
        )
        assert len(rbc.co_workers) == 2
        assert "泡泡" in rbc.co_workers


# ─── compute_mood_modifiers ───────────────────────────────────────

class TestComputeMoodModifiers:
    def test_empty_control(self):
        mods = compute_mood_modifiers([], None)
        assert mods.control_recovery == 0.0
        assert mods.mlynar_spread is False

    def test_single_control_op(self):
        ops = [mk_op("中枢A", [mk_skill("ctrl", "Control", efficient={"all": 0.0})])]
        mods = compute_mood_modifiers(ops, None)
        assert mods.control_recovery == 0.05

    def test_five_control_ops(self):
        ops = [
            mk_op(f"中枢{i}", [mk_skill("ctrl", "Control", efficient={"all": 0.0})])
            for i in range(5)
        ]
        mods = compute_mood_modifiers(ops, None)
        assert mods.control_recovery == 0.25  # 5 × 0.05

    def test_mlynar_detected(self):
        ops = [mk_op("玛恩纳", [mk_skill("control_mp_lonely[000]", "Control",
                                          efficient={"all": 0.0})])]
        mods = compute_mood_modifiers(ops, None)
        assert mods.mlynar_spread is True
        assert mods.global_work_recovery == 0.1


# ─── _apply_mp_cost ───────────────────────────────────────────────

class TestApplyMpCost:
    @pytest.fixture
    def lookup(self):
        huaiku = mk_op("槐琥", [
            mk_skill("manu_cost_all[000]", "Mfg", efficient={"all": 0.0}),
        ])
        return {"槐琥": huaiku, "阿米娅": mk_op("阿米娅")}

    def test_no_buff_no_change(self, lookup):
        burn = _apply_mp_cost(0.65, "阿米娅", ["凯尔希"], lookup)
        assert burn == 0.65

    def test_zero_buff(self, lookup):
        """槐琥消除仅作用自身技能分量，不归零全局 burn"""
        burn = _apply_mp_cost(0.65, "阿米娅", ["槐琥"], lookup)
        assert burn == 0.65  # 阿米娅无自身 buff，槐琥不改变 burn

    def test_zero_buff_with_self_cost(self, lookup):
        """槐琥消除自身 buff 分量：泡泡 -0.25 被消除"""
        paopao = mk_op("泡泡", [
            mk_skill("manu_prod_limit&cost[010]", "Mfg", efficient={"all": 0.0}),
        ])
        lookup2 = {"槐琥": lookup["槐琥"], "泡泡": paopao}
        burn = _apply_mp_cost(0.65, "泡泡", ["槐琥"], lookup2, self_cost_delta=-0.25)
        assert burn == 0.90  # 0.65 - (-0.25) = 0.90, 回到标准值

    def test_zero_buff_阿罗玛_penalty_removed(self, lookup):
        """槐琥消除自身 buff 分量：阿罗玛 +0.25 被消除"""
        aloma = mk_op("阿罗玛", [
            mk_skill("manu_formula_spd&cost[001]", "Mfg", efficient={"all": 0.0}),
        ])
        lookup2 = {"槐琥": lookup["槐琥"], "阿罗玛": aloma}
        burn = _apply_mp_cost(0.90, "阿罗玛", ["槐琥"], lookup2, self_cost_delta=0.25)
        assert burn == 0.65  # 0.90 - 0.25 = 0.65, 回到标准值

    def test_unknown_buff_ignored(self, lookup):
        burn = _apply_mp_cost(0.65, "阿米娅", ["不存在"], lookup)
        assert burn == 0.65


# ─── MoodModifiers ────────────────────────────────────────────────

class TestMoodModifiersData:
    def test_default_zero(self):
        m = MoodModifiers()
        assert m.control_recovery == 0.0
        assert m.mlynar_spread is False
        assert m.global_work_recovery == 0.0

    def test_dorm_bonus_for_normal(self):
        m = MoodModifiers(dorm_bonus_all=0.2)
        op = mk_op("普通", [])
        assert m.dorm_bonus_for(op) == 0.2

    def test_dorm_bonus_for_elite(self):
        m = MoodModifiers(dorm_bonus_elite=0.45, dorm_bonus_all=0.2)
        op = Operator(char_id="elite", name="精英", rarity=5)
        assert m.dorm_bonus_for(op) == 0.45

    def test_dorm_bonus_low_rarity_uses_all(self):
        m = MoodModifiers(dorm_bonus_elite=0.45, dorm_bonus_all=0.15)
        op = Operator(char_id="low", name="低星", rarity=3)
        assert m.dorm_bonus_for(op) == 0.15


# ─── 自身 mp_cost ─────────────────────────────────────────────────

class TestSelfMpCost:
    """干员自身技能的 mp_cost 修正"""

    def test_泡泡自身减免(self):
        paopao = mk_op("泡泡", [
            mk_skill("manu_prod_limit&cost[010]", "Mfg", efficient={"all": 0.0}),
        ])
        lookup = {"泡泡": paopao}
        delta = _compute_self_mp_cost("泡泡", lookup)
        assert delta == -0.25

    def test_阿罗玛自身增加(self):
        aloma = mk_op("阿罗玛", [
            mk_skill("manu_formula_spd&cost[001]", "Mfg", efficient={"all": 0.0}),
        ])
        lookup = {"阿罗玛": aloma}
        delta = _compute_self_mp_cost("阿罗玛", lookup)
        assert delta == 0.25

    def test_多技能叠加(self):
        op = mk_op("复合", [
            mk_skill("manu_prod_limit&cost[010]", "Mfg", efficient={"all": 0.0}),
            mk_skill("manu_prod_spd&limit&cost[000]", "Mfg", efficient={"all": 0.0}),
        ])
        lookup = {"复合": op}
        delta = _compute_self_mp_cost("复合", lookup)
        assert delta == -0.40  # -0.25 + -0.15

    def test_空技能返回零(self):
        op = mk_op("阿米娅", [])
        lookup = {"阿米娅": op}
        assert _compute_self_mp_cost("阿米娅", lookup) == 0.0

    def test_未知干员返回零(self):
        assert _compute_self_mp_cost("不存在", {}) == 0.0

    def test_work_burn_含自身减免(self):
        paopao = mk_op("泡泡", [
            mk_skill("manu_prod_limit&cost[010]", "Mfg", efficient={"all": 0.0}),
        ])
        mc = MoodContext(
            operator_moods={"泡泡": 24.0},
            params=SolverParams(),
            _op_lookup={"泡泡": paopao},
        )
        burn_bubble = mc.work_burn("泡泡", "Mfg", 3)
        burn_plain = mc.work_burn("阿米娅", "Mfg", 3)
        assert burn_bubble < burn_plain

    def test_work_burn_含自身增加(self):
        aloma = mk_op("阿罗玛", [
            mk_skill("manu_formula_spd&cost[001]", "Mfg", efficient={"all": 0.0}),
        ])
        mc = MoodContext(
            operator_moods={"阿罗玛": 24.0},
            params=SolverParams(),
            _op_lookup={"阿罗玛": aloma},
        )
        burn_aloma = mc.work_burn("阿罗玛", "Mfg", 3)
        burn_plain = mc.work_burn("阿米娅", "Mfg", 3)
        assert burn_aloma > burn_plain
