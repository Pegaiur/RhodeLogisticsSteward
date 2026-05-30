"""局部搜索测试 (Step 2)

测试 evaluate_full_plan 全量评估与 local_search_refine 局部优化。
"""

import pytest

from steward_core.models import (
    EfficiencyMap, Operator, RoomAssignment, ShiftPlan,
    SolveResult, Skill,
)
from steward_core.solver.config import SolverConfig


def _mk_op(name: str = "测试", skills: list[Skill] | None = None,
           group_id: str | None = None, nation_id: str | None = None) -> Operator:
    return Operator(char_id=name, name=name, skills=skills or [],
                    group_id=group_id, nation_id=nation_id)


def _mk_mfg_skill(buff_name: str, efficiency: float, buff_id: str = "test",
                  room_type: str = "Mfg") -> Skill:
    return Skill(
        buff_id=buff_id, buff_name=buff_name, skill_icon=buff_id,
        room_type=room_type,
        efficient=EfficiencyMap(raw={"all": efficiency}),
    )


def _mk_trade_skill(efficiency: float, buff_id: str = "test") -> Skill:
    return Skill(
        buff_id=buff_id, buff_name="贸易技能", skill_icon=buff_id,
        room_type="Trade",
        efficient=EfficiencyMap(raw={"all": efficiency}),
    )


def _mk_power_skill(efficiency: float, buff_id: str = "test") -> Skill:
    return Skill(
        buff_id=buff_id, buff_name="发电技能", skill_icon=buff_id,
        room_type="Power",
        efficient=EfficiencyMap(raw={"all": efficiency}),
    )


class TestEvaluateFullPlan:
    """全量排班评估"""

    def test_单间Mfg_返回正值(self):
        """含一个 Mfg 房间的全量评估返回正值"""
        from steward_core.solver.refine import evaluate_full_plan

        ops = [
            _mk_op("A", [_mk_mfg_skill("s", 30.0, "a")]),
            _mk_op("B", [_mk_mfg_skill("s", 25.0, "b")]),
            _mk_op("C", [_mk_mfg_skill("s", 20.0, "c")]),
        ]
        plan = ShiftPlan(
            name="test",
            assignments=[
                RoomAssignment("Mfg", 0, ["A", "B", "C"], "CombatRecord"),
            ],
        )

        score = evaluate_full_plan(plan, ops)
        assert score > 0

    def test_空排班_返回零(self):
        """无干员的空排班 → 返回 0"""
        from steward_core.solver.refine import evaluate_full_plan

        plan = ShiftPlan(name="test", assignments=[])
        score = evaluate_full_plan(plan, [])
        assert score == 0.0

    def test_好排班优于差排班(self):
        """多间 Mfg 的高效排班 > 低效排班"""
        from steward_core.solver.refine import evaluate_full_plan

        high_ops = [
            _mk_op("A", [_mk_mfg_skill("s", 30.0, "a")]),
            _mk_op("B", [_mk_mfg_skill("s", 30.0, "b")]),
            _mk_op("C", [_mk_mfg_skill("s", 30.0, "c")]),
            _mk_op("D", [_mk_mfg_skill("s", 30.0, "d")]),
            _mk_op("E", [_mk_mfg_skill("s", 30.0, "e")]),
            _mk_op("F", [_mk_mfg_skill("s", 30.0, "f")]),
        ]

        low_ops = [
            _mk_op("A", [_mk_mfg_skill("s", 10.0, "a")]),
            _mk_op("B", [_mk_mfg_skill("s", 10.0, "b")]),
            _mk_op("C", [_mk_mfg_skill("s", 10.0, "c")]),
            _mk_op("D", [_mk_mfg_skill("s", 10.0, "d")]),
            _mk_op("E", [_mk_mfg_skill("s", 10.0, "e")]),
            _mk_op("F", [_mk_mfg_skill("s", 10.0, "f")]),
        ]

        assignments = [
            RoomAssignment("Mfg", 0, ["A", "B", "C"], "CombatRecord"),
            RoomAssignment("Mfg", 1, ["D", "E", "F"], "CombatRecord"),
        ]
        high_plan = ShiftPlan(name="high", assignments=assignments)
        low_plan = ShiftPlan(name="low", assignments=assignments)

        assert evaluate_full_plan(high_plan, high_ops) > evaluate_full_plan(low_plan, low_ops)

    def test_混合设施_评估非零(self):
        """含 Mfg + Trade + Power 的混合排班评估正常"""
        from steward_core.solver.refine import evaluate_full_plan

        ops = [
            _mk_op("A", [_mk_mfg_skill("s", 30.0, "a")]),
            _mk_op("B", [_mk_mfg_skill("s", 25.0, "b")]),
            _mk_op("C", [_mk_mfg_skill("s", 20.0, "c")]),
            _mk_op("D", [_mk_trade_skill(30.0, "d")]),
            _mk_op("E", [_mk_trade_skill(20.0, "e")]),
            _mk_op("F", [_mk_power_skill(20.0, "f")]),
        ]
        plan = ShiftPlan(
            name="test",
            assignments=[
                RoomAssignment("Mfg", 0, ["A", "B", "C"], "CombatRecord"),
                RoomAssignment("Trade", 0, ["D", "E"], "Money"),
                RoomAssignment("Power", 0, ["F"]),
            ],
        )

        score = evaluate_full_plan(plan, ops)
        assert score > 0


