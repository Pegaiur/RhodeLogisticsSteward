"""control_linkages 模块单元测试 — 中枢全局效率 (C1)"""

import pytest

from steward_core.models import EfficiencyMap, LinearSegment, Operator, Skill


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


# ─── C1 中枢全局效率 ─────────────────────────────────────────────

class TestControlGlobalBonus:
    """C1: compute_control_global_bonus — 中枢干员提供全局效率加成"""

    def test_凯尔希_制造站加2percent(self):
        """凯尔希(最高权限) → 制造站+2%，同种取最高"""
        from steward_core.synergy import compute_control_global_bonus

        # Arrange
        kalts = _mk_op("凯尔希")
        ling = _mk_op("令")
        chongyue = _mk_op("重岳")
        xi = _mk_op("夕")

        # Act
        bonus = compute_control_global_bonus([kalts, ling, chongyue, xi])

        # Assert
        assert bonus.mfg_bonus == 2.0

    def test_无加成中枢_返回零(self):
        """令/重岳/夕/焰尾 均无全局效率 buff → 返回零"""
        from steward_core.synergy import compute_control_global_bonus

        # Arrange
        ops = [_mk_op("令"), _mk_op("重岳"), _mk_op("夕"), _mk_op("焰尾")]

        # Act
        bonus = compute_control_global_bonus(ops)

        # Assert
        assert bonus.mfg_bonus == 0.0
        assert bonus.trade_bonus == 0.0

    def test_empty_control(self):
        """空中枢 → 无加成"""
        from steward_core.synergy import compute_control_global_bonus

        bonus = compute_control_global_bonus([])
        assert bonus.mfg_bonus == 0.0
        assert bonus.trade_bonus == 0.0

    def test_Mon3tr_制造站加2percent(self):
        """Mon3tr(最高权限) → 制造站+2%（真数据下可能替代凯尔希出现）"""
        from steward_core.synergy import compute_control_global_bonus

        mon3tr = _mk_op("Mon3tr")
        bonus = compute_control_global_bonus([mon3tr])
        assert bonus.mfg_bonus == 2.0

    def test_同种取最高_两干员共存(self):
        """凯尔希和 Mon3tr 共存 → 同种效果取最高，仍为 2%"""
        from steward_core.synergy import compute_control_global_bonus

        kalts = _mk_op("凯尔希")
        mon3tr = _mk_op("Mon3tr")
        bonus = compute_control_global_bonus([kalts, mon3tr])
        assert bonus.mfg_bonus == 2.0


# ─── CONTROL 全局加成扩展 ────────────────────────────────────────

class TestControlGlobalExtended:
    """C1 扩展: 超频/以身作则/共事情谊/秘传交涉术"""

    def test_超频_2作业平台_制造加2(self):
        """布丁超频: ≥2作业平台在发电站 → 制造+2%"""
        from steward_core.synergy import compute_control_global_bonus

        buding = _mk_op("布丁")
        bonus = compute_control_global_bonus([buding], power_platforms={"Lancet-2": True, "Castle-3": True})

        assert bonus.mfg_bonus == 2.0

    def test_超频_不足2台_无加成(self):
        """布丁超频: 仅1台作业平台 → 无加成"""
        from steward_core.synergy import compute_control_global_bonus

        buding = _mk_op("布丁")
        bonus = compute_control_global_bonus([buding], power_platforms={"Lancet-2": True})

        assert bonus.mfg_bonus == 0.0

    def test_以身作则_MH同中枢_制造加2(self):
        """麒麟R夜刀以身作则: 怪物猎人同中枢 → 制造+2%"""
        from steward_core.synergy import compute_control_global_bonus

        yedao = _mk_op("麒麟R夜刀")
        heijiao = _mk_op("火龙S黑角")
        bonus = compute_control_global_bonus([yedao, heijiao])

        assert bonus.mfg_bonus == 2.0

    def test_以身作则_MH不在中枢_无加成(self):
        """麒麟R夜刀单独在中枢，无MH同伴 → 无加成"""
        from steward_core.synergy import compute_control_global_bonus

        yedao = _mk_op("麒麟R夜刀")
        bonus = compute_control_global_bonus([yedao])

        assert bonus.mfg_bonus == 0.0

    def test_秘传交涉术_MH同中枢_贸易加7(self):
        """火龙S黑角秘传交涉术: MH同中枢 → 贸易+7%"""
        from steward_core.synergy import compute_control_global_bonus

        heijiao = _mk_op("火龙S黑角")
        yedao = _mk_op("麒麟R夜刀")
        bonus = compute_control_global_bonus([heijiao, yedao])

        assert bonus.trade_bonus == 7.0

    def test_共事情谊_龙门近卫局同中枢_制造加3(self):
        """斩业星熊共事情谊: 龙门近卫局同中枢 → 制造+3%"""
        from steward_core.synergy import compute_control_global_bonus

        xingxiong = _mk_op("斩业星熊")
        chen = _mk_op("陈")
        bonus = compute_control_global_bonus([xingxiong, chen])

        assert bonus.mfg_bonus == 3.0


