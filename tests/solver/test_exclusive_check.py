"""独占冲突检查测试 (Step 1b)

测试 _greedy_allocate_with_support 在 SolverConfig.exclusive_support_check
开关下的冲突判定行为。
"""

import pytest

from steward_core.solver.config import SolverConfig


def _make_entry(score, members, trade_support=None, office_support=None,
                control_support=None, dorm_support=None):
    """构造 evaluated 列表中的一条记录"""
    support_map = {}
    all_names = []
    if trade_support:
        support_map["Trade"] = trade_support
        all_names.extend(trade_support)
    if office_support:
        support_map["Office"] = office_support
        all_names.extend(office_support)
    if control_support:
        support_map["Control"] = control_support
        all_names.extend(control_support)
    if dorm_support:
        support_map["Dormitory"] = dorm_support
        all_names.extend(dorm_support)
    return (score, members, all_names, support_map)


class TestExclusiveSupportCheckOff:
    """开关关闭 = 旧行为（扁平冲突检查）"""

    def test_骑士支撑共享_旧逻辑下冲突(self):
        """两个骑士 combo 共享薇薇安娜+焰尾 → 扁平冲突，只能取一个"""
        from steward_core.solver.greed import _greedy_allocate_with_support

        evaluated = [
            _make_entry(500, ["耀骑士临光", "A", "B"],
                        control_support=["薇薇安娜", "焰尾"]),
            _make_entry(400, ["砾", "C", "D"],
                        control_support=["薇薇安娜", "焰尾"]),
        ]

        result = _greedy_allocate_with_support(evaluated, room_count=2, config=None)
        assert len(result) == 1
        assert result[0][0] == ["耀骑士临光", "A", "B"]

    def test_宿舍支撑共享_旧逻辑下冲突(self):
        """两个 combo 共享塑心(宿舍) → 扁平冲突，只能取一个"""
        from steward_core.solver.greed import _greedy_allocate_with_support

        evaluated = [
            _make_entry(500, ["迷迭香", "A", "B"],
                        dorm_support=["塑心", "爱丽丝"]),
            _make_entry(400, ["C", "D", "E"],
                        dorm_support=["塑心"]),
        ]

        result = _greedy_allocate_with_support(evaluated, room_count=2, config=None)
        assert len(result) == 1


class TestExclusiveSupportCheckOn:
    """开关开启 = 新行为（仅独占支撑冲突检查）"""

    def test_骑士支撑共享_新逻辑不冲突(self):
        """两个骑士 combo 共享薇薇安娜+焰尾(中枢,共享) → 独占检查不冲突"""
        from steward_core.solver.greed import _greedy_allocate_with_support

        config = SolverConfig(exclusive_support_check=True)
        evaluated = [
            _make_entry(500, ["耀骑士临光", "A", "B"],
                        control_support=["薇薇安娜", "焰尾"]),
            _make_entry(400, ["砾", "C", "D"],
                        control_support=["薇薇安娜", "焰尾"]),
        ]

        result = _greedy_allocate_with_support(
            evaluated, room_count=2, config=config,
        )
        assert len(result) == 2  # 两间都能取

    def test_宿舍支撑共享_新逻辑不冲突(self):
        """两个 combo 共享塑心(宿舍,共享) → 独占检查不冲突"""
        from steward_core.solver.greed import _greedy_allocate_with_support

        config = SolverConfig(exclusive_support_check=True)
        evaluated = [
            _make_entry(500, ["迷迭香", "A", "B"],
                        dorm_support=["塑心", "爱丽丝"]),
            _make_entry(400, ["C", "D", "E"],
                        dorm_support=["塑心"]),
        ]

        result = _greedy_allocate_with_support(
            evaluated, room_count=2, config=config,
        )
        assert len(result) == 2

    def test_Trade独占支撑_仍然冲突(self):
        """两个 combo 都需要黑键(Trade,独占) → 独占检查依然冲突"""
        from steward_core.solver.greed import _greedy_allocate_with_support

        config = SolverConfig(exclusive_support_check=True)
        evaluated = [
            _make_entry(500, ["迷迭香", "A", "B"],
                        trade_support=["黑键"]),
            _make_entry(400, ["C", "D", "E"],
                        trade_support=["黑键"]),
        ]

        result = _greedy_allocate_with_support(
            evaluated, room_count=2, config=config,
        )
        assert len(result) == 1  # 黑键独占，仍冲突

    def test_Office独占支撑_仍然冲突(self):
        """两个 combo 都需要絮雨(Office,独占) → 独占检查依然冲突"""
        from steward_core.solver.greed import _greedy_allocate_with_support

        config = SolverConfig(exclusive_support_check=True)
        evaluated = [
            _make_entry(500, ["迷迭香", "A", "B"],
                        office_support=["絮雨"]),
            _make_entry(400, ["C", "D", "E"],
                        office_support=["絮雨"]),
        ]

        result = _greedy_allocate_with_support(
            evaluated, room_count=2, config=config,
        )
        assert len(result) == 1  # 絮雨独占，仍冲突


class TestControlCapacity:
    """中枢容量不再在贪心阶段限制，由 fill_control 阶段统一择优"""

    def test_旧逻辑_容量不再限制(self):
        """Control 不再因容量跳过：combo2 不含冲突支撑，正常接受"""
        from steward_core.solver.greed import _greedy_allocate_with_support

        evaluated = [
            _make_entry(500, ["A", "B", "C"],
                        control_support=["C1", "C2", "C3"]),
            _make_entry(400, ["D", "E", "F"],
                        control_support=["C4", "C5", "C6"]),
            _make_entry(300, ["G", "H", "I"],
                        control_support=["C4"]),
        ]

        result = _greedy_allocate_with_support(evaluated, room_count=2, config=None)
        assert len(result) == 2
        assert result[0][0] == ["A", "B", "C"]
        assert result[1][0] == ["D", "E", "F"]  # 不再因容量跳过

    def test_新逻辑_容量不再限制(self):
        """独占检查模式下 Control 容量也不再限制"""
        from steward_core.solver.greed import _greedy_allocate_with_support

        config = SolverConfig(exclusive_support_check=True)
        evaluated = [
            _make_entry(500, ["A", "B", "C"],
                        control_support=["C1", "C2", "C3"]),
            _make_entry(400, ["D", "E", "F"],
                        control_support=["C4", "C5", "C6"]),
            _make_entry(300, ["G", "H", "I"],
                        control_support=["C4"]),
        ]

        result = _greedy_allocate_with_support(
            evaluated, room_count=2, config=config,
        )
        assert len(result) == 2
        assert result[0][0] == ["A", "B", "C"]
        assert result[1][0] == ["D", "E", "F"]


class TestConfigDefault:
    """不传 config = 旧行为"""

    def test_不传config_按旧逻辑冲突(self):
        """config=None → 默认 SolverConfig() → 扁平冲突"""
        from steward_core.solver.greed import _greedy_allocate_with_support

        evaluated = [
            _make_entry(500, ["耀骑士临光", "A", "B"],
                        control_support=["薇薇安娜", "焰尾"]),
            _make_entry(400, ["砾", "C", "D"],
                        control_support=["薇薇安娜", "焰尾"]),
        ]

        # 不传 config
        result = _greedy_allocate_with_support(evaluated, room_count=2)
        assert len(result) == 1
