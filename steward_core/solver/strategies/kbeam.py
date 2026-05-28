"""K-Beam 搜索策略

在 Phase 1（制造站穷举）后保留 K 条最佳分配路径，
Phase 2（中枢填充）和 Phase 3a（贸易站穷举）在每条路径上并行执行，
择优后继续 Phase 3b-4。

不改动任何 Phase 模块——K-Beam 是纯编排层逻辑。
"""

from steward_core.models import Operator, RoomAssignment, ShiftPlan, SolveResult
from steward_core.synergy import (
    classify_mfg_operators, build_candidate_pool, get_synergy_enablers,
    get_system_contributors,
)
from steward_core.synergy._derived import MFG_ANCHORS

from ..config import SolverConfig
from ..global_state import GlobalState
from ..greed import _generate_combos, _greedy_allocate_with_support_excluding
from ..phase2_control import _phase2_control
from ..phase3_trade import _phase3_trade
from ..phase3_remaining import _phase3_remaining
from ..phase4_dorm import _phase4_dorm
from ..refine import local_search_refine, _production_score
from ..strategy import PartialSolution, Strategy
from ..support import _evaluate_with_support, compute_optimal_support


class KBeamStrategy(Strategy):
    """K-Beam 搜索策略"""

    name = "kbeam"

    def __init__(self, beam_width: int = 5):
        self.beam_width = beam_width

    def execute(
        self,
        operators: list[Operator],
        config: SolverConfig,
        op_lookup: dict[str, Operator],
    ) -> SolveResult:
        params = config.params
        anchor_names = MFG_ANCHORS
        ctrl_global_names = set(get_system_contributors("Control", "global_bonus"))
        dorm_names_list = get_system_contributors("Dormitory")
        power_names = set(get_system_contributors("Power"))

        mfg_paths = self._phase1_kbeam(operators, config, op_lookup, anchor_names)
        if not mfg_paths:
            return self._empty_result(config)

        for path in mfg_paths:
            _phase2_control(
                operators=operators, assigned_ids=path.assigned_ids,
                assigned_names=path.assigned_names, assignments=path.assignments,
                op_lookup=op_lookup, locked_support=path.locked_support,
                ctrl_global_names=ctrl_global_names, config=config,
            )
            _phase3_trade(
                operators=operators, assigned_ids=path.assigned_ids,
                assigned_names=path.assigned_names, assignments=path.assignments,
                op_lookup=op_lookup, locked_support=path.locked_support,
                config=config,
            )

        best = self._select_best(mfg_paths, operators, params)

        _phase3_remaining(
            operators=operators, assigned_ids=best.assigned_ids,
            assigned_names=best.assigned_names, assignments=best.assignments,
            op_lookup=op_lookup, locked_support=best.locked_support,
            power_names=power_names, config=config,
        )
        _phase4_dorm(
            operators=operators, assigned_ids=best.assigned_ids,
            assigned_names=best.assigned_names, assignments=best.assignments,
            op_lookup=op_lookup, locked_support=best.locked_support,
            dorm_names_list=dorm_names_list, config=config,
        )

        half_hours = int(params.shift_hours / 2.0)
        plan = ShiftPlan(
            name=f"KBeam-{int(params.shift_hours)}h-K{self.beam_width}",
            assignments=best.assignments,
            period_from=f"{half_hours:02d}:00",
            period_to=f"{half_hours + int(params.shift_hours) - 1:02d}:59",
        )
        result = SolveResult(plans=[plan], autofill_count=0, config_used=config)
        result = local_search_refine(result, operators, config)
        return result

    # ── 私有方法 ──

    def _phase1_kbeam(self, operators, config, op_lookup, anchor_names):
        """Phase 1: CR K 条路径 × PG 1 条 → K 条完整 Mfg 路径"""
        k = self.beam_width
        use_global = config.global_state_scoring if config else False

        # ── CR: 评估 + K 条分配 ──
        cr_allocations = self._evaluate_and_allocate_k(
            operators, config, op_lookup, anchor_names,
            "CombatRecord", room_count=2, k=k,
            assigned_ids=set(), use_global=use_global,
        )
        if not cr_allocations:
            return []

        # ── PG: 每条 CR 路径上评估 + 1 条分配 ──
        paths = []
        for cr_alloc in cr_allocations:
            pg_assigned = set(cr_alloc["assigned_ids"])
            pg_allocations = self._evaluate_and_allocate_k(
                operators, config, op_lookup, anchor_names,
                "PureGold", room_count=2, k=1,
                assigned_ids=pg_assigned, use_global=use_global,
            )
            if not pg_allocations:
                continue
            pg_alloc = pg_allocations[0]

            merged = PartialSolution.empty()
            merged.assigned_ids = cr_alloc["assigned_ids"] | pg_alloc["assigned_ids"]
            merged.assigned_names = cr_alloc["assigned_names"] | pg_alloc["assigned_names"]
            merged.assignments = cr_alloc["assignments"] + pg_alloc["assignments"]
            for facility in ("Control", "Trade", "Dormitory", "Office"):
                merged.locked_support[facility] = (
                    cr_alloc["locked_support"].get(facility, set())
                    | pg_alloc["locked_support"].get(facility, set())
                )
            paths.append(merged)

        return paths[:k]

    def _evaluate_and_allocate_k(
        self, operators, config, op_lookup, anchor_names,
        product, room_count, k, assigned_ids, use_global,
    ):
        """对指定产物评估全部 combo 并贪心取 K 条分配"""
        mfg_ops = [op for op in operators if op.has_skill_for("Mfg", product)]
        if not mfg_ops:
            return []

        classification = classify_mfg_operators(mfg_ops, product, anchor_names)
        pool = build_candidate_pool(mfg_ops, classification, room_type="Mfg", product=product)
        pool = [op for op in pool if op.char_id not in assigned_ids]
        existing = {op.char_id for op in pool}
        for enabler in get_synergy_enablers(operators, "Mfg", product):
            if enabler.char_id not in existing and enabler.char_id not in assigned_ids:
                pool.append(enabler)
        combos = _generate_combos(pool, 3)

        gs = GlobalState.for_layout_243() if use_global else None
        evaluated = []
        for combo_ops in combos:
            score, support_map = _evaluate_with_support(
                combo_ops, "Mfg", product, operators, assigned_ids,
                params=config.params,
            )
            combo_names = [op.name for op in combo_ops]
            all_support_names = [n for names2 in support_map.values() for n in names2]
            if use_global and gs is not None:
                bundles = compute_optimal_support(combo_ops).bundles
                penalty = gs.scarcity_penalty(bundles, alpha=config.params.global_state_alpha)
                score -= penalty
            evaluated.append((score, combo_names, all_support_names, support_map))
        evaluated.sort(key=lambda x: -x[0])

        results = []
        used_sets = []
        for _ in range(k):
            allocated = _greedy_allocate_with_support_excluding(
                evaluated, room_count=room_count,
                config=config, exclude_sets=used_sets,
            )
            if allocated is None:
                break
            used_sets.append(frozenset(tuple(names) for names, _ in allocated))

            alloc_ids = set()
            alloc_names = set()
            alloc_assignments = []
            alloc_support: dict[str, set[str]] = {
                "Control": set(), "Trade": set(), "Dormitory": set(), "Office": set(),
            }
            for names, support_map in allocated:
                for op in pool:
                    if op.name in names:
                        alloc_ids.add(op.char_id)
                        alloc_names.add(op.name)
                for facility, s_names in support_map.items():
                    alloc_support[facility].update(s_names)
                    for n in s_names:
                        if n in op_lookup:
                            alloc_ids.add(op_lookup[n].char_id)
                            alloc_names.add(n)
                room_idx = len(alloc_assignments)
                alloc_assignments.append(RoomAssignment(
                    room_type="Mfg", room_index=room_idx,
                    operators=names, product=product,
                ))
            results.append({
                "assigned_ids": alloc_ids,
                "assigned_names": alloc_names,
                "assignments": alloc_assignments,
                "locked_support": alloc_support,
            })
        return results

    def _select_best(self, paths, operators, params):
        """用 production.calculate() 选真实经济产出最高的路径"""
        best_path = paths[0]
        best_score = -float("inf")
        for path in paths:
            plan = ShiftPlan(name="_eval", assignments=path.assignments)
            score = _production_score(plan, operators, params)
            if score > best_score:
                best_score = score
                best_path = path
        return best_path

    def _empty_result(self, config):
        return SolveResult(plans=[ShiftPlan(name="KBeam-empty")], config_used=config)
