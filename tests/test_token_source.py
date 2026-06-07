"""TokenSource 统一计数层单元测试 — Phase A 原型验证"""

import pytest

from steward_core.models import EfficiencyMap, Operator, Skill


def _mk_op(
    name: str = "测试",
    char_id: str = "",
    skills: list[Skill] | None = None,
    group_id: str | None = None,
    nation_id: str | None = None,
    team_id: str | None = None,
) -> Operator:
    return Operator(
        char_id=char_id or name,
        name=name,
        skills=skills or [],
        group_id=group_id,
        nation_id=nation_id,
        team_id=team_id,
    )


def _mk_mfg_skill(buff_id: str = "manu_prod_spd[001]") -> Skill:
    return Skill(
        buff_id=buff_id,
        buff_name="测试制造技能",
        skill_icon=buff_id,
        room_type="Mfg",
        efficient=EfficiencyMap(raw={"all": 25.0}),
    )


# ─── Phase A1: TokenSource dataclass + 拓扑排序执行引擎 ────────────────


class TestTokenSourceBasic:
    """最基本的 TokenSource 构造与 evaluate_tokens 调用"""

    def test_wildcard_count_returns_operator_count(self):
        """condition='*' aggregate='count' → 返回干员总数"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A"), _mk_op("B"), _mk_op("C")]
        sources = [TokenSource(token="total", condition="*")]

        result = evaluate_tokens(sources, ops)
        assert result["total"] == 3.0

    def test_wildcard_scope_global_counts_all(self):
        """scope='global' 不计房间边界"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A"), _mk_op("B"), _mk_op("C")]
        sources = [TokenSource(token="total", condition="*", scope="global")]

        result = evaluate_tokens(sources, ops)
        assert result["total"] == 3.0

    def test_empty_operators_returns_zero(self):
        """空干员列表 → token 值为 0"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        sources = [TokenSource(token="total", condition="*")]
        result = evaluate_tokens(sources, [])
        assert result["total"] == 0.0


class TestTopologicalSort:
    """depends_on 拓扑排序与循环依赖检测"""

    def test_simple_dependency_B_after_A(self):
        """B depends_on A → A 先计算，B 读取 A 的值"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("X"), _mk_op("Y")]
        sources = [
            TokenSource(token="a", condition="*"),
            TokenSource(token="b", depends_on="a", aggregate="passthrough"),
        ]

        result = evaluate_tokens(sources, ops)
        assert result["a"] == 2.0
        assert result["b"] == 2.0  # passthrough → 透传 a 的值

    def test_chain_dependency_three_levels(self):
        """A → B → C 三级依赖链"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("X")]
        sources = [
            TokenSource(token="a", condition="*"),
            TokenSource(token="b", depends_on="a", aggregate="passthrough"),
            TokenSource(token="c", depends_on="b", aggregate="passthrough"),
        ]

        result = evaluate_tokens(sources, ops)
        assert result["a"] == 1.0
        assert result["b"] == 1.0
        assert result["c"] == 1.0

    def test_cyclic_dependency_raises_error(self):
        """A→B→A 循环依赖抛出异常"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        sources = [
            TokenSource(token="a", depends_on="b", aggregate="passthrough"),
            TokenSource(token="b", depends_on="a", aggregate="passthrough"),
        ]

        with pytest.raises(ValueError, match="循环依赖"):
            evaluate_tokens(sources, [])

    def test_self_dependency_raises_error(self):
        """A depends_on A → 自循环抛出异常"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        sources = [
            TokenSource(token="self_loop", depends_on="self_loop", aggregate="passthrough"),
        ]

        with pytest.raises(ValueError, match="循环依赖"):
            evaluate_tokens(sources, [])

    def test_nonexistent_dependency_raises_error(self):
        """depends_on 指向不存在的 token → 异常"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        sources = [
            TokenSource(token="a", depends_on="missing", aggregate="passthrough"),
        ]

        with pytest.raises(ValueError, match="不存在"):
            evaluate_tokens(sources, [])


