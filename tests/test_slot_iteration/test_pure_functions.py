"""slot_iteration.py 纯函数单元测试"""

import pytest
from steward_core.models import Operator, Skill, EfficiencyMap, RoomAssignment, LayoutConfig
from steward_core.solver.slot_iteration import (
    STATE_DIMENSIONS,
    IterationContext,
    extract_state_vector,
    compute_partial_derivatives,
    contribution,
)


def make_op(name, char_id, room_type, *, efficiency=0.0, product=None, buff_id="", rarity=5):
    skills = []
    if buff_id or efficiency > 0:
        eff_raw = {}
        if product:
            eff_raw[product] = efficiency
        else:
            eff_raw["all"] = efficiency
        skills = [Skill(
            buff_id=buff_id or f"test_{char_id}",
            buff_name="",
            skill_icon="",
            room_type=room_type,
            efficient=EfficiencyMap(raw=eff_raw),
        )]
    return Operator(
        char_id=char_id, name=name, rarity=rarity,
        skills=skills, nation_id="test", group_id="test",
    )


def _ctx(window_hours=12.0):
    return IterationContext(
        window_index=0,
        window_hours=window_hours,
        S={d: 0.0 for d in STATE_DIMENSIONS},
        D={d: 0.0 for d in STATE_DIMENSIONS},
        lambda_op={},
    )


class TestExtractStateVector:

    def test_empty_assignments(self):
        S = extract_state_vector([], {})
        assert S["perception"] == 0.0
        assert S["yanhuo"] == 0.0
        assert S["monster_cuisine"] == 0.0
        assert S["silent_resonance"] == 0.0
        assert S["engineering_robots"] == 64.0

    def test_ling_only_in_control(self):
        ling = make_op("令", "ling", "Control", buff_id="ling_yanhuo_15")
        ops = {"令": ling}
        assignments = [
            RoomAssignment(room_type="Control", room_index=0, operators=["令"]),
        ]
        S = extract_state_vector(assignments, ops)
        assert S["yanhuo"] == 15.0
        assert S["perception"] == 0.0

    def test_full_control_plus_dorm_generates_perception(self):
        ling = make_op("令", "ling", "Control", buff_id="ling_yanhuo_15")
        xi = make_op("夕", "xi", "Control", buff_id="xi_perception_10")
        suxin = make_op("塑心", "suxin", "Dormitory", buff_id="dorm_rec_bd_n1_n3[000]")
        rsm = make_op("迷迭香", "rosmontis", "Mfg", buff_id="dorm_rec_bd_n1_n3[000]")
        ops = {"令": ling, "夕": xi, "塑心": suxin, "迷迭香": rsm}
        assignments = [
            RoomAssignment(room_type="Control", room_index=0, operators=["令", "夕"]),
            RoomAssignment(room_type="Dormitory", room_index=0, operators=["塑心"]),
            RoomAssignment(room_type="Mfg", room_index=0, operators=["迷迭香"], product="CombatRecord"),
        ]
        S = extract_state_vector(assignments, ops)
        assert S["yanhuo"] >= 0
        assert S["perception"] >= 0
        assert S["silent_resonance"] >= 0


class TestComputePartialDerivatives:

    def test_no_readers_returns_zero(self):
        op = make_op("普通制造", "mfg_001", "Mfg", efficiency=30.0, product="CombatRecord")
        ops = {"普通制造": op}
        assignments = [
            RoomAssignment(room_type="Mfg", room_index=0, operators=["普通制造"], product="CombatRecord"),
        ]
        D = compute_partial_derivatives(assignments, 12.0, ops)
        assert all(D[d] == 0.0 for d in STATE_DIMENSIONS)

    def test_marginal_positive_for_buff_consumers(self):
        rsm = make_op("迷迭香", "rosmontis", "Mfg", efficiency=0.0, product="CombatRecord", buff_id="rosmontis_perception")
        ops = {"迷迭香": rsm}
        assignments = [
            RoomAssignment(room_type="Mfg", room_index=0, operators=["迷迭香"], product="CombatRecord"),
        ]
        D = compute_partial_derivatives(assignments, 12.0, ops)
        assert D["perception"] > 0.0

    def test_no_reader_when_not_in_mfg_trade(self):
        rsm = make_op("迷迭香", "rosmontis", "Dormitory", efficiency=0.0, buff_id="rosmontis_perception")
        ops = {"迷迭香": rsm}
        assignments = [
            RoomAssignment(room_type="Dormitory", room_index=0, operators=["迷迭香"]),
        ]
        D = compute_partial_derivatives(assignments, 12.0, ops)
        assert D["perception"] == 0.0


