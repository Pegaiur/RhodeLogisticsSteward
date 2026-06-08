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


def _mk_trade_skill(eff_all: float = 0.0) -> Skill:
    """创建 Trade 技能，可指定效率值"""
    return Skill(
        buff_id="trade_ord_spd[001]",
        buff_name="测试贸易技能",
        skill_icon="trade_ord_spd[001]",
        room_type="Trade",
        efficient=EfficiencyMap(raw={"all": eff_all} if eff_all else {"all": 0.0}),
    )


def _mk_mfg_skill_with_eff(eff_all: float = 25.0, capacity: int = 0) -> Skill:
    """创建 Mfg 技能，可指定效率和容量"""
    return Skill(
        buff_id="manu_prod_spd[001]",
        buff_name="测试制造技能",
        skill_icon="manu_prod_spd[001]",
        room_type="Mfg",
        efficient=EfficiencyMap(raw={"all": eff_all}),
        capacity_bonus=capacity,
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

    def test_team_id(self):
        from steward_core.token_source import _build_matcher

        m = _build_matcher("team_id=reserve1")
        assert m(_mk_op("芬", team_id="reserve1"))
        assert not m(_mk_op("其他", team_id="other"))


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
        from steward_core.synergy.token_maps import PHASE_A_SOURCES
        from steward_core.token_source import evaluate_tokens

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


# ─── Phase B3: is_abyssal_hunter ────────────────────────────────────


class TestConditionAbyssalHunter:
    """condition='is_abyssal_hunter' 派生布尔"""

    def test_abyssal_hunter_match(self):
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [
            _mk_op("歌蕾蒂娅", group_id="abyssal"),
            _mk_op("普通", group_id="other"),
        ]
        sources = [TokenSource(token="t", condition="is_abyssal_hunter")]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == 1.0

    def test_abyssal_hunter_no_match(self):
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A", group_id="other")]
        sources = [TokenSource(token="t", condition="is_abyssal_hunter")]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == 0.0


# ─── Phase B4: skill_class 条件 ─────────────────────────────────────


class TestConditionSkillClass:
    """condition='skill_class=v' 技能类别标签匹配"""

    def test_skill_class_match(self):
        from steward_core.token_source import TokenSource, evaluate_tokens

        s1 = _mk_mfg_skill("manu_spd_rhine[001]")
        s1.buff_name = "莱茵科技·α"
        s2 = _mk_mfg_skill("manu_spd_pinus[001]")
        s2.buff_name = "红松骑士团·α"

        ops = [
            _mk_op("A", skills=[s1]),
            _mk_op("B", skills=[s2]),
            _mk_op("C"),
        ]
        sources = [TokenSource(token="t", condition="skill_class=红松骑士团")]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == 1.0

    def test_skill_class_no_match(self):
        from steward_core.token_source import TokenSource, evaluate_tokens

        s = _mk_mfg_skill()
        s.buff_name = "标准化·β"
        ops = [_mk_op("A", skills=[s])]
        sources = [TokenSource(token="t", condition="skill_class=红松骑士团")]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == 0.0

    def test_skill_class_multiple_skills(self):
        """干员有多个技能，其中一个匹配"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        s1 = _mk_mfg_skill()
        s1.buff_name = "标准化·α"
        s2 = _mk_mfg_skill()
        s2.buff_name = "红松骑士团·α"

        ops = [_mk_op("A", skills=[s1, s2])]
        sources = [TokenSource(token="t", condition="skill_class=红松骑士团")]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == 1.0

    def test_glasgow_trade_counts_group(self):
        """group_id=glasgow → 计数"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("摩根", group_id="glasgow"), _mk_op("戴菲恩", group_id="glasgow")]
        result = evaluate_tokens([TokenSource(token="t", condition="group_id=glasgow")], ops)
        assert result["t"] == 2.0


# ─── Phase C1: evaluate_room() 接入框架 ────────────────────────────


class TestPhaseC1RoomIntegration:
    """TokenSource 接入 evaluate_room() — 计数对齐验证"""

    def test_facility_count_tokens_match_layout(self):
        """synergy_facility_count 的内部布局计数 + per-op 计数与 TokenSource 一致"""
        from steward_core.token_source import evaluate_tokens
        from steward_core.synergy.token_maps import PHASE_B_FACTORY_COUNT
        from steward_core.models import RoomConfig, LayoutConfig
        from steward_core.solver.slot.context import SlotContext

        # 243 布局模拟
        layout = LayoutConfig(rooms=[
            RoomConfig("Trade", 0, 3, "Money"),
            RoomConfig("Trade", 1, 3, "Money"),
            RoomConfig("Mfg", 0, 3, "CombatRecord"),
            RoomConfig("Mfg", 1, 3, "PureGold"),
            RoomConfig("Dormitory", 0, 5, level=3),
            RoomConfig("Dormitory", 1, 5, level=3),
            RoomConfig("Dormitory", 2, 5, level=2),
            RoomConfig("Dormitory", 3, 5, level=2),
        ])

        # 清流（A_FACILITY_LINK 条目：每贸易站 +20%）
        op = _mk_op("清流")
        ctx = SlotContext(operators=[op], op_lookup={"清流": op}, layout=layout)

        # TokenSource 工厂计数
        tokens = evaluate_tokens(PHASE_B_FACTORY_COUNT, [], ctx)
        assert tokens["trade_rooms"] == 2.0
        assert tokens["mfg_rooms"] == 2.0
        assert tokens["power_rooms"] == 0.0

    def test_tokens_equal_synergy_facility_count_internals(self):
        """TokenSource 计数值与 synergy_facility_count 内部计算一致"""
        from steward_core.token_source import TokenSource, evaluate_tokens
        from steward_core.models import RoomConfig, LayoutConfig
        from steward_core.solver.slot.context import SlotContext

        layout = LayoutConfig(rooms=[
            RoomConfig("Trade", 0, 3, "Money"),
            RoomConfig("Trade", 1, 3, "Money"),
            RoomConfig("Mfg", 0, 3, "CombatRecord"),
            RoomConfig("Mfg", 1, 3, "PureGold"),
            RoomConfig("Mfg", 2, 3, "PureGold"),
            RoomConfig("Dormitory", 0, 5, level=3),
            RoomConfig("Dormitory", 1, 5, level=3),
        ])

        ctx = SlotContext(operators=[], op_lookup={}, layout=layout)

        # TokenSource 计数
        sources = [
            TokenSource(token="trade_rooms", depends_on="layout", target_room="Trade"),
            TokenSource(token="mfg_rooms", depends_on="layout", target_room="Mfg"),
        ]
        tokens = evaluate_tokens(sources, [], ctx)

        # synergy_facility_count 内部: trade_count = sum(1 for r in layout.rooms if r.room_type == "Trade")
        expected_trade = sum(1 for r in layout.rooms if r.room_type == "Trade")
        expected_mfg = sum(1 for r in layout.rooms if r.room_type == "Mfg")

        assert tokens["trade_rooms"] == float(expected_trade)
        assert tokens["mfg_rooms"] == float(expected_mfg)


# ─── Phase C3: TokenSource 替代 evaluate_room 内计数函数 ──────────


class TestPhaseC3EvaluateRoom:
    """TokenSource room_tokens 替代旧计数函数"""

    def test_room_tokens_pairs_match(self):
        """room_tokens pair 值与 synergy_pair 内部计数一致"""
        from steward_core.token_source import compute_room_tokens

        ops = [_mk_op("阿兰娜"), _mk_op("温米")]
        room_tokens = compute_room_tokens(ops)
        # pair token 现在已纳入 compute_room_tokens (Phase C3 扩展)
        assert room_tokens["alanna_wenmi"] == 1.0

    def test_room_tokens_count_matches_faction_room(self):
        """room_tokens 阵营计数与 synergy_faction_room 内部一致"""
        from steward_core.token_source import compute_room_tokens
        from steward_core.synergy.mfg_linkages import synergy_faction_room

        ops = [_mk_op("历阵锐枪芬", team_id="reserve1"), _mk_op("克洛斯", team_id="reserve1")]
        room_tokens = compute_room_tokens(ops)

        # TokenSource reserve1_mfg 统计 team_id=reserve1
        assert room_tokens["reserve1_mfg"] == 2.0

        # 旧函数：芬 + 克洛斯均在制造站 CombarRecord → bonus_per=10%
        segs = synergy_faction_room(ops, "Mfg", "CombatRecord", 12.0)
        assert len(segs) == 1
        assert segs[0].a == pytest.approx(20.0)  # 2 * 10%

    def test_room_tokens_count_matches_skill_count(self):
        """room_tokens skill_class 与 synergy_skill_count 内部一致"""
        from steward_core.token_source import compute_room_tokens
        from steward_core.synergy.mfg_linkages import synergy_skill_count

        s_std = _mk_mfg_skill(); s_std.buff_name = "标准化·α"
        ops = [_mk_op("水月", skills=[s_std]), _mk_op("A", skills=[s_std])]
        room_tokens = compute_room_tokens(ops)

        assert room_tokens["standardization_count"] == 2.0

        segs = synergy_skill_count(ops, "Mfg")
        assert len(segs) == 1
        assert segs[0].a == pytest.approx(10.0)  # 2 * 5%


# ─── Phase C4: Control 层计数替换 ────────────────────────────────


class TestPhaseC4Control:
    """TokenSource 替代 _eval_per_op / control_per_operator_bonus 计数"""

    def test_tokens_match_eval_per_op_group_id(self):
        """room_tokens pinus_cr 与 _eval_per_op group_id 计数一致"""
        from steward_core.token_source import compute_room_tokens
        from steward_core.synergy.control_linkages import _eval_per_op, ControlPerOpEntry

        ops = [_mk_op("A", group_id="pinus"), _mk_op("B", group_id="pinus"), _mk_op("C")]
        room_tokens = compute_room_tokens(ops)

        # TokenSource: 2 名 pinus → pinus_cr = 2
        assert room_tokens["pinus_cr"] == 2.0

        # 旧函数
        entry = ControlPerOpEntry(
            scope="per_op", condition_field="group_id", condition_value="pinus",
            room_type="Mfg", bonus_per=5.0, product=None,
        )
        bonus = _eval_per_op(entry, ops)
        assert bonus == pytest.approx(10.0)  # 2 * 5%

    def test_tokens_match_eval_per_op_knights(self):
        """room_tokens knight_mfg 与 _eval_per_op is_knight 计数一致"""
        from steward_core.token_source import compute_room_tokens
        from steward_core.synergy.control_linkages import _eval_per_op, ControlPerOpEntry

        # kazimierz → is_knight = True
        ops = [_mk_op("A", nation_id="kazimierz"), _mk_op("B", nation_id="kazimierz")]
        room_tokens = compute_room_tokens(ops)

        assert room_tokens["knight_mfg"] == 2.0

        entry = ControlPerOpEntry(
            scope="per_op", condition_field="is_knight", condition_value="",
            room_type="Mfg", bonus_per=5.0, product=None,
        )
        bonus = _eval_per_op(entry, ops)
        assert bonus == pytest.approx(10.0)  # 2 * 5%

    def test_tokens_match_count_ge(self):
        """room_tokens karlan3_trade 与 _eval_per_op count_ge 计数一致"""
        from steward_core.token_source import compute_room_tokens
        from steward_core.synergy.control_linkages import _eval_per_op, ControlPerOpEntry

        ops = [_mk_op("A", group_id="karlan"), _mk_op("B", group_id="karlan"), _mk_op("C", group_id="karlan")]
        room_tokens = compute_room_tokens(ops)

        # 3 名 karlan → count_ge:karlan=3 → karlan3_trade = 1
        assert room_tokens["karlan3_trade"] == 1.0

        entry = ControlPerOpEntry(
            scope="per_room", condition_field="count_ge", condition_value="3",
            room_type="Trade", bonus_per=5.0, product=None,
        )
        bonus = _eval_per_op(entry, ops)
        assert bonus == pytest.approx(5.0)  # 满足阈值 → 5%


# ─── Phase B7: 旧函数集成对齐 ───────────────────────────────────


class TestIntegrationSkillCount:
    """TokenSource 与 synergy_skill_count 计数对齐"""

    def test_skill_class_count_matches_old(self):
        from steward_core.synergy.token_maps import PHASE_B_SKILL_CLASS
        from steward_core.token_source import evaluate_tokens
        from steward_core.synergy.mfg_linkages import synergy_skill_count

        # A 有标准化技能，B 有莱茵科技，C 无技能标签
        s_std = _mk_mfg_skill(); s_std.buff_name = "标准化·α"
        s_rhine = _mk_mfg_skill(); s_rhine.buff_name = "莱茵科技·β"
        ops = [
            _mk_op("水月", skills=[s_std]),
            _mk_op("X", skills=[s_std]),
            _mk_op("Y", skills=[s_rhine]),
            _mk_op("Z"),
        ]

        # TokenSource: 标准化 = 水月+X = 2
        tokens = evaluate_tokens(PHASE_B_SKILL_CLASS, ops)
        assert tokens["standardization_count"] == 2.0
        assert tokens["rhine_tech_count"] == 1.0

        # 旧函数: 水月在房间内 → 标准化计数 = 2 → bonus = 2*5 = 10
        # 多萝西不在 ops → 无莱茵科技持有者 → 无莱茵段
        segments = synergy_skill_count(ops, "Mfg")
        # 水月: 标准化持有者，count=2，bonus=10
        assert len(segments) == 1
        assert segments[0].a == pytest.approx(10.0)  # 2 matching * 5%


class TestIntegrationGlobalFaction:
    """TokenSource 与 synergy_global_faction 计数对齐"""

    def test_global_faction_count_matches_old(self):
        from steward_core.synergy.token_maps import PHASE_B_GLOBAL_FACTION
        from steward_core.token_source import evaluate_tokens
        from steward_core.synergy.global_linkages import synergy_global_faction

        # 全局 4 名 rhine 干员，但 cap=5
        all_ops = [_mk_op(f"R{i}", group_id="rhine") for i in range(4)]
        room_ops = [_mk_op("缪尔赛思", group_id="rhine")]  # 持有者在房间内

        # TokenSource: rhine_global count = 4
        tokens = evaluate_tokens(PHASE_B_GLOBAL_FACTION, all_ops)
        assert tokens["rhine_global"] == 4.0  # 4 ≤ cap=5

        # 旧函数: 缪尔赛思在房间内 → count=4-1(排除自身)=3 → bonus=3*3=9
        segments = synergy_global_faction(room_ops, "Power", "Power", all_ops, 12.0)
        assert len(segments) == 1
        assert segments[0].a == pytest.approx(9.0)  # (4-1) * 3%


class TestIntegrationClusterHunting:
    """TokenSource 与 compute_cluster_hunting_bonus 计数对齐"""

    def test_abyssal_count_matches_old(self):
        from steward_core.synergy.token_maps import PHASE_B_CLUSTER
        from steward_core.token_source import evaluate_tokens

        ops = [
            _mk_op("A", group_id="abyssal"),
            _mk_op("B", group_id="abyssal"),
            _mk_op("C", group_id="other"),
        ]

        # TokenSource 集群狩猎: abyssal_mfg count = 2
        tokens = evaluate_tokens(PHASE_B_CLUSTER, ops)
        assert tokens["abyssal_mfg"] == 2.0

        # 旧函数需 control_ops + mfg_assignments，此处仅验证 TokenSource 计数
        # 与 _CLUSTER_HUNTING_TABLE 的 group_id 条件一致


# ─── Phase B5: 引擎 layout/facility 依赖 ─────────────────────────


class TestLayoutDependency:
    """TokenSource depends_on='layout' — 从 SlotContext.layout 查询"""

    def test_layout_trade_room_count(self):
        from steward_core.token_source import TokenSource, evaluate_tokens
        from steward_core.solver.slot.context import SlotContext
        from steward_core.models import RoomConfig, LayoutConfig

        layout = LayoutConfig(rooms=[
            RoomConfig("Trade", 0, 3, "Money"),
            RoomConfig("Trade", 1, 3, "Money"),
            RoomConfig("Mfg", 0, 3, "CombatRecord"),
        ])
        ctx = SlotContext(operators=[], op_lookup={}, layout=layout)

        sources = [TokenSource(token="trade_rooms", depends_on="layout", target_room="Trade")]
        result = evaluate_tokens(sources, [], ctx)
        assert result["trade_rooms"] == 2.0

    def test_layout_ctx_none_returns_zero(self):
        from steward_core.token_source import TokenSource, evaluate_tokens

        sources = [TokenSource(token="trade_rooms", depends_on="layout", target_room="Trade")]
        result = evaluate_tokens(sources, [], None)
        assert result["trade_rooms"] == 0.0


class TestFacilityDependency:
    """TokenSource depends_on='facility' — 从 ctx.build_all_assignments() 查询"""

    def test_facility_ctx_none_returns_zero(self):
        from steward_core.token_source import TokenSource, evaluate_tokens

        sources = [TokenSource(
            token="sui_facilities", depends_on="facility", condition="group_id=sui",
        )]
        result = evaluate_tokens(sources, [], None)
        assert result["sui_facilities"] == 0.0

    def test_facility_sui_count(self):
        from steward_core.token_source import TokenSource, evaluate_tokens
        from steward_core.solver.slot.context import SlotContext, SlotAssignment, WindowState
        from steward_core.models import RoomConfig, LayoutConfig

        layout = LayoutConfig(rooms=[
            RoomConfig("Trade", 0, 3, "Money"),
            RoomConfig("Trade", 1, 3, "Money"),
        ])
        op_ling = _mk_op("令", group_id="sui")
        op_xi = _mk_op("夕", group_id="sui")
        ctx = SlotContext(
            operators=[op_ling, op_xi],
            op_lookup={"令": op_ling, "夕": op_xi},
            layout=layout,
            windows=[
                WindowState(assignments=[
                    SlotAssignment("trade_0_0", "Trade", "Money", "令", 0),
                    SlotAssignment("trade_0_1", "Trade", "Money", "夕", 0),
                    SlotAssignment("trade_1_0", "Trade", "Money", "", 1),
                ])
            ],
        )

        sources = [TokenSource(
            token="sui_facilities",
            depends_on="facility",
            condition="group_id=sui",
        )]
        result = evaluate_tokens(sources, [], ctx)
        assert result["sui_facilities"] == 1.0  # 只有 Trade 0 含 sui


# ─── B7 补充：可立即完成的注册测试 ──────────────────────────────


class TestPhaseBAPairs:
    """A 层配对 + 阵营额外"""

    def test_alanna_wenmi_pair(self):
        from steward_core.synergy.token_maps import PHASE_B_A_PAIRS
        from steward_core.token_source import evaluate_tokens

        ops = [_mk_op("阿兰娜"), _mk_op("温米")]
        result = evaluate_tokens(PHASE_B_A_PAIRS, ops)
        assert result["alanna_wenmi"] == 1.0

    def test_morgan_siege_pair(self):
        from steward_core.synergy.token_maps import PHASE_B_A_PAIRS
        from steward_core.token_source import evaluate_tokens

        ops = [_mk_op("摩根")]
        result = evaluate_tokens(PHASE_B_A_PAIRS, ops)
        assert result["morgan_siege"] == 0.0  # 推进之王不在


class TestPhaseBTradePairs:
    """贸易配对"""

    def test_texas_lappland_pair(self):
        from steward_core.synergy.token_maps import PHASE_B_TRADE_PAIRS
        from steward_core.token_source import evaluate_tokens

        ops = [_mk_op("德克萨斯"), _mk_op("拉普兰德")]
        result = evaluate_tokens(PHASE_B_TRADE_PAIRS, ops)
        assert result["texas_lappland"] == 1.0


class TestPhaseBEffAmplifier:
    """贸易效率放大"""

    def test_trade_eff_total(self):
        from steward_core.synergy.token_maps import PHASE_B_EFF_AMPLIFIER
        from steward_core.token_source import evaluate_tokens

        ops = [_mk_op("A", skills=[_mk_trade_skill(30.0)]), _mk_op("B", skills=[_mk_trade_skill(20.0)])]
        result = evaluate_tokens(PHASE_B_EFF_AMPLIFIER, ops)
        assert result["trade_eff_total"] == pytest.approx(50.0)


class TestPhaseBConditionalEff:
    """贸易条件效率"""

    def test_siye_in_base(self):
        from steward_core.synergy.token_maps import PHASE_B_CONDITIONAL_EFF
        from steward_core.token_source import evaluate_tokens

        ops = [_mk_op("伺夜"), _mk_op("其他")]
        result = evaluate_tokens(PHASE_B_CONDITIONAL_EFF, ops)
        assert result["siye_in_base"] == 1.0


class TestPhaseBEliteFacilities:
    """设施 group elite"""

    def test_elite_facility_count(self):
        from steward_core.synergy.token_maps import PHASE_B_FACILITY_GROUP
        from steward_core.token_source import evaluate_tokens
        from steward_core.solver.slot.context import SlotContext, SlotAssignment, WindowState
        from steward_core.models import RoomConfig, LayoutConfig

        layout = LayoutConfig(rooms=[RoomConfig("Trade", 0, 3, "Money")])
        op = _mk_op("德克萨斯", group_id="elite")
        ctx = SlotContext(
            operators=[op],
            op_lookup={"德克萨斯": op},
            layout=layout,
            windows=[WindowState(assignments=[
                SlotAssignment("trade_0_0", "Trade", "Money", "德克萨斯", 0),
            ])],
        )
        result = evaluate_tokens(PHASE_B_FACILITY_GROUP, [], ctx)
        assert result["elite_facilities"] == 1.0


# ─── Phase B6: layout/facility 注册测试 ───────────────────────────


class TestPhaseBFactoryCount:
    """工厂数量联动 TokenSource"""

    def test_trade_room_count(self):
        from steward_core.synergy.token_maps import PHASE_B_FACTORY_COUNT
        from steward_core.token_source import evaluate_tokens
        from steward_core.solver.slot.context import SlotContext
        from steward_core.models import RoomConfig, LayoutConfig

        layout = LayoutConfig(rooms=[
            RoomConfig("Trade", 0, 3, "Money"),
            RoomConfig("Trade", 1, 3, "Money"),
            RoomConfig("Mfg", 0, 3, "CombatRecord"),
        ])
        ctx = SlotContext(operators=[], op_lookup={}, layout=layout)
        result = evaluate_tokens(PHASE_B_FACTORY_COUNT, [], ctx)
        assert result["trade_rooms"] == 2.0
        assert result["mfg_rooms"] == 1.0
        assert result["power_rooms"] == 0.0


class TestPhaseBFacilityGroup:
    """设施 group 计数 TokenSource"""

    def test_sui_facility_count(self):
        from steward_core.synergy.token_maps import PHASE_B_FACILITY_GROUP
        from steward_core.token_source import evaluate_tokens
        from steward_core.solver.slot.context import SlotContext, SlotAssignment, WindowState
        from steward_core.models import RoomConfig, LayoutConfig

        layout = LayoutConfig(rooms=[RoomConfig("Trade", 0, 3, "Money")])
        op = _mk_op("令", group_id="sui")
        ctx = SlotContext(
            operators=[op],
            op_lookup={"令": op},
            layout=layout,
            windows=[WindowState(assignments=[
                SlotAssignment("trade_0_0", "Trade", "Money", "令", 0),
            ])],
        )
        result = evaluate_tokens(PHASE_B_FACILITY_GROUP, [], ctx)
        assert result["sui_facilities"] == 1.0


# ─── Phase B1: 新增 TokenSource 注册 ──────────────────────────────


class TestPhaseBSkillClass:
    """A 层技能标签计数"""

    def test_skill_class_all_evaluable(self):
        from steward_core.synergy.token_maps import PHASE_B_SKILL_CLASS
        from steward_core.token_source import evaluate_tokens

        s1 = _mk_mfg_skill(); s1.buff_name = "标准化·α"
        s2 = _mk_mfg_skill(); s2.buff_name = "莱茵科技·β"
        s3 = _mk_mfg_skill(); s3.buff_name = "金属工艺·γ"
        ops = [
            _mk_op("A", skills=[s1]),
            _mk_op("B", skills=[s2]),
            _mk_op("C", skills=[s3]),
        ]
        result = evaluate_tokens(PHASE_B_SKILL_CLASS, ops)
        assert result["standardization_count"] == 1.0
        assert result["rhine_tech_count"] == 1.0
        assert result["metal_craft_count"] == 1.0


class TestPhaseBGlobalFaction:
    """B 层全局阵营计数"""

    def test_rhine_global_count(self):
        from steward_core.synergy.token_maps import PHASE_B_GLOBAL_FACTION
        from steward_core.token_source import evaluate_tokens

        ops = [
            _mk_op("A", group_id="rhine"),
            _mk_op("B", group_id="rhine"),
            _mk_op("C", group_id="other"),
        ]
        result = evaluate_tokens(PHASE_B_GLOBAL_FACTION, ops)
        assert result["rhine_global"] == 2.0

    def test_rhine_global_cap(self):
        from steward_core.synergy.token_maps import PHASE_B_GLOBAL_FACTION
        from steward_core.token_source import evaluate_tokens

        ops = [_mk_op("X", group_id="rhine") for _ in range(10)]
        result = evaluate_tokens(PHASE_B_GLOBAL_FACTION, ops)
        assert result["rhine_global"] == 5.0  # cap=5


class TestPhaseBCrossPairs:
    """B 层跨房间配对"""

    def test_liexia_gumi_pair(self):
        from steward_core.synergy.token_maps import PHASE_B_CROSS_PAIRS
        from steward_core.token_source import evaluate_tokens

        ops = [
            _mk_op("烈夏"),
            _mk_op("古米"),
        ]
        result = evaluate_tokens(PHASE_B_CROSS_PAIRS, ops)
        assert result["liexia_gumi"] == 1.0

    def test_liexia_gumi_missing(self):
        from steward_core.synergy.token_maps import PHASE_B_CROSS_PAIRS
        from steward_core.token_source import evaluate_tokens

        ops = [_mk_op("烈夏")]
        result = evaluate_tokens(PHASE_B_CROSS_PAIRS, ops)
        assert result["liexia_gumi"] == 0.0


class TestPhaseBCluster:
    """C 层集群狩猎"""

    def test_abyssal_mfg_count(self):
        from steward_core.synergy.token_maps import PHASE_B_CLUSTER
        from steward_core.token_source import evaluate_tokens

        ops = [
            _mk_op("A", group_id="abyssal"),
            _mk_op("B", group_id="abyssal"),
            _mk_op("C", group_id="other"),
        ]
        result = evaluate_tokens(PHASE_B_CLUSTER, ops)
        assert result["abyssal_mfg"] == 2.0


# ─── Phase B2: buff_id → Token 映射 ────────────────────────────────


class TestBuffToTokens:
    """_BUFF_TO_TOKENS 映射表"""

    def test_covers_all_14_producer_entries(self):
        from steward_core.synergy.token_maps import _BUFF_TO_TOKENS

        assert len(_BUFF_TO_TOKENS) == 14

    def test_black_key_cascade(self):
        """黑键 trade_ord_spd_bd_n1[000] 同时产出 perception + silent_resonance"""
        from steward_core.synergy.token_maps import _BUFF_TO_TOKENS

        tokens = _BUFF_TO_TOKENS["trade_ord_spd_bd_n1[000]"]
        assert "perception" in tokens
        assert "silent_resonance" in tokens


# ─── Phase B6: 级联正确性测试 ───────────────────────────────────


class TestBuffCascade:
    """黑键 perception→silent_resonance + 令 yanhuo→wushu_crystal 级联"""

    def test_perception_to_silent_resonance(self):
        """perception 作为上游 token → silent_resonance passthrough 接收"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A"), _mk_op("B"), _mk_op("C")]
        sources = [
            TokenSource(token="perception", condition="*"),
            TokenSource(
                token="silent_resonance",
                depends_on="perception",
                aggregate="passthrough",
            ),
        ]
        result = evaluate_tokens(sources, ops)
        assert result["perception"] == 3.0
        assert result["silent_resonance"] == 3.0

    def test_yanhuo_to_wushu_crystal(self):
        """yanhuo → wushu_crystal 级联（令的衍生物）"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A"), _mk_op("B")]
        sources = [
            TokenSource(token="yanhuo", condition="*"),
            TokenSource(
                token="wushu_crystal",
                depends_on="yanhuo",
                aggregate="passthrough",
            ),
        ]
        result = evaluate_tokens(sources, ops)
        assert result["yanhuo"] == 2.0
        assert result["wushu_crystal"] == 2.0

    def test_cascade_chain_three_levels(self):
        """perception → silent_resonance → downstream 三级链"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("X")]
        sources = [
            TokenSource(token="perception", condition="*"),
            TokenSource(
                token="silent_resonance",
                depends_on="perception",
                aggregate="passthrough",
            ),
            TokenSource(
                token="downstream",
                depends_on="silent_resonance",
                aggregate="passthrough",
            ),
        ]
        result = evaluate_tokens(sources, ops)
        assert result["perception"] == 1.0
        assert result["silent_resonance"] == 1.0
        assert result["downstream"] == 1.0

    def test_all_tokens_known_dimensions(self):
        """所有产出 token 属于已知维度"""
        from steward_core.synergy.token_maps import _BUFF_TO_TOKENS

        known = {"yanhuo", "perception", "monster_cuisine", "silent_resonance"}
        for buff_id, tokens in _BUFF_TO_TOKENS.items():
            for t in tokens:
                assert t in known, f"{buff_id} 产出未知 token: {t}"

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


# ─── A5: cap 截断 + attr=None 边界 ────────────────────────────────


class TestAggregateCap:
    """四种聚合模式的 cap 截断行为"""

    def test_efficiency_sum_cap(self):
        from steward_core.token_source import TokenSource, evaluate_tokens
        ops = [_mk_op("A", skills=[_mk_trade_skill(100.0)]) for _ in range(3)]
        sources = [TokenSource(
            token="t", condition="*",
            aggregate="efficiency_sum", aggregate_unit=1.0,
            target_room="Trade", cap=50.0,
        )]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == 50.0  # 300 → cap 50

    def test_max_efficiency_cap(self):
        from steward_core.token_source import TokenSource, evaluate_tokens
        ops = [
            _mk_op("A", skills=[_mk_trade_skill(30.0)]),
            _mk_op("B", skills=[_mk_trade_skill(90.0)]),
        ]
        sources = [TokenSource(
            token="t", condition="*",
            aggregate="max_efficiency", target_room="Trade", cap=50.0,
        )]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == 50.0  # max=90 → cap 50

    def test_attribute_sum_cap(self):
        from steward_core.token_source import TokenSource, evaluate_tokens
        ops = [_mk_op("A", skills=[_mk_mfg_skill_with_eff(capacity=4)]) for _ in range(3)]
        sources = [TokenSource(
            token="t", condition="*",
            aggregate="attribute_sum", target_room="Mfg",
            attr="capacity_bonus", cap=8.0,
        )]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == 8.0  # 12 → cap 8

    def test_distinct_cap(self):
        from steward_core.token_source import TokenSource, evaluate_tokens
        from steward_core.models import Skill, EfficiencyMap
        skills = [
            Skill("b1", "s1", "icon_A", "Mfg", EfficiencyMap(raw={"all": 10.0})),
            Skill("b2", "s2", "icon_B", "Mfg", EfficiencyMap(raw={"all": 20.0})),
            Skill("b3", "s3", "icon_C", "Mfg", EfficiencyMap(raw={"all": 30.0})),
        ]
        ops = [_mk_op("A", skills=[skills[0]]), _mk_op("B", skills=[skills[1]]), _mk_op("C", skills=[skills[2]])]
        sources = [TokenSource(
            token="t", condition="*",
            aggregate="distinct", target_room="Mfg",
            attr="skill_icon", cap=2.0,
        )]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == 2.0  # 3 unique → cap 2


class TestAggregateBoundary:
    """边界条件"""

    def test_attribute_sum_attr_none_returns_zero(self):
        from steward_core.token_source import TokenSource, evaluate_tokens
        ops = [_mk_op("A", skills=[_mk_mfg_skill_with_eff(capacity=2)])]
        sources = [TokenSource(
            token="t", condition="*",
            aggregate="attribute_sum", target_room="Mfg",
            attr=None,
        )]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == 0.0

    def test_distinct_attr_none_returns_zero(self):
        from steward_core.token_source import TokenSource, evaluate_tokens
        ops = [_mk_op("A")]
        sources = [TokenSource(
            token="t", condition="*",
            aggregate="distinct", target_room="Mfg",
            attr=None,
        )]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == 0.0


# ─── Phase A5: 聚合模式单元测试 ─────────────────────────────────────


class TestAggregateEfficiencySum:
    """aggregate='efficiency_sum' — 效率值聚合除以 unit"""

    def test_efficiency_sum_trade(self):
        """3 名干员的 Trade 效率 ÷ unit=3 → (30+60+0)/3 = 30"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [
            _mk_op("A", skills=[_mk_trade_skill(30.0)]),
            _mk_op("B", skills=[_mk_trade_skill(60.0)]),
            _mk_op("C", skills=[_mk_trade_skill(0.0)]),
        ]
        sources = [TokenSource(
            token="trade_eff_avg", condition="*",
            aggregate="efficiency_sum", aggregate_unit=3.0,
            target_room="Trade",
        )]
        result = evaluate_tokens(sources, ops)
        assert result["trade_eff_avg"] == pytest.approx(30.0)

    def test_efficiency_sum_empty(self):
        """无技能干员 → 0"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A"), _mk_op("B")]
        sources = [TokenSource(
            token="t", condition="*",
            aggregate="efficiency_sum", aggregate_unit=1.0,
            target_room="Trade",
        )]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == 0.0

    def test_efficiency_sum_with_unit(self):
        """aggregate_unit 放大效果"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A", skills=[_mk_trade_skill(100.0)])]
        sources = [TokenSource(
            token="t", condition="*",
            aggregate="efficiency_sum", aggregate_unit=10.0,
            target_room="Trade",
        )]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == pytest.approx(10.0)  # 100/10


