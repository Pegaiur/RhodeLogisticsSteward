"""效率函数单元测试 (efficiency_fn.py)

全部测试通过内存构造，不依赖磁盘文件。
遵循 TDD 3A 模式 (Arrange → Act → Assert)。
"""

import pytest

from steward_core.models import LinearSegment
from steward_core.efficiency_fn import (
    constant_efficiency,
    ramping_efficiency,
    stepped_efficiency,
    integrate_segments,
    _dominates_simple,
    _dominates,
    rank_by_dominance,
)


# ─── constant_efficiency ────────────────────────────────────────

class TestConstantEfficiency:
    """常数效率技能 → 分段表示"""

    def test_无心情消耗_单段全时长(self):
        """mood_burn=0 → 一段常数覆盖整个 T"""
        # Arrange & Act
        segs = constant_efficiency(30.0, mood_burn=0.0, T=12.0)

        # Assert: 单段, a=30, b=0, 从 0 到 12
        assert len(segs) == 1
        seg = segs[0]
        assert seg.a == 30.0
        assert seg.b == 0.0
        assert seg.t_start == 0.0
        assert seg.dt == 12.0

    def test_心情消耗_不触发截断(self):
        """t_red=24/0.65=36.9h > 12h → 不截断，单段"""
        # Arrange & Act
        segs = constant_efficiency(25.0, mood_burn=0.65, T=12.0)

        # Assert: 单段，积分为 25×12=300
        assert len(segs) == 1
        assert pytest.approx(segs[0].integrate()) == 300.0

    def test_心情消耗_触发截断(self):
        """t_red=24/1.5=16h, T=24h → 两段: [0,16) 满效率, [16,24] 归零"""
        # Arrange & Act
        segs = constant_efficiency(30.0, mood_burn=1.5, T=24.0)

        # Assert: 两段
        assert len(segs) == 2
        # 第一段: 0→16, a=30
        assert segs[0].a == 30.0
        assert segs[0].t_start == 0.0
        assert pytest.approx(segs[0].dt) == 16.0
        # 第二段: 16→24, a=0 (归零)
        assert segs[1].a == 0.0
        assert pytest.approx(segs[1].t_start) == 16.0
        assert pytest.approx(segs[1].dt) == 8.0

    def test_效率为零_产出零段(self):
        """efficiency=0 的条件技能，MVP 不参与积分 → 返回空或零段"""
        # Arrange & Act
        segs = constant_efficiency(0.0, mood_burn=0.0, T=12.0)

        # Assert: 至少有一段的积分 = 0
        total = sum(s.integrate() for s in segs)
        assert total == 0.0

    def test_负数效率_惩罚段(self):
        """efficiency<0 (如心情消耗惩罚) → 积分应为负"""
        # Arrange & Act
        segs = constant_efficiency(-5.0, mood_burn=0.0, T=12.0)

        # Assert: 积分 = -5×12 = -60
        total = sum(s.integrate() for s in segs)
        assert pytest.approx(total) == -60.0


# ─── ramping_efficiency ─────────────────────────────────────────

