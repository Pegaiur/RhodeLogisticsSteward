"""控制中枢 / 剩余设施 / 冷启动 单元测试

覆盖 solver/slot/control.py、remaining.py、_cold_start.py。
"""

import pytest

from steward_core.models import LayoutConfig
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import SlotContext
from steward_core.solver.slot.control import phase_control
from steward_core.solver.slot.remaining import (
    phase_remaining,
    _product_for,
    _make_slot_id_inline,
)
from steward_core.solver.slot._cold_start import (
    cold_start_ctrl_ops,
    cold_start_dorm_ops,
)
from tests.helpers import dummy_op, mk_op, mk_simple_skill


# ─── control ─────────────────────────────────────────────────────

class TestPhaseControl:
    @pytest.fixture
    def ops(self):
        return [
            dummy_op("char_a", "A"),
            dummy_op("char_b", "B"),
            dummy_op("char_c", "C"),
        ]

    def test_no_control_skill_no_fill(self, ops):
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_control(ctx)
        assert ctx.ops_of_type(0, "Control") == []

    def test_no_crash_empty_d(self, ops):
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_control(ctx, 0, {})

    def test_single_control_op_placed(self):
        ops = [
            mk_op("中枢A", [mk_simple_skill("Control", 0.0, "ctrl_a")]),
            dummy_op("char_b", "B"),
        ]
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_control(ctx)
        ctrl = ctx.ops_of_type(0, "Control")
        assert len(ctrl) >= 1
        assert "中枢A" in ctrl

    def test_multiple_control_ops_best_chosen(self):
        ops = [
            mk_op("中枢A", [mk_simple_skill("Control", 0.0, "ctrl_a")]),
            mk_op("中枢B", [mk_simple_skill("Control", 0.0, "ctrl_b")]),
        ]
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_control(ctx)
        ctrl = ctx.ops_of_type(0, "Control")
        assert 1 <= len(ctrl) <= 2

    def test_already_full_skips(self):
        ops = [
            mk_op("中枢A", [mk_simple_skill("Control", 0.0, "ctrl_a")]),
            mk_op("中枢B", [mk_simple_skill("Control", 0.0, "ctrl_b")]),
            mk_op("中枢C", [mk_simple_skill("Control", 0.0, "ctrl_c")]),
            mk_op("中枢D", [mk_simple_skill("Control", 0.0, "ctrl_d")]),
            mk_op("中枢E", [mk_simple_skill("Control", 0.0, "ctrl_e")]),
            mk_op("中枢F", [mk_simple_skill("Control", 0.0, "ctrl_f")]),
        ]
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        # 预填满 5 个槽位
        for i, name in enumerate(["中枢A", "中枢B", "中枢C", "中枢D", "中枢E"]):
            ctx.place(0, f"control_0_{i}", name)
        before = ctx.ops_of_type(0, "Control")
        phase_control(ctx)
        after = ctx.ops_of_type(0, "Control")
        assert before == after


# ─── remaining ────────────────────────────────────────────────────

class TestPhaseRemaining:
    @pytest.fixture
    def ops(self):
        return [
            dummy_op("char_a", "A"),
            dummy_op("char_b", "B"),
            dummy_op("char_c", "C"),
        ]

    def test_no_crash_empty_skills(self, ops):
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_remaining(ctx)
        assert isinstance(ctx.ops_of_type(0, "Power"), list)

    def test_power_op_placed(self):
        ops = [
            mk_op("发电A", [mk_simple_skill("Power", 10.0, "pw_a")]),
            dummy_op("char_b", "B"),
        ]
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_remaining(ctx)
        power = ctx.ops_of_type(0, "Power")
        assert len(power) >= 1
        assert "发电A" in power

    def test_reception_op_placed(self):
        ops = [
            mk_op("会客A", [mk_simple_skill("Reception", 10.0, "rc_a")]),
            dummy_op("char_b", "B"),
        ]
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_remaining(ctx)
        reception = ctx.ops_of_type(0, "Reception")
        assert len(reception) >= 1

    def test_office_op_placed(self):
        ops = [
            mk_op("办公室A", [mk_simple_skill("Office", 10.0, "of_a")]),
            dummy_op("char_b", "B"),
        ]
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_remaining(ctx)
        office = ctx.ops_of_type(0, "Office")
        assert len(office) >= 1

    def test_dorm_op_placed(self):
        ops = [
            mk_op("宿舍A", [mk_simple_skill("Dormitory", 10.0, "dm_a")]),
            dummy_op("char_b", "B"),
        ]
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        phase_remaining(ctx)
        dorm = ctx.ops_of_type(0, "Dormitory")
        assert len(dorm) >= 1


class TestProductFor:
    def test_power(self):
        assert _product_for("Power") == ""

    def test_reception(self):
        assert _product_for("Reception") == "General"

    def test_office(self):
        assert _product_for("Office") == "HR"

    def test_dormitory(self):
        assert _product_for("Dormitory") == "Rest"

    def test_unknown(self):
        assert _product_for("Unknown") == ""


class TestMakeSlotID:
    def test_mfg(self):
        assert _make_slot_id_inline("Mfg", 0, 2) == "mfg_0_2"

    def test_trade(self):
        assert _make_slot_id_inline("Trade", 1, 0) == "trade_1_0"

    def test_power(self):
        assert _make_slot_id_inline("Power", 2, 0) == "power_2_0"

    def test_unknown_fallback(self):
        assert _make_slot_id_inline("Foo", 0, 1) == "foo_0_1"


# ─── cold_start ──────────────────────────────────────────────────

class TestColdStart:
    @pytest.fixture
    def ops(self):
        return [
            dummy_op("char_a", "A"),
            dummy_op("char_b", "B"),
        ]

    def test_ctrl_ops_empty(self, ops):
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        result = cold_start_ctrl_ops(ctx, 0)
        assert result == []

    def test_dorm_ops_empty(self, ops):
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        result = cold_start_dorm_ops(ctx, 0)
        assert result == []

    def test_ctrl_ops_with_skills(self):
        ops = [
            mk_op("中枢A", [mk_simple_skill("Control", 0.0, "ctrl_a")]),
            mk_op("中枢B", [mk_simple_skill("Control", 0.0, "ctrl_b")]),
        ]
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        result = cold_start_ctrl_ops(ctx, 0)
        assert 1 <= len(result) <= 2

    def test_dorm_ops_with_skills(self):
        ops = [
            mk_op("宿舍A", [mk_simple_skill("Dormitory", 10.0, "dm_a")]),
            mk_op("宿舍B", [mk_simple_skill("Dormitory", 10.0, "dm_b")]),
        ]
        ctx = SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )
        result = cold_start_dorm_ops(ctx, 0)
        assert 1 <= len(result) <= 2
