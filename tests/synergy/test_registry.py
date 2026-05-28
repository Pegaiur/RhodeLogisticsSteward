"""registry 模块单元测试 — SystemContributor / ROSEMARY_SUPPORT 注册表"""

import pytest

from steward_core.models import EfficiencyMap, LinearSegment, Operator, Skill


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


# ─── ROSEMARY_SUPPORT 扩展 ────────────────────────────────────────

class TestRosemarySupportExtension:
    """ROSEMARY_SUPPORT: 办公室支撑干员注册"""

    def test_rosemary_support_含office键(self):
        """ROSEMARY_SUPPORT 应包含 'Office' 键"""
        from steward_core.synergy import ROSEMARY_SUPPORT

        assert "Office" in ROSEMARY_SUPPORT
        assert ROSEMARY_SUPPORT["Office"] == ["絮雨"]

    def test_rosemary_support_含塑心(self):
        """ROSEMARY_SUPPORT['Dormitory'] 应包含塑心（B5无声共鸣生成者）"""
        from steward_core.synergy import ROSEMARY_SUPPORT

        assert "塑心" in ROSEMARY_SUPPORT["Dormitory"]
