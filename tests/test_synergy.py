"""联动函数单元测试 (synergy.py)

全部测试通过内存构造 Operator 和 Skill，不依赖磁盘文件。
遵循 TDD 3A 模式 (Arrange → Act → Assert)。
"""

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


# ─── A1 干员配对 ─────────────────────────────────────────────────

class TestSynergyPair:
    """A1: synergy_pair — 识别同房间干员配对"""

    def test_酒神_Christine_配对触发(self):
        """Miss.Christine + 酒神 同制造站 → 作战记录+30%"""
        from steward_core.synergy import synergy_pair

        # Arrange
        christine = _mk_op("Miss.Christine", group_id="chr")
        wine = _mk_op("酒神", group_id="wine")
        filler = _mk_op("填位")

        # Act
        segs = synergy_pair([christine, wine, filler], "Mfg", "CombatRecord", 12.0)

        # Assert: 应输出一个 +30% 的常数段
        assert len(segs) == 1
        assert segs[0].a == 30.0
        assert segs[0].b == 0.0

    def test_配对不满足_不输出(self):
        """只有酒神没有 Christine → 不触发"""
        from steward_core.synergy import synergy_pair

        # Arrange
        wine = _mk_op("酒神")
        filler1 = _mk_op("A")
        filler2 = _mk_op("B")

        # Act
        segs = synergy_pair([wine, filler1, filler2], "Mfg", "CombatRecord", 12.0)

        # Assert
        assert segs == []

    def test_阿兰娜_温米_贵金属配对(self):
        """阿兰娜 + 温米 同制造站 → 贵金属+15%"""
        from steward_core.synergy import synergy_pair

        # Arrange
        alana = _mk_op("阿兰娜")
        wenmi = _mk_op("温米")
        filler = _mk_op("填位")

        # Act
        segs = synergy_pair([alana, wenmi, filler], "Mfg", "PureGold", 12.0)

        # Assert
        assert len(segs) == 1
        assert segs[0].a == 15.0

    def test_产物不匹配_不触发(self):
        """阿兰娜+温米配对仅在贵金属下触发，作战记录下不应触发"""
        from steward_core.synergy import synergy_pair

        # Arrange
        alana = _mk_op("阿兰娜")
        wenmi = _mk_op("温米")
        filler = _mk_op("填位")

        # Act
        segs = synergy_pair([alana, wenmi, filler], "Mfg", "CombatRecord", 12.0)

        # Assert
        assert segs == []


# ─── A3 技能类型计数 ─────────────────────────────────────────────

class TestSynergySkillCount:
    """A3: synergy_skill_count — 统计同房间技能类型"""

    def test_水月_两个标准化提供者_加10(self):
        """水月(标准化计数) + 2个标准化干员 → +10%"""
        from steward_core.synergy import synergy_skill_count, synergy_skill_alias

        # Arrange: 水月(计数锚点) + 杰西卡(标准化) + 调香师(标准化)
        shuiyue = _mk_op("水月")
        jessica = _mk_op("杰西卡")
        perfumer = _mk_op("调香师")

        # 标准化类技能通过 buff_name 识别
        jessica.skills.append(_mk_skill("sk1", "Mfg", "标准化·α"))
        perfumer.skills.append(_mk_skill("sk2", "Mfg", "标准化·β"))

        # Act
        alias = synergy_skill_alias([shuiyue, jessica, perfumer])
        segs = synergy_skill_count([shuiyue, jessica, perfumer], "Mfg", alias, 12.0)

        # Assert: 2个标准化提供者 + 水月自身 → 但水月不算提供者(他是计数者)
        # 实际上计数逻辑: 统计同房标准化技能数，水月自身无标准化技能
        # 杰西卡1 + 调香师1 = 2 个标准化 → 水月 +2×5% = +10%
        assert len(segs) == 1
        assert segs[0].a == 10.0

    def test_无技能计数锚点_不输出(self):
        """房间没有水月/多萝西/苍苔 → 不输出任何加成"""
        from steward_core.synergy import synergy_skill_count, synergy_skill_alias

        # Arrange: 三个普通干员，无锚点
        ops = [_mk_op("A"), _mk_op("B"), _mk_op("C")]
        alias = synergy_skill_alias(ops)

        # Act
        segs = synergy_skill_count(ops, "Mfg", alias, 12.0)

        # Assert
        assert segs == []

    def test_多萝西_三个莱茵科技提供者_加15(self):
        """多萝西(莱茵科技计数) + 3个莱茵干员 → +15%"""
        from steward_core.synergy import synergy_skill_count, synergy_skill_alias

        # Arrange
        dorothy = _mk_op("多萝西")
        silence = _mk_op("白面鸮")
        nastici = _mk_op("娜斯提")
        star = _mk_op("星源")

        silence.skills.append(_mk_skill("s1", "Mfg", "莱茵科技·α"))
        nastici.skills.append(_mk_skill("s2", "Mfg", "莱茵科技·β"))
        star.skills.append(_mk_skill("s3", "Mfg", "莱茵科技·γ"))

        ops = [dorothy, silence, nastici, star]
        alias = synergy_skill_alias(ops)

        # Act
        segs = synergy_skill_count(ops, "Mfg", alias, 12.0)

        # Assert: 3个莱茵科技 → 多萝西 +3×5% = +15%
        assert len(segs) == 1
        assert segs[0].a == 15.0

    def test_苍苔_计数含自身金属工艺技能(self):
        """苍苔(金属工艺计数) + 自身金属工艺·α + 2个金属工艺干员 → +15%"""
        from steward_core.synergy import synergy_skill_count, synergy_skill_alias

        # Arrange: 苍苔自身持有金属工艺·α（打工心得应含自身）
        cangtai = _mk_op("苍苔")
        cangtai.skills.append(_mk_skill("sk_self", "Mfg", "金属工艺·α"))
        yinxing = _mk_op("引星棘刺")
        yinxing.skills.append(_mk_skill("sk1", "Mfg", "金属工艺·α"))
        li = _mk_op("砾")
        li.skills.append(_mk_skill("sk2", "Mfg", "金属工艺·β"))

        ops = [cangtai, yinxing, li]
        alias = synergy_skill_alias(ops)

        # Act
        segs = synergy_skill_count(ops, "Mfg", alias, 12.0)

        # Assert: 苍苔 + 引星棘刺 + 砾 = 3 × 5% = 15%
        assert len(segs) == 1
        assert segs[0].a == 15.0


