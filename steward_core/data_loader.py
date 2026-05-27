"""数据加载模块

从 character_identity.json + buffs_infrastructure.json 加载干员与技能数据，
产出可用于排班求解的 Operator 列表。

与旧版 data_loader 的区别：
- 数据源：character_identity.json (替代 building_data.json) + buffs_infrastructure.json (替代 infrast.json)
- 效率值：buffs_infrastructure.json 的 efficiency 字段 (float)，通过 description 文本判定产物匹配
- 身份字段：nationId/groupId/teamId → nation_id/group_id/team_id
"""

import json
import re
from pathlib import Path
from typing import Optional

from steward_core.models import EfficiencyMap, Operator, Skill

ROOM_TYPE_MAP: dict[str, str] = {
    "CONTROL": "Control",
    "TRADING": "Trade",
    "MANUFACTURE": "Mfg",
    "POWER": "Power",
    "MEETING": "Reception",
    "HIRE": "Office",
    "DORMITORY": "Dormitory",
}

FACILITY_TYPES = {v for v in ROOM_TYPE_MAP.values()}

_CAPACITY_RE = re.compile(r"仓库容量上限\+(\d+)")


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _determine_product(description: str) -> Optional[str]:
    """根据 buff description 文本判定产物类型

    返回 'CombatRecord', 'PureGold', 'OriginStone', 或 None (通用技能)。
    注意：源石类配方（F_DIAMOND）与贵金属/作战记录互斥，必须单独排除，
    否则会被误判为通用技能导致跨产物生效。
    """
    desc = description
    has_record = "作战记录" in desc
    has_gold = "贵金属" in desc or "赤金" in desc
    has_originium = "源石" in desc

    if has_originium:
        return "OriginStone"
    if has_record and not has_gold:
        return "CombatRecord"
    if has_gold and not has_record:
        return "PureGold"
    return None


def _build_efficiency_map(efficiency: float, product: Optional[str]) -> EfficiencyMap:
    """将 buffs_infrastructure 的 efficiency 字段转换为 EfficiencyMap

    产物匹配逻辑：
    - 纯作战记录技能: EfficiencyMap({"CombatRecord": efficiency})
    - 纯贵金属技能: EfficiencyMap({"PureGold": efficiency})
    - 通用技能: EfficiencyMap({"all": efficiency})
    - efficiency=0 的条件技能: EfficiencyMap({"all": 0.0})
    """
    if product == "CombatRecord":
        return EfficiencyMap(raw={"CombatRecord": efficiency})
    elif product == "PureGold":
        return EfficiencyMap(raw={"PureGold": efficiency})
    elif product == "OriginStone":
        return EfficiencyMap(raw={"OriginStone": efficiency})
    else:
        return EfficiencyMap(raw={"all": efficiency})


def load_operators_v2(
    character_identity_path: Path,
    buffs_infrastructure_path: Path,
) -> list[Operator]:
    """从 character_identity.json + buffs_infrastructure.json 加载全量干员

    Args:
        character_identity_path: character_identity.json 路径
        buffs_infrastructure_path: buffs_infrastructure.json 路径

    Returns:
        全量 Operator 列表，每人含已解析效率值的 Skill 列表
    """
    ci = _load_json(character_identity_path)
    bi = _load_json(buffs_infrastructure_path)

    operators: list[Operator] = []

    for char_id, char_data in ci.items():
        name = char_data.get("name", char_id)
        rarity = char_data.get("rarity", 0)
        nation_id = char_data.get("nationId") or None
        group_id = char_data.get("groupId") or None
        team_id = char_data.get("teamId") or None

        op = Operator(
            char_id=char_id,
            name=name,
            rarity=rarity,
            group_id=group_id,
            nation_id=nation_id,
            team_id=team_id,
        )

        for sk_data in char_data.get("skills", []):
            buff_id = sk_data.get("buffId", "")
            if not buff_id or buff_id not in bi:
                continue

            buff = bi[buff_id]
            room_type_raw = buff.get("roomType", "")
            room_type = ROOM_TYPE_MAP.get(room_type_raw, "")

            if room_type not in FACILITY_TYPES:
                continue

            efficiency = buff.get("efficiency", 0.0)
            description = buff.get("description", "")
            buff_name = buff.get("buffName", buff_id)
            phase = sk_data.get("phase", 0)

            product = _determine_product(description)
            efficient = _build_efficiency_map(efficiency, product)

            capacity = 0
            m = _CAPACITY_RE.search(description)
            if m:
                capacity = int(m.group(1))

            skill = Skill(
                buff_id=buff_id,
                buff_name=buff_name,
                skill_icon=buff_id,
                room_type=room_type,
                efficient=efficient,
                phase=phase,
                capacity_bonus=capacity,
            )
            op.skills.append(skill)

        operators.append(op)

    return operators


# ─── 旧版兼容层（供 run_solver.py 等存量代码使用，MV4 后移除） ───

# 旧版 infrast.json 设施键列表
_LEGACY_INFRA_FACILITIES = ["Control", "Mfg", "Trade", "Power", "Reception", "Office", "Dormitory"]

_LEGACY_PHASE_MAP: dict[str, int] = {
    "PHASE_0": 0,
    "PHASE_1": 1,
    "PHASE_2": 2,
}


def _legacy_build_efficiency_index(infrast: dict) -> dict[str, EfficiencyMap]:
    """从 infrast.json 构建 skillIcon → EfficiencyMap 的索引"""
    index: dict[str, EfficiencyMap] = {}
    for facility_key in _LEGACY_INFRA_FACILITIES:
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
    """加载全量干员数据 (旧版 API，兼容 building_data.json + infrast.json)

    遍历 building_data.json 中所有干员，展开 buffChar → buffData，
    通过 buffId 查询 roomType / skillIcon，再通过 skillIcon 查询效率值。

    此函数为旧版兼容层，MV4 将迁移到 load_operators_v2 后移除。
    """
    building = _load_json(building_data_path)
    infrast = _load_json(infrast_path)

    eff_index = _legacy_build_efficiency_index(infrast)
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
                phase = _LEGACY_PHASE_MAP.get(phase_str, 0)

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
