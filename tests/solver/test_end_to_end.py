"""端到端/集成测试

真数据验证与纯内存端到端路径测试。
"""

from pathlib import Path

import pytest

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


_TEST_ANCHORS = {"水月", "海沫", "森蚺", "温蒂", "多萝西", "苍苔", "掠风", "异客"}


class TestRealDataEndToEnd:
    """真数据验证：核心人数约束"""

    def test_制造站候选人数_匹配文档预期(self):
        """从真数据加载后，CR=60, PG=56 与文档一致"""
        from steward_core.data_loader import load_operators_v2, ROOM_TYPE_MAP
        from steward_core.synergy import classify_mfg_operators

        project_root = Path(__file__).resolve().parent.parent.parent
        ci_path = project_root / "character_identity.json"
        bi_path = project_root / "buffs_infrastructure.json"

        if not ci_path.exists() or not bi_path.exists():
            pytest.skip("真数据文件不存在")

        all_ops = load_operators_v2(ci_path, bi_path)
        mfg_ops = [op for op in all_ops if op.has_skill_for("Mfg")]

        cr = [op for op in mfg_ops if op.has_skill_for("Mfg", "CombatRecord")]
        pg = [op for op in mfg_ops if op.has_skill_for("Mfg", "PureGold")]

        # CR 候选人数在合理范围（游戏版本更新时上限会增长，仅保底下限）
        assert len(cr) >= 50
        assert len(pg) >= 50

        # 分类验证
        classification = classify_mfg_operators(cr, "CombatRecord", _TEST_ANCHORS)
        assert len(classification.anchors) >= 3  # 至少水月/多萝西/海沫

    def test_end_to_end_纯内存_无崩溃(self):
        """端到端求解不崩溃"""
        # 此测试用纯内存数据跑通路径，不验证结果正确性
        from steward_core.synergy import classify_mfg_operators, build_candidate_pool
        from steward_core.solver.greed import _generate_combos, _greedy_allocate
        from steward_core.evaluate import evaluate_room

        # Arrange: 构造 6 个制造站干员（模拟真实分布）
        ops = [
            _mk_op("地灵", [_mk_mfg_skill("s", 35.0, "a")]),
            _mk_op("裂响", [_mk_mfg_skill("s", 35.0, "b")]),
            _mk_op("水月", [_mk_mfg_skill("标准化·α", 25.0, "s1")]),
            _mk_op("海沫", [_mk_mfg_skill("标准化·β", 25.0, "s2")]),
            _mk_op("杰西卡", [_mk_mfg_skill("标准化·α", 25.0, "s3")]),
            _mk_op("白雪", [_mk_mfg_skill("标准化·α", 30.0, "s4")]),
        ]

        classification = classify_mfg_operators(ops, "CombatRecord", _TEST_ANCHORS)
        pool = build_candidate_pool(ops, classification)
        combos = _generate_combos(pool, 3)

        evaluated = []
        for combo_ops in combos:
            score = evaluate_room(combo_ops, "Mfg", "CombatRecord", power_count=3)
            evaluated.append((score, [op.name for op in combo_ops]))

        evaluated.sort(key=lambda x: -x[0])
        allocated = _greedy_allocate(evaluated, room_count=2)

        # Assert: 成功分配至少1间
        assert len(allocated) >= 1
        assert len(allocated[0]) == 3