class TestCapAndExcludeSelf:
    """cap 上限与 exclude_self"""

    def test_cap_truncates_value(self):
        """cap=1 时 count 上限为 1"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A"), _mk_op("B"), _mk_op("C")]
        sources = [TokenSource(token="capped", condition="*", cap=1.0)]

        result = evaluate_tokens(sources, ops)
        assert result["capped"] == 1.0


# ─── Phase A2: 条件解析器（parse_condition + _build_matcher） ─────────────


class TestConditionGroupId:
    """condition='group_id=v'"""

    def test_group_id_match(self):
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [
            _mk_op("A", group_id="pinus"),
            _mk_op("B", group_id="other"),
            _mk_op("C", group_id="pinus"),
        ]
        sources = [TokenSource(token="pinus_count", condition="group_id=pinus")]

        result = evaluate_tokens(sources, ops)
        assert result["pinus_count"] == 2.0

    def test_group_id_no_match(self):
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A", group_id="other"), _mk_op("B", group_id="other")]
        sources = [TokenSource(token="count", condition="group_id=pinus")]

        result = evaluate_tokens(sources, ops)
        assert result["count"] == 0.0

    def test_group_id_with_cap(self):
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A", group_id="pinus") for _ in range(5)]
        sources = [TokenSource(token="capped", condition="group_id=pinus", cap=2.0)]

        result = evaluate_tokens(sources, ops)
        assert result["capped"] == 2.0


class TestConditionNationId:
    """condition='nation_id=v'"""

    def test_nation_id_match(self):
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [
            _mk_op("A", nation_id="siracusa"),
            _mk_op("B", nation_id="laterano"),
        ]
        sources = [TokenSource(token="sir", condition="nation_id=siracusa")]

        result = evaluate_tokens(sources, ops)
        assert result["sir"] == 1.0


class TestConditionCharId:
    """condition='char_id=v'"""

    def test_char_id_exact_match(self):
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [
            _mk_op("焰尾", char_id="char_140_white"),
            _mk_op("野鬃", char_id="char_141_nights"),
        ]
        sources = [TokenSource(token="target", condition="char_id=char_140_white")]

        result = evaluate_tokens(sources, ops)
        assert result["target"] == 1.0

    def test_char_id_no_match(self):
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A", char_id="char_001")]
        sources = [TokenSource(token="target", condition="char_id=nonexistent")]

        result = evaluate_tokens(sources, ops)
        assert result["target"] == 0.0


class TestConditionIsKnight:
    """condition='is_knight' 派生布尔"""

    def test_is_knight_matches_knight_op(self):
        from steward_core.token_source import TokenSource, evaluate_tokens

        # 焰尾：Kazimierz 势力 + pinus 阵营
        ops = [
            _mk_op("焰尾", group_id="pinus", nation_id="kazimierz"),
            _mk_op("普通干员", group_id="other", nation_id="other"),
        ]
        sources = [TokenSource(token="knights", condition="is_knight")]

        result = evaluate_tokens(sources, ops)
        assert result["knights"] == 1.0

    def test_is_knight_kazimierz_only(self):
        """仅 Kazimierz 势力（无 pinus）也算骑士"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A", nation_id="kazimierz")]
        sources = [TokenSource(token="knights", condition="is_knight")]

        result = evaluate_tokens(sources, ops)
        assert result["knights"] == 1.0


class TestConditionCountGe:
    """condition='count_ge:g=N' 阈值条件"""

    def test_count_ge_sufficient(self):
        """>=N 人满足条件 → token=1"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [
            _mk_op("A", group_id="karlan"),
            _mk_op("B", group_id="karlan"),
            _mk_op("C", group_id="karlan"),
        ]
        sources = [TokenSource(token="karlan3", condition="count_ge:karlan=3")]

        result = evaluate_tokens(sources, ops)
        assert result["karlan3"] == 1.0

    def test_count_ge_insufficient(self):
        """<N 人 → token=0"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A", group_id="karlan"), _mk_op("B", group_id="karlan")]
        sources = [TokenSource(token="karlan3", condition="count_ge:karlan=3")]

        result = evaluate_tokens(sources, ops)
        assert result["karlan3"] == 0.0


