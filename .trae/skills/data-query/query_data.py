"""数据查询工具 - 对项目数据源执行常见查询

使用 character_identity.json + buffs_infrastructure.json 作为主数据源（轻量、快速），
支持按干员、设施、buff、组织、星级等多维度查询，避免每次分析数据时重复写临时脚本。

用法:
  python .trae/skills/data-query/query_data.py operator <干员名或ID>    # 查干员身份与技能
  python .trae/skills/data-query/query_data.py facility <设施类型>       # 列出某设施的所有干员
  python .trae/skills/data-query/query_data.py buff <buffId或名称>      # 查 buff 详情与拥有者
  python .trae/skills/data-query/query_data.py group <组织ID>           # 按 groupId 筛选干员
  python .trae/skills/data-query/query_data.py team <队伍ID>            # 按 teamId 筛选干员
  python .trae/skills/data-query/query_data.py nation <势力ID>          # 按 nationId 筛选干员
  python .trae/skills/data-query/query_data.py search <关键词>           # 在 buff 名称/描述中搜索
  python .trae/skills/data-query/query_data.py rarity <星级>             # 按星级筛选干员
  python .trae/skills/data-query/query_data.py compare <干员1> <干员2>   # 对比两个干员的基建技能
  python .trae/skills/data-query/query_data.py stats                    # 数据统计概览
  python .trae/skills/data-query/query_data.py list-groups              # 列出所有组织及人数
  python .trae/skills/data-query/query_data.py list-teams               # 列出所有队伍及人数
  python .trae/skills/data-query/query_data.py list-nations             # 列出所有势力及人数
  python .trae/skills/data-query/query_data.py list-facilities          # 列出所有设施类型及技能数

设施类型:
  CONTROL / MANUFACTURE / TRADING / POWER / MEETING / HIRE / DORMITORY
  TRAINING / WORKSHOP (仅 buff 表中有，干员身份表中不直接标注)
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

IDENTITY_PATH = PROJECT_ROOT / "character_identity.json"
BUFFS_INFRA_PATH = PROJECT_ROOT / "buffs_infrastructure.json"
BUFFS_NONPROD_PATH = PROJECT_ROOT / "buffs_non_production.json"

ROOM_TYPE_CN: dict[str, str] = {
    "CONTROL": "控制中枢",
    "MANUFACTURE": "制造站",
    "TRADING": "贸易站",
    "POWER": "发电站",
    "MEETING": "会客室",
    "HIRE": "办公室",
    "DORMITORY": "宿舍",
    "TRAINING": "训练室",
    "WORKSHOP": "加工站",
}

RARITY_CN: dict[int, str] = {
    0: "1★",
    1: "2★",
    2: "3★",
    3: "4★",
    4: "5★",
    5: "6★",
}

PHASE_CN: dict[int, str] = {
    0: "精0",
    1: "精1",
    2: "精2",
}


class DataStore:
    """数据存储，惰性加载各数据源"""

    def __init__(self):
        self._identity: dict | None = None
        self._buffs_infra: dict | None = None
        self._buffs_nonprod: dict | None = None
        self._name_index: dict[str, str] | None = None

    @property
    def identity(self) -> dict:
        if self._identity is None:
            self._identity = _load_json(IDENTITY_PATH)
        return self._identity

    @property
    def buffs_infra(self) -> dict:
        if self._buffs_infra is None:
            self._buffs_infra = _load_json(BUFFS_INFRA_PATH)
        return self._buffs_infra

    @property
    def buffs_nonprod(self) -> dict:
        if self._buffs_nonprod is None:
            self._buffs_nonprod = _load_json(BUFFS_NONPROD_PATH)
        return self._buffs_nonprod

    @property
    def all_buffs(self) -> dict:
        """合并基建 buff 和非生产 buff"""
        return {**self.buffs_infra, **self.buffs_nonprod}

    @property
    def name_index(self) -> dict[str, str]:
        """中文名 → char_id 的索引"""
        if self._name_index is None:
            self._name_index = {}
            for char_id, data in self.identity.items():
                name = data.get("name", "")
                if name and name != char_id:
                    self._name_index[name] = char_id
        return self._name_index

    def resolve_char_id(self, query: str) -> str | None:
        """将中文名或 char_id 解析为标准 char_id"""
        if query in self.identity:
            return query
        return self.name_index.get(query)


def _load_json(path: Path) -> dict:
    """加载 UTF-8 编码的 JSON 文件"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _format_rarity(rarity: int) -> str:
    """将数值星级格式化为显示用字符串，如 5 → '6★'"""
    return RARITY_CN.get(rarity, f"{rarity}★")


