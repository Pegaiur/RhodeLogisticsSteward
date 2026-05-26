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

    def test_森蚺_自动化α_5percent每站(self):
        """森蚺(自动化α) → 3站×5%=15%"""
        from steward_core.synergy import synergy_automation

        # Arrange
        senia = _mk_op("森蚺")
        filler1 = _mk_op("A")
        filler2 = _mk_op("B")

        # Act
        segs, zero_set = synergy_automation([senia, filler1, filler2], "Mfg", power_count=3)

        # Assert
        assert len(segs) == 1
        assert segs[0].a == 15.0  # 3×5%

    def test_非制造站_不触发(self):
        """自动化仅在 Mfg 触发"""
        from steward_core.synergy import synergy_automation

        # Arrange
        wenti = _mk_op("温蒂")
        filler = _mk_op("A")

        # Act
        segs, zero_set = synergy_automation([wenti, filler], "Trade", power_count=3)

        # Assert
        assert segs == []
        assert zero_set == set()