# ─── A4 技能类型别名 ─────────────────────────────────────────────

class TestSynergySkillAlias:
    """A4: synergy_skill_alias — 技能类型视作别名"""

    def test_海沫在场_莱茵科技视作标准化(self):
        """海沫的意识兼容将莱茵→标准化"""
        from steward_core.synergy import synergy_skill_alias

        # Arrange
        haimo = _mk_op("海沫")
        filler = _mk_op("填位")

        # Act
        alias = synergy_skill_alias([haimo, filler])

        # Assert
        assert "莱茵科技" in alias
        assert "标准化" in alias.get("莱茵科技", [])

    def test_无海沫_无别名(self):
        """无海沫时别名映射为空"""
        from steward_core.synergy import synergy_skill_alias

        # Arrange
        ops = [_mk_op("A"), _mk_op("B")]

        # Act
        alias = synergy_skill_alias(ops)

        # Assert
        assert alias == {}

    def test_别名生效_水月计数含莱茵科技(self):
        """海沫在场 → 莱茵科技也视作标准化 → 水月能多计数"""
        from steward_core.synergy import synergy_skill_count, synergy_skill_alias

        # Arrange: 水月 + 海沫(别名) + 白面鸮(莱茵科技)
        # 海沫触发别名 → 白面鸮的莱茵科技也视为标准化
        # 水月计数: 白面鸮(莱茵→标准化) = 1 → +5%
        shuiyue = _mk_op("水月")
        haimo = _mk_op("海沫")
        silence = _mk_op("白面鸮")
        silence.skills.append(_mk_skill("s1", "Mfg", "莱茵科技·α"))

        ops = [shuiyue, haimo, silence]
        alias = synergy_skill_alias(ops)

        # Act
        segs = synergy_skill_count(ops, "Mfg", alias, 12.0)

        # Assert: 白面鸮被别名视为标准化 → 水月 +1×5%
        assert len(segs) == 1
        assert segs[0].a == 5.0


# ─── A5 自动化 ───────────────────────────────────────────────────

class TestSynergyAutomation:
    """A5: synergy_automation — 其他归零+发电站加成"""

    def test_温蒂自动化_归零他人_3发电站(self):
        """温蒂(仿生海龙) → 其他2人归零，自身+45%(3站×15%)"""
        from steward_core.synergy import synergy_automation

        # Arrange
        wenti = _mk_op("温蒂")
        filler1 = _mk_op("A")
        filler2 = _mk_op("B")

        # Act
        segs, zero_set = synergy_automation([wenti, filler1, filler2], "Mfg", power_count=3, T=12.0)

        # Assert
        assert len(segs) == 1
        assert segs[0].a == 45.0  # 3×15%
        assert "A" in zero_set
        assert "B" in zero_set
        assert "温蒂" not in zero_set

    def test_森蚺持有α和β_取最高版本(self):
        """森蚺同时持有 automation[000](α/5%) 和 [010](β/10%) → 应取 β(10%/站)"""
        from steward_core.synergy import synergy_automation

        # Arrange: 森蚺 skills 含两个 automation buff
        senran = _mk_op("森蚺")
        senran.skills.append(_mk_skill("manu_prod_spd&power[000]", "Mfg", "自动化·α"))
        senran.skills.append(_mk_skill("manu_prod_spd&power[010]", "Mfg", "自动化·β"))
        filler1 = _mk_op("A")
        filler2 = _mk_op("B")

        # Act
        segs, zero_set = synergy_automation([senran, filler1, filler2], "Mfg", power_count=3, T=12.0)

        # Assert: 3 发电站 × 10%(β) = 30%
        assert len(segs) == 1
        assert segs[0].a == 30.0  # 不是 15.0 (α)

    def test_掠风仅有α_取5percent(self):
        """掠风仅持有 automation[000](α) → 应取 5%/站"""
        from steward_core.synergy import synergy_automation

        # Arrange
        luefeng = _mk_op("掠风")
        luefeng.skills.append(_mk_skill("manu_prod_spd&power[000]", "Mfg", "自动化·α"))
        filler1 = _mk_op("A")
        filler2 = _mk_op("B")

        # Act
        segs, zero_set = synergy_automation([luefeng, filler1, filler2], "Mfg", power_count=3, T=12.0)

        # Assert: 3 发电站 × 5%(α) = 15%
        assert len(segs) == 1
        assert segs[0].a == 15.0

    def test_自动化不触发_普通房间(self):
        """无自动化干员 → 返回空"""
        from steward_core.synergy import synergy_automation

        # Arrange
        ops = [_mk_op("A"), _mk_op("B"), _mk_op("C")]

        # Act
        segs, zero_set = synergy_automation(ops, "Mfg", power_count=3, T=12.0)

        # Assert
        assert segs == []
        assert zero_set == set()


