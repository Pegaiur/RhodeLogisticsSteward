"""输出模块

将求解结果格式化为 MAA custom_infrast JSON，并提供与基准模板的对比功能。
"""

import json
from pathlib import Path
from typing import Any, Optional

from steward_core.models import SolveResult, ShiftPlan, RoomAssignment

# room_type → MAA JSON key 映射
_ROOM_TO_JSON_KEY: dict[str, str] = {
    "Control": "control",
    "Trade": "trading",
    "Mfg": "manufacture",
    "Power": "power",
    "Reception": "meeting",
    "Office": "hire",
}

# 产物名 → MAA JSON product 值映射
_PRODUCT_MAP: dict[str, str] = {
    "Money": "LMD",
    "PureGold": "Pure Gold",
    "CombatRecord": "Battle Record",
    "OriginStone": "OriginStone",
    "General": "General",
    "HR": "HR",
}


def _room_to_json(assignment: RoomAssignment) -> dict:
    """单个房间分配 → JSON 对象"""
    entry: dict[str, Any] = {
        "operators": assignment.operators,
        "sort": True,
        "autofill": assignment.autofill,
    }
    if assignment.product:
        product_label = _PRODUCT_MAP.get(assignment.product, assignment.product)
        entry["product"] = product_label
    return entry


def _shift_to_json(plan: ShiftPlan) -> dict:
    """单个 ShiftPlan → MAA 排班 JSON"""
    rooms: dict[str, list[dict]] = {}
    for assignment in plan.assignments:
        json_key = _ROOM_TO_JSON_KEY.get(assignment.room_type, assignment.room_type.lower())

        if json_key not in rooms:
            rooms[json_key] = []

        # 确保数组长度 >= room_index+1
        while len(rooms[json_key]) <= assignment.room_index:
            rooms[json_key].append({"skip": True})

        rooms[json_key][assignment.room_index] = _room_to_json(assignment)

    return {
        "name": plan.name,
        "period": [[plan.period_from, plan.period_to]],
        "drones": {
            "room": _ROOM_TO_JSON_KEY.get(plan.drone_room, plan.drone_room),
            "index": plan.drone_index + 1,  # MAA 协议要求 1-based 索引
            "order": plan.drone_order,
        },
        "rooms": rooms,
    }


def to_json(result: SolveResult, title: str = "RhodeLogisticsSteward 排班方案") -> dict:
    """将求解结果转换为 MAA custom_infrast JSON 格式"""
    return {
        "title": title,
        "description": f"由 RhodeLogisticsSteward 自动生成",
        "plans": [_shift_to_json(p) for p in result.plans],
    }


def save_json(result: SolveResult, output_path: Path, title: str = "RhodeLogisticsSteward 排班方案") -> None:
    """将求解结果保存为 MAA custom_infrast JSON 文件"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = to_json(result, title)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"[输出] 已保存至: {output_path}")


# ─── 基准对比 ────────────────────────────────────────────────────

def compare_with_baseline(
    result: SolveResult,
    baseline_path: Path,
) -> dict:
    """将求解结果与 MAA 内置模板做对比

    仅对比排班的核心设施（control/trading/manufacture/power/meeting/hire），
    宿舍和加工站不参与对比。

    Returns:
        {
            "facility_match_rates": { facility: 匹配率 },
            "mismatched_pairs": [ (facility, room, our_op, their_op), ... ],
            "overall_match_rate": 总匹配率,
        }
    """
    baseline = _load_json(baseline_path)
    baseline_plans = baseline.get("plans", [])
    if not baseline_plans:
        return {"error": "基准模板中没有 plans"}

    our_plan = result.plans[0] if result.plans else None
    if our_plan is None:
        return {"error": "求解结果中没有 plan"}

    baseline_rooms = baseline_plans[0].get("rooms", {})

    total_match = 0
    total_slots = 0
    facility_rates: dict[str, float] = {}
    mismatches: list[dict] = []

    for assignment in our_plan.assignments:
        json_key = _ROOM_TO_JSON_KEY.get(assignment.room_type, "")
        baseline_room_list = baseline_rooms.get(json_key, [])
        if assignment.room_index >= len(baseline_room_list):
            continue
        baseline_room = baseline_room_list[assignment.room_index]
        baseline_ops = baseline_room.get("operators", [])

        our_ops = assignment.operators
        # 计算交集
        match_count = len(set(our_ops) & set(baseline_ops))
        slot_count = max(len(our_ops), len(baseline_ops), assignment.autofill and 1 or 0)

        total_match += match_count
        total_slots += slot_count

        rate = match_count / slot_count if slot_count > 0 else 0.0
        facility_rates[f"{assignment.room_type}_{assignment.room_index}"] = rate

        for i, op in enumerate(our_ops):
            if i < len(baseline_ops) and op != baseline_ops[i]:
                mismatches.append({
                    "facility": f"{assignment.room_type}_{assignment.room_index}",
                    "our": op,
                    "baseline": baseline_ops[i],
                })

    overall = total_match / total_slots if total_slots > 0 else 0.0

    return {
        "facility_match_rates": facility_rates,
        "mismatched_pairs": mismatches,
        "overall_match_rate": round(overall, 4),
        "total_matched": total_match,
        "total_slots": total_slots,
    }


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