# ─── C1 中枢全局扩展（望） ────────────────────────────────────────

class TestC1Wang:
    """C1: compute_control_global_bonus — 望（外势实地条件型）"""

    def test_望_243布局_外势大于实地_仅贸易加7(self):
        """243布局(Mfg=4, Trade=2, Power=3): 外势(5) >= 实地(4) → 仅 Trade +7%"""
        from steward_core.synergy import compute_control_global_bonus

        wang = _mk_op("望")
        bonus = compute_control_global_bonus([wang], mfg_rooms=4, trade_rooms=2, power_rooms=3)

        assert bonus.trade_bonus == 7.0
        assert bonus.mfg_bonus == 0.0

    def test_望_实地大于外势_仅制造加2(self):
        """外势(trade+power=3) < 实地(mfg=4) → 仅 Mfg +2%"""
        from steward_core.synergy import compute_control_global_bonus

        wang = _mk_op("望")
        bonus = compute_control_global_bonus([wang], mfg_rooms=4, trade_rooms=1, power_rooms=2)

        assert bonus.mfg_bonus == 2.0
        assert bonus.trade_bonus == 0.0

    def test_望_默认参数_外势实地均为零_贸易加7(self):
        """默认参数(0,0,0): 外势(0) >= 实地(0) → Trade +7%（向后兼容）"""
        from steward_core.synergy import compute_control_global_bonus

        wang = _mk_op("望")
        bonus = compute_control_global_bonus([wang])

        assert bonus.trade_bonus == 7.0
        assert bonus.mfg_bonus == 0.0

    def test_望与凯尔希共存_243_同种取最高(self):
        """243布局: 凯尔希 Mfg +2% + 望 Trade +7%（望无制造加成）"""
        from steward_core.synergy import compute_control_global_bonus

        wang = _mk_op("望")
        kalts = _mk_op("凯尔希")

        bonus = compute_control_global_bonus([wang, kalts], mfg_rooms=4, trade_rooms=2, power_rooms=3)
        assert bonus.mfg_bonus == 2.0   # 凯尔希2
        assert bonus.trade_bonus == 7.0  # 望7


# ─── C1 全局贸易加成 fallback（阿米娅/诗怀雅/佩佩/阿斯卡纶） ────

class TestC1Trade7Fallback:
    """C1: compute_control_global_bonus — 全局贸易+7% fallback"""

    def test_阿米娅_贸易加7(self):
        from steward_core.synergy import compute_control_global_bonus

        amiya = _mk_op("阿米娅")
        bonus = compute_control_global_bonus([amiya])

        assert bonus.trade_bonus == 7.0
        assert bonus.mfg_bonus == 0.0

    def test_诗怀雅_贸易加7(self):
        from steward_core.synergy import compute_control_global_bonus

        swire = _mk_op("诗怀雅")
        bonus = compute_control_global_bonus([swire])

        assert bonus.trade_bonus == 7.0

    def test_佩佩_贸易加7(self):
        from steward_core.synergy import compute_control_global_bonus

        mingjiao = _mk_op("明椒")
        bonus = compute_control_global_bonus([mingjiao])

        assert bonus.trade_bonus == 7.0

    def test_阿斯卡纶_贸易加7(self):
        from steward_core.synergy import compute_control_global_bonus

        ascln = _mk_op("阿斯卡纶")
        bonus = compute_control_global_bonus([ascln])

        assert bonus.trade_bonus == 7.0

    def test_阿米娅加望_同种取最高仍为7(self):
        """同种取最高：望7 与 阿米娅7 → 取 max=7"""
        from steward_core.synergy import compute_control_global_bonus

        amiya = _mk_op("阿米娅")
        wang = _mk_op("望")
        bonus = compute_control_global_bonus([amiya, wang])

        assert bonus.trade_bonus == 7.0


