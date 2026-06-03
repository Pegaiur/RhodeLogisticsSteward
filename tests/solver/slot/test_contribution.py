"""统一贡献评分单元测试"""

import pytest

from steward_core.models import EfficiencyMap, LayoutConfig, Operator, Skill
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext
from steward_core.solver.slot.contribution import contribution
from steward_core.mood_flow import MoodContext


def _dummy_op(char_id: str, name: str) -> Operator:
    return Operator(char_id=char_id, name=name, skills=[])


def _dorm_op(name: str, char_id: str, recovery: float) -> Operator:
    """构造宿舍恢复型干员"""
    return Operator(
        char_id=char_id, name=name,
        skills=[Skill(
            buff_id=f"dorm_rec_{char_id}",
            buff_name="宿舍恢复技能",
            skill_icon="test",
            room_type="DORMITORY",
            efficient=EfficiencyMap(raw={"all": recovery}),
        )],
    )


def _dorm_all_op(name: str, char_id: str, recovery: float) -> Operator:
    """构造全体恢复型宿舍干员（D 类：buff_id 以 dorm_rec_all 开头）"""
    return Operator(
        char_id=char_id, name=name,
        skills=[Skill(
            buff_id=f"dorm_rec_all[{char_id}]",
            buff_name="全体恢复",
            skill_icon="test",
            room_type="DORMITORY",
            efficient=EfficiencyMap(raw={"all": recovery}),
        )],
    )


def _dorm_single_op(name: str, char_id: str, recovery: float) -> Operator:
    """构造单体恢复型宿舍干员（C 类：buff_id 以 dorm_rec_single 开头）"""
    return Operator(
        char_id=char_id, name=name,
        skills=[Skill(
            buff_id=f"dorm_rec_single[{char_id}]",
            buff_name="单体恢复",
            skill_icon="test",
            room_type="DORMITORY",
            efficient=EfficiencyMap(raw={"all": recovery}),
        )],
    )


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


class TestDormContributionWithLambdaK:
    """宿舍贡献——房间感知边际评估

    新模型：宿管价值 = 状态向量增量 + 对室友的恢复增量 - 槽位机会成本。
    空房间无室友时 Part2=0；有室友时 Part2 反映 recovery delta × roommate_λ；
    同房间第2个C类增量=0（Rule3取max）。
    测试验证公式结构正确性，不做绝对值断言（取决于 λ 参数比例）。
    """

    @pytest.fixture
    def dorm_recovery_op(self):
        """全体恢复型宿舍干员（D 类：dorm_rec_all，+0.25/h）"""
        return _dorm_all_op("杜林", "char_durin", 0.25)

    @pytest.fixture
    def dorm_single_op(self):
        """单体恢复型宿舍干员（C 类：dorm_rec_single，+0.55/h）"""
        return _dorm_single_op("闪灵", "char_single", 0.55)

    @pytest.fixture
    def work_op(self):
        """普通工作干员（制造站）"""
        return Operator(
            char_id="char_work", name="酒神",
            skills=[Skill(
                buff_id="manu_prod_spd[000]",
                buff_name="制造",
                skill_icon="test",
                room_type="Manufacture",
                efficient=EfficiencyMap(raw={"Battle Record": 0.25}),
            )],
        )

    def test_empty_room_no_recovery_delta(self, dorm_recovery_op):
        """空房间无室友 → recovery 贡献=0（Part2不触发）"""
        ctx = SlotContext.from_layout(
            [dorm_recovery_op],
            LayoutConfig.layout_243(),
            SolverParams(),
        )
        ctx.lambda_k = 0.0  # 消除机会成本干扰
        result = contribution(ctx, "杜林", "Dormitory")
        # 无状态写入、无室友、无机会成本 → 0
        assert result == 0.0, f"空房间应=0，实际={result}"

    def test_roommate_recovery_delta_positive(self, dorm_recovery_op, work_op):
        """有室友时 D 类宿管产生正恢复增量"""
        ctx = SlotContext.from_layout(
            [dorm_recovery_op, work_op],
            LayoutConfig.layout_243(),
            SolverParams(),
        )
        ctx.place(0, "dorm_0_0", "酒神")
        mc = MoodContext.fresh([dorm_recovery_op, work_op], SolverParams())
        object.__setattr__(mc, "operator_moods", {"酒神": 12.0, "杜林": 24.0})
        ctx.op_peak_eff["酒神"] = 25.0
        result = contribution(ctx, "杜林", "Dormitory", room_index=0, mood_ctx=mc)
        assert result > 0, f"室友恢复增量应为正: {result}"

    def test_single_type_redundant_delta_zero(self, dorm_single_op, work_op):
        """同房间第2个C类增量=0（Rule3取max）"""
        second_c = _dorm_single_op("芙蓉", "char_single2", 0.30)
        ctx = SlotContext.from_layout(
            [dorm_single_op, second_c, work_op],
            LayoutConfig.layout_243(),
            SolverParams(),
        )
        ctx.lambda_ops["酒神"] = 100.0
        ctx.lambda_k = 0.0
        ctx.place(0, "dorm_0_0", "闪灵")
        ctx.place(0, "dorm_0_1", "酒神")
        result = contribution(ctx, "芙蓉", "Dormitory", room_index=0)
        # 闪灵(0.55) > 芙蓉(0.30) → Rule3取max → Δrec=0
        # λ_k=0 → 机会成本=0 → 结果=0
        assert result == 0.0, (
            f"第2个C类增量应为0，实际={result}"
        )

    def test_no_lambda_no_recovery_contribution(self, dorm_recovery_op):
        """λ 全部为 0 时恢复部分不产生贡献"""
        ctx = SlotContext.from_layout(
            [dorm_recovery_op],
            LayoutConfig.layout_243(),
            SolverParams(),
        )
        ctx.lambda_k = 0.0
        ctx.lambda_ops["杜林"] = 0.0
        result = contribution(ctx, "杜林", "Dormitory")
        assert result == 0.0, f"λ=0 时贡献应为 0，实际={result}"