# ─── A6 设施数量联动 ─────────────────────────────────────────────

class TestSynergyFacilityCount:
    """A6: synergy_facility_count — 根据全基建设施数量计算加成"""

    def test_清流_每个贸易站加20贵金属(self):
        """清流在 Mfg PureGold，2 个贸易站 → +40%"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig, RoomConfig

        # Arrange
        qingliu = _mk_op("清流")
        layout = LayoutConfig(rooms=[
            RoomConfig("Trade", 0, 3, "Money"),
            RoomConfig("Trade", 1, 3, "Money"),
        ])

        # Act
        segs = synergy_facility_count([qingliu], "Mfg", "PureGold", layout, T=12.0)

        # Assert: +40% 常数段
        assert len(segs) == 1
        assert segs[0].a == 40.0

    def test_清流_非贵金属产物_不触发(self):
        """清流在 CombatRecord → 不应触发（仅贵金属）"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig, RoomConfig

        # Arrange
        qingliu = _mk_op("清流")
        layout = LayoutConfig(rooms=[
            RoomConfig("Trade", 0, 3, "Money"),
            RoomConfig("Trade", 1, 3, "Money"),
        ])

        # Act
        segs = synergy_facility_count([qingliu], "Mfg", "CombatRecord", layout, T=12.0)

        # Assert
        assert segs == []

    def test_空弦_每宿舍等级加2贸易(self):
        """空弦 (β) 在 Trade，4 间宿舍 × Lv5 → +40%"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig

        # Arrange
        kongxian = _mk_op("空弦")
        layout = LayoutConfig(rooms=[])

        # Act: dorm_levels 默认 20 (4×Lv5)
        segs = synergy_facility_count([kongxian], "Trade", "Money", layout, T=12.0)

        # Assert: +40%
        assert len(segs) == 1
        assert segs[0].a == 40.0

    def test_伺夜_每会客室等级加5_上限40(self):
        """伺夜在 Trade，Meeting Lv3 → +15%（未触上限）"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig, RoomConfig

        # Arrange
        siye = _mk_op("伺夜")
        layout = LayoutConfig(rooms=[
            RoomConfig("Reception", 0, 2, "General"),
        ])

        # Act: 1间 Reception × Lv3 = 3 × 5% = 15%
        segs = synergy_facility_count([siye], "Trade", "Money", layout, T=12.0)

        # Assert
        assert len(segs) == 1
        assert segs[0].a == 15.0

    def test_伺夜_高会客室触发上限(self):
        """伺夜在 Trade，Meeting Lv9 → 45% → clamp 到 40%"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig, RoomConfig

        # Arrange
        siye = _mk_op("伺夜")
        layout = LayoutConfig(rooms=[
            RoomConfig("Reception", 0, 2, "General"),
            RoomConfig("Reception", 1, 2, "General"),
            RoomConfig("Reception", 2, 2, "General"),
        ])

        # Act: 3间 Meeting × Lv3 = 9 × 5% = 45% → clamp to 40%
        segs = synergy_facility_count([siye], "Trade", "Money", layout, T=12.0)

        # Assert
        assert segs[0].a == 40.0

    def test_石英_每配方类型加2贸易(self):
        """石英在 Trade，制造站 2 种配方 → +4%"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig, RoomConfig

        # Arrange
        shiying = _mk_op("石英")
        layout = LayoutConfig(rooms=[
            RoomConfig("Mfg", 0, 3, "CombatRecord"),
            RoomConfig("Mfg", 1, 3, "PureGold"),
        ])

        # Act: 2 种配方类型 × 2% = 4%
        segs = synergy_facility_count([shiying], "Trade", "Money", layout, T=12.0)

        # Assert
        assert len(segs) == 1
        assert segs[0].a == 4.0

    def test_无A6干员_返回空(self):
        """房间内无 A6 干员 → 空列表"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig

        # Arrange
        filler = _mk_op("填位")
        layout = LayoutConfig(rooms=[])

        # Act
        segs = synergy_facility_count([filler], "Mfg", "PureGold", layout, T=12.0)

        # Assert
        assert segs == []

    def test_娜仁图亚_赤金加宿舍等级(self):
        """娜仁图亚在 Mfg PureGold，20 宿舍等级 → +20%"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig

        # Arrange
        narentuya = _mk_op("娜仁图亚")
        layout = LayoutConfig(rooms=[])

        # Act: dorm_levels 默认 20 (4×Lv5)
        segs = synergy_facility_count([narentuya], "Mfg", "PureGold", layout, T=12.0)

        # Assert: +20%
        assert len(segs) == 1
        assert segs[0].a == 20.0


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

        control = [_mk_op("令"), _mk_op("重岳"), _mk_op("夕")]
        pool = compute_buff_pool(control, suich_count=5)

        assert pool.yanhuo == 40
        assert pool.perception == 10
        assert pool.thought_chains == 10  # 1:1
        assert pool.wushu_crystal == 8   # 40//5

    def test_c2_global_burn_固定中枢(self):
        """C2: 3人工位 burn = 0.75 - 中枢减免(5×0.05) - 重岳孤光共照(0.05)"""
        from steward_core.synergy import compute_global_burn, compute_buff_pool

        control = [_mk_op("令"), _mk_op("重岳"), _mk_op("夕"), _mk_op("凯尔希"), _mk_op("焰尾")]
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

        control = [_mk_op("令"), _mk_op("重岳"), _mk_op("夕"), _mk_op("凯尔希"), _mk_op("焰尾")]
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


