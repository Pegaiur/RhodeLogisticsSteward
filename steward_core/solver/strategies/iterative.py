"""不动点迭代策略

通过 BuffPool 迭代自洽来消除顺序贪心的跨设施估计误差。
"""

from steward_core.models import Operator, ShiftPlan, SolveResult
from steward_core.synergy import get_system_contributors
from steward_core.synergy._derived import MFG_ANCHORS

from ..config import SolverConfig
from ..context import GlobalContext
from ..exhaust_mfg import exhaust_mfg
from ..fill_control import fill_control
from ..exhaust_trade import exhaust_trade
from ..fill_remaining import fill_remaining
from ..fill_dorm import fill_dorm
from ..refine import local_search_refine, _production_score
from ..strategy import PartialSolution, Strategy

ANCHOR_NAMES = MFG_ANCHORS


class IterativeStrategy(Strategy):
    """不动点迭代策略

    算法：
      1. 用乐观估计生成初始 Pool P₀（假设所有 BuffPool 生产者都在工作设施中）
      2. 以 P_k 为全局基准评估所有 combo，贪心分配各设施
      3. 从分配结果反向构建 GlobalContext → 计算实际 Pool P_{k+1}
      4. 若 P_{k+1} == P_k → 收敛（Pool 与分配自洽），返回结果
      5. 否则 k += 1 回到步骤 2，最多 max_rounds 轮

    核心不变量：
      - 每一轮所有 combo 评估使用相同的 BuffPool，消除跨设施估计误差
      - 收敛条件 P_{k+1} == P_k 意味着 Pool 自洽
    """

    name = "iterative"

    def __init__(self, max_rounds: int = 5):
        self.max_rounds = max_rounds

    def execute(
        self,
        operators: list[Operator],
        config: SolverConfig,
        op_lookup: dict[str, Operator],
    ) -> SolveResult:
        params = config.params
        ctrl_global_names = set(get_system_contributors("Control", "global_bonus"))
        dorm_names_list = get_system_contributors("Dormitory")
        power_names = set(get_system_contributors("Power"))

        pool = self._initial_pool(operators, params)

        best_result = None
        best_score = float("-inf")

        for _round in range(self.max_rounds):
            result = self._solve_with_pool(
                operators, config, op_lookup, pool,
                ctrl_global_names, dorm_names_list, power_names,
            )
            new_pool = GlobalContext.from_plan(
                result.plans[0], operators, params,
            ).buff_pool

            if new_pool == pool:
                return result

            score = _production_score(result.plans[0], operators, params)
            if score > best_score:
                best_score = score
                best_result = result

            pool = new_pool

        return best_result if best_result else result

    def _initial_pool(self, operators, params):
        """乐观初始 Pool：假设所有 BuffPool 生产者都在对应设施中"""
        dorm_est = [
            Operator(char_id=f"_dorm_{i}", name=f"填位宿舍{i}", skills=[])
            for i in range(params.dorm_estimated_count)
        ]
        ctx = GlobalContext.from_estimated(
            control_operators=[],
            dorm_operators=dorm_est,
            all_operators=operators,
            assigned_names=set(),
            params=params,
            has_rosmontis_in_mfg=True,
            has_ebnhlz_in_trade=True,
            has_wuyou_in_trade=True,
            ling_mood_below_12=True,
            perception_from_office=params.office_perception_base,
        )
        return ctx.buff_pool

    def _solve_with_pool(
        self, operators, config, op_lookup, pool,
        ctrl_global_names, dorm_names_list, power_names,
    ):
        """以固定 BuffPool 执行完整求解（绕过 Pipeline，直接调用 Phase）"""
        params = config.params
        state = PartialSolution.empty()

        exhaust_mfg(
            operators=operators, assigned_ids=state.assigned_ids,
            assigned_names=state.assigned_names, assignments=state.assignments,
            op_lookup=op_lookup, locked_support=state.locked_support,
            anchor_names=ANCHOR_NAMES, config=config,
            override_pool=pool,
        )

        exhaust_trade(
            operators=operators, assigned_ids=state.assigned_ids,
            assigned_names=state.assigned_names, assignments=state.assignments,
            op_lookup=op_lookup, locked_support=state.locked_support,
            config=config, override_pool=pool,
        )

        fill_control(
            operators=operators, assigned_ids=state.assigned_ids,
            assigned_names=state.assigned_names, assignments=state.assignments,
            op_lookup=op_lookup, locked_support=state.locked_support,
            ctrl_global_names=ctrl_global_names, config=config,
        )

        fill_remaining(
            operators=operators, assigned_ids=state.assigned_ids,
            assigned_names=state.assigned_names, assignments=state.assignments,
            op_lookup=op_lookup, locked_support=state.locked_support,
            power_names=power_names, config=config,
        )

        fill_dorm(
            operators=operators, assigned_ids=state.assigned_ids,
            assigned_names=state.assigned_names, assignments=state.assignments,
            op_lookup=op_lookup, locked_support=state.locked_support,
            dorm_names_list=dorm_names_list, config=config,
        )

        half_hours = int(params.shift_hours / 2.0)
        plan = ShiftPlan(
            name=f"Iter-{int(params.shift_hours)}h-R{self.max_rounds}",
            assignments=state.assignments,
            period_from=f"{half_hours:02d}:00",
            period_to=f"{half_hours + int(params.shift_hours) - 1:02d}:59",
        )
        result = SolveResult(plans=[plan], autofill_count=0, config_used=config)
        result = local_search_refine(result, operators, config)
        return result
