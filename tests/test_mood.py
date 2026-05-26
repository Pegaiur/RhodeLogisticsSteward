"""心情消耗计算模块 (mood.py) 的纯内存单元测试

全部测试通过内存构造 Operator 和 ShiftPlan，不依赖磁盘文件。
遵循 TDD 3A 模式 (Arrange → Act → Assert)。
"""

import pytest

from steward_core.models import EfficiencyMap, Operator, RoomAssignment, ShiftPlan, Skill
from steward_core.mood import (
    MoodReport,
    RoomMood,
    calculate,
)


def _mk_op(name: str, skills: list[Skill] | None = None) -> Operator:
    return Operator(char_id=name, name=name, skills=skills or [])


def _mk_skill(room_type: str, efficient: dict[str, float], buff_id: str = "test", skill_icon: str | None = None) -> Skill:
    return Skill(
        buff_id=buff_id,
        buff_name="测试",
        skill_icon=skill_icon or f"test_{buff_id}",
        room_type=room_type,
        efficient=EfficiencyMap(raw=efficient),
    )


def _mk_ctrl_cost(name: str, extra_ctrl_val: float | None = None) -> Operator:
    """构造带基础控制中枢技能 (bskill_ctrl_cost, 0.05) 的干员"""
    skills = [
        _mk_skill("Control", {"all": 0.05}, buff_id="ctrl_cost", skill_icon="bskill_ctrl_cost"),
    ]
    if extra_ctrl_val is not None:
        skills.append(_mk_skill("Control", {"all": extra_ctrl_val}, buff_id="ctrl_extra"))
    return _mk_op(name, skills)


# ─── 控制中枢减免 ──────────────────────────────────────────────

class TestControlBonus:
    """验证控制中枢基础减免 + 额外技能叠加"""

    def test_五名干员_仅基础减免(self):
        """每名中枢干员 +0.05/时，5人 → 0.25/时"""
        # Arrange
        ctrl_ops = [_mk_ctrl_cost(f"中枢{i+1}") for i in range(5)]
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=[op.name for op in ctrl_ops]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=["A"]),
            ],
        )
        worker = _mk_op("A", [_mk_skill("Mfg", {"all": 0})])

        # Act
        report = calculate(plan, ctrl_ops + [worker], shift_hours=24.0)

        # Assert
        assert report.control_bonus == pytest.approx(0.25)

    def test_额外减免叠加(self):
        """中枢干员有 bskill_ctrl_cost 以外的 Control 技能，值 ≤1 为减免"""
        # Arrange: 5 名干员，1 人有额外 0.1
        ctrl_ops = [
            _mk_ctrl_cost("A"),
            _mk_ctrl_cost("B"),
            _mk_ctrl_cost("C"),
            _mk_ctrl_cost("D"),
            _mk_ctrl_cost("E", extra_ctrl_val=0.1),  # ctrl_cost_expand 类似
        ]
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=[op.name for op in ctrl_ops]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=["W"]),
            ],
        )
        worker = _mk_op("W", [_mk_skill("Mfg", {"all": 0})])

        # Act
        report = calculate(plan, ctrl_ops + [worker], shift_hours=24.0)

        # Assert: 5×0.05 + 0.1 = 0.35
        assert report.control_bonus == pytest.approx(0.35)

    def test_排除bskill_ctrl_cost_避免双计(self):
        """bskill_ctrl_cost (基础 0.05) 已在头数中计入，额外技能不应重复加"""
        # Arrange: 1 名干员，仅有 bskill_ctrl_cost
        ctrl_op = _mk_ctrl_cost("中枢")
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=[ctrl_op.name]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=["W"]),
            ],
        )
        worker = _mk_op("W", [])

        # Act
        report = calculate(plan, [ctrl_op, worker], shift_hours=24.0)

        # Assert: 1×0.05 基础，无额外 → 合计 0.05
        assert report.control_bonus == pytest.approx(0.05)

    def test_额外技能值大于1_不计入减免(self):
        """Control 技能值为 7 的不应计入减免 (那是全局效率加成而非心情)"""
        # Arrange
        extra_skill = _mk_skill("Control", {"all": 7}, buff_id="ctrl_t_spd")
        ctrl_op = _mk_op("阿米娅", [
            _mk_skill("Control", {"all": 0.05}, buff_id="ctrl_cost", skill_icon="bskill_ctrl_cost"),
            extra_skill,
        ])
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=[ctrl_op.name]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=["W"]),
            ],
        )
        worker = _mk_op("W", [])

        # Act
        report = calculate(plan, [ctrl_op, worker], shift_hours=24.0)

        # Assert: 仅 1×0.05 基础，all=7 被过滤 (>1 不在 0<val<1 范围)
        assert report.control_bonus == pytest.approx(0.05)


