"""排班求解器数据模型"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
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
    """
    char_id: str
    name: str
    rarity: int = 0
    skills: list[Skill] = field(default_factory=list)
    group_id: Optional[str] = None
    nation_id: Optional[str] = None
    team_id: Optional[str] = None

    def best_efficiency(self, room_type: str, product: Optional[str] = None) -> float:
        """获取该干员在指定设施和产物下的最高效率值"""
        best = -999.0
        for skill in self.skills:
            if skill.effective_for(room_type, product):
                eff = skill.efficient.get(product) if product else skill.efficient.max_value()
                if eff > best:
                    best = eff
        return best

    def has_skill_for(self, room_type: str, product: Optional[str] = None) -> bool:
        """检查该干员是否有适用于指定设施和产物的技能"""
        for skill in self.skills:
            if skill.effective_for(room_type, product):
                return True
        return False


# ─── 设施布局配置 ───────────────────────────────────────────────

@dataclass
class RoomConfig:
    """单个房间配置"""
    room_type: str
    room_index: int
    slots: int
    product: Optional[str] = None


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
        """
        rooms = [
            RoomConfig("Mfg", 0, 3, "CombatRecord"),
            RoomConfig("Mfg", 1, 3, "CombatRecord"),
            RoomConfig("Mfg", 2, 3, "PureGold"),
            RoomConfig("Mfg", 3, 3, "PureGold"),
            RoomConfig("Trade", 0, 3, "Money"),
            RoomConfig("Trade", 1, 3, "Money"),
            RoomConfig("Control", 0, 5),
            RoomConfig("Power", 0, 1),
            RoomConfig("Power", 1, 1),
            RoomConfig("Power", 2, 1),
            RoomConfig("Reception", 0, 2, "General"),
            RoomConfig("Office", 0, 1, "HR"),
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
    drone_room: str = "Trade"
    drone_index: int = 0
    drone_order: str = "pre"


@dataclass
class SolveResult:
    """求解结果"""
    plans: list[ShiftPlan] = field(default_factory=list)
    autofill_count: int = 0
