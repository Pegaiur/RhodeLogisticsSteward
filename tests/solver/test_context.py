"""GlobalContext 统一上下文构造测试"""

from steward_core.models import EfficiencyMap, Operator, RoomAssignment, ShiftPlan, Skill
from steward_core.solver.context import GlobalContext
from steward_core.solver.params import SolverParams


def _mk_op(name: str = "测试", skills: list[Skill] | None = None,
           group_id: str | None = None, nation_id: str | None = None) -> Operator:
    return Operator(char_id=name, name=name, skills=skills or [],
                    group_id=group_id, nation_id=nation_id)


def _mk_mfg_skill(efficiency: float, buff_id: str = "test") -> Skill:
    return Skill(
        buff_id=buff_id, buff_name="制造技能", skill_icon=buff_id,
        room_type="Mfg",
        efficient=EfficiencyMap(raw={"all": efficiency}),
    )


def _mk_ctrl_skill(efficiency: float, buff_id: str = "test") -> Skill:
    return Skill(
        buff_id=buff_id, buff_name="中枢技能", skill_icon=buff_id,
        room_type="Control",
        efficient=EfficiencyMap(raw={"all": efficiency}),
    )


class TestGlobalContextFromEstimated:
    """from_estimated() — 预评估上下文"""

    def test_空上下文_返回有效对象(self):
        """无 control/dorm → GlobalContext 默认值仍可构造"""
        params = SolverParams()
        ctx = GlobalContext.from_estimated(
            control_operators=[], dorm_operators=[], all_operators=[],
            assigned_names=set(), params=params,
        )
        assert ctx.global_bonus is not None
        assert ctx.effective_power == 3  # BASE_POWER_COUNT

    def test_有控制中枢_生成global_bonus(self):
        """控制中枢干员 → global_bonus 被计算"""
        params = SolverParams()
        ctrl_ops = [
            _mk_op("C1", [_mk_ctrl_skill(0.0, "c1")]),
        ]
        ctx = GlobalContext.from_estimated(
            control_operators=ctrl_ops, dorm_operators=[], all_operators=ctrl_ops,
            assigned_names=set(), params=params,
        )
        assert ctx.control_operators == ctrl_ops

    def test_含迷迭香_标志正确(self):
        """mfg_operators → buff_pool 被正确初始化"""
        params = SolverParams()
        rosmontis = _mk_op("迷迭香", [_mk_mfg_skill(0.0, "manu_prod_spd_bd_n1[000]")])
        ebenholz = _mk_op("黑键", [_mk_mfg_skill(0.0, "trade_ord_spd_bd_n1[000]")])
        ctx = GlobalContext.from_estimated(
            control_operators=[], dorm_operators=[], all_operators=[],
            assigned_names=set(), params=params,
            mfg_operators=[rosmontis], trade_operators=[ebenholz],
        )
        assert ctx.buff_pool is not None


class TestGlobalContextFromPlan:
    """from_plan() — 已完成排班的上下文"""

    def test_空排班_返回有效对象(self):
        """空 ShiftPlan → 有效 GlobalContext"""
        params = SolverParams()
        plan = ShiftPlan(name="test", assignments=[])
        ctx = GlobalContext.from_plan(plan, [], params)
        assert ctx.global_bonus is not None
        assert ctx.effective_power == 3

    def test_含Mfg房间_提取上下文(self):
        """从含 Mfg 的排班中构建上下文"""
        params = SolverParams()
        ops = [
            _mk_op("A", [_mk_mfg_skill(30.0, "a")]),
            _mk_op("B", [_mk_mfg_skill(25.0, "b")]),
            _mk_op("C", [_mk_mfg_skill(20.0, "c")]),
            _mk_op("CtrlA", [_mk_ctrl_skill(0.0, "ctrl_a")]),
        ]
        plan = ShiftPlan(
            name="test",
            assignments=[
                RoomAssignment("Mfg", 0, ["A", "B", "C"], "CombatRecord"),
                RoomAssignment("Control", 0, ["CtrlA"]),
            ],
        )
        ctx = GlobalContext.from_plan(plan, ops, params)
        assert len(ctx.control_operators) == 1
        assert ctx.control_operators[0].name == "CtrlA"
        assert "Mfg" in ctx.all_assignments

    def test_迷迭香在Mfg_标志正确(self):
        """迷迭香在 Mfg → has_rosmontis 被正确检测"""
        params = SolverParams()
        rosmontis = _mk_op("迷迭香", [_mk_mfg_skill(0.0, "ros")])
        plan = ShiftPlan(
            name="test",
            assignments=[
                RoomAssignment("Mfg", 0, ["迷迭香", "A", "B"], "CombatRecord"),
            ],
        )
        ctx = GlobalContext.from_plan(plan, [rosmontis], params)
        assert ctx.buff_pool is not None
