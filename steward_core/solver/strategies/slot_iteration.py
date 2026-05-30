"""槽位迭代策略——基于状态不动点迭代的混合求解

Phase A/B: Mfg/Trade 穷举（含完整联动求值）——保留组合搜索以避免类型 4/6 的精度损失
Phase C/D: Control/Power/Reception/Office/Dormitory contribution 贪心——用偏导数传导
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from steward_core.models import Operator, RoomAssignment, ShiftPlan, SolveResult

from ..config import SolverConfig
from ..strategy import PartialSolution, Strategy
from ..slot_iteration import (
    S_MAX,
    IterationContext,
    _build_slot_links,
    extract_state_vector,
    compute_partial_derivatives,
    contribution,
    update_lambda_bisection,
)

if TYPE_CHECKING:
    pass

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
        if config.params.slot_cold_start:
            return self._execute_cold_start(operators, config, op_lookup)

        hot_result = self._execute_single(operators, config, op_lookup,
                                          cold_start=False)
        return hot_result

    def _execute_single(
        self,
        operators: list[Operator],
        config: SolverConfig,
        op_lookup: dict[str, Operator],
        cold_start: bool = False,
    ) -> SolveResult:
        """单次求解：热启动或冷启动迭代"""
        max_rounds = config.params.slot_max_rounds
        shift_hours = config.params.shift_hours

        if cold_start:
            A = self._cold_start_init(operators, config, op_lookup)
        else:
            baseline_result = self._hot_start(operators, config, op_lookup)
            A = self._assignments_from_result(baseline_result)
            if not A:
                return baseline_result

        if cold_start:
            S_vec = dict(S_MAX)
        else:
            S_vec = extract_state_vector(A, op_lookup)
        D_vec = compute_partial_derivatives(A, shift_hours, op_lookup)
        V: set[tuple] = set()
        lambda_op: dict[str, float] = {}
        best_A = A
        best_S = S_vec
        best_D = D_vec

        for _round in range(max_rounds):
            ctx = IterationContext(
                window_index=0,
                window_hours=shift_hours,
                S=S_vec,
                D=D_vec,
                lambda_op=lambda_op,
                link_value=_build_slot_links(A, shift_hours),
            )

            A_prev = A
            A = self._phase_ab_mfg_trade(ctx, A, operators, op_lookup, config)

            S_vec = extract_state_vector(A, op_lookup)
            D_vec = compute_partial_derivatives(A, shift_hours, op_lookup)
            ctx = IterationContext(
                window_index=0,
                window_hours=shift_hours,
                S=S_vec,
                D=D_vec,
                lambda_op=lambda_op,
                link_value=_build_slot_links(A, shift_hours),
            )

            A = self._phase_c_control(ctx, A, operators, op_lookup, config)
            A = self._phase_d_remaining(ctx, A, operators, op_lookup, config)

            S_vec = extract_state_vector(A, op_lookup)
            D_vec = compute_partial_derivatives(A, shift_hours, op_lookup)

            lambda_op = update_lambda_bisection(lambda_op, A, A_prev, op_lookup, ctx)

            key = self._assignment_key(A)
            if key in V:
                A = self._joint_perturbation(A, A_prev, ctx, V, operators, op_lookup, config)
                if A is not None:
                    S_vec = extract_state_vector(A, op_lookup)
                    D_vec = compute_partial_derivatives(A, shift_hours, op_lookup)
                    lambda_op = update_lambda_bisection(lambda_op, A, A_prev, op_lookup, ctx)
                    best_A = A
                    best_S = S_vec
                    best_D = D_vec
                break
            V.add(key)

            best_A = A
            best_S = S_vec
            best_D = D_vec

        return self._result_from_assignments(best_A, operators, config, op_lookup)

    def _execute_cold_start(
        self,
        operators: list[Operator],
        config: SolverConfig,
        op_lookup: dict[str, Operator],
    ) -> SolveResult:
        """多启动策略：热启动 + 冷启动中取较优者"""
        hot_result = self._execute_single(operators, config, op_lookup, cold_start=False)
        cold_result = self._execute_single(operators, config, op_lookup, cold_start=True)
        hot_A = self._assignments_from_result(hot_result)
        cold_A = self._assignments_from_result(cold_result)
        hot_D = compute_partial_derivatives(hot_A, config.params.shift_hours, op_lookup)
        cold_D = compute_partial_derivatives(cold_A, config.params.shift_hours, op_lookup)
        hot_sum = sum(hot_D.values())
        cold_sum = sum(cold_D.values())
        if cold_sum > hot_sum:
            return cold_result
        return hot_result

    def _cold_start_init(
        self,
        operators: list[Operator],
        config: SolverConfig,
        op_lookup: dict[str, Operator],
    ) -> list[RoomAssignment]:
        """S₀_max 冷启动：构建仅有 Mfg/Trade（空填充）的初始分配，
        D 基于 S_MAX 上界计算

        不依赖 BaselineStrategy——仅填充 Mfg/Trade 为 autofill 空房间，
        让第一轮迭代的偏导数 以 S_MAX 乐观上界驱动 Control/Dorm 选人。
        """
        A: list[RoomAssignment] = []
        room_types = [("Mfg", 0, "CombatRecord"), ("Mfg", 1, "CombatRecord"),
                      ("Mfg", 2, "PureGold"), ("Mfg", 3, "PureGold"),
                      ("Trade", 0, "Money"), ("Trade", 1, "Money"),
                      ("Control", 0, None), ("Power", 0, None),
                      ("Power", 1, None), ("Power", 2, None),
                      ("Reception", 0, "General"), ("Office", 0, "HR"),
                      ("Training", 0, None), ("Workshop", 0, None),
                      ("Dormitory", 0, "Rest"), ("Dormitory", 1, "Rest"),
                      ("Dormitory", 2, "Rest"), ("Dormitory", 3, "Rest")]
        for rt, ri, prod in room_types:
            A.append(RoomAssignment(
                room_type=rt, room_index=ri,
                operators=[], product=prod,
                autofill=True,
            ))
        return A

    def _joint_perturbation(
        self,
        A: list[RoomAssignment],
        A_prev: list[RoomAssignment],
        ctx: IterationContext,
        V: set[tuple],
        operators: list[Operator],
        op_lookup: dict[str, Operator],
        config: SolverConfig,
    ) -> list[RoomAssignment] | None:
        """联合扰动：攻击跨 Phase 鞍点

        耦合对 = 类型 1f 读取者所在 Mfg/Trade 房间 ↔ 写入其消费维度的 Control/Dorm 写入者
        同时替换读者和写入者的 top-3 替代者，检查是否打破鞍点。
        """
        readers_dim = {}
        for a in A:
            if a.room_type not in ("Mfg", "Trade") or not a.operators:
                continue
            for name in a.operators:
                dim = _reader_dimension(name)
                if dim and a.operators:
                    readers_dim[dim] = readers_dim.get(dim, []) + [(a, name)]

        writers_dim = {}
        for a in A:
            if a.room_type not in ("Control", "Dormitory") or not a.operators:
                continue
            for name in a.operators:
                delta = _compute_state_delta_simple(name, a.room_type, A, operators, op_lookup)
                for dim in delta:
                    if delta[dim] != 0:
                        writers_dim[dim] = writers_dim.get(dim, []) + [(a, name)]

        for dim in set(readers_dim.keys()) & set(writers_dim.keys()):
            for reader_a, reader_name in readers_dim[dim][:2]:
                alt_readers = _find_alternatives(
                    reader_a, reader_name, operators, op_lookup, ctx, A, config,
                    count=3,
                )
                for writer_a, writer_name in writers_dim[dim][:2]:
                    alt_writers = _find_alternatives(
                        writer_a, writer_name, operators, op_lookup, ctx, A, config,
                        count=3,
                    )
                    for alt_r in alt_readers:
                        for alt_w in alt_writers:
                            new_A = [RoomAssignment(
                                room_type=a.room_type, room_index=a.room_index,
                                operators=list(a.operators), product=a.product,
                                autofill=a.autofill,
                            ) for a in A]
                            _replace_in_assignments(new_A, reader_name, alt_r, reader_a.room_type)
                            _replace_in_assignments(new_A, writer_name, alt_w, writer_a.room_type)
                            key = self._assignment_key(new_A)
                            if key not in V:
                                return new_A

        return None

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
        """Phase A/B: Mfg + Trade 穷举（复用 exhaust_mfg/exhaust_trade）

        从 A 中的实际中枢/宿舍/Office 构造 BuffPool，通过 override_pool
        传入 exhaust 模块，使穷举评估基于真实中枢上下文而非空白估计。
        """
        from ..exhaust_mfg import exhaust_mfg
        from ..exhaust_trade import exhaust_trade
        from steward_core.synergy._derived import MFG_ANCHORS
        from steward_core.solver.slot_iteration import (
            _DEFAULT_SUICH_COUNT, _DEFAULT_DORM_LEVEL, _room_ops_by_type,
            _LAYOUT_243,
        )
        from steward_core.synergy.buff_pool import compute_buff_pool

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

        ctrl_ops = _room_ops_by_type(A, "Control", op_lookup)
        dorm_ops = _room_ops_by_type(A, "Dormitory", op_lookup)
        office_ops = _room_ops_by_type(A, "Office", op_lookup)

        has_rosmontis = any(
            a.room_type == "Mfg" and "迷迭香" in a.operators for a in A
        )
        has_ebnhlz = any(
            a.room_type == "Trade" and "黑键" in a.operators for a in A
        )
        has_wuyou = any(
            a.room_type == "Trade" and "乌有" in a.operators for a in A
        )
        office_perception = 20 if any(o.name == "絮雨" for o in office_ops) else 0

        override_pool = compute_buff_pool(
            control_operators=ctrl_ops,
            suich_count=_DEFAULT_SUICH_COUNT,
            dorm_operators=dorm_ops if dorm_ops else None,
            dorm_level=_DEFAULT_DORM_LEVEL,
            has_rosmontis_in_mfg=has_rosmontis,
            has_ebnhlz_in_trade=has_ebnhlz,
            has_wuyou_in_trade=has_wuyou,
            perception_from_office=office_perception,
            layout=_LAYOUT_243,
        )

        mfg_result = exhaust_mfg(
            operators=operators,
            assigned_ids=state.assigned_ids,
            assigned_names=state.assigned_names,
            assignments=state.assignments,
            op_lookup=op_lookup,
            locked_support=state.locked_support,
            anchor_names=MFG_ANCHORS,
            config=config,
            override_pool=override_pool,
        )

        trade_result = exhaust_trade(
            operators=operators,
            assigned_ids=state.assigned_ids,
            assigned_names=state.assigned_names,
            assignments=state.assignments,
            op_lookup=op_lookup,
            locked_support=state.locked_support,
            config=config,
            override_pool=override_pool,
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
        """Phase C: Control 槽位顺序贪心——每选一人后重算边际贡献

        对每个候选干员计算 contribution 时使用当前已选中中枢干员作为
        评估基线，使得"同种效果取最高"的互斥语义生效——
        第二个同类型全局注入者边际贡献为零。
        """
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

        base_A = [a for a in A if a.room_type != "Control"]

        selected_control: list[Operator] = []
        selected_names: list[str] = []

        for _slot in range(max_slots):
            remaining = [op for op in control_candidates
                         if op.name not in selected_names and op.name not in assigned_names]
            if not remaining:
                break

            temp_control = RoomAssignment(
                room_type="Control", room_index=0,
                operators=[o.name for o in selected_control],
                product=None,
            )
            eval_A = [*base_A, temp_control]

            best_score = float("-inf")
            best_op: Operator | None = None
            for op in remaining:
                c = contribution(op.name, "Control", ctx, op_lookup, eval_A)
                if c <= float("-inf"):
                    continue
                bias = config.params.control_global_sort_bias if op.name in ctrl_global_names else 0.0
                score = c + bias
                if score > best_score:
                    best_score = score
                    best_op = op

            if best_op is None or best_score <= 0.0:
                break
            selected_control.append(best_op)
            selected_names.append(best_op.name)
            assigned_names.add(best_op.name)

        new_A: list[RoomAssignment] = list(base_A)

        for i in range(5):
            if i < len(selected_names):
                new_A.append(RoomAssignment(
                    room_type="Control",
                    room_index=i,
                    operators=[selected_names[i]],
                    product=None,
                ))
            else:
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

        dorm_room_size = config.params.dorm_room_size
        total_slots = config.params.dorm_max_operators
        selected = [name for _, name in scored[:total_slots]]

        filler_pool = [op.name for op in candidates if op.name not in {s for _, s in scored}]
        while len(selected) < total_slots and filler_pool:
            selected.append(filler_pool.pop(0))

        new_A: list[RoomAssignment] = []
        slot_ptr = 0
        room_idx = 0
        for a in A:
            if a.room_type == "Dormitory":
                names = selected[slot_ptr:slot_ptr + dorm_room_size]
                new_A.append(RoomAssignment(
                    room_type="Dormitory",
                    room_index=room_idx,
                    operators=names,
                    product=a.product,
                    autofill=not names,
                ))
                slot_ptr += dorm_room_size
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


def _reader_dimension(name: str) -> str | None:
    from steward_core.synergy import _B_BUFF_CONSUMER_TABLE
    from ..slot_iteration import _BUFF_CONSUMER_DIMENSION
    if name not in _B_BUFF_CONSUMER_TABLE:
        return None
    entry = _B_BUFF_CONSUMER_TABLE[name]
    if entry.bonus_per <= 0:
        return None
    return _BUFF_CONSUMER_DIMENSION.get(name)


def _compute_state_delta_simple(
    name: str,
    facility: str,
    assignments: list[RoomAssignment],
    operators: list[Operator],
    op_lookup: dict[str, Operator],
) -> dict[str, float]:
    from ..slot_iteration import _compute_state_delta_for_control, _compute_state_delta_for_dorm
    op = op_lookup.get(name)
    if op is None:
        return {}
    if facility == "Control":
        return _compute_state_delta_for_control(op, assignments, op_lookup)
    elif facility == "Dormitory":
        return _compute_state_delta_for_dorm(op, assignments, op_lookup)
    return {}


def _find_alternatives(
    room_a: RoomAssignment,
    current_name: str,
    operators: list[Operator],
    op_lookup: dict[str, Operator],
    ctx: IterationContext,
    A: list[RoomAssignment],
    config: SolverConfig,
    count: int = 3,
) -> list[str]:
    """为指定房间找 top-N 替代干员"""
    from ..slot_iteration import contribution

    assigned = {n for a in A for n in a.operators if n != current_name}
    candidates = [
        op for op in operators
        if op.has_skill_for(room_a.room_type, room_a.product)
        and op.name not in assigned
    ]
    scored = []
    for op in candidates:
        c = contribution(op.name, room_a.room_type, ctx, op_lookup, A)
        if c > float("-inf"):
            scored.append((c, op.name))
    scored.sort(key=lambda x: -x[0])
    return [name for _, name in scored[:count]]


def _replace_in_assignments(
    A: list[RoomAssignment],
    old_name: str,
    new_name: str,
    target_room_type: str,
) -> None:
    for a in A:
        if a.room_type == target_room_type and old_name in a.operators:
            a.operators = [new_name if n == old_name else n for n in a.operators]
            return
