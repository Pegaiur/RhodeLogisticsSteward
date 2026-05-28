"""facility_linkages 模块单元测试 — 设施数量联动 (A6)"""

import pytest

from steward_core.models import EfficiencyMap, LayoutConfig, LinearSegment, Operator, RoomConfig, Skill


def _mk_op(name: str = "测试", skills: list[Skill] | None = None,
           group_id: str | None = None, nation_id: str | None = None,
           team_id: str | None = None) -> Operator:
    return Operator(char_id=name, name=name, skills=skills or [],
                    group_id=group_id, nation_id=nation_id, team_id=team_id)


def _mk_skill(buff_id: str, room_type: str, buff_name: str = "测试技能",
              efficient: dict[str, float] | None = None,
              capacity: int = 0) -> Skill:
    return Skill(
        buff_id=buff_id,
        buff_name=buff_name,
        skill_icon=buff_id,
        room_type=room_type,
        efficient=EfficiencyMap(raw=efficient or {"all": 0.0}),
        capacity_bonus=capacity,
    )


# ─── A6 设施数量联动 ─────────────────────────────────────────────

class TestSynergyFacilityCount:
    """A6: synergy_facility_count — 根据全基建设施数量计算加成"""

    def test_清流_每个贸易站加20贵金属(self):
        """清流在 Mfg PureGold，2 个贸易站 → +40%"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig, RoomConfig

        # Arrange
        qingliu = _mk_op("清流")
        layout = LayoutConfig(rooms=[
            RoomConfig("Trade", 0, 3, "Money"),
            RoomConfig("Trade", 1, 3, "Money"),
        ])

        # Act
        segs = synergy_facility_count([qingliu], "Mfg", "PureGold", layout, T=12.0)

        # Assert: +40% 常数段
        assert len(segs) == 1
        assert segs[0].a == 40.0

    def test_清流_非贵金属产物_不触发(self):
        """清流在 CombatRecord → 不应触发（仅贵金属）"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig, RoomConfig

        # Arrange
        qingliu = _mk_op("清流")
        layout = LayoutConfig(rooms=[
            RoomConfig("Trade", 0, 3, "Money"),
            RoomConfig("Trade", 1, 3, "Money"),
        ])

        # Act
        segs = synergy_facility_count([qingliu], "Mfg", "CombatRecord", layout, T=12.0)

        # Assert
        assert segs == []

    def test_空弦_每宿舍等级加2贸易(self):
        """空弦 (β) 在 Trade，4 间宿舍 × Lv5 → +40%"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig

        # Arrange
        kongxian = _mk_op("空弦")
        layout = LayoutConfig(rooms=[])

        # Act: dorm_levels 默认 20 (4×Lv5)
        segs = synergy_facility_count([kongxian], "Trade", "Money", layout, T=12.0)

        # Assert: +40%
        assert len(segs) == 1
        assert segs[0].a == 40.0

    def test_伺夜_每会客室等级加5_上限40(self):
        """伺夜在 Trade，Meeting Lv3 → +15%（未触上限）"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig, RoomConfig

        # Arrange
        siye = _mk_op("伺夜")
        layout = LayoutConfig(rooms=[
            RoomConfig("Reception", 0, 2, "General"),
        ])

        # Act: 1间 Reception × Lv3 = 3 × 5% = 15%
        segs = synergy_facility_count([siye], "Trade", "Money", layout, T=12.0)

        # Assert
        assert len(segs) == 1
        assert segs[0].a == 15.0

    def test_伺夜_高会客室触发上限(self):
        """伺夜在 Trade，Meeting Lv9 → 45% → clamp 到 40%"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig, RoomConfig

        # Arrange
        siye = _mk_op("伺夜")
        layout = LayoutConfig(rooms=[
            RoomConfig("Reception", 0, 2, "General"),
            RoomConfig("Reception", 1, 2, "General"),
            RoomConfig("Reception", 2, 2, "General"),
        ])

        # Act: 3间 Meeting × Lv3 = 9 × 5% = 45% → clamp to 40%
        segs = synergy_facility_count([siye], "Trade", "Money", layout, T=12.0)

        # Assert
        assert segs[0].a == 40.0

    def test_石英_每配方类型加2贸易(self):
        """石英在 Trade，制造站 2 种配方 → +4%"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig, RoomConfig

        # Arrange
        shiying = _mk_op("石英")
        layout = LayoutConfig(rooms=[
            RoomConfig("Mfg", 0, 3, "CombatRecord"),
            RoomConfig("Mfg", 1, 3, "PureGold"),
        ])

        # Act: 2 种配方类型 × 2% = 4%
        segs = synergy_facility_count([shiying], "Trade", "Money", layout, T=12.0)

        # Assert
        assert len(segs) == 1
        assert segs[0].a == 4.0

    def test_无A6干员_返回空(self):
        """房间内无 A6 干员 → 空列表"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig

        # Arrange
        filler = _mk_op("填位")
        layout = LayoutConfig(rooms=[])

        # Act
        segs = synergy_facility_count([filler], "Mfg", "PureGold", layout, T=12.0)

        # Assert
        assert segs == []

    def test_娜仁图亚_赤金加宿舍等级(self):
        """娜仁图亚在 Mfg PureGold，20 宿舍等级 → +20%"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig

        # Arrange
        narentuya = _mk_op("娜仁图亚")
        layout = LayoutConfig(rooms=[])

        # Act: dorm_levels 默认 20 (4×Lv5)
        segs = synergy_facility_count([narentuya], "Mfg", "PureGold", layout, T=12.0)

        # Assert: +20%
        assert len(segs) == 1
        assert segs[0].a == 20.0


# ─── A6 扩展：手艺人 ───────────────────────────────────────────────

class TestTrainingRoomA6:
    """A6 扩展: synergy_facility_count — 训练室等级联动"""

    def test_手艺人_训练室Lv3_加30percent(self):
        """维伊在 Mfg，1间 Lv3 训练室 → +30%"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig, RoomConfig

        weiyi = _mk_op("维伊")
        layout = LayoutConfig(rooms=[
            RoomConfig("Training", 0, 1),
        ])

        segs = synergy_facility_count([weiyi], "Mfg", "PureGold", layout, T=12.0)
        assert len(segs) == 1
        assert segs[0].a == 30.0  # 3级 × 10% = 30%

    def test_手艺人_触发上限30(self):
        """维伊在 Mfg，2间 Lv3 训练室 → 受上限 30% 限制"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig, RoomConfig

        weiyi = _mk_op("维伊")
        layout = LayoutConfig(rooms=[
            RoomConfig("Training", 0, 1),
            RoomConfig("Training", 1, 1),
        ])

        segs = synergy_facility_count([weiyi], "Mfg", "PureGold", layout, T=12.0)
        assert len(segs) == 1
        assert segs[0].a == 30.0  # 6级 × 10% = 60% → clamp 30%