# ─── C2 中枢 per-operator 加成 ──────────────────────────────────────

class TestC2PerOperatorBonus:
    """C2: control_per_operator_bonus — 中枢干员对房间干员的条件加成"""

    def test_八幡海铃_叙拉古Trade干员每人加5(self):
        """八幡海铃(家族认可)在中枢 → 每个叙拉古 Trade 干员 +5%"""
        from steward_core.synergy import control_per_operator_bonus

        yahata = _mk_op("八幡海铃")
        bellone = _mk_op("贝洛内", nation_id="siracusa")
        siye = _mk_op("伺夜", nation_id="siracusa")

        bonus = control_per_operator_bonus(
            [yahata], [bellone, siye], "Money", room_type="Trade",
        )
        assert bonus == 10.0  # 2 人 × 5%

    def test_八幡海铃_无叙拉古干员_不加成(self):
        """八幡海铃在 but Trade 无叙拉古干员 → 0"""
        from steward_core.synergy import control_per_operator_bonus

        yahata = _mk_op("八幡海铃")
        generic = _mk_op("普通干员", nation_id="lungmen")

        bonus = control_per_operator_bonus(
            [yahata], [generic], "Money", room_type="Trade",
        )
        assert bonus == 0.0

    def test_焰尾_红松骑士团Mfg_CR加10_PG减10(self):
        """焰尾在中枢 → 每个红松骑士团 Mfg 干员: CR +10%, PG -10%"""
        from steward_core.synergy import control_per_operator_bonus

        flammetail = _mk_op("焰尾")
        p1 = _mk_op("野鬃", group_id="pinus")
        p2 = _mk_op("灰毫", group_id="pinus")

        bonus_cr = control_per_operator_bonus(
            [flammetail], [p1, p2], "CombatRecord", room_type="Mfg",
        )
        assert bonus_cr == 20.0

        bonus_pg = control_per_operator_bonus(
            [flammetail], [p1], "PureGold", room_type="Mfg",
        )
        assert bonus_pg == -10.0

    def test_焰尾_Trade房间_不触发(self):
        """焰尾加成仅对 Mfg 生效"""
        from steward_core.synergy import control_per_operator_bonus

        flammetail = _mk_op("焰尾")
        p1 = _mk_op("野鬃", group_id="pinus")

        bonus = control_per_operator_bonus(
            [flammetail], [p1], "Money", room_type="Trade",
        )
        assert bonus == 0.0

    def test_薇薇安娜_骑士Mfg每人加7(self):
        """薇薇安娜在中枢 → 每个骑士 Mfg 干员 +7%"""
        from steward_core.synergy import control_per_operator_bonus

        vvana = _mk_op("薇薇安娜")
        k1 = _mk_op("耀骑士临光", nation_id="kazimierz")
        k2 = _mk_op("砾", nation_id="kazimierz")

        bonus = control_per_operator_bonus(
            [vvana], [k1, k2], "CombatRecord", room_type="Mfg",
        )
        assert bonus == 14.0

    def test_涤火杰西卡_黑钢国际Mfg每人加5(self):
        """涤火杰西卡(老友相聚)在中枢 → 每个黑钢国际 Mfg 干员 +5%"""
        from steward_core.synergy import control_per_operator_bonus

        jessica = _mk_op("涤火杰西卡")
        b1 = _mk_op("香草", group_id="blacksteel")
        b2 = _mk_op("杰西卡", group_id="blacksteel")

        bonus = control_per_operator_bonus(
            [jessica], [b1, b2], "CombatRecord", room_type="Mfg",
        )
        assert bonus == 10.0

    def test_八幡海铃不在中枢_不加成(self):
        """中枢无八幡海铃 → 叙拉古加成不触发"""
        from steward_core.synergy import control_per_operator_bonus

        other = _mk_op("凯尔希")
        bellone = _mk_op("贝洛内", nation_id="siracusa")

        bonus = control_per_operator_bonus(
            [other], [bellone], "Money", room_type="Trade",
        )
        assert bonus == 0.0

    def test_八幡海铃_Mfg房间_不触发(self):
        """八幡海铃的加成仅对 Trade/Money 生效，Mfg 不触发"""
        from steward_core.synergy import control_per_operator_bonus

        yahata = _mk_op("八幡海铃")
        bellone = _mk_op("贝洛内", nation_id="siracusa")

        bonus = control_per_operator_bonus(
            [yahata], [bellone], "CombatRecord", room_type="Mfg",
        )
        assert bonus == 0.0

    def test_八幡海铃_叙拉古干员混编_仅计数叙拉古(self):
        """Trade 房 3 人（2 叙拉古 + 1 非叙拉古）→ +10%"""
        from steward_core.synergy import control_per_operator_bonus

        yahata = _mk_op("八幡海铃")
        bellone = _mk_op("贝洛内", nation_id="siracusa")
        siye = _mk_op("伺夜", nation_id="siracusa")
        generic = _mk_op("普通干员", nation_id="lungmen")

        bonus = control_per_operator_bonus(
            [yahata], [bellone, siye, generic], "Money", room_type="Trade",
        )
        assert bonus == 10.0

    def test_银灰异格_Trade满3谢拉格_加10(self):
        """凛御银灰在中枢，Trade 房 ≥3 谢拉格干员 → +10%"""
        from steward_core.synergy import control_per_operator_bonus

        silverash = _mk_op("凛御银灰")
        k1 = _mk_op("崖心", group_id="karlan")
        k2 = _mk_op("讯使", group_id="karlan")
        k3 = _mk_op("角峰", group_id="karlan")

        bonus = control_per_operator_bonus(
            [silverash], [k1, k2, k3], "Money", room_type="Trade",
        )
        assert bonus == 10.0

    def test_银灰异格_Trade不足3谢拉格_不加成(self):
        """凛御银灰在中枢，Trade 房仅 2 谢拉格 → 0"""
        from steward_core.synergy import control_per_operator_bonus

        silverash = _mk_op("凛御银灰")
        k1 = _mk_op("崖心", group_id="karlan")
        k2 = _mk_op("讯使", group_id="karlan")

        bonus = control_per_operator_bonus(
            [silverash], [k1, k2], "Money", room_type="Trade",
        )
        assert bonus == 0.0

    def test_戴菲恩_Trade每格拉斯哥帮加10(self):
        """戴菲恩在中枢，Trade 房 2 格拉斯哥帮 → +20%"""
        from steward_core.synergy import control_per_operator_bonus

        delphin = _mk_op("戴菲恩")
        g1 = _mk_op("推进之王", group_id="glasgow")
        g2 = _mk_op("摩根", group_id="glasgow")

        bonus = control_per_operator_bonus(
            [delphin], [g1, g2], "Money", room_type="Trade",
        )
        assert bonus == 20.0

    def test_戴菲恩_无格拉斯哥帮_不加成(self):
        """戴菲恩在中枢，Trade 房无格拉斯哥帮 → 0"""
        from steward_core.synergy import control_per_operator_bonus

        delphin = _mk_op("戴菲恩")
        generic = _mk_op("普通干员")

        bonus = control_per_operator_bonus(
            [delphin], [generic], "Money", room_type="Trade",
        )
        assert bonus == 0.0

    def test_银灰异格_Mfg房间_不触发(self):
        """凛御银灰加成仅对 Trade 生效"""
        from steward_core.synergy import control_per_operator_bonus

        silverash = _mk_op("凛御银灰")
        k1 = _mk_op("崖心", group_id="karlan")
        k2 = _mk_op("讯使", group_id="karlan")
        k3 = _mk_op("角峰", group_id="karlan")

        bonus = control_per_operator_bonus(
            [silverash], [k1, k2, k3], "PureGold", room_type="Mfg",
        )
        assert bonus == 0.0

    def test_戴菲恩_Mfg房间_不触发(self):
        """戴菲恩加成仅对 Trade 生效"""
        from steward_core.synergy import control_per_operator_bonus

        delphin = _mk_op("戴菲恩")
        g1 = _mk_op("摩根", group_id="glasgow")

        bonus = control_per_operator_bonus(
            [delphin], [g1], "PureGold", room_type="Mfg",
        )
        assert bonus == 0.0

    def test_银灰异格不在中枢_不加成(self):
        """中枢无凛御银灰 → 加成不触发"""
        from steward_core.synergy import control_per_operator_bonus

        other = _mk_op("凯尔希")
        k1 = _mk_op("崖心", group_id="karlan")
        k2 = _mk_op("讯使", group_id="karlan")
        k3 = _mk_op("角峰", group_id="karlan")

        bonus = control_per_operator_bonus(
            [other], [k1, k2, k3], "Money", room_type="Trade",
        )
        assert bonus == 0.0

    def test_灵知_谢拉格Trade每名负15(self):
        """灵知在中枢 → 每名谢拉格 Trade 干员 -15%"""
        from steward_core.synergy import control_per_operator_bonus

        gnosis = _mk_op("灵知")
        k1 = _mk_op("崖心", group_id="karlan")
        k2 = _mk_op("讯使", group_id="karlan")

        bonus = control_per_operator_bonus(
            [gnosis], [k1, k2], "Money", room_type="Trade",
        )
        assert bonus == -30.0

    def test_灵知_Mfg房间_不触发(self):
        """灵知加成仅对 Trade 生效"""
        from steward_core.synergy import control_per_operator_bonus

        gnosis = _mk_op("灵知")
        k1 = _mk_op("崖心", group_id="karlan")

        bonus = control_per_operator_bonus(
            [gnosis], [k1], "CombatRecord", room_type="Mfg",
        )
        assert bonus == 0.0


