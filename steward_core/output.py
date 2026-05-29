"""输出模块

将求解结果格式化为 MAA custom_infrast JSON（符合 MAA 基建排班协议 v5.x）。
"""

import json
import random
from pathlib import Path
from typing import Any

from steward_core.models import SolveResult, ShiftPlan, RoomAssignment

_ROOM_TO_JSON_KEY: dict[str, str] = {
    "Control": "control",
    "Trade": "trading",
    "Mfg": "manufacture",
    "Power": "power",
    "Reception": "meeting",
    "Office": "hire",
    "Dormitory": "dormitory",
}

_PRODUCT_MAP: dict[str, str] = {
    "Money": "LMD",
    "PureGold": "Pure Gold",
    "CombatRecord": "Battle Record",
    "OriginStone": "OriginStone",
    "General": "General",
    "HR": "HR",
}

_ID_RANGE = (10**15, 10**16)


def _new_id() -> int:
    return random.randint(*_ID_RANGE)


def _build_schedule_type(plan: ShiftPlan) -> dict[str, int]:
    counts: dict[str, int] = {"planTimes": 1}
    for a in plan.assignments:
        json_key = _ROOM_TO_JSON_KEY.get(a.room_type, a.room_type.lower())
        counts[json_key] = counts.get(json_key, 0) + 1
    return counts


def _room_to_json(assignment: RoomAssignment) -> dict:
    entry: dict[str, Any] = {
        "operators": assignment.operators,
        "sort": False,
        "autofill": assignment.autofill,
    }
    if assignment.product:
        product_label = _PRODUCT_MAP.get(assignment.product, assignment.product)
        entry["product"] = product_label
    return entry


def _shift_to_json(plan: ShiftPlan) -> dict:
    rooms: dict[str, list[dict]] = {}
    for assignment in plan.assignments:
        json_key = _ROOM_TO_JSON_KEY.get(assignment.room_type, assignment.room_type.lower())

        if json_key not in rooms:
            rooms[json_key] = []

        while len(rooms[json_key]) <= assignment.room_index:
            rooms[json_key].append({"skip": True})

        rooms[json_key][assignment.room_index] = _room_to_json(assignment)

    return {
        "name": plan.name,
        "description": f"由 RhodeLogisticsSteward 自动生成 — {plan.name}",
        "period": [[plan.period_from, plan.period_to]],
        "Fiammetta": {
            "enable": False,
            "target": "",
            "order": "pre",
        },
        "drones": {
            "enable": True,
            "room": _ROOM_TO_JSON_KEY.get(plan.drone_room, plan.drone_room),
            "index": plan.drone_index + 1,
            "order": plan.drone_order,
        },
        "rooms": rooms,
    }


def to_json(result: SolveResult, title: str = "RhodeLogisticsSteward 排班方案") -> dict:
    plans = [_shift_to_json(p) for p in result.plans]
    schedule_type = _build_schedule_type(result.plans[0]) if result.plans else {}
    return {
        "id": _new_id(),
        "title": title,
        "description": "由 RhodeLogisticsSteward 自动生成",
        "buildingType": 243,
        "planTimes": "单班",
        "scheduleType": schedule_type,
        "plans": plans,
    }


def save_json(result: SolveResult, output_path: Path, title: str = "RhodeLogisticsSteward 排班方案") -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = to_json(result, title)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"[输出] 已保存至: {output_path}")