def _format_phase(phase: int) -> str:
    """将精英阶段数值格式化为显示用字符串，如 2 → '精2'"""
    return PHASE_CN.get(phase, f"精{phase}")


# ============================================================
# 子命令处理
# ============================================================


def cmd_operator(store: DataStore, query: str):
    """查询干员身份与基建技能"""
    char_id = store.resolve_char_id(query)
    if not char_id:
        print(f"[未找到] 干员 '{query}' 不在 character_identity.json 中")
        return

    data = store.identity[char_id]
    name = data.get("name", char_id)
    rarity = data.get("rarity", 0)
    profession = data.get("profession", "")
    nation = data.get("nationId", "")
    group = data.get("groupId")
    team = data.get("teamId")
    sub_power = data.get("subPower", [])
    skills = data.get("skills", [])

    print(f"干员: {name} ({char_id})")
    print(f"星级: {_format_rarity(rarity)}  |  职业: {profession}")
    print(f"势力: {nation}", end="")
    if group:
        print(f"  |  组织: {group}", end="")
    if team:
        print(f"  |  队伍: {team}", end="")
    print()

    if sub_power:
        sp_parts = []
        for sp in sub_power:
            parts = []
            if sp.get("nationId"):
                parts.append(sp["nationId"])
            if sp.get("groupId"):
                parts.append(f"组织={sp['groupId']}")
            if sp.get("teamId"):
                parts.append(f"队伍={sp['teamId']}")
            sp_parts.append(" + ".join(parts) if parts else "(空)")
        print(f"附属势力: {', '.join(sp_parts)}")

    if skills:
        print(f"\n基建技能 ({len(skills)} 条):")
        for i, sk in enumerate(skills, 1):
            buff_id = sk.get("buffId", "")
            room_type = sk.get("roomType", "")
            phase = sk.get("phase", 0)
            room_cn = ROOM_TYPE_CN.get(room_type, room_type)

            buff_info = store.all_buffs.get(buff_id, {})
            buff_name = buff_info.get("buffName", "")
            description = buff_info.get("description", "")
            efficiency = buff_info.get("efficiency", "")
            targets = buff_info.get("targets", [])

            line = f"  [{i}] {buff_name} ({buff_id})"
            if efficiency and efficiency != 0:
                line += f"  效率: {efficiency:+}"
            line += f"\n      设施: {room_cn}  |  需求: {_format_phase(phase)}"
            if targets:
                line += f"  |  目标: {', '.join(targets)}"
            print(line)
            if description:
                print(f"      描述: {description}")
    else:
        print("\n(无基建技能)")


def cmd_facility(store: DataStore, room_type: str):
    """列出某设施类型的所有干员"""
    room_upper = room_type.upper()
    room_cn = ROOM_TYPE_CN.get(room_upper, room_upper)

    results: list[tuple[str, str, int, int, str]] = []
    for char_id, data in store.identity.items():
        name = data.get("name", char_id)
        rarity = data.get("rarity", 0)
        for sk in data.get("skills", []):
            if sk.get("roomType", "") == room_upper:
                buff_id = sk.get("buffId", "")
                phase = sk.get("phase", 0)
                buff_info = store.all_buffs.get(buff_id, {})
                buff_name = buff_info.get("buffName", buff_id)
                results.append((char_id, name, rarity, phase, buff_name))
                break

    results.sort(key=lambda x: (-x[2], x[1]))

    print(f"设施: {room_cn} ({room_upper})")
    print(f"拥有此设施技能的干员: {len(results)} 人\n")
    print(f"{'干员':<10} {'星级':<6} {'需求':<6} {'技能名'}")
    print("-" * 60)
    for char_id, name, rarity, phase, buff_name in results:
        print(f"{name:<10} {_format_rarity(rarity):<6} {_format_phase(phase):<6} {buff_name}")


