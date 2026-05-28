"""排班求解器

Mfg 和 Trade 均使用 C(n,3) 穷举（含联动）+ 贪心分配。
剩余设施（Power/Reception/Office）用支配偏序贪心。
中枢后置于 Mfg + Trade，由两者累计的支撑需求动态决定。
"""

from steward_core.models import Operator, ShiftPlan, SolveResult
from steward_core.synergy import (
    compute_control_global_bonus,
    compute_buff_pool,
    compute_effective_power_count, _has_power_count_modifier,
    get_system_contributors,
    classify_mfg_operators, prune_equivalent, build_candidate_pool,
    classify_trade_operators,
    control_per_operator_bonus, _is_glasgow,
    get_synergy_enablers,
)
from steward_core.evaluate import evaluate_room
from steward_core.constants import BASE_POWER_COUNT

from .support import compute_optimal_support, _evaluate_with_support, compute_trade_support
from .greed import (
    _greedy_allocate, _greedy_allocate_with_support, _greedy_remaining,
    _generate_combos, _upper_bound_ok, _evaluate_trade_combo,
)
from .phase1_mfg import _phase1_mfg
from .phase2_control import _phase2_control
from .phase3_trade import _phase3_trade
from .phase3_remaining import _phase3_remaining
from .phase4_dorm import _phase4_dorm

T = 12.0

ANCHOR_NAMES = set(get_system_contributors("Mfg", "anchor"))

# 系统贡献者按设施索引（由 synergy.py 注册表生成）
_CTRL_GLOBAL_NAMES = set(get_system_contributors("Control", "global_bonus"))
_DORM_NAMES = get_system_contributors("Dormitory")
_POWER_NAMES = set(get_system_contributors("Power", "facility_modifier"))

# 中枢全局加成在控制中枢填充中的排序偏置
# 中枢填充时按 best_efficiency 排序，C1 全局加成者个人效率=0，需大偏置强制排前
_CTRL_GLOBAL_SORT_BIAS = 1000.0


def solve_mvp(operators: list[Operator]) -> SolveResult:
    """MVP 完整求解：制造站穷举 + 贸易站穷举 + 中枢后置填充 + 剩余设施贪心

    中枢后置于 Mfg + Trade：由两者的支撑需求累计决定组成。
    返回 SolveResult，含一个 12h ShiftPlan。
    """
    assigned_ids: set[str] = set()
    assigned_names: set[str] = set()
    assignments: list = []
    autofill_count = 0
    op_lookup = {op.name: op for op in operators}
    locked_support: dict[str, set[str]] = {
        "Control": set(), "Trade": set(), "Dormitory": set(), "Office": set(),
    }

    # Phase 1: 制造站穷举（CR 2间 + PG 2间）
    autofill_count += _phase1_mfg(
        operators, assigned_ids, assigned_names, assignments,
        op_lookup, locked_support, ANCHOR_NAMES,
    )

    # Phase 3a: 贸易站穷举（使用 locked_support 估计中枢，中枢尚未填充）
    autofill_count += _phase3_trade(
        operators, assigned_ids, assigned_names, assignments,
        op_lookup, locked_support,
    )

    # Phase 2: 填充中枢（来自 Phase 1 Mfg 锁 + Phase 3a Trade 锁）
    ctrl_names = _phase2_control(
        operators, assigned_ids, assignments, locked_support, op_lookup,
        _CTRL_GLOBAL_NAMES, _CTRL_GLOBAL_SORT_BIAS,
    )

    # Phase 3b: 剩余设施（Power/Reception/Office）贪心
    autofill_count += _phase3_remaining(
        operators, assigned_ids, assigned_names, assignments,
        op_lookup, locked_support, _POWER_NAMES,
    )

    # Phase 4: 宿舍填充（优先B层生成者 → 任意填充至20人）
    autofill_count += _phase4_dorm(
        operators, assigned_ids, assignments, op_lookup, locked_support, _DORM_NAMES,
    )

    plan = ShiftPlan(
        name="MVP-12h",
        assignments=assignments,
        period_from="00:00",
        period_to="11:59",
    )
    return SolveResult(plans=[plan], autofill_count=autofill_count)
