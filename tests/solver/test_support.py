"""support 模块单元测试 — compute_trade_support"""

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


class TestComputeTradeSupport:
    """compute_trade_support — Trade combo 的跨房支撑干员锁定"""

    def test_孑触发_锁定灵知到中枢(self):
        """Trade combo 含孑 → Control 锁灵知"""
        from steward_core.solver.support import compute_trade_support

        jie = _mk_op("孑")
        support = compute_trade_support([jie])

        assert "灵知" in support["Control"]

    def test_叙拉古触发_锁定八幡海铃到中枢(self):
        """Trade combo 含叙拉古干员 → Control 锁八幡海铃"""
        from steward_core.solver.support import compute_trade_support

        bellone = _mk_op("贝洛内", nation_id="siracusa")
        support = compute_trade_support([bellone])

        assert "八幡海铃" in support["Control"]

    def test_叙拉古伺夜触发_锁八幡海铃(self):
        """Trade combo 含伺夜(叙拉古) → Control 锁八幡海铃"""
        from steward_core.solver.support import compute_trade_support

        siye = _mk_op("伺夜", nation_id="siracusa")
        support = compute_trade_support([siye])

        assert "八幡海铃" in support["Control"]

    def test_孑加叙拉古_同时锁灵知和八幡海铃(self):
        """Trade combo 含孑+叙拉古干员 → Control 锁灵知+八幡海铃"""
        from steward_core.solver.support import compute_trade_support

        jie = _mk_op("孑")
        bellone = _mk_op("贝洛内", nation_id="siracusa")
        support = compute_trade_support([jie, bellone])

        assert "灵知" in support["Control"]
        assert "八幡海铃" in support["Control"]

    def test_无触发条件_返回空(self):
        """Trade combo 无孑也无叙拉古 → 所有支撑集为空"""
        from steward_core.solver.support import compute_trade_support

        generic = _mk_op("普通干员", nation_id="lungmen")
        support = compute_trade_support([generic])

        assert support["Control"] == []
        assert support["Trade"] == []
        assert support["Dormitory"] == []

    def test_空combo_返回空(self):
        """空 combo → 所有支撑集为空"""
        from steward_core.solver.support import compute_trade_support

        support = compute_trade_support([])

        assert support["Control"] == []
        assert support["Trade"] == []
        assert support["Dormitory"] == []
