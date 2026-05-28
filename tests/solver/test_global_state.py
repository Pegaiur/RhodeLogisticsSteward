"""全局状态包级稀缺度测试 (Step 3)

测试 GlobalState 的包可用性跟踪与稀缺度惩罚。
"""

import pytest


class TestGlobalStateBasics:
    """GlobalState 基础操作"""

    def test_初始构造_设置包可用性(self):
        """GlobalState 按给定的初始可用性构造"""
        from steward_core.solver.global_state import GlobalState

        state = GlobalState(bundle_availability={"迷迭香包": 1, "骑士包": 2})
        assert state.bundle_availability["迷迭香包"] == 1
        assert state.bundle_availability["骑士包"] == 2

    def test_default_initial_availability(self):
        """classmethod 提供默认的 243 布局初始可用性"""
        from steward_core.solver.global_state import GlobalState

        state = GlobalState.for_layout_243()
        assert state.bundle_availability["迷迭香包"] == 1
        assert state.bundle_availability["骑士包"] >= 1

    def test_空包列表_can_allocate返回True(self):
        """无包的 combo → 总可分配"""
        from steward_core.solver.global_state import GlobalState

        state = GlobalState.for_layout_243()
        assert state.can_allocate([]) is True

    def test_包有余量_can_allocate返回True(self):
        """包可用性 > 0 → 可分配"""
        from steward_core.solver.global_state import GlobalState

        state = GlobalState(bundle_availability={"迷迭香包": 1})
        assert state.can_allocate(["迷迭香包"]) is True

    def test_包已耗尽_can_allocate返回False(self):
        """包可用性 = 0 → 不可分配"""
        from steward_core.solver.global_state import GlobalState

        state = GlobalState(bundle_availability={"迷迭香包": 0})
        assert state.can_allocate(["迷迭香包"]) is False


class TestScarcityPenalty:
    """稀缺度惩罚计算"""

    def test_空包_无惩罚(self):
        """无包的 combo → 惩罚为 0"""
        from steward_core.solver.global_state import GlobalState

        state = GlobalState.for_layout_243()
        penalty = state.scarcity_penalty([], alpha=0.3)
        assert penalty == 0.0

    def test_最后一个_重罚(self):
        """包只剩 1 次 → 重型惩罚"""
        from steward_core.solver.global_state import GlobalState

        state = GlobalState(bundle_availability={"迷迭香包": 1})
        penalty = state.scarcity_penalty(["迷迭香包"], alpha=0.3)
        assert penalty > 0

    def test_数量充裕_轻罚或无罚(self):
        """包余量=4 → 无惩罚；余量=2 → 轻惩罚"""
        from steward_core.solver.global_state import GlobalState

        # 余量 4 → > 3 阈值，无罚
        state = GlobalState(bundle_availability={"骑士包": 4})
        penalty = state.scarcity_penalty(["骑士包"], alpha=0.3)
        assert penalty == 0.0

        # 余量 2 → ≤ 3 阈值，轻罚
        state2 = GlobalState(bundle_availability={"骑士包": 2})
        penalty2 = state2.scarcity_penalty(["骑士包"], alpha=0.3)
        assert penalty2 > 0

    def test_alpha为零_惩罚归零(self):
        """alpha=0 → 所有惩罚归零（关闭全局状态效果）"""
        from steward_core.solver.global_state import GlobalState

        state = GlobalState(bundle_availability={"迷迭香包": 1})
        penalty = state.scarcity_penalty(["迷迭香包"], alpha=0.0)
        assert penalty == 0.0

    def test_惩罚随alpha线性增长(self):
        """惩罚 ∝ alpha"""
        from steward_core.solver.global_state import GlobalState

        state = GlobalState(bundle_availability={"迷迭香包": 1})
        p_small = state.scarcity_penalty(["迷迭香包"], alpha=0.1)
        p_large = state.scarcity_penalty(["迷迭香包"], alpha=0.5)
        assert p_large > p_small


class TestAllocate:
    """消耗包余量"""

    def test_分配后余量减少(self):
        """allocate 后可用性 -1"""
        from steward_core.solver.global_state import GlobalState

        state = GlobalState(bundle_availability={"迷迭香包": 1, "骑士包": 2})
        state.allocate(["迷迭香包"])
        assert state.bundle_availability["迷迭香包"] == 0
        assert state.bundle_availability["骑士包"] == 2  # 不受影响

    def test_多包同时分配(self):
        """同时消耗多个包"""
        from steward_core.solver.global_state import GlobalState

        state = GlobalState(bundle_availability={"迷迭香包": 1, "骑士包": 2})
        state.allocate(["迷迭香包", "骑士包"])
        assert state.bundle_availability["迷迭香包"] == 0
        assert state.bundle_availability["骑士包"] == 1

    def test_未注册包_不报错(self):
        """allocate 未注册的包名不报错"""
        from steward_core.solver.global_state import GlobalState

        state = GlobalState(bundle_availability={})
        state.allocate(["不存在的包"])  # 不抛异常