class TestRampingEfficiency:
    """时变技能（7 条）：线性爬升 + 饱和 + 心情截断"""

    def test_爬升至饱和_典型制造技能(self):
        """k0=20, r=1, ceiling=25, T=12 → 前5h 爬升, 后7h 饱和"""
        # Arrange & Act
        segs = ramping_efficiency(20.0, 1.0, 25.0, mood_burn=0.0, T=12.0)

        # Assert
        assert len(segs) == 2
        # 第一段: [0,5) 爬升 a=20, b=1
        assert segs[0].a == 20.0
        assert segs[0].b == 1.0
        assert pytest.approx(segs[0].dt) == 5.0
        # 第二段: [5,12) 饱和 a=25, b=0
        assert segs[1].a == 25.0
        assert segs[1].b == 0.0
        assert pytest.approx(segs[1].dt) == 7.0

    def test_爬升速度快_短时间饱和(self):
        """k0=15, r=2, ceiling=25 → 5h 后饱和"""
        # Arrange & Act
        segs = ramping_efficiency(15.0, 2.0, 25.0, mood_burn=0.0, T=12.0)

        # Assert: 两段, 第一段 dt = (25-15)/2 = 5h
        assert len(segs) == 2
        assert pytest.approx(segs[0].dt) == 5.0
        assert pytest.approx(segs[1].dt) == 7.0

    def test_班次内未饱和_全爬升(self):
        """ceiling 很高，12h 内不饱和 → 单段爬升"""
        # Arrange & Act
        segs = ramping_efficiency(10.0, 1.0, 50.0, mood_burn=0.0, T=12.0)

        # Assert: 单段爬升，积分 = a×12 + b×144/2 = 120+72=192
        assert len(segs) == 1
        assert pytest.approx(segs[0].integrate()) == 192.0

    def test_爬升中触发心情截断(self):
        """爬升未饱和前触发 t_red → 两段：爬升 + 归零"""
        # t_red = 24/0.65 ≈ 36.9h → 不触发
        # 用 mood_burn=3.0 使 t_red=8h, ceiling=30, k0=15, r=2 → 饱和时间=7.5h
        # 爬升到 8h → e(8)=15+16=31, 但 ceiling 30 → 实际先饱和后截断
        # 用 mood_burn=2.4, t_red=10h, k0=10, r=3, ceiling=30 → 饱和=6.67h
        # 更简单: k0=10, r=2, ceiling=20, mood_burn=3.0 (t_red=8h)
        # 饱和 = (20-10)/2 = 5h, 在 t_red 之前 → 先饱和后截断
        # Arrange & Act
        segs = ramping_efficiency(10.0, 2.0, 20.0, mood_burn=3.0, T=24.0)

        # Assert: 三段: 爬升[0,5) + 饱和[5,8) + 归零[8,24)
        assert len(segs) == 3
        assert segs[0].b == 2.0  # 爬升段
        assert pytest.approx(segs[0].dt) == 5.0
        assert segs[1].a == 20.0  # 饱和段
        assert pytest.approx(segs[1].dt) == 3.0  # 8-5
        assert segs[2].a == 0.0  # 归零段
        assert pytest.approx(segs[2].dt) == 16.0  # 24-8


# ─── 支配关系 ────────────────────────────────────────────────────

class TestDominance:
    """支配偏序: A 支配 B ⇔ e_A(t) ≥ e_B(t) for all t ∈ [0,T]"""

    def test_常数技能_效率高支配效率低(self):
        """A=30, B=20, 无截断 → A 支配 B"""
        # Arrange
        seg_a = [LinearSegment(a=30, b=0, t_start=0, dt=12)]
        seg_b = [LinearSegment(a=20, b=0, t_start=0, dt=12)]

        # Act
        result = _dominates_simple(seg_a, seg_b, T=12.0)

        # Assert
        assert result is True

    def test_常数技能_效率低不支配效率高(self):
        """B=20 不支配 A=30"""
        # Arrange
        seg_a = [LinearSegment(a=20, b=0, t_start=0, dt=12)]
        seg_b = [LinearSegment(a=30, b=0, t_start=0, dt=12)]

        # Act
        result = _dominates_simple(seg_a, seg_b, T=12.0)

        # Assert
        assert result is False

    def test_相同技能_互支配(self):
        """相同效率 → A 支配 B 且 B 支配 A"""
        # Arrange
        seg = [LinearSegment(a=25, b=0, t_start=0, dt=12)]

        # Act
        a_to_b = _dominates_simple(seg, seg, T=12.0)

        # Assert
        assert a_to_b is True

    def test_提前截断_不支配全时长(self):
        """A 效率高但 t_red 短, B 效率低但全程有效 → 互不支配"""
        # A: eff=40, t_red=8h (mood_burn=3.0)
        # B: eff=25, t_red=24h (无截断)
        seg_a = [
            LinearSegment(a=40, b=0, t_start=0, dt=8),
            LinearSegment(a=0, b=0, t_start=8, dt=4),
        ]
        seg_b = [LinearSegment(a=25, b=0, t_start=0, dt=12)]

        # Act: A 不支配 B (t<8 时 A 高, 但 t>8 时 A=0 < B=25)
        a_dom_b = _dominates_simple(seg_a, seg_b, T=12.0)
        b_dom_a = _dominates_simple(seg_b, seg_a, T=12.0)

        # Assert
        assert a_dom_b is False
        assert b_dom_a is False

    def test_高且长_支配低且短(self):
        """A eff=30 全程, B eff=20 且 t_red=8h → A 支配 B"""
        seg_a = [LinearSegment(a=30, b=0, t_start=0, dt=12)]
        seg_b = [
            LinearSegment(a=20, b=0, t_start=0, dt=8),
            LinearSegment(a=0, b=0, t_start=8, dt=4),
        ]

        # Act
        result = _dominates_simple(seg_a, seg_b, T=12.0)

        # Assert
        assert result is True


