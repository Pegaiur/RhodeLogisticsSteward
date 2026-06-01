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

    def test_贝洛内加伺夜同房_订单上限加2(self):
        """贝洛内+伺夜同房（未偿还的债务）→ 订单上限+2"""
        from steward_core.synergy import synergy_jie_order

        jie = self._mk_jie_e2()
        bellone = _mk_op("贝洛内")
        bellone.skills.append(_mk_skill("trade_ord_limit&cost_P[020]", "Trade", "未偿还的债务"))
        siye = _mk_op("伺夜")

        # 无其他队友 → 上限=10+2(贝洛内)→ ceiling=12×4%=48%
        segs = synergy_jie_order([jie, bellone, siye], "Trade", [], 12.0)
        assert segs[0].a == 48.0

    def test_贝洛内无伺夜_不加成(self):
        """贝洛内独自 + 孑 → 无伺夜，订单上限不加"""
        from steward_core.synergy import synergy_jie_order

        jie = self._mk_jie_e2()
        bellone = _mk_op("贝洛内")
        bellone.skills.append(_mk_skill("trade_ord_limit&cost_P[020]", "Trade", "未偿还的债务"))
        generic = _mk_op("其他干员")

        # 无伺夜 → 上限=10 → 40%
        segs = synergy_jie_order([jie, bellone, generic], "Trade", [], 12.0)
        assert segs[0].a == 40.0


# ─── OrderLimitContext 上下文 ────────────────────────────────────

class TestOrderLimitContext:
    """OrderLimitContext 数据类基础功能"""

    def test_创建上下文_初始总数为10(self):
        """新建上下文 → base=10, total=10"""
        from steward_core.synergy.trade_linkages import OrderLimitContext

        ctx = OrderLimitContext()
        assert ctx.base == 10
        assert ctx.total == 10
        assert ctx.contributions == {}

    def test_add增量为正_总数增加(self):
        """add 正增量 → contributions 登记 + total 增加"""
        from steward_core.synergy.trade_linkages import OrderLimitContext

        ctx = OrderLimitContext()
        ctx.add("谈判", 5)
        assert ctx.total == 15
        assert ctx.contributions == {"谈判": 5}

    def test_add增量为负_总数减少(self):
        """add 负增量（孑压缩场景）→ total 减少"""
        from steward_core.synergy.trade_linkages import OrderLimitContext

        ctx = OrderLimitContext()
        ctx.add("孑·订单压缩", -6)
        assert ctx.total == 4
        assert ctx.contributions == {"孑·订单压缩": -6}

    def test_add增量为零_不登记(self):
        """add 零增量 → contributions 不新增条目"""
        from steward_core.synergy.trade_linkages import OrderLimitContext

        ctx = OrderLimitContext()
        ctx.add("无变化", 0)
        assert "无变化" not in ctx.contributions

    def test_多次add同源_累加(self):
        """多次 add 同一 source → 值累加"""
        from steward_core.synergy.trade_linkages import OrderLimitContext

        ctx = OrderLimitContext()
        ctx.add("谈判", 5)
        ctx.add("谈判", 5)
        assert ctx.total == 20
        assert ctx.contributions == {"谈判": 10}


# ─── compute_trade_order_limit 单元测试 ──────────────────────────

