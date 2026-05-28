"""global_linkages 模块单元测试 — 全局联动 (B6 全局阵营 / B7 跨房间配对)"""

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


# ─── B7 跨房间配对 ──────────────────────────────────────────────────

class TestCrossRoomPair:
    """B7: synergy_cross_room_pair — 跨设施干员条件配对"""

    def test_患难拍档_古米在贸易站_作战记录加35(self):
        """烈夏在 Mfg CR，古米在 Trade → CR +35%"""
        from steward_core.synergy import synergy_cross_room_pair

        liexia = _mk_op("烈夏")
        gumi = _mk_op("古米")

        all_assignments = {"Trade": [gumi]}

        segs = synergy_cross_room_pair([liexia], "Mfg", "CombatRecord", all_assignments, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 35.0

    def test_患难拍档_古米不在贸易站_不加成(self):
        """烈夏在 Mfg，古米不在 Trade → 空"""
        from steward_core.synergy import synergy_cross_room_pair

        liexia = _mk_op("烈夏")

        segs = synergy_cross_room_pair([liexia], "Mfg", "CombatRecord", {}, 12.0)
        assert segs == []

    def test_患难拍档_产物不匹配_不触发(self):
        """烈夏在 Mfg PureGold，古米在 Trade → 不触发（仅作战记录）"""
        from steward_core.synergy import synergy_cross_room_pair

        liexia = _mk_op("烈夏")
        gumi = _mk_op("古米")

        all_assignments = {"Trade": [gumi]}

        segs = synergy_cross_room_pair([liexia], "Mfg", "PureGold", all_assignments, 12.0)
        assert segs == []

    def test_无B7干员_返回空(self):
        """房间无 B7 锚点干员 → 空列表"""
        from steward_core.synergy import synergy_cross_room_pair

        a = _mk_op("填位A")
        b = _mk_op("填位B")

        all_assignments = {"Trade": [_mk_op("古米")]}

        segs = synergy_cross_room_pair([a, b], "Mfg", "CombatRecord", all_assignments, 12.0)
        assert segs == []


# ─── B6 全局阵营计数 ─────────────────────────────────────────────

class TestB6GlobalFaction:
    """B6: synergy_global_faction — 全基建阵营计数"""

    def test_缪尔赛思_莱茵生命除己4名_发电加12(self):
        """缪尔赛思在 Power，全局有5名莱茵生命干员(含自身) → (5-1)×3% = 12%"""
        from steward_core.synergy import synergy_global_faction

        muelsyse = _mk_op("缪尔赛思", group_id="rhine")
        others = [_mk_op(f"莱茵{i}", group_id="rhine") for i in range(4)]

        all_ops = [muelsyse] + others
        segs = synergy_global_faction([muelsyse], "Power", "", all_ops, 12.0)

        assert len(segs) == 1
        assert segs[0].a == 12.0  # (5-1) × 3% = 12%

    def test_缪尔赛思_仅自身_不加成(self):
        """缪尔赛思独自 → 除自身无莱茵干员 → 0"""
        from steward_core.synergy import synergy_global_faction

        muelsyse = _mk_op("缪尔赛思", group_id="rhine")
        segs = synergy_global_faction([muelsyse], "Power", "", [muelsyse], 12.0)

        assert segs == []

    def test_杏仁_黑钢国际含自身3名_贵金属加6(self):
        """杏仁在 Mfg PureGold，含自身3名黑钢 → min(3,3)×2% = 6%"""
        from steward_core.synergy import synergy_global_faction

        almond = _mk_op("杏仁", group_id="blacksteel")
        others = [_mk_op(f"黑钢{i}", group_id="blacksteel") for i in range(2)]
        all_ops = [almond] + others + [_mk_op(f"其他{i}") for i in range(5)]

        segs = synergy_global_faction([almond], "Mfg", "PureGold", all_ops, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 6.0  # 3人 × 2%

    def test_杏仁_超过上限3_不变(self):
        """杏仁在场，全局5名黑钢 → min(5,3)×2% = 6%（触发上限）"""
        from steward_core.synergy import synergy_global_faction

        almond = _mk_op("杏仁", group_id="blacksteel")
        others = [_mk_op(f"黑钢{i}", group_id="blacksteel") for i in range(5)]
        all_ops = [almond] + others

        segs = synergy_global_faction([almond], "Mfg", "PureGold", all_ops, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 6.0  # clamp 3 × 2%

    def test_娜斯提_莱茵生命5名_贵金属加15(self):
        """娜斯提在场，全局5名莱茵 → 5×3% = 15%"""
        from steward_core.synergy import synergy_global_faction

        nasti = _mk_op("娜斯提", group_id="rhine")
        others = [_mk_op(f"莱茵{i}", group_id="rhine") for i in range(4)]
        all_ops = [nasti] + others

        segs = synergy_global_faction([nasti], "Mfg", "PureGold", all_ops, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 15.0  # 5人 × 3%

    def test_杏仁_非Mfg房间_不触发(self):
        """杏仁在 Trade → 不触发 B6（目标设施为 Mfg）"""
        from steward_core.synergy import synergy_global_faction

        almond = _mk_op("杏仁", group_id="blacksteel")
        others = [_mk_op(f"黑钢{i}", group_id="blacksteel") for i in range(2)]
        all_ops = [almond] + others

        segs = synergy_global_faction([almond], "Trade", "Money", all_ops, 12.0)
        assert segs == []


# ─── B7 跨房间配对扩展 ──────────────────────────────────────────

class TestB7CrossRoomExtended:
    """B7: synergy_cross_room_pair — 深巡 跨设施配对"""

    def test_深巡_乌尔比安在任意设施_贸易加10(self):
        """深巡在 Trade，乌尔比安在 Control → Trade +10%(β)"""
        from steward_core.synergy import synergy_cross_room_pair

        shenxun = _mk_op("深巡")
        urbien = _mk_op("乌尔比安")

        all_assignments = {"Control": [urbien], "Trade": [shenxun]}
        segs = synergy_cross_room_pair([shenxun], "Trade", "Money", all_assignments, 12.0)

        assert len(segs) == 1
        assert segs[0].a == 10.0

    def test_深巡_乌尔比安不在_不加成(self):
        """深巡在 Trade，乌尔比安不在基建设施 → 空"""
        from steward_core.synergy import synergy_cross_room_pair

        shenxun = _mk_op("深巡")
        segs = synergy_cross_room_pair([shenxun], "Trade", "Money", {}, 12.0)

        assert segs == []
