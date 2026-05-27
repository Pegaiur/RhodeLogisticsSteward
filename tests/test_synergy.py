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
              efficient: dict[str, float] | None = None) -> Skill:
    return Skill(
        buff_id=buff_id,
        buff_name=buff_name,
        skill_icon=buff_id,
        room_type=room_type,
        efficient=EfficiencyMap(raw=efficient or {"all": 0.0}),
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
        segs = synergy_pair([christine, wine, filler], "Mfg", "CombatRecord")

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
        segs = synergy_pair([wine, filler1, filler2], "Mfg", "CombatRecord")

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
        segs = synergy_pair([alana, wenmi, filler], "Mfg", "PureGold")

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
        segs = synergy_pair([alana, wenmi, filler], "Mfg", "CombatRecord")

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
        segs = synergy_skill_count([shuiyue, jessica, perfumer], "Mfg", alias)

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
        segs = synergy_skill_count(ops, "Mfg", alias)

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
        segs = synergy_skill_count(ops, "Mfg", alias)

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
        segs = synergy_skill_count(ops, "Mfg", alias)

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
        segs = synergy_skill_count(ops, "Mfg", alias)

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
        segs, zero_set = synergy_automation([wenti, filler1, filler2], "Mfg", power_count=3)

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
        segs, zero_set = synergy_automation([senran, filler1, filler2], "Mfg", power_count=3)

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
        segs, zero_set = synergy_automation([luefeng, filler1, filler2], "Mfg", power_count=3)

        # Assert: 3 发电站 × 5%(α) = 15%
        assert len(segs) == 1
        assert segs[0].a == 15.0

    def test_自动化不触发_普通房间(self):
        """无自动化干员 → 返回空"""
        from steward_core.synergy import synergy_automation

        # Arrange
        ops = [_mk_op("A"), _mk_op("B"), _mk_op("C")]

        # Act
        segs, zero_set = synergy_automation(ops, "Mfg", power_count=3)

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
        segs = synergy_facility_count([qingliu], "Mfg", "PureGold", layout)

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
        segs = synergy_facility_count([qingliu], "Mfg", "CombatRecord", layout)

        # Assert
        assert segs == []

    def test_空弦_每宿舍等级加2贸易(self):
        """空弦 (β) 在 Trade，4 间宿舍 × Lv3 → +24%"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig

        # Arrange
        kongxian = _mk_op("空弦")
        layout = LayoutConfig(rooms=[])

        # Act: dorm_levels 默认 12
        segs = synergy_facility_count([kongxian], "Trade", "Money", layout)

        # Assert: +24%
        assert len(segs) == 1
        assert segs[0].a == 24.0

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
        segs = synergy_facility_count([siye], "Trade", "Money", layout)

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
        segs = synergy_facility_count([siye], "Trade", "Money", layout)

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
        segs = synergy_facility_count([shiying], "Trade", "Money", layout)

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
        segs = synergy_facility_count([filler], "Mfg", "PureGold", layout)

        # Assert
        assert segs == []

    def test_娜仁图亚_赤金加宿舍等级(self):
        """娜仁图亚在 Mfg PureGold，12 宿舍等级 → +12%"""
        from steward_core.synergy import synergy_facility_count
        from steward_core.models import LayoutConfig

        # Arrange
        narentuya = _mk_op("娜仁图亚")
        layout = LayoutConfig(rooms=[])

        # Act: dorm_levels 默认 12
        segs = synergy_facility_count([narentuya], "Mfg", "PureGold", layout)

        # Assert: +12%
        assert len(segs) == 1
        assert segs[0].a == 12.0


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

        segs = synergy_buff_pool_consumer([miluoxiang], "Mfg", "PureGold", pool)
        assert len(segs) == 1
        assert segs[0].a == 10.0

    def test_b5_无声共鸣_黑键_贸易加成(self):
        """silent_resonance=15 → 黑键 β: 每2共鸣=+1% → +7% Trade"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        heijian = _mk_op("黑键")
        pool = BuffPool(silent_resonance=15)

        segs = synergy_buff_pool_consumer([heijian], "Trade", "Money", pool)
        assert len(segs) == 1
        assert segs[0].a == 7.0  # 15//2 = 7

    def test_b2_工程机器人_至简消费(self):
        """至简在 Mfg，42 robots(14设施×Lv3) → β: 每8机器人+5% → +25%"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        zhijian = _mk_op("至简")
        pool = BuffPool(engineering_robots=42)

        segs = synergy_buff_pool_consumer([zhijian], "Mfg", "PureGold", pool)
        assert len(segs) == 1
        assert segs[0].a == 25.0  # 42//8*5 = 25

    def test_b4_魔物料理_玛露西尔消费(self):
        """玛露西尔在 Mfg，cuisine=3 → +3%"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        maluxier = _mk_op("玛露西尔")
        pool = BuffPool(monster_cuisine=3)

        segs = synergy_buff_pool_consumer([maluxier], "Mfg", "PureGold", pool)
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

        segs = synergy_buff_pool_consumer([shu], "Mfg", "PureGold", pool)
        assert len(segs) == 1
        assert segs[0].a == 13.0  # 40//3 = 13

    def test_乌有_烟火转化为贸易效率(self):
        """乌有: per 1 烟火 → +1%，40 烟火 → +40%"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        wuyou = _mk_op("乌有")
        pool = BuffPool(yanhuo=40, perception=0)

        segs = synergy_buff_pool_consumer([wuyou], "Trade", "Money", pool)
        assert len(segs) == 1
        assert segs[0].a == 40.0

    def test_截云_烟火转巫术结晶(self):
        """截云: per 5 烟火 → +1 巫术结晶，per 1 巫术结晶 → +2% Mfg(β)"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        jieyun = _mk_op("截云")
        pool = BuffPool(yanhuo=40, perception=0, wushu_crystal=8)  # 40//5=8

        segs = synergy_buff_pool_consumer([jieyun], "Mfg", "PureGold", pool)
        assert len(segs) == 1
        assert segs[0].a == 16.0  # 8 × 2%

    def test_零烟火_无加成(self):
        """BuffPool 归零 → 消费者无输出"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        shu = _mk_op("黍")
        pool = BuffPool(yanhuo=0, perception=0)

        segs = synergy_buff_pool_consumer([shu], "Mfg", "PureGold", pool)
        assert segs == []

    def test_非目标房间_不触发(self):
        """黍在 Trade → 不触发烟火加成"""
        from steward_core.synergy import synergy_buff_pool_consumer, BuffPool

        shu = _mk_op("黍")
        pool = BuffPool(yanhuo=40, perception=0)

        segs = synergy_buff_pool_consumer([shu], "Trade", "Money", pool)
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
