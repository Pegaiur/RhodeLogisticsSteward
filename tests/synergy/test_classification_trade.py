"""贸易站干员分类测试 (synergy/classification.py)

测试 classify_trade_operators 锚点/提供者/纯效率分类逻辑。
"""

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


_TRADE_TEST_ANCHORS = {"巫恋", "火哨", "吉星", "雪雉"}


class TestClassifyTradeOperators:
    """分类 Trade 干员: 订单机制锚点 / 反馈型锚点 / 提供者 / 纯效率"""

    def test_订单机制型_但书归为锚点(self):
        from steward_core.synergy import classify_trade_operators
        but = _mk_op("但书", [_mk_mfg_skill("合同法", 0.0, "trade_ord_law[000]", "Trade")])
        filler = _mk_op("白雪", [_mk_mfg_skill("高效生产", 30.0, "generic", "Trade")])
        result = classify_trade_operators([but, filler], _TRADE_TEST_ANCHORS)
        assert "但书" in {op.name for op in result.anchors}

    def test_订单机制型_龙舌兰归为锚点(self):
        from steward_core.synergy import classify_trade_operators
        tequila = _mk_op("龙舌兰", [_mk_mfg_skill("投资·β", 0.0, "trade_ord_long[010]", "Trade")])
        result = classify_trade_operators([tequila], _TRADE_TEST_ANCHORS)
        assert "龙舌兰" in {op.name for op in result.anchors}

    def test_反馈型锚点_巫恋归为锚点(self):
        from steward_core.synergy import classify_trade_operators
        shamare = _mk_op("巫恋", [_mk_mfg_skill("低语", 0.0, "trade_ord_vodfox[000]", "Trade")])
        result = classify_trade_operators([shamare], _TRADE_TEST_ANCHORS)
        assert "巫恋" in {op.name for op in result.anchors}

    def test_B层消费者_乌有归为提供者(self):
        from steward_core.synergy import classify_trade_operators
        wuyou = _mk_op("乌有", [_mk_mfg_skill("人间烟火", 0.0, "b1", "Trade")])
        result = classify_trade_operators([wuyou], _TRADE_TEST_ANCHORS)
        assert "乌有" in {op.name for op in result.providers}

    def test_纯效率_归为纯效率(self):
        from steward_core.synergy import classify_trade_operators
        normal = _mk_op("白雪", [_mk_mfg_skill("高效生产", 30.0, "generic", "Trade")])
        result = classify_trade_operators([normal], _TRADE_TEST_ANCHORS)
        assert "白雪" in {op.name for op in result.pure_efficiency}
        assert len(result.anchors) == 0
