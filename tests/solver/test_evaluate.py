"""组合评估测试

测试 _evaluate_trade_combo（Trade 组合 LMD 日产评估）与 _upper_bound_ok（上界预判）。
"""

from steward_core.models import EfficiencyMap, Operator, Skill


def _mk_op(name: str = "测试", skills: list[Skill] | None = None,
           group_id: str | None = None) -> Operator:
    return Operator(char_id=name, name=name, skills=skills or [], group_id=group_id)


def _mk_mfg_skill(buff_name: str, efficiency: float, buff_id: str = "test",
                  room_type: str = "Mfg") -> Skill:
    return Skill(
        buff_id=buff_id, buff_name=buff_name, skill_icon=buff_id,
        room_type=room_type,
        efficient=EfficiencyMap(raw={"all": efficiency}),
    )


class TestEvaluateTradeCombo:
    """_evaluate_trade_combo: Trade 3人组合的 LMD 日产评估"""

    def test_纯效率三人组_产出为正(self):
        from steward_core.synergy import GlobalBonus, compute_buff_pool
        ops = [
            _mk_op("A", [_mk_mfg_skill("高效生产", 30.0, "generic", "Trade")]),
            _mk_op("B", [_mk_mfg_skill("高效生产", 30.0, "generic", "Trade")]),
            _mk_op("C", [_mk_mfg_skill("高效生产", 30.0, "generic", "Trade")]),
        ]
        from steward_core.solver.greed import _evaluate_trade_combo
        lmd = _evaluate_trade_combo(ops, 3, 12.0, GlobalBonus(), compute_buff_pool([], suich_count=0), 0.0)
        assert lmd > 5000, f"预期 >5000, 实际 {lmd:.0f}"

    def test_但书_产出高于基准(self):
        from steward_core.synergy import GlobalBonus, compute_buff_pool
        but = _mk_op("但书", [_mk_mfg_skill("合同法", 0.0, "trade_ord_law[000]", "Trade")])
        fa = _mk_op("A", [_mk_mfg_skill("高效生产", 30.0, "generic", "Trade")])
        fb = _mk_op("B", [_mk_mfg_skill("高效生产", 30.0, "generic", "Trade")])
        from steward_core.solver.greed import _evaluate_trade_combo
        lmd = _evaluate_trade_combo([but, fa, fb], 3, 12.0, GlobalBonus(), compute_buff_pool([], suich_count=0), 0.0)
        assert lmd > 7000, f"但书应大幅高于基准, 实际 {lmd:.0f}"


class TestPruning:
    """剪枝规则的正确性验证 — _upper_bound_ok"""

    def test_上界预判_不可能翻盘的组合被过滤(self):
        """低效干员组合 → 上界 < best_known×0.95 → 被剪掉"""
        from steward_core.solver.greed import _upper_bound_ok

        # Arrange: best是3个35干员(积分=35×3×12=1260)，当前是3个20(积分=20×3×12=720)
        best_known = 1260.0  # 3×35×12
        total = 720.0        # 3×20×12

        # Act
        ok = _upper_bound_ok(total, best_known)

        # Assert: 720 < 1260×0.95=1197 → 不合格
        assert ok is False

    def test_上界预判_高效组合不被过滤(self):
        """三35 → 上界=1260 → 通过"""
        from steward_core.solver.greed import _upper_bound_ok

        # Arrange
        best_known = 1260.0
        total = 1260.0

        # Act
        ok = _upper_bound_ok(total, best_known)

        # Assert
        assert ok is True