# ─── 旧 C1 测试续（已在 TestControlGlobalBonus 类中） ────────────

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


# ─── B1 宿舍感知信息生成器 ────────────────────────────────────────

class TestDormPerception:
    """B1: compute_buff_pool 扩展 — 宿舍干员生成感知信息"""

    def test_迷迭香超感_宿舍每有干员_感知加一(self):
        """迷迭香在制造站，4名宿舍干员 → +4 感知信息"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("夕")]
        dorm = [_mk_op("填位A"), _mk_op("填位B"), _mk_op("填位C"), _mk_op("填位D")]

        pool = compute_buff_pool(control, dorm_operators=dorm,
                                 has_rosmontis_in_mfg=True)

        assert pool.perception == 10 + 4  # 夕(10) + 迷迭香超感(4)
        assert pool.thought_chains == 14

    def test_黑键乐感_宿舍每有干员_感知加一(self):
        """黑键在贸易站，4名宿舍干员 → +4 感知信息"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("夕")]
        dorm = [_mk_op("A"), _mk_op("B"), _mk_op("C"), _mk_op("D")]

        pool = compute_buff_pool(control, dorm_operators=dorm,
                                 has_ebnhlz_in_trade=True)

        assert pool.perception == 10 + 4  # 夕(10) + 黑键乐感(4)
        assert pool.thought_chains == 14

    def test_迷迭香和黑键同时在场_感知叠加(self):
        """迷迭香在Mfg + 黑键在Trade → 各贡献宿舍数量感知"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("夕")]
        dorm = [_mk_op("A"), _mk_op("B"), _mk_op("C"), _mk_op("D")]

        pool = compute_buff_pool(control, dorm_operators=dorm,
                                 has_rosmontis_in_mfg=True,
                                 has_ebnhlz_in_trade=True)

        assert pool.perception == 10 + 4 + 4  # 夕(10) + 迷迭香(4) + 黑键(4)
        assert pool.thought_chains == 18

    def test_爱丽丝梦境呓语_宿舍等级转感知(self):
        """爱丽丝在宿舍 Lv3 → 3梦境 → +3 感知信息"""
        from steward_core.synergy import compute_buff_pool

        alice = _mk_op("爱丽丝")
        alice.skills.append(_mk_skill("dorm_rec_bd_n1_n2[000]", "Dormitory", "睡前故事"))
        alice.skills.append(_mk_skill("dorm_rec_bd_n1[000]", "Dormitory", "梦境呓语"))

        control = [_mk_op("夕")]  # 仅夕提供10感知
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

        control = [_mk_op("夕")]
        dorm = [cherni]

        pool = compute_buff_pool(control, dorm_operators=dorm, dorm_level=3)

        assert pool.perception == 10 + 3  # 夕(10) + 车尔尼小节(3)

    def test_无宿舍干员_无额外感知(self):
        """空宿舍 → 仅中枢生成感知"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("夕")]
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

        control = [_mk_op("令"), _mk_op("夕")]
        dorm = [sensi]

        pool = compute_buff_pool(control, dorm_operators=dorm, dorm_level=3)

        assert pool.monster_cuisine == 3

    def test_无森西_无魔物料理(self):
        """无森西在宿舍 → monster_cuisine = 0"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("夕")]
        dorm = [_mk_op("填位")]

        pool = compute_buff_pool(control, dorm_operators=dorm)

        assert pool.monster_cuisine == 0


# ─── 完整 BuffPool 集成测试 ────────────────────────────────────────

class TestFullBuffPool:
    """集成：控制中枢 + 宿舍干员 → 完整 BuffPool"""

    def test_完整BuffPool_含所有宿舍生成器(self):
        """令+夕中枢，迷迭香Mfg+黑键Trade，爱丽丝+车尔尼+塑心+森西宿舍"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("夕")]

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
            has_rosmontis_in_mfg=True, has_ebnhlz_in_trade=True,
        )

        # 夕(10) + 迷迭香超感(4) + 黑键乐感(4) + 爱丽丝梦境(3) + 车尔尼小节(3) = 24
        assert pool.perception == 24
        assert pool.thought_chains == 24
        assert pool.monster_cuisine == 3  # 森西 Lv3

    def test_完整BuffPool_宿舍等级5_满20人(self):
        """令<12 + 宿舍 Lv5 + 满 20 人 → 感知=54（含4宿舍干员不含塑心）"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("夕")]

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
            has_rosmontis_in_mfg=True, has_ebnhlz_in_trade=True,
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

        control = [_mk_op("令"), _mk_op("夕")]
        pool = compute_buff_pool(control, ling_mood_below_12=True)

        assert pool.yanhuo == 0
        assert pool.perception == 20  # 令(10) + 夕(10)

    def test_令心情高于12_默认产生烟火(self):
        """默认 ling_mood_below_12=False → 令产生烟火"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("夕")]
        pool = compute_buff_pool(control)

        assert pool.yanhuo == 15
        assert pool.perception == 10  # 仅夕


# ─── A2 阵营计数（同房） ──────────────────────────────────────────

