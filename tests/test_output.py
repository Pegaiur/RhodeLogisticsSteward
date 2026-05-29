"""输出模块测试 (output.py)

验证 MAA 基建排班协议 v5.x 字段完整性。
所有测试通过内存构造，不依赖磁盘文件。
"""

import json
import tempfile
from pathlib import Path

import pytest

from steward_core.models import RoomAssignment, ShiftPlan, SolveResult
from steward_core.output import to_json, save_json, _new_id, _build_schedule_type


_MAA_REQUIRED_KEYS = {
    "id", "title", "description", "buildingType", "planTimes",
    "scheduleType", "plans",
}

_PLAN_REQUIRED_KEYS = {
    "name", "description", "period", "Fiammetta", "drones", "rooms",
}

_DRONES_REQUIRED_KEYS = {"enable", "room", "index", "order"}

_FIAMMETTA_REQUIRED_KEYS = {"enable", "target", "order"}

_ROOM_REQUIRED_KEYS = {"operators", "sort", "autofill"}


def _mk_plan(name: str = "早班", assignments: list[RoomAssignment] | None = None) -> ShiftPlan:
    return ShiftPlan(
        name=name,
        assignments=assignments or [],
        period_from="08:00",
        period_to="19:59",
        drone_room="Trade",
        drone_index=0,
        drone_order="pre",
    )


def _mk_mfg(name: str, index: int = 0, product: str = "CombatRecord") -> RoomAssignment:
    return RoomAssignment("Mfg", index, [name, "A", "B"], product)


def _mk_trade(name: str, index: int = 0) -> RoomAssignment:
    return RoomAssignment("Trade", index, [name, "C", "D"], "Money")


class TestTopLevelSchema:
    """顶层字段完整性"""

    def test_包含所有必需顶层键(self):
        result = SolveResult(plans=[_mk_plan()])
        data = to_json(result)
        assert _MAA_REQUIRED_KEYS <= data.keys()

    def test_id_为15到16位数字(self):
        result = SolveResult(plans=[_mk_plan()])
        data = to_json(result)
        assert 10**15 <= data["id"] <= 10**16
        assert isinstance(data["id"], int)

    def test_id_每次调用不一致(self):
        result = SolveResult(plans=[_mk_plan()])
        id1 = to_json(result)["id"]
        id2 = to_json(result)["id"]
        assert id1 != id2

    def test_buildingType_为243(self):
        result = SolveResult(plans=[_mk_plan()])
        data = to_json(result)
        assert data["buildingType"] == 243

    def test_planTimes_为单班(self):
        result = SolveResult(plans=[_mk_plan()])
        data = to_json(result)
        assert data["planTimes"] == "单班"

    def test_description_存在(self):
        result = SolveResult(plans=[_mk_plan()])
        data = to_json(result)
        assert "RhodeLogisticsSteward" in data["description"]

    def test_title_使用传入值(self):
        result = SolveResult(plans=[_mk_plan()])
        data = to_json(result, title="自定义标题")
        assert data["title"] == "自定义标题"

    def test_空plans不出错(self):
        result = SolveResult(plans=[])
        data = to_json(result)
        assert data["plans"] == []
        assert data["scheduleType"] == {}


class TestScheduleType:
    """scheduleType 统计"""

    def test_空排班_scheduleType_仅含planTimes(self):
        plan = _mk_plan(assignments=[])
        st = _build_schedule_type(plan)
        assert st == {"planTimes": 1}

    def test_制造站4间_贸易站2间_发电站3间(self):
        assignments = [
            _mk_mfg("mf0", 0), _mk_mfg("mf1", 1),
            _mk_mfg("mf2", 2), _mk_mfg("mf3", 3),
            _mk_trade("tr0", 0), _mk_trade("tr1", 1),
            RoomAssignment("Power", 0, ["P0"]),
            RoomAssignment("Power", 1, ["P1"]),
            RoomAssignment("Power", 2, ["P2"]),
        ]
        plan = _mk_plan(assignments=assignments)
        st = _build_schedule_type(plan)
        assert st["manufacture"] == 4
        assert st["trading"] == 2
        assert st["power"] == 3
        assert st["planTimes"] == 1


class TestPlanSchema:
    """plan 字段完整性"""

    def test_包含所有必需plan键(self):
        plan = _mk_plan(assignments=[_mk_mfg("mf0")])
        result = SolveResult(plans=[plan])
        data = to_json(result)
        p0 = data["plans"][0]
        assert _PLAN_REQUIRED_KEYS <= p0.keys()

    def test_description_含plan名(self):
        plan = _mk_plan(name="晚班", assignments=[_mk_mfg("mf0")])
        result = SolveResult(plans=[plan])
        data = to_json(result)
        assert "晚班" in data["plans"][0]["description"]

    def test_Fiammetta_单班次不启用(self):
        plan = _mk_plan(assignments=[_mk_mfg("mf0")])
        result = SolveResult(plans=[plan])
        data = to_json(result)
        f = data["plans"][0]["Fiammetta"]
        assert _FIAMMETTA_REQUIRED_KEYS <= f.keys()
        assert f["enable"] is False

    def test_drones_包含所有必需键(self):
        plan = _mk_plan(assignments=[_mk_mfg("mf0")])
        result = SolveResult(plans=[plan])
        data = to_json(result)
        d = data["plans"][0]["drones"]
        assert _DRONES_REQUIRED_KEYS <= d.keys()
        assert d["enable"] is True

    def test_drones_room_使用协议键名(self):
        plan = _mk_plan()
        result = SolveResult(plans=[plan])
        data = to_json(result)
        d = data["plans"][0]["drones"]
        assert d["room"] == "trading"

    def test_drones_index_为1_based(self):
        plan = _mk_plan()
        result = SolveResult(plans=[plan])
        data = to_json(result)
        d = data["plans"][0]["drones"]
        assert d["index"] == 1


