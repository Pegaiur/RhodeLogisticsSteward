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
        lianjin = _mk_op("炼金术士")
        bonus = compute_control_global_bonus([yedao, lianjin])

        assert bonus.mfg_bonus == 2.0

    def test_以身作则_MH不在中枢_无加成(self):
        """麒麟R夜刀单独在中枢，无MH同伴 → 无加成"""
        from steward_core.synergy import compute_control_global_bonus

        yedao = _mk_op("麒麟R夜刀")
        bonus = compute_control_global_bonus([yedao])

        assert bonus.mfg_bonus == 0.0

    def test_秘传交涉术_MH同中枢_贸易加7(self):
        """炼金术士秘传交涉术: MH同中枢 → 贸易+7%"""
        from steward_core.synergy import compute_control_global_bonus

        lianjin = _mk_op("炼金术士")
        yedao = _mk_op("麒麟R夜刀")
        bonus = compute_control_global_bonus([lianjin, yedao])

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
    """C1: compute_control_global_bonus — 望（外势实地）"""

    def test_望_外势_贸易加7(self):
        """望在中枢 → 贸易 +7%（外势）"""
        from steward_core.synergy import compute_control_global_bonus

        wang = _mk_op("望")
        bonus = compute_control_global_bonus([wang])

        # 望：外势 → Trade +7%，实地 → Mfg +2%
        assert bonus.trade_bonus == 7.0

    def test_望与凯尔希共存_同种取最高(self):
        """望 + 凯尔希 → Trade 取最高(望7 > 凯尔希0), Mfg 取最高(凯尔希2 > 望2)"""
        from steward_core.synergy import compute_control_global_bonus

        wang = _mk_op("望")
        kalts = _mk_op("凯尔希")

        bonus = compute_control_global_bonus([wang, kalts])
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

        peper = _mk_op("佩佩")
        bonus = compute_control_global_bonus([peper])

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