class TestComputeTradeOrderLimit:
    """compute_trade_order_limit — 综合订单上限计算"""

    def _mk_trade_layout(self, level: int = 3) -> LayoutConfig:
        return LayoutConfig(rooms=[
            RoomConfig("Trade", 0, 3, "Money", level=level),
            RoomConfig("Trade", 1, 3, "Money", level=level),
        ])

    def test_无特殊干员_仅基础10(self):
        """无任何订单上限相关技能 → total=10"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        op = _mk_op("普通干员")
        ctx = compute_trade_order_limit([op], self._mk_trade_layout(), [])
        assert ctx.total == 10

    def test_桃金娘谈判_加5(self):
        """桃金娘持有 trade_ord_limit&cost[000] → +5"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        myrtle = _mk_op("桃金娘")
        myrtle.skills.append(_mk_skill("trade_ord_limit&cost[000]", "Trade", "谈判"))
        ctx = compute_trade_order_limit([myrtle], self._mk_trade_layout(), [])
        assert ctx.total == 15
        assert ctx.contributions.get("谈判") == 5

    def test_拉普兰德醉翁之意alpha_有德克萨斯_加2(self):
        """拉普兰德 + 德克萨斯同房 → 醉翁之意·α +2"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        lappland = _mk_op("拉普兰德")
        lappland.skills.append(_mk_skill("trade_ord_limit&cost_P[000]", "Trade", "醉翁之意·α"))
        texas = _mk_op("德克萨斯")
        ctx = compute_trade_order_limit(
            [lappland, texas], self._mk_trade_layout(), [],
        )
        assert ctx.total == 12
        assert ctx.contributions.get("醉翁之意·α") == 2

    def test_拉普兰德醉翁之意alpha_无德克萨斯_不加(self):
        """拉普兰德独自 → 醉翁之意不触发"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        lappland = _mk_op("拉普兰德")
        lappland.skills.append(_mk_skill("trade_ord_limit&cost_P[000]", "Trade", "醉翁之意·α"))
        generic = _mk_op("其他")
        ctx = compute_trade_order_limit(
            [lappland, generic], self._mk_trade_layout(), [],
        )
        assert ctx.total == 10
        assert "醉翁之意·α" not in ctx.contributions

    def test_拉普兰德醉翁之意beta_有德克萨斯_加4(self):
        """拉普兰德精2 + 德克萨斯 → 醉翁之意·β +4"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        lappland = _mk_op("拉普兰德")
        lappland.skills.append(_mk_skill("trade_ord_limit&cost_P[001]", "Trade", "醉翁之意·β"))
        texas = _mk_op("德克萨斯")
        ctx = compute_trade_order_limit(
            [lappland, texas], self._mk_trade_layout(), [],
        )
        assert ctx.total == 14
        assert ctx.contributions.get("醉翁之意·β") == 4

    def test_瑰盐多面逢源_贸易站3级_加3(self):
        """瑰盐 多面逢源 × 贸易站等级3 → +3"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        rosesa = _mk_op("瑰盐")
        rosesa.skills.append(_mk_skill("trade_ord_limit&trade&lv[000]", "Trade", "多面逢源"))
        ctx = compute_trade_order_limit([rosesa], self._mk_trade_layout(level=3), [])
        assert ctx.total == 13
        assert ctx.contributions.get("多面逢源") == 3

    def test_贝洛内加伺夜_加2(self):
        """贝洛内 + 伺夜同房 → +2"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        bellone = _mk_op("贝洛内")
        siye = _mk_op("伺夜")
        ctx = compute_trade_order_limit(
            [bellone, siye], self._mk_trade_layout(), [],
        )
        assert ctx.total == 12
        assert ctx.contributions.get("贝洛内+伺夜") == 2

    def test_灵知中枢_1喀兰贸易_加6(self):
        """灵知在中枢 + 1名谢拉格在Trade → +6"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        cliffheart = _mk_op("崖心", group_id="karlan")
        gnosis = _mk_op("灵知")
        ctx = compute_trade_order_limit(
            [cliffheart], self._mk_trade_layout(), [gnosis],
        )
        assert ctx.total == 16
        assert ctx.contributions.get("灵知·喀兰贸易") == 6

    def test_孑压缩_2个30percent队友_压缩为4(self):
        """孑 + 2名30%队友 → other_eff=60 → 上限=10-6=4"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        jie = _mk_op("孑")
        jie.skills.append(_mk_skill("trade_ord_limit_count[000]", "Trade", "市井之道"))
        jie.skills.append(_mk_skill("trade_ord_limit_diff[000]", "Trade", "摊贩经济"))
        a = _mk_op("队友A")
        a.skills.append(_mk_skill("t30", "Trade", "", {"Money": 30.0}))
        b = _mk_op("队友B")
        b.skills.append(_mk_skill("t30", "Trade", "", {"Money": 30.0}))

        ctx = compute_trade_order_limit([jie, a, b], self._mk_trade_layout(), [])
        assert ctx.total == 4
        assert ctx.contributions.get("孑·订单压缩") == -6

    def test_孑压缩_最低为1(self):
        """孑 + 4名30%队友 → other_eff=120 → 上限 clamp 到 1"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        jie = _mk_op("孑")
        jie.skills.append(_mk_skill("trade_ord_limit_count[000]", "Trade", "市井之道"))
        jie.skills.append(_mk_skill("trade_ord_limit_diff[000]", "Trade", "摊贩经济"))
        ops = [jie]
        for i in range(4):
            o = _mk_op(f"队友{i}")
            o.skills.append(_mk_skill("t30", "Trade", "", {"Money": 30.0}))
            ops.append(o)

        ctx = compute_trade_order_limit(ops, self._mk_trade_layout(), [])
        assert ctx.total == 1
        assert ctx.contributions.get("孑·订单压缩") == -9

    def test_复合场景_谈判加孑压缩(self):
        """桃金娘(+5) + 孑压缩(-6) → total=9"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        myrtle = _mk_op("桃金娘")
        myrtle.skills.append(_mk_skill("trade_ord_limit&cost[000]", "Trade", "谈判"))
        jie = _mk_op("孑")
        jie.skills.append(_mk_skill("trade_ord_limit_count[000]", "Trade", "市井之道"))
        jie.skills.append(_mk_skill("trade_ord_limit_diff[000]", "Trade", "摊贩经济"))
        a = _mk_op("队友A")
        a.skills.append(_mk_skill("t30", "Trade", "", {"Money": 30.0}))
        b = _mk_op("队友B")
        b.skills.append(_mk_skill("t30", "Trade", "", {"Money": 30.0}))

        ctx = compute_trade_order_limit([myrtle, jie, a, b], self._mk_trade_layout(), [])
        assert ctx.total == 9  # 10+5(谈判)-6(孑)=9

    def test_瑰盐佩佩同房_累加(self):
        """瑰盐 + 佩佩均持有多面逢源 → 累加: 2 × (1×3级) = 6"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        rosesa = _mk_op("瑰盐")
        rosesa.skills.append(_mk_skill("trade_ord_limit&trade&lv[000]", "Trade", "多面逢源"))
        pepe = _mk_op("佩佩")
        pepe.skills.append(_mk_skill("trade_ord_limit&trade&lv[000]", "Trade", "多面逢源"))
        ctx = compute_trade_order_limit(
            [rosesa, pepe], self._mk_trade_layout(level=3), [],
        )
        assert ctx.total == 16
        assert ctx.contributions.get("多面逢源") == 6


