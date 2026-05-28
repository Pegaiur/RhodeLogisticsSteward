"""trade_linkages 模块单元测试 — 贸易站联动 (鸿雪销路宣发 / 孑订单压缩)"""

import pytest

from steward_core.models import EfficiencyMap, LayoutConfig, LinearSegment, Operator, RoomConfig, Skill


def _mk_op(name: str = "测试", skills: list[Skill] | None = None,
           group_id: str | None = None, nation_id: str | None = None,
           team_id: str | None = None) -> Operator:
    return Operator(char_id=name, name=name, skills=skills or [],
                    group_id=group_id, nation_id=nation_id, team_id=team_id)


def _mk_skill(buff_id: str, room_type: str, buff_name: str = "测试技能",
              efficient: dict[str, float] | None = None,
              capacity: int = 0) -> Skill:
    return Skill(
        buff_id=buff_id,
        buff_name=buff_name,
        skill_icon=buff_id,
        room_type=room_type,
        efficient=EfficiencyMap(raw=efficient or {"all": 0.0}),
        capacity_bonus=capacity,
    )


# ─── 鸿雪销路宣发 + 际崖居民 ─────────────────────────────────────

class TestGoldLineSynergy:
    """鸿雪双技能: synergy_trade_gold_lines — 销路宣发+际崖居民"""

    def test_销路宣发_2赤金线_加10percent(self):
        """鸿雪在 Trade，无杜林族 → 基础 2 赤金线 × 5% = 10%"""
        from steward_core.synergy import synergy_trade_gold_lines
        from steward_core.models import LayoutConfig, RoomConfig

        hongxue = _mk_op("鸿雪")
        layout = LayoutConfig(rooms=[
            RoomConfig("Mfg", 0, 3, "PureGold"),
            RoomConfig("Mfg", 1, 3, "PureGold"),
        ])

        segs = synergy_trade_gold_lines([hongxue], "Trade", "Money", layout, T=12.0)
        assert len(segs) == 1
        assert segs[0].a == 10.0

    def test_销路宣发_无鸿雪_返回空(self):
        """房间无鸿雪 → 空"""
        from steward_core.synergy import synergy_trade_gold_lines
        from steward_core.models import LayoutConfig

        op = _mk_op("其他")
        segs = synergy_trade_gold_lines([op], "Trade", "Money", LayoutConfig(rooms=[]), 12.0)
        assert segs == []

    def test_销路宣发_非Trade_返回空(self):
        """鸿雪在 Mfg → 不触发"""
        from steward_core.synergy import synergy_trade_gold_lines
        from steward_core.models import LayoutConfig

        hongxue = _mk_op("鸿雪")
        segs = synergy_trade_gold_lines([hongxue], "Mfg", "PureGold", LayoutConfig(rooms=[]), 12.0)
        assert segs == []

    def test_际崖居民_2杜林族_加2赤金线(self):
        """2 杜林族 + 2 基础赤金线 = 4 赤金线 × 5% = 20%"""
        from steward_core.synergy import synergy_trade_gold_lines
        from steward_core.models import LayoutConfig, RoomConfig

        hongxue = _mk_op("鸿雪")
        layout = LayoutConfig(rooms=[
            RoomConfig("Mfg", 0, 3, "PureGold"),
            RoomConfig("Mfg", 1, 3, "PureGold"),
        ])
        durin_names = {"桃金娘", "褐果"}

        segs = synergy_trade_gold_lines([hongxue], "Trade", "Money", layout, durin_names, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 20.0  # (2基础+2杜林) × 5%

    def test_际崖居民_超过4杜林_上限4(self):
        """5 杜林族 → 上限 4 赤金线额外 → 总 6 线 × 5% = 30%"""
        from steward_core.synergy import synergy_trade_gold_lines
        from steward_core.models import LayoutConfig, RoomConfig

        hongxue = _mk_op("鸿雪")
        layout = LayoutConfig(rooms=[
            RoomConfig("Mfg", 0, 3, "PureGold"),
            RoomConfig("Mfg", 1, 3, "PureGold"),
        ])
        durin_names = {"杜林", "桃金娘", "褐果", "至简", "多萝西"}

        segs = synergy_trade_gold_lines([hongxue], "Trade", "Money", layout, durin_names, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 30.0  # (2基础+min(5,4)) × 5%


# ─── A7 孑订单压缩机制 ───────────────────────────────────────────

class TestJieOrderMechanics:
    """A7: synergy_jie_order — 孑市井之道/摊贩经济"""

    def _mk_jie_e2(self) -> Operator:
        """构造精2孑（含两个互斥技能）"""
        jie = _mk_op("孑")
        jie.skills.append(_mk_skill("trade_ord_limit_count[000]", "Trade", "市井之道"))
        jie.skills.append(_mk_skill("trade_ord_limit_diff[000]", "Trade", "摊贩经济"))
        return jie

    def _mk_jie_e1(self) -> Operator:
        """构造精1孑（仅市井之道）"""
        jie = _mk_op("孑")
        jie.skills.append(_mk_skill("trade_ord_limit_count[000]", "Trade", "市井之道"))
        return jie

    def test_精2孑_两队友各30percent_效率约为4x4percent(self):
        """精2孑 + 2名30%队友 → 上限=10-6=4 → 孑效率≈16%"""
        from steward_core.synergy import synergy_jie_order

        jie = self._mk_jie_e2()
        a = _mk_op("队友A")
        a.skills.append(_mk_skill("t30", "Trade", "", {"all": 30.0}))
        b = _mk_op("队友B")
        b.skills.append(_mk_skill("t30", "Trade", "", {"all": 30.0}))

        segs = synergy_jie_order([jie, a, b], "Trade", [], 12.0)
        assert len(segs) == 1
        # 上限=10-6=4, 精2恒定: 4×4%=16%
        assert segs[0].a == 16.0
        assert segs[0].b == 0.0

    def test_精2孑_无队友_上限10_效率40(self):
        """精2孑独自 → 上限=10 → 10×4%=40%"""
        from steward_core.synergy import synergy_jie_order

        jie = self._mk_jie_e2()
        segs = synergy_jie_order([jie], "Trade", [], 12.0)
        assert len(segs) == 1
        assert segs[0].a == 40.0

    def test_精1孑_返回ramp段(self):
        """精1孑 → 仅市井之道，ramp从0爬升到上限×4%"""
        from steward_core.synergy import synergy_jie_order

        jie = self._mk_jie_e1()
        a = _mk_op("队友A")
        a.skills.append(_mk_skill("t30", "Trade", "", {"all": 30.0}))
        b = _mk_op("队友B")
        b.skills.append(_mk_skill("t30", "Trade", "", {"all": 30.0}))

        segs = synergy_jie_order([jie, a, b], "Trade", [], 12.0)
        assert len(segs) >= 2  # ramp段 + 恒定段
        assert segs[0].b > 0   # 第一个段是爬升

    def test_精1孑_无ordered技能_不触发(self):
        """孑无市井之道技能 → 返回空"""
        from steward_core.synergy import synergy_jie_order

        jie = _mk_op("孑")  # 无技能
        segs = synergy_jie_order([jie], "Trade", [], 12.0)
        assert segs == []

    def test_灵知加成_上限额外加6(self):
        """灵知在中枢 + 1名谢拉格在Trade → 上限+6 → 10-6+6=10 → 40%"""
        from steward_core.synergy import synergy_jie_order

        jie = self._mk_jie_e2()
        a = _mk_op("崖心", group_id="karlan")
        a.skills.append(_mk_skill("t30", "Trade", "", {"all": 30.0}))
        b = _mk_op("队友B")
        b.skills.append(_mk_skill("t30", "Trade", "", {"all": 30.0}))

        lingzhi = _mk_op("灵知")
        segs = synergy_jie_order([jie, a, b], "Trade", [lingzhi], 12.0)
        # 上限=10-6+6=10, 精2: 10×4%=40%
        assert segs[0].a == 40.0

    def test_孑不在房间_返回空(self):
        """无孑在 Trade → 空"""
        from steward_core.synergy import synergy_jie_order

        a = _mk_op("队友A")
        segs = synergy_jie_order([a], "Trade", [], 12.0)
        assert segs == []

    def test_孑非Trade房间_不触发(self):
        """孑在 Mfg → 空"""
        from steward_core.synergy import synergy_jie_order

        jie = self._mk_jie_e2()
        segs = synergy_jie_order([jie], "Mfg", [], 12.0)
        assert segs == []

    def test_订单上限最低为1(self):
        """上限压缩后不低于1（含灵知后仍≥1的截断）"""
        from steward_core.synergy import synergy_jie_order

        jie = self._mk_jie_e2()
        # 4名30%队友 → 120% → 上限=10-12=-2 → clamp=1
        ops = [jie]
        for i in range(4):
            o = _mk_op(f"队友{i}")
            o.skills.append(_mk_skill("t30", "Trade", "", {"all": 30.0}))
            ops.append(o)

        segs = synergy_jie_order(ops, "Trade", [], 12.0)
        assert segs[0].a == 4.0  # 1×4%