class TestSynergyFactionRoom:
    """A2: synergy_faction_room — 同房间阵营干员计数"""

    def test_重聚时光_A1小队两名干员_加20(self):
        """历阵锐枪芬在 Mfg，房间含 2 名 A1小队(reserve1)干员 → +20%"""
        from steward_core.synergy import synergy_faction_room

        fen2 = _mk_op("历阵锐枪芬")
        fen = _mk_op("芬", team_id="reserve1")
        melantha = _mk_op("玫兰莎", team_id="reserve1")

        segs = synergy_faction_room([fen2, fen, melantha], "Mfg", "PureGold", 12.0)

        assert len(segs) == 1
        assert segs[0].a == 20.0  # 2人 × 10%

    def test_重聚时光_无A1小队_不加成(self):
        """历阵锐枪芬在 Mfg，但房间无 A1小队干员 → 空"""
        from steward_core.synergy import synergy_faction_room

        fen2 = _mk_op("历阵锐枪芬")
        other = _mk_op("其他")

        segs = synergy_faction_room([fen2, other], "Mfg", "PureGold", 12.0)

        assert segs == []

    def test_重聚时光_非Mfg房间_不触发(self):
        """历阵锐枪芬在 Trade → 不触发阵营计数"""
        from steward_core.synergy import synergy_faction_room

        fen2 = _mk_op("历阵锐枪芬")
        fen = _mk_op("芬", team_id="reserve1")

        segs = synergy_faction_room([fen2, fen], "Trade", "Money", 12.0)

        assert segs == []

    def test_无A2干员_返回空(self):
        """房间无 A2 锚点干员 → 空列表"""
        from steward_core.synergy import synergy_faction_room

        a = _mk_op("填位A")
        b = _mk_op("填位B", team_id="reserve1")

        segs = synergy_faction_room([a, b], "Mfg", "PureGold", 12.0)

        assert segs == []


# ─── A6 扩展：手艺人 ───────────────────────────────────────────────

class TestTrainingRoomA6:
    """A6 扩展: synergy_facility_count — 训练室等级联动"""

    def test_手艺人_训练室Lv3_加30percent(self):
        """维伊在 Mfg，1间 Lv3 训练室 → +30%"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig, RoomConfig

        weiyi = _mk_op("维伊")
        layout = LayoutConfig(rooms=[
            RoomConfig("Training", 0, 1),
        ])

        segs = synergy_facility_count([weiyi], "Mfg", "PureGold", layout, T=12.0)
        assert len(segs) == 1
        assert segs[0].a == 30.0  # 3级 × 10% = 30%

    def test_手艺人_触发上限30(self):
        """维伊在 Mfg，2间 Lv3 训练室 → 受上限 30% 限制"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig, RoomConfig

        weiyi = _mk_op("维伊")
        layout = LayoutConfig(rooms=[
            RoomConfig("Training", 0, 1),
            RoomConfig("Training", 1, 1),
        ])

        segs = synergy_facility_count([weiyi], "Mfg", "PureGold", layout, T=12.0)
        assert len(segs) == 1
        assert segs[0].a == 30.0  # 6级 × 10% = 60% → clamp 30%


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


# ─── 爬升型效率 ────────────────────────────────────────────────────

class TestRampingOperator:
    """爬升型效率技能: operator_ramp_segments → ramping_efficiency"""

    def test_例行清扫_阿罗玛_返回爬升段(self):
        """阿罗玛持有 例行清扫(0→20%@2%/h) → 爬升段(0→10h ramp + 10→12h 常数20%)"""
        from steward_core.synergy import operator_ramp_segments

        aluoma = _mk_op("阿罗玛")
        aluoma.skills.append(_mk_skill(
            "manu_prod_spd_addition[100]", "Mfg", "例行清扫", {"all": 0.0},
        ))

        segs = operator_ramp_segments(aluoma, "Mfg", "PureGold", T=12.0)
        assert segs is not None
        assert len(segs) == 2
        assert segs[0].a == 0.0 and segs[0].b == 2.0  # ramp
        assert segs[1].a == 20.0 and segs[1].b == 0.0  # saturated

    def test_非爬升技能干员_返回None(self):
        """普通干员无爬升技能 → None"""
        from steward_core.synergy import operator_ramp_segments

        op = _mk_op("普通")
        op.skills.append(_mk_skill("manu_prod_spd[001]", "Mfg", "普通技能", {"all": 25.0}))

        segs = operator_ramp_segments(op, "Mfg", "PureGold", T=12.0)
        assert segs is None

    def test_例行清扫_非Mfg房间_返回None(self):
        """例行清扫技能在 Trade 房间不适用 → 返回 None（函数按 room_type 过滤）"""
        from steward_core.synergy import operator_ramp_segments

        aluoma = _mk_op("阿罗玛")
        aluoma.skills.append(_mk_skill(
            "manu_prod_spd_addition[100]", "Mfg", "例行清扫", {"all": 0.0},
        ))

        segs = operator_ramp_segments(aluoma, "Trade", "Money", T=12.0)
        assert segs is None


# ─── 仓库容量→效率 ──────────────────────────────────────────────────

