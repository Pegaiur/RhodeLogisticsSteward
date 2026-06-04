"""制造站干员分类测试 (synergy/classification.py)

测试 classify_mfg_operators 锚点/提供者/纯效率分类、剪枝规则、房间评估。
"""

from pathlib import Path

import pytest

from steward_core.models import EfficiencyMap, Operator, Skill

# 分类测试中使用合成干员不在 _derived.py 中，
# 防御性兜底自然触发 UserWarning —— 这是预期行为。
pytestmark = pytest.mark.filterwarnings(
    "ignore:干员.*未在 _derived.py 注册:UserWarning",
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


_TEST_ANCHORS = {"水月", "海沫", "森蚺", "温蒂", "多萝西", "苍苔", "掠风", "异客"}


class TestClassifyOperators:
    """分类制造站干员: 纯效率 / 联动锚点 / 技能提供者"""

    def test_普通干员_归为纯效率(self):
        """无联动角色 → 归入纯效率池"""
        from steward_core.synergy import classify_mfg_operators

        # Arrange: 使用无技能类别标签的干员名，技能名不含标准化/莱茵等关键词
        ops = [
            _mk_op("白雪", [_mk_mfg_skill("作战指导录像", 30.0)]),
            _mk_op("薄绿", [_mk_mfg_skill("生产力加成", 25.0)]),
            _mk_op("玛露西尔", [_mk_mfg_skill("高效生产", 30.0)]),
        ]

        # Act
        result = classify_mfg_operators(ops, "CombatRecord", _TEST_ANCHORS)

        # Assert: 全部归入 pure
        names = {op.name for op in result.pure_efficiency}
        assert "白雪" in names
        assert len(result.anchors) == 0

    def test_联动锚点_正确识别(self):
        """水月(计数锚点) → anchors, 海沫(别名锚点) → anchors"""
        from steward_core.synergy import classify_mfg_operators

        # Arrange
        shuiyue = _mk_op("水月", [_mk_mfg_skill("标准化·α", 25.0)])
        haimo = _mk_op("海沫", [_mk_mfg_skill("标准化·β", 25.0)])
        filler = _mk_op("白雪", [_mk_mfg_skill("高效生产", 30.0)])

        # Act
        result = classify_mfg_operators([shuiyue, haimo, filler], "CombatRecord", _TEST_ANCHORS)

        # Assert
        anchor_names = {op.name for op in result.anchors}
        assert "水月" in anchor_names
        assert "海沫" in anchor_names
        assert "白雪" not in anchor_names

    def test_技能提供者_正确识别(self):
        """杰西卡有标准化技能 → providers"""
        from steward_core.synergy import classify_mfg_operators

        # Arrange
        jessica = _mk_op("杰西卡", [_mk_mfg_skill("标准化·β", 25.0)])
        filler = _mk_op("白雪", [_mk_mfg_skill("高效生产", 30.0)])

        # Act
        result = classify_mfg_operators([jessica, filler], "CombatRecord", _TEST_ANCHORS)

        # Assert: 杰西卡有标准化标签 → provider, 白雪无标签 → pure
        provider_names = {op.name for op in result.providers}
        pure_names = {op.name for op in result.pure_efficiency}
        assert "杰西卡" in provider_names
        assert "白雪" in pure_names

    def test_产物分离_贵金属技能不出现于作战记录(self):
        """从真数据加载后，纯贵金属干员不应出现在 CR 候选池"""
        # Arrange: 加载真数据
        from steward_core.data_loader import load_operators_v2

        project_root = Path(__file__).resolve().parent.parent.parent
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
        # 游戏版本更新新增干员时上限会增长，仅保底下限
        assert len(cr_ops) >= 50
        assert len(pg_ops) >= 50

    def test_B层消费者_归为providers(self):
        """黍(raw eff=0,B1消费者) → 应归入 providers 而非被剪枝"""
        from steward_core.synergy import classify_mfg_operators

        # Arrange: 黍持有 Mfg 条件型 buff (eff=0)
        shu = _mk_op("黍", [_mk_mfg_skill("人间烟火·α", 0.0, "b1")])
        filler = _mk_op("白雪", [_mk_mfg_skill("高效生产", 30.0)])

        # Act
        result = classify_mfg_operators([shu, filler], "CombatRecord", _TEST_ANCHORS)

        # Assert: 黍 → providers（不被剪枝）
        provider_names = {op.name for op in result.providers}
        pure_names = {op.name for op in result.pure_efficiency}
        assert "黍" in provider_names
        assert "黍" not in pure_names

    def test_B层消费者_桑葚归为providers(self):
        """桑葚(raw eff=0,B1消费者) → providers"""
        from steward_core.synergy import classify_mfg_operators

        # Arrange
        sangshen = _mk_op("桑葚", [_mk_mfg_skill("人间烟火·α", 0.0, "b1")])
        filler = _mk_op("白雪", [_mk_mfg_skill("高效生产", 30.0)])

        # Act
        result = classify_mfg_operators([sangshen, filler], "CombatRecord", _TEST_ANCHORS)

        # Assert
        provider_names = {op.name for op in result.providers}
        assert "桑葚" in provider_names

    def test_B层消费者_乌有在Trade_不影响Mfg分类(self):
        """乌有是 Trade 消费者，在 Mfg 分类中不应出现"""
        from steward_core.synergy import classify_mfg_operators

        # Arrange: 乌有有 Trade skill，但在 Mfg 分类上下文中
        wuyou = _mk_op("乌有", [
            _mk_mfg_skill("人间烟火·α", 0.0, "b1", room_type="Trade"),
        ])
        filler = _mk_op("白雪", [_mk_mfg_skill("高效生产", 30.0)])

        # Act
        result = classify_mfg_operators([wuyou, filler], "CombatRecord", _TEST_ANCHORS)

        # Assert: 乌有不应出现在 Mfg providers 中（他是 Trade 专属）
        provider_names = {op.name for op in result.providers}
        assert "乌有" not in provider_names


class TestPruning:
    """剪枝规则的正确性验证 — Mfg 侧"""

    def test_等价类合并_纯效率只保留代表(self):
        """三个无联动干员 → 组合数从 C(3,3)=1 缩到 1（已经是1）"""
        # 构造更大池验证: 5个纯效率干员 → 仅需保留前3名最高效的组合
        from steward_core.synergy import prune_equivalent

        # Arrange: 5个纯效率干员
        ops = [
            _mk_op("A", [_mk_mfg_skill("s", 35.0, "a")]),
            _mk_op("B", [_mk_mfg_skill("s", 35.0, "b")]),
            _mk_op("C", [_mk_mfg_skill("s", 30.0, "c")]),
            _mk_op("D", [_mk_mfg_skill("s", 30.0, "d")]),
            _mk_op("E", [_mk_mfg_skill("s", 25.0, "e")]),
        ]

        # Act: 等价类合并后，纯效率仅保留 Top-3
        pure_pool = prune_equivalent(ops, "Mfg", top_k=3)

        # Assert: 只保留前3名
        assert len(pure_pool) == 3
        from steward_core.synergy import operator_estimated_efficiency
        efficiencies = [operator_estimated_efficiency(op, "Mfg") for op in pure_pool]
        assert 35.0 in efficiencies
        assert 25.0 not in efficiencies

    def test_锚点池筛选_保留锚点加配套(self):
        """水月+海沫+3个标准化提供者 vs 纯效率池 → 锚点池包含锚点和配套"""
        from steward_core.synergy import classify_mfg_operators, build_candidate_pool

        # Arrange
        shuiyue = _mk_op("水月", [_mk_mfg_skill("标准化·α", 25.0, "s1")])
        haimo = _mk_op("海沫", [_mk_mfg_skill("标准化·β", 25.0, "s2")])
        jessica = _mk_op("杰西卡", [_mk_mfg_skill("标准化·α", 25.0, "s3")])
        perfumer = _mk_op("调香师", [_mk_mfg_skill("标准化·β", 25.0, "s4")])
        # 纯效率干员: 白雪(30), 薄绿(25), 玛露西尔(30) — 这些不是锚点
        bai = _mk_op("白雪", [_mk_mfg_skill("标准化·α", 30.0, "s5")])
        bo = _mk_op("薄绿", [_mk_mfg_skill("标准化·β", 25.0, "s6")])
        all_ops = [shuiyue, haimo, jessica, perfumer, bai, bo]

        classification = classify_mfg_operators(all_ops, "CombatRecord", _TEST_ANCHORS)

        # Act
        pool = build_candidate_pool(all_ops, classification)

        # Assert: 池包含所有锚点+配套
        pool_names = {op.name for op in pool}
        assert "水月" in pool_names
        assert "海沫" in pool_names
        assert "杰西卡" in pool_names
        # 白雪作为高纯效率，也应保留
        assert "白雪" in pool_names


class TestRoomEvaluation:
    """单房间穷举评估（含联动）"""

    def test_纯效率评估_个体效率求和(self):
        """三干员无联动 → 产出 = Σ个体效率"""
        from steward_core.evaluate import evaluate_room

        # Arrange
        ops = [
            _mk_op("A", [_mk_mfg_skill("s", 30.0, "a")]),
            _mk_op("B", [_mk_mfg_skill("s", 25.0, "b")]),
            _mk_op("C", [_mk_mfg_skill("s", 20.0, "c")]),
        ]

        # Act
        score = evaluate_room(ops, "Mfg", "CombatRecord", power_count=3)

        # Assert: 30+25+20=75 → 积分 75×12=900
        assert pytest.approx(score) == 900.0

    def test_含联动评估_超出个体效率之和(self):
        """水月+2个标准化干员 → 联动加成 +10% → 产出 > 个体之和"""
        from steward_core.evaluate import evaluate_room

        # Arrange
        shuiyue = _mk_op("水月", [_mk_mfg_skill("标准化·α", 25.0, "s1")])
        # 两个标准化提供者(不含水月自身)
        jessica = _mk_op("杰西卡", [_mk_mfg_skill("标准化·α", 25.0, "s2")])
        perfumer = _mk_op("调香师", [_mk_mfg_skill("标准化·β", 25.0, "s3")])

        # Act: 含联动
        score_with = evaluate_room([shuiyue, jessica, perfumer], "Mfg", "CombatRecord", power_count=3)
        # Act: 不含联动（把水月换成普通25干员）
        filler = _mk_op("填位", [_mk_mfg_skill("标准化·α", 25.0, "s4")])
        score_without = evaluate_room([filler, jessica, perfumer], "Mfg", "CombatRecord", power_count=3)

        # Assert: 联动版 > 无联动版
        assert score_with > score_without

    def test_自动化房间_非自动化干员归零(self):
        """温蒂自动化 → 其他2人效率归零，仅计温蒂的发电站加成"""
        from steward_core.evaluate import evaluate_room

        # Arrange: 温蒂(自动化15%/站) + 2个高效干员
        wenti = _mk_op("温蒂")
        high_eff_a = _mk_op("地灵", [_mk_mfg_skill("高效生产", 35.0, "a")])
        high_eff_b = _mk_op("炎熔", [_mk_mfg_skill("高效生产", 35.0, "b")])

        # Act
        score = evaluate_room([wenti, high_eff_a, high_eff_b], "Mfg", "CombatRecord", power_count=3)

        # Assert: 温蒂个体效率为0(无制造技能)，地灵和炎熔归零
        # 仅自动化加成: 3×15×12 = 540
        assert score == pytest.approx(540.0, rel=0.01)

    def test_自动化房间_自动化干员自身不被归零(self):
        """森蚺+温蒂共存 → 自动化加成叠加，两者都不在 zero_set 中"""
        from steward_core.evaluate import evaluate_room

        # Arrange: 森蚺(5%/站) + 温蒂(15%/站) + 填位
        senia = _mk_op("森蚺")
        wenti = _mk_op("温蒂")
        filler = _mk_op("填位", [_mk_mfg_skill("高效生产", 30.0, "f")])

        # Act
        score = evaluate_room([senia, wenti, filler], "Mfg", "CombatRecord", power_count=3)

        # Assert: filler归零，自动化叠加=森蚺15(3×5)+温蒂45(3×15)=60
        # 积分 = 60×12 = 720
        assert score == pytest.approx(720.0, rel=0.01)
