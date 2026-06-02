"""心情链式流转 (_compute_chained_mood_reports) 的集成测试

验证跨班次心情状态正确传递，不依赖磁盘文件。
"""

import pytest

from steward_core.models import EfficiencyMap, Operator, RoomAssignment, ShiftPlan, Skill
from steward_core.report import _compute_chained_mood_reports


def _mk_op(name: str, skills: list[Skill] | None = None) -> Operator:
    return Operator(char_id=name, name=name, skills=skills or [])


def _mk_skill(room_type: str, efficient: dict[str, float], buff_id: str = "test", skill_icon: str | None = None) -> Skill:
    return Skill(
        buff_id=buff_id,
        buff_name="test",
        skill_icon=skill_icon or f"test_{buff_id}",
        room_type=room_type,
        efficient=EfficiencyMap(raw=efficient),
    )


def _mk_ctrl_cost(name: str) -> Operator:
    return _mk_op(name, [
        _mk_skill("Control", {"all": 0.05}, buff_id="ctrl_cost", skill_icon="bskill_ctrl_cost"),
    ])


class TestChainedMoodReports:
    """验证 _compute_chained_mood_reports 跨班次链式流转"""

    def test_两班次后第二班初始心情不为全满(self):
        """两个相同 Mfg 干员工作两班次后，第二班 initial_moods 应低于 24.0"""
        # Arrange: 5 中枢 + 2 制造站干员
        ctrl_ops = [_mk_ctrl_cost(f"C{i+1}") for i in range(5)]
        mfg_a = _mk_op("MfgA", [_mk_skill("Mfg", {"all": 0})])
        mfg_b = _mk_op("MfgB", [_mk_skill("Mfg", {"all": 0})])

        all_ops = ctrl_ops + [mfg_a, mfg_b]

        plan = ShiftPlan(
            name="W1",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=[op.name for op in ctrl_ops]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=["MfgA", "MfgB"]),
                RoomAssignment(room_type="Dormitory", room_index=0, operators=[]),
            ],
        )

        plans = [plan, plan]

        # Act
        reports = _compute_chained_mood_reports(plans, all_ops, shift_hours=12.0)

        # Assert: 第一班满心情，第二班心情已有消耗
        r0 = reports[0]
        r1 = reports[1]

        assert r0.red_face_count == 0

        # 第二班制造站干员不应从 24.0 开始
        if r1.rooms:
            room = r1.rooms[0]
            for name in ["MfgA", "MfgB"]:
                init_val = room.operator_initial.get(name)
                assert init_val is not None
                assert init_val < 24.0, f"{name} 第二班初始心情应为 {init_val} (<24.0)"

    def test_宿舍恢复后心情有所回升(self):
        """工作后进宿舍恢复，第三班初始心情应高于连续工作方案"""
        # Arrange: 1 中枢 + 1 制造站
        ctrl = _mk_ctrl_cost("C1")
        mfg = _mk_op("Mfg", [_mk_skill("Mfg", {"all": 0})])
        dorm_mate = _mk_op("DormMate", [])

        all_ops = [ctrl, mfg, dorm_mate]

        shift_hours = 12.0

        plan_work = ShiftPlan(
            name="W-work",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=["C1"]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=["Mfg"]),
                RoomAssignment(room_type="Dormitory", room_index=0, operators=[]),
            ],
        )

        plan_rest = ShiftPlan(
            name="W-rest",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=["C1"]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=[]),
                RoomAssignment(room_type="Dormitory", room_index=0, operators=["Mfg"]),
            ],
        )

        # W1 工作 → W2 休息 → W3 工作 (休息方案)
        reports_rest = _compute_chained_mood_reports(
            [plan_work, plan_rest, plan_work], all_ops, shift_hours,
        )

        # W1 工作 → W2 工作 → W3 工作 (连续方案)
        reports_work = _compute_chained_mood_reports(
            [plan_work, plan_work, plan_work], all_ops, shift_hours,
        )

        # 第三班 (index 2) 初始心情：休息方案应更高
        mfg_rest_init_w3 = reports_rest[2].rooms[0].operator_initial.get("Mfg", 24.0)
        mfg_work_init_w3 = reports_work[2].rooms[0].operator_initial.get("Mfg", 24.0)

        assert mfg_rest_init_w3 > mfg_work_init_w3, (
            f"休息方案W3初始={mfg_rest_init_w3:.1f} 应 > 连续方案W3初始={mfg_work_init_w3:.1f}"
        )

    def test_单班次不链式不影响结果(self):
        """单班次时行为应与原 calculate() 一致"""
        ctrl = _mk_ctrl_cost("C1")
        mfg = _mk_op("Mfg", [_mk_skill("Mfg", {"all": 0})])
        all_ops = [ctrl, mfg]

        plan = ShiftPlan(
            name="W0",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=["C1"]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=["Mfg"]),
            ],
        )

        reports = _compute_chained_mood_reports([plan], all_ops, shift_hours=12.0)
        assert len(reports) == 1
        assert reports[0].rooms[0].operator_initial.get("Mfg") == pytest.approx(24.0)