class TestCapacityToEff:
    """容量→效率转换: synergy_capacity_to_eff — 红云/泡泡"""

    def test_回收利用_总容量16_效率加32(self):
        """红云在场，房间内容量总和 16 → 16×2% = 32%"""
        from steward_core.synergy import synergy_capacity_to_eff

        hongyun = _mk_op("红云")
        op1 = _mk_op("拾荒者")
        op1.skills.append(_mk_skill("m_limit", "Mfg", "拾荒者", {"all": 0.0}, capacity=8))
        op2 = _mk_op("囤积者")
        op2.skills.append(_mk_skill("m_limit2", "Mfg", "囤积者", {"all": 0.0}, capacity=8))

        segs = synergy_capacity_to_eff([hongyun, op1, op2], "Mfg", "PureGold", 12.0)
        assert len(segs) == 1
        assert segs[0].a == 32.0

    def test_回收利用_无红云_返回空(self):
        """房间无红云/泡泡 → 容量不转化效率"""
        from steward_core.synergy import synergy_capacity_to_eff

        op1 = _mk_op("拾荒者")
        op1.skills.append(_mk_skill("m_limit", "Mfg", "拾荒者", {"all": 0.0}, capacity=8))

        segs = synergy_capacity_to_eff([op1], "Mfg", "PureGold", 12.0)
        assert segs == []

    def test_大就是好_小于16格_每格1percent(self):
        """泡泡在场，总容量 10 → 10×1% = 10%"""
        from steward_core.synergy import synergy_capacity_to_eff

        paopao = _mk_op("泡泡")
        op1 = _mk_op("拾荒者")
        op1.skills.append(_mk_skill("m_limit", "Mfg", "拾荒者", {"all": 0.0}, capacity=10))

        segs = synergy_capacity_to_eff([paopao, op1], "Mfg", "PureGold", 12.0)
        assert len(segs) == 1
        assert segs[0].a == 10.0

    def test_大就是好_超过16格_分段费率(self):
        """泡泡在场，总容量 20 → 16×1% + 4×3% = 28%"""
        from steward_core.synergy import synergy_capacity_to_eff

        paopao = _mk_op("泡泡")
        op1 = _mk_op("探险者")
        op1.skills.append(_mk_skill("m_limit", "Mfg", "探险者", {"all": 0.0}, capacity=20))

        segs = synergy_capacity_to_eff([paopao, op1], "Mfg", "PureGold", 12.0)
        assert len(segs) == 1
        assert segs[0].a == 28.0  # 16×1 + 4×3

    def test_泡泡和红云同时在场_仅泡泡生效(self):
        """泡泡/红云共存 → 大就是好！优先，回收利用被屏蔽"""
        from steward_core.synergy import synergy_capacity_to_eff

        paopao = _mk_op("泡泡")
        hongyun = _mk_op("红云")
        op1 = _mk_op("拾荒者")
        op1.skills.append(_mk_skill("m_limit", "Mfg", "拾荒者", {"all": 0.0}, capacity=8))

        segs = synergy_capacity_to_eff([paopao, hongyun, op1], "Mfg", "PureGold", 12.0)
        assert len(segs) == 1
        assert segs[0].a == 8.0  # 泡泡费率 8×1%，非红云 8×2%


# ─── 配合意识 ──────────────────────────────────────────────────────

class TestAmplifier:
    """效率放大器: synergy_efficiency_amplifier — 槐琥"""

    def test_配合意识_他人提供30percent_额外加30(self):
        """槐琥在场，其他干员效率总和 30% → 30/5×5 = 30%，上限 40% → 30%"""
        from steward_core.synergy import synergy_efficiency_amplifier

        huaigu = _mk_op("槐琥")
        op1 = _mk_op("高效果")
        op1.skills.append(_mk_skill("m_eff", "Mfg", "高效", {"all": 25.0}))
        op2 = _mk_op("中效果")
        op2.skills.append(_mk_skill("m_eff2", "Mfg", "中效", {"all": 5.0}))

        segs = synergy_efficiency_amplifier([huaigu, op1, op2], "Mfg", "PureGold", 12.0)
        assert len(segs) == 1
        assert segs[0].a == 30.0  # (25+5)//5 × 5

    def test_配合意识_触发上限40(self):
        """他人效率 50% → 50/5×5=50 → clamp 40%"""
        from steward_core.synergy import synergy_efficiency_amplifier

        huaigu = _mk_op("槐琥")
        op1 = _mk_op("超高效")
        op1.skills.append(_mk_skill("m_eff", "Mfg", "超高效", {"all": 50.0}))

        segs = synergy_efficiency_amplifier([huaigu, op1], "Mfg", "PureGold", 12.0)
        assert len(segs) == 1
        assert segs[0].a == 40.0

    def test_配合意识_无槐琥_返回空(self):
        """房间无槐琥 → 空"""
        from steward_core.synergy import synergy_efficiency_amplifier

        op1 = _mk_op("高效")
        op1.skills.append(_mk_skill("m_eff", "Mfg", "高效", {"all": 25.0}))

        segs = synergy_efficiency_amplifier([op1], "Mfg", "PureGold", 12.0)
        assert segs == []


# ─── 归零变体 ──────────────────────────────────────────────────────

