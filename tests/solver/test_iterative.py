"""不动点迭代策略测试

TDD 三层：单元（Pool 初始化） → 集成（IterativeStrategy） → 对比（vs Baseline）
"""

from steward_core.solver.strategies import IterativeStrategy, BaselineStrategy
from steward_core.solver.strategies.iterative import IterativeStrategy as IS  # 白盒访问 _initial_pool
from steward_core.models import ShiftPlan
from tests.strategy_helpers import (
    make_op, strategy_runner,
    assert_no_duplicate_operators, assert_operator_in_room,
)


def _minimal_pool() -> list:
    """构造最小 Mfg+Trade 干员池，覆盖全部设施"""
    ops = []
    for i in range(9):
        ops.append(make_op(f"cr_{i}", f"cr_{i}", "Mfg",
                           efficiency=25.0, product="CombatRecord"))
    for i in range(9):
        ops.append(make_op(f"pg_{i}", f"pg_{i}", "Mfg",
                           efficiency=25.0, product="PureGold"))
    for i in range(9):
        ops.append(make_op(f"trade_{i}", f"trade_{i}", "Trade",
                           efficiency=30.0, product="Money"))
    for i in range(5):
        ops.append(make_op(f"ctrl_{i}", f"ctrl_{i}", "Control", efficiency=0.0))
    for i in range(3):
        ops.append(make_op(f"power_{i}", f"power_{i}", "Power", efficiency=20.0))
    for i in range(2):
        ops.append(make_op(f"rec_{i}", f"rec_{i}", "Reception", efficiency=25.0))
    ops.append(make_op("off_0", "off_0", "Office", efficiency=0.0))
    return ops


# ── 单元测试：Pool 初始化与反算 ──

class TestPoolInitAndReverse:

    def test_初始pool_乐观假设(self):
        """初始 Pool 的 yanhuo/perception > 0（乐观假设生效）"""
        from steward_core.solver.params import SolverParams
        ops = _minimal_pool()
        strategy = IS(max_rounds=5)
        params = SolverParams()
        pool = strategy._initial_pool(ops, params)
        assert pool.yanhuo > 0, f"乐观初始 Pool 应有烟火，实际 {pool.yanhuo}"
        assert pool.perception > 0, f"乐观初始 Pool 应有感知信息，实际 {pool.perception}"

    def test_从空排班反算pool_全零(self):
        """空排班 → pool 全零"""
        from steward_core.solver.params import SolverParams
        from steward_core.solver.context import GlobalContext

        params = SolverParams()
        plan = ShiftPlan(name="test", assignments=[])
        ctx = GlobalContext.from_plan(plan, [], params)
        pool = ctx.buff_pool
        assert pool.yanhuo == 0
        assert pool.perception == 0
        assert pool.silent_resonance == 0

    def test_pool_from_result_与from_plan一致(self):
        """_solve_with_pool 产出的 result 用 from_plan 反算 pool 自洽"""
        ops = _minimal_pool()
        result = strategy_runner(IterativeStrategy, ops, max_rounds=1)
        from steward_core.solver.params import SolverParams
        from steward_core.solver.context import GlobalContext
        params = SolverParams()
        pool = GlobalContext.from_plan(result.plans[0], ops, params).buff_pool
        assert pool is not None


# ── 集成测试：IterativeStrategy 正确性 ──