# ─── 恩怨（德克萨斯 + 拉普兰德配对） ─────────────────────────────

class TestTexasLapplandSynergy:
    """A层·恩怨 — 德克萨斯与拉普兰德配对 +65%"""

    def test_恩怨_德克萨斯加拉普兰德_65percent(self):
        """德克萨斯 + 拉普兰德同房 Trade → 返回 65% 常数段"""
        from steward_core.synergy.trade_linkages import synergy_texas_lappland

        texas = _mk_op("德克萨斯")
        lappland = _mk_op("拉普兰德")
        segs = synergy_texas_lappland([texas, lappland], "Trade", 12.0)
        assert len(segs) == 1
        assert segs[0].a == 65.0
        assert segs[0].b == 0.0

    def test_恩怨_仅德克萨斯_返回空(self):
        """仅德克萨斯 → 不触发"""
        from steward_core.synergy.trade_linkages import synergy_texas_lappland

        texas = _mk_op("德克萨斯")
        segs = synergy_texas_lappland([texas], "Trade", 12.0)
        assert segs == []

    def test_恩怨_非Trade_返回空(self):
        """德克萨斯 + 拉普兰德在 Mfg → 不触发"""
        from steward_core.synergy.trade_linkages import synergy_texas_lappland

        texas = _mk_op("德克萨斯")
        lappland = _mk_op("拉普兰德")
        segs = synergy_texas_lappland([texas, lappland], "Mfg", 12.0)
        assert segs == []


# ─── 琳琅诗怀雅 招商引资（每订单上限 4%） ─────────────────────────