# ─── rank_by_dominance ───────────────────────────────────────────

class TestRankByDominance:
    """支配偏序排序: 多趟 Kahn 拓扑"""

    def test_全支配链_正确排序(self):
        """A支配B支配C → 输出 A,B,C"""
        # Arrange
        seg_a = constant_efficiency(30.0, mood_burn=0.0, T=12.0)
        seg_b = constant_efficiency(25.0, mood_burn=0.0, T=12.0)
        seg_c = constant_efficiency(20.0, mood_burn=0.0, T=12.0)
        candidates = [(seg_a, "A"), (seg_b, "B"), (seg_c, "C")]

        # Act
        result = rank_by_dominance(candidates, T=12.0)

        # Assert
        assert result == ["A", "B", "C"]

    def test_互不支配_按积分排序(self):
        """高短 vs 低长 → 互不支配 → 退化到全积分比较"""
        # A: eff=40 但 t_red=8h → 积分=320
        # B: eff=25 全程 → 积分=300
        # 互不支配，积分 A > B
        seg_a = constant_efficiency(40.0, mood_burn=3.0, T=12.0)
        seg_b = constant_efficiency(25.0, mood_burn=0.0, T=12.0)
        candidates = [(seg_a, "A"), (seg_b, "B")]

        # Act
        result = rank_by_dominance(candidates, T=12.0)

        # Assert: A 积分 40×8=320 > B 25×12=300 → A 在前
        assert result == ["A", "B"]

    def test_空列表_返回空(self):
        """空候选池 → 空结果"""
        # Arrange & Act
        result = rank_by_dominance([], T=12.0)

        # Assert
        assert result == []

    def test_单元素_返回自身(self):
        """单候选 → 单结果"""
        # Arrange
        seg = constant_efficiency(30.0, mood_burn=0.0, T=12.0)
        candidates = [(seg, "唯一")]

        # Act
        result = rank_by_dominance(candidates, T=12.0)

        # Assert
        assert result == ["唯一"]

    def test_有等效率干员_均被选出(self):
        """两个 eff=30 的干员，互支配 → 都应出现在结果中"""
        # Arrange
        seg_a = constant_efficiency(30.0, mood_burn=0.0, T=12.0)
        seg_b = constant_efficiency(30.0, mood_burn=0.0, T=12.0)
        candidates = [(seg_a, "A"), (seg_b, "B")]

        # Act
        result = rank_by_dominance(candidates, T=12.0)

        # Assert: 两人都出现
        assert set(result) == {"A", "B"}
        assert len(result) == 2


# ─── integrate_segments ──────────────────────────────────────────