def cmd_buff(store: DataStore, query: str):
    """查询 buff 详情与拥有者"""
    all_buffs = store.all_buffs

    matched_id: str | None = None
    if query in all_buffs:
        matched_id = query
    else:
        for buff_id, buff_info in all_buffs.items():
            if query.lower() in buff_info.get("buffName", "").lower():
                if matched_id is not None:
                    print(f"[警告] 多个匹配: {matched_id} 和 {buff_id}，使用第一个")
                    break
                matched_id = buff_id

    if not matched_id:
        print(f"[未找到] buff '{query}'")
        return

    buff_info = all_buffs[matched_id]
    print(f"Buff: {buff_info.get('buffName', '')} ({matched_id})")
    print(f"设施: {ROOM_TYPE_CN.get(buff_info.get('roomType', ''), buff_info.get('roomType', ''))}")
    eff = buff_info.get("efficiency", "")
    if eff is not None and eff != 0:
        print(f"效率值: {eff:+}")
    print(f"描述: {buff_info.get('description', '')}")
    targets = buff_info.get("targets", [])
    if targets:
        print(f"目标: {', '.join(targets)}")

    char_ids = buff_info.get("charId", [])
    if char_ids:
        print(f"\n拥有此 buff 的干员 ({len(char_ids)} 人):")
        chars_with_name: list[tuple[str, str, int]] = []
        for cid in char_ids:
            ident = store.identity.get(cid, {})
            name = ident.get("name", cid)
            rarity = ident.get("rarity", 0)
            chars_with_name.append((cid, name, rarity))
        chars_with_name.sort(key=lambda x: (-x[2], x[1]))
        for cid, name, rarity in chars_with_name:
            print(f"  {name} ({cid})  {_format_rarity(rarity)}")
    else:
        print("\n(此 buff 未标注拥有干员)")


def cmd_group(store: DataStore, group_id: str):
    """按 groupId 筛选干员"""
    _filter_by_field(store, "groupId", group_id, "组织")


def cmd_team(store: DataStore, team_id: str):
    """按 teamId 筛选干员"""
    _filter_by_field(store, "teamId", team_id, "队伍")


def cmd_nation(store: DataStore, nation_id: str):
    """按 nationId 筛选干员"""
    _filter_by_field(store, "nationId", nation_id, "势力")
    _filter_by_field(store, "subPower", nation_id, "附属势力", fuzzy_match=True)


def _filter_by_field(store: DataStore, field: str, value: str, label: str, fuzzy_match: bool = False):
    """按指定字段值筛选干员并输出表格，支持 subPower 的模糊匹配"""
    results: list[tuple[str, str, int, str, str | None]] = []

    for char_id, data in store.identity.items():
        name = data.get("name", char_id)
        rarity = data.get("rarity", 0)
        profession = data.get("profession", "")

        matched_group = None
        if fuzzy_match and field == "subPower":
            for sp in data.get("subPower", []):
                if sp.get("nationId") == value:
                    matched_group = sp.get("groupId")
                    break
                if sp.get("groupId") == value:
                    matched_group = sp.get("groupId")
                    break
            if matched_group is None:
                continue
        else:
            val = data.get(field)
            if val != value:
                continue
            if field == "subPower":
                for sp in data.get("subPower", []):
                    if sp.get("nationId") == value:
                        matched_group = sp.get("groupId")
                        break

        results.append((char_id, name, rarity, profession, matched_group))

    results.sort(key=lambda x: (-x[2], x[1]))

    title = f"{label}: {value}"
    print(f"{title} - {len(results)} 人\n")
    print(f"{'干员':<10} {'星级':<6} {'职业':<12} {'组织' if any(r[4] for r in results) else ''}")
    print("-" * 60)
    for char_id, name, rarity, profession, mg in results:
        extra = f"  {mg}" if mg else ""
        print(f"{name:<10} {_format_rarity(rarity):<6} {profession:<12}{extra}")


