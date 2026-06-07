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
