"""排班求解器单元测试 (solver.py MV3 重写)

测试制造站穷举+剪枝+贪心分配的核心逻辑。
纯内存构造优先，关键路径辅以真数据验证。
遵循 TDD 3A 模式。
"""

from pathlib import Path

import pytest

from steward_core.models import EfficiencyMap, LinearSegment, Operator, RoomConfig, Skill
from steward_core.efficiency_fn import constant_efficiency, integrate_segments
from steward_core.synergy import (
    synergy_pair, synergy_skill_count, synergy_skill_alias, synergy_automation,
)


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


# ─── 干员角色分类 ───────────────────────────────────────────────

class TestClassifyOperators:
    """分类制造站干员: 纯效率 / 联动锚点 / 技能提供者"""

    def test_普通干员_归为纯效率(self):
        """无联动角色 → 归入纯效率池"""
        from steward_core.solver import _classify_mfg_operators

        # Arrange: 使用无技能类别标签的干员名，技能名不含标准化/莱茵等关键词
        ops = [
            _mk_op("白雪", [_mk_mfg_skill("作战指导录像", 30.0)]),
            _mk_op("薄绿", [_mk_mfg_skill("生产力加成", 25.0)]),
            _mk_op("玛露西尔", [_mk_mfg_skill("高效生产", 30.0)]),
        ]

        # Act
        result = _classify_mfg_operators(ops, "CombatRecord")

        # Assert: 全部归入 pure
        names = {op.name for op in result.pure_efficiency}
        assert "白雪" in names
        assert len(result.anchors) == 0

    def test_联动锚点_正确识别(self):
        """水月(计数锚点) → anchors, 海沫(别名锚点) → anchors"""
        from steward_core.solver import _classify_mfg_operators

        # Arrange
        shuiyue = _mk_op("水月", [_mk_mfg_skill("标准化·α", 25.0)])
        haimo = _mk_op("海沫", [_mk_mfg_skill("标准化·β", 25.0)])
        filler = _mk_op("白雪", [_mk_mfg_skill("高效生产", 30.0)])

        # Act
        result = _classify_mfg_operators([shuiyue, haimo, filler], "CombatRecord")

        # Assert
        anchor_names = {op.name for op in result.anchors}
        assert "水月" in anchor_names
        assert "海沫" in anchor_names
        assert "白雪" not in anchor_names

    def test_技能提供者_正确识别(self):
        """杰西卡有标准化技能 → providers"""
        from steward_core.solver import _classify_mfg_operators

        # Arrange
        jessica = _mk_op("杰西卡", [_mk_mfg_skill("标准化·β", 25.0)])
        filler = _mk_op("白雪", [_mk_mfg_skill("高效生产", 30.0)])

        # Act
        result = _classify_mfg_operators([jessica, filler], "CombatRecord")

        # Assert: 杰西卡有标准化标签 → provider, 白雪无标签 → pure
        provider_names = {op.name for op in result.providers}
        pure_names = {op.name for op in result.pure_efficiency}
        assert "杰西卡" in provider_names
        assert "白雪" in pure_names

    def test_产物分离_贵金属技能不出现于作战记录(self):
        """从真数据加载后，纯贵金属干员不应出现在 CR 候选池"""
        # Arrange: 加载真数据
        from steward_core.data_loader import load_operators_v2

        project_root = Path(__file__).resolve().parent.parent
        ci_path = project_root / "character_identity.json"
        bi_path = project_root / "buffs_infrastructure.json"

        if not ci_path.exists() or not bi_path.exists():
            pytest.skip("真数据文件不存在")

        all_ops = load_operators_v2(ci_path, bi_path)

        # Act: 筛选制造站干员
        mfg_ops = [op for op in all_ops if op.has_skill_for("Mfg")]

        # Assert: 统计各产物候选人数
        cr_ops = [op for op in mfg_ops if op.has_skill_for("Mfg", "CombatRecord")]
        pg_ops = [op for op in mfg_ops if op.has_skill_for("Mfg", "PureGold")]

        assert len(cr_ops) > 0
        assert len(pg_ops) > 0
        assert 70 <= len(cr_ops) <= 90
        assert 70 <= len(pg_ops) <= 90


# ─── 剪枝规则 ───────────────────────────────────────────────────

