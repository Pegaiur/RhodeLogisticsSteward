"""排班求解器数据模型"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from steward_core.solver.config import SolverConfig


@dataclass(slots=True)
class LinearSegment:
    """e(t) 的一个线性片段: e(t) = a + b·t, t ∈ [t_start, t_start + dt]

    所有技能效率统一归约为此数据结构。
    积分闭式解: ∫(a + b·t) dt = a·dt + b·(t1² - t0²)/2
    """
    a: float       # 截距（百分值，如 30 表示 +30%）
    b: float       # 斜率（百分值/h，如 -2.5 表示 -2.5%/h）
    t_start: float # 起始时间 (h)
    dt: float      # 持续时间 (h)

    def integrate(self) -> float:
        """∫(a + b·t) dt over [t_start, t_start+dt]"""
        if self.dt <= 0:
            return 0.0
        t0 = self.t_start
        t1 = self.t_start + self.dt
        return self.a * self.dt + self.b * (t1**2 - t0**2) / 2.0


@dataclass
class EfficiencyMap:
    """技能在不同产物下的效率值

    直接使用 MAA infrast.json 的 efficient 字段：
    - all=30 表示全产物 +30%
    - PureGold=25 表示仅赤金 +25%
    - CombatRecord=30.1 表示作战记录 +30%，.1 为 MAA 内部单产品优先标记

    raw 保留原始值以供后续扩展（如联动校验需要区分 0.05 vs 30）。
    """
    raw: dict[str, float]

    def get(self, product: str) -> float:
        """获取指定产物下的效率值

        优先返回产品专属值（如 PureGold=25），
        无专属值时回退到 all（通用效率），
        均无时返回哨兵值。
        """
        if product in self.raw:
            return self.raw[product]
        if "all" in self.raw:
            return self.raw["all"]
        return -999.0

    def max_value(self) -> float:
        """获取所有产物中的最高效率值"""
        if not self.raw:
            return -999.0
        return max(self.raw.values())


@dataclass
class Skill:
    """单个基建技能

    由 building_data.json 的 buffChar[].buffData[] 展开而来，
    通过 buffId 关联 buffs{} 表获取 roomType 和 skillIcon，
    再通过 skillIcon 映射到 infrast.json 获取效率值。
    """
    buff_id: str
    buff_name: str
    skill_icon: str
    room_type: str
    efficient: EfficiencyMap
    phase: int = 0
    capacity_bonus: int = 0

    def effective_for(self, room_type: str, product: Optional[str] = None) -> bool:
        """检查该技能在指定设施和产物下是否生效"""
        if self.room_type != room_type:
            return False
        if product is not None and product not in self.efficient.raw and "all" not in self.efficient.raw:
            return False
        return True


@dataclass
class Operator:
    """干员

    char_id / name 来自 character_identity.json
    rarity 预留，后续 Step 4 练度过滤时可能需要
    skills 为该干员的所有基建技能（已解析效率值）
    group_id/nation_id/team_id 用于体系联动判定（阵营/势力/队伍）
    sub_group_ids 来自 character_identity.json subPower[].groupId，用于附属阵营判定
    sub_nation_ids 来自 character_identity.json subPower[].nationId，用于附属势力判定
    sub_team_ids   来自 character_identity.json subPower[].teamId，用于附属队伍判定
    """
    char_id: str
    name: str
    rarity: int = 0
    elite_phase: int = 2
    skills: list[Skill] = field(default_factory=list)
    group_id: Optional[str] = None
    nation_id: Optional[str] = None
    team_id: Optional[str] = None
    sub_group_ids: frozenset[str] = field(default_factory=frozenset)
    sub_nation_ids: frozenset[str] = field(default_factory=frozenset)
    sub_team_ids: frozenset[str] = field(default_factory=frozenset)

    def has_group(self, group_id: str) -> bool:
        """检查干员是否属于指定阵营（含主 group_id 和 subPower 附属 group）"""
        return self.group_id == group_id or group_id in self.sub_group_ids

    def has_nation(self, nation_id: str) -> bool:
        """检查干员是否属于指定势力（含主 nation_id 和 subPower 附属 nation）"""
        return self.nation_id == nation_id or nation_id in self.sub_nation_ids

    def has_team(self, team_id: str) -> bool:
        """检查干员是否属于指定队伍（含主 team_id 和 subPower 附属 team）"""
        return self.team_id == team_id or team_id in self.sub_team_ids

    def has_skill_for(self, room_type: str, product: Optional[str] = None) -> bool:
        """检查该干员是否有适用于指定设施和产物的技能"""
        for skill in self.skills:
            if skill.effective_for(room_type, product):
                return True
        return False

    def active_skills_for(self, room_type: str) -> list[Skill]:
        """本 roomType 下扣除升级覆写后实际生效的技能。

        判定规则：同 buffId 前缀组内取 phase 最高且已解锁的技能。
        不同前缀组共存。同 phase 时取效率值更高的。
        前缀 = buffId 去掉末尾 [数字]，如 'manu_prod_spd_bd[010]' -> 'manu_prod_spd_bd'
        """
        available = [sk for sk in self.skills if sk.phase <= self.elite_phase]
        groups: dict[str, Skill] = {}
        for sk in available:
            if sk.room_type != room_type:
                continue
            prefix = _buff_id_prefix(sk.buff_id)
            if prefix not in groups:
                groups[prefix] = sk
                continue
            existing = groups[prefix]
            if sk.phase > existing.phase:
                groups[prefix] = sk
            elif sk.phase == existing.phase:
                if sk.efficient.max_value() > existing.efficient.max_value():
                    groups[prefix] = sk
        return list(groups.values())


def _buff_id_prefix(buff_id: str) -> str:
    """去掉 buffId 末尾 [NNN] 后缀，返回前缀。

    'manu_prod_spd_bd[010]' -> 'manu_prod_spd_bd'
    'trade_ord_spd&tag[000]' -> 'trade_ord_spd&tag'
    """
    m = re.match(r"^(.+)\[\d+\]$", buff_id)
    return m.group(1) if m else buff_id


# ─── 设施布局配置 ───────────────────────────────────────────────

@dataclass
class RoomConfig:
    """单个房间配置"""
    room_type: str
    room_index: int
    slots: int
    product: Optional[str] = None
    level: int = 3


@dataclass
class LayoutConfig:
    """设施布局配置

    定义所有需要排班的设施，包括每间房工位数和产物类型。
    按求解优先级排列。
    """
    rooms: list[RoomConfig] = field(default_factory=list)

    @staticmethod
    def layout_243() -> "LayoutConfig":
        """243 布局（2 Trade + 4 Mfg + 3 Power）

        资源链与优先级：
        - 赤金是贸易站原料 → 制造站整体排在贸易站前
        - 经验几乎完全依赖基建产出，赤金超出贸易站消耗则价值归零
          → 制造站内部 经验 > 赤金
        - 控制中枢/发电站不与生产设施竞争干员，位置不影响结果
        - 宿舍 4×5人，不参与生产竞争，排在本配置末尾由求解器单独填充
        """
        rooms = [
            RoomConfig("Mfg", 0, 3, "CombatRecord"),
            RoomConfig("Mfg", 1, 3, "CombatRecord"),
            RoomConfig("Mfg", 2, 3, "PureGold"),
            RoomConfig("Mfg", 3, 3, "PureGold"),
            RoomConfig("Trade", 0, 3, "Money"),
            RoomConfig("Trade", 1, 3, "Money"),
            RoomConfig("Control", 0, 5, level=5),
            RoomConfig("Power", 0, 1),
            RoomConfig("Power", 1, 1),
            RoomConfig("Power", 2, 1),
            RoomConfig("Reception", 0, 2, "General"),
            RoomConfig("Office", 0, 1, "HR"),
            RoomConfig("Training", 0, 1),
            RoomConfig("Workshop", 0, 1),
            RoomConfig("Dormitory", 0, 5, "Rest", level=5),
            RoomConfig("Dormitory", 1, 5, "Rest", level=5),
            RoomConfig("Dormitory", 2, 5, "Rest", level=5),
            RoomConfig("Dormitory", 3, 5, "Rest", level=5),
        ]
        return LayoutConfig(rooms=rooms)


# ─── 排班结果 ───────────────────────────────────────────────────

@dataclass
class RoomAssignment:
    """单个房间的分配结果"""
    room_type: str
    room_index: int
    operators: list[str] = field(default_factory=list)
    product: Optional[str] = None
    autofill: bool = False


@dataclass
class ShiftPlan:
    """单个班次的排班方案"""
    name: str
    assignments: list[RoomAssignment] = field(default_factory=list)
    period_from: str = "00:00"
    period_to: str = "23:59"
    drone_room: str = "Mfg"
    drone_index: int = 0
    drone_order: str = "pre"


@dataclass
class SolveResult:
    """求解结果"""
    plans: list[ShiftPlan] = field(default_factory=list)
    autofill_count: int = 0
    config_used: Optional["SolverConfig"] = None
    mood_snapshots: list[dict[str, tuple[float, float]]] = field(default_factory=list)
    """每班次心情快照: [{干员名: (班次前心情, 班次后心情)}, ...]，由 solve_multi_shift 填充"""
