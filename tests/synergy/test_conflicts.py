"""效率机制冲突解析单元测试

覆盖 resolve_efficiency_conflicts 的核心场景。
"""

from steward_core.models import Operator


def _mk_op(name: str, skills: list["Skill"] | None = None) -> Operator:
    from steward_core.models import Skill
    return Operator(
        name=name, char_id=name.lower(),
        skills=skills if skills else [], rarity=5,
    )


def _trade_skill(buff_id: str) -> "Skill":
    from steward_core.models import Skill, EfficiencyMap
    return Skill(
        buff_id=buff_id, buff_name="", skill_icon="",
        room_type="Trade", efficient=EfficiencyMap(raw={}),
    )


class TestClosureDisablesWhisper:
    def test_closure_在场时_whisper_被禁用(self):
        from steward_core.synergy.conflicts import resolve_efficiency_conflicts

        closure = _mk_op("可露希尔", [_trade_skill("trade_ord_closure[000]")])
        whisper = _mk_op("巫恋", [_trade_skill("trade_ord_vodfox&cost[000]")])
        other = _mk_op("A", [])

        disabled = resolve_efficiency_conflicts(
            [closure, whisper, other], "Trade",
        )
        assert "whisper" in disabled

    def test_closure_不在场时_whisper_正常(self):
        from steward_core.synergy.conflicts import resolve_efficiency_conflicts

        whisper = _mk_op("巫恋", [_trade_skill("trade_ord_vodfox&cost[000]")])
        other = _mk_op("A", [_trade_skill("trade_ord_law[000]")])

        disabled = resolve_efficiency_conflicts(
            [whisper, other], "Trade",
        )
        assert "whisper" not in disabled

    def test_非_trade_房间_不受影响(self):
        from steward_core.synergy.conflicts import resolve_efficiency_conflicts

        closure = _mk_op("可露希尔", [_trade_skill("trade_ord_closure[000]")])
        whisper = _mk_op("巫恋", [_trade_skill("trade_ord_vodfox&cost[000]")])

        disabled = resolve_efficiency_conflicts(
            [closure, whisper], "Mfg",
        )
        assert disabled == frozenset()


class TestEdgeCases:
    def test_空操作员列表(self):
        from steward_core.synergy.conflicts import resolve_efficiency_conflicts

        disabled = resolve_efficiency_conflicts([], "Trade")
        assert disabled == frozenset()

    def test_仅有_whisper_无订单机制(self):
        from steward_core.synergy.conflicts import resolve_efficiency_conflicts

        whisper = _mk_op("巫恋", [_trade_skill("trade_ord_vodfox&cost[000]")])
        other = _mk_op("A", [])

        disabled = resolve_efficiency_conflicts(
            [whisper, other], "Trade",
        )
        assert "whisper" not in disabled

    def test_closure_前缀匹配含后缀的_buff_id(self):
        from steward_core.synergy.conflicts import resolve_efficiency_conflicts

        closure = _mk_op("可露希尔", [_trade_skill("trade_ord_closure&cost[000]")])
        whisper = _mk_op("巫恋", [_trade_skill("trade_ord_vodfox&cost[000]")])

        disabled = resolve_efficiency_conflicts(
            [closure, whisper], "Trade",
        )
        assert "whisper" in disabled
