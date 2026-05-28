"""硬编码数据推导脚本

扫描协同表与角色数据，生成 steward_core/synergy/_derived.py。
运行: python scripts/derive.py
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from steward_core.synergy.mfg_linkages import (
    _A_PAIR_TABLE,
    _A_SKILL_COUNT_TABLE,
    _A_AUTOMATION_FALLBACK,
    _A_ROOM_FACTION_TABLE,
    _A_ROOM_FACTION_EXTRA,
)
from steward_core.synergy.facility_linkages import _A_FACILITY_LINK_TABLE
from steward_core.synergy.buff_pool import _B_BUFF_CONSUMER_TABLE
from steward_core.synergy.global_linkages import _B_CROSS_ROOM_PAIR_TABLE, _B_GLOBAL_FACTION_TABLE


def _derive_mfg_anchors() -> set[str]:
    names: set[str] = set()

    for holder, _target, _prod in _A_PAIR_TABLE:
        names.add(holder)

    names.update(_A_SKILL_COUNT_TABLE.keys())
    names.update(_A_AUTOMATION_FALLBACK.keys())

    for holder, e in _A_ROOM_FACTION_TABLE.items():
        if e.target_room is None or e.target_room == "Mfg":
            names.add(holder)

    for holder in _A_ROOM_FACTION_EXTRA:
        names.add(holder)

    for holder, e in _A_FACILITY_LINK_TABLE.items():
        if e.target_room is None or e.target_room == "Mfg":
            names.add(holder)

    for holder, e in _B_BUFF_CONSUMER_TABLE.items():
        if e.target_room == "Mfg":
            names.add(holder)

    for holder, e in _B_CROSS_ROOM_PAIR_TABLE.items():
        if e.target_room is None or e.target_room == "Mfg":
            names.add(holder)

    for holder, e in _B_GLOBAL_FACTION_TABLE.items():
        if e.target_room is None or e.target_room == "Mfg":
            names.add(holder)

    names.update({"海沫", "泡泡", "红云", "槐琥"})

    return names


def _derive_trade_anchors() -> set[str]:
    names: set[str] = set()

    for holder, e in _A_ROOM_FACTION_TABLE.items():
        if e.target_room is None or e.target_room == "Trade":
            names.add(holder)

    for holder, e in _A_FACILITY_LINK_TABLE.items():
        if e.target_room is None or e.target_room == "Trade":
            names.add(holder)

    for holder, e in _B_BUFF_CONSUMER_TABLE.items():
        if e.target_room == "Trade":
            names.add(holder)

    for holder, e in _B_CROSS_ROOM_PAIR_TABLE.items():
        if e.target_room is None or e.target_room == "Trade":
            names.add(holder)

    for holder, e in _B_GLOBAL_FACTION_TABLE.items():
        if e.target_room is None or e.target_room == "Trade":
            names.add(holder)

    names.update({"巫恋", "火哨", "吉星", "雪雉", "德克萨斯"})

    return names


def _derive_name_sets() -> dict[str, set[str]]:
    ci_path = PROJECT_ROOT / "character_identity.json"
    if not ci_path.exists():
        print(f"[警告] 找不到 {ci_path}，名称集合仅使用硬编码值")
        return _fallback_name_sets()

    with open(ci_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    knight: set[str] = set()
    op_platform: set[str] = set()
    durin: set[str] = set()
    mh: set[str] = set()
    lung_men: set[str] = set()

    for op_data in raw.values():
        name = op_data.get("name", "")
        if not name:
            continue
        nation = op_data.get("nationId", "")
        group = op_data.get("groupId", "")

        if nation == "kazimierz" or group == "pinus":
            knight.add(name)

    knight.update({
        "砾", "野鬃", "白金", "鞭刃", "暴雨", "耀骑士临光",
        "瑕光", "临光", "远牙", "灰毫", "焰尾", "薇薇安娜",
    })
    durin.update({"杜林", "桃金娘", "褐果", "至简"})
    mh.update({"麒麟R夜刀", "炼金术士"})
    lung_men.update({"陈", "星熊", "诗怀雅", "斩业星熊"})
    op_platform.update({"Lancet-2", "Castle-3", "THRM-EX", "正义骑士号"})

    return {
        "KNIGHT_NAMES": knight,
        "DURIN_NAMES": durin,
        "OP_PLATFORM_NAMES": op_platform,
        "MH_NAMES": mh,
        "LUNG_MEN_GUARD_NAMES": lung_men,
    }


def _fallback_name_sets() -> dict[str, set[str]]:
    return {
        "KNIGHT_NAMES": {
            "砾", "野鬃", "白金", "鞭刃", "暴雨", "耀骑士临光",
            "瑕光", "临光", "远牙", "灰毫", "焰尾", "薇薇安娜",
        },
        "DURIN_NAMES": {"杜林", "桃金娘", "褐果", "至简"},
        "OP_PLATFORM_NAMES": {"Lancet-2", "Castle-3", "THRM-EX", "正义骑士号"},
        "MH_NAMES": {"麒麟R夜刀", "炼金术士"},
        "LUNG_MEN_GUARD_NAMES": {"陈", "星熊", "诗怀雅", "斩业星熊"},
    }


def _format_set(s: set[str]) -> str:
    items = sorted(s)
    lines = []
    for item in items:
        lines.append(f'    "{item}",')
    return "\n".join(lines)


def generate(output_path: Path) -> None:
    mfg = _derive_mfg_anchors()
    trade = _derive_trade_anchors()
    name_sets = _derive_name_sets()

    lines = [
        '"""自动生成的硬编码数据',
        "",
        "由 scripts/derive.py 生成，请勿手动编辑。",
        '运行: python scripts/derive.py',
        '"""',
        "",
        "# ── 制造站锚点 ──",
        "# 来源：_A_PAIR_TABLE / _A_SKILL_COUNT_TABLE / _A_AUTOMATION_FALLBACK",
        "#       _A_ROOM_FACTION_TABLE / _A_FACILITY_LINK_TABLE",
        "#       _B_BUFF_CONSUMER_TABLE / _B_CROSS_ROOM_PAIR_TABLE",
        "#       _B_GLOBAL_FACTION_TABLE / 硬编码特殊干员",
        "MFG_ANCHORS: set[str] = {",
        _format_set(mfg),
        "}",
        "",
        "# ── 贸易站锚点 ──",
        "# 来源：_A_ROOM_FACTION_TABLE / _A_FACILITY_LINK_TABLE",
        "#       _B_BUFF_CONSUMER_TABLE / _B_CROSS_ROOM_PAIR_TABLE",
        "#       _B_GLOBAL_FACTION_TABLE / 手工注册",
        "TRADE_ANCHORS: set[str] = {",
        _format_set(trade),
        "}",
    ]

    for var_name in ["KNIGHT_NAMES", "DURIN_NAMES", "OP_PLATFORM_NAMES",
                     "MH_NAMES", "LUNG_MEN_GUARD_NAMES"]:
        lines.append("")
        lines.append(f"# ── {var_name} ──")
        desc = {
            "KNIGHT_NAMES": "骑士：nationId==kazimierz OR groupId==pinus OR 硬编码",
            "DURIN_NAMES": "杜林族：硬编码（character_identity.json 无 raceId 字段）",
            "OP_PLATFORM_NAMES": "作业平台：硬编码（机器人 profession 无特殊标识）",
            "MH_NAMES": "怪物猎人小队：硬编码",
            "LUNG_MEN_GUARD_NAMES": "龙门近卫局：硬编码",
        }.get(var_name, "")
        lines.append(f"# 推导规则：{desc}")
        lines.append(f"{var_name}: set[str] = {{")
        lines.append(_format_set(name_sets[var_name]))
        lines.append("}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[derive] 已生成 {output_path}")
    print(f"  MFG_ANCHORS: {len(mfg)} 名")
    print(f"  TRADE_ANCHORS: {len(trade)} 名")
    for k, v in name_sets.items():
        print(f"  {k}: {len(v)} 名")


if __name__ == "__main__":
    output = PROJECT_ROOT / "steward_core" / "synergy" / "_derived.py"
    generate(output)