class TestSwiresOrderLimit:
    """A层·招商引资 — 琳琅诗怀雅 每订单上限 +4%"""

    def test_招商引资_基础10订单_40percent(self):
        """order_ctx.total=10 → 10×4% = 40%"""
        from steward_core.synergy.trade_linkages import (
            synergy_swires_order_limit, OrderLimitContext,
        )

        swires = _mk_op("琳琅诗怀雅")
        ctx = OrderLimitContext()
        segs = synergy_swires_order_limit([swires], "Trade", ctx, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 40.0

    def test_招商引资_5订单_20percent(self):
        """order_ctx.total=5 → 5×4% = 20%"""
        from steward_core.synergy.trade_linkages import (
            synergy_swires_order_limit, OrderLimitContext,
        )

        swires = _mk_op("琳琅诗怀雅")
        ctx = OrderLimitContext()
        ctx.add("孑·订单压缩", -5)
        segs = synergy_swires_order_limit([swires], "Trade", ctx, 12.0)
        assert segs[0].a == 20.0

    def test_招商引资_无琳琅诗怀雅_返回空(self):
        """无琳琅诗怀雅 → 空"""
        from steward_core.synergy.trade_linkages import (
            synergy_swires_order_limit, OrderLimitContext,
        )

        op = _mk_op("其他")
        ctx = OrderLimitContext()
        segs = synergy_swires_order_limit([op], "Trade", ctx, 12.0)
        assert segs == []


# ─── 锏 冠军风采（每5订单上限 +25%，上限100%） ────────────────────

class TestDegenbrecherOrderLimit:
    """A层·冠军风采 — 锏 每5订单上限 +25%，上限 100%"""

    def test_冠军风采_10订单_50percent(self):
        """order_ctx.total=10 → int(10/5)×25 = 50%"""
        from steward_core.synergy.trade_linkages import (
            synergy_degenbrecher_order_limit, OrderLimitContext,
        )

        degen = _mk_op("锏")
        ctx = OrderLimitContext()
        segs = synergy_degenbrecher_order_limit([degen], "Trade", ctx, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 50.0

    def test_冠军风采_20订单_100percent上限(self):
        """order_ctx.total=20 → int(20/5)×25=100，但上限 100"""
        from steward_core.synergy.trade_linkages import (
            synergy_degenbrecher_order_limit, OrderLimitContext,
        )

        degen = _mk_op("锏")
        ctx = OrderLimitContext()
        ctx.add("谈判", 5)
        ctx.add("贝洛内+伺夜", 2)
        # total=27, floor(27/5)=5, 5×25=125, cap=100
        for i in range(10):
            ctx.add(f"buf{i}", 1)
        segs = synergy_degenbrecher_order_limit([degen], "Trade", ctx, 12.0)
        assert segs[0].a == 100.0

    def test_冠军风采_4订单_0percent(self):
        """order_ctx.total=4 → int(4/5)×25 = 0%"""
        from steward_core.synergy.trade_linkages import (
            synergy_degenbrecher_order_limit, OrderLimitContext,
        )

        degen = _mk_op("锏")
        ctx = OrderLimitContext()
        ctx.add("孑·订单压缩", -6)  # total=4
        segs = synergy_degenbrecher_order_limit([degen], "Trade", ctx, 12.0)
        assert segs == []

    def test_冠军风采_无锏_返回空(self):
        """无锏 → 空"""
        from steward_core.synergy.trade_linkages import (
            synergy_degenbrecher_order_limit, OrderLimitContext,
        )

        op = _mk_op("其他")
        ctx = OrderLimitContext()
        segs = synergy_degenbrecher_order_limit([op], "Trade", ctx, 12.0)
        assert segs == []


# ─── synergy_jie_order 通过 order_ctx 传入 ────────────────────────

class TestJieOrderWithContext:
    """synergy_jie_order 支持可选 order_ctx 参数"""

    def _mk_jie_e2(self) -> Operator:
        jie = _mk_op("孑")
        jie.skills.append(_mk_skill("trade_ord_limit_count[000]", "Trade", "市井之道"))
        jie.skills.append(_mk_skill("trade_ord_limit_diff[000]", "Trade", "摊贩经济"))
        return jie

    def test_传入order_ctx_使用上下文订单上限(self):
        """传入 order_ctx.total=6 → ceiling=6×4%=24%"""
        from steward_core.synergy.trade_linkages import (
            synergy_jie_order, OrderLimitContext,
        )

        jie = self._mk_jie_e2()
        ctx = OrderLimitContext()
        ctx.add("孑·订单压缩", -4)  # total=6

        segs = synergy_jie_order([jie], "Trade", [], 12.0, order_ctx=ctx)
        assert len(segs) == 1
        assert segs[0].a == 24.0  # 6×4%

    def test_不传order_ctx_回退原有逻辑(self):
        """不传 order_ctx → 沿用原始内部计算（行为不退化）"""
        from steward_core.synergy.trade_linkages import synergy_jie_order

        jie = self._mk_jie_e2()
        a = _mk_op("队友A")
        a.skills.append(_mk_skill("t30", "Trade", "", {"all": 30.0}))
        b = _mk_op("队友B")
        b.skills.append(_mk_skill("t30", "Trade", "", {"all": 30.0}))

        segs = synergy_jie_order([jie, a, b], "Trade", [], 12.0)
        assert len(segs) == 1
        assert segs[0].a == 16.0  # 原始行为不变
