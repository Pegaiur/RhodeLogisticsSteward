"""K-Beam Strategy 测试

TDD 三层：单元（排斥分配器） → 集成（KBeamStrategy） → 对比（vs Baseline）
"""

import pytest
from steward_core.solver.greed import (
    _greedy_allocate_with_support,
    _greedy_allocate_with_support_excluding,
)
from steward_core.solver.strategies import BaselineStrategy, KBeamStrategy
from tests.strategy_helpers import (
    make_op, strategy_runner, assert_plan_structure,
    assert_no_duplicate_operators,
)


# ─── 4b.1 单元测试：排斥分配器 ────────────────────────────────────

def _build_evaluated(n: int) -> list:
    """构造 n 个互不冲突的评分元组，分数递减"""
    return [
        (float(100 - i), [f"op_{i}_a", f"op_{i}_b"], [], {})
        for i in range(n)
    ]


class TestGreedyAllocateExcluding:

    def test_无排斥_等价于原贪心(self):
        """exclude_sets=None → 与原函数输出一致"""
        ev = _build_evaluated(10)
        r1 = _greedy_allocate_with_support(ev, room_count=2)
        r2 = _greedy_allocate_with_support_excluding(ev, room_count=2)
        assert r1 == r2

    def test_排斥唯一解_返回None(self):
        """只有 2 个可用 combo → 排斥后无解"""
        ev = _build_evaluated(2)
        forbidden = frozenset({("op_0_a", "op_0_b"), ("op_1_a", "op_1_b")})
        result = _greedy_allocate_with_support_excluding(
            ev, room_count=2, exclude_sets=[forbidden],
        )
        assert result is None

    def test_排斥首选_返回次优(self):
        """排斥最高分分配 → 贪心被迫取次优集合"""
        ev = _build_evaluated(6)
        # 原贪心取 combo 0 + combo 1
        r1 = _greedy_allocate_with_support(ev, room_count=2)
        first_set = frozenset(tuple(names) for names, _ in r1)

        r2 = _greedy_allocate_with_support_excluding(
            ev, room_count=2, exclude_sets=[first_set],
        )
        # 次优应为 combo 0 + combo 2（被排斥的恰好是 {0,1}）
        assert r2 is not None
        assert r2 != r1

    def test_多轮排斥_每条路径不同(self):
        """迭代 K=3 次，3 条路径的 combo 集合互不相同"""
        ev = _build_evaluated(10)
        used = []
        results = []
        for _ in range(3):
            r = _greedy_allocate_with_support_excluding(
                ev, room_count=2, exclude_sets=used,
            )
            if r is None:
                break
            results.append(r)
            used.append(frozenset(tuple(names) for names, _ in r))
        assert len(results) >= 2
        # 所有路径互不相同
        for i in range(len(results)):
            for j in range(i + 1, len(results)):
                assert results[i] != results[j]

    def test_排斥耗尽_提前终止(self):
        """C(3,2)=3 种分配，K=5 → 返回 3 条后终止"""
        ev = _build_evaluated(3)
        used = []
        results = []
        for _ in range(5):
            r = _greedy_allocate_with_support_excluding(
                ev, room_count=2, exclude_sets=used,
            )
            if r is None:
                break
            results.append(r)
            used.append(frozenset(tuple(names) for names, _ in r))
        # C(3,2)=3 种互不冲突的分配
        assert len(results) == 3


# ─── 4b.2 集成测试：KBeamStrategy 正确性 ───────────────────────────

def _minimal_mfg_pool() -> list:
    """构造最小 Mfg+Trade 干员池，覆盖全部设施

    prune_equivalent 限制纯效率最多 3 人，因此每种产物至少需要 9 人
    （3 纯效率 + 锚点分类的额外人选）。
    """
    from tests.strategy_helpers import make_op

    ops = []
    # CR 制造站 (9人 → 2间 × 3人，含 prune 后余量)
    for i in range(9):
        ops.append(make_op(f"cr_{i}", f"cr_{i}", "Mfg",
                           efficiency=25.0, product="CombatRecord"))
    # PG 制造站 (9人)
    for i in range(9):
        ops.append(make_op(f"pg_{i}", f"pg_{i}", "Mfg",
                           efficiency=25.0, product="PureGold"))
    # 贸易站 (9人)
    for i in range(9):
        ops.append(make_op(f"trade_{i}", f"trade_{i}", "Trade",
                           efficiency=30.0, product="Money"))
    # 中枢 (5人)
    for i in range(5):
        ops.append(make_op(f"ctrl_{i}", f"ctrl_{i}", "Control", efficiency=0.0))
    # 发电站 (3人)
    for i in range(3):
        ops.append(make_op(f"power_{i}", f"power_{i}", "Power", efficiency=20.0))
    # 会客室 (2人)
    for i in range(2):
        ops.append(make_op(f"rec_{i}", f"rec_{i}", "Reception", efficiency=25.0))
    # 办公室 (1人)
    ops.append(make_op("off_0", "off_0", "Office", efficiency=0.0))
    return ops


class TestKBeamCorrectness:

    def test_产出有效排班方案(self):
        """K=3，产出 SolveResult 含完整房间结构（Mfg 房间数取决于池大小）"""
        ops = _minimal_mfg_pool()
        result = strategy_runner(KBeamStrategy, ops, beam_width=3)
        plan = result.plans[0]
        mfg_count = sum(1 for a in plan.assignments if a.room_type == "Mfg")
        assert mfg_count >= 1, f"Mfg 房间数: {mfg_count}"
        # 验证基本结构存在
        for rt in ["Control", "Power", "Reception", "Office"]:
            assert any(a.room_type == rt for a in plan.assignments), f"缺少 {rt}"

    def test_无重复干员(self):
        """H2 约束——任何干员只出现一次"""
        ops = _minimal_mfg_pool()
        result = strategy_runner(KBeamStrategy, ops, beam_width=3)
        assert_no_duplicate_operators(result)

    def test_制造站全部满员(self):
        """Mfg 房间均满 3 人"""
        ops = _minimal_mfg_pool()
        result = strategy_runner(KBeamStrategy, ops, beam_width=3)
        plan = result.plans[0]
        for a in plan.assignments:
            if a.room_type == "Mfg" and not a.autofill:
                assert len(a.operators) == 3, f"Mfg 房间 {a.room_index} 不满员"

    def test_贸易站产出存在(self):
        """Trade 房间存在且非空"""
        ops = _minimal_mfg_pool()
        result = strategy_runner(KBeamStrategy, ops, beam_width=3)
        plan = result.plans[0]
        trade_rooms = [a for a in plan.assignments if a.room_type == "Trade"]
        assert len(trade_rooms) >= 1
        filled = [a for a in trade_rooms if a.operators]
        assert len(filled) >= 1

    def test_产物类型正确(self):
        """CR 房间 product=CombatRecord，PG 房间 product=PureGold"""
        ops = _minimal_mfg_pool()
        result = strategy_runner(KBeamStrategy, ops, beam_width=3)
        plan = result.plans[0]
        mfg_products = {a.product for a in plan.assignments if a.room_type == "Mfg"}
        assert "CombatRecord" in mfg_products
        assert "PureGold" in mfg_products

    def test_中枢五人上限(self):
        """Control 不超过 5 人"""
        ops = _minimal_mfg_pool()
        result = strategy_runner(KBeamStrategy, ops, beam_width=3)
        plan = result.plans[0]
        for a in plan.assignments:
            if a.room_type == "Control":
                assert len(a.operators) <= 5
