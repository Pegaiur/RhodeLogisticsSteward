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


# ─── Step A 新增 mp_cost buff 回归测试 ─────────────────────────────

class TestNewSelfMpCost:
    """Step A + D：新接入的 mp_cost buff 自身修正校验

    覆盖 HIRE / MEETING / CONTROL 三类设施的无条件自身 buff。
    """

    # ── HIRE 自身 buff ──────────────────────────────────────────

    def test_地灵_准时下班_增加2消耗(self):
        """hire_spd_cost[200] = +2.0/h"""
        op = mk_op("地灵", [
            mk_skill("hire_spd_cost[200]", "HIRE", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("地灵", {"地灵": op})
        assert delta == 2.0

    def test_斥罪_法为正典_增加0点5消耗(self):
        """hire_spd_cost[210] = +0.5/h"""
        op = mk_op("斥罪", [
            mk_skill("hire_spd_cost[210]", "HIRE", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("斥罪", {"斥罪": op})
        assert delta == 0.5

    def test_水灯心_alpha_增加1消耗(self):
        """hire_spd_cost[220] = +1.0/h"""
        op = mk_op("水灯心", [
            mk_skill("hire_spd_cost[220]", "HIRE", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("水灯心", {"水灯心": op})
        assert delta == 1.0

    def test_水灯心_beta_增加1消耗(self):
        """hire_spd_cost[230] = +1.0/h"""
        op = mk_op("水灯心", [
            mk_skill("hire_spd_cost[230]", "HIRE", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("水灯心", {"水灯心": op})
        assert delta == 1.0

    def test_桑葚_救援队珠算_减少消耗(self):
        """hire_spd_cost[100] = -0.25/h"""
        op = mk_op("桑葚", [
            mk_skill("hire_spd_cost[100]", "HIRE", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("桑葚", {"桑葚": op})
        assert delta == -0.25

    def test_林_特殊渠道_减少消耗(self):
        """hire_spd_cost[111] = -0.25/h"""
        op = mk_op("林", [
            mk_skill("hire_spd_cost[111]", "HIRE", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("林", {"林": op})
        assert delta == -0.25

    def test_深律_alpha_减少消耗(self):
        """hire_spd_cost[101] = -0.25/h"""
        op = mk_op("深律", [
            mk_skill("hire_spd_cost[101]", "HIRE", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("深律", {"深律": op})
        assert delta == -0.25

    def test_行箸_alpha_减少消耗(self):
        """hire_spd_cost[112] = -0.25/h"""
        op = mk_op("行箸", [
            mk_skill("hire_spd_cost[112]", "HIRE", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("行箸", {"行箸": op})
        assert delta == -0.25

    # ── MEETING 自身 buff ───────────────────────────────────────

    def test_见行者_逻辑推理_增加2消耗(self):
        """meet_spd&cost[100] = +2.0/h（核心用例）"""
        op = mk_op("见行者", [
            mk_skill("meet_spd&cost[100]", "MEETING", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("见行者", {"见行者": op})
        assert delta == 2.0

    def test_见行者_work_burn_reception(self):
        """见行者在 Reception 的 work_burn 应显著高于普通干员"""
        jianxingzhe = mk_op("见行者", [
            mk_skill("meet_spd&cost[100]", "MEETING", efficient={"all": 0.0}),
        ])
        mc = MoodContext(
            operator_moods={"见行者": 24.0, "阿米娅": 24.0},
            params=SolverParams(),
            _op_lookup={"见行者": jianxingzhe},
        )
        burn_jx = mc.work_burn("见行者", "Reception", 2)
        burn_plain = mc.work_burn("阿米娅", "Reception", 2)
        assert burn_jx > burn_plain + 1.5  # +2.0 差异应显著

    def test_见行者_12h班次_心情耗尽(self):
        """见行者 +2.0/h 消耗 + 基础 ~0.9 = ~2.9/h，
        12h 班次消耗 ~35，远超 24h 满心情 → 撑不过一个班次"""
        jianxingzhe = mk_op("见行者", [
            mk_skill("meet_spd&cost[100]", "MEETING", efficient={"all": 0.0}),
        ])
        mc = MoodContext(
            operator_moods={"见行者": 24.0},
            params=SolverParams(),
            _op_lookup={"见行者": jianxingzhe},
        )
        burn = mc.work_burn("见行者", "Reception", 2)
        assert burn > 2.0, f"预期消耗 >2.0/h，实际 {burn:.2f}"
        # 12h × burn > 24h → 心情在一班内耗尽
        assert burn * 12.0 > 24.0, f"见行者应撑不过一个班次，12h × {burn:.2f} = {burn * 12:.1f}"

    def test_提丰_冰原游弋_增加0点5消耗(self):
        """meet_spd&sami[000] = +0.5/h"""
        op = mk_op("提丰", [
            mk_skill("meet_spd&sami[000]", "MEETING", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("提丰", {"提丰": op})
        assert delta == 0.5

    def test_凛视_远见_增加0点5消耗(self):
        """meet_spd&bd[000] = +0.5/h"""
        op = mk_op("凛视", [
            mk_skill("meet_spd&bd[000]", "MEETING", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("凛视", {"凛视": op})
        assert delta == 0.5

    # ── CONTROL 自身 buff ───────────────────────────────────────

    def test_涤火杰西卡_老友相聚_增加0点5消耗(self):
        """control_bd_spd[000] = +0.5/h"""
        op = mk_op("涤火杰西卡", [
            mk_skill("control_bd_spd[000]", "Control", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("涤火杰西卡", {"涤火杰西卡": op})
        assert delta == 0.5

    def test_怒潮凛冬_是团长_增加0点5消耗(self):
        """control_meeting_bd[000] = +0.5/h"""
        op = mk_op("怒潮凛冬", [
            mk_skill("control_meeting_bd[000]", "Control", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("怒潮凛冬", {"怒潮凛冬": op})
        assert delta == 0.5

    def test_夕_不以己悲_增加0点5消耗_in_control(self):
        """control_mp_cost&bd2[000] = +0.5/h"""
        op = mk_op("夕", [
            mk_skill("control_mp_cost&bd2[000]", "Control", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("夕", {"夕": op})
        assert delta == 0.5

    def test_重岳_知我为我_增加0点5消耗(self):
        """control_mp_cost&bd_up[000] = +0.5/h"""
        op = mk_op("重岳", [
            mk_skill("control_mp_cost&bd_up[000]", "Control", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("重岳", {"重岳": op})
        assert delta == 0.5

    def test_麒麟R夜刀_耐力回复_增加0点5消耗(self):
        """control_mp_cost&bd2[010] = +0.5/h"""
        op = mk_op("麒麟R夜刀", [
            mk_skill("control_mp_cost&bd2[010]", "Control", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("麒麟R夜刀", {"麒麟R夜刀": op})
        assert delta == 0.5

    def test_艾拉_反抗者_增加0点25消耗(self):
        """control_clue_cost&faction[990] = +0.25/h"""
        op = mk_op("艾拉", [
            mk_skill("control_clue_cost&faction[990]", "Control",
                     efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("艾拉", {"艾拉": op})
        assert delta == 0.25

    def test_祐天寺若麦_成效优先_增加0点05消耗(self):
        """control_mp&meet_spd[000] = +0.05/h"""
        op = mk_op("祐天寺若麦", [
            mk_skill("control_mp&meet_spd[000]", "Control", efficient={"all": 0.0}),
        ])
        delta = _compute_self_mp_cost("祐天寺若麦", {"祐天寺若麦": op})
        assert delta == 0.05


# ─── 巫恋房间级 mp_cost ───────────────────────────────────────────

class TestWuLianRoomMpCost:
    """巫恋 trade_ord_vodfox[000] 房间级 +0.25/h"""

    def test_巫恋低语_对同房干员增加消耗(self):
        """巫恋在 Trade 房间时，同房其他干员心情消耗 +0.25/h"""
        wulian = mk_op("巫恋", [
            mk_skill("trade_ord_vodfox[000]", "Trading", efficient={"all": 0.0}),
        ])
        amiya = mk_op("阿米娅")
        lookup = {"巫恋": wulian, "阿米娅": amiya}
        # 无巫恋时 burn
        burn_base = _apply_mp_cost(0.70, "阿米娅", ["其他人"], lookup)
        burn_with_wulian = _apply_mp_cost(0.70, "阿米娅", ["巫恋"], lookup)
        assert burn_with_wulian == pytest.approx(burn_base + 0.25)

    def test_wulian_not_triggered_if_not_in_room(self):
        """巫恋不在房间时不触发"""
        wulian = mk_op("巫恋", [
            mk_skill("trade_ord_vodfox[000]", "Trading", efficient={"all": 0.0}),
        ])
        amiya = mk_op("阿米娅")
        lookup = {"巫恋": wulian, "阿米娅": amiya}
        burn = _apply_mp_cost(0.70, "阿米娅", ["泡泡"], lookup)
        assert burn == 0.70  # 巫恋不在 co_workers 中，不触发


# ─── TRADING _P 同僚条件配对 ──────────────────────────────────────

class TestSelfPairMpCost:
    """TRADING _P 后缀 buff: mp_cost 在同僚配对时生效"""

    def test_德克萨斯_恩怨_拉普兰德同房_增加消耗(self):
        """trade_ord_spd&cost_P[000]: 拉普兰德同房时 +0.3/h"""
        texas = mk_op("德克萨斯", [
            mk_skill("trade_ord_spd&cost_P[000]", "Trading", efficient={"all": 0.0}),
        ])
        lapland = mk_op("拉普兰德")
        amiya = mk_op("阿米娅")
        lookup = {"德克萨斯": texas, "拉普兰德": lapland, "阿米娅": amiya}
        # 拉普兰德不在时不触发
        burn_no = _apply_mp_cost(0.70, "德克萨斯", ["阿米娅"], lookup)
        assert burn_no == 0.70
        # 拉普兰德在时 +0.3
        burn_yes = _apply_mp_cost(0.70, "德克萨斯", ["拉普兰德", "阿米娅"], lookup)
        assert burn_yes == pytest.approx(1.00)

    def test_德克萨斯_默契_能天使同房_减少消耗(self):
        """trade_ord_limit&cost_P[010]: 能天使同房时 -0.3/h"""
        texas = mk_op("德克萨斯", [
            mk_skill("trade_ord_limit&cost_P[010]", "Trading", efficient={"all": 0.0}),
        ])
        exusiai = mk_op("能天使")
        lookup = {"德克萨斯": texas, "能天使": exusiai}
        burn_no = _apply_mp_cost(0.70, "德克萨斯", ["其他"], lookup)
        assert burn_no == 0.70
        burn_yes = _apply_mp_cost(0.70, "德克萨斯", ["能天使"], lookup)
        assert burn_yes == pytest.approx(0.40)  # 0.70 - 0.30

    def test_拉普兰德_醉翁之意_德克萨斯同房_减少消耗(self):
        """trade_ord_limit&cost_P[000]: 德克萨斯同房时 -0.1/h"""
        lapland = mk_op("拉普兰德", [
            mk_skill("trade_ord_limit&cost_P[000]", "Trading", efficient={"all": 0.0}),
        ])
        texas = mk_op("德克萨斯")
        lookup = {"拉普兰德": lapland, "德克萨斯": texas}
        burn_no = _apply_mp_cost(0.70, "拉普兰德", ["其他"], lookup)
        assert burn_no == 0.70
        burn_yes = _apply_mp_cost(0.70, "拉普兰德", ["德克萨斯"], lookup)
        assert burn_yes == pytest.approx(0.60)  # 0.70 - 0.10

    def test_贝洛内_未偿还的债务_伺夜同房_减少消耗(self):
        """trade_ord_limit&cost_P[020]: 伺夜同房时 -0.1/h"""
        bellone = mk_op("贝洛内", [
            mk_skill("trade_ord_limit&cost_P[020]", "Trading", efficient={"all": 0.0}),
        ])
        siye = mk_op("伺夜")
        lookup = {"贝洛内": bellone, "伺夜": siye}
        burn_no = _apply_mp_cost(0.70, "贝洛内", ["其他"], lookup)
        assert burn_no == 0.70
        burn_yes = _apply_mp_cost(0.70, "贝洛内", ["伺夜"], lookup)
        assert burn_yes == pytest.approx(0.60)

    def test_德克萨斯_恩怨加默契_双条件均满足_叠加(self):
        """拉普兰德和能天使同在时，恩怨+0.3 + 默契-0.3 = 0（抵消）"""
        texas = mk_op("德克萨斯", [
            mk_skill("trade_ord_spd&cost_P[000]", "Trading", efficient={"all": 0.0}),
            mk_skill("trade_ord_limit&cost_P[010]", "Trading", efficient={"all": 0.0}),
        ])
        lapland = mk_op("拉普兰德")
        exusiai = mk_op("能天使")
        lookup = {"德克萨斯": texas, "拉普兰德": lapland, "能天使": exusiai}
        burn = _apply_mp_cost(0.70, "德克萨斯",
                              ["拉普兰德", "能天使"], lookup)
        assert burn == pytest.approx(0.70)  # +0.3 -0.3 = 0
