"""数据模型单元测试 (models.py, LinearSegment)

全部测试通过内存构造，不依赖磁盘文件。
遵循 TDD 3A 模式 (Arrange → Act → Assert)。
"""

import pytest

from steward_core.models import EfficiencyMap, LinearSegment, Operator, Skill


def _mk_op(name: str = "测试干员", skills: list[Skill] | None = None,
           elite_phase: int = 2) -> Operator:
    return Operator(char_id=name, name=name, skills=skills or [], elite_phase=elite_phase)


def _mk_skill(room_type: str, efficient: dict[str, float], buff_id: str = "test_buff",
              phase: int = 0) -> Skill:
    return Skill(
        buff_id=buff_id,
        buff_name="测试技能",
        skill_icon=f"test_{buff_id}",
        room_type=room_type,
        efficient=EfficiencyMap(raw=efficient),
        phase=phase,
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
        """不传新字段时，operator_estimated_efficiency 和 has_skill_for 仍正常工作"""
        from steward_core.synergy import operator_estimated_efficiency
        # Arrange
        sk = _mk_skill("Mfg", {"all": 30})
        op = Operator(char_id="op1", name="万能工", skills=[sk])

        # Act
        eff = operator_estimated_efficiency(op, "Mfg", "PureGold")
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


# ─── active_skills_for 升级/共存判定 ─────────────────────────────

class TestActiveSkillsFor:
    """Operator.active_skills_for — 同前缀升级去重、异前缀共存"""

    def test_同前缀不同phase_取最高phase(self):
        """同前缀 buffId，phase 0→2 升级链，仅保留 phase 2"""
        # Arrange: 迷迭香: bd_n1[000](phase 0) + bd[000](phase 0) + bd[010](phase 2)
        bd_n1 = _mk_skill("Mfg", {"all": 0.0}, buff_id="manu_prod_spd_bd_n1[000]", phase=0)
        bd_alpha = _mk_skill("Mfg", {"all": 0.0}, buff_id="manu_prod_spd_bd[000]", phase=0)
        bd_beta = _mk_skill("Mfg", {"all": 0.0}, buff_id="manu_prod_spd_bd[010]", phase=2)
        op = _mk_op("迷迭香", skills=[bd_n1, bd_alpha, bd_beta])

        # Act
        active = op.active_skills_for("Mfg")

        # Assert: bd_n1 不同前缀共存 + bd 组内取 bd_beta
        assert len(active) == 2
        buff_ids = {sk.buff_id for sk in active}
        assert "manu_prod_spd_bd_n1[000]" in buff_ids
        assert "manu_prod_spd_bd[010]" in buff_ids
        assert "manu_prod_spd_bd[000]" not in buff_ids

    def test_异前缀_全部保留(self):
        """不同前缀技能全部共存"""
        # Arrange: 德克萨斯: spd&cost_P + limit&cost_P
        sk1 = _mk_skill("Trade", {"all": 65.0}, buff_id="trade_ord_spd&cost_P[000]", phase=0)
        sk2 = _mk_skill("Trade", {"all": 0.0}, buff_id="trade_ord_limit&cost_P[010]", phase=2)
        op = _mk_op("德克萨斯", skills=[sk1, sk2])

        # Act
        active = op.active_skills_for("Trade")

        # Assert: 两个都保留
        assert len(active) == 2
        buff_ids = {sk.buff_id for sk in active}
        assert "trade_ord_spd&cost_P[000]" in buff_ids
        assert "trade_ord_limit&cost_P[010]" in buff_ids

    def test_同前缀同phase取效率高者(self):
        """同前缀且 phase 相同，取效率值更高的"""
        # Arrange
        sk_weak = _mk_skill("Trade", {"all": 15.0}, buff_id="trade_ord_spd[010]", phase=0)
        sk_strong = _mk_skill("Trade", {"all": 25.0}, buff_id="trade_ord_spd[011]", phase=0)
        op = _mk_op("测试", skills=[sk_weak, sk_strong])

        # Act
        active = op.active_skills_for("Trade")

        # Assert: 仅保留效率高的
        assert len(active) == 1
        assert active[0].buff_id == "trade_ord_spd[011]"
        assert active[0].efficient.max_value() == 25.0

    def test_裁缝同前缀仍走升级去重_豁免由调用方负责(self):
        """裁缝 trade_ord_wt&cost 在 active_skills_for 层面仍升级去重

        裁缝是已知豁免：α+β 在游戏中共存叠加。
        但 active_skills_for 不做特殊处理——豁免由调用方 (_extract_tailor_level)
        使用 raw op.skills 实现。
        """
        # Arrange
        tailor_a = _mk_skill("Trade", {"all": 0.0}, buff_id="trade_ord_wt&cost[000]", phase=0)
        tailor_b = _mk_skill("Trade", {"all": 0.0}, buff_id="trade_ord_wt&cost[010]", phase=2)
        op = _mk_op("柏喙", skills=[tailor_a, tailor_b])

        # Act
        active = op.active_skills_for("Trade")

        # Assert: 按通用规则，同前缀升级去重 → 仅保留 β
        assert len(active) == 1
        assert active[0].buff_id == "trade_ord_wt&cost[010]"

    def test_elite_phase过滤_仅保留已解锁技能(self):
        """Operator.elite_phase=1 时，phase=2 的技能被过滤"""
        # Arrange
        sk_e0 = _mk_skill("Mfg", {"all": 15.0}, buff_id="manu_prod_spd[001]", phase=0)
        sk_e2 = _mk_skill("Mfg", {"all": 25.0}, buff_id="manu_prod_spd[011]", phase=2)
        op = _mk_op("赫默", skills=[sk_e0, sk_e2], elite_phase=1)

        # Act
        active = op.active_skills_for("Mfg")

        # Assert: 仅 phase 0 可用
        assert len(active) == 1
        assert active[0].buff_id == "manu_prod_spd[001]"

    def test_elite_phase等于2_全部技能可用(self):
        """Operator.elite_phase=2 时，phase 0/1/2 均可用"""
        # Arrange
        sk0 = _mk_skill("Mfg", {"all": 10.0}, buff_id="manu_prod_spd[000]", phase=0)
        sk2 = _mk_skill("Mfg", {"all": 30.0}, buff_id="manu_prod_spd[010]", phase=2)
        op = _mk_op("测试", skills=[sk0, sk2], elite_phase=2)

        # Act
        active = op.active_skills_for("Mfg")

        # Assert: phase 2 生效（同前缀升级）
        assert len(active) == 1
        assert active[0].buff_id == "manu_prod_spd[010]"

    def test_不同roomType不互相干扰(self):
        """Mfg 技能不受 Trade 技能迭代影响"""
        # Arrange
        mfg_sk = _mk_skill("Mfg", {"all": 25}, buff_id="manu_prod_spd[011]", phase=2)
        trade_sk = _mk_skill("Trade", {"all": 20}, buff_id="trade_ord_spd[000]", phase=0)
        op = _mk_op("测试", skills=[mfg_sk, trade_sk])

        # Act
        mfg_active = op.active_skills_for("Mfg")
        trade_active = op.active_skills_for("Trade")

        # Assert
        assert len(mfg_active) == 1
        assert mfg_active[0].buff_id == "manu_prod_spd[011]"
        assert len(trade_active) == 1
        assert trade_active[0].buff_id == "trade_ord_spd[000]"
