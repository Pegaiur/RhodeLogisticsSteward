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
              capacity: int = 0, phase: int = 0) -> Skill:
    return Skill(
        buff_id=buff_id,
        buff_name=buff_name,
        skill_icon=buff_id,
        room_type=room_type,
        efficient=EfficiencyMap(raw=efficient or {"all": 0.0}),
        capacity_bonus=capacity,
        phase=phase,
    )


# ─── 鸿雪销路宣发 + 际崖居民 ─────────────────────────────────────

class TestGoldLineSynergy:
    """鸿雪双技能: synergy_trade_gold_lines — 销路宣发+际崖居民"""

    def test_销路宣发_2赤金线_加10percent(self):
        """鸿雪持有 trade_ord_spd&gold[100] → 2 赤金线 × 5% = 10%"""
        from steward_core.synergy import synergy_trade_gold_lines
        from steward_core.models import LayoutConfig, RoomConfig

        hongxue = _mk_op("鸿雪")
        hongxue.skills.append(_mk_skill("trade_ord_spd&gold[100]", "Trade", "销路宣发"))
        layout = LayoutConfig(rooms=[
            RoomConfig("Mfg", 0, 3, "PureGold"),
            RoomConfig("Mfg", 1, 3, "PureGold"),
        ])

        segs = synergy_trade_gold_lines([hongxue], "Trade", "Money", layout, T=12.0)
        assert len(segs) == 1
        assert segs[0].a == 10.0

    def test_销路宣发_无鸿雪buff_返回空(self):
        """房间无人持有 trade_ord_spd&gold[100] → 空"""
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
        hongxue.skills.append(_mk_skill("trade_ord_spd&gold[100]", "Trade", "销路宣发"))
        segs = synergy_trade_gold_lines([hongxue], "Mfg", "PureGold", LayoutConfig(rooms=[]), 12.0)
        assert segs == []

    def test_际崖居民_2杜林族_加2赤金线(self):
        """2 杜林族 + 2 基础赤金线 = 4 赤金线 × 5% = 20%"""
        from steward_core.synergy import synergy_trade_gold_lines
        from steward_core.models import LayoutConfig, RoomConfig

        hongxue = _mk_op("鸿雪")
        hongxue.skills.append(_mk_skill("trade_ord_spd&gold[100]", "Trade", "销路宣发"))
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
        hongxue.skills.append(_mk_skill("trade_ord_spd&gold[100]", "Trade", "销路宣发"))
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
        """贝洛内 + 伺夜同房 → +2（表驱动，需 buff 存在）"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        bellone = _mk_op("贝洛内")
        bellone.skills.append(_mk_skill("trade_ord_limit&cost_P[020]", "Trade", "未偿还的债务"))
        siye = _mk_op("伺夜")
        ctx = compute_trade_order_limit(
            [bellone, siye], self._mk_trade_layout(), [],
        )
        assert ctx.total == 12
        assert ctx.contributions.get("未偿还的债务") == 2

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


# ─── 贸易配对表驱动 ──────────────────────────────────────────

class TestTradePairSynergy:
    """A层·贸易配对 — _TRADE_PAIR_TABLE 表驱动"""

    def test_恩怨_德克萨斯加拉普兰德_65percent(self):
        """德克萨斯持有 trade_ord_spd&cost_P + 拉普兰德同房 → 65%"""
        from steward_core.synergy.trade_linkages import synergy_trade_pair

        texas = _mk_op("德克萨斯")
        texas.skills.append(_mk_skill("trade_ord_spd&cost_P[000]", "Trade", "恩怨"))
        lappland = _mk_op("拉普兰德")
        segs = synergy_trade_pair([texas, lappland], "Trade", 12.0)
        assert len(segs) == 1
        assert segs[0].a == 65.0

    def test_恩怨_仅德克萨斯_返回空(self):
        """仅德克萨斯 → 不触发"""
        from steward_core.synergy.trade_linkages import synergy_trade_pair

        texas = _mk_op("德克萨斯")
        texas.skills.append(_mk_skill("trade_ord_spd&cost_P[000]", "Trade", "恩怨"))
        segs = synergy_trade_pair([texas], "Trade", 12.0)
        assert segs == []

    def test_恩怨_非Trade_返回空(self):
        """德克萨斯 + 拉普兰德在 Mfg → 不触发"""
        from steward_core.synergy.trade_linkages import synergy_trade_pair

        texas = _mk_op("德克萨斯")
        texas.skills.append(_mk_skill("trade_ord_spd&cost_P[000]", "Trade", "恩怨"))
        lappland = _mk_op("拉普兰德")
        segs = synergy_trade_pair([texas, lappland], "Mfg", 12.0)
        assert segs == []

    def test_蕾缪安加能天使_25percent(self):
        """蕾缪安持有 trade_ord_spd&multiPar[100] + 能天使同房 → +25%"""
        from steward_core.synergy.trade_linkages import synergy_trade_pair

        lemuen = _mk_op("蕾缪安")
        lemuen.skills.append(_mk_skill("trade_ord_spd&multiPar[100]", "Trade", "相伴"))
        exusiai = _mk_op("能天使")
        segs = synergy_trade_pair([lemuen, exusiai], "Trade", 12.0)
        assert len(segs) == 1
        assert segs[0].a == 25.0

    def test_蕾缪安_无能天使_返回空(self):
        """蕾缪安独自 → 不触发"""
        from steward_core.synergy.trade_linkages import synergy_trade_pair

        lemuen = _mk_op("蕾缪安")
        lemuen.skills.append(_mk_skill("trade_ord_spd&multiPar[100]", "Trade", "相伴"))
        segs = synergy_trade_pair([lemuen], "Trade", 12.0)
        assert segs == []

    def test_双配对同时触发(self):
        """德克萨斯+拉普兰德 + 蕾缪安+能天使 → 65+25=90%"""
        from steward_core.synergy.trade_linkages import synergy_trade_pair

        texas = _mk_op("德克萨斯")
        texas.skills.append(_mk_skill("trade_ord_spd&cost_P[000]", "Trade", "恩怨"))
        lappland = _mk_op("拉普兰德")
        lemuen = _mk_op("蕾缪安")
        lemuen.skills.append(_mk_skill("trade_ord_spd&multiPar[100]", "Trade", "相伴"))
        exusiai = _mk_op("能天使")

        segs = synergy_trade_pair([texas, lappland, lemuen, exusiai], "Trade", 12.0)
        assert len(segs) == 2
        bonuses = {s.a for s in segs}
        assert bonuses == {65.0, 25.0}



# ─── 琳琅诗怀雅 招商引资（每订单上限 4%） ─────────────────────────

class TestSwiresOrderLimit:
    """A层·招商引资 — 琳琅诗怀雅 每订单上限 +4%"""

    def test_招商引资_基础10订单_40percent(self):
        """order_ctx.total=10 → 10×4% = 40%"""
        from steward_core.synergy.trade_linkages import (
            synergy_swires_order_limit, OrderLimitContext,
        )

        swires = _mk_op("琳琅诗怀雅")
        swires.skills.append(_mk_skill("trade_ord_spd_variable[000]", "Trade", "招商引资"))
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
        swires.skills.append(_mk_skill("trade_ord_spd_variable[000]", "Trade", "招商引资"))
        ctx = OrderLimitContext()
        ctx.add("孑·订单压缩", -5)
        segs = synergy_swires_order_limit([swires], "Trade", ctx, 12.0)
        assert segs[0].a == 20.0

    def test_招商引资_无buff_返回空(self):
        """无人持有 trade_ord_spd_variable[000] → 空"""
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
        degen.skills.append(_mk_skill("trade_ord_spd_variable3[000]", "Trade", "冠军风采"))
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
        degen.skills.append(_mk_skill("trade_ord_spd_variable3[000]", "Trade", "冠军风采"))
        ctx = OrderLimitContext()
        ctx.add("谈判", 5)
        ctx.add("未偿还的债务", 2)
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
        degen.skills.append(_mk_skill("trade_ord_spd_variable3[000]", "Trade", "冠军风采"))
        ctx = OrderLimitContext()
        ctx.add("孑·订单压缩", -6)  # total=4
        segs = synergy_degenbrecher_order_limit([degen], "Trade", ctx, 12.0)
        assert segs == []

    def test_冠军风采_无buff_返回空(self):
        """无人持有 trade_ord_spd_variable3[000] → 空"""
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


# ─── 订单上限表补全（trade_ord_spd&limit） ────────────────────────

class TestOrderLimitTableExpansion:
    """_ORDER_LIMIT_TABLE 补全: 5 条新增订单上限贡献 buff"""

    def _mk_trade_layout(self, level: int = 3):
        from steward_core.models import LayoutConfig, RoomConfig
        return LayoutConfig(rooms=[
            RoomConfig("Trade", 0, 3, "Money", level=level),
            RoomConfig("Trade", 1, 3, "Money", level=level),
        ])

    def test_黑角订单管理alpha_加2(self):
        """trade_ord_spd&limit[000] → 订单上限 +2"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        heijiao = _mk_op("黑角")
        heijiao.skills.append(_mk_skill("trade_ord_spd&limit[000]", "Trade", "订单管理·α"))
        ctx = compute_trade_order_limit([heijiao], self._mk_trade_layout(), [])
        assert ctx.total == 12
        assert ctx.contributions.get("订单管理·α") == 2

    def test_涤火杰西卡订单管理beta_加4(self):
        """trade_ord_spd&limit[001] → 订单上限 +4"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        jessica = _mk_op("涤火杰西卡")
        jessica.skills.append(_mk_skill("trade_ord_spd&limit[001]", "Trade", "订单管理·β"))
        ctx = compute_trade_order_limit([jessica], self._mk_trade_layout(), [])
        assert ctx.total == 14
        assert ctx.contributions.get("订单管理·β") == 4

    def test_远山供应管理_加1(self):
        """trade_ord_spd&limit[010] → 订单上限 +1"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        yuanshan = _mk_op("远山")
        yuanshan.skills.append(_mk_skill("trade_ord_spd&limit[010]", "Trade", "供应管理"))
        ctx = compute_trade_order_limit([yuanshan], self._mk_trade_layout(), [])
        assert ctx.total == 11
        assert ctx.contributions.get("供应管理") == 1

    def test_银灰喀兰贸易alpha_加2(self):
        """trade_ord_spd&limit[020] → 订单上限 +2"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        silverash = _mk_op("银灰")
        silverash.skills.append(_mk_skill("trade_ord_spd&limit[020]", "Trade", "喀兰贸易·α"))
        ctx = compute_trade_order_limit([silverash], self._mk_trade_layout(), [])
        assert ctx.total == 12
        assert ctx.contributions.get("喀兰贸易·α") == 2

    def test_银灰喀兰之主_加4(self):
        """trade_ord_spd&limit[022] → 订单上限 +4"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        silverash = _mk_op("银灰")
        silverash.skills.append(_mk_skill("trade_ord_spd&limit[022]", "Trade", "喀兰之主"))
        ctx = compute_trade_order_limit([silverash], self._mk_trade_layout(), [])
        assert ctx.total == 14
        assert ctx.contributions.get("喀兰之主") == 4

    def test_银灰精2两条技能_仅beta生效(self):
        """银灰精2持有 α[020](phase 0)+主[022](phase 2) → 同前缀升级，仅主(+4)生效"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        silverash = _mk_op("银灰")
        silverash.skills.append(_mk_skill("trade_ord_spd&limit[020]", "Trade", "喀兰贸易·α", phase=0))
        silverash.skills.append(_mk_skill("trade_ord_spd&limit[022]", "Trade", "喀兰之主", phase=2))
        ctx = compute_trade_order_limit([silverash], self._mk_trade_layout(), [])
        assert ctx.total == 14
        assert ctx.contributions.get("喀兰之主") == 4
        assert ctx.contributions.get("喀兰贸易·α") is None


# ─── 贸易站 per-operator 分享（火哨/吉星） ─────────────────────────

class TestTradeShareSynergy:
    """A层·贸易分享 — synergy_trade_share"""

    def test_火哨代为说项_3队友_45percent(self):
        """火哨 + 3名队友 → (4-1)×15 = 45%"""
        from steward_core.synergy.trade_linkages import synergy_trade_share

        huoshao = _mk_op("火哨")
        huoshao.skills.append(_mk_skill("trade_ord_spd&share[000]", "Trade", "代为说项"))
        ops = [huoshao] + [_mk_op(f"队友{i}") for i in range(3)]
        segs = synergy_trade_share(ops, "Trade", 12.0)
        assert len(segs) == 1
        assert segs[0].a == 45.0

    def test_吉星勤俭经营alpha_3队友_30percent(self):
        """吉星α + 3名队友 → (4-1)×10 = 30%"""
        from steward_core.synergy.trade_linkages import synergy_trade_share

        jixing = _mk_op("吉星")
        jixing.skills.append(_mk_skill("trade_ord_spd&share[001]", "Trade", "勤俭经营·α"))
        ops = [jixing] + [_mk_op(f"队友{i}") for i in range(3)]
        segs = synergy_trade_share(ops, "Trade", 12.0)
        assert len(segs) == 1
        assert segs[0].a == 30.0

    def test_吉星勤俭经营beta_3队友_60percent(self):
        """吉星β + 3名队友 → (4-1)×20 = 60%"""
        from steward_core.synergy.trade_linkages import synergy_trade_share

        jixing = _mk_op("吉星")
        jixing.skills.append(_mk_skill("trade_ord_spd&share[002]", "Trade", "勤俭经营·β"))
        ops = [jixing] + [_mk_op(f"队友{i}") for i in range(3)]
        segs = synergy_trade_share(ops, "Trade", 12.0)
        assert len(segs) == 1
        assert segs[0].a == 60.0

    def test_火哨独自_0percent(self):
        """火哨独自 → 0 名队友 → 0%"""
        from steward_core.synergy.trade_linkages import synergy_trade_share

        huoshao = _mk_op("火哨")
        huoshao.skills.append(_mk_skill("trade_ord_spd&share[000]", "Trade", "代为说项"))
        segs = synergy_trade_share([huoshao], "Trade", 12.0)
        assert segs == []

    def test_非Trade_返回空(self):
        """火哨在 Mfg → 不触发"""
        from steward_core.synergy.trade_linkages import synergy_trade_share

        huoshao = _mk_op("火哨")
        huoshao.skills.append(_mk_skill("trade_ord_spd&share[000]", "Trade", "代为说项"))
        segs = synergy_trade_share([huoshao], "Mfg", 12.0)
        assert segs == []

    def test_无buff_返回空(self):
        """无人持有 trade_ord_spd&share → 0"""
        from steward_core.synergy.trade_linkages import synergy_trade_share

        op = _mk_op("其他")
        segs = synergy_trade_share([op, _mk_op("队友")], "Trade", 12.0)
        assert segs == []


# ─── 雪雉 效率→效率放大器 ───────────────────────────────────────

class TestTradeEfficiencyAmplifier:
    """A层·效率放大 — synergy_trade_efficiency_amplifier"""

    def test_雪雉alpha_60percent总效率_额外30percent_capped_at_25(self):
        """雪雉α: room_eff=60, floor(60/5)=12步, 12×5=60, cap=25 → 25%"""
        from steward_core.synergy.trade_linkages import synergy_trade_efficiency_amplifier

        xuezhi = _mk_op("雪雉")
        xuezhi.skills.append(_mk_skill("trade_ord_spd_variable2[000]", "Trade", "天道酬勤·α"))
        segs = synergy_trade_efficiency_amplifier([xuezhi], "Trade", 60.0, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 25.0

    def test_雪雉alpha_20percent总效率_20percent(self):
        """雪雉α: room_eff=20, floor(20/5)=4步, 4×5=20, cap=25 → 20%"""
        from steward_core.synergy.trade_linkages import synergy_trade_efficiency_amplifier

        xuezhi = _mk_op("雪雉")
        xuezhi.skills.append(_mk_skill("trade_ord_spd_variable2[000]", "Trade", "天道酬勤·α"))
        segs = synergy_trade_efficiency_amplifier([xuezhi], "Trade", 20.0, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 20.0

    def test_雪雉beta_60percent总效率_额外30percent(self):
        """雪雉β: room_eff=60, floor(60/5)=12步, 12×5=60, cap=35 → 35%"""
        from steward_core.synergy.trade_linkages import synergy_trade_efficiency_amplifier

        xuezhi = _mk_op("雪雉")
        xuezhi.skills.append(_mk_skill("trade_ord_spd_variable2[001]", "Trade", "天道酬勤·β"))
        segs = synergy_trade_efficiency_amplifier([xuezhi], "Trade", 60.0, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 35.0

    def test_雪雉总效率小于步长_返回空(self):
        """雪雉α: room_eff=3, floor(3/5)=0 → 0%"""
        from steward_core.synergy.trade_linkages import synergy_trade_efficiency_amplifier

        xuezhi = _mk_op("雪雉")
        xuezhi.skills.append(_mk_skill("trade_ord_spd_variable2[000]", "Trade", "天道酬勤·α"))
        segs = synergy_trade_efficiency_amplifier([xuezhi], "Trade", 3.0, 12.0)
        assert segs == []

    def test_无buff_返回空(self):
        """无人持有 trade_ord_spd_variable2 → 空"""
        from steward_core.synergy.trade_linkages import synergy_trade_efficiency_amplifier

        op = _mk_op("其他")
        segs = synergy_trade_efficiency_amplifier([op], "Trade", 50.0, 12.0)
        assert segs == []

    def test_非Trade_返回空(self):
        """雪雉在 Mfg → 不触发"""
        from steward_core.synergy.trade_linkages import synergy_trade_efficiency_amplifier

        xuezhi = _mk_op("雪雉")
        xuezhi.skills.append(_mk_skill("trade_ord_spd_variable2[000]", "Trade", "天道酬勤·α"))
        segs = synergy_trade_efficiency_amplifier([xuezhi], "Mfg", 50.0, 12.0)
        assert segs == []


# ─── 贝洛内/赫德雷 per-operator 条件效率 ──────────────────────────

class TestTradeConditionalEff:
    """A层·条件效率 — synergy_trade_conditional_eff"""

    def _mk_assignments(self, **facilities: list):
        """构造 all_assignments: {facility_name: operator_list}"""
        return dict(facilities)

    def test_贝洛内alpha_伺夜在基建_加5(self):
        """贝洛内α + 伺夜在 Control → +5%"""
        from steward_core.synergy.trade_linkages import synergy_trade_conditional_eff

        bellone = _mk_op("贝洛内")
        bellone.skills.append(_mk_skill("trade_ord_spd_ext[020]", "Trade", "家族经营·α"))
        siye = _mk_op("伺夜")
        assignments = {"Control": [siye]}

        segs = synergy_trade_conditional_eff([bellone], "Trade", assignments, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 5.0

    def test_贝洛内beta_伺夜在基建_加10(self):
        """贝洛内β + 伺夜在 Mfg → +10%"""
        from steward_core.synergy.trade_linkages import synergy_trade_conditional_eff

        bellone = _mk_op("贝洛内")
        bellone.skills.append(_mk_skill("trade_ord_spd_ext[021]", "Trade", "家族经营·β"))
        siye = _mk_op("伺夜")
        assignments = {"Mfg": [siye]}

        segs = synergy_trade_conditional_eff([bellone], "Trade", assignments, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 10.0

    def test_贝洛内_伺夜不在基建_不加(self):
        """贝洛内α + 伺夜不在基建 → 空"""
        from steward_core.synergy.trade_linkages import synergy_trade_conditional_eff

        bellone = _mk_op("贝洛内")
        bellone.skills.append(_mk_skill("trade_ord_spd_ext[020]", "Trade", "家族经营·α"))
        assignments = {}  # 伺夜不在任何地方

        segs = synergy_trade_conditional_eff([bellone], "Trade", assignments, 12.0)
        assert segs == []

    def test_赫德雷alpha_伊内丝在工作场所_加5(self):
        """赫德雷α + 伊内丝在 Trade → target_scope="workspace" → +5%"""
        from steward_core.synergy.trade_linkages import synergy_trade_conditional_eff

        hederei = _mk_op("赫德雷")
        hederei.skills.append(_mk_skill("trade_ord_par&per[000]", "Trade", "白手起家·α"))
        yineisi = _mk_op("伊内丝")
        assignments = {"Trade": [yineisi]}

        segs = synergy_trade_conditional_eff([hederei], "Trade", assignments, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 5.0

    def test_赫德雷alpha_伊内丝在宿舍_不加(self):
        """赫德雷α + 伊内丝在 Dormitory（非workspace）→ 不触发"""
        from steward_core.synergy.trade_linkages import synergy_trade_conditional_eff

        hederei = _mk_op("赫德雷")
        hederei.skills.append(_mk_skill("trade_ord_par&per[000]", "Trade", "白手起家·α"))
        yineisi = _mk_op("伊内丝")
        assignments = {"Dormitory": [yineisi]}

        segs = synergy_trade_conditional_eff([hederei], "Trade", assignments, 12.0)
        assert segs == []

    def test_赫德雷beta_伊内丝和W都在_各加5(self):
        """赫德雷β + 伊内丝在 Control + W 在 Mfg → +5+5=10%"""
        from steward_core.synergy.trade_linkages import synergy_trade_conditional_eff

        hederei = _mk_op("赫德雷")
        hederei.skills.append(_mk_skill("trade_ord_par&per[001]", "Trade", "白手起家·β"))
        yineisi = _mk_op("伊内丝")
        w_op = _mk_op("W")
        assignments = {"Control": [yineisi], "Mfg": [w_op]}

        segs = synergy_trade_conditional_eff([hederei], "Trade", assignments, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 10.0

    def test_赫德雷beta_仅W在_伊内丝不在_5percent(self):
        """赫德雷β + W 在 Mfg（伊内丝不在）→ 仅 W 触发 +5%"""
        from steward_core.synergy.trade_linkages import synergy_trade_conditional_eff

        hederei = _mk_op("赫德雷")
        hederei.skills.append(_mk_skill("trade_ord_par&per[001]", "Trade", "白手起家·β"))
        w_op = _mk_op("W")
        assignments = {"Mfg": [w_op]}

        segs = synergy_trade_conditional_eff([hederei], "Trade", assignments, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 5.0

    def test_非Trade_返回空(self):
        """贝洛内在 Mfg → 不触发"""
        from steward_core.synergy.trade_linkages import synergy_trade_conditional_eff

        bellone = _mk_op("贝洛内")
        bellone.skills.append(_mk_skill("trade_ord_spd_ext[020]", "Trade", "家族经营·α"))
        siye = _mk_op("伺夜")
        assignments = {"Control": [siye]}

        segs = synergy_trade_conditional_eff([bellone], "Mfg", assignments, 12.0)
        assert segs == []


# ─── 维什戴尔→赫德雷 中枢贸易订单上限联动 ────────────────────────────

class TestControlTradeLimit:
    """C层·中枢→贸易站订单上限 — _CONTROL_TRADE_LIMIT_TABLE"""

    def _mk_trade_layout(self, level: int = 3):
        from steward_core.models import LayoutConfig, RoomConfig
        return LayoutConfig(rooms=[
            RoomConfig("Trade", 0, 3, "Money", level=level),
            RoomConfig("Trade", 1, 3, "Money", level=level),
        ])

    def test_维什戴尔alpha_赫德雷在贸易站_加1(self):
        """维什戴尔α(精0)在中枢 + 赫德雷在Trade → +1"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit
        from steward_core.models import Operator

        hederei = _mk_op("赫德雷")
        wishadel = Operator(
            char_id="维什戴尔", name="维什戴尔",
            skills=[_mk_skill("control_meeting&ord[000]", "Control", "同谋·α")],
            elite_phase=0,
        )
        ctx = compute_trade_order_limit(
            [hederei], self._mk_trade_layout(), [wishadel],
        )
        assert ctx.total == 11
        assert ctx.contributions.get("维什戴尔->赫德雷") == 1

    def test_维什戴尔beta_赫德雷在贸易站_加2(self):
        """维什戴尔β(精2)在中枢 + 赫德雷在Trade → +2"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit
        from steward_core.models import Operator

        hederei = _mk_op("赫德雷")
        wishadel = Operator(
            char_id="维什戴尔", name="维什戴尔",
            skills=[_mk_skill("control_meeting&ord[001]", "Control", "同谋·β")],
            elite_phase=2,
        )
        ctx = compute_trade_order_limit(
            [hederei], self._mk_trade_layout(), [wishadel],
        )
        assert ctx.total == 12
        assert ctx.contributions.get("维什戴尔->赫德雷") == 2

    def test_维什戴尔在中枢_赫德雷不在贸易站_不加(self):
        """维什戴尔在中枢 + 赫德雷不在 → 不触发"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        other = _mk_op("其他干员")
        wishadel = _mk_op("维什戴尔", skills=[
            _mk_skill("control_meeting&ord[000]", "Control", "同谋·α"),
        ])
        ctx = compute_trade_order_limit(
            [other], self._mk_trade_layout(), [wishadel],
        )
        assert ctx.total == 10
        assert "维什戴尔->赫德雷" not in ctx.contributions

    def test_赫德雷在贸易站_维什戴尔不在中枢_不加(self):
        """赫德雷在Trade + 维什戴尔不在中枢 → 不触发"""
        from steward_core.synergy.trade_linkages import compute_trade_order_limit

        hederei = _mk_op("赫德雷")
        ctx = compute_trade_order_limit(
            [hederei], self._mk_trade_layout(), [],
        )
        assert ctx.total == 10
        assert "维什戴尔->赫德雷" not in ctx.contributions