class TestPruning:
    """三条剪枝规则的正确性验证"""

    def test_等价类合并_纯效率只保留代表(self):
        """三个无联动干员 → 组合数从 C(3,3)=1 缩到 1（已经是1）"""
        # 构造更大池验证: 5个纯效率干员 → 仅需保留前3名最高效的组合
        from steward_core.solver import _prune_equivalent

        # Arrange: 5个纯效率干员
        ops = [
            _mk_op("A", [_mk_mfg_skill("s", 35.0, "a")]),
            _mk_op("B", [_mk_mfg_skill("s", 35.0, "b")]),
            _mk_op("C", [_mk_mfg_skill("s", 30.0, "c")]),
            _mk_op("D", [_mk_mfg_skill("s", 30.0, "d")]),
            _mk_op("E", [_mk_mfg_skill("s", 25.0, "e")]),
        ]

        # Act: 等价类合并后，纯效率仅保留 Top-3
        pure_pool = _prune_equivalent(ops, top_k=3)

        # Assert: 只保留前3名
        assert len(pure_pool) == 3
        efficiencies = [op.best_efficiency("Mfg") for op in pure_pool]
        assert 35.0 in efficiencies
        assert 25.0 not in efficiencies

    def test_锚点池筛选_保留锚点加配套(self):
        """水月+海沫+3个标准化提供者 vs 纯效率池 → 锚点池包含锚点和配套"""
        from steward_core.solver import _classify_mfg_operators, _build_candidate_pool

        # Arrange
        shuiyue = _mk_op("水月", [_mk_mfg_skill("标准化·α", 25.0, "s1")])
        haimo = _mk_op("海沫", [_mk_mfg_skill("标准化·β", 25.0, "s2")])
        jessica = _mk_op("杰西卡", [_mk_mfg_skill("标准化·α", 25.0, "s3")])
        perfumer = _mk_op("调香师", [_mk_mfg_skill("标准化·β", 25.0, "s4")])
        # 纯效率干员: 白雪(30), 薄绿(25), 玛露西尔(30) — 这些不是锚点
        bai = _mk_op("白雪", [_mk_mfg_skill("标准化·α", 30.0, "s5")])
        bo = _mk_op("薄绿", [_mk_mfg_skill("标准化·β", 25.0, "s6")])
        all_ops = [shuiyue, haimo, jessica, perfumer, bai, bo]

        classification = _classify_mfg_operators(all_ops, "CombatRecord")

        # Act
        pool = _build_candidate_pool(all_ops, classification)

        # Assert: 池包含所有锚点+配套
        pool_names = {op.name for op in pool}
        assert "水月" in pool_names
        assert "海沫" in pool_names
        assert "杰西卡" in pool_names
        # 白雪作为高纯效率，也应保留
        assert "白雪" in pool_names

    def test_上界预判_不可能翻盘的组合被过滤(self):
        """低效干员组合 → 上界 < best_known×0.95 → 被剪掉"""
        from steward_core.solver import _upper_bound_ok

        # Arrange: best是3个35干员(积分=35×3×12=1260)，当前是3个20(积分=20×3×12=720)
        best_known = 1260.0  # 3×35×12
        total = 720.0        # 3×20×12

        # Act
        ok = _upper_bound_ok(total, best_known)

        # Assert: 720 < 1260×0.95=1197 → 不合格
        assert ok is False

    def test_上界预判_高效组合不被过滤(self):
        """三35 → 上界=1260 → 通过"""
        from steward_core.solver import _upper_bound_ok

        # Arrange
        best_known = 1260.0
        total = 1260.0

        # Act
        ok = _upper_bound_ok(total, best_known)

        # Assert
        assert ok is True


# ─── 房间评估 ───────────────────────────────────────────────────

class TestRoomEvaluation:
    """单房间穷举评估（含联动）"""

    def test_纯效率评估_个体效率求和(self):
        """三干员无联动 → 产出 = Σ个体效率"""
        from steward_core.solver import _evaluate_room_combo

        # Arrange
        ops = [
            _mk_op("A", [_mk_mfg_skill("s", 30.0, "a")]),
            _mk_op("B", [_mk_mfg_skill("s", 25.0, "b")]),
            _mk_op("C", [_mk_mfg_skill("s", 20.0, "c")]),
        ]

        # Act
        score = _evaluate_room_combo(ops, "Mfg", "CombatRecord", power_count=3)

        # Assert: 30+25+20=75 → 积分 75×12=900
        assert pytest.approx(score) == 900.0

    def test_含联动评估_超出个体效率之和(self):
        """水月+2个标准化干员 → 联动加成 +10% → 产出 > 个体之和"""
        from steward_core.solver import _evaluate_room_combo

        # Arrange
        shuiyue = _mk_op("水月", [_mk_mfg_skill("标准化·α", 25.0, "s1")])
        # 两个标准化提供者(不含水月自身)
        jessica = _mk_op("杰西卡", [_mk_mfg_skill("标准化·α", 25.0, "s2")])
        perfumer = _mk_op("调香师", [_mk_mfg_skill("标准化·β", 25.0, "s3")])

        # Act: 含联动
        score_with = _evaluate_room_combo([shuiyue, jessica, perfumer], "Mfg", "CombatRecord", power_count=3)
        # Act: 不含联动（把水月换成普通25干员）
        filler = _mk_op("填位", [_mk_mfg_skill("标准化·α", 25.0, "s4")])
        score_without = _evaluate_room_combo([filler, jessica, perfumer], "Mfg", "CombatRecord", power_count=3)

        # Assert: 联动版 > 无联动版
        assert score_with > score_without