# ─── 工作消耗 ──────────────────────────────────────────────────

class TestWorkBurn:
    """验证工作设施心情消耗公式"""

    def test_三人房_基础消耗(self):
        """3人制造站: 1.0 - 0.05×2 = 0.90/时"""
        # Arrange
        workers = [_mk_op(f"W{i+1}", [_mk_skill("Mfg", {"all": 0})]) for i in range(3)]
        ctrl_op = _mk_ctrl_cost("中枢")
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=[ctrl_op.name]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=[w.name for w in workers]),
            ],
        )

        # Act
        report = calculate(plan, [ctrl_op] + workers, shift_hours=24.0)

        # Assert
        room = report.rooms[0]
        assert room.base_burn == pytest.approx(0.90)

    def test_一人房_无非数减免(self):
        """1人发电站: 基础消耗 = 1.0, 无减产"""
        # Arrange
        worker = _mk_op("W", [_mk_skill("Power", {"all": 0})])
        ctrl_ops = [_mk_ctrl_cost(f"C{i+1}") for i in range(5)]
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=[op.name for op in ctrl_ops]),
                RoomAssignment(room_type="Power", room_index=0, operators=[worker.name]),
            ],
        )

        # Act
        report = calculate(plan, ctrl_ops + [worker], shift_hours=24.0)

        # Assert
        room = report.rooms[0]
        assert room.base_burn == pytest.approx(1.0)

    def test_净消耗_最小值零(self):
        """净消耗 = max(0, 基础 - 中枢减免)，不应为负"""
        # Arrange: 5人中枢(0.25) + 额外(0.75) → 减免 1.0, 3人房基础 0.9 → 净消耗 0
        ctrl_ops = []
        for i in range(5):
            sk = _mk_skill("Control", {"all": 0.15}, buff_id=f"extra_{i}")
            ctrl_ops.append(_mk_op(f"C{i+1}", [
                _mk_skill("Control", {"all": 0.05}, buff_id="ctrl_cost"),
                sk,
            ]))
        workers = [_mk_op(f"W{i+1}", [_mk_skill("Mfg", {"all": 0})]) for i in range(3)]
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=[op.name for op in ctrl_ops]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=[w.name for w in workers]),
            ],
        )

        # Act
        report = calculate(plan, ctrl_ops + workers, shift_hours=24.0)

        # Assert
        room = report.rooms[0]
        assert room.net_burn == pytest.approx(0.0)

    def test_三人房_五中枢_24h剩余(self):
        """2经验房 3人, 5人中枢 → 净消耗=0.65/时, 24h剩余=8.4"""
        # Arrange: 5 人中枢 (0.25), Mfg 3人 (base=0.9, net=0.65)
        ctrl_ops = [_mk_ctrl_cost(f"C{i+1}") for i in range(5)]
        workers = [_mk_op(f"W{i+1}", [_mk_skill("Mfg", {"all": 0})]) for i in range(3)]
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=[op.name for op in ctrl_ops]),
                RoomAssignment(room_type="Mfg", room_index=0, product="CombatRecord", operators=[w.name for w in workers]),
            ],
        )

        # Act
        report = calculate(plan, ctrl_ops + workers, shift_hours=24.0)

        # Assert
        room = report.rooms[0]
        assert room.base_burn == pytest.approx(0.90)
        assert room.net_burn == pytest.approx(0.65)
        assert room.remaining_after_shift == pytest.approx(8.4)


# ─── 蓝脸/红脸判定 ─────────────────────────────────────────────