class TestZeroingVariant:
    """归零变体: synergy_zeroing_variant — 科学改造/流程优化"""

    def test_科学改造_归零他人_补偿容量(self):
        """科学改造：归零他人效率，每干员+5容量。效率加成由 capacity_to_eff 计算"""
        from steward_core.synergy import synergy_zeroing_variant

        holder = _mk_op("科学改造干员")
        holder.skills.append(_mk_skill("manu_prod_spd&manu[000]", "Mfg", "科学改造", {"all": 0.0}))

        other = _mk_op("其他人")

        segs, zero = synergy_zeroing_variant([holder, other], "Mfg", "PureGold", 12.0)
        assert len(segs) == 0  # 无效率加成，纯补偿容量
        assert zero == {"其他人"}

    def test_流程优化_归零他人_补偿效率(self):
        """流程优化：归零他人效率，每干员+10%效率"""
        from steward_core.synergy import synergy_zeroing_variant

        holder = _mk_op("流程优化干员")
        holder.skills.append(_mk_skill("manu_prod_spd&manu[100]", "Mfg", "流程优化", {"all": 0.0}))

        other = _mk_op("其他人")

        segs, zero = synergy_zeroing_variant([holder, other], "Mfg", "PureGold", 12.0)
        assert len(segs) == 1
        assert segs[0].a == 20.0  # 2人(含持有者) × 10%
        assert zero == {"其他人"}

    def test_无归零变体_返回空(self):
        """普通房间 → 空"""
        from steward_core.synergy import synergy_zeroing_variant

        op1 = _mk_op("普通A")
        op2 = _mk_op("普通B")

        segs, zero = synergy_zeroing_variant([op1, op2], "Mfg", "PureGold", 12.0)
        assert segs == []
        assert zero == set()


# ─── 机械精通（作业平台） ────────────────────────────────────────────