def cmd_search(store: DataStore, keyword: str):
    """在 buff 名称和描述中搜索关键词"""
    all_buffs = store.all_buffs
    matches: list[tuple[str, str, str, str, int]] = []

    kw_lower = keyword.lower()
    for buff_id, buff_info in all_buffs.items():
        buff_name = buff_info.get("buffName", "")
        description = buff_info.get("description", "")
        room_type = buff_info.get("roomType", "")

        score = 0
        if kw_lower in buff_name.lower():
            score += 10
        if kw_lower in description.lower():
            score += 1

        if score > 0:
            char_ids = buff_info.get("charId", [])
            matches.append((buff_id, buff_name, room_type, description, len(char_ids), score))

    if not matches:
        print(f"[未找到] 关键词 '{keyword}' 未匹配到任何 buff")
        return

    matches.sort(key=lambda x: (-x[5], x[1]))

    print(f"搜索 '{keyword}' 匹配 {len(matches)} 条 buff:\n")
    for buff_id, buff_name, room_type, desc, char_count, score in matches[:30]:
        room_cn = ROOM_TYPE_CN.get(room_type, room_type)
        print(f"  [{room_cn}] {buff_name} ({buff_id})  -  {char_count} 人拥有")
        if score >= 10:
            print(f"    描述: {desc}")
    if len(matches) > 30:
        print(f"  ... 还有 {len(matches) - 30} 条结果未显示")


def cmd_rarity(store: DataStore, rarity_str: str):
    """按星级筛选干员"""
    try:
        rarity = int(rarity_str)
    except ValueError:
        print(f"[错误] 无效星级: {rarity_str}")
        return

    results: list[tuple[str, str, str, int]] = []
    for char_id, data in store.identity.items():
        if data.get("rarity") == rarity:
            name = data.get("name", char_id)
            profession = data.get("profession", "")
            skill_count = len(data.get("skills", []))
            results.append((char_id, name, profession, skill_count))

    results.sort(key=lambda x: x[1])

    print(f"星级: {_format_rarity(rarity)} - {len(results)} 人\n")
    print(f"{'干员':<10} {'职业':<12} {'技能数'}")
    print("-" * 40)
    for char_id, name, profession, skill_count in results:
        print(f"{name:<10} {profession:<12} {skill_count}")


def cmd_compare(store: DataStore, op1: str, op2: str):
    """对比两个干员的基建技能"""
    char_id1 = store.resolve_char_id(op1)
    char_id2 = store.resolve_char_id(op2)

    if not char_id1:
        print(f"[未找到] 干员 '{op1}'")
        return
    if not char_id2:
        print(f"[未找到] 干员 '{op2}'")
        return

    data1 = store.identity[char_id1]
    data2 = store.identity[char_id2]
    name1 = data1.get("name", char_id1)
    name2 = data2.get("name", char_id2)

    print(f"对比: {name1} ({char_id1})  vs  {name2} ({char_id2})")
    print(f"星级: {_format_rarity(data1.get('rarity', 0))}  vs  {_format_rarity(data2.get('rarity', 0))}")
    print(f"职业: {data1.get('profession', '')}  vs  {data2.get('profession', '')}")
    print()

    skills1 = data1.get("skills", [])
    skills2 = data2.get("skills", [])

    def _skill_set(skills):
        """提取技能的去重标识集合 (buffId, roomType, phase)"""
        return {(s["buffId"], s["roomType"], s["phase"]) for s in skills}

    set1 = _skill_set(skills1)
    set2 = _skill_set(skills2)

    common = set1 & set2
    only1 = set1 - set2
    only2 = set2 - set1

    if only1:
        print(f"{name1} 独有的技能:")
        for buff_id, room_type, phase in only1:
            buff_info = store.all_buffs.get(buff_id, {})
            buff_name = buff_info.get("buffName", buff_id)
            room_cn = ROOM_TYPE_CN.get(room_type, room_type)
            print(f"  {buff_name} [{room_cn}] {_format_phase(phase)}")

    if only2:
        print(f"{name2} 独有的技能:")
        for buff_id, room_type, phase in only2:
            buff_info = store.all_buffs.get(buff_id, {})
            buff_name = buff_info.get("buffName", buff_id)
            room_cn = ROOM_TYPE_CN.get(room_type, room_type)
            print(f"  {buff_name} [{room_cn}] {_format_phase(phase)}")

    if common:
        print(f"共同技能:")
        for buff_id, room_type, phase in common:
            buff_info = store.all_buffs.get(buff_id, {})
            buff_name = buff_info.get("buffName", buff_id)
            room_cn = ROOM_TYPE_CN.get(room_type, room_type)
            print(f"  {buff_name} [{room_cn}] {_format_phase(phase)}")

    if not only1 and not only2 and not common:
        print("两个干员均无基建技能")
    elif not only1 and not only2:
        print("两个干员的基建技能完全相同")


