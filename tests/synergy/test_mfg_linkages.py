"""mfg_linkages 模块单元测试 — 制造站联动 (A1-A5, 归零, 机械, 爬升, 容量, 放大器)"""

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


# ─── A2 阵营计数扩展（Trade: 摩根/新约能天使） ─────────────────────

class TestA2TradeFaction:
    """A2: synergy_faction_room — Trade 设施阵营计数"""

    def test_摩根_格拉斯哥帮_含自身_加40(self):
        """摩根 + 推王(格帮) → 2名格帮 × 20% = 40% A2计数 + 推王专属额外35% = 75%"""
        from steward_core.synergy import synergy_faction_room

        morgan = _mk_op("摩根", group_id="glasgow")
        sieger = _mk_op("推进之王", group_id="glasgow")

        segs = synergy_faction_room([morgan, sieger], "Trade", "Money", 12.0)

        assert len(segs) == 2
        assert segs[0].a == 40.0  # 2人 × 20%
        assert segs[1].a == 35.0  # 推王专属额外+35%

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

    def test_森蚺持有alpha和beta_取最高版本(self):
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

    def test_掠风仅有alpha_取5percent(self):
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

    def test_急性子_芬_20爬升至25(self):
        """芬持有 急性子(20→25%@1%/h) → 爬升段(20% + 1%/h ramp + 5h后饱和25%)"""
        from steward_core.synergy import operator_ramp_segments

        fen = _mk_op("芬")
        fen.skills.append(_mk_skill(
            "manu_prod_spd_addition[030]", "Mfg", "急性子", {"all": 20.0},
        ))

        segs = operator_ramp_segments(fen, "Mfg", "PureGold", T=12.0)
        assert segs is not None
        assert len(segs) == 2
        assert segs[0].a == 20.0 and segs[0].b == 1.0  # ramp
        assert segs[1].a == 25.0 and segs[1].b == 0.0  # saturated

    def test_等不及_刻俄柏_20爬升至25(self):
        """刻俄柏持有 "等不及"(20→25%@1%/h) → 爬升段(20% + 1%/h ramp + 5h后饱和25%)"""
        from steward_core.synergy import operator_ramp_segments

        keeba = _mk_op("刻俄柏")
        keeba.skills.append(_mk_skill(
            "manu_prod_spd_addition[031]", "Mfg", "\"等不及\"", {"all": 20.0},
        ))

        segs = operator_ramp_segments(keeba, "Mfg", "CombatRecord", T=12.0)
        assert segs is not None
        assert len(segs) == 2
        assert segs[0].a == 20.0 and segs[0].b == 1.0
        assert segs[1].a == 25.0 and segs[1].b == 0.0

    def test_慢性子_克洛丝_15爬升至25(self):
        """克洛丝持有 慢性子(15→25%@2%/h) → 爬升段(15% + 2%/h ramp + 5h后饱和25%)"""
        from steward_core.synergy import operator_ramp_segments

        kroos = _mk_op("克洛丝")
        kroos.skills.append(_mk_skill(
            "manu_prod_spd_addition[040]", "Mfg", "慢性子", {"all": 15.0},
        ))

        segs = operator_ramp_segments(kroos, "Mfg", "PureGold", T=12.0)
        assert segs is not None
        assert len(segs) == 2
        assert segs[0].a == 15.0 and segs[0].b == 2.0  # ramp
        assert segs[1].a == 25.0 and segs[1].b == 0.0  # saturated

    def test_延时摄影_稀音_15爬升至25(self):
        """稀音持有 延时摄影(15→25%@2%/h) → 爬升段(15% + 2%/h ramp + 5h后饱和25%)"""
        from steward_core.synergy import operator_ramp_segments

        xiyin = _mk_op("稀音")
        xiyin.skills.append(_mk_skill(
            "manu_prod_spd_addition[041]", "Mfg", "延时摄影", {"all": 15.0},
        ))

        segs = operator_ramp_segments(xiyin, "Mfg", "CombatRecord", T=12.0)
        assert segs is not None
        assert len(segs) == 2
        assert segs[0].a == 15.0 and segs[0].b == 2.0
        assert segs[1].a == 25.0 and segs[1].b == 0.0

    def test_聚影_伊内丝_会客室爬升(self):
        """伊内丝持有 聚影(20→30%@2%/h) → 会客室爬升段(20% + 2%/h ramp + 5h后饱和30%)"""
        from steward_core.synergy import operator_ramp_segments

        ines = _mk_op("伊内丝")
        ines.skills.append(_mk_skill(
            "meet_spd_hast[000]", "Reception", "聚影", {"all": 20.0},
        ))

        segs = operator_ramp_segments(ines, "Reception", "General", T=12.0)
        assert segs is not None
        assert len(segs) == 2
        assert segs[0].a == 20.0 and segs[0].b == 2.0  # ramp
        assert segs[1].a == 30.0 and segs[1].b == 0.0  # saturated


# ─── operator_estimated_efficiency ───────────────────────────────