# ─── C3 中枢→会客室加成 ──────────────────────────────────────────

class TestC3ControlReception:
    """C3: compute_control_reception_bonus — 中枢干员对会客室的全局加成"""

    def _make_ctx(self, control_names, reception_names=None, **op_kwargs):
        """构造最小 SlotContext: 仅填充 Control 槽位"""
        from steward_core.solver.slot.context import SlotContext
        from steward_core.solver.params import SolverParams

        params = SolverParams()
        ops = []
        for name in control_names:
            ops.append(_mk_op(name, **op_kwargs))
        if reception_names:
            for name in reception_names:
                ops.append(_mk_op(name, **op_kwargs))

        extra_names = []
        if reception_names:
            extra_names = list(reception_names)
        for name in set(control_names) | set(extra_names or []):
            if not any(o.name == name for o in ops):
                ops.append(_mk_op(name))

        ctx = SlotContext(operators=ops, op_lookup={o.name: o for o in ops}, params=params)
        ctx.windows = [type("_W", (), {"assignments": []})()]
        from steward_core.solver.slot.context import WindowState
        ctx.windows = [WindowState()]

        for i, name in enumerate(control_names):
            ctx.windows[0].assignments.append(type("_A", (), {
                "slot_id": f"control_0_{i}",
                "facility_type": "Control",
                "product": "",
                "operator_name": name,
                "room_index": 0,
            })())
        if reception_names:
            for i, name in enumerate(reception_names):
                ctx.windows[0].assignments.append(type("_A", (), {
                    "slot_id": f"reception_0_{i}",
                    "facility_type": "Reception",
                    "product": "",
                    "operator_name": name,
                    "room_index": 0,
                })())
        return ctx

    def test_老鲤_会客室加25(self):
        """老鲤在中枢 → 无条件 +25%"""
        from steward_core.synergy.control_linkages import compute_control_reception_bonus

        ctx = self._make_ctx(["老鲤"])
        ctrl_ops = [ctx.op_lookup["老鲤"]]

        bonus = compute_control_reception_bonus(ctrl_ops, ctx, 0)
        assert bonus == 25.0

    def test_魔王_会客室加15(self):
        """魔王在中枢 → 无条件 +15%"""
        from steward_core.synergy.control_linkages import compute_control_reception_bonus

        ctx = self._make_ctx(["魔王"])
        ctrl_ops = [ctx.op_lookup["魔王"]]

        bonus = compute_control_reception_bonus(ctrl_ops, ctx, 0)
        assert bonus == 15.0

    def test_老鲤魔王共存_取最高25(self):
        """老鲤+魔王同在中枢 → max(25, 15) = 25"""
        from steward_core.synergy.control_linkages import compute_control_reception_bonus

        ctx = self._make_ctx(["老鲤", "魔王"])
        ctrl_ops = [ctx.op_lookup["老鲤"], ctx.op_lookup["魔王"]]

        bonus = compute_control_reception_bonus(ctrl_ops, ctx, 0)
        assert bonus == 25.0

    def test_摆渡人_3名米诺斯_加15(self):
        """摆渡人在中枢 + 全基建 3 名米诺斯干员 → 3×5 = 15%"""
        from steward_core.synergy.control_linkages import compute_control_reception_bonus

        ctx = self._make_ctx(["摆渡人"])
        ferryman = ctx.op_lookup["摆渡人"]
        ferryman.nation_id = "minos"
        m1 = _mk_op("帕拉斯", nation_id="minos")
        m2 = _mk_op("刻俄柏", nation_id="minos")
        ctx.op_lookup[m1.name] = m1
        ctx.op_lookup[m2.name] = m2
        ctx.operators.extend([m1, m2])
        ctrl_ops = [ferryman]

        bonus = compute_control_reception_bonus(ctrl_ops, ctx, 0)
        assert bonus == 15.0

    def test_摆渡人_米诺斯超上限_截断25(self):
        """摆渡人在中枢 + 6 名米诺斯 → min(6×5, 25) = 25"""
        from steward_core.synergy.control_linkages import compute_control_reception_bonus

        ctx = self._make_ctx(["摆渡人"])
        ferryman = ctx.op_lookup["摆渡人"]
        ferryman.nation_id = "minos"
        for i in range(5):
            m = _mk_op(f"米诺斯{i}", nation_id="minos")
            ctx.op_lookup[m.name] = m
            ctx.operators.append(m)
        ctrl_ops = [ferryman]

        bonus = compute_control_reception_bonus(ctrl_ops, ctx, 0)
        assert bonus == 25.0

    def test_维什戴尔_伊内丝在会客室_加5(self):
        """维什戴尔在中枢 + 伊内丝在会客室 → +5%"""
        from steward_core.synergy.control_linkages import compute_control_reception_bonus

        ctx = self._make_ctx(["维什戴尔"], reception_names=["伊内丝"])
        ctrl_ops = [ctx.op_lookup["维什戴尔"]]

        bonus = compute_control_reception_bonus(ctrl_ops, ctx, 0)
        assert bonus == 5.0

    def test_维什戴尔_伊内丝不在会客室_不加(self):
        """维什戴尔在中枢 but 伊内丝不在 Reception → 0"""
        from steward_core.synergy.control_linkages import compute_control_reception_bonus

        ctx = self._make_ctx(["维什戴尔"])
        ctrl_ops = [ctx.op_lookup["维什戴尔"]]

        bonus = compute_control_reception_bonus(ctrl_ops, ctx, 0)
        assert bonus == 0.0

    def test_怒潮凛冬_2名乌萨斯会客室_加20(self):
        """怒潮凛冬在中枢 + 2 名乌萨斯在会客室 → 2×10 = 20%"""
        from steward_core.synergy.control_linkages import compute_control_reception_bonus

        ctx = self._make_ctx(
            ["怒潮凛冬"],
            reception_names=["早露", "真理"],
        )
        early_dew = ctx.op_lookup["早露"]
        early_dew.nation_id = "ursus"
        truth = ctx.op_lookup["真理"]
        truth.nation_id = "ursus"
        ctrl_ops = [ctx.op_lookup["怒潮凛冬"]]

        bonus = compute_control_reception_bonus(ctrl_ops, ctx, 0)
        assert bonus == 20.0