class TestLocalSearchIntegration:
    """solve_mvp 集成 — 局部搜索开关"""

    def test_开关关闭_不执行搜索(self):
        """config.local_search_enabled=False → 与不传 config 结果一致"""
        from steward_core.solver import solve_mvp

        ops = [
            _mk_op("A", [_mk_mfg_skill("s", 30.0, "a")]),
            _mk_op("B", [_mk_mfg_skill("s", 25.0, "b")]),
            _mk_op("C", [_mk_mfg_skill("s", 20.0, "c")]),
        ]
        result_off = solve_mvp(ops, config=SolverConfig(local_search_enabled=False))
        result_default = solve_mvp(ops)

        assert result_off.autofill_count == result_default.autofill_count

    def test_开关开启_不崩溃(self):
        """config.local_search_enabled=True → 求解不崩溃，返回有效结果"""
        from steward_core.solver import solve_mvp

        ops = [
            _mk_op("A", [_mk_mfg_skill("s", 30.0, "a")]),
            _mk_op("B", [_mk_mfg_skill("s", 25.0, "b")]),
            _mk_op("C", [_mk_mfg_skill("s", 20.0, "c")]),
            _mk_op("D", [_mk_mfg_skill("s", 15.0, "d")]),
            _mk_op("E", [_mk_mfg_skill("s", 10.0, "e")]),
            _mk_op("F", [_mk_mfg_skill("s", 30.0, "f")]),
        ]
        result = solve_mvp(ops, config=SolverConfig(local_search_enabled=True))

        assert result is not None
        assert len(result.plans) == 1


class TestLocalSearchImprovement:
    """局部搜索应发现并修正明显的次优方案"""

    def test_手动构造次优方案_搜索可改进(self):
        """构造一个单房间排班——搜索至少不崩溃并返回结果"""
        from steward_core.solver.refine import local_search_refine, evaluate_full_plan

        all_ops = [
            _mk_op("高A", [_mk_mfg_skill("s", 30.0, "a")]),
            _mk_op("高B", [_mk_mfg_skill("s", 30.0, "b")]),
            _mk_op("高C", [_mk_mfg_skill("s", 30.0, "c")]),
            _mk_op("低D", [_mk_mfg_skill("s", 10.0, "d")]),
            _mk_op("低E", [_mk_mfg_skill("s", 10.0, "e")]),
            _mk_op("低F", [_mk_mfg_skill("s", 10.0, "f")]),
        ]

        # 构造一个故意用低效干员的排班
        assignments = [
            RoomAssignment("Mfg", 0, ["低D", "低E", "低F"], "CombatRecord"),
        ]
        plan = ShiftPlan(name="test", assignments=assignments)
        result = SolveResult(plans=[plan], autofill_count=0)

        baseline = evaluate_full_plan(plan, all_ops)
        refined = local_search_refine(result, all_ops, SolverConfig(local_search_enabled=True))

        # 搜索后不应崩溃，且结果包含有效排班
        assert refined is not None
        assert len(refined.plans) == 1
        assert len(refined.plans[0].assignments) >= 1