def cmd_stats(store: DataStore):
    """数据统计概览"""
    identity = store.identity

    total = len(identity)
    rarity_dist = Counter()
    profession_dist = Counter()
    nation_dist = Counter()
    group_dist = Counter()
    team_dist = Counter()
    skill_count_dist = Counter()
    room_dist = Counter()
    phase_dist = Counter()
    has_subpower = 0

    for data in identity.values():
        rarity_dist[data.get("rarity", 0)] += 1
        profession_dist[data.get("profession", "")] += 1
        nation_dist[data.get("nationId", "")] += 1
        if data.get("groupId"):
            group_dist[data["groupId"]] += 1
        if data.get("teamId"):
            team_dist[data["teamId"]] += 1
        if data.get("subPower"):
            has_subpower += 1

        skills = data.get("skills", [])
        skill_count_dist[len(skills)] += 1
        for sk in skills:
            room_dist[sk.get("roomType", "")] += 1
            phase_dist[sk.get("phase", 0)] += 1

    print("=" * 60)
    print(f"数据统计概览")
    print("=" * 60)
    print(f"\n干员总数: {total}")

    print(f"\n--- 星级分布 ---")
    for r in sorted(rarity_dist, reverse=True):
        print(f"  {_format_rarity(r)}: {rarity_dist[r]} 人")

    print(f"\n--- 职业分布 ---")
    for prof, count in profession_dist.most_common():
        print(f"  {prof}: {count} 人")

    print(f"\n--- 势力分布 (top 20) ---")
    for nation, count in nation_dist.most_common(20):
        print(f"  {nation}: {count} 人")

    print(f"\n--- 组织分布 ---")
    for group, count in group_dist.most_common():
        print(f"  {group}: {count} 人")

    print(f"\n--- 队伍分布 ---")
    for team, count in team_dist.most_common():
        print(f"  {team}: {count} 人")

    print(f"\n--- 附属势力干员数 ---")
    print(f"  有 subPower 的: {has_subpower} 人")

    print(f"\n--- 技能数分布 ---")
    for cnt in sorted(skill_count_dist):
        label = f"{cnt} 个技能" if cnt > 0 else "无技能"
        print(f"  {label}: {skill_count_dist[cnt]} 人")

    print(f"\n--- 技能设施分布 ---")
    for room, count in room_dist.most_common():
        room_cn = ROOM_TYPE_CN.get(room, room)
        print(f"  {room_cn} ({room}): {count} 条")

    print(f"\n--- 技能阶段分布 ---")
    for phase in sorted(phase_dist):
        print(f"  {_format_phase(phase)}: {phase_dist[phase]} 条")


def cmd_list_groups(store: DataStore):
    """列出所有组织及人数"""
    _list_field(store, "groupId", "组织")


def cmd_list_teams(store: DataStore):
    """列出所有队伍及人数"""
    _list_field(store, "teamId", "队伍")


def cmd_list_nations(store: DataStore):
    """列出所有势力及人数"""
    _list_field(store, "nationId", "势力")


def _list_field(store: DataStore, field: str, label: str):
    """统计并输出干员表中某字段值的分布情况"""
    dist = Counter()
    for data in store.identity.values():
        val = data.get(field)
        if val:
            dist[val] += 1

    print(f"所有{label}:\n")
    for val, count in dist.most_common():
        print(f"  {val}: {count} 人")


def cmd_list_facilities(store: DataStore):
    """列出所有设施类型及技能数"""
    room_dist = Counter()
    room_operators: dict[str, set] = {}

    for char_id, data in store.identity.items():
        for sk in data.get("skills", []):
            room = sk.get("roomType", "")
            room_dist[room] += 1
            if room not in room_operators:
                room_operators[room] = set()
            room_operators[room].add(char_id)

    print("设施类型及技能分布:\n")
    print(f"{'设施':<16} {'中文名':<10} {'技能数':<8} {'干员数'}")
    print("-" * 50)
    for room, count in room_dist.most_common():
        room_cn = ROOM_TYPE_CN.get(room, room)
        op_count = len(room_operators.get(room, set()))
        print(f"{room:<16} {room_cn:<10} {count:<8} {op_count}")


