"""测试辅助函数

提供统一的 Operator / Skill 构造器，消除各测试模块间的重复定义。
所有函数通过内存构造，不依赖磁盘文件。
"""

from steward_core.models import EfficiencyMap, Operator, Skill


def mk_op(name: str = "测试",
          skills: list[Skill] | None = None,
          group_id: str | None = None,
          nation_id: str | None = None,
          team_id: str | None = None) -> Operator:
    """构造测试用 Operator（含完整身份字段）"""
    return Operator(
        char_id=name, name=name, skills=skills or [],
        group_id=group_id, nation_id=nation_id, team_id=team_id,
    )


def dummy_op(char_id: str, name: str) -> Operator:
    """构造无技能的桩干员（仅身份赋值用）"""
    return Operator(char_id=char_id, name=name, skills=[])


def mk_skill(buff_id: str,
             room_type: str,
             buff_name: str = "测试技能",
             efficient: dict[str, float] | None = None,
             capacity: int = 0) -> Skill:
    """构造测试用 Skill（含 capacity_bonus 字段）"""
    return Skill(
        buff_id=buff_id,
        buff_name=buff_name,
        skill_icon=buff_id,
        room_type=room_type,
        efficient=EfficiencyMap(raw=efficient or {"all": 0.0}),
        capacity_bonus=capacity,
    )


def mk_simple_skill(room_type: str,
                    efficiency: float,
                    buff_id: str = "test",
                    buff_name: str = "") -> Skill:
    """构造简洁 Skill：仅需 room_type + efficiency

    用于 solver 风格测试，无需指定 efficient dict 结构。
    """
    return Skill(
        buff_id=buff_id,
        buff_name=buff_name or f"技能_{buff_id}",
        skill_icon=buff_id,
        room_type=room_type,
        efficient=EfficiencyMap(raw={"all": efficiency}),
    )

