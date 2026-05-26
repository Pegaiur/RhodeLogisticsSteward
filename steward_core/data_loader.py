"""数据加载模块

加载 building_data.json（干员→技能映射）和 infrast.json（技能→效率值），
交叉引用后产出可用于排班求解的 Operator 列表。

Step 1 全 box 满练度：不按 phase 过滤，所有技能均可用。
Step 4 真实练度：由求解器根据玩家 elite 等级过滤 skills。
"""

import json
from pathlib import Path
from typing import Optional

from steward_core.models import EfficiencyMap, Operator, Skill

# building_data.json 中的 roomType 到 infrast.json 中设施键的映射
ROOM_TYPE_MAP: dict[str, str] = {
    "CONTROL": "Control",
    "TRADING": "Trade",
    "MANUFACTURE": "Mfg",
    "POWER": "Power",
    "MEETING": "Reception",
    "HIRE": "Office",
    "DORMITORY": "Dormitory",
}

# infrast.json 中的设施键列表（所有可能包含技能定义的设施）
_INFRA_FACILITIES = ["Control", "Mfg", "Trade", "Power", "Reception", "Office", "Dormitory"]

# PHASE 字符串到数值的映射
PHASE_MAP: dict[str, int] = {
    "PHASE_0": 0,
    "PHASE_1": 1,
    "PHASE_2": 2,
}


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_efficiency_index(infrast: dict) -> dict[str, EfficiencyMap]:
    """从 infrast.json 构建 skillIcon → EfficiencyMap 的索引"""
    index: dict[str, EfficiencyMap] = {}
    for facility_key in _INFRA_FACILITIES:
        facility_data = infrast.get(facility_key, {})
        skills = facility_data.get("skills", {})
        for skill_icon, skill_data in skills.items():
            efficient_raw = skill_data.get("efficient", {})
            if efficient_raw:
                index[skill_icon] = EfficiencyMap(raw=dict(efficient_raw))
    return index


def load_operators(
    building_data_path: Path,
    infrast_path: Path,
    name_lookup: Optional[dict[str, str]] = None,
) -> list[Operator]:
    """加载全量干员数据

    遍历 building_data.json 中所有干员，展开 buffChar → buffData，
    通过 buffId 查询 roomType / skillIcon，再通过 skillIcon 查询效率值。
    所有技能均保留原始 phase 值，由求解器按需过滤。

    Args:
        building_data_path: building_data.json 路径
        infrast_path: infrast.json 路径
        name_lookup: char_id → 中文名 的可选映射，不提供时用 char_id 作为名称

    Returns:
        全量 Operator 列表，每人含已解析效率值的 Skill 列表
    """
    building = _load_json(building_data_path)
    infrast = _load_json(infrast_path)

    eff_index = _build_efficiency_index(infrast)
    chars = building.get("chars", {})
    buffs = building.get("buffs", {})

    if name_lookup is None:
        name_lookup = {}

    operators: list[Operator] = []

    for char_id, char_data in chars.items():
        name = name_lookup.get(char_id, char_id)
        rarity = char_data.get("rarity", 0)
        op = Operator(char_id=char_id, name=name, rarity=rarity)

        for buff_char in char_data.get("buffChar", []):
            for buff_data in buff_char.get("buffData", []):
                buff_id = buff_data.get("buffId", "")
                if not buff_id:
                    continue

                phase_str = buff_data.get("cond", {}).get("phase", "PHASE_0")
                phase = PHASE_MAP.get(phase_str, 0)

                buff_info = buffs.get(buff_id, {})
                room_type_raw = buff_info.get("roomType", "")
                room_type = ROOM_TYPE_MAP.get(room_type_raw, "")
                skill_icon = buff_info.get("skillIcon", "")
                buff_name = buff_info.get("buffName", buff_id)

                if not room_type:
                    continue

                efficient = eff_index.get(skill_icon)
                if efficient is None:
                    continue

                skill = Skill(
                    buff_id=buff_id,
                    buff_name=buff_name,
                    skill_icon=skill_icon,
                    room_type=room_type,
                    efficient=efficient,
                    phase=phase,
                )
                op.skills.append(skill)

        operators.append(op)

    return operators