# ============================================================
# 主入口
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="数据查询工具 - 对项目数据源执行常见查询",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python .trae/skills/data-query/query_data.py operator 阿米娅
  python .trae/skills/data-query/query_data.py facility MANUFACTURE
  python .trae/skills/data-query/query_data.py buff 最高权限
  python .trae/skills/data-query/query_data.py search 标准化
  python .trae/skills/data-query/query_data.py group karlan
  python .trae/skills/data-query/query_data.py rarity 6
  python .trae/skills/data-query/query_data.py stats
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    p_op = subparsers.add_parser("operator", help="查询干员身份与基建技能")
    p_op.add_argument("query", help="干员中文名或 char_id")

    p_fac = subparsers.add_parser("facility", help="列出某设施类型的所有干员")
    p_fac.add_argument("room_type", help="设施类型 (CONTROL/MANUFACTURE/TRADING/POWER/MEETING/HIRE/DORMITORY)")

    p_buff = subparsers.add_parser("buff", help="查询 buff 详情与拥有者")
    p_buff.add_argument("query", help="buffId 或 buff 名称")

    p_group = subparsers.add_parser("group", help="按 groupId 筛选干员")
    p_group.add_argument("group_id", help="组织 ID")

    p_team = subparsers.add_parser("team", help="按 teamId 筛选干员")
    p_team.add_argument("team_id", help="队伍 ID")

    p_nation = subparsers.add_parser("nation", help="按 nationId 筛选干员")
    p_nation.add_argument("nation_id", help="势力 ID")

    p_search = subparsers.add_parser("search", help="在 buff 名称/描述中搜索关键词")
    p_search.add_argument("keyword", help="搜索关键词")

    p_rarity = subparsers.add_parser("rarity", help="按星级筛选干员")
    p_rarity.add_argument("rarity", help="星级 (0-5, 对应 1★~6★)")

    p_comp = subparsers.add_parser("compare", help="对比两个干员的基建技能")
    p_comp.add_argument("op1", help="干员1 (中文名或 char_id)")
    p_comp.add_argument("op2", help="干员2 (中文名或 char_id)")

    subparsers.add_parser("stats", help="数据统计概览")
    subparsers.add_parser("list-groups", help="列出所有组织及人数")
    subparsers.add_parser("list-teams", help="列出所有队伍及人数")
    subparsers.add_parser("list-nations", help="列出所有势力及人数")
    subparsers.add_parser("list-facilities", help="列出所有设施类型及技能数")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    missing = []
    if not IDENTITY_PATH.exists():
        missing.append(str(IDENTITY_PATH))
    if not BUFFS_INFRA_PATH.exists():
        missing.append(str(BUFFS_INFRA_PATH))
    if missing:
        print(f"[错误] 缺少必要数据文件: {', '.join(missing)}")
        print("请先运行 scripts/extract_character_identity.py 生成 character_identity.json")
        return

    store = DataStore()

    commands = {
        "operator": lambda: cmd_operator(store, args.query),
        "facility": lambda: cmd_facility(store, args.room_type),
        "buff": lambda: cmd_buff(store, args.query),
        "group": lambda: cmd_group(store, args.group_id),
        "team": lambda: cmd_team(store, args.team_id),
        "nation": lambda: cmd_nation(store, args.nation_id),
        "search": lambda: cmd_search(store, args.keyword),
        "rarity": lambda: cmd_rarity(store, args.rarity),
        "compare": lambda: cmd_compare(store, args.op1, args.op2),
        "stats": lambda: cmd_stats(store),
        "list-groups": lambda: cmd_list_groups(store),
        "list-teams": lambda: cmd_list_teams(store),
        "list-nations": lambda: cmd_list_nations(store),
        "list-facilities": lambda: cmd_list_facilities(store),
    }

    handler = commands.get(args.command)
    if handler:
        handler()


if __name__ == "__main__":
    main()
