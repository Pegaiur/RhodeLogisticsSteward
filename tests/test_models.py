"""数据模型单元测试 (models.py, LinearSegment)

全部测试通过内存构造，不依赖磁盘文件。
遵循 TDD 3A 模式 (Arrange → Act → Assert)。
"""

import pytest

from steward_core.models import EfficiencyMap, LinearSegment, Operator, Skill


def _mk_op(name: str = "测试干员", skills: list[Skill] | None = None) -> Operator:
    return Operator(char_id=name, name=name, skills=skills or [])


def _mk_skill(room_type: str, efficient: dict[str, float], buff_id: str = "test_buff") -> Skill:
    return Skill(
        buff_id=buff_id,
        buff_name="测试技能",
        skill_icon=f"test_{buff_id}",
        room_type=room_type,
        efficient=EfficiencyMap(raw=efficient),
    )


# ─── Operator 身份字段扩展 ──────────────────────────────────────

class TestOperatorIdentity:
    """MV0-1: Operator 新增 group_id / nation_id / team_id"""

    def test_新建干员_默认无身份字段(self):
        """新建 Operator 不传身份字段时，三者均为 None"""
        # Arrange & Act
        op = Operator(char_id="char_test", name="测试")

        # Assert
        assert op.group_id is None
        assert op.nation_id is None
        assert op.team_id is None

    def test_设置身份字段_可正确读取(self):
        """显式传入身份字段后，可正确读取"""
        # Arrange & Act
        op = Operator(
            char_id="char_003_kalts",
            name="凯尔希",
            rarity=5,
            group_id="rhodes",
            nation_id="rhodes",
            team_id="sweep",
        )

        # Assert
        assert op.group_id == "rhodes"
        assert op.nation_id == "rhodes"
        assert op.team_id == "sweep"

    def test_部分身份字段_其余为None(self):
        """只传部分身份字段，未传的仍为 None"""
        # Arrange & Act
        op = Operator(
            char_id="char_test",
            name="测试",
            group_id="glasgow",
        )

        # Assert
        assert op.group_id == "glasgow"
        assert op.nation_id is None
        assert op.team_id is None

    def test_向后兼容_原有代码不传身份字段仍可运行(self):
        """不传新字段时，best_efficiency 和 has_skill_for 仍正常工作"""
        # Arrange
        sk = _mk_skill("Mfg", {"all": 30})
        op = Operator(char_id="op1", name="万能工", skills=[sk])

        # Act
        eff = op.best_efficiency("Mfg", "PureGold")
        has = op.has_skill_for("Mfg", "PureGold")

        # Assert
        assert eff == 30.0
        assert has is True
        assert op.group_id is None


# ─── LinearSegment ───────────────────────────────────────────────

class TestLinearSegment:
    """MV0-2: LinearSegment 数据结构与积分"""

    def test_常数段_构造正确(self):
        """常数段 a=30, b=0, t_start=0, dt=12 → integrate=360"""
        # Arrange & Act
        seg = LinearSegment(a=30.0, b=0.0, t_start=0.0, dt=12.0)

        # Assert: 积分 = 30 × 12 = 360
        assert seg.a == 30.0
        assert seg.b == 0.0
        assert seg.t_start == 0.0
        assert seg.dt == 12.0
        assert pytest.approx(seg.integrate()) == 360.0

    def test_线性段_构造正确(self):
        """线性段 a=10, b=2, t_start=0, dt=5 → integrate = 10×5 + 2×(25-0)/2 = 75"""
        # Arrange & Act
        seg = LinearSegment(a=10.0, b=2.0, t_start=0.0, dt=5.0)

        # Assert: ∫(10+2t)dt from 0 to 5 = 10*5 + 2*25/2 = 50 + 25 = 75
        assert pytest.approx(seg.integrate()) == 75.0

    def test_线性段_非零起始时间(self):
        """线性段从 t=3 开始 → integrate 应正确计算偏移"""
        # Arrange: e(t) = 10 + 2t, t ∈ [3, 8]
        # ∫(10+2t)dt from 3 to 8 = (10*8 + 8²) - (10*3 + 3²) = (80+64) - (30+9) = 144-39 = 105
        # Or: 10*5 + 2*(64-9)/2 = 50 + 55 = 105
        seg = LinearSegment(a=10.0, b=2.0, t_start=3.0, dt=5.0)

        # Act
        val = seg.integrate()

        # Assert
        assert pytest.approx(val) == 105.0

    def test_零时长段_积分为零(self):
        """dt=0 → 积分必为零"""
        # Arrange & Act
        seg = LinearSegment(a=100.0, b=50.0, t_start=0.0, dt=0.0)

        # Assert
        assert seg.integrate() == 0.0

    def test_负数效率_积分可为负(self):
        """a<0 时积分可以为负 (表示惩罚)"""
        # Arrange & Act
        seg = LinearSegment(a=-10.0, b=0.0, t_start=0.0, dt=12.0)

        # Assert: -10 × 12 = -120
        assert pytest.approx(seg.integrate()) == -120.0

    def test_纯斜率段_截距为零(self):
        """a=0, b=3, t_start=0, dt=4 → integrate = 0×4 + 3×(16-0)/2 = 24"""
        # Arrange & Act
        seg = LinearSegment(a=0.0, b=3.0, t_start=0.0, dt=4.0)

        # Assert
        assert pytest.approx(seg.integrate()) == 24.0


# ─── LinearSegment 辅助函数（预热，实现在 MV1） ──────────────────

class TestLinearSegmentHelpers:
    """即将在 MV1 efficiency_fn.py 中实现的辅助函数"""

    def test_空列表积分_返回零(self):
        """空段列表积分应为 0"""
        # 此函数尚未实现，测试将失败 → 红灯
        from steward_core.efficiency_fn import integrate_segments

        # Act
        val = integrate_segments([], T=12.0)

        # Assert
        assert val == 0.0

    def test_单段积分_与段自身一致(self):
        """单段积分应与 segment.integrate() 一致"""
        from steward_core.efficiency_fn import integrate_segments

        # Arrange
        seg = LinearSegment(a=30.0, b=0.0, t_start=0.0, dt=12.0)

        # Act
        val = integrate_segments([seg], T=12.0)

        # Assert
        assert pytest.approx(val) == seg.integrate()
