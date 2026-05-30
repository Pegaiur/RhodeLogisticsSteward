"""槽位迭代策略——基于状态不动点迭代的混合求解

Phase A/B: Mfg/Trade 穷举（含完整联动求值）——保留组合搜索以避免类型 4/6 的精度损失
Phase C/D: Control/Power/Reception/Office/Dormitory contribution 贪心——用偏导数传导
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from steward_core.models import Operator, RoomAssignment, ShiftPlan, SolveResult, LayoutConfig

from ..config import SolverConfig
from ..strategy import PartialSolution, Strategy
from ..slot_iteration import (
    IterationContext,
    extract_state_vector,
    compute_partial_derivatives,
    contribution,
)

if TYPE_CHECKING:
    from ..strategy import PartialSolution as PartialSolutionType

_LAYOUT_243 = LayoutConfig.layout_243()


class SlotIterationStrategy(Strategy):
    """混合迭代求解策略

    热启动: A₀ = BaselineStrategy 结果
    迭代循环: Sₖ → Dₖ → Phase A/B 穷举 → Phase C/D contribution 贪心
    终止: 记忆机制防退化 + 收敛检测
    """

    name = "slot_iter"

    def __init__(self, cold_start: bool = False):
        self._cold_start = cold_start  # 第二期实现：S₀_max 冷启动替代热启动

    def execute(
        self,
        operators: list[Operator],
        config: SolverConfig,
        op_lookup: dict[str, Operator],
    ) -> SolveResult:
        max_rounds = config.params.slot_max_rounds if hasattr(config.params, "slot_max_rounds") else 5
        shift_hours = config.params.shift_hours

        baseline_result = self._hot_start(operators, config, op_lookup)
        A = self._assignments_from_result(baseline_result)

        if not A:
            return baseline_result

        S_vec = extract_state_vector(A, op_lookup)
        D_vec = compute_partial_derivatives(A, shift_hours, op_lookup)
        V: set[tuple] = set()

        for _round in range(max_rounds):
            ctx = IterationContext(
                window_index=0,
                window_hours=shift_hours,
                S=S_vec,
                D=D_vec,
                lambda_op={},
            )

            A = self._phase_ab_mfg_trade(ctx, A, operators, op_lookup, config)
            A = self._phase_c_control(ctx, A, operators, op_lookup, config)
            A = self._phase_d_remaining(ctx, A, operators, op_lookup, config)

            S_vec = extract_state_vector(A, op_lookup)
            D_vec = compute_partial_derivatives(A, shift_hours, op_lookup)

            key = self._assignment_key(A)
            if key in V:
                break
            V.add(key)

        return self._result_from_assignments(A, operators, config, op_lookup)

    def _hot_start(
        self,
        operators: list[Operator],
        config: SolverConfig,
        op_lookup: dict[str, Operator],
    ) -> SolveResult:
        """从 BaselineStrategy 获取初始解 A₀"""
        from ..strategies.baseline import BaselineStrategy

        baseline_config = SolverConfig(
            params=config.params,
            mood_ctx=config.mood_ctx,
        )
        baseline = BaselineStrategy()
        return baseline.execute(operators, baseline_config, op_lookup)

    def _assignments_from_result(self, result: SolveResult) -> list[RoomAssignment]:
        """从 SolveResult 提取 assignments 列表的深拷贝"""
        if not result.plans:
            return []
        return [
            RoomAssignment(
                room_type=a.room_type,
                room_index=a.room_index,
                operators=list(a.operators),
                product=a.product,
                autofill=a.autofill,
            )
            for a in result.plans[0].assignments
        ]

    def _assignment_key(self, assignments: list[RoomAssignment]) -> tuple:
        """生成分配方案的不可变键（用于记忆集合）"""
        items = []
        for a in assignments:
            if a.operators:
                items.append((
                    a.room_type,
                    a.room_index,
                    a.product,
                    tuple(sorted(a.operators)),
                ))
        return tuple(sorted(items))

    def _phase_ab_mfg_trade(
        self,
        ctx: IterationContext,
        A: list[RoomAssignment],
        operators: list[Operator],
        op_lookup: dict[str, Operator],
        config: SolverConfig,
    ) -> list[RoomAssignment]:
        """Phase A/B: Mfg + Trade 穷举（复用 BaselineStrategy 的 exhaust_mfg/exhaust_trade）

        构建 PartialSolution 快照 → 调用 exhaust 模块 → 提取 Mfg/Trade 分配。
        """
        from ..exhaust_mfg import exhaust_mfg
        from ..exhaust_trade import exhaust_trade
        from steward_core.synergy._derived import MFG_ANCHORS

        state = PartialSolution.empty()

        control_assignments = [a for a in A if a.room_type == "Control"]
        dorm_assignments = [a for a in A if a.room_type == "Dormitory"]

        for a in control_assignments:
            for name in a.operators:
                if name in op_lookup:
                    state.assigned_ids.add(op_lookup[name].char_id)
                    state.assigned_names.add(name)

        for a in dorm_assignments:
            for name in a.operators:
                if name in op_lookup:
                    state.assigned_ids.add(op_lookup[name].char_id)
                    state.assigned_names.add(name)

        mfg_result = exhaust_mfg(
            operators=operators,
            assigned_ids=state.assigned_ids,
            assigned_names=state.assigned_names,
            assignments=state.assignments,
            op_lookup=op_lookup,
            locked_support=state.locked_support,
            anchor_names=MFG_ANCHORS,
            config=config,
        )

        trade_result = exhaust_trade(
            operators=operators,
            assigned_ids=state.assigned_ids,
            assigned_names=state.assigned_names,
            assignments=state.assignments,
            op_lookup=op_lookup,
            locked_support=state.locked_support,
            config=config,
        )

        new_A: list[RoomAssignment] = []
        mfg_trade_assignments = [
            a for a in state.assignments
            if a.room_type in ("Mfg", "Trade")
        ]

        for a in A:
            if a.room_type in ("Mfg", "Trade"):
                replacement = next(
                    (ma for ma in mfg_trade_assignments
                     if ma.room_type == a.room_type and ma.room_index == a.room_index),
                    None,
                )
                if replacement is not None:
                    new_A.append(replacement)
                    mfg_trade_assignments.remove(replacement)
                else:
                    new_A.append(RoomAssignment(
                        room_type=a.room_type,
                        room_index=a.room_index,
                        operators=[],
                        product=a.product,
                        autofill=True,
                    ))
            else:
                new_A.append(RoomAssignment(
                    room_type=a.room_type,
                    room_index=a.room_index,
                    operators=list(a.operators),
                    product=a.product,
                    autofill=a.autofill,
                ))

        return new_A

    def _phase_c_control(
        self,
        ctx: IterationContext,
        A: list[RoomAssignment],
        operators: list[Operator],
        op_lookup: dict[str, Operator],
        config: SolverConfig,
    ) -> list[RoomAssignment]:
        """Phase C: Control 槽位 contribution 贪心"""
        from steward_core.synergy import get_system_contributors

        max_slots = config.params.control_max_slots

        assigned_names: set[str] = set()
        for a in A:
            if a.room_type == "Control":
                continue
            assigned_names.update(a.operators)

        control_candidates = [
            op for op in operators
            if op.has_skill_for("Control", None) and op.name not in assigned_names
        ]

        ctrl_global_names = set(get_system_contributors("Control", "global_bonus"))

        scored = []
        for op in control_candidates:
            c = contribution(op.name, "Control", ctx, op_lookup, A)
            if c > float("-inf"):
                bias = config.params.control_global_sort_bias if op.name in ctrl_global_names else 0.0
                scored.append((c + bias, op.name))

        scored.sort(key=lambda x: -x[0])

        selected_names: list[str] = []
        for _, name in scored:
            if len(selected_names) >= max_slots:
                break
            if name not in assigned_names:
                selected_names.append(name)
                assigned_names.add(name)

        new_A: list[RoomAssignment] = []
        control_slot = 0
        for a in A:
            if a.room_type == "Control":
                slot_names = selected_names[control_slot:control_slot + 1] if control_slot < len(selected_names) else []
                new_A.append(RoomAssignment(
                    room_type="Control",
                    room_index=a.room_index,
                    operators=list(slot_names),
                    product=a.product,
                ))
                control_slot += 1
            else:
                new_A.append(RoomAssignment(
                    room_type=a.room_type,
                    room_index=a.room_index,
                    operators=list(a.operators),
                    product=a.product,
                    autofill=a.autofill,
                ))

        for i in range(control_slot, 5):
            new_A.append(RoomAssignment(
                room_type="Control",
                room_index=i,
                operators=[],
                product=None,
                autofill=True,
            ))

        return new_A

    def _phase_d_remaining(
        self,
        ctx: IterationContext,
        A: list[RoomAssignment],
        operators: list[Operator],
        op_lookup: dict[str, Operator],
        config: SolverConfig,
    ) -> list[RoomAssignment]:
        """Phase D: Power/Reception/Office/Dormitory contribution 贪心"""
        A = self._phase_d_power(ctx, A, operators, op_lookup, config)
        A = self._phase_d_reception(ctx, A, operators, op_lookup)
        A = self._phase_d_office(ctx, A, operators, op_lookup)
        A = self._phase_d_dormitory(ctx, A, operators, op_lookup, config)
        return A

    def _assigned_names_except(
        self,
        A: list[RoomAssignment],
        except_room: str,
    ) -> set[str]:
        names: set[str] = set()
        for a in A:
            if a.room_type == except_room:
                continue
            names.update(a.operators)
        return names

    def _phase_d_power(
        self,
        ctx: IterationContext,
        A: list[RoomAssignment],
        operators: list[Operator],
        op_lookup: dict[str, Operator],
        config: SolverConfig,
    ) -> list[RoomAssignment]:
        assigned = self._assigned_names_except(A, "Power")

        candidates = [
            op for op in operators
            if op.has_skill_for("Power", None) and op.name not in assigned
        ]

        scored = []
        for op in candidates:
            c = contribution(op.name, "Power", ctx, op_lookup, A)
            if c > float("-inf"):
                scored.append((c, op.name))

        scored.sort(key=lambda x: -x[0])
        selected = [name for _, name in scored[:3]]

        new_A: list[RoomAssignment] = []
        power_idx = 0
        for a in A:
            if a.room_type == "Power":
                slot_name = selected[power_idx] if power_idx < len(selected) else None
                new_A.append(RoomAssignment(
                    room_type="Power",
                    room_index=a.room_index,
                    operators=[slot_name] if slot_name else [],
                    product=a.product,
                    autofill=slot_name is None,
                ))
                power_idx += 1
            else:
                new_A.append(RoomAssignment(
                    room_type=a.room_type,
                    room_index=a.room_index,
                    operators=list(a.operators),
                    product=a.product,
                    autofill=a.autofill,
                ))

        return new_A

    def _phase_d_reception(
        self,
        ctx: IterationContext,
        A: list[RoomAssignment],
        operators: list[Operator],
        op_lookup: dict[str, Operator],
    ) -> list[RoomAssignment]:
        assigned = self._assigned_names_except(A, "Reception")

        candidates = [
            op for op in operators
            if op.has_skill_for("Reception", None) and op.name not in assigned
        ]

        scored = []
        for op in candidates:
            c = contribution(op.name, "Reception", ctx, op_lookup, A)
            if c > float("-inf"):
                scored.append((c, op.name))

        scored.sort(key=lambda x: -x[0])
        selected = [name for _, name in scored[:2]]

        new_A: list[RoomAssignment] = []
        reception_idx = 0
        for a in A:
            if a.room_type == "Reception":
                slot_names = selected[reception_idx:reception_idx + 2] if reception_idx < len(selected) else []
                new_A.append(RoomAssignment(
                    room_type="Reception",
                    room_index=a.room_index,
                    operators=slot_names,
                    product=a.product,
                    autofill=not slot_names,
                ))
                reception_idx += 1
            else:
                new_A.append(RoomAssignment(
                    room_type=a.room_type,
                    room_index=a.room_index,
                    operators=list(a.operators),
                    product=a.product,
                    autofill=a.autofill,
                ))

        return new_A

    def _phase_d_office(
        self,
        ctx: IterationContext,
        A: list[RoomAssignment],
        operators: list[Operator],
        op_lookup: dict[str, Operator],
    ) -> list[RoomAssignment]:
        assigned = self._assigned_names_except(A, "Office")

        candidates = [
            op for op in operators
            if op.has_skill_for("Office", None) and op.name not in assigned
        ]

        scored = []
        for op in candidates:
            c = contribution(op.name, "Office", ctx, op_lookup, A)
            if c > float("-inf"):
                scored.append((c, op.name))

        scored.sort(key=lambda x: -x[0])
        selected = [name for _, name in scored[:1]]

        new_A: list[RoomAssignment] = []
        office_idx = 0
        for a in A:
            if a.room_type == "Office":
                slot_name = selected[office_idx] if office_idx < len(selected) else None
                new_A.append(RoomAssignment(
                    room_type="Office",
                    room_index=a.room_index,
                    operators=[slot_name] if slot_name else [],
                    product=a.product,
                    autofill=slot_name is None,
                ))
                office_idx += 1
            else:
                new_A.append(RoomAssignment(
                    room_type=a.room_type,
                    room_index=a.room_index,
                    operators=list(a.operators),
                    product=a.product,
                    autofill=a.autofill,
                ))

        return new_A

    def _phase_d_dormitory(
        self,
        ctx: IterationContext,
        A: list[RoomAssignment],
        operators: list[Operator],
        op_lookup: dict[str, Operator],
        config: SolverConfig,
    ) -> list[RoomAssignment]:
        assigned = self._assigned_names_except(A, "Dormitory")

        candidates = [
            op for op in operators
            if op.name not in assigned
        ]

        dorm_candidates = [
            op for op in candidates
            if op.has_skill_for("Dormitory", None)
        ]

        scored = []
        for op in dorm_candidates:
            c = contribution(op.name, "Dormitory", ctx, op_lookup, A)
            if c > float("-inf"):
                scored.append((c, op.name))

        scored.sort(key=lambda x: -x[0])

        dorm_configs = [(5, 4)]
        total_slots = sum(slots for slots, _ in dorm_configs)
        selected = [name for _, name in scored[:total_slots]]

        filler_pool = [op.name for op in candidates if op.name not in {s for _, s in scored}]
        while len(selected) < total_slots and filler_pool:
            selected.append(filler_pool.pop(0))

        new_A: list[RoomAssignment] = []
        slot_ptr = 0
        room_idx = 0
        for a in A:
            if a.room_type == "Dormitory":
                slots = 5
                names = selected[slot_ptr:slot_ptr + slots]
                new_A.append(RoomAssignment(
                    room_type="Dormitory",
                    room_index=room_idx,
                    operators=names,
                    product=a.product,
                    autofill=not names,
                ))
                slot_ptr += slots
                room_idx += 1
            elif a.room_type in ("Training", "Workshop"):
                new_A.append(RoomAssignment(
                    room_type=a.room_type,
                    room_index=a.room_index,
                    operators=[],
                    product=a.product,
                    autofill=True,
                ))
            else:
                new_A.append(RoomAssignment(
                    room_type=a.room_type,
                    room_index=a.room_index,
                    operators=list(a.operators),
                    product=a.product,
                    autofill=a.autofill,
                ))

        return new_A

    def _result_from_assignments(
        self,
        A: list[RoomAssignment],
        operators: list[Operator],
        config: SolverConfig,
        op_lookup: dict[str, Operator],
    ) -> SolveResult:
        """从 assignments 列表构建 SolveResult"""
        half_hours = int(config.params.shift_hours / 2.0)
        plan = ShiftPlan(
            name=f"SlotIter-{int(config.params.shift_hours)}h",
            assignments=A,
            period_from=f"{half_hours:02d}:00",
            period_to=f"{half_hours + int(config.params.shift_hours) - 1:02d}:59",
        )
        return SolveResult(
            plans=[plan],
            autofill_count=sum(1 for a in A if a.autofill),
            config_used=config,
        )
