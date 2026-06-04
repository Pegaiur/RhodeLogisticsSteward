"""全局上下文构造器

统一 buff_pool、global_bonus、effective_power 的构建逻辑，
消除 support.py / exhaust_trade.py / production.py 中的重复实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from steward_core.constants import BASE_POWER_COUNT
from steward_core.models import LayoutConfig
from steward_core.synergy import (
    compute_control_global_bonus,
    compute_buff_pool,
    _has_power_count_modifier,
    GlobalBonus,
    BuffPool,
)

if TYPE_CHECKING:
    from steward_core.models import Operator, RoomAssignment, ShiftPlan
    from steward_core.mood_flow import MoodContext
    from .params import SolverParams


@dataclass
class GlobalContext:
    """求解过程中的全局状态快照

    所有评估函数共享同一个构造路径，确保 buff_pool、有效发电站数
    等全局状态的计算口径完全一致。
    """

    global_bonus: GlobalBonus = field(default_factory=GlobalBonus)
    buff_pool: BuffPool | None = None
    effective_power: int = BASE_POWER_COUNT
    control_operators: list = field(default_factory=list)
    dorm_operators: list = field(default_factory=list)
    all_assignments: dict[str, list] = field(default_factory=dict)

    @classmethod
    def from_estimated(
        cls,
        control_operators: list[Operator],
        dorm_operators: list[Operator],
        all_operators: list[Operator],
        assigned_names: set[str],
        params: "SolverParams",
        *,
        mfg_operators: list[Operator] | None = None,
        trade_operators: list[Operator] | None = None,
        office_operators: list[Operator] | None = None,
        ling_mood_below_12: bool = False,
        xi_mood_below_12: bool | None = None,
        mood_ctx: "MoodContext | None" = None,
        office_perception_base: int = 20,
        effective_power: int | None = None,
    ) -> "GlobalContext":
        """从估计数据构建上下文（Phase 1/3a 预评估用）

        用于尚未完成完整排班的阶段：
        - Phase 1 Mfg 评估：control/dorm 来自 available_support
        - Phase 3a Trade 评估：dorm 为估计占位干员

        mood_ctx 不为 None 时优先从其实值提取心情门控 bool，
        否则使用显式传入的参数（向后兼容）。
        effective_power 可由调用方预计算传入以跳过全量 _has_power_count_modifier 扫描。
        """
        global_bonus = compute_control_global_bonus(control_operators)

        if mood_ctx is not None:
            ling_mood_below_12 = mood_ctx.is_below("令", 12.0)
            xi_mood_below_12 = mood_ctx.is_below("夕", 12.0)

        buff_pool = compute_buff_pool(
            control_operators,
            dorm_operators=dorm_operators,
            dorm_level=params.dorm_level,
            mfg_operators=mfg_operators,
            trade_operators=trade_operators,
            office_operators=office_operators,
            office_perception_base=office_perception_base,
            ling_mood_below_12=ling_mood_below_12,
            xi_mood_below_12=xi_mood_below_12,
            layout=LayoutConfig.layout_243(),
        )

        if effective_power is None:
            effective_power = BASE_POWER_COUNT + sum(
                1 for op in all_operators
                if op.name not in assigned_names and _has_power_count_modifier(op)
            )
        # 森蚺"我寻思能行"：Lancet-2 可用时若森蚺在中枢则+2
        if any(op.name == "Lancet-2" for op in all_operators):
            for op in control_operators:
                if any(s.buff_id == "control_pow_bot[000]" for s in op.skills):
                    effective_power += 2
                    break

        return cls(
            global_bonus=global_bonus,
            buff_pool=buff_pool,
            effective_power=effective_power,
            control_operators=control_operators,
            dorm_operators=dorm_operators,
        )

    @classmethod
    def from_plan(
        cls,
        plan: "ShiftPlan",
        all_operators: list[Operator],
        params: "SolverParams",
        mood_ctx: "MoodContext | None" = None,
    ) -> "GlobalContext":
        """从已完成的排班方案构建上下文（production 评估用）

        从实际 assignment 中提取控制中枢、宿舍、以及 buff 生成者是否在
        工作设施中的布尔状态。
        mood_ctx 不为 None 时优先从其实值提取心情门控 bool，
        否则回退到旧代理（ling_mood_below_12 = 迷迭香在 Mfg）。
        """
        from steward_core.models import Operator
        from steward_core.synergy import _B_ROSEMARY, _B_EBENHOLZ

        op_lookup = {op.name: op for op in all_operators}

        def _room_ops(room_type: str) -> list[Operator]:
            names: list[str] = []
            for a in plan.assignments:
                if a.room_type == room_type:
                    names.extend(a.operators)
            return [op_lookup[n] for n in names if n in op_lookup]

        control_ops = _room_ops("Control")
        dorm_ops = _room_ops("Dormitory")
        mfg_ops = _room_ops("Mfg")
        trade_ops = _room_ops("Trade")
        office_ops = _room_ops("Office")

        global_bonus = compute_control_global_bonus(control_ops)

        if mood_ctx is not None:
            ling_mood_below_12 = mood_ctx.is_below("令", 12.0)
            xi_mood_below_12 = mood_ctx.is_below("夕", 12.0)
        else:
            ling_mood_below_12 = any(
                op.name == _B_ROSEMARY for op in mfg_ops
            )
            xi_mood_below_12 = None

        buff_pool = compute_buff_pool(
            control_ops,
            dorm_operators=dorm_ops,
            dorm_level=params.dorm_level,
            mfg_operators=mfg_ops,
            trade_operators=trade_ops,
            office_operators=office_ops,
            office_perception_base=params.office_perception_base,
            ling_mood_below_12=ling_mood_below_12,
            xi_mood_below_12=xi_mood_below_12,
            layout=LayoutConfig.layout_243(),
        )

        effective_power = BASE_POWER_COUNT + sum(
            1 for op in all_operators
            if _has_power_count_modifier(op)
        )
        # 森蚺"我寻思能行"：Lancet-2 在发电站时若森蚺在中枢则+2
        lancet_in_power = any(
            a.room_type == "Power" and "Lancet-2" in a.operators
            for a in plan.assignments
        )
        if lancet_in_power:
            for op in control_ops:
                if any(s.buff_id == "control_pow_bot[000]" for s in op.skills):
                    effective_power += 2
                    break

        all_assignments: dict[str, list[Operator]] = {}
        for a in plan.assignments:
            if a.room_type not in all_assignments:
                all_assignments[a.room_type] = []
            for name in a.operators:
                if name in op_lookup:
                    op = op_lookup[name]
                    if op not in all_assignments[a.room_type]:
                        all_assignments[a.room_type].append(op)

        return cls(
            global_bonus=global_bonus,
            buff_pool=buff_pool,
            effective_power=effective_power,
            control_operators=control_ops,
            dorm_operators=dorm_ops,
            all_assignments=all_assignments,
        )
