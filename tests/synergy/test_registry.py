"""registry 模块单元测试 — SystemContributor / ROSEMARY_SUPPORT 注册表"""

import importlib
import pkgutil

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


# ─── TABLES 注册器一致性检查 ──────────────────────────────────────


class TestTablesRegistryConsistency:
    """确保所有硬编码 dict 表都在 TABLES 注册器中登记"""

    def test_全部_TABLE_字典已在TABLES注册(self):
        """扫描 synergy 包中所有 _TABLE 结尾的 dict 变量，确认全部在 TABLES 中注册"""
        import steward_core.synergy as synergy_pkg

        from steward_core.synergy import TABLES

        registered_ids = {id(m.table) for m in TABLES.values()}
        unregistered = {}

        for _, mod_name, _ in pkgutil.walk_packages(
            synergy_pkg.__path__, prefix="steward_core.synergy."
        ):
            if mod_name == "steward_core.synergy.types":
                continue
            mod = importlib.import_module(mod_name)
            for attr_name in dir(mod):
                if not attr_name.endswith("_TABLE"):
                    continue
                obj = getattr(mod, attr_name)
                if not isinstance(obj, dict):
                    continue
                if id(obj) not in registered_ids:
                    unregistered[f"{mod_name}.{attr_name}"] = type(obj).__name__

        assert not unregistered, (
            f"以下 _TABLE 字典未在 TABLES 注册器中登记:\n"
            + "\n".join(f"  {k}" for k in unregistered)
            + "\n请同步更新 synergy/types.py 中的 TABLES 字典。"
        )