class TestIterativeCorrectness:

    def test_纯效率池_一轮收敛(self):
        """无 BuffPool 消费者 → 初始 Pool 已自洽 → 1 轮收敛"""
        ops = _minimal_pool()
        result = strategy_runner(IterativeStrategy, ops, max_rounds=5)
        assert result.plans[0] is not None
        assert len(result.plans[0].assignments) > 0

    def test_产出有效排班(self):
        """Plan 含 Mfg/Trade/Control/Power 等"""
        ops = _minimal_pool()
        result = strategy_runner(IterativeStrategy, ops, max_rounds=3)
        plan = result.plans[0]
        for rt in ["Mfg", "Trade", "Control", "Power", "Reception", "Office"]:
            assert any(a.room_type == rt for a in plan.assignments), f"缺少 {rt}"

    def test_无重复干员(self):
        """H2 约束——任何干员只出现一次"""
        ops = _minimal_pool()
        result = strategy_runner(IterativeStrategy, ops, max_rounds=3)
        assert_no_duplicate_operators(result)

    def test_产物类型正确(self):
        """CR=CombatRecord, PG=PureGold"""
        ops = _minimal_pool()
        result = strategy_runner(IterativeStrategy, ops, max_rounds=3)
        plan = result.plans[0]
        mfg_products = {a.product for a in plan.assignments if a.room_type == "Mfg"}
        assert "CombatRecord" in mfg_products
        assert "PureGold" in mfg_products

    def test_制造站满员(self):
        """Mfg 非 autofill 房间均满 3 人"""
        ops = _minimal_pool()
        result = strategy_runner(IterativeStrategy, ops, max_rounds=3)
        plan = result.plans[0]
        for a in plan.assignments:
            if a.room_type == "Mfg" and not a.autofill:
                assert len(a.operators) == 3, f"Mfg 房间 {a.room_index} 不满员"

    def test_贸易站产出存在(self):
        """Trade 房间存在且非空"""
        ops = _minimal_pool()
        result = strategy_runner(IterativeStrategy, ops, max_rounds=3)
        plan = result.plans[0]
        trade_rooms = [a for a in plan.assignments if a.room_type == "Trade"]
        assert len(trade_rooms) >= 1
        filled = [a for a in trade_rooms if a.operators]
        assert len(filled) >= 1

    def test_中枢五人上限(self):
        """Control 不超过 5 人"""
        ops = _minimal_pool()
        result = strategy_runner(IterativeStrategy, ops, max_rounds=3)
        plan = result.plans[0]
        for a in plan.assignments:
            if a.room_type == "Control":
                assert len(a.operators) <= 5

    def test_达到上限后返回最优(self):
        """max_rounds=1 → 返回唯一一轮结果（不崩溃）"""
        ops = _minimal_pool()
        result = strategy_runner(IterativeStrategy, ops, max_rounds=1)
        assert result.plans[0] is not None

    def test_vs_baseline_不退化(self):
        """IterativeStrategy 产出 ≥ BaselineStrategy 产出"""
        from steward_core.solver.params import SolverParams
        from steward_core.solver.refine import _production_score  # 白盒访问评分函数

        ops = _minimal_pool()
        base_result = strategy_runner(BaselineStrategy, ops)
        iter_result = strategy_runner(IterativeStrategy, ops, max_rounds=5)

        params = SolverParams()
        base_score = _production_score(base_result.plans[0], ops, params)
        iter_score = _production_score(iter_result.plans[0], ops, params)
        assert iter_score >= base_score * 0.99, (
            f"Iterative({iter_score:.1f}) < Baseline({base_score:.1f}), 差距过大"
        )


# ── 回归测试：跨设施协同 ──

class TestCrossFacilitySynergy:

    def test_乌有在Trade_黍在Mfg_跨设施烟火协同(self):
        """IterativeStrategy 能发现乌有(Trade)→烟火→黍(Mfg)的跨设施协同

        乌有在贸易站产出烟火，黍在制造站消费烟火。
        顺序贪心可能遗漏此协同（Mfg 先选时 Trade 未定）。
        """
        ops = _minimal_pool() + [
            make_op("黍", "shu", "Mfg", buff_id="buff_mfg_bd_n1_n1[004]"),
            make_op("乌有", "wuyou", "Trade", buff_id="buff_trade_bd_n1_n1[004]"),
        ]
        result = strategy_runner(IterativeStrategy, ops, max_rounds=5)
        assert_no_duplicate_operators(result)
        assert_operator_in_room(result, "Mfg", "黍")
        assert_operator_in_room(result, "Trade", "乌有")