# ─── C4 集群狩猎加成 ──────────────────────────────────────────

class TestClusterHuntingBonus:
    """C4: compute_cluster_hunting_bonus — 歌蕾蒂娅集群狩猎按站加成"""

    def _mk_abyssal(self, name: str) -> Operator:
        """构造深海猎人干员（group_id="abyssal"）"""
        return _mk_op(name, group_id="abyssal")

    def _mk_gladiia_ctrl(self) -> Operator:
        """构造持有集群狩猎 buff 的歌蕾蒂娅"""
        return Operator(
            char_id="歌蕾蒂娅", name="歌蕾蒂娅",
            skills=[_mk_skill("control_mp_aegir2[010]", "Control", "集群狩猎·β")],
            group_id="abyssal",
        )

    def test_4abyssal在各Mfg站_该站得40(self):
        """歌蕾蒂娅在Control + 4深海猎人在4间Mfg → 该站 +40%（4×10）"""
        from steward_core.synergy.control_linkages import compute_cluster_hunting_bonus

        gladiia = self._mk_gladiia_ctrl()
        skadi = self._mk_abyssal("斯卡蒂")
        specter = self._mk_abyssal("幽灵鲨")
        andreana = self._mk_abyssal("安哲拉")
        ulpian = self._mk_abyssal("乌尔比安")

        op_lookup = {o.name: o for o in [gladiia, skadi, specter, andreana, ulpian]}

        # 4 间 Mfg 站，每间各 1 个深海猎人
        all_mfg = {
            0: ["斯卡蒂"],
            1: ["幽灵鲨"],
            2: ["安哲拉"],
            3: ["乌尔比安"],
        }

        bonus = compute_cluster_hunting_bonus(
            control_ops=[gladiia],
            all_mfg_assignments=all_mfg,
            op_lookup=op_lookup,
            this_room_index=0,
        )
        assert bonus == 40.0  # 4 abyssal in Mfg × 10

    def test_歌蕾蒂娅不在Control_返回零(self):
        """歌蕾蒂娅不在 control_ops 中 → 0"""
        from steward_core.synergy.control_linkages import compute_cluster_hunting_bonus

        gladiia = self._mk_gladiia_ctrl()
        skadi = self._mk_abyssal("斯卡蒂")
        op_lookup = {"歌蕾蒂娅": gladiia, "斯卡蒂": skadi}
        all_mfg = {0: ["斯卡蒂"]}

        bonus = compute_cluster_hunting_bonus(
            control_ops=[], all_mfg_assignments=all_mfg,
            op_lookup=op_lookup, this_room_index=0,
        )
        assert bonus == 0.0

    def test_无深海猎人在Mfg_返回零(self):
        """歌蕾蒂娅在Control 但 Mfg 站无深海猎人 → 0"""
        from steward_core.synergy.control_linkages import compute_cluster_hunting_bonus

        gladiia = self._mk_gladiia_ctrl()
        op_lookup = {"歌蕾蒂娅": gladiia}

        bonus = compute_cluster_hunting_bonus(
            control_ops=[gladiia], all_mfg_assignments={},
            op_lookup=op_lookup, this_room_index=0,
        )
        assert bonus == 0.0

    def test_该房间无深海猎人_即使其他房间有(self):
        """Room 0 无 abyssal → 0，即使 Room 1-3 有"""
        from steward_core.synergy.control_linkages import compute_cluster_hunting_bonus

        gladiia = self._mk_gladiia_ctrl()
        skadi = self._mk_abyssal("斯卡蒂")
        specter = self._mk_abyssal("幽灵鲨")
        op_lookup = {"歌蕾蒂娅": gladiia, "斯卡蒂": skadi, "幽灵鲨": specter}

        all_mfg = {
            0: ["普通干员"],  # 该房间无 abyssal
            1: ["斯卡蒂"],
            2: ["幽灵鲨"],
        }

        bonus = compute_cluster_hunting_bonus(
            control_ops=[gladiia], all_mfg_assignments=all_mfg,
            op_lookup=op_lookup, this_room_index=0,
        )
        assert bonus == 0.0  # 该站无深海猎人 → 不加成

    def test_上限90_10个深海猎人(self):
        """10 个深海猎人在 Mfg → 上限 90%（不是 100%）"""
        from steward_core.synergy.control_linkages import compute_cluster_hunting_bonus

        gladiia = self._mk_gladiia_ctrl()
        ops = [gladiia]
        all_mfg: dict[int, list[str]] = {}
        for i in range(10):
            name = f"深海{i}"
            ops.append(self._mk_abyssal(name))
            all_mfg[i] = [name]

        op_lookup = {o.name: o for o in ops}

        bonus = compute_cluster_hunting_bonus(
            control_ops=[gladiia], all_mfg_assignments=all_mfg,
            op_lookup=op_lookup, this_room_index=0,
        )
        assert bonus == 90.0  # min(10×10, 90)

    def test_歌蕾蒂娅无cluster_hunting_buff_返回零(self):
        """歌蕾蒂娅在Control 但无 control_mp_aegir2 skill → 0"""
        from steward_core.synergy.control_linkages import compute_cluster_hunting_bonus

        gladiia = _mk_op("歌蕾蒂娅", group_id="abyssal")
        skadi = self._mk_abyssal("斯卡蒂")
        op_lookup = {"歌蕾蒂娅": gladiia, "斯卡蒂": skadi}
        all_mfg = {0: ["斯卡蒂"]}

        bonus = compute_cluster_hunting_bonus(
            control_ops=[gladiia], all_mfg_assignments=all_mfg,
            op_lookup=op_lookup, this_room_index=0,
        )
        assert bonus == 0.0

    def test_非深海猎人不受影响(self):
        """Mfg 站有非 abyssal 干员 → 不计入深海猎人计数"""
        from steward_core.synergy.control_linkages import compute_cluster_hunting_bonus

        gladiia = self._mk_gladiia_ctrl()
        skadi = self._mk_abyssal("斯卡蒂")
        amiya = _mk_op("阿米娅")
        op_lookup = {"歌蕾蒂娅": gladiia, "斯卡蒂": skadi, "阿米娅": amiya}

        all_mfg = {
            0: ["斯卡蒂", "阿米娅", "普通干员"],
        }

        bonus = compute_cluster_hunting_bonus(
            control_ops=[gladiia], all_mfg_assignments=all_mfg,
            op_lookup=op_lookup, this_room_index=0,
        )
        assert bonus == 10.0  # 仅 斯卡蒂 1 人计入