class TestRecoveryContribution:
    """中枢心情恢复贡献——mood_saved × eff_weight × base_LMD"""

    @pytest.fixture
    def params(self) -> SolverParams:
        return SolverParams(shift_hours=12.0)

    def _mk_mlynar(self) -> Operator:
        """玛恩纳：control_mp_lonely[000] 公事公办"""
        return Operator(
            char_id="char_mlynar", name="玛恩纳",
            skills=[Skill(
                buff_id="control_mp_lonely[000]", buff_name="公事公办",
                skill_icon="test", room_type="CONTROL",
                efficient=EfficiencyMap(raw={"all": 0.0}),
            )],
        )

    def _mk_work_op(self, char_id: str, name: str, eff: float = 0.0) -> Operator:
        return Operator(
            char_id=char_id, name=name,
            skills=[Skill(
                buff_id=f"work_{char_id}", buff_name="工作技能",
                skill_icon="test", room_type="MANUFACTURE",
                efficient=EfficiencyMap(raw={"all": eff}),
            )],
        )

    def test_recovery_value_positive_with_working_ops(self, params):
        """有 Mfg/Trade 工作干员时，control_recovery 贡献为正"""
        from steward_core.solver.slot.contribution import _compute_recovery_value
        mlynar = self._mk_mlynar()
        w1 = self._mk_work_op("w1", "工作A", 30.0)
        w2 = self._mk_work_op("w2", "工作B", 60.0)
        ops = [mlynar, w1, w2] + [_dummy_op(f"d{i}", f"填位{i}") for i in range(3)]
        ctx = SlotContext.from_layout(ops, LayoutConfig.layout_243(), params)
        ctx.place(0, "mfg_0_0", "工作A")
        ctx.place(0, "mfg_0_1", "工作B")
        ctx.op_peak_eff["工作A"] = 30.0
        ctx.op_peak_eff["工作B"] = 60.0

        value = _compute_recovery_value(ctx, ["玛恩纳"], 0)
        assert value > 0.0

    def test_recovery_value_zero_without_working_ops(self, params):
        """无 Mfg/Trade 干员时，恢复贡献为 0"""
        from steward_core.solver.slot.contribution import _compute_recovery_value
        mlynar = self._mk_mlynar()
        ops = [mlynar] + [_dummy_op(f"d{i}", f"填位{i}") for i in range(3)]
        ctx = SlotContext.from_layout(ops, LayoutConfig.layout_243(), params)
        value = _compute_recovery_value(ctx, ["玛恩纳"], 0)
        assert value == 0.0

    def test_recovery_marginal_delta(self, params):
        """新增中枢干员 → recovery 边际增量正确"""
        from steward_core.solver.slot.contribution import _compute_recovery_value
        mlynar = self._mk_mlynar()
        dubin = Operator(
            char_id="char_130", name="杜宾",
            skills=[Skill(
                buff_id="control_mp_cost[000]", buff_name="左膀右臂",
                skill_icon="test", room_type="CONTROL",
                efficient=EfficiencyMap(raw={"all": 0.0}),
            )],
        )
        w1 = self._mk_work_op("w1", "工作A", 30.0)
        ops = [mlynar, dubin, w1] + [_dummy_op(f"x{i}", f"填{i}") for i in range(3)]
        ctx = SlotContext.from_layout(ops, LayoutConfig.layout_243(), params)
        ctx.place(0, "mfg_0_0", "工作A")
        ctx.op_peak_eff["工作A"] = 30.0

        val_without = _compute_recovery_value(ctx, [], 0)
        val_with_dubin = _compute_recovery_value(ctx, ["杜宾"], 0)
        val_with_both = _compute_recovery_value(ctx, ["杜宾", "玛恩纳"], 0)

        # 每增加一名持有 control_mp_cost 的中枢：control_recovery +0.05/h
        assert val_with_dubin > val_without
        assert val_with_both > val_with_dubin
        # 玛恩纳额外提供 global_work_recovery +0.1/h + spread
        delta_mlynar = val_with_both - val_with_dubin
        delta_dubin = val_with_dubin - val_without
        assert delta_mlynar > delta_dubin, f"玛恩纳增量{delta_mlynar}应 > 杜宾增量{delta_dubin}"
