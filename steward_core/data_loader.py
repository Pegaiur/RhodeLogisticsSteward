"""数据加载模块

从 character_identity.json + buffs_infrastructure.json 加载干员与技能数据，
产出可用于排班求解的 Operator 列表。

与旧版 data_loader 的区别：
- 数据源：character_identity.json (替代 building_data.json) + buffs_infrastructure.json (替代 infrast.json)
- 效率值：buffs_infrastructure.json 的 efficiency 字段 (float)，通过 targets 结构化字段判定产物匹配
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

_DORM_EFF_RE = re.compile(r"<@cc\.vup>\+(\d+\.?\d*)</>")
"""从 DORMITORY buff 描述文本中提取心情恢复效率值（/h）

MAA 的 infrast.json 不包含宿舍非生产技能，buffs_infrastructure.json 中 efficiency 恒为 0。
常量恢复 buff 的效率值嵌入在描述文本的 <@cc.vup>+X.X</> 标记中，
本正则匹配该标记并提取数值。
仅适用于纯常量 buff（dorm_rec_all / dorm_rec_single / dorm_rec_oneself），
混合型和条件型 buff 需在后续单独处理。
"""


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_MFG_TARGETS_MAP: dict[frozenset[str], str] = {
    frozenset({"F_GOLD"}): "PureGold",
    frozenset({"F_EXP"}): "CombatRecord",
    frozenset({"F_DIAMOND"}): "OriginStone",
}


def _mfg_product_from_targets(targets: list[str]) -> Optional[str]:
    """根据 buff targets 结构化字段判定制造站产物类型

    仅适用于 roomType=MANUFACTURE。
    targets 为 ["F_GOLD","F_EXP","F_DIAMOND"] 或 [] 时返回 None（通用技能）。
    注意：前提假设 targets 不存在双产品组合（如仅 F_GOLD+F_EXP），
    当前 109 条 Mfg buff 均符合此模式。若未来游戏新增双产品 buff，
    需在 _MFG_TARGETS_MAP 中追加对应映射。
    """
    return _MFG_TARGETS_MAP.get(frozenset(targets))


def _parse_dorm_efficiency(description: str) -> float:
    """从 DORMITORY buff 描述中提取常量恢复效率值

    匹配 <@cc.vup>+X.X</> 模式，提取 X.X 作为恢复值 (/h)。
    仅适用于纯常量 buff，不处理多值/条件型。
    无匹配时返回 0.0。
    """
    m = _DORM_EFF_RE.search(description)
    if m:
        return float(m.group(1))
    return 0.0


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
        sub_group_ids = frozenset(
            sp.get("groupId") for sp in char_data.get("subPower", [])
            if sp.get("groupId")
        )
        sub_nation_ids = frozenset(
            sp.get("nationId") for sp in char_data.get("subPower", [])
            if sp.get("nationId")
        )
        sub_team_ids = frozenset(
            sp.get("teamId") for sp in char_data.get("subPower", [])
            if sp.get("teamId")
        )

        if rarity <= 1:
            elite_phase = 0
        elif rarity == 2:
            elite_phase = 1
        else:
            elite_phase = 2

        op = Operator(
            char_id=char_id,
            name=name,
            rarity=rarity,
            elite_phase=elite_phase,
            group_id=group_id,
            nation_id=nation_id,
            team_id=team_id,
            sub_group_ids=sub_group_ids,
            sub_nation_ids=sub_nation_ids,
            sub_team_ids=sub_team_ids,
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

            # ─── DORMITORY buff 效率值从描述文本提取 ──────────────────
            # MAA infrast.json 不包含宿舍非生产技能，buffs_infrastructure.json
            # 中 efficiency 恒为 0。纯常量恢复 buff 的效率值从描述标记
            # <@cc.vup>+X.X</> 中提取。覆盖 dorm_rec_all / dorm_rec_single /
            # dorm_rec_oneself 三类白名单前缀。
            #
            # TODO: 以下 DORM buff 尚未从描述提取效率，待后续实现:
            #
            # === 双值混合型 (17 条, 含自身+他人双值) ===
            #   dorm_rec_all&oneself[000/001/010/011/012/021/022/042]
            #   dorm_rec_single&oneself[000~040]
            #   dorm_rec_oneself2[000/001]
            #
            # === 条件型: 依赖基地全局状态 (8 条) ===
            #   dorm_rec_all&profession[000]  奶羊  每名行医+0.06
            #   dorm_rec_all&tag[000]         森西  莱欧斯小队额外加成
            #   dorm_rec_all&group[000]       余   每名岁+0.06
            #   dorm_rec_all&bd[000]          塑心  每5共鸣+0.01
            #   dorm_rec_all&unfull[000/001]  波卜  基础+不满人数加成
            #   dorm_rec_all&tired[000/100]   刺玫/撷英  低心情条件加成
            #
            # === 条件型: 依赖设施数量 (7 条) ===
            #   dorm_rec_all&lv[000/100]      响石  等级加成
            #   dorm_hireToRecAll[000/001/021] 斥罪/隐德来希  招募位加成
            #   dorm_powToRecAll[000/010]     流明  发电站加成
            #
            # === 条件型: 指名目标加成 (6 条) ===
            #   dorm_rec_single_P[000/001/002] 黑/特米米/深靛  指名目标加成
            #   dorm_rec_single_power[000/001/100] 寒檀/新约能天使  阵营目标加成
            #
            # === 分布式 / 特殊机制 (3 条) ===
            #   dorm_rec_all&single[000]  冰酿  总+0.8 分配型
            #   dorm_exchangeAp[000]      菲亚梅塔  心情互换
            #   dorm_rec_toone[000]       摩根  特定干员加成
            #
            # === 状态生产型 (5 条, 不经过 dorm_recovery, 通过 contribution Part 1) ===
            #   dorm_bd_num[000]              塑心  每室友+1 无声共鸣
            #   dorm_rec_bd_dungeon[000]      森西  每级+1 魔物料理
            #   dorm_rec_bd_n1[000/100]       爱丽丝/车尔尼  梦境/小节→感知信息
            #   dorm_rec_bd_n1_n2[000]        爱丽丝  梦境产生+恢复0.1
            #   dorm_rec_bd_n1_n3[000]        车尔尼  小节产生+单体恢复0.65
            if (
                room_type == "Dormitory"
                and efficiency == 0.0
                and buff_id.startswith(
                    ("dorm_rec_all[", "dorm_rec_single[", "dorm_rec_oneself[")
                )
            ):
                efficiency = _parse_dorm_efficiency(description)

            if room_type == "Trade":
                efficient = EfficiencyMap(raw={"Money": efficiency})
            elif room_type == "Mfg":
                targets = buff.get("targets", [])
                product = _mfg_product_from_targets(targets)
                if product:
                    efficient = EfficiencyMap(raw={product: efficiency})
                else:
                    efficient = EfficiencyMap(raw={"all": efficiency})
            else:
                efficient = EfficiencyMap(raw={"all": efficiency})

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