class TestExpected12hEfficiency:
    """爬升感知的平均效率预估: operator_estimated_efficiency"""

    def test_阿罗玛_例行清扫_12h平均约11_67(self):
        """阿罗玛 [100]: 0→20%@2%/h, 10h饱和 → 12h平均 = (100+40)/12 = 11.67%"""
        from steward_core.synergy import operator_estimated_efficiency

        aluoma = _mk_op("阿罗玛")
        aluoma.skills.append(_mk_skill(
            "manu_prod_spd_addition[100]", "Mfg", "例行清扫", {"all": 0.0},
        ))

        eff = operator_estimated_efficiency(aluoma, "Mfg", "PureGold", T=12.0)
        assert pytest.approx(eff, rel=0.01) == 11.67

    def test_芬_急性子_12h平均约23_96(self):
        """芬 [030]: 20→25%@1%/h, 5h饱和 → 12h平均 = (112.5+175)/12 ≈ 23.96%"""
        from steward_core.synergy import operator_estimated_efficiency

        fen = _mk_op("芬")
        fen.skills.append(_mk_skill(
            "manu_prod_spd_addition[030]", "Mfg", "急性子", {"all": 20.0},
        ))

        eff = operator_estimated_efficiency(fen, "Mfg", "CombatRecord", T=12.0)
        # ramp: integrate(20+1t, 0,5) + 25*7 = 112.5 + 175 = 287.5 → /12 = 23.958
        assert pytest.approx(eff, rel=0.01) == 23.96

    def test_克洛丝_慢性子_12h平均约22_92(self):
        """克洛丝 [040]: 15→25%@2%/h, 5h饱和 → 12h平均 = (100+175)/12 ≈ 22.92%"""
        from steward_core.synergy import operator_estimated_efficiency

        kroos = _mk_op("克洛丝")
        kroos.skills.append(_mk_skill(
            "manu_prod_spd_addition[040]", "Mfg", "慢性子", {"all": 15.0},
        ))

        eff = operator_estimated_efficiency(kroos, "Mfg", "PureGold", T=12.0)
        # ramp: integrate(15+2t, 0,5) + 25*7 = 100 + 175 = 275 → /12 = 22.917
        assert pytest.approx(eff, rel=0.01) == 22.92

    def test_非爬升技能_回退到best_efficiency(self):
        """无爬升技能 → 返回 best_efficiency 标量"""
        from steward_core.synergy import operator_estimated_efficiency

        op = _mk_op("普通")
        op.skills.append(_mk_skill("manu_prod_spd[001]", "Mfg", "普通技能", {"all": 30.0}))

        eff = operator_estimated_efficiency(op, "Mfg", "PureGold", T=12.0)
        assert eff == 30.0

    def test_非Mfg房间_回退到best_efficiency(self):
        """Trade 设施无爬升 → 返回 raw 标量"""
        from steward_core.synergy import operator_estimated_efficiency

        op = _mk_op("贸易干员")
        op.skills.append(_mk_skill("trade_ord_spd[001]", "Trade", "贸易技能", {"Money": 30.0}))

        eff = operator_estimated_efficiency(op, "Trade", "Money", T=12.0)
        assert eff == 30.0

    def test_伊内丝_聚影_12h平均约27_92(self):
        """伊内丝 (Reception): 20→30%@2%/h, 5h饱和 → 12h平均 = (125+210)/12 ≈ 27.92%"""
        from steward_core.synergy import operator_estimated_efficiency

        ines = _mk_op("伊内丝")
        ines.skills.append(_mk_skill(
            "meet_spd_hast[000]", "Reception", "聚影", {"all": 20.0},
        ))

        eff = operator_estimated_efficiency(ines, "Reception", "General", T=12.0)
        # ramp: integrate(20+2t, 0,5) + 30*7 = 125 + 210 = 335 → /12 = 27.917
        assert pytest.approx(eff, rel=0.01) == 27.92


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

    def test_机械精通alpha_2台作业平台_贵金属加10(self):
        """阿兰娜机械精通α: 2台作业平台在发电站 → +10%"""
        from steward_core.synergy import synergy_token_prod

        alanna = _mk_op("阿兰娜")
        alanna.skills.append(_mk_skill("manu_token_prod_spd[000]", "Mfg", "机械精通·α", {"all": 0.0}))

        platforms = {"Lancet-2": True, "Castle-3": True}

        segs = synergy_token_prod([alanna], "Mfg", "PureGold", platforms, 12.0)
        assert len(segs) == 1
        assert segs[0].a == 10.0

    def test_机械精通alpha_贵金属专属_作战记录不触发(self):
        """α仅在贵金属配方生效"""
        from steward_core.synergy import synergy_token_prod

        alanna = _mk_op("阿兰娜")
        alanna.skills.append(_mk_skill("manu_token_prod_spd[000]", "Mfg", "机械精通·α", {"all": 0.0}))

        platforms = {"Lancet-2": True}

        segs = synergy_token_prod([alanna], "Mfg", "CombatRecord", platforms, 12.0)
        assert segs == []

    def test_机械精通beta_3台作业平台_贵金属加30(self):
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
