"""whisper 归零完整性集成测试

验证所有被 whisper 归零的 synergy 函数不向 evaluate_room 泄漏效率。
这是 evaluate.py §3.1 根因的回归测试：
  operators → non_zero_ops 改动了 6 处，本测试确保零遗漏。
"""

import os
import pytest

from steward_core.data_loader import load_operators_v2
from steward_core.evaluate import evaluate_room

# 需要真数据（facility_link_table / trade_share_table 等）
pytestmark = pytest.mark.skipif(
    not os.path.exists("character_identity.json"),
    reason="需要 character_identity.json 真数据",
)


@pytest.fixture(scope="module")
def _real_ops():
    return load_operators_v2("character_identity.json", "buffs_infrastructure.json")


@pytest.fixture(scope="module")
def lookup(_real_ops):
    return {op.name: op for op in _real_ops}


def _eff(lookup, names: list[str]) -> float:
    """便捷：evaluate_room 返回的积分值"""
    return evaluate_room(
        [lookup[n] for n in names], "Trade", "Money", power_count=3, T=12.0,
    )


class TestWhisperZeroNoLeak:
    """whisper 归零后，房间效率应恰好为 whisper 自身加成 + base"""

    def test_whisper_alone_no_bonus(self, lookup):
        """巫恋单独入 Trade → 0（无人可归零）"""
        eff = _eff(lookup, ["巫恋"])
        assert eff == pytest.approx(0.0, abs=0.1)

    def test_whisper_plus_one_is_45pct(self, lookup):
        """巫恋 + 1 室友 → 45% × 12h = 540"""
        eff = _eff(lookup, ["巫恋", "龙舌兰"])
        expected = 45.0 * 12.0  # whisper bonus: 45% × T
        assert eff == pytest.approx(expected, abs=0.5)

    def test_whisper_plus_two_is_90pct(self, lookup):
        """巫恋 + 2 室友 → 90% × 12h = 1080"""
        eff = _eff(lookup, ["巫恋", "龙舌兰", "柏喙"])
        expected = 90.0 * 12.0  # whisper bonus: 90% × T
        assert eff == pytest.approx(expected, abs=0.5)

    # ── 回归：6 处 operators→non_zero_ops 修复的泄漏验证 ──

    def test_facility_count_not_leaked_空弦(self, lookup):
        """空弦 facility_count(dorm_levels) 被 whisper 归零后不应贡献 +40%"""
        eff_with_wulian = _eff(lookup, ["巫恋", "空弦", "龙舌兰"])
        eff_baseline = _eff(lookup, ["巫恋", "龙舌兰", "柏喙"])
        # 两者应相近（空弦归零后与裁缝归零后效率相同）
        assert eff_with_wulian == pytest.approx(eff_baseline, abs=1.0)

    def test_facility_count_not_leaked_伺夜(self, lookup):
        """伺夜 facility_count(meeting_level) 被 whisper 归零后不应贡献"""
        eff_with_wulian = _eff(lookup, ["巫恋", "伺夜", "龙舌兰"])
        eff_baseline = _eff(lookup, ["巫恋", "龙舌兰", "柏喙"])
        assert eff_with_wulian == pytest.approx(eff_baseline, abs=1.0)

    def test_trade_share_not_leaked(self, lookup):
        """吉星/火哨 share buff 被 whisper 归零后不应贡献"""
        eff_with_share = _eff(lookup, ["巫恋", "火哨", "龙舌兰"])
        eff_no_share = _eff(lookup, ["巫恋", "龙舌兰", "柏喙"])
        assert eff_with_share == pytest.approx(eff_no_share, abs=1.0)

    def test_trade_amplifier_not_leaked(self, lookup):
        """雪雉放大器被 whisper 归零后不应放大 whisper 自身效率"""
        eff_with_amp = _eff(lookup, ["巫恋", "雪雉", "龙舌兰"])
        eff_no_amp = _eff(lookup, ["巫恋", "龙舌兰", "柏喙"])
        assert eff_with_amp == pytest.approx(eff_no_amp, abs=1.0)

    def test_any_three_with_whisper_same_efficiency(self, lookup):
        """任意 3 人 whisper 组合效率相同——归零后只有 whisper 自身贡献"""
        combos = [
            ["巫恋", "空弦", "龙舌兰"],
            ["巫恋", "吉星", "柏喙"],
            ["巫恋", "伺夜", "火哨"],
            ["巫恋", "雪雉", "龙舌兰"],
        ]
        effs = [_eff(lookup, c) for c in combos]
        # 所有组合效率应在 whisper 90% × 12h = 1080 附近（±1 容差）
        expected = 90.0 * 12.0
        for i, eff in enumerate(effs):
            assert eff == pytest.approx(expected, abs=1.0), \
                f"combo {combos[i]}: eff={eff:.1f} expected~{expected:.1f}"