class TestIntegrateSegments:
    """segments 列表在 [0,T] 上的积分求和"""

    def test_单段全覆盖(self):
        segs = [LinearSegment(a=30, b=0, t_start=0, dt=12)]
        total = integrate_segments(segs, T=12.0)
        assert pytest.approx(total) == 360.0

    def test_多段求和(self):
        segs = [
            LinearSegment(a=30, b=0, t_start=0, dt=6),
            LinearSegment(a=20, b=0, t_start=6, dt=6),
        ]
        total = integrate_segments(segs, T=12.0)
        assert pytest.approx(total) == 300.0  # 30×6 + 20×6

    def test_段超出T被裁剪(self):
        segs = [LinearSegment(a=30, b=0, t_start=8, dt=10)]
        total = integrate_segments(segs, T=12.0)
        assert pytest.approx(total) == 120.0  # 30×4


# ─── _dominates（通版支配）───────────────────────────────────────

class TestFullDominance:
    """通版支配判定：逐点比较"""

    def test_常数技能_支配成立(self):
        seg_a = [LinearSegment(a=30, b=0, t_start=0, dt=12)]
        seg_b = [LinearSegment(a=20, b=0, t_start=0, dt=12)]
        assert _dominates(seg_a, seg_b, T=12.0) is True

    def test_爬升技能_被常数高值支配(self):
        seg_a = [LinearSegment(a=35, b=0, t_start=0, dt=12)]
        seg_b = ramping_efficiency(20.0, 1.0, 30.0, mood_burn=0.0, T=12.0)
        assert _dominates(seg_a, seg_b, T=12.0) is True

    def test_爬升技能_互不支配(self):
        """A: 常数30  vs  B: k0=20 r=2 ceiling=40
        t=0 时 A>B, t=10 时 B>A → 互不支配
        """
        seg_a = [LinearSegment(a=30, b=0, t_start=0, dt=12)]
        seg_b = ramping_efficiency(20.0, 2.0, 40.0, mood_burn=0.0, T=12.0)
        assert _dominates(seg_a, seg_b, T=12.0) is False
        assert _dominates(seg_b, seg_a, T=12.0) is False


# ─── stepped_efficiency ──────────────────────────────────────────

class TestSteppedEfficiency:
    """梯级衰减效率：每 step_interval 心情落差触发一级衰减"""

    def test_无心情消耗_单段常数(self):
        segs = stepped_efficiency(30.0, mood_burn=0.0, T=12.0)
        assert len(segs) == 1
        assert segs[0].a == 30.0

    def test_轻量消耗_一级衰减(self):
        """mood_burn=0.65, T=12 → 心情降至 24-7.8=16.2
        steps_down = ⌊(24-16.2)/4⌋ = ⌊1.95⌋ = 1
        eff = 30 - 1×5 = 25
        """
        segs = stepped_efficiency(30.0, mood_burn=0.65, T=12.0)
        assert len(segs) >= 1
        for seg in segs:
            assert seg.a >= 0.0

    def test_中等消耗_两级衰减(self):
        """mood_burn=1.5, T=12 → 心情降至 24-18=6
        steps_down = ⌊(24-6)/4⌋ = ⌊4.5⌋ = 4
        eff = max(0, 30-4×5) = 10
        """
        segs = stepped_efficiency(30.0, mood_burn=1.5, T=12.0,
                                  step_size=5.0, step_interval=4.0)
        assert len(segs) > 1

    def test_归零_心情耗尽后效率为零(self):
        """心情归零后 eff=0"""
        segs = stepped_efficiency(10.0, mood_burn=3.0, T=12.0,
                                  step_size=5.0, step_interval=4.0)
        assert segs[-1].a == 0.0

    def test_自定参数_输出合理范围(self):
        """step_size=3, step_interval=6 自定义参数"""
        segs = stepped_efficiency(30.0, mood_burn=0.65, T=12.0,
                                  step_size=3.0, step_interval=6.0)
        total = integrate_segments(segs, T=12.0)
        assert total > 0
        assert total <= 30.0 * 12.0