class TestConditionPair:
    """condition='pair=char_id_A:char_id_B' 二元配对"""

    def test_pair_both_present(self):
        """双方都在 scope 内 → token=1"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [
            _mk_op("德克萨斯", char_id="char_103_angel"),
            _mk_op("拉普兰德", char_id="char_140_white"),
        ]
        sources = [TokenSource(token="texas_lappy", condition="pair=char_103_angel:char_140_white")]

        result = evaluate_tokens(sources, ops)
        assert result["texas_lappy"] == 1.0

    def test_pair_one_missing(self):
        """只有一方 → token=0"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("德克萨斯", char_id="char_103_angel")]
        sources = [TokenSource(token="texas_lappy", condition="pair=char_103_angel:char_140_white")]

        result = evaluate_tokens(sources, ops)
        assert result["texas_lappy"] == 0.0

    def test_pair_neither_present(self):
        """双方都不在 → token=0"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("无关", char_id="char_999")]
        sources = [TokenSource(token="texas_lappy", condition="pair=char_103_angel:char_140_white")]

        result = evaluate_tokens(sources, ops)
        assert result["texas_lappy"] == 0.0


class TestConditionErrors:
    """条件解析器的错误处理"""

    def test_unknown_condition_key_raises(self):
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A")]
        sources = [TokenSource(token="bad", condition="unknown_key=value")]

        with pytest.raises(ValueError, match="未知"):
            evaluate_tokens(sources, ops)

    def test_malformed_pair_raises(self):
        """pair 格式错误（无冒号分隔）"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A")]
        sources = [TokenSource(token="bad", condition="pair=only_one")]

        with pytest.raises(ValueError, match="期望格式"):
            evaluate_tokens(sources, ops)

    def test_count_ge_no_group_raises(self):
        """count_ge 缺少 group 参数"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A")]
        sources = [TokenSource(token="bad", condition="count_ge=3")]

        with pytest.raises(ValueError, match="count_ge"):
            evaluate_tokens(sources, ops)

    def test_count_ge_non_integer_raises(self):
        """count_ge N 不是整数"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A")]
        sources = [TokenSource(token="bad", condition="count_ge:karlan=abc")]

        with pytest.raises(ValueError, match="count_ge"):
            evaluate_tokens(sources, ops)


# ─── _build_matcher 独立测试 ────────────────────────────────────


class TestBuildMatcher:
    """_build_matcher 的直接调用路径（绕过 evaluate_tokens）"""

    def test_build_wildcard(self):
        from steward_core.token_source import _build_matcher

        m = _build_matcher("*")
        assert m(_mk_op("任意"))

    def test_build_group_id(self):
        from steward_core.token_source import _build_matcher

        m = _build_matcher("group_id=pinus")
        assert m(_mk_op("A", group_id="pinus"))
        assert not m(_mk_op("B", group_id="other"))

    def test_build_nation_id(self):
        from steward_core.token_source import _build_matcher

        m = _build_matcher("nation_id=siracusa")
        assert m(_mk_op("A", nation_id="siracusa"))
        assert not m(_mk_op("B", nation_id="other"))

    def test_build_char_id(self):
        from steward_core.token_source import _build_matcher

        m = _build_matcher("char_id=char_140_white")
        assert m(_mk_op("焰尾", char_id="char_140_white"))
        assert not m(_mk_op("其他", char_id="other"))

    def test_build_is_knight(self):
        from steward_core.token_source import _build_matcher

        m = _build_matcher("is_knight")
        # Kazimierz 势力 + pinus 阵营
        assert m(_mk_op("焰尾", group_id="pinus", nation_id="kazimierz"))
        assert not m(_mk_op("普通", group_id="other", nation_id="other"))

    def test_build_unknown_key_raises(self):
        from steward_core.token_source import _build_matcher
        import pytest

        with pytest.raises(ValueError, match="未知"):
            _build_matcher("unknown_key=value")

    def test_build_pair_raises_not_implemented(self):
        from steward_core.token_source import _build_matcher
        import pytest

        with pytest.raises(NotImplementedError, match="直接处理"):
            _build_matcher("pair=A:B")

    def test_build_count_ge_raises_not_implemented(self):
        from steward_core.token_source import _build_matcher
        import pytest

        with pytest.raises(NotImplementedError, match="直接处理"):
            _build_matcher("count_ge:karlan=3")