class TestRoomSchema:
    """rooms 条目字段完整性"""

    def test_房间条目包含所有必需键(self):
        plan = _mk_plan(assignments=[_mk_mfg("mf0")])
        result = SolveResult(plans=[plan])
        data = to_json(result)
        rooms = data["plans"][0]["rooms"]
        assert "manufacture" in rooms
        entry = rooms["manufacture"][0]
        assert _ROOM_REQUIRED_KEYS <= entry.keys()

    def test_sort_默认为False(self):
        plan = _mk_plan(assignments=[_mk_mfg("mf0")])
        result = SolveResult(plans=[plan])
        data = to_json(result)
        entry = data["plans"][0]["rooms"]["manufacture"][0]
        assert entry["sort"] is False

    def test_autofill_按赋值传递(self):
        plan = _mk_plan(assignments=[
            RoomAssignment("Mfg", 0, ["mf0"], autofill=True),
        ])
        result = SolveResult(plans=[plan])
        data = to_json(result)
        entry = data["plans"][0]["rooms"]["manufacture"][0]
        assert entry["autofill"] is True

    def test_product_映射为MAA枚举值(self):
        plan = _mk_plan(assignments=[_mk_mfg("mf0", product="PureGold")])
        result = SolveResult(plans=[plan])
        data = to_json(result)
        entry = data["plans"][0]["rooms"]["manufacture"][0]
        assert entry["product"] == "Pure Gold"

    def test_product_CombatRecord映射(self):
        plan = _mk_plan(assignments=[_mk_mfg("mf0", product="CombatRecord")])
        result = SolveResult(plans=[plan])
        data = to_json(result)
        entry = data["plans"][0]["rooms"]["manufacture"][0]
        assert entry["product"] == "Battle Record"

    def test_无product不输出该字段(self):
        plan = _mk_plan(assignments=[
            RoomAssignment("Control", 0, ["CtrlA"]),
        ])
        result = SolveResult(plans=[plan])
        data = to_json(result)
        entry = data["plans"][0]["rooms"]["control"][0]
        assert "product" not in entry

    def test_未满index用skip占位(self):
        plan = _mk_plan(assignments=[_mk_mfg("mf1", index=1)])
        result = SolveResult(plans=[plan])
        data = to_json(result)
        mfg_rooms = data["plans"][0]["rooms"]["manufacture"]
        assert len(mfg_rooms) >= 2
        assert mfg_rooms[0] == {"skip": True}

    def test_所有房间类型键使用协议命名(self):
        assignments = [
            RoomAssignment("Control", 0, ["A"]),
            RoomAssignment("Trade", 0, ["B"]),
            RoomAssignment("Mfg", 0, ["C"]),
            RoomAssignment("Power", 0, ["D"]),
            RoomAssignment("Reception", 0, ["E"]),
            RoomAssignment("Office", 0, ["F"]),
            RoomAssignment("Dormitory", 0, ["G"]),
        ]
        plan = _mk_plan(assignments=assignments)
        result = SolveResult(plans=[plan])
        data = to_json(result)
        rooms = data["plans"][0]["rooms"]
        assert set(rooms.keys()) == {
            "control", "trading", "manufacture", "power",
            "meeting", "hire", "dormitory",
        }


class TestMultiPlan:
    """多 plan 场景"""

    def test_两个plan各自有独立字段(self):
        p1 = _mk_plan(name="早班", assignments=[_mk_mfg("mf0", 0)])
        p2 = _mk_plan(name="晚班", assignments=[_mk_mfg("mf1", 1)])
        result = SolveResult(plans=[p1, p2])
        data = to_json(result)
        assert len(data["plans"]) == 2
        assert data["plans"][0]["name"] == "早班"
        assert data["plans"][1]["name"] == "晚班"

    def test_scheduleType_使用第一个plan统计(self):
        p1 = _mk_plan(name="早班", assignments=[
            _mk_mfg("mf0", 0), _mk_mfg("mf1", 1),
        ])
        p2 = _mk_plan(name="晚班", assignments=[_mk_mfg("mf2", 2)])
        result = SolveResult(plans=[p1, p2])
        data = to_json(result)
        assert data["scheduleType"]["manufacture"] == 2


class TestSaveJson:
    """磁盘写入"""

    def test_可写入磁盘并可重新读取(self):
        plan = _mk_plan(assignments=[_mk_mfg("mf0")])
        result = SolveResult(plans=[plan])

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8",
        ) as f:
            out_path = Path(f.name)

        try:
            save_json(result, out_path)
            with open(out_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            assert 10**15 <= loaded["id"] <= 10**16
            assert loaded["buildingType"] == 243
            assert loaded["planTimes"] == "单班"
            assert loaded["plans"][0]["name"] == "早班"
            assert "manufacture" in loaded["plans"][0]["rooms"]
            assert loaded["plans"][0]["drones"]["enable"] is True
        finally:
            out_path.unlink(missing_ok=True)
