"""心情报告数据类 (MoodReport / RoomMood) 的接口验证测试

验证纯数据类接口（直接构造实例，不调用 calculate()），不涉及心情计算逻辑。
"""

from steward_core.mood import MoodReport, RoomMood


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
                    is_red_face=False,
                ),
            ],
            red_face_count=0,
        )
        s = report.summary()
        assert "中枢" in s
        assert "OK" in s

    def test_summary_红脸场景(self):
        """红脸时 summary 应显示 ! 标记"""
        report = MoodReport(
            shift_hours=24,
            shift_name="测试",
            red_face_count=1,
            rooms=[
                RoomMood(
                    room_type="Mfg", room_index=0,
                    operators=["B"],
                    net_burn=0.65, remaining_after_shift=-1,
                    is_red_face=True,
                ),
            ],
        )
        s = report.summary()
        assert "!" in s

    def test_RoomMood_status(self):
        """RoomMood.status() 在不同心情下返回正确字符串"""
        assert "正常" in RoomMood(room_type="Mfg", room_index=0, remaining_after_shift=20).status()
        assert "红脸" in RoomMood(room_type="Mfg", room_index=0, remaining_after_shift=-1, is_red_face=True).status()
