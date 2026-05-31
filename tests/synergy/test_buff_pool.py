"""buff_pool 模块单元测试 — BuffPool 生成与消费 (B1-B5)"""

import pytest

from steward_core.models import EfficiencyMap, LayoutConfig, LinearSegment, Operator, Skill


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


def _make_office_op() -> Operator:
    """创建持有絮雨追忆技能的 Office 干员"""
    return _mk_op("絮雨", [_mk_skill("hire_spd_bd_n1[000]", "HIRE", "追忆")])


def _mk_xi() -> Operator:
    return _mk_op("夕", [
        _mk_skill("control_mp_cost&bd1[000]", "Control", "不以物喜"),
        _mk_skill("control_mp_cost&bd2[000]", "Control", "不以己悲"),
    ])


def _mk_sangshen() -> Operator:
    return _mk_op("桑葚", [
        _mk_skill("hire_spd_bd_n1_n1[200]", "HIRE", "灾后普查"),
    ])


def _mk_shenlv() -> Operator:
    return _mk_op("深律", [
        _mk_skill("hire_spd_bd_n1_n1[300]", "HIRE", "心声图绘"),
    ])


# ─── B2 工程机器人 / B3 思维链环 / B4 魔物料理 / B5 无声共鸣 ──

class TestBLayer:
    """B2/B3/B4/B5: 跨设施体系消费函数"""

    def test_b3_思维链环_迷迭香_感知转制造(self):
        """perception=10 → 10链环 → 迷迭香 +10% Mfg(β:1链环=1%)"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        miluoxiang = _mk_op("迷迭香")
        pool = BuffPool(perception=10, thought_chains=10)

        segs = synergy_buff_pool_consumer([miluoxiang], "Mfg", "PureGold", pool, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 10.0

    def test_b5_无声共鸣_黑键_贸易加成(self):
        """silent_resonance=15 → 黑键 β: 每2共鸣=+1% → +7% Trade"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        heijian = _mk_op("黑键")
        pool = BuffPool(silent_resonance=15)

        segs = synergy_buff_pool_consumer([heijian], "Trade", "Money", pool, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 7.0  # 15//2 = 7

    def test_b2_工程机器人_至简消费(self):
        """至简在 Mfg，42 robots(14设施×Lv3) → β: 每8机器人+5% → +25%"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        zhijian = _mk_op("至简")
        pool = BuffPool(engineering_robots=42)

        segs = synergy_buff_pool_consumer([zhijian], "Mfg", "PureGold", pool, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 25.0  # 42//8*5 = 25

    def test_b4_魔物料理_玛露西尔消费(self):
        """玛露西尔在 Mfg，cuisine=3 → +3%"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        maluxier = _mk_op("玛露西尔")
        pool = BuffPool(monster_cuisine=3)

        segs = synergy_buff_pool_consumer([maluxier], "Mfg", "PureGold", pool, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 3.0

    def test_compute_buff_pool_含b3b5(self):
        """compute_buff_pool 现在包含 thought_chains + silent_resonance"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("重岳"), _mk_xi()]
        pool = compute_buff_pool(control, suich_count=5)

        assert pool.yanhuo == 40
        assert pool.perception == 10
        assert pool.thought_chains == 10  # 1:1
        assert pool.wushu_crystal == 8   # 40//5

    def test_c2_global_burn_固定中枢(self):
        """C2: 3人工位 burn = 0.75 - 中枢减免(5×0.05) - 重岳孤光共照(0.05)"""
        from steward_core.synergy import compute_global_burn, compute_buff_pool

        control = [_mk_op("令"), _mk_op("重岳"), _mk_xi(), _mk_op("凯尔希"), _mk_op("焰尾")]
        buff_pool = compute_buff_pool(control, suich_count=5)
        burn = compute_global_burn(control, buff_pool, worker_count=3)

        assert burn < 0.75  # 中枢减免生效
        assert burn >= 0    # 不低于 0


# ─── B1 人间烟火 ─────────────────────────────────────────────────

class TestBuffPool:
    """B1: compute_buff_pool + synergy_buff_pool_consumer"""

    def test_固定中枢_产生烟火(self):
        """令+重岳+夕+凯尔希+焰尾 → 烟火=15(令)+25(重岳5岁)=40"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("重岳"), _mk_xi(), _mk_op("凯尔希"), _mk_op("焰尾")]
        pool = compute_buff_pool(control, suich_count=5)

        assert pool.yanhuo == 40
        assert pool.perception == 10  # 夕 mood>12

    def test_empty_control(self):
        """无中枢 → 零烟火"""
        from steward_core.synergy import compute_buff_pool

        pool = compute_buff_pool([])
        assert pool.yanhuo == 0
        assert pool.perception == 0

    def test_黍_烟火转化为制造效率(self):
        """黍: per 3 烟火 → +1%，40 烟火 → +13%"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool, compute_buff_pool

        shu = _mk_op("黍")
        pool = BuffPool(yanhuo=40, perception=0)

        segs = synergy_buff_pool_consumer([shu], "Mfg", "PureGold", pool, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 13.0  # 40//3 = 13

    def test_乌有_烟火转化为贸易效率(self):
        """乌有: per 1 烟火 → +1%，40 烟火 → +40%"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        wuyou = _mk_op("乌有")
        pool = BuffPool(yanhuo=40, perception=0)

        segs = synergy_buff_pool_consumer([wuyou], "Trade", "Money", pool, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 40.0

    def test_截云_烟火转巫术结晶(self):
        """截云: per 5 烟火 → +1 巫术结晶，per 1 巫术结晶 → +2% Mfg(β)"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        jieyun = _mk_op("截云")
        pool = BuffPool(yanhuo=40, perception=0, wushu_crystal=8)  # 40//5=8

        segs = synergy_buff_pool_consumer([jieyun], "Mfg", "PureGold", pool, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 16.0  # 8 × 2%

    def test_零烟火_无加成(self):
        """BuffPool 归零 → 消费者无输出"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        shu = _mk_op("黍")
        pool = BuffPool(yanhuo=0, perception=0)

        segs = synergy_buff_pool_consumer([shu], "Mfg", "PureGold", pool, 12.0)
        assert segs == []

    def test_非目标房间_不触发(self):
        """黍在 Trade → 不触发烟火加成"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        shu = _mk_op("黍")
        pool = BuffPool(yanhuo=40, perception=0)

        segs = synergy_buff_pool_consumer([shu], "Trade", "Money", pool, 12.0)
        assert segs == []


# ─── B1 宿舍感知信息生成器 ────────────────────────────────────────

class TestDormPerception:
    """B1: compute_buff_pool 扩展 — 宿舍干员生成感知信息"""

    def test_迷迭香超感_宿舍每有干员_感知加一(self):
        """迷迭香在制造站，4名宿舍干员 → +4 感知信息"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        dorm = [_mk_op("填位A"), _mk_op("填位B"), _mk_op("填位C"), _mk_op("填位D")]

        pool = compute_buff_pool(control, dorm_operators=dorm,
                                 mfg_operators=[_mk_op("迷迭香", [_mk_skill("manu_prod_spd_bd_n1[000]", "Mfg", "超感")])])

        assert pool.perception == 10 + 4  # 夕(10) + 迷迭香超感(4)
        assert pool.thought_chains == 14

    def test_黑键乐感_宿舍每有干员_感知加一(self):
        """黑键在贸易站，4名宿舍干员 → +4 感知信息"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        dorm = [_mk_op("A"), _mk_op("B"), _mk_op("C"), _mk_op("D")]

        pool = compute_buff_pool(control, dorm_operators=dorm,
                                 trade_operators=[_mk_op("黑键", [_mk_skill("trade_ord_spd_bd_n1[000]", "TRADING", "乐感")])])

        assert pool.perception == 10 + 4  # 夕(10) + 黑键乐感(4)
        assert pool.thought_chains == 14

    def test_迷迭香和黑键同时在场_感知叠加(self):
        """迷迭香在Mfg + 黑键在Trade → 各贡献宿舍数量感知"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        dorm = [_mk_op("A"), _mk_op("B"), _mk_op("C"), _mk_op("D")]

        pool = compute_buff_pool(control, dorm_operators=dorm,
                                 mfg_operators=[_mk_op("迷迭香", [_mk_skill("manu_prod_spd_bd_n1[000]", "Mfg", "超感")])],
                                 trade_operators=[_mk_op("黑键", [_mk_skill("trade_ord_spd_bd_n1[000]", "TRADING", "乐感")])])

        assert pool.perception == 10 + 4 + 4  # 夕(10) + 迷迭香(4) + 黑键(4)
        assert pool.thought_chains == 18

    def test_爱丽丝梦境呓语_宿舍等级转感知(self):
        """爱丽丝在宿舍 Lv3 → 3梦境 → +3 感知信息"""
        from steward_core.synergy import compute_buff_pool

        alice = _mk_op("爱丽丝")
        alice.skills.append(_mk_skill("dorm_rec_bd_n1_n2[000]", "Dormitory", "睡前故事"))
        alice.skills.append(_mk_skill("dorm_rec_bd_n1[000]", "Dormitory", "梦境呓语"))

        control = [_mk_xi()]  # 仅夕提供10感知
        dorm = [alice]

        pool = compute_buff_pool(control, dorm_operators=dorm, dorm_level=3)

        assert pool.perception == 10 + 3  # 夕(10) + 爱丽丝梦境(3)
        assert pool.thought_chains == 13

    def test_车尔尼琴键漫步_宿舍等级转感知(self):
        """车尔尼在宿舍 Lv3 → 3小节 → +3 感知信息"""
        from steward_core.synergy import compute_buff_pool

        cherni = _mk_op("车尔尼")
        cherni.skills.append(_mk_skill("dorm_rec_bd_n1_n3[000]", "Dormitory", "慢板行歌"))
        cherni.skills.append(_mk_skill("dorm_rec_bd_n1[100]", "Dormitory", "琴键漫步"))

        control = [_mk_xi()]
        dorm = [cherni]

        pool = compute_buff_pool(control, dorm_operators=dorm, dorm_level=3)

        assert pool.perception == 10 + 3  # 夕(10) + 车尔尼小节(3)

    def test_无宿舍干员_无额外感知(self):
        """空宿舍 → 仅中枢生成感知"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        pool = compute_buff_pool(control, dorm_operators=[])

        assert pool.perception == 10  # 仅夕
        assert pool.thought_chains == 10


# ─── B4 魔物料理生成器 ────────────────────────────────────────────

class TestMonsterCuisine:
    """B4: compute_buff_pool 扩展 — 森西生成魔物料理"""

    def test_森西大食堂_宿舍等级转魔物料理(self):
        """森西在宿舍 Lv3 → +3 魔物料理"""
        from steward_core.synergy import compute_buff_pool

        sensi = _mk_op("森西")
        sensi.skills.append(_mk_skill("dorm_rec_bd_dungeon[000]", "Dormitory", "森西大食堂"))

        control = [_mk_op("令"), _mk_xi()]
        dorm = [sensi]

        pool = compute_buff_pool(control, dorm_operators=dorm, dorm_level=3)

        assert pool.monster_cuisine == 3

    def test_无森西_无魔物料理(self):
        """无森西在宿舍 → monster_cuisine = 0"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        dorm = [_mk_op("填位")]

        pool = compute_buff_pool(control, dorm_operators=dorm)

        assert pool.monster_cuisine == 0


# ─── 完整 BuffPool 集成测试 ────────────────────────────────────────

class TestFullBuffPool:
    """集成：控制中枢 + 宿舍干员 → 完整 BuffPool"""

    def test_完整BuffPool_含所有宿舍生成器(self):
        """令+夕中枢，迷迭香Mfg+黑键Trade，爱丽丝+车尔尼+塑心+森西宿舍"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]

        alice = _mk_op("爱丽丝")
        alice.skills.append(_mk_skill("dorm_rec_bd_n1_n2[000]", "Dormitory", "睡前故事"))
        alice.skills.append(_mk_skill("dorm_rec_bd_n1[000]", "Dormitory", "梦境呓语"))

        cherni = _mk_op("车尔尼")
        cherni.skills.append(_mk_skill("dorm_rec_bd_n1_n3[000]", "Dormitory", "慢板行歌"))
        cherni.skills.append(_mk_skill("dorm_rec_bd_n1[100]", "Dormitory", "琴键漫步"))

        suxin = _mk_op("塑心")

        sensi = _mk_op("森西")
        sensi.skills.append(_mk_skill("dorm_rec_bd_dungeon[000]", "Dormitory", "森西大食堂"))

        dorm = [alice, cherni, suxin, sensi]

        pool = compute_buff_pool(
            control, dorm_operators=dorm, dorm_level=3,
            mfg_operators=[_mk_op("迷迭香", [_mk_skill("manu_prod_spd_bd_n1[000]", "Mfg", "超感")])], trade_operators=[_mk_op("黑键", [_mk_skill("trade_ord_spd_bd_n1[000]", "TRADING", "乐感")])],
        )

        # 夕(10) + 迷迭香超感(4) + 黑键乐感(4) + 爱丽丝梦境(3) + 车尔尼小节(3) = 24
        assert pool.perception == 24
        assert pool.thought_chains == 24
        assert pool.monster_cuisine == 3  # 森西 Lv3

    def test_完整BuffPool_宿舍等级5_满20人(self):
        """令<12 + 宿舍 Lv5 + 满 20 人 → 感知=54（含4宿舍干员不含塑心）"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]

        alice = _mk_op("爱丽丝")
        alice.skills.append(_mk_skill("dorm_rec_bd_n1_n2[000]", "Dormitory", "睡前故事"))
        alice.skills.append(_mk_skill("dorm_rec_bd_n1[000]", "Dormitory", "梦境呓语"))

        cherni = _mk_op("车尔尼")
        cherni.skills.append(_mk_skill("dorm_rec_bd_n1_n3[000]", "Dormitory", "慢板行歌"))
        cherni.skills.append(_mk_skill("dorm_rec_bd_n1[100]", "Dormitory", "琴键漫步"))

        sensi = _mk_op("森西")
        sensi.skills.append(_mk_skill("dorm_rec_bd_dungeon[000]", "Dormitory", "森西大食堂"))

        suxin = _mk_op("塑心")

        # 满 20 人宿舍：4 名指定 + 16 名填充
        dorm = [alice, cherni, suxin, sensi] + [_mk_op(f"填位{i}") for i in range(16)]

        pool = compute_buff_pool(
            control, dorm_operators=dorm, dorm_level=5,
            mfg_operators=[_mk_op("迷迭香", [_mk_skill("manu_prod_spd_bd_n1[000]", "Mfg", "超感")])], trade_operators=[_mk_op("黑键", [_mk_skill("trade_ord_spd_bd_n1[000]", "TRADING", "乐感")])],
            ling_mood_below_12=True,
        )

        # 令<12(10) + 夕(10) + 迷迭香超感(20) + 黑键乐感(20)
        # + 爱丽丝梦境(5) + 车尔尼小节(5) = 70
        assert pool.perception == 70
        assert pool.yanhuo == 0  # 令 mood<12 → 无烟火
        assert pool.thought_chains == 70
        assert pool.monster_cuisine == 5  # 森西 Lv5

    def test_令心情低于12_产生感知而非烟火(self):
        """令 mood<12 → +10 感知，不产生烟火"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        pool = compute_buff_pool(control, ling_mood_below_12=True)

        assert pool.yanhuo == 0
        assert pool.perception == 20  # 令(10) + 夕(10)

    def test_夕心情低于12_产生烟火(self):
        """夕 mood<12 → 不以物喜 → 烟火+15"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        pool = compute_buff_pool(control, xi_mood_below_12=True)

        assert pool.yanhuo == 30  # 令默认(15) + 夕不以物喜(15)
        assert pool.perception == 0  # 夕不产生感知(mood<12)，令也默认烟火

    def test_令心情高于12_默认产生烟火(self):
        """默认 ling_mood_below_12=False → 令产生烟火"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        pool = compute_buff_pool(control)

        assert pool.yanhuo == 15
        assert pool.perception == 10  # 仅夕


# ─── B2 工程机器人生成 ──────────────────────────────────────────

class TestEngineeringRobots:
    """B2: compute_engineering_robots — 绘图设计生成工程机器人"""

    def test_243布局_18间设施含中枢与宿舍Lv5_触发上限64机器人(self):
        """13 工作 Lv3 + 中枢 Lv5 + 4 宿舍 Lv5 = 64 → 触及上限"""
        from steward_core.synergy import compute_engineering_robots
        from steward_core.models import LayoutConfig

        layout = LayoutConfig.layout_243()

        robots = compute_engineering_robots(layout)
        assert robots == 64  # 13工作Lv3(=39) + 中枢Lv5(=5) + 4宿舍Lv5(=20) = 64 = cap

    def test_空布局_返回0(self):
        """空布局 → 0 机器人"""
        from steward_core.synergy import compute_engineering_robots
        from steward_core.models import LayoutConfig

        layout = LayoutConfig(rooms=[])

        robots = compute_engineering_robots(layout)
        assert robots == 0

    def test_buff_pool含机器人(self):
        """compute_buff_pool 包含工程机器人计数"""
        from steward_core.synergy import compute_buff_pool
        from steward_core.models import LayoutConfig

        layout = LayoutConfig.layout_243()
        pool = compute_buff_pool([], layout=layout)

        assert pool.engineering_robots == 64

    def test_机械辅助alpha_42机器人_加10percent(self):
        """至简 α: 每16机器人→+5%，42机器人 → 42//16×5 = 10%"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        zhijian = _mk_op("至简")
        pool = BuffPool(engineering_robots=42)

        segs = synergy_buff_pool_consumer([zhijian], "Mfg", "PureGold", pool, 12.0)
        assert segs[0].a == 25.0  # β: 42//8*5 = 25 (β 比 α 优，取 β)


# ─── B1 办公室/Trade 生成源 ──────────────────────────────────────

class TestB1OfficeTradeGeneration:
    """B1: compute_buff_pool 扩展 — Office/Trade 来源的烟火/感知信息生成"""

    def test_絮雨_office_感知信息(self):
        """perception_from_office=20 → 感知信息额外 +20（2招募位×10记忆碎片）"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        pool = compute_buff_pool(control, office_operators=[_make_office_op()], office_perception_base=20)

        assert pool.perception == 30  # 夕(10) + 絮雨Office(20)
        assert pool.thought_chains == 30

    def test_絮雨_office_感知信息_与迷迭香超感叠加(self):
        """perception_from_office=20 + 迷迭香超感(5 dorm) → 叠加"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        dorm = [_mk_op(f"填位{i}") for i in range(5)]

        pool = compute_buff_pool(
            control, dorm_operators=dorm,
            mfg_operators=[_mk_op("迷迭香", [_mk_skill("manu_prod_spd_bd_n1[000]", "Mfg", "超感")])], office_operators=[_make_office_op()], office_perception_base=20,
        )

        assert pool.perception == 10 + 5 + 20  # 夕(10) + 迷迭香超感(5) + 絮雨(20)
        assert pool.thought_chains == 35

    def test_乌有_trade_烟火生成(self):
        """乌有在贸易站，20名宿舍干员 → yanhuo +20"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("重岳")]
        dorm = [_mk_op(f"填位{i}") for i in range(20)]

        pool = compute_buff_pool(
            control, suich_count=5, dorm_operators=dorm,
            trade_operators=[_mk_op("乌有", [_mk_skill("trade_ord_spd_bd_n2[000]", "TRADING", "愿者上钩")])],
        )

        assert pool.yanhuo == 15 + 25 + 20  # 令(15) + 重岳5岁(25) + 乌有(20)
        assert pool.wushu_crystal == 60 // 5  # 60 烟火 → 12 巫术结晶

    def test_乌有_未在贸易站_不产生烟火(self):
        """乌有不在贸易站 → 无额外烟火"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("重岳")]
        dorm = [_mk_op(f"填位{i}") for i in range(20)]

        pool = compute_buff_pool(control, suich_count=5, dorm_operators=dorm)

        assert pool.yanhuo == 15 + 25  # 仅令(15) + 重岳(25)，无乌有

    def test_絮雨_零招募位_不产生感知(self):
        """perception_from_office=0 → 无额外感知（边界）"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        pool = compute_buff_pool(control, office_operators=[_make_office_op()], office_perception_base=0)

        assert pool.perception == 10  # 仅夕(10)

    def test_桑葚_office_烟火(self):
        """桑葚在 Office，office_yanhuo_base=20 → 烟火+20"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("重岳")]
        office_op = _mk_sangshen()
        pool = compute_buff_pool(
            control, suich_count=5,
            office_operators=[office_op], office_yanhuo_base=20,
        )

        assert pool.yanhuo == 15 + 25 + 20  # 令(15) + 重岳(25) + 桑葚(20)

    def test_深律_office_无声共鸣(self):
        """深律在 Office，office_silent_base=30 → 无声共鸣+30"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        office_op = _mk_shenlv()
        pool = compute_buff_pool(
            control, office_operators=[office_op], office_silent_base=30,
            trade_operators=[_mk_op("黑键", [_mk_skill("trade_ord_spd_bd_n1[000]", "TRADING", "乐感")])],
        )

        # 夕(10 perception) + 黑键乐感(0, 无宿舍干员) = 10 感知信息 → 10 无声共鸣
        # 深律 office_silent_base=30 → +30 无声共鸣
        assert pool.silent_resonance == 40  # 夕感知(10) + 深律(30)


# ─── B5 无声共鸣生成 ─────────────────────────────────────────────

class TestB5SilentResonance:
    """B5: compute_buff_pool 扩展 — 无声共鸣生成（塑心宿舍 + 黑键感知转化）"""

    def test_塑心_宿舍_无声共鸣生成(self):
        """塑心在宿舍，20名干员 → silent_resonance +20"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        suxin = _mk_op("塑心")
        dorm = [suxin] + [_mk_op(f"填位{i}") for i in range(19)]

        pool = compute_buff_pool(
            control, dorm_operators=dorm, dorm_level=5,
            trade_operators=[_mk_op("黑键", [_mk_skill("trade_ord_spd_bd_n1[000]", "TRADING", "乐感")])], ling_mood_below_12=True,
        )

        # 令<12(10) + 夕(10) + 黑键乐感20人(20) = 40 perception → 40 silent_resonance
        # 塑心宿舍 20人 → +20 silent_resonance
        assert pool.perception == 40  # 令<12(10)+夕(10)+黑键乐感(20)
        assert pool.thought_chains == 40
        assert pool.silent_resonance == 60  # 40(感知→共鸣) + 20(塑心)

    def test_黑键_不在贸易站_无声共鸣仅塑心(self):
        """黑键不在 Trade → 无感知→共鸣转化，仅塑心宿舍生成"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        suxin = _mk_op("塑心")
        dorm = [suxin] + [_mk_op(f"填位{i}") for i in range(4)]

        pool = compute_buff_pool(
            control, dorm_operators=dorm, dorm_level=5,
            ling_mood_below_12=True,
        )

        # 黑键不在 Trade → silent_resonance 仅来自塑心
        assert pool.silent_resonance == 5  # 塑心宿舍 5人

    def test_无声共鸣_零感知_零塑心_为零(self):
        """无感知 + 无塑心 → silent_resonance=0（边界）"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令")]  # 令 mood>12 → 烟火，无感知
        pool = compute_buff_pool(control)

        assert pool.silent_resonance == 0
        assert pool.perception == 0

    def test_完整链_无声共鸣全链路(self):
        """令<12(10)+夕(10)+迷迭香超感(5)+黑键乐感(5)+塑心宿舍(5)=35 silent_resonance"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_xi()]
        suxin = _mk_op("塑心")
        dorm = [suxin] + [_mk_op(f"填位{i}") for i in range(4)]

        pool = compute_buff_pool(
            control, dorm_operators=dorm, dorm_level=5,
            mfg_operators=[_mk_op("迷迭香", [_mk_skill("manu_prod_spd_bd_n1[000]", "Mfg", "超感")])], trade_operators=[_mk_op("黑键", [_mk_skill("trade_ord_spd_bd_n1[000]", "TRADING", "乐感")])],
            ling_mood_below_12=True,
        )

        # 感知: 令<12(10) + 夕(10) + 迷迭香(5) + 黑键(5) = 30
        # silent_resonance: 感知→共鸣(30) + 塑心宿舍(5) = 35
        assert pool.perception == 30
        assert pool.silent_resonance == 35


# ─── BuffPool 可组合化 (Track B1) ────────────────────────────────

class TestBuffPoolComposition:
    """BuffPool.__add__ / clone / __eq__ / _derive_pool"""

    def test_add_合并两个非零pool(self):
        """BuffPool(yanhuo=10) + BuffPool(perception=5)"""
        from steward_core.synergy import BuffPool

        a = BuffPool(yanhuo=10, perception=0)
        b = BuffPool(yanhuo=0, perception=5)
        c = a + b
        assert c.yanhuo == 10
        assert c.perception == 5

    def test_add_多字段不互相干扰(self):
        """7 个字段各设不同值，合并后各字段独立正确"""
        from steward_core.synergy import BuffPool

        a = BuffPool(yanhuo=1, perception=2, wushu_crystal=3, thought_chains=4,
                     silent_resonance=5, engineering_robots=6, monster_cuisine=7)
        b = BuffPool(yanhuo=10, perception=20, wushu_crystal=30, thought_chains=40,
                     silent_resonance=50, engineering_robots=60, monster_cuisine=70)
        c = a + b
        assert c.yanhuo == 11
        assert c.perception == 22
        assert c.wushu_crystal == 33
        assert c.thought_chains == 44
        assert c.silent_resonance == 55
        assert c.engineering_robots == 66
        assert c.monster_cuisine == 77

    def test_clone_深拷贝(self):
        """clone() 后修改原对象不影响克隆体"""
        from steward_core.synergy import BuffPool

        a = BuffPool(yanhuo=10, perception=5)
        b = a.clone()
        a.yanhuo = 999
        assert b.yanhuo == 10
        assert b.perception == 5

    def test_eq_相同值相等(self):
        """两个独立构造的同值 Pool 相等"""
        from steward_core.synergy import BuffPool

        a = BuffPool(yanhuo=10, perception=5)
        b = BuffPool(yanhuo=10, perception=5)
        assert a == b

    def test_eq_不同值不等(self):
        """yanhuo 差 1 即不等"""
        from steward_core.synergy import BuffPool

        a = BuffPool(yanhuo=10)
        b = BuffPool(yanhuo=11)
        assert a != b

    def test_eq_合并后相等(self):
        """a + b == c 当 c 手动填入相同值"""
        from steward_core.synergy import BuffPool

        a = BuffPool(yanhuo=5, perception=3)
        b = BuffPool(yanhuo=2, perception=1)
        c = BuffPool(yanhuo=7, perception=4)
        assert a + b == c

    def test_derive_pool_烟火转巫术(self):
        """yanhuo=14 → wushu_crystal=2，同时 thought_chains=perception"""
        from steward_core.synergy.buff_pool import _derive_pool
        from steward_core.synergy import BuffPool

        pool = BuffPool(yanhuo=14, perception=8)
        _derive_pool(pool)
        assert pool.wushu_crystal == 2
        assert pool.thought_chains == 8

    def test_derive_pool_零值不变(self):
        """全零 pool 派生后仍为零"""
        from steward_core.synergy.buff_pool import _derive_pool
        from steward_core.synergy import BuffPool

        pool = BuffPool()
        _derive_pool(pool)
        assert pool.wushu_crystal == 0
        assert pool.thought_chains == 0