# ─── 绮良赤金线增强（synergy_trade_gold_lines 扩展） ──────────────

class TestGoldLineKirara:
    """synergy_trade_gold_lines — 绮良订单流可视化 赤金线追加"""

    def test_绮良alpha_4条赤金线_额外2条(self):
        """绮良α + 4 基础赤金线 → floor(4/4)×2=2 追加 → 总 6 线 × 5% = 30%"""
        from steward_core.synergy.trade_linkages import synergy_trade_gold_lines
        from steward_core.models import LayoutConfig, RoomConfig

        hongxue = _mk_op("鸿雪")
        hongxue.skills.append(_mk_skill("trade_ord_spd&gold[100]", "Trade", "销路宣发"))
        kirara = _mk_op("绮良")
        kirara.skills.append(_mk_skill("trade_ord_line_gold[000]", "Trade", "订单流可视化·α"))
        layout = LayoutConfig(rooms=[
            RoomConfig("Mfg", 0, 3, "PureGold"),
            RoomConfig("Mfg", 1, 3, "PureGold"),
            RoomConfig("Mfg", 2, 3, "PureGold"),
            RoomConfig("Mfg", 3, 3, "PureGold"),
        ])

        segs = synergy_trade_gold_lines([hongxue, kirara], "Trade", "Money", layout, T=12.0)
        assert len(segs) == 1
        assert segs[0].a == 30.0  # (4基础+2绮良) × 5%

    def test_绮良beta_2条赤金线_额外2条(self):
        """绮良β + 2 基础赤金线 → floor(2/2)×2=2 追加 → 总 4 线 × 5% = 20%"""
        from steward_core.synergy.trade_linkages import synergy_trade_gold_lines
        from steward_core.models import LayoutConfig, RoomConfig

        hongxue = _mk_op("鸿雪")
        hongxue.skills.append(_mk_skill("trade_ord_spd&gold[100]", "Trade", "销路宣发"))
        kirara = _mk_op("绮良")
        kirara.skills.append(_mk_skill("trade_ord_line_gold[010]", "Trade", "订单流可视化·β"))
        layout = LayoutConfig(rooms=[
            RoomConfig("Mfg", 0, 3, "PureGold"),
            RoomConfig("Mfg", 1, 3, "PureGold"),
        ])

        segs = synergy_trade_gold_lines([hongxue, kirara], "Trade", "Money", layout, T=12.0)
        assert len(segs) == 1
        assert segs[0].a == 20.0  # (2基础+2绮良) × 5%

    def test_绮良alpha_不足4线_不追加(self):
        """绮良α + 2 基础赤金线 → floor(2/4)=0 → 不减反触发为0"""
        from steward_core.synergy.trade_linkages import synergy_trade_gold_lines
        from steward_core.models import LayoutConfig, RoomConfig

        hongxue = _mk_op("鸿雪")
        hongxue.skills.append(_mk_skill("trade_ord_spd&gold[100]", "Trade", "销路宣发"))
        kirara = _mk_op("绮良")
        kirara.skills.append(_mk_skill("trade_ord_line_gold[000]", "Trade", "订单流可视化·α"))
        layout = LayoutConfig(rooms=[
            RoomConfig("Mfg", 0, 3, "PureGold"),
            RoomConfig("Mfg", 1, 3, "PureGold"),
        ])

        segs = synergy_trade_gold_lines([hongxue, kirara], "Trade", "Money", layout, T=12.0)
        assert len(segs) == 1
        assert segs[0].a == 10.0  # 2×5%，无追加

    def test_仅绮良_无鸿雪_无金线触发(self):
        """仅有绮良（无鸿雪 gold_lines 机制）→ 空"""
        from steward_core.synergy.trade_linkages import synergy_trade_gold_lines
        from steward_core.models import LayoutConfig, RoomConfig

        kirara = _mk_op("绮良")
        kirara.skills.append(_mk_skill("trade_ord_line_gold[000]", "Trade", "订单流可视化·α"))
        layout = LayoutConfig(rooms=[
            RoomConfig("Mfg", 0, 3, "PureGold"),
        ])

        segs = synergy_trade_gold_lines([kirara], "Trade", "Money", layout, T=12.0)
        assert segs == []