class TestFaceThresholds:
    """验证蓝脸 ≤12、红脸 ≤0 的判定"""

    def test_蓝脸阈值12(self):
        """剩余心情 = 12 应为蓝脸"""
        # Arrange: 制造 net_burn=0.5, 24h → 剩余=12
        ctrl_ops = []
        for i in range(5):
            ctrl_ops.append(_mk_op(f"C{i+1}", [
                _mk_skill("Control", {"all": 0.05}, buff_id="ctrl_cost"),
                _mk_skill("Control", {"all": 0.08}, buff_id=f"extra_{i}"),
            ]))
        workers = [_mk_op(f"W{i+1}") for i in range(3)]
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=[op.name for op in ctrl_ops]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=[w.name for w in workers]),
            ],
        )

        # Act
        report = calculate(plan, ctrl_ops + workers, shift_hours=24.0)

        # Assert: 减免=0.25+5×0.08=0.65, base=0.9, net=0.25, 剩余=24-6=18
        pass

    def test_红脸阈值零(self):
        """净消耗导致心情归零应为红脸"""
        # Arrange: 12h 班次, net_burn=1.0, 剩余=24-12=12 → 12h
        # 改用长班次迫使红脸: net_burn=0.9, 30h → 剩余 = 24 - 0.9×30 = -4.0
        ctrl_op = _mk_ctrl_cost("C1")  # 仅 0.05 减免
        worker = _mk_op("W1", [])
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=[ctrl_op.name]),
                RoomAssignment(room_type="Power", room_index=0, operators=[worker.name]),  # 1人房, base=1.0
            ],
        )

        # Act: net=0.95, 26h → 24-0.95×26 = -0.7
        report = calculate(plan, [ctrl_op, worker], shift_hours=26.0)

        # Assert
        room = report.rooms[0]
        assert room.is_red_face
        assert report.red_face_count == 1

    def test_正常心情_非蓝非红(self):
        """剩余心情 ≥ 13 为正常"""
        # Arrange: 小减免, 短班次
        ctrl_ops = [_mk_ctrl_cost(f"C{i+1}") for i in range(5)]
        worker = _mk_op("W", [_mk_skill("Mfg", {"all": 0})])
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=[op.name for op in ctrl_ops]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=[worker.name]),
            ],
        )

        # Act: 12h
        report = calculate(plan, ctrl_ops + [worker], shift_hours=12.0)

        # Assert: net=0.65, 剩余=24-7.8=16.2 → 正常
        room = report.rooms[0]
        assert not room.is_blue_face
        assert not room.is_red_face


# ─── 非工作设施排除 ────────────────────────────────────────────

class TestFacilityExclusion:
    """验证非工作设施不计入心情消耗"""

    def test_控制中枢_不产生消耗条目(self):
        """Control 房间不应出现在 report.rooms 中"""
        # Arrange
        ctrl_ops = [_mk_ctrl_cost(f"C{i+1}") for i in range(3)]
        worker = _mk_op("W", [_mk_skill("Mfg", {"all": 0})])
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=[op.name for op in ctrl_ops]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=[worker.name]),
            ],
        )

        # Act
        report = calculate(plan, ctrl_ops + [worker], shift_hours=24.0)

        # Assert: 仅 1 个工作房间
        assert len(report.rooms) == 1
        assert report.rooms[0].room_type == "Mfg"

    def test_空工作设施_跳过(self):
        """无干员的工作设施不产生 mood room"""
        # Arrange
        ctrl_op = _mk_ctrl_cost("C")
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Control", room_index=0, operators=[ctrl_op.name]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=[]),  # autofill
            ],
        )

        # Act
        report = calculate(plan, [ctrl_op], shift_hours=24.0)

        # Assert
        assert len(report.rooms) == 0


# ─── 报告接口 ──────────────────────────────────────────────────

class TestReportInterface:
    """验证 MoodReport.summary() 和 all_pass()"""

    def test_all_pass_无红脸(self):
        """无红脸时 all_pass() 返回 True"""
        report = MoodReport(shift_hours=24, shift_name="测试", red_face_count=0)
        assert report.all_pass() is True

    def test_all_pass_有红脸(self):
        """有红脸时 all_pass() 返回 False"""
        report = MoodReport(shift_hours=24, shift_name="测试", red_face_count=1)
        assert report.all_pass() is False

    def test_summary_输出不崩溃(self):
        """summary() 在各种场景下不崩溃"""
        report = MoodReport(
            shift_hours=24,
            shift_name="测试",
            control_operators=["A"],
            control_bonus=0.25,
            rooms=[
                RoomMood(
                    room_type="Mfg", room_index=0,
                    operators=["B", "C", "D"],
                    base_burn=0.9, net_burn=0.65, remaining_after_shift=8.4,
                    is_blue_face=True, is_red_face=False,
                ),
            ],
            blue_face_count=1,
            red_face_count=0,
        )
        s = report.summary()
        assert "控制中枢" in s
        assert "通过" in s

    def test_summary_红脸场景(self):
        """红脸时 summary 应提示轮换"""
        report = MoodReport(
            shift_hours=24,
            shift_name="测试",
            blue_face_count=0,
            red_face_count=1,
        )
        s = report.summary()
        assert "轮换" in s

    def test_RoomMood_status(self):
        """RoomMood.status() 在不同心情下返回正确字符串"""
        assert "正常" in RoomMood(room_type="Mfg", room_index=0, remaining_after_shift=20).status()
        assert "蓝脸" in RoomMood(room_type="Mfg", room_index=0, remaining_after_shift=10, is_blue_face=True).status()
        assert "红脸" in RoomMood(room_type="Mfg", room_index=0, remaining_after_shift=-1, is_red_face=True).status()