class TestContribution:

    def test_control_contribution_positive_for_buff_writer(self):
        ling = make_op("令", "ling", "Control", buff_id="ling_yanhuo_15")
        ops = {"令": ling}
        ctx = _ctx()
        ctx = IterationContext(
            window_index=ctx.window_index,
            window_hours=ctx.window_hours,
            S=ctx.S,
            D={**ctx.D, "yanhuo": 10.0},
            lambda_op=ctx.lambda_op,
            ratios=ctx.ratios,
        )
        assignments = [
            RoomAssignment(room_type="Control", room_index=0, operators=[]),
        ]
        c = contribution("令", "Control", ctx, ops, assignments)
        assert c > 0.0

    def test_power_contribution_positive(self):
        op = make_op("格雷伊", "greyy", "Power", efficiency=20.0, product="Drone")
        ops = {"格雷伊": op}
        ctx = _ctx()
        c = contribution("格雷伊", "Power", ctx, ops, [])
        assert c > 0.0

    def test_power_contribution_zero_for_no_skill(self):
        op = make_op("无技能", "none_001", "Power", efficiency=0.0)
        ops = {"无技能": op}
        ctx = _ctx()
        c = contribution("无技能", "Power", ctx, ops, [])
        assert c == 0.0

    def test_reception_contribution_positive(self):
        op = make_op("线索干员", "rec_001", "Reception", efficiency=25.0, product="General")
        ops = {"线索干员": op}
        ctx = _ctx()
        c = contribution("线索干员", "Reception", ctx, ops, [])
        assert c > 0.0

    def test_office_contribution_positive(self):
        op = make_op("人事干员", "hr_001", "Office", efficiency=40.0, product="HR")
        ops = {"人事干员": op}
        ctx = _ctx()
        c = contribution("人事干员", "Office", ctx, ops, [])
        assert c > 0.0

    def test_dorm_contribution_positive_for_buff_provider(self):
        suxin = make_op("塑心", "suxin", "Dormitory", buff_id="dorm_rec_bd_n1_n3[000]")
        rsm = make_op("迷迭香", "rosmontis", "Mfg", efficiency=0.0, product="CombatRecord", buff_id="rosmontis_perception")
        ops = {"塑心": suxin, "迷迭香": rsm}
        assignments = [
            RoomAssignment(room_type="Dormitory", room_index=0, operators=[]),
            RoomAssignment(room_type="Mfg", room_index=0, operators=["迷迭香"], product="CombatRecord"),
        ]
        D = compute_partial_derivatives(assignments, 12.0, ops)
        ctx = IterationContext(
            window_index=0,
            window_hours=12.0,
            S={d: 0.0 for d in STATE_DIMENSIONS},
            D=D,
            lambda_op={},
        )
        c = contribution("塑心", "Dormitory", ctx, ops, assignments)
        assert c >= 0.0

    def test_nonexistent_operator(self):
        ctx = _ctx()
        c = contribution("不存在", "Control", ctx, {}, [])
        assert c == float("-inf")

    def test_unknown_facility(self):
        op = make_op("测试", "test_001", "Mfg", efficiency=25.0)
        ops = {"测试": op}
        ctx = _ctx()
        c = contribution("测试", "Unknown", ctx, ops, [])
        assert c == float("-inf")


class TestIterationContext:

    def test_frozen_prevents_reassignment(self):
        ctx = _ctx()
        with pytest.raises(Exception):
            ctx.S = {"yanhuo": 999.0}

    def test_default_ratios(self):
        ctx = _ctx()
        assert ctx.ratios.reception_to_mfg == 0.10
        assert ctx.ratios.office_to_mfg == 1.10
        assert ctx.ratios.drone_to_mfg == 0.5
        assert ctx.ratios.xp_lmd == 1.3
