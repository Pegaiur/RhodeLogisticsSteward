"""系统贡献者注册表"""

from dataclasses import dataclass

from steward_core.models import Operator


@dataclass
class SystemContributor:
    """个人效率为0但对排班系统有非零贡献的干员"""
    name: str
    facility_types: list[str]      # 贡献的目标设施
    contribution_type: str          # "global_bonus" | "b_generator" | "facility_modifier" | "anchor"


_SYSTEM_CONTRIBUTORS: list[SystemContributor] = [
    # 中枢全局加成（C1）
    SystemContributor("凯尔希", ["Control"], "global_bonus"),
    SystemContributor("灵知", ["Control"], "global_bonus"),
    # 宿舍 B 层生成者（B1 感知/B4 魔物料理/B5 无声共鸣）
    SystemContributor("森西", ["Dormitory"], "b_generator"),
    SystemContributor("爱丽丝", ["Dormitory"], "b_generator"),
    SystemContributor("车尔尼", ["Dormitory"], "b_generator"),
    SystemContributor("塑心", ["Dormitory"], "b_generator"),
    # 发电站设施数量修改器
    SystemContributor("承曦格雷伊", ["Power"], "facility_modifier"),
    # 制造站联动锚点（A1/A3/A5）
    SystemContributor("水月", ["Mfg"], "anchor"),
    SystemContributor("多萝西", ["Mfg"], "anchor"),
    SystemContributor("苍苔", ["Mfg"], "anchor"),
    SystemContributor("海沫", ["Mfg"], "anchor"),
    SystemContributor("森蚺", ["Mfg"], "anchor"),
    SystemContributor("温蒂", ["Mfg"], "anchor"),
    SystemContributor("掠风", ["Mfg"], "anchor"),
    SystemContributor("异客", ["Mfg"], "anchor"),
    SystemContributor("阿兰娜", ["Mfg"], "anchor"),
    SystemContributor("Miss.Christine", ["Mfg"], "anchor"),
    SystemContributor("怒潮凛冬", ["Mfg"], "anchor"),
    # 贸易站联动锚点（A7 反馈型 + 配对型）
    SystemContributor("巫恋", ["Trade"], "anchor"),
    SystemContributor("火哨", ["Trade"], "anchor"),
    SystemContributor("吉星", ["Trade"], "anchor"),
    SystemContributor("雪雉", ["Trade"], "anchor"),
    SystemContributor("德克萨斯", ["Trade"], "anchor"),
    SystemContributor("摩根", ["Trade"], "anchor"),
    SystemContributor("新约能天使", ["Trade"], "anchor"),
]


def get_system_contributors(
    facility: str,
    contribution_type: str | None = None,
) -> list[str]:
    """获取指定设施的系统贡献者名称列表"""
    result: list[str] = []
    for c in _SYSTEM_CONTRIBUTORS:
        if facility in c.facility_types:
            if contribution_type is None or c.contribution_type == contribution_type:
                result.append(c.name)
    return result
