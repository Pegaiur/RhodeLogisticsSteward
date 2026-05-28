"""支撑包数据结构测试 (SupportBundle + BUNDLES 注册表)"""

import pytest

from steward_core.models import EfficiencyMap, Operator, Skill


def _mk_op(name: str = "测试", skills: list[Skill] | None = None,
           group_id: str | None = None, nation_id: str | None = None,
           team_id: str | None = None) -> Operator:
    return Operator(char_id=name, name=name, skills=skills or [],
                    group_id=group_id, nation_id=nation_id, team_id=team_id)


def _mk_skill(buff_id: str, room_type: str, buff_name: str = "测试技能",
              efficient: dict[str, float] | None = None) -> Skill:
    return Skill(
        buff_id=buff_id, buff_name=buff_name, skill_icon=buff_id,
        room_type=room_type,
        efficient=EfficiencyMap(raw=efficient or {"all": 0.0}),
    )


class TestSupportBundleStructure:
    """SupportBundle 数据结构"""

    def test_迷迭香包_独占支撑为Trade和Office(self):
        """迷迭香包独占资源：黑键(1个Trade工位) + 絮雨(1个Office工位)"""
        from steward_core.solver.bundle import BUNDLES

        bundle = BUNDLES["迷迭香包"]
        assert bundle.name == "迷迭香包"

        assert "Trade" in bundle.exclusive
        assert "黑键" in bundle.exclusive["Trade"]

        assert "Office" in bundle.exclusive
        assert "絮雨" in bundle.exclusive["Office"]

    def test_迷迭香包_共享支撑为Control和Dormitory(self):
        """迷迭香包共享资源：中枢(令/夕) + 宿舍(爱丽丝/车尔尼/森西/塑心)"""
        from steward_core.solver.bundle import BUNDLES

        bundle = BUNDLES["迷迭香包"]

        assert "Control" in bundle.shared
        assert "令" in bundle.shared["Control"]
        assert "夕" in bundle.shared["Control"]

        assert "Dormitory" in bundle.shared
        assert "爱丽丝" in bundle.shared["Dormitory"]
        assert "车尔尼" in bundle.shared["Dormitory"]
        assert "森西" in bundle.shared["Dormitory"]
        assert "塑心" in bundle.shared["Dormitory"]

    def test_骑士包_无独占支撑(self):
        """骑士包所有支撑都是共享的（中枢，服务于所有设施）"""
        from steward_core.solver.bundle import BUNDLES

        bundle = BUNDLES["骑士包"]
        assert bundle.name == "骑士包"
        assert bundle.exclusive == {}

    def test_骑士包_共享支撑为Control(self):
        """骑士包共享：薇薇安娜 + 焰尾 → 中枢"""
        from steward_core.solver.bundle import BUNDLES

        bundle = BUNDLES["骑士包"]
        assert "Control" in bundle.shared
        assert "薇薇安娜" in bundle.shared["Control"]
        assert "焰尾" in bundle.shared["Control"]


class TestBundleActivation:
    """compute_optimal_support 返回 SupportResult（含 bundles 列表）"""

    def test_迷迭香combo_激活迷迭香包(self):
        """迷迭香在 Mfg combo → SupportResult.bundles 含 '迷迭香包'"""
        from steward_core.solver.support import compute_optimal_support

        op = _mk_op("迷迭香")
        result = compute_optimal_support([op])

        assert "迷迭香包" in result.bundles

    def test_骑士combo_激活骑士包(self):
        """骑士(Mfg锚点)在 combo → SupportResult.bundles 含 '骑士包'"""
        from steward_core.solver.support import compute_optimal_support

        knight = _mk_op("耀骑士临光")
        result = compute_optimal_support([knight])

        assert "骑士包" in result.bundles

    def test_迷迭香加骑士combo_激活两个包(self):
        """迷迭香+骑士同房 → 两个包都激活"""
        from steward_core.solver.support import compute_optimal_support

        rosmontis = _mk_op("迷迭香")
        knight = _mk_op("耀骑士临光")
        result = compute_optimal_support([rosmontis, knight])

        assert "迷迭香包" in result.bundles
        assert "骑士包" in result.bundles

    def test_纯效率combo_无包激活(self):
        """无锚点的纯效率 combo → SupportResult.bundles 为空"""
        from steward_core.solver.support import compute_optimal_support

        op = _mk_op("白雪")
        result = compute_optimal_support([op])

        assert result.bundles == []

    def test_空combo_无包激活(self):
        """空 combo → bundles 为空"""
        from steward_core.solver.support import compute_optimal_support

        result = compute_optimal_support([])

        assert result.bundles == []


class TestBackwardCompatibility:
    """向后兼容：旧代码用 .support_map 解包"""

    def test_SupportResult可解包为dict(self):
        """SupportResult.support_map 返回原始 dict，与旧接口一致"""
        from steward_core.solver.support import compute_optimal_support

        op = _mk_op("迷迭香")
        result = compute_optimal_support([op])

        support_map = result.support_map
        assert isinstance(support_map, dict)
        assert "Control" in support_map
        assert "黑键" in support_map["Trade"]

    def test_旧调用方_best_efficiency仍可用(self):
        """_evaluate_with_support 应适配 SupportResult（内部解包 support_map）"""
        from steward_core.solver.support import _evaluate_with_support

        rosmontis = _mk_op("迷迭香")
        filler_a = _mk_op("填位A", [_mk_skill("s", "Mfg")])
        filler_b = _mk_op("填位B", [_mk_skill("s", "Mfg")])

        score, available = _evaluate_with_support(
            [rosmontis, filler_a, filler_b], "Mfg", "CombatRecord",
            [rosmontis, filler_a, filler_b], set(),
        )

        assert isinstance(score, float)
        assert score > 0
        assert isinstance(available, dict)