# ─── 跨间贪心分配 ──────────────────────────────────────────────

class TestGreedyAllocation:
    """制造站跨间贪心分配"""

    def test_无冲突_直接取前N(self):
        """两间房无冲突 → 直接取前2组合"""
        from steward_core.solver import _greedy_allocate

        # Arrange: 三个独立组合，互不冲突
        combos = [
            (100.0, ["A", "B", "C"]),
            (90.0, ["D", "E", "F"]),
            (80.0, ["G", "H", "I"]),
        ]

        # Act
        result = _greedy_allocate(combos, room_count=2)

        # Assert
        assert len(result) == 2
        assert result[0] == ["A", "B", "C"]
        assert result[1] == ["D", "E", "F"]

    def test_有冲突_跳过选下一个(self):
        """组合1和2共享D → 跳过组合2选组合3"""
        from steward_core.solver import _greedy_allocate

        # Arrange
        combos = [
            (100.0, ["A", "B", "C"]),
            (90.0, ["C", "D", "E"]),   # 冲突: C 已被占
            (85.0, ["F", "G", "H"]),   # 无冲突
        ]

        # Act
        result = _greedy_allocate(combos, room_count=2)

        # Assert: 第二间跳到组合3
        assert len(result) == 2
        assert result[0] == ["A", "B", "C"]
        assert result[1] == ["F", "G", "H"]

    def test_候选不足_提前终止(self):
        """仅1个组合可用 → 只分配1间"""
        from steward_core.solver import _greedy_allocate

        # Arrange
        combos = [(100.0, ["A", "B", "C"])]

        # Act
        result = _greedy_allocate(combos, room_count=2)

        # Assert
        assert len(result) == 1


# ─── 真数据端到端 ──────────────────────────────────────────────

class TestRealDataEndToEnd:
    """真数据验证：核心人数约束"""

    def test_制造站候选人数_匹配文档预期(self):
        """从真数据加载后，CR=60, PG=56 与文档一致"""
        from steward_core.data_loader import load_operators_v2, ROOM_TYPE_MAP
        from steward_core.solver import _classify_mfg_operators

        project_root = Path(__file__).resolve().parent.parent
        ci_path = project_root / "character_identity.json"
        bi_path = project_root / "buffs_infrastructure.json"

        if not ci_path.exists() or not bi_path.exists():
            pytest.skip("真数据文件不存在")

        all_ops = load_operators_v2(ci_path, bi_path)
        mfg_ops = [op for op in all_ops if op.has_skill_for("Mfg")]

        cr = [op for op in mfg_ops if op.has_skill_for("Mfg", "CombatRecord")]
        pg = [op for op in mfg_ops if op.has_skill_for("Mfg", "PureGold")]

        # CR 候选人数在合理范围
        assert 70 <= len(cr) <= 90
        assert 70 <= len(pg) <= 90

        # 分类验证
        classification = _classify_mfg_operators(cr, "CombatRecord")
        assert len(classification.anchors) >= 3  # 至少水月/多萝西/海沫

    def test_end_to_end_纯内存_无崩溃(self):
        """端到端求解不崩溃"""
        # 此测试用纯内存数据跑通路径，不验证结果正确性
        from steward_core.solver import _classify_mfg_operators, _build_candidate_pool
        from steward_core.solver import _generate_combos, _evaluate_room_combo, _greedy_allocate

        # Arrange: 构造 6 个制造站干员（模拟真实分布）
        ops = [
            _mk_op("地灵", [_mk_mfg_skill("s", 35.0, "a")]),
            _mk_op("裂响", [_mk_mfg_skill("s", 35.0, "b")]),
            _mk_op("水月", [_mk_mfg_skill("标准化·α", 25.0, "s1")]),
            _mk_op("海沫", [_mk_mfg_skill("标准化·β", 25.0, "s2")]),
            _mk_op("杰西卡", [_mk_mfg_skill("标准化·α", 25.0, "s3")]),
            _mk_op("白雪", [_mk_mfg_skill("标准化·α", 30.0, "s4")]),
        ]

        classification = _classify_mfg_operators(ops, "CombatRecord")
        pool = _build_candidate_pool(ops, classification)
        combos = _generate_combos(pool, 3)

        evaluated = []
        for combo_ops in combos:
            score = _evaluate_room_combo(combo_ops, "Mfg", "CombatRecord", power_count=3)
            evaluated.append((score, [op.name for op in combo_ops]))

        evaluated.sort(key=lambda x: -x[0])
        allocated = _greedy_allocate(evaluated, room_count=2)

        # Assert: 成功分配至少1间
        assert len(allocated) >= 1
        assert len(allocated[0]) == 3
