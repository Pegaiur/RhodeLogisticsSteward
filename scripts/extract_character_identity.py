"""从 character_table.json + building_data.json 提取干员身份与基建技能

50万行原始数据 → 精炼 JSON，包含身份字段和基建技能，供排班求解器使用。
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_CHAR = PROJECT_ROOT / "character_table.json"
SOURCE_BUILD = PROJECT_ROOT / "building_data.json"
TARGET = PROJECT_ROOT / "character_identity.json"

RARITY_MAP: dict[str, int] = {
    "TIER_1": 0,
    "TIER_2": 1,
    "TIER_3": 2,
    "TIER_4": 3,
    "TIER_5": 4,
    "TIER_6": 5,
}

PHASE_MAP: dict[str, int] = {
    "PHASE_0": 0,
    "PHASE_1": 1,
    "PHASE_2": 2,
}


def _resolve_skills(chars_data: dict, buffs_data: dict) -> dict[str, list[dict]]:
    """从 building_data.json 的 chars + buffs 解析每个 char_id 的基建技能列表"""
    skill_map: dict[str, list[dict]] = {}

    for char_id, char_entry in chars_data.items():
        skills: list[dict] = []
        for buff_char in char_entry.get("buffChar", []):
            for buff_data in buff_char.get("buffData", []):
                buff_id = buff_data.get("buffId", "")
                if not buff_id:
                    continue

                buff_info = buffs_data.get(buff_id, {})
                if not buff_info:
                    continue

                cond = buff_data.get("cond", {})
                phase_str = cond.get("phase", "PHASE_0")
                phase = PHASE_MAP.get(phase_str, 0)

                skills.append({
                    "buffId": buff_id,
                    "roomType": buff_info.get("roomType", ""),
                    "phase": phase,
                })

        skill_map[char_id] = skills

    return skill_map


def main():
    for src in (SOURCE_CHAR, SOURCE_BUILD):
        if not src.exists():
            print(f"[错误] 源文件不存在: {src}")
            return

    print(f"[读取] {SOURCE_CHAR}")
    with open(SOURCE_CHAR, "r", encoding="utf-8") as f:
        char_raw = json.load(f)

    print(f"[读取] {SOURCE_BUILD}")
    with open(SOURCE_BUILD, "r", encoding="utf-8") as f:
        build_raw = json.load(f)

    build_chars = build_raw.get("chars", {})
    build_buffs = build_raw.get("buffs", {})
    print(f"[解析] building_data.json 中 buff 条目: {len(build_buffs)}")

    skill_map = _resolve_skills(build_chars, build_buffs)

    identity: dict[str, dict] = {}
    stats = {
        "total": 0,
        "skipped_token": 0,
        "skipped_unobtainable": 0,
        "has_group": 0,
        "has_team": 0,
        "has_subpower": 0,
        "total_skills": 0,
        "no_skill": 0,
    }

    for char_id, data in sorted(char_raw.items()):
        stats["total"] += 1

        if not char_id.startswith("char_"):
            stats["skipped_token"] += 1
            continue

        if data.get("isNotObtainable", False):
            stats["skipped_unobtainable"] += 1
            continue

        rarity_str = data.get("rarity", "TIER_1")
        rarity = RARITY_MAP.get(rarity_str, 0)

        entry = {
            "name": data.get("name", char_id),
            "rarity": rarity,
            "profession": data.get("profession", ""),
            "nationId": data.get("nationId", ""),
            "groupId": data.get("groupId"),
            "teamId": data.get("teamId"),
        }

        sub_power = data.get("subPower")
        if sub_power:
            stats["has_subpower"] += 1
            entry["subPower"] = [
                {
                    "nationId": sp.get("nationId", ""),
                    "groupId": sp.get("groupId"),
                    "teamId": sp.get("teamId"),
                }
                for sp in sub_power
            ]

        if entry["groupId"]:
            stats["has_group"] += 1
        if entry["teamId"]:
            stats["has_team"] += 1

        skills = skill_map.get(char_id, [])
        if skills:
            entry["skills"] = skills
            stats["total_skills"] += len(skills)
        else:
            stats["no_skill"] += 1

        identity[char_id] = entry

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with open(TARGET, "w", encoding="utf-8") as f:
        json.dump(identity, f, ensure_ascii=False, indent=2)
        f.write("\n")

    kept = stats["total"] - stats["skipped_token"] - stats["skipped_unobtainable"]
    print(f"[输出] {TARGET}")
    print(f"[统计] 干员总数(源): {stats['total']}")
    print(f"[统计] 已排除 token/召唤物: {stats['skipped_token']}")
    print(f"[统计] 已排除不可获取: {stats['skipped_unobtainable']}")
    print(f"[统计] 最终保留: {kept}")
    print(f"[统计] 基建技能总条数: {stats['total_skills']}")
    print(f"[统计] 无基建技能的干员: {stats['no_skill']}")
    print(f"[统计] 有 groupId 的: {stats['has_group']}")
    print(f"[统计] 有 teamId 的: {stats['has_team']}")
    print(f"[统计] 有 subPower 的: {stats['has_subpower']}")

    src_size_kb = SOURCE_CHAR.stat().st_size / 1024
    tgt_size_kb = TARGET.stat().st_size / 1024
    print(f"[体积] {src_size_kb:.0f} KB → {tgt_size_kb:.0f} KB (压缩率 {100 - tgt_size_kb / src_size_kb * 100:.1f}%)")


if __name__ == "__main__":
    main()
