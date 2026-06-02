"""Reception 组合枚举单元测试

验证 _select_reception_combo 对条件型 buff 的正确感知：
solo（独享）、pair（配对）、faction（阵营）、dorm_has（跨房），
以及使能者（无 Reception 技能的干员）的自动准入。
"""

import pytest

from steward_core.models import EfficiencyMap, LayoutConfig, Operator, Skill
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext


def _rec_op(name: str, char_id: str, *buff_ids: str,
            rarity: int = 5, elite_phase: int = 2,
            nation_id: str | None = None,
            group_id: str | None = None) -> Operator:
    """构造会客室干员"""
    skills = []
    for bid in buff_ids:
        skills.append(Skill(
            buff_id=bid, buff_name=bid, skill_icon=bid,
            room_type="Reception",
            efficient=EfficiencyMap(raw={"General": 0.0}),
        ))
    return Operator(
        char_id=char_id, name=name, rarity=rarity,
        elite_phase=elite_phase,
        skills=skills,
        nation_id=nation_id, group_id=group_id,
    )


def _dummy_op(name: str, char_id: str) -> Operator:
    """无技能的普通干员（使能者）"""
    return Operator(char_id=char_id, name=name, skills=[])


# ─── 条件表（导入后使用，此处仅声明） ────────────────────────────


class TestReceptionCombo:
    """Reception 组合枚举 — 红灯：先写测试，预留函数接口"""

    @pytest.fixture
    def params(self):
        return SolverParams()

    @pytest.fixture
    def layout(self):
        return LayoutConfig.layout_243()

    def _make_ctx(self, ops, params, layout):
        return SlotContext.from_layout(ops, layout, params)

    # ─── 红灯 1: 独享条件 ────────────────────────────────────────

    def test_solo_kazema_gets_35_pct(self, params, layout):
        """风丸 meet_spd_condChar[000] 单独在会客室 → +35%"""
        from steward_core.solver.slot.contribution import (
            _select_reception_combo,
        )
        kazema = _rec_op("风丸", "char_kazema", "meet_spd_condChar[000]")
        ops = [kazema]
        ctx = self._make_ctx(ops, params, layout)
        D = {}

        combo = _select_reception_combo(ctx, 0, D)
        assert len(combo) == 1
        assert combo[0] == "风丸"

    def test_solo_hamoni_gets_50_pct(self, params, layout):
        """和弦 meet_spd&cost_condChar[000] 单独在会客室 → +50%"""
        from steward_core.solver.slot.contribution import (
            _select_reception_combo,
        )
        hamoni = _rec_op("和弦", "char_hamoni", "meet_spd&cost_condChar[000]")
        ops = [hamoni]
        ctx = self._make_ctx(ops, params, layout)
        D = {}

        combo = _select_reception_combo(ctx, 0, D)
        assert len(combo) == 1
        assert combo[0] == "和弦"

    # ─── 红灯 2: 配对条件 ────────────────────────────────────────

    def test_pair_vulpis_lisa_gets_30_pct(self, params, layout):
        """忍冬 meet_spd&bd[100] + 铃兰同房 → +30%（铃兰无 Reception 技能）"""
        from steward_core.solver.slot.contribution import (
            _select_reception_combo,
        )
        vulpis = _rec_op("忍冬", "char_vulpis", "meet_spd&bd[100]")
        lisa = _dummy_op("铃兰", "char_lisa")
        ops = [vulpis, lisa]
        ctx = self._make_ctx(ops, params, layout)
        D = {}

        combo = _select_reception_combo(ctx, 0, D)
        assert set(combo) == {"忍冬", "铃兰"}

    def test_pair_threye_typhon_gets_15_pct(self, params, layout):
        """凛视 meet_spd&bd[010] + 提丰同房 → +15%"""
        from steward_core.solver.slot.contribution import (
            _select_reception_combo,
        )
        threye = _rec_op("凛视", "char_threye", "meet_spd&bd[010]")
        typhon = _rec_op("提丰", "char_typhon", "meet_spd&sami[000]")
        ops = [threye, typhon]
        ctx = self._make_ctx(ops, params, layout)
        D = {}

        combo = _select_reception_combo(ctx, 0, D)
        assert set(combo) == {"凛视", "提丰"}

    # ─── 红灯 3: 阵营配对 ───────────────────────────────────────

    def test_faction_typhon_sami(self, params, layout):
        """提丰 meet_spd&sami[000] + 萨米干员同房 → +5%"""
        from steward_core.solver.slot.contribution import (
            _select_reception_combo,
        )
        typhon = _rec_op("提丰", "char_typhon", "meet_spd&sami[000]",
                          nation_id="sami")
        sami_op = _rec_op("凛视", "char_threye", "meet_spd&bd[010]",
                          nation_id="sami")
        ops = [typhon, sami_op]
        ctx = self._make_ctx(ops, params, layout)
        D = {}

        combo = _select_reception_combo(ctx, 0, D)
        assert set(combo) == {"提丰", "凛视"}

    # ─── 红灯 4: 组合 vs 贪心回归 ────────────────────────────────

    def test_combo_does_not_regress_for_unconditional(self, params, layout):
        """无条件纯效率干员，组合枚举结果不退化于贪心单点"""
        from steward_core.solver.slot.contribution import (
            _select_reception_combo,
        )
        op_a = _rec_op("A", "char_a", "meet_spd[030]")  # 25%
        op_b = _rec_op("B", "char_b", "meet_spd[020]")  # 20%
        ops = [op_a, op_b]
        ctx = self._make_ctx(ops, params, layout)
        D = {}

        combo = _select_reception_combo(ctx, 0, D)
        assert len(combo) == 2
        assert "A" in combo
        assert "B" in combo

    # ─── 红灯 5: 空候选池 ────────────────────────────────────────

    def test_empty_candidate_returns_empty(self, params, layout):
        """无会客室技能干员 → 返回空列表"""
        from steward_core.solver.slot.contribution import (
            _select_reception_combo,
        )
        ops = [_dummy_op("X", "char_x"), _dummy_op("Y", "char_y")]
        ctx = self._make_ctx(ops, params, layout)
        D = {}

        combo = _select_reception_combo(ctx, 0, D)
        assert combo == []
