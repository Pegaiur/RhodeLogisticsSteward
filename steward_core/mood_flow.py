"""心情流转引擎 — MoodContext + MoodModifiers

统一的心情状态容器，替代分散的硬编码 bool（ling_mood_below_12 等）。
MoodModifiers 是全局心情修正器，与 BuffPool 同构：全局生成 → 不可变传递 → 逐设施消费。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from steward_core.models import Operator
    from steward_core.synergy.buff_pool import BuffPool
    from steward_core.solver.params import SolverParams


@dataclass
class MoodModifiers:
    """全局心情修正器 — 一次计算，供所有工作/宿舍干员使用

    与 BuffPool 同构：全局生成 → 不可变传递 → 逐设施消费。
    差异：这里是速率修正（浮点），不是可消耗资源（整数）。
    """

    control_recovery: float = 0.0
    """中枢内部恢复速率（control_mp_cost 系列：每名中枢干员 +0.05/h）"""

    mlynar_spread: bool = False
    """玛恩纳公事公办：将 control_recovery 扩散至工作设施"""

    global_work_recovery: float = 0.0
    """工作设施全局恢复（玛恩纳直接提供 +0.1/h）"""

    yanhuo_recovery: float = 0.0
    """重岳孤光共照：+0.05 + 烟火÷20×0.05/h"""

    dorm_bonus_all: float = 0.0
    """中枢→宿舍恢复加成，适用全体宿舍干员（control_dorm_rec[000]~[002]、control_dorm_rec2[000]）"""

    dorm_bonus_elite: float = 0.0
    """中枢→宿舍恢复加成，仅适用精英干员（control_dorm_rec_tag[001] 阿斯卡纶）"""

    def dorm_bonus_for(self, op: "Operator") -> float:
        """根据干员类型返回适用的宿舍恢复加成"""
        bonus = self.dorm_bonus_all
        if op.rarity >= 5:
            bonus = max(bonus, self.dorm_bonus_elite)
        return bonus


def compute_mood_modifiers(
    control_operators: list["Operator"],
    buff_pool: "BuffPool | None",
) -> MoodModifiers:
    """从控制中枢配置计算全局心情修正器

    覆盖：control_mp_cost 系列（9条）、control_mp_lonely（1条）、
          control_dorm_rec 系列（5条）、重岳孤光共照。
    未覆盖：Per-operator 恢复（菲亚梅塔/塑心/车尔尼）— 由 evaluate_dorm_recovery() 处理。
    """
    mods = MoodModifiers()
    names = {op.name for op in control_operators}

    mods.control_recovery = len(control_operators) * 0.05

    if any(
        s.buff_id == "control_mp_lonely[000]"
        for op in control_operators
        for s in op.skills
    ):
        mods.mlynar_spread = True
        mods.global_work_recovery = 0.1

    if "重岳" in names and buff_pool is not None:
        mods.yanhuo_recovery = 0.05 + (buff_pool.yanhuo // 20) * 0.05

    for op in control_operators:
        for s in op.skills:
            if s.buff_id.startswith("control_dorm_rec_tag"):
                val = s.efficient.max_value()
                if val > mods.dorm_bonus_elite:
                    mods.dorm_bonus_elite = val
            elif s.buff_id.startswith("control_dorm_rec"):
                val = s.efficient.max_value()
                if val > mods.dorm_bonus_all:
                    mods.dorm_bonus_all = val

    return mods


def compute_global_burn(
    control_operators: list["Operator"],
    buff_pool: "BuffPool",
    worker_count: int = 3,
) -> float:
    """计算工作干员的心情消耗率净值 (mood_burn)

    迁移自 synergy/mood.py，保留原接口以兼容存量调用方。
    最终将被 MoodContext.work_burn() 替代。
    base = 1.0 - 0.05 × (worker_count - 1)，3 工位 → 0.90。
    """
    base = 1.0 - 0.05 * max(0, worker_count - 1)

    modifiers = compute_mood_modifiers(control_operators, buff_pool)
    recovery = modifiers.control_recovery + modifiers.yanhuo_recovery
    if modifiers.mlynar_spread:
        recovery += modifiers.control_recovery + modifiers.global_work_recovery
    return max(0.0, base - recovery)


@dataclass
class MoodContext:
    """统一的心情状态上下文，替代所有分散的硬编码 bool

    所有需要心情感知的函数从本结构读取，不再接受散列的心情 bool 参数。
    不可变操作：after_shift()/after_recovery() 返回新实例，适合 K-Beam 分叉。
    """

    operator_moods: dict[str, float] = field(default_factory=dict)
    """干员名 → 当前心情值 (0.0 ~ 24.0)"""

    modifiers: MoodModifiers | None = None
    """全局心情修正器（惰性计算或显式设置）"""

    warmup_hours: dict[str, float] = field(default_factory=dict)
    """干员名 → 已连续工作小时数（离开工位归零，菲亚梅塔交换后保持）"""

    fiammetta_swap_planned: bool = False
    """求解器已规划菲亚梅塔交换（用于输出层 Fiammetta.enable）"""

    fiammetta_target: str = ""
    """菲亚梅塔交换目标干员名（用于输出层 Fiammetta.target）"""

    control_operators: list[str] = field(default_factory=list)
    """中枢干员名列表（用于计算全局减免）"""

    dorm_assignments: dict[str, str] | None = None
    """宿舍分配: {干员名 → 宿舍编号}。None 表示宿舍尚未分配"""

    shift_hours: float = 12.0
    """当前班次时长"""

    params: "SolverParams | None" = None
    """求解器参数（用于读取心情阈值等配置）"""

    _op_lookup: dict[str, "Operator"] = field(default_factory=dict, repr=False)
    """干员名 → Operator 对象（内置查找表，供 ensure_modifiers 解析 skills）"""

    @classmethod
    def fresh(
        cls,
        operators: list["Operator"],
        params: "SolverParams | None" = None,
    ) -> "MoodContext":
        """从全量干员池构造初始心情上下文（所有干员满心情 24.0）"""
        return cls(
            operator_moods={op.name: 24.0 for op in operators},
            warmup_hours={},
            params=params,
            _op_lookup={op.name: op for op in operators},
        )

    def mood_of(self, name: str) -> float:
        """获取干员心情值，未记录则返回满值"""
        return self.operator_moods.get(name, 24.0)

    def is_below(self, name: str, threshold: float = 12.0) -> bool:
        """心情是否低于阈值"""
        return self.mood_of(name) < threshold

    def _resolve_control_operators(self) -> list["Operator"]:
        """将 control_operators 名列表解析为 Operator 对象列表

        优先使用 _op_lookup，缺失时构造伪对象（仅含 name，无 skills）。
        调用方应确保在 fresh() 时注入 _op_lookup 以获得完整的 modifiers 计算。
        """
        from steward_core.models import Operator as OpModel

        result = []
        for name in self.control_operators:
            op = self._op_lookup.get(name)
            if op is None:
                op = OpModel(char_id="", name=name)
            result.append(op)
        return result

    def ensure_modifiers(self, buff_pool: "BuffPool | None" = None) -> MoodModifiers:
        """惰性初始化全局心情修正器

        首次调用时从 control_operators + _op_lookup 计算并缓存到 self.modifiers。
        需要 _op_lookup 已填充（通过 fresh() 或显式设置），
        否则玛恩纳扩散/dorm_bonus 检测无法生效（伪 Operator 无 skills）。
        """
        if self.modifiers is not None:
            return self.modifiers
        ops = self._resolve_control_operators()
        object.__setattr__(self, "modifiers", compute_mood_modifiers(ops, buff_pool))
        return self.modifiers

    def work_burn(
        self,
        name: str,
        room_type: str,
        room_slots: int = 3,
        buff_pool: "BuffPool | None" = None,
    ) -> float:
        """计算单干员工作消耗率净值 (mood_burn)

        公式: base - recovery_modifiers
          base = 1.0 - 0.05 × (room_slots - 1)，3 工位 → 0.90
          recovery = control_recovery + yanhuo_recovery + (mlynar spread)
        """
        base = 1.0 - 0.05 * max(0, room_slots - 1)
        modifiers = self.ensure_modifiers(buff_pool)
        recovery = modifiers.control_recovery + modifiers.yanhuo_recovery
        if modifiers.mlynar_spread:
            recovery += modifiers.control_recovery + modifiers.global_work_recovery
        return max(0.0, base - recovery)

    def room_burn(
        self,
        operators: list["Operator"],
        room_type: str,
        buff_pool: "BuffPool | None" = None,
    ) -> float:
        """计算房间内工作干员的平均净消耗率（供 evaluate_room 使用）

        取所有干员 work_burn 的最大值（最差者决定截断时点）。
        """
        if not operators:
            return 0.0
        slots = len(operators)
        return max(
            self.work_burn(op.name, room_type, slots, buff_pool)
            for op in operators
        )

    def dorm_recovery(
        self,
        name: str,
        dorm_mates: list["Operator"] | None = None,
    ) -> float:
        """计算干员在宿舍中的恢复速率 (mood_recovery/h)

        当 dorm_assignments 已设置时从内部查询同宿舍干员；
        当 dorm_assignments=None 时使用传入的 dorm_mates（评估候选配置）。
        委托给 evaluate_dorm_recovery() 独立函数执行实际计算。
        """
        from steward_core.dorm_recovery import evaluate_dorm_recovery
        from steward_core.models import Operator as OpModel

        op = self._op_lookup.get(name)
        if op is None:
            op = OpModel(char_id="", name=name)

        if dorm_mates is None and self.dorm_assignments is not None:
            target_dorm = self.dorm_assignments.get(name)
            if target_dorm is not None:
                dorm_mates = [
                    self._op_lookup[n] for n, d in self.dorm_assignments.items()
                    if d == target_dorm and n in self._op_lookup
                ]
            else:
                dorm_mates = [op]

        if dorm_mates is None:
            dorm_mates = [op]

        modifiers = self.ensure_modifiers()
        yanhuo_bonus = 0.0
        if self.modifiers and self.modifiers.yanhuo_recovery > 0.0:
            yanhuo_bonus = max(0.0, self.modifiers.yanhuo_recovery - 0.05)

        return evaluate_dorm_recovery(
            dorm_ops=dorm_mates,
            target_op=op,
            dorm_bonus_all=modifiers.dorm_bonus_all,
            dorm_bonus_elite=modifiers.dorm_bonus_elite,
            yanhuo_bonus=yanhuo_bonus,
        )

    def after_shift(
        self,
        working_names: set[str],
        shift_hours_override: float | None = None,
    ) -> "MoodContext":
        """应用一个班次后的心情变化（不可变，返回新实例）

        working_names: 本班次工作的干员名集合
        shift_hours_override: 覆盖默认班次时长（用于测试/自定义班次）

        注意：当前对所有工作设施使用相同的 work_burn 公式（3 工位基础）。
        不同工位数设施（Trade 2/3 工位、Power 1 工位）的 burn 差异
        将在 mood_burn 激活后通过 per-room 计算修正。
        """
        hours = shift_hours_override if shift_hours_override is not None else self.shift_hours
        new_moods = dict(self.operator_moods)
        new_warmup = dict(self.warmup_hours)

        for name in self.operator_moods:
            if name in working_names:
                if name not in self.control_operators:
                    burn = self.work_burn(name, "Mfg", 3)
                    new_moods[name] = max(0.0, new_moods[name] - burn * hours)
                new_warmup[name] = self.warmup_hours.get(name, 0.0) + hours
            else:
                new_warmup.pop(name, None)

        return replace(
            self,
            operator_moods=new_moods,
            warmup_hours=new_warmup,
        )

    def after_recovery(self, hours: float) -> "MoodContext":
        """应用恢复间隔后的心情变化（不可变，返回新实例）

        hours: 恢复时长
        宿舍中的干员按 dorm_recovery() 速率恢复，上限 24.0。
        中枢干员不受影响。
        暖机状态（warmup_hours）在宿舍恢复后归零——干员离开工位后爬升进度重置。
        菲亚梅塔交换是唯一保留暖机的途径（尚未实现，待后续建模）。
        """
        new_moods = dict(self.operator_moods)

        for name in self.operator_moods:
            if name in self.control_operators:
                continue
            recovery_rate = self.dorm_recovery(name)
            if recovery_rate > 0:
                new_moods[name] = min(24.0, new_moods[name] + recovery_rate * hours)

        return replace(self, operator_moods=new_moods, warmup_hours={})

    def qiangan_decay_basis(
        self,
        operators: list["Operator"],
        room_type: str,
        buff_pool: "BuffPool | None" = None,
    ) -> float | None:
        """返回铅踝梯级衰减的初始心情值（供 stepped_efficiency 使用）

        仅在房间内有铅踝时返回非 None。
        """
        names = {op.name for op in operators}
        if "铅踝" not in names:
            return None
        return self.mood_of("铅踝")