# ─── Phase A3: SlotContext.find_by_char_id ──────────────────────


class TestFindByCharId:
    """SlotContext 和 GlobalContext 的 find_by_char_id 方法"""

    def test_slot_context_find_existing(self):
        from steward_core.solver.slot.context import SlotContext

        ops = [
            _mk_op("焰尾", char_id="char_140_white"),
            _mk_op("野鬃", char_id="char_141_nights"),
        ]
        ctx = SlotContext(operators=ops, op_lookup={op.name: op for op in ops})

        found = ctx.find_by_char_id("char_140_white")
        assert found is not None
        assert found.name == "焰尾"

    def test_slot_context_find_nonexistent(self):
        from steward_core.solver.slot.context import SlotContext

        ops = [_mk_op("A", char_id="char_001")]
        ctx = SlotContext(operators=ops, op_lookup={op.name: op for op in ops})

        found = ctx.find_by_char_id("nonexistent")
        assert found is None

    def test_global_context_find_existing(self):
        from steward_core.solver.context import GlobalContext

        ops = [_mk_op("令", char_id="char_201_ling")]
        gctx = GlobalContext(control_operators=ops)

        found = gctx.find_by_char_id("char_201_ling")
        assert found is not None
        assert found.name == "令"

    def test_global_context_find_nonexistent(self):
        from steward_core.solver.context import GlobalContext

        gctx = GlobalContext()
        found = gctx.find_by_char_id("nonexistent")
        assert found is None


# ─── Phase A4: TokenSource 注册（A 层同房阵营 3 + PerOp 8） ─────────


