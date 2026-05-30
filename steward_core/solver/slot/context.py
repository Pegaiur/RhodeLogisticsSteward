"""槽位求解器统一状态载体

SlotContext 替代旧的 locked_support / assigned_ids / assigned_names
等多个可变 dict 的碎片化状态传递，提供统一的读写接口。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from steward_core.models import Operator, LayoutConfig
    from steward_core.solver.params import SolverParams


STATE_DIMS = ("yanhuo", "perception", "engineering_robots", "monster_cuisine", "silent_resonance")
"""全局状态向量的 5 个维度"""


@dataclass
class StateVector:
    """全局状态向量

    技能通过此数据结构通信——类型 2 技能写入，类型 1f 技能读取。
    维度枚举见 STATE_DIMS。
    """

    yanhuo: float = 0.0
    perception: float = 0.0
    engineering_robots: float = 0.0
    monster_cuisine: float = 0.0
    silent_resonance: float = 0.0

    def __getitem__(self, dim: str) -> float:
        return getattr(self, dim)

    def __setitem__(self, dim: str, value: float) -> None:
        object.__setattr__(self, dim, value)

    def to_dict(self) -> dict[str, float]:
        return {d: getattr(self, d) for d in STATE_DIMS}

    @classmethod
    def from_dict(cls, d: dict[str, float]) -> "StateVector":
        return cls(**{k: d.get(k, 0.0) for k in STATE_DIMS})

    @classmethod
    def s_max(cls, layout_type: str = "243") -> "StateVector":
        """S_max 乐观上界（冷启动用）

        取所有可用类型 2 写入者的最大可能增量，
        仅计入不依赖其他分配的独立项。
        """
        _ = layout_type
        return cls(
            yanhuo=95.0,
            perception=60.0,
            engineering_robots=64.0,
            monster_cuisine=5.0,
            silent_resonance=10.0,
        )


@dataclass
class SlotAssignment:
    """单个槽位的分配记录"""

    slot_id: str
    facility_type: str
    product: str
    operator_name: str
    room_index: int = 0

    @property
    def is_empty(self) -> bool:
        return self.operator_name == ""


@dataclass
class WindowState:
    """单窗口状态快照"""

    assignments: list[SlotAssignment] = field(default_factory=list)
    S: StateVector = field(default_factory=StateVector)
    D: dict[str, float] = field(default_factory=dict)


@dataclass
class SlotContext:
    """求解器统一状态载体

    替代旧的 locked_support + assigned_ids + assigned_names + GlobalContext。
    提供按窗口/按槽位的读写接口。

    使用模式：
        ctx = SlotContext.from_layout(operators, layout, params)
        # Phase 各阶段通过 ctx.place() / ctx.vacate() 修改分配
        # 迭代间通过 ctx.signature() 检测重访
    """

    operators: list = field(default_factory=list)
    op_lookup: dict = field(default_factory=dict)
    params: "SolverParams | None" = None
    layout: "LayoutConfig | None" = None
    num_windows: int = 1

    windows: list[WindowState] = field(default_factory=list)

    lambda_ops: dict[str, float] = field(default_factory=dict)
    hours_used: dict[str, float] = field(default_factory=dict)

    prev_P: float = 0.0
    visited: set[str] = field(default_factory=set)

    # ── 工厂方法 ──────────────────────────────────────────

    @classmethod
    def from_layout(
        cls,
        operators: list,
        layout: "LayoutConfig",
        params: "SolverParams",
        *,
        num_windows: int = 1,
    ) -> "SlotContext":
        """从布局配置构建空上下文

        为每个房间 × 槽位生成空 SlotAssignment。
        """
        from steward_core.models import Operator

        op_lookup = {op.char_id: op for op in operators}

        windows = []
        for _ in range(num_windows):
            assignments = []
            for room in layout.rooms:
                for s in range(room.slots):
                    slot_id = _make_slot_id(room.room_type, room.room_index, s)
                    assignments.append(SlotAssignment(
                        slot_id=slot_id,
                        facility_type=room.room_type,
                        product=room.product or "",
                        operator_name="",
                        room_index=room.room_index,
                    ))
            windows.append(WindowState(assignments=assignments))

        return cls(
            operators=operators,
            op_lookup=op_lookup,
            params=params,
            layout=layout,
            num_windows=num_windows,
            windows=windows,
        )

    # ── 槽位读写 ──────────────────────────────────────────

    def place(self, window_idx: int, slot_id: str, op_name: str) -> None:
        """将干员放入指定槽位"""
        for a in self.windows[window_idx].assignments:
            if a.slot_id == slot_id:
                a.operator_name = op_name
                return
        raise KeyError(f"槽位不存在: {slot_id}")

    def vacate(self, window_idx: int, slot_id: str) -> str:
        """清空槽位，返回原干员名"""
        for a in self.windows[window_idx].assignments:
            if a.slot_id == slot_id:
                name = a.operator_name
                a.operator_name = ""
                return name
        raise KeyError(f"槽位不存在: {slot_id}")

    def get_op(self, window_idx: int, slot_id: str) -> str:
        """读取槽位当前干员名"""
        for a in self.windows[window_idx].assignments:
            if a.slot_id == slot_id:
                return a.operator_name
        return ""

    def assigned_ids(self, window_idx: int = 0) -> set[str]:
        """已分配干员的 char_id 集合"""
        name_to_id = {op.name: op.char_id for op in self.op_lookup.values()}
        result = set()
        for a in self.windows[window_idx].assignments:
            if a.operator_name and a.operator_name in name_to_id:
                result.add(name_to_id[a.operator_name])
        return result

    def assigned_names(self, window_idx: int = 0) -> set[str]:
        """已分配干员的名字集合"""
        return {a.operator_name for a in self.windows[window_idx].assignments
                if a.operator_name}

    def slots_of_type(self, window_idx: int, facility_type: str) -> list[SlotAssignment]:
        """获取指定设施类型的所有槽位"""
        return [a for a in self.windows[window_idx].assignments
                if a.facility_type == facility_type]

    def ops_of_type(self, window_idx: int, facility_type: str) -> list[str]:
        """获取指定设施类型中已分配的干员名"""
        return [a.operator_name for a in self.slots_of_type(window_idx, facility_type)
                if a.operator_name]

    def room_slots(self, window_idx: int, facility_type: str, room_index: int) -> list[SlotAssignment]:
        """获取指定房间的所有槽位"""
        return [a for a in self.windows[window_idx].assignments
                if a.facility_type == facility_type and a.room_index == room_index]

    def room_ops(
        self, window_idx: int, facility_type: str, room_index: int
    ) -> list[str]:
        """获取指定房间已分配的干员名"""
        return [a.operator_name for a in self.room_slots(window_idx, facility_type, room_index)
                if a.operator_name]

    # ── 迭代支持 ──────────────────────────────────────────

    def signature(self, window_idx: int = 0) -> str:
        """生成分配方案的标准化签名（用于记忆去重）

        按 slot_id 排序，确保同一分配不同表示得出相同签名。
        """
        parts = []
        for a in sorted(self.windows[window_idx].assignments, key=lambda x: x.slot_id):
            parts.append(f"{a.slot_id}={a.operator_name}")
        return "|".join(parts)

    def clone(self) -> "SlotContext":
        """深拷贝上下文（迭代中生成新候选方案用）"""
        import copy
        return copy.deepcopy(self)


_FACILITY_PREFIX = {
    "Mfg": "mfg",
    "Trade": "trade",
    "Control": "control",
    "Power": "power",
    "Reception": "reception",
    "Office": "office",
    "Dormitory": "dorm",
    "Training": "training",
    "Workshop": "workshop",
}


def _make_slot_id(facility_type: str, room_index: int, slot_index: int) -> str:
    """生成全局唯一槽位 ID

    >>> _make_slot_id("Mfg", 0, 0)
    'mfg_0_0'
    >>> _make_slot_id("Trade", 1, 2)
    'trade_1_2'
    """
    prefix = _FACILITY_PREFIX.get(facility_type, facility_type.lower())
    return f"{prefix}_{room_index}_{slot_index}"