class TestTokenProd:
    """作业平台联动: synergy_token_prod — 机械精通α/β"""

    def test_机械精通α_2台作业平台_贵金属加10(self):
        """阿兰娜机械精通α: 2台作业平台在发电站 → +10%"""
        from steward_core.synergy import synergy_token_prod

        alanna = _mk_op("阿兰娜")
        alanna.skills.append(_mk_skill("manu_token_prod_spd[000]", "Mfg", "机械精通·α", {"all": 0.0}))

        platforms = {"Lancet-2": True, "Castle-3": True}

        segs = synergy_token_prod([alanna], "Mfg", "PureGold", platforms, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 10.0

    def test_机械精通α_贵金属专属_作战记录不触发(self):
        """α仅在贵金属配方生效"""
        from steward_core.synergy import synergy_token_prod

        alanna = _mk_op("阿兰娜")
        alanna.skills.append(_mk_skill("manu_token_prod_spd[000]", "Mfg", "机械精通·α", {"all": 0.0}))

        platforms = {"Lancet-2": True}

        segs = synergy_token_prod([alanna], "Mfg", "CombatRecord", platforms, 12.0)
        assert segs == []

    def test_机械精通β_3台作业平台_贵金属加30(self):
        """β: 每台+10%，3台 → 30%"""
        from steward_core.synergy import synergy_token_prod

        alanna = _mk_op("阿兰娜")
        alanna.skills.append(_mk_skill("manu_token_prod_spd[010]", "Mfg", "机械精通·β", {"all": 0.0}))

        platforms = {"Lancet-2": True, "Castle-3": True, "THRM-EX": True}

        segs = synergy_token_prod([alanna], "Mfg", "PureGold", platforms, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 30.0

    def test_无机械精通技能_返回空(self):
        """普通干员无机械精通 → 空"""
        from steward_core.synergy import synergy_token_prod

        op = _mk_op("普通")
        platforms = {"Lancet-2": True}

        segs = synergy_token_prod([op], "Mfg", "PureGold", platforms, 12.0)
        assert segs == []


# ─── B2 工程机器人生成 ──────────────────────────────────────────

class TestEngineeringRobots:
    """B2: compute_engineering_robots — 绘图设计生成工程机器人"""

    def test_243布局_14设施Lv3_生成42机器人(self):
        """14 间设施 × Lv3 = 42 机器人"""
        from steward_core.synergy import compute_engineering_robots
        from steward_core.models import LayoutConfig

        layout = LayoutConfig.layout_243()

        robots = compute_engineering_robots(layout)
        assert robots == 51  # 17 间设施(含Training+4Dorm) × Lv3

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

        assert pool.engineering_robots == 51

    def test_机械辅助α_42机器人_加10percent(self):
        """至简 α: 每16机器人→+5%，42机器人 → 42//16×5 = 10%"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        zhijian = _mk_op("至简")
        pool = BuffPool(engineering_robots=42)

        segs = synergy_buff_pool_consumer([zhijian], "Mfg", "PureGold", pool, 12.0)
        assert segs[0].a == 25.0  # β: 42//8*5 = 25 (β 比 α 优，取 β)


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


# ─── B1 办公室/Trade 生成源（新增） ──────────────────────────────────

class TestB1OfficeTradeGeneration:
    """B1: compute_buff_pool 扩展 — Office/Trade 来源的烟火/感知信息生成"""

    def test_絮雨_office_感知信息(self):
        """perception_from_office=20 → 感知信息额外 +20（2招募位×10记忆碎片）"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("夕")]
        pool = compute_buff_pool(control, perception_from_office=20)

        assert pool.perception == 30  # 夕(10) + 絮雨Office(20)
        assert pool.thought_chains == 30

    def test_絮雨_office_感知信息_与迷迭香超感叠加(self):
        """perception_from_office=20 + 迷迭香超感(5 dorm) → 叠加"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("夕")]
        dorm = [_mk_op(f"填位{i}") for i in range(5)]

        pool = compute_buff_pool(
            control, dorm_operators=dorm,
            has_rosmontis_in_mfg=True, perception_from_office=20,
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
            has_wuyou_in_trade=True,
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

        control = [_mk_op("令"), _mk_op("夕")]
        pool = compute_buff_pool(control, perception_from_office=0)

        assert pool.perception == 10  # 仅夕(10)


# ─── B5 无声共鸣生成（新增） ─────────────────────────────────────────

class TestB5SilentResonance:
    """B5: compute_buff_pool 扩展 — 无声共鸣生成（塑心宿舍 + 黑键感知转化）"""

    def test_塑心_宿舍_无声共鸣生成(self):
        """塑心在宿舍，20名干员 → silent_resonance +20"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("夕")]
        suxin = _mk_op("塑心")
        dorm = [suxin] + [_mk_op(f"填位{i}") for i in range(19)]

        pool = compute_buff_pool(
            control, dorm_operators=dorm, dorm_level=5,
            has_ebnhlz_in_trade=True, ling_mood_below_12=True,
        )

        # 令<12(10) + 夕(10) + 黑键乐感20人(20) = 40 perception → 40 silent_resonance
        # 塑心宿舍 20人 → +20 silent_resonance
        assert pool.perception == 40  # 令<12(10)+夕(10)+黑键乐感(20)
        assert pool.thought_chains == 40
        assert pool.silent_resonance == 60  # 40(感知→共鸣) + 20(塑心)

    def test_黑键_不在贸易站_无声共鸣仅塑心(self):
        """黑键不在 Trade → 无感知→共鸣转化，仅塑心宿舍生成"""
        from steward_core.synergy import compute_buff_pool

        control = [_mk_op("令"), _mk_op("夕")]
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

        control = [_mk_op("令"), _mk_op("夕")]
        suxin = _mk_op("塑心")
        dorm = [suxin] + [_mk_op(f"填位{i}") for i in range(4)]

        pool = compute_buff_pool(
            control, dorm_operators=dorm, dorm_level=5,
            has_rosmontis_in_mfg=True, has_ebnhlz_in_trade=True,
            ling_mood_below_12=True,
        )

        # 感知: 令<12(10) + 夕(10) + 迷迭香(5) + 黑键(5) = 30
        # silent_resonance: 感知→共鸣(30) + 塑心宿舍(5) = 35
        assert pool.perception == 30
        assert pool.silent_resonance == 35
        assert pool.thought_chains == 30


# ─── ROSEMARY_SUPPORT 扩展（新增） ────────────────────────────────────

class TestRosemarySupportExtension:
    """ROSEMARY_SUPPORT: 办公室支撑干员注册"""

    def test_rosemary_support_含office键(self):
        """ROSEMARY_SUPPORT 应包含 'Office' 键"""
        from steward_core.synergy import ROSEMARY_SUPPORT

        assert "Office" in ROSEMARY_SUPPORT
        assert ROSEMARY_SUPPORT["Office"] == ["絮雨"]

    def test_rosemary_support_含塑心(self):
        """ROSEMARY_SUPPORT['Dormitory'] 应包含塑心（B5无声共鸣生成者）"""
        from steward_core.synergy import ROSEMARY_SUPPORT

        assert "塑心" in ROSEMARY_SUPPORT["Dormitory"]


# ─── A2 阵营计数扩展（Trade: 摩根/新约能天使） ─────────────────────

class TestA2TradeFaction:
    """A2: synergy_faction_room — Trade 设施阵营计数"""

    def test_摩根_格拉斯哥帮_含自身_加40(self):
        """摩根 + 推王(格帮) → 2名格帮 × 20% = 40%"""
        from steward_core.synergy import synergy_faction_room

        morgan = _mk_op("摩根", group_id="glasgow")
        sieger = _mk_op("推进之王", group_id="glasgow")

        segs = synergy_faction_room([morgan, sieger], "Trade", "Money", 12.0)

        assert len(segs) == 1
        assert segs[0].a == 40.0  # 2人 × 20%

    def test_摩根_仅自身_格拉斯哥帮_加20(self):
        """摩根独自在场 → 1名格帮(自身) × 20% = 20%"""
        from steward_core.synergy import synergy_faction_room

        morgan = _mk_op("摩根", group_id="glasgow")

        segs = synergy_faction_room([morgan], "Trade", "Money", 12.0)

        assert len(segs) == 1
        assert segs[0].a == 20.0  # 自身 1人 × 20%

    def test_新约能天使_拉特兰_含自身_加30(self):
        """新约能天使 + 1名 Laterano → 2名 × 15% = 30%"""
        from steward_core.synergy import synergy_faction_room

        neoexu = _mk_op("新约能天使", nation_id="laterano")
        other = _mk_op("拉特兰干员", nation_id="laterano")

        segs = synergy_faction_room([neoexu, other], "Trade", "Money", 12.0)

        assert len(segs) == 1
        assert segs[0].a == 30.0  # 2人 × 15%

    def test_新约能天使_仅自身_拉特兰_加15(self):
        """新约能天使独自在场 → 1名(自身) × 15% = 15%"""
        from steward_core.synergy import synergy_faction_room

        neoexu = _mk_op("新约能天使", nation_id="laterano")

        segs = synergy_faction_room([neoexu], "Trade", "Money", 12.0)

        assert len(segs) == 1
        assert segs[0].a == 15.0

    def test_摩根_非Trade房间_不触发(self):
        """摩根在 Mfg → 不触发 A2 贸易加成"""
        from steward_core.synergy import synergy_faction_room

        morgan = _mk_op("摩根", group_id="glasgow")

        segs = synergy_faction_room([morgan], "Mfg", "PureGold", 12.0)
        assert segs == []

    def test_新约能天使_非Trade房间_不触发(self):
        """新约能天使在 Mfg → 不触发"""
        from steward_core.synergy import synergy_faction_room

        neoexu = _mk_op("新约能天使", nation_id="laterano")

        segs = synergy_faction_room([neoexu], "Mfg", "PureGold", 12.0)
        assert segs == []