class TestPhaseASources:
    """PHASE_A_SOURCES 11 条注册的覆盖测试"""

    def test_all_sources_evaluable(self):
        """所有 11 条注册均可被 evaluate_tokens 成功计算"""
        from steward_core.token_source import PHASE_A_SOURCES, evaluate_tokens

        # 构造覆盖全部条件的干员池
        ops = [
            _mk_op("芬", team_id="reserve1"),
            _mk_op("摩根", group_id="glasgow"),
            _mk_op("能天使", nation_id="laterano"),
            _mk_op("焰尾", group_id="pinus", nation_id="kazimierz"),
            _mk_op("野鬃", group_id="pinus", nation_id="kazimierz"),
            _mk_op("野鬃2", group_id="pinus", nation_id="kazimierz"),
            _mk_op("野鬃3", group_id="pinus", nation_id="kazimierz"),
            _mk_op("薇薇安娜", group_id="pinus", nation_id="kazimierz"),
            _mk_op("涤火杰西卡", group_id="blacksteel"),
            _mk_op("八幡海铃", nation_id="siracusa"),
            _mk_op("银灰", group_id="karlan"),
            _mk_op("初雪", group_id="karlan"),
            _mk_op("崖心", group_id="karlan"),
            _mk_op("戴菲恩", group_id="glasgow"),
            _mk_op("灵知", group_id="karlan"),
        ]

        result = evaluate_tokens(PHASE_A_SOURCES, ops)
        assert len(result) == 11

    def test_reserve1_mfg_counts_team(self):
        """team_id=reserve1 → 计数 1"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("芬", team_id="reserve1"), _mk_op("其他", team_id="other")]
        result = evaluate_tokens([TokenSource(token="t", condition="team_id=reserve1")], ops)
        assert result["t"] == 1.0

    def test_glasgow_trade_counts_group(self):
        """group_id=glasgow → 计数"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("摩根", group_id="glasgow"), _mk_op("戴菲恩", group_id="glasgow")]
        result = evaluate_tokens([TokenSource(token="t", condition="group_id=glasgow")], ops)
        assert result["t"] == 2.0

    def test_laterano_trade_counts_nation(self):
        """nation_id=laterano → 计数"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("能天使", nation_id="laterano")]
        result = evaluate_tokens([TokenSource(token="t", condition="nation_id=laterano")], ops)
        assert result["t"] == 1.0

    def test_pinus_cr_counts_four(self):
        """4 名 pinus → pinus_cr = 4"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [
            _mk_op("A", group_id="pinus", nation_id="kazimierz") for _ in range(4)
        ]
        result = evaluate_tokens([TokenSource(token="pinus_cr", condition="group_id=pinus")], ops)
        assert result["pinus_cr"] == 4.0

    def test_knight_mfg_counts_knights(self):
        """is_knight → 匹配 pinus + kazimierz"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [
            _mk_op("焰尾", group_id="pinus", nation_id="kazimierz"),
            _mk_op("野鬃", group_id="pinus", nation_id="kazimierz"),
            _mk_op("普通", group_id="other", nation_id="other"),
        ]
        result = evaluate_tokens([TokenSource(token="t", condition="is_knight")], ops)
        assert result["t"] == 2.0

    def test_blacksteel_mfg_counts(self):
        """group_id=blacksteel → 计数"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("涤火杰西卡", group_id="blacksteel")]
        result = evaluate_tokens([TokenSource(token="t", condition="group_id=blacksteel")], ops)
        assert result["t"] == 1.0

    def test_siracusa_trade_counts(self):
        """nation_id=siracusa → 计数"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("八幡海铃", nation_id="siracusa")]
        result = evaluate_tokens([TokenSource(token="t", condition="nation_id=siracusa")], ops)
        assert result["t"] == 1.0

    def test_karlan3_threshold_met(self):
        """3 名 karlan → karlan3_trade = 1"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [
            _mk_op("银灰", group_id="karlan"),
            _mk_op("初雪", group_id="karlan"),
            _mk_op("崖心", group_id="karlan"),
        ]
        result = evaluate_tokens([TokenSource(token="t", condition="count_ge:karlan=3")], ops)
        assert result["t"] == 1.0

    def test_karlan3_threshold_not_met(self):
        """2 名 karlan → karlan3_trade = 0"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [
            _mk_op("银灰", group_id="karlan"),
            _mk_op("初雪", group_id="karlan"),
        ]
        result = evaluate_tokens([TokenSource(token="t", condition="count_ge:karlan=3")], ops)
        assert result["t"] == 0.0

    def test_glasgow_trade_bonus(self):
        """group_id=glasgow → 戴菲恩另开 token"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("戴菲恩", group_id="glasgow")]
        result = evaluate_tokens([TokenSource(token="t", condition="group_id=glasgow")], ops)
        assert result["t"] == 1.0

    def test_karlan_trade_penalty(self):
        """karlan 惩罚 token（灵知）"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("灵知", group_id="karlan")]
        result = evaluate_tokens([TokenSource(token="t", condition="group_id=karlan")], ops)
        assert result["t"] == 1.0

    def test_team_id_match(self):
        """team_id 条件语法独立测试"""
        from steward_core.token_source import _build_matcher

        m = _build_matcher("team_id=reserve1")
        assert m(_mk_op("芬", team_id="reserve1"))
        assert not m(_mk_op("其他", team_id="other"))
