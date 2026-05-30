"""SlotContext + StateVector 单元测试"""

import pytest

from steward_core.models import LayoutConfig, Operator, Skill
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.context import (
    SlotContext,
    StateVector,
    SlotAssignment,
    WindowState,
    STATE_DIMS,
    _make_slot_id,
)


def _dummy_op(char_id: str, name: str) -> Operator:
    return Operator(char_id=char_id, name=name, skills=[])


class TestStateVector:
    def test_default_zero(self):
        sv = StateVector()
        assert sv.yanhuo == 0.0
        assert sv.perception == 0.0

    def test_getitem(self):
        sv = StateVector(yanhuo=10.0, perception=5.0)
        assert sv["yanhuo"] == 10.0
        assert sv["perception"] == 5.0

    def test_setitem(self):
        sv = StateVector()
        sv["yanhuo"] = 15.0
        assert sv.yanhuo == 15.0

    def test_to_dict(self):
        sv = StateVector(yanhuo=10.0)
        d = sv.to_dict()
        assert d["yanhuo"] == 10.0
        assert d["perception"] == 0.0
        assert len(d) == 5

    def test_from_dict(self):
        sv = StateVector.from_dict({"yanhuo": 20.0, "unknown": 99.0})
        assert sv.yanhuo == 20.0
        assert sv.monster_cuisine == 0.0

    def test_s_max(self):
        sv = StateVector.s_max()
        assert sv.yanhuo == 95.0
        assert sv.perception == 60.0
        assert sv.engineering_robots == 64.0
        assert sv.monster_cuisine == 5.0
        assert sv.silent_resonance == 10.0

    def test_s_max_unknown_layout(self):
        sv = StateVector.s_max(layout_type="unknown")
        assert sv.yanhuo == 95.0


class TestSlotID:
    def test_mfg_id(self):
        assert _make_slot_id("Mfg", 0, 0) == "mfg_0_0"
        assert _make_slot_id("Mfg", 3, 2) == "mfg_3_2"

    def test_trade_id(self):
        assert _make_slot_id("Trade", 1, 0) == "trade_1_0"

    def test_control_id(self):
        assert _make_slot_id("Control", 0, 0) == "control_0_0"

    def test_unknown_type(self):
        assert _make_slot_id("Unknown", 0, 0) == "unknown_0_0"


class TestSlotAssignment:
    def test_empty(self):
        a = SlotAssignment("mfg_0_0", "Mfg", "CombatRecord", "")
        assert a.is_empty

    def test_not_empty(self):
        a = SlotAssignment("mfg_0_0", "Mfg", "CombatRecord", "迷迭香")
        assert not a.is_empty


class TestSlotContext:
    @pytest.fixture
    def ops(self):
        return [
            _dummy_op("char_001", "阿米娅"),
            _dummy_op("char_002", "凯尔希"),
            _dummy_op("char_003", "令"),
        ]

    @pytest.fixture
    def empty_ctx(self, ops):
        return SlotContext.from_layout(
            ops, LayoutConfig.layout_243(), SolverParams(),
        )

    def test_from_layout_creates_correct_slots(self, empty_ctx):
        ctx = empty_ctx
        mfg_slots = ctx.slots_of_type(0, "Mfg")
        assert len(mfg_slots) == 12  # 4 rooms × 3 slots

        trade_slots = ctx.slots_of_type(0, "Trade")
        assert len(trade_slots) == 6  # 2 rooms × 3 slots

        control_slots = ctx.slots_of_type(0, "Control")
        assert len(control_slots) == 5

        power_slots = ctx.slots_of_type(0, "Power")
        assert len(power_slots) == 3

    def test_from_layout_all_empty(self, empty_ctx):
        ctx = empty_ctx
        assert ctx.assigned_names() == set()
        assert ctx.assigned_ids() == set()

    def test_place_and_get(self, empty_ctx):
        ctx = empty_ctx
        ctx.place(0, "mfg_0_0", "迷迭香")
        assert ctx.get_op(0, "mfg_0_0") == "迷迭香"

        ctx.place(0, "mfg_0_0", "泡泡")
        assert ctx.get_op(0, "mfg_0_0") == "泡泡"

    def test_vacate(self, empty_ctx):
        ctx = empty_ctx
        ctx.place(0, "mfg_0_0", "迷迭香")
        name = ctx.vacate(0, "mfg_0_0")
        assert name == "迷迭香"
        assert ctx.get_op(0, "mfg_0_0") == ""

    def test_place_nonexistent_slot_raises(self, empty_ctx):
        with pytest.raises(KeyError):
            empty_ctx.place(0, "nonexistent", "阿米娅")

    def test_assigned_ids(self, ops, empty_ctx):
        ctx = empty_ctx
        ctx.place(0, "mfg_0_0", "阿米娅")
        assert ctx.assigned_ids() == {"char_001"}

    def test_assigned_names(self, empty_ctx):
        ctx = empty_ctx
        ctx.place(0, "mfg_0_0", "阿米娅")
        ctx.place(0, "mfg_0_1", "凯尔希")
        assert ctx.assigned_names() == {"阿米娅", "凯尔希"}

    def test_ops_of_type(self, empty_ctx):
        ctx = empty_ctx
        ctx.place(0, "mfg_0_0", "迷迭香")
        ctx.place(0, "mfg_0_1", "泡泡")
        assert ctx.ops_of_type(0, "Mfg") == ["迷迭香", "泡泡"]

    def test_room_ops(self, empty_ctx):
        ctx = empty_ctx
        ctx.place(0, "mfg_0_0", "迷迭香")
        ctx.place(0, "mfg_0_1", "泡泡")
        ctx.place(0, "mfg_1_0", "其他")
        assert ctx.room_ops(0, "Mfg", 0) == ["迷迭香", "泡泡"]
        assert ctx.room_ops(0, "Mfg", 1) == ["其他"]

    def test_signature_deterministic(self, empty_ctx):
        ctx = empty_ctx
        ctx.place(0, "mfg_0_0", "迷迭香")
        ctx.place(0, "trade_0_0", "巫恋")
        sig1 = ctx.signature()
        sig2 = ctx.signature()
        assert sig1 == sig2

    def test_signature_different_assignments(self, empty_ctx):
        ctx1 = empty_ctx
        ctx1.place(0, "mfg_0_0", "迷迭香")
        ctx2 = SlotContext.from_layout(
            empty_ctx.operators,
            LayoutConfig.layout_243(),
            SolverParams(),
        )
        ctx2.place(0, "mfg_0_0", "泡泡")
        assert ctx1.signature() != ctx2.signature()

    def test_clone_independent(self, empty_ctx):
        ctx = empty_ctx
        ctx.place(0, "mfg_0_0", "迷迭香")
        cloned = ctx.clone()
        cloned.place(0, "mfg_0_0", "泡泡")
        assert ctx.get_op(0, "mfg_0_0") == "迷迭香"
        assert cloned.get_op(0, "mfg_0_0") == "泡泡"

    def test_op_lookup(self, ops, empty_ctx):
        ctx = empty_ctx
        assert ctx.op_lookup["char_001"].name == "阿米娅"

    def test_place_unknown_op_no_error(self, empty_ctx):
        ctx = empty_ctx
        ctx.place(0, "mfg_0_0", "不存在的干员")
        assert ctx.get_op(0, "mfg_0_0") == "不存在的干员"
