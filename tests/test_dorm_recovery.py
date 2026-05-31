"""宿舍恢复速率评估单元测试 (dorm_recovery.py)

测试 evaluate_dorm_recovery 的 6 条聚合规则 + 边界条件。
全部通过内存构造，不依赖磁盘文件。
"""

import pytest

from steward_core.models import EfficiencyMap, Operator, Skill
from steward_core.dorm_recovery import evaluate_dorm_recovery, _get_effective_dorm_value


def _dorm_skill(buff_id: str, value: float) -> Skill:
    return Skill(
        buff_id=buff_id,
        buff_name=f"宿舍_{buff_id}",
        skill_icon=buff_id,
        room_type="DORMITORY",
        efficient=EfficiencyMap(raw={"all": value}),
    )


def _dorm_op(name: str, rarity: int = 0, skills: list[Skill] | None = None) -> Operator:
    return Operator(
        char_id=name, name=name, rarity=rarity, skills=skills or [],
    )


# ─── Rule 1: 菲亚梅塔自律 ────────────────────────────────────────

class TestRule1FiammettaSelf:
    def test_菲亚梅塔返回固定2(self):
        target = _dorm_op("菲亚梅塔", skills=[
            _dorm_skill("dorm_recExcludeOther[000]", 0.0),
        ])
        assert evaluate_dorm_recovery([target], target) == 2.0

    def test_隔离同宿舍他人buff(self):
        """自律隔离外部加成——同宿舍干员的全体恢复不应生效"""
        target = _dorm_op("菲亚梅塔", skills=[
            _dorm_skill("dorm_recExcludeOther[000]", 0.0),
        ])
        peer = _dorm_op("杜林", skills=[_dorm_skill("dorm_rec_all[000]", 0.25)])
        assert evaluate_dorm_recovery([target, peer], target, dorm_bonus_all=0.2) == 2.0

    def test_隔离人间烟火(self):
        target = _dorm_op("菲亚梅塔", skills=[
            _dorm_skill("dorm_recExcludeOther[000]", 0.0),
        ])
        assert evaluate_dorm_recovery([target], target, yanhuo_bonus=0.15) == 2.0


# ─── Rule 2: 自身恢复 ────────────────────────────────────────────

class TestRule2SelfRecovery:
    def test_自身技能生效(self):
        target = _dorm_op("推王", skills=[_dorm_skill("dorm_rec_oneself[000]", 0.55)])
        assert evaluate_dorm_recovery([target], target) == 0.55

    def test_多个自身技能取最大(self):
        target = _dorm_op("推王", skills=[
            _dorm_skill("dorm_rec_oneself[000]", 0.55),
            _dorm_skill("dorm_rec_oneself_e2[001]", 0.65),
        ])
        assert evaluate_dorm_recovery([target], target) == 0.65

    def test_含与号的自身技能也识别(self):
        """dorm_rec_xxx&oneself_xxx 格式也被识别"""
        target = _dorm_op("推王", skills=[
            _dorm_skill("dorm_rec_a&oneself_b[000]", 0.45),
        ])
        assert evaluate_dorm_recovery([target], target) == 0.45


# ─── Rule 3: 单体恢复 (peer → target) ────────────────────────────

class TestRule3SingleRecovery:
    def test_室友单体技能生效(self):
        target = _dorm_op("阿米娅")
        peer = _dorm_op("杜林", skills=[_dorm_skill("dorm_rec_single[000]", 0.2)])
        rate = evaluate_dorm_recovery([target, peer], target)
        assert rate == 0.2

    def test_多个室友单体取最大(self):
        target = _dorm_op("阿米娅")
        p1 = _dorm_op("杜林", skills=[_dorm_skill("dorm_rec_single[000]", 0.2)])
        p2 = _dorm_op("12F", skills=[_dorm_skill("dorm_rec_single[001]", 0.3)])
        rate = evaluate_dorm_recovery([target, p1, p2], target)
        assert rate == 0.3

    def test_单体技能不对自身生效(self):
        op = _dorm_op("杜林", skills=[_dorm_skill("dorm_rec_single[000]", 0.2)])
        rate = evaluate_dorm_recovery([op], op)
        assert rate == 0.0


# ─── Rule 4: 全体恢复 (peer sum) ─────────────────────────────────

class TestRule4AllRecovery:
    def test_室友全体技能生效(self):
        target = _dorm_op("阿米娅")
        peer = _dorm_op("杜林", skills=[_dorm_skill("dorm_rec_all[000]", 0.1)])
        rate = evaluate_dorm_recovery([target, peer], target)
        assert rate == 0.1

    def test_多个全体技能累加(self):
        target = _dorm_op("阿米娅")
        p1 = _dorm_op("杜林", skills=[_dorm_skill("dorm_rec_all[000]", 0.1)])
        p2 = _dorm_op("12F", skills=[_dorm_skill("dorm_rec_all[001]", 0.1)])
        rate = evaluate_dorm_recovery([target, p1, p2], target)
        assert rate == 0.2

    def test_全体技能不对自身生效(self):
        op = _dorm_op("杜林", skills=[_dorm_skill("dorm_rec_all[000]", 0.1)])
        rate = evaluate_dorm_recovery([op], op)
        assert rate == 0.0


# ─── Rule 5: 中枢全局宿舍加成 ────────────────────────────────────

class TestRule5ControlBonus:
    def test_全员加成生效(self):
        target = _dorm_op("阿米娅")
        rate = evaluate_dorm_recovery([target], target, dorm_bonus_all=0.15)
        assert rate == 0.15

    def test_精英加成对五星生效(self):
        target = _dorm_op("阿米娅", rarity=5)
        rate = evaluate_dorm_recovery(
            [target], target, dorm_bonus_all=0.15, dorm_bonus_elite=0.45,
        )
        assert rate == 0.60

    def test_精英加成不对四星生效(self):
        target = _dorm_op("阿米娅", rarity=4)
        rate = evaluate_dorm_recovery(
            [target], target, dorm_bonus_all=0.15, dorm_bonus_elite=0.45,
        )
        assert rate == 0.15


# ─── Rule 6: 人间烟火 ────────────────────────────────────────────

class TestRule6Yanhuo:
    def test_人间烟火加成生效(self):
        target = _dorm_op("阿米娅")
        rate = evaluate_dorm_recovery([target], target, yanhuo_bonus=0.15)
        assert rate == 0.15


# ─── 组合规则 ────────────────────────────────────────────────────

class TestCombinedRules:
    def test_自身加室友全体加奖励叠加(self):
        target = _dorm_op("推王", skills=[_dorm_skill("dorm_rec_oneself[000]", 0.55)])
        peer = _dorm_op("杜林", skills=[_dorm_skill("dorm_rec_all[000]", 0.1)])
        rate = evaluate_dorm_recovery(
            [target, peer], target,
            dorm_bonus_all=0.15, yanhuo_bonus=0.05,
        )
        assert pytest.approx(rate) == 0.85

    def test_空宿舍返回零(self):
        target = _dorm_op("阿米娅")
        rate = evaluate_dorm_recovery([], target)
        assert rate == 0.0


# ─── _get_effective_dorm_value ────────────────────────────────────

class TestGetEffectiveDormValue:
    def test_正常值(self):
        sk = _dorm_skill("test", 0.25)
        assert _get_effective_dorm_value(sk) == 0.25

    def test_负数截断为零(self):
        sk = _dorm_skill("test", -5.0)
        assert _get_effective_dorm_value(sk) == 0.0

    def test_零值(self):
        sk = _dorm_skill("test", 0.0)
        assert _get_effective_dorm_value(sk) == 0.0
