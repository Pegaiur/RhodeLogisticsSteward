"""BaselineStrategy 的 Pipeline 编排器测试"""

import pytest

from steward_core.models import EfficiencyMap, Operator, RoomAssignment, Skill
from steward_core.solver.config import SolverConfig
from steward_core.solver.strategies.baseline import Pipeline


def _mk_op(name: str = "测试", skills: list[Skill] | None = None) -> Operator:
    return Operator(char_id=name, name=name, skills=skills or [])


def _mk_mfg_skill(efficiency: float, buff_id: str = "test") -> Skill:
    return Skill(
        buff_id=buff_id, buff_name="制造技能", skill_icon=buff_id,
        room_type="Mfg",
        efficient=EfficiencyMap(raw={"all": efficiency}),
    )


class TestPipelineDefault:
    """默认流水线"""

    def test_default_返回非空流水线(self):
        """Pipeline.default() 返回含 Phase 的流水线"""
        pipe = Pipeline.default()
        assert len(pipe.phases) >= 4
        phase_names = [name for name, _ in pipe.phases]
        assert "mfg" in phase_names
        assert "trade" in phase_names
        assert "control" in phase_names

    def test_describe_返回描述字符串(self):
        """describe() 返回可读的流水线描述"""
        pipe = Pipeline.default()
        desc = pipe.describe()
        assert "mfg" in desc
        assert "→" in desc  # 箭头分隔

    def test_default_run_空干员_不崩溃(self):
        """默认流水线对空干员集运行不崩溃"""
        pipe = Pipeline.default()
        config = SolverConfig()
        assigned_ids = set()
        assigned_names = set()
        assignments = []
        op_lookup = {}
        locked = {"Control": set(), "Trade": set(), "Dormitory": set(), "Office": set()}

        autofill = pipe.run([], config, assigned_ids, assigned_names, assignments, op_lookup, locked)
        assert isinstance(autofill, int)

    def test_default_run_有干员_产生分配(self):
        """默认流水线对简单干员集运行产生有效分配"""
        pipe = Pipeline.default()
        config = SolverConfig()
        ops = [
            _mk_op("A", [_mk_mfg_skill(30.0, "a")]),
            _mk_op("B", [_mk_mfg_skill(25.0, "b")]),
            _mk_op("C", [_mk_mfg_skill(20.0, "c")]),
            _mk_op("D", [_mk_mfg_skill(30.0, "d")]),
            _mk_op("E", [_mk_mfg_skill(25.0, "e")]),
            _mk_op("F", [_mk_mfg_skill(20.0, "f")]),
        ]
        assigned_ids = set()
        assigned_names = set()
        assignments = []
        op_lookup = {op.name: op for op in ops}
        locked = {"Control": set(), "Trade": set(), "Dormitory": set(), "Office": set()}

        autofill = pipe.run(ops, config, assigned_ids, assigned_names, assignments, op_lookup, locked)
        assert autofill >= 0
        assert len(assignments) > 0


class TestPipelineCustom:
    """自定义流水线"""

    def test_with_phases_构造有效流水线(self):
        """with_phases() 可构造自定义 Phase 顺序"""
        from steward_core.solver.exhaust_mfg import exhaust_mfg

        pipe = Pipeline.with_phases([
            ("mfg", exhaust_mfg),
        ])
        assert len(pipe.phases) == 1
        assert pipe.phases[0][0] == "mfg"

    def test_describe_自定义流水线(self):
        """自定义流水线的 describe 正确反映顺序"""
        from steward_core.solver.exhaust_mfg import exhaust_mfg
        from steward_core.solver.fill_control import fill_control

        pipe = Pipeline.with_phases([
            ("control", fill_control),
            ("mfg", exhaust_mfg),
        ])
        assert pipe.describe() == "control → mfg"