# ─── 集群狩猎冲突检测 ──────────────────────────────────────────

class TestClusterHuntingConflicts:
    """集群狩猎与配合意识/自动化/仿生海龙的冲突"""

    def test_检测集群狩猎激活(self):
        """has_cluster_hunting: 歌蕾蒂娅在Control且持有buff → True"""
        from steward_core.synergy.control_linkages import has_cluster_hunting

        gladiia = Operator(
            char_id="歌蕾蒂娅", name="歌蕾蒂娅",
            skills=[_mk_skill("control_mp_aegir2[010]", "Control", "集群狩猎·β")],
        )
        assert has_cluster_hunting([gladiia])

    def test_检测无集群狩猎(self):
        """歌蕾蒂娅无集群狩猎buff → False"""
        from steward_core.synergy.control_linkages import has_cluster_hunting

        gladiia = _mk_op("歌蕾蒂娅")
        assert not has_cluster_hunting([gladiia])

    def test_检测空中枢(self):
        """空 control_ops → False"""
        from steward_core.synergy.control_linkages import has_cluster_hunting

        assert not has_cluster_hunting([])

    def test_配合意识被集群狩猎禁用(self):
        """歌蕾蒂娅集群狩猎激活 → 槐琥配合意识失效"""
        from steward_core.synergy.control_linkages import get_disabled_mfg_mechs

        gladiia = Operator(
            char_id="歌蕾蒂娅", name="歌蕾蒂娅",
            skills=[_mk_skill("control_mp_aegir2[010]", "Control", "集群狩猎·β")],
        )
        disabled = get_disabled_mfg_mechs([gladiia])
        assert "combo_amplify" in disabled

    def test_自动化清零集群狩猎_gladiia不在Control(self):
        """自动化归零者进入房间 → 集群狩猎被清零（无论 歌蕾蒂娅 是否在 Control）"""
        from steward_core.synergy.control_linkages import is_cluster_hunting_zeroed

        # 自动化归零者（如森蚺）在 Mfg 房间
        eunectes = Operator(
            char_id="森蚺", name="森蚺",
            skills=[_mk_skill("manu_prod_spd&power[000]", "Mfg", "自动化·α")],
        )
        assert is_cluster_hunting_zeroed([eunectes], "Mfg")

    def test_无归零者_集群狩猎不清零(self):
        """普通 Mfg 房间无自动化/仿生海龙 → 集群狩猎正常"""
        from steward_core.synergy.control_linkages import is_cluster_hunting_zeroed

        generic = _mk_op("普通干员")
        assert not is_cluster_hunting_zeroed([generic], "Mfg")