class TestAggregateMaxEfficiency:
    """aggregate='max_efficiency' — 最高效率值"""

    def test_max_efficiency(self):
        """3 名干员中最高 Trade 效率"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [
            _mk_op("A", skills=[_mk_trade_skill(30.0)]),
            _mk_op("B", skills=[_mk_trade_skill(90.0)]),
            _mk_op("C", skills=[_mk_trade_skill(45.0)]),
        ]
        sources = [TokenSource(
            token="max_eff", condition="*",
            aggregate="max_efficiency", target_room="Trade",
        )]
        result = evaluate_tokens(sources, ops)
        assert result["max_eff"] == 90.0

    def test_max_efficiency_empty(self):
        """无技能干员 → 0"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A")]
        sources = [TokenSource(
            token="t", condition="*",
            aggregate="max_efficiency", target_room="Trade",
        )]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == 0.0


class TestAggregateAttributeSum:
    """aggregate='attribute_sum' — 属性值聚合"""

    def test_attribute_sum_capacity(self):
        """capacity_bonus 总和"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [
            _mk_op("A", skills=[_mk_mfg_skill_with_eff(capacity=2)]),
            _mk_op("B", skills=[_mk_mfg_skill_with_eff(capacity=4)]),
            _mk_op("C", skills=[_mk_mfg_skill_with_eff(capacity=0)]),
        ]
        sources = [TokenSource(
            token="total_cap", condition="*",
            aggregate="attribute_sum", target_room="Mfg",
            attr="capacity_bonus",
        )]
        result = evaluate_tokens(sources, ops)
        assert result["total_cap"] == 6.0


class TestAggregateDistinct:
    """aggregate='distinct' — 去重计数"""

    def test_distinct_skill_icons(self):
        """按 skill_icon 去重计数"""
        from steward_core.token_source import TokenSource, evaluate_tokens
        from steward_core.models import Skill, EfficiencyMap

        s1 = Skill("b1", "s1", "icon_A", "Mfg", EfficiencyMap(raw={"all": 10.0}))
        s2 = Skill("b2", "s2", "icon_A", "Mfg", EfficiencyMap(raw={"all": 20.0}))
        s3 = Skill("b3", "s3", "icon_B", "Mfg", EfficiencyMap(raw={"all": 30.0}))

        ops = [
            _mk_op("A", skills=[s1]),
            _mk_op("B", skills=[s2]),
            _mk_op("C", skills=[s3]),
        ]
        sources = [TokenSource(
            token="unique_icons", condition="*",
            aggregate="distinct", target_room="Mfg",
            attr="skill_icon",
        )]
        result = evaluate_tokens(sources, ops)
        assert result["unique_icons"] == 2.0  # icon_A, icon_B

    def test_distinct_empty(self):
        """无技能 → 0"""
        from steward_core.token_source import TokenSource, evaluate_tokens

        ops = [_mk_op("A")]
        sources = [TokenSource(
            token="t", condition="*",
            aggregate="distinct", target_room="Mfg",
            attr="skill_icon",
        )]
        result = evaluate_tokens(sources, ops)
        assert result["t"] == 0.0


# ─── Phase A6: 集成测试 — TokenSource vs 旧函数输出对齐 ─────────────────


class TestIntegrationFactionRoom:
    """TokenSource 与 synergy_faction_room 计数对齐"""

    def _token(self, ops, token_name):
        from steward_core.synergy.token_maps import PHASE_A_SOURCES
        from steward_core.token_source import evaluate_tokens
        result = evaluate_tokens(PHASE_A_SOURCES, ops)
        return result.get(token_name, 0.0)

    def test_reserve1_计数一致(self):
        ops = [
            _mk_op("芬", team_id="reserve1"),
            _mk_op("克洛丝", team_id="reserve1"),
            _mk_op("其他", team_id="other"),
        ]
        assert self._token(ops, "reserve1_mfg") == 2.0

    def test_glasgow_计数一致(self):
        ops = [
            _mk_op("摩根", group_id="glasgow"),
            _mk_op("因陀罗", group_id="glasgow"),
            _mk_op("戴菲恩", group_id="glasgow"),
        ]
        assert self._token(ops, "glasgow_trade") == 3.0

    def test_laterano_计数一致(self):
        ops = [
            _mk_op("新约能天使", nation_id="laterano"),
            _mk_op("安比尔", nation_id="laterano"),
        ]
        assert self._token(ops, "laterano_trade") == 2.0


class TestIntegrationPerOp:
    """TokenSource 与 _eval_per_op 计数对齐"""

    def test_pinus_四骑士计数一致(self):
        from steward_core.token_source import TokenSource, evaluate_tokens
        ops = [
            _mk_op("焰尾", group_id="pinus", nation_id="kazimierz"),
            _mk_op("野鬃", group_id="pinus", nation_id="kazimierz"),
            _mk_op("灰毫", group_id="pinus", nation_id="kazimierz"),
            _mk_op("远牙", group_id="pinus", nation_id="kazimierz"),
        ]
        sources = [
            TokenSource(token="pinus", condition="group_id=pinus"),
            TokenSource(token="knight", condition="is_knight"),
        ]
        result = evaluate_tokens(sources, ops)
        assert result["pinus"] == 4.0
        assert result["knight"] == 4.0

    def test_黑钢计数一致(self):
        from steward_core.token_source import TokenSource, evaluate_tokens
        ops = [_mk_op("涤火杰西卡", group_id="blacksteel")]
        result = evaluate_tokens([TokenSource(token="t", condition="group_id=blacksteel")], ops)
        assert result["t"] == 1.0

    def test_叙拉古计数一致(self):
        from steward_core.token_source import TokenSource, evaluate_tokens
        ops = [_mk_op("八幡海铃", nation_id="siracusa")]
        result = evaluate_tokens([TokenSource(token="t", condition="nation_id=siracusa")], ops)
        assert result["t"] == 1.0

    def test_karlan3_阈值达成(self):
        from steward_core.token_source import TokenSource, evaluate_tokens
        ops = [
            _mk_op("银灰", group_id="karlan"),
            _mk_op("初雪", group_id="karlan"),
            _mk_op("崖心", group_id="karlan"),
        ]
        result = evaluate_tokens([TokenSource(token="t", condition="count_ge:karlan=3")], ops)
        assert result["t"] == 1.0

    def test_glasgow_戴菲恩计数一致(self):
        from steward_core.token_source import TokenSource, evaluate_tokens
        ops = [_mk_op("戴菲恩", group_id="glasgow")]
        result = evaluate_tokens([TokenSource(token="t", condition="group_id=glasgow")], ops)
        assert result["t"] == 1.0

    def test_karlan_灵知惩罚计数一致(self):
        from steward_core.token_source import TokenSource, evaluate_tokens
        ops = [_mk_op("灵知", group_id="karlan"), _mk_op("银灰", group_id="karlan")]
        result = evaluate_tokens([TokenSource(token="t", condition="group_id=karlan")], ops)
        assert result["t"] == 2.0


# ─── Phase B7 补充：延期项解锁 ────────────────────────────────────


class TestPhaseB7FacilityGroupAlign:
    """synergy_facility_group 与 TokenSource 集成对齐"""

    def test_facility_group_elite_count(self):
        from steward_core.synergy.token_maps import PHASE_B_FACILITY_GROUP
        from steward_core.token_source import evaluate_tokens
        from steward_core.synergy.facility_group import count_facilities_with_group
        from steward_core.solver.slot.context import SlotContext, SlotAssignment, WindowState
        from steward_core.models import RoomConfig, LayoutConfig

        layout = LayoutConfig(rooms=[
            RoomConfig("Trade", 0, 3, "Money"),
            RoomConfig("Trade", 1, 3, "Money"),
            RoomConfig("Office", 0, 3),
        ])
        op1 = _mk_op("A", group_id="elite")
        op2 = _mk_op("B", group_id="elite")
        ctx = SlotContext(
            operators=[op1, op2],
            op_lookup={"A": op1, "B": op2},
            layout=layout,
            windows=[WindowState(assignments=[
                SlotAssignment("t0", "Trade", "Money", "A", 0),
                SlotAssignment("t1", "Trade", "Money", "B", 1),
            ])],
        )

        tokens = evaluate_tokens(PHASE_B_FACILITY_GROUP, [], ctx)
        assert tokens["elite_facilities"] == 1.0  # 2 elite → 1 设施类型 (Trade)

        # 旧函数对齐
        assignments = ctx.build_all_assignments(window_idx=0)
        old_count = count_facilities_with_group(assignments, "elite")
        assert old_count == 1


class TestPhaseB7FacilityCountAlign:
    """synergy_facility_count 纯计数部分与 TokenSource 对齐"""

    def test_factory_count_tokens(self):
        from steward_core.synergy.token_maps import PHASE_B_FACTORY_COUNT
        from steward_core.token_source import evaluate_tokens
        from steward_core.models import RoomConfig, LayoutConfig
        from steward_core.solver.slot.context import SlotContext

        layout = LayoutConfig(rooms=[
            RoomConfig("Trade", 0, 3, "Money"),
            RoomConfig("Mfg", 0, 3, "CombatRecord"),
            RoomConfig("Mfg", 1, 3, "PureGold"),
            RoomConfig("Power", 0, 3),
            RoomConfig("Power", 1, 3),
        ])
        ctx = SlotContext(operators=[], op_lookup={}, layout=layout)
        tokens = evaluate_tokens(PHASE_B_FACTORY_COUNT, [], ctx)

        # synergy_facility_count 内部对应值
        assert tokens["trade_rooms"] == 1.0
        assert tokens["mfg_rooms"] == 2.0
        assert tokens["power_rooms"] == 2.0


# ─── Phase B7 收尾：FACILITY_ATTRS + TRADE_SHARE + 全量纳入 ───────


class TestPhaseB7FacilityAttrs:
    """attribute_sum + distinct 布局聚合"""

    def test_dorm_levels_sum(self):
        from steward_core.synergy.token_maps import PHASE_B_FACILITY_ATTRS
        from steward_core.token_source import evaluate_tokens
        from steward_core.models import RoomConfig, LayoutConfig
        from steward_core.solver.slot.context import SlotContext

        layout = LayoutConfig(rooms=[
            RoomConfig("Dormitory", 0, 5, level=3),
            RoomConfig("Dormitory", 1, 5, level=3),
            RoomConfig("Dormitory", 2, 5, level=2),
        ])
        ctx = SlotContext(operators=[], op_lookup={}, layout=layout)
        tokens = evaluate_tokens(PHASE_B_FACILITY_ATTRS, [], ctx)
        assert tokens["dorm_levels"] == 8.0  # 3 + 3 + 2

    def test_meeting_level(self):
        from steward_core.synergy.token_maps import PHASE_B_FACILITY_ATTRS
        from steward_core.token_source import evaluate_tokens
        from steward_core.models import RoomConfig, LayoutConfig
        from steward_core.solver.slot.context import SlotContext

        layout = LayoutConfig(rooms=[RoomConfig("Reception", 0, 3, level=3)])
        ctx = SlotContext(operators=[], op_lookup={}, layout=layout)
        tokens = evaluate_tokens(PHASE_B_FACILITY_ATTRS, [], ctx)
        assert tokens["meeting_level"] == 3.0

    def test_mfg_recipe_types_distinct(self):
        from steward_core.synergy.token_maps import PHASE_B_FACILITY_ATTRS
        from steward_core.token_source import evaluate_tokens
        from steward_core.models import RoomConfig, LayoutConfig
        from steward_core.solver.slot.context import SlotContext

        layout = LayoutConfig(rooms=[
            RoomConfig("Mfg", 0, 3, "CombatRecord"),
            RoomConfig("Mfg", 1, 3, "PureGold"),
            RoomConfig("Mfg", 2, 3, "CombatRecord"),
        ])
        ctx = SlotContext(operators=[], op_lookup={}, layout=layout)
        tokens = evaluate_tokens(PHASE_B_FACILITY_ATTRS, [], ctx)
        assert tokens["mfg_recipe_types"] == 2.0  # CR + PG, 去重

    def test_train_level(self):
        from steward_core.synergy.token_maps import PHASE_B_FACILITY_ATTRS
        from steward_core.token_source import evaluate_tokens
        from steward_core.models import RoomConfig, LayoutConfig
        from steward_core.solver.slot.context import SlotContext

        layout = LayoutConfig(rooms=[RoomConfig("Training", 0, 3, level=3)])
        ctx = SlotContext(operators=[], op_lookup={}, layout=layout)
        tokens = evaluate_tokens(PHASE_B_FACILITY_ATTRS, [], ctx)
        assert tokens["train_level"] == 3.0


class TestPhaseB7TradeShare:
    """exclude_self 贸易分享"""

    def test_exclude_self_effect(self):
        from steward_core.synergy.token_maps import PHASE_B_TRADE_SHARE
        from steward_core.token_source import evaluate_tokens

        ops = [_mk_op("A"), _mk_op("B"), _mk_op("C")]
        tokens = evaluate_tokens(PHASE_B_TRADE_SHARE, ops)
        # exclude_self: count=3 → 3-1=2（每持有者减自身，非全局减1）
        # 因此 3 持有者各自看到 count=2
        assert tokens["trade_share_houshao"] == 2.0


class TestComputeRoomTokensAllSources:
    """compute_room_tokens 全量纳入"""

    def test_all_sources_compute(self):
        from steward_core.token_source import compute_room_tokens

        ops = [_mk_op("A")]
        room_tokens = compute_room_tokens(ops)
        # 不传 ctx，depends_on 源返回 0.0
        # 纯 counting 源应有值
        assert "rhine_global" in room_tokens
        # 新纳入列表应有 key 存在
        assert "trade_eff_total" in room_tokens
        assert "siye_in_base" in room_tokens
        assert "trade_share_houshao" in room_tokens
        assert "wisudell_hedley" in room_tokens


# ─── Phase B7 解锁：自动化 + 归零变体 ──────────────────────────────


class TestAutomationZeroingConditions:
    """is_automation_holder + is_zeroing_variant_holder 派生布尔"""

    def test_is_automation_holder_buff_match(self):
        from steward_core.token_source import _build_matcher

        s = _mk_mfg_skill("manu_prod_spd&power[000]")
        op = _mk_op("A", skills=[s])
        matcher = _build_matcher("is_automation_holder")
        assert matcher(op) is True

    def test_is_automation_holder_name_fallback(self):
        from steward_core.token_source import _build_matcher

        op = _mk_op("森蚺")
        matcher = _build_matcher("is_automation_holder")
        assert matcher(op) is True

    def test_is_not_automation_holder(self):
        from steward_core.token_source import _build_matcher

        op = _mk_op("A")
        matcher = _build_matcher("is_automation_holder")
        assert matcher(op) is False

    def test_is_zeroing_variant_holder_match(self):
        from steward_core.token_source import _build_matcher

        s = _mk_mfg_skill("manu_prod_spd&manu[000]")
        op = _mk_op("A", skills=[s])
        matcher = _build_matcher("is_zeroing_variant_holder")
        assert matcher(op) is True

    def test_automation_count_token(self):
        from steward_core.synergy.token_maps import PHASE_B_AUTOMATION
        from steward_core.token_source import evaluate_tokens

        s = _mk_mfg_skill("manu_prod_spd&power[000]")
        ops = [_mk_op("A", skills=[s]), _mk_op("B", skills=[s]), _mk_op("C")]
        tokens = evaluate_tokens(PHASE_B_AUTOMATION, ops)
        assert tokens["automation_count"] == 2.0

    def test_zeroing_variant_count_token(self):
        from steward_core.synergy.token_maps import PHASE_B_ZEROING_VARIANT
        from steward_core.token_source import evaluate_tokens

        s = _mk_mfg_skill("manu_prod_spd&manu[100]")
        ops = [_mk_op("A", skills=[s])]
        tokens = evaluate_tokens(PHASE_B_ZEROING_VARIANT, ops)
        assert tokens["zeroing_variant_count"] == 1.0
