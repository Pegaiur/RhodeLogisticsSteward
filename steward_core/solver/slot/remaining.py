"""Phase D: 剩余设施（Power/Reception/Office/Dormitory）contribution 贪心

替代旧 fill_remaining.py + fill_dorm.py。
每种设施通过 contribution(ctx, op_name, facility_type, D=D) 评分，
按槽位逐个竞争选出。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .contribution import contribution

if TYPE_CHECKING:
    from .context import SlotContext


def phase_remaining(
    ctx: "SlotContext",
    window_idx: int = 0,
    D: dict[str, float] | None = None,
) -> None:
    """填充 Power/Reception/Office/Dormitory 槽位

    每种设施按槽位数取 contribution 最高的未分配干员。
    顺序贪心：每选一人后更新 assigned_ids，下一人从剩余池选。
    """
    from .partials import compute_partial_derivatives

    if D is None:
        D = compute_partial_derivatives(ctx, window_idx)

    facility_configs = [
        ("Power", 3),
        ("Reception", 2),
        ("Office", 1),
        ("Dormitory", 20),
    ]

    assigned_ids = ctx.assigned_ids(window_idx)

    for facility_type, total_slots in facility_configs:
        existing = ctx.ops_of_type(window_idx, facility_type)
        filled = len(existing)
        room_count = _room_count_for(ctx, facility_type)

        for _ in range(total_slots - filled):
            best_op_name = None
            best_score = float("-inf")

            for op in ctx.operators:
                if op.char_id in assigned_ids:
                    continue
                if not op.has_skill_for(facility_type, _product_for(facility_type)):
                    continue

                score = contribution(ctx, op.name, facility_type, window_idx, D)
                if score > best_score:
                    best_score = score
                    best_op_name = op.name

            if best_op_name is None:
                break

            existing = ctx.ops_of_type(window_idx, facility_type)
            room_idx = _find_room_with_space(
                ctx, window_idx, facility_type, room_count,
            )
            slot_idx = _next_slot_in_room(ctx, window_idx, facility_type, room_idx)
            slot_id = _make_slot_id_inline(facility_type, room_idx, slot_idx)
            ctx.place(window_idx, slot_id, best_op_name)
            assigned_ids.add(ctx.op_lookup[best_op_name].char_id)


def _product_for(facility_type: str) -> str:
    return {
        "Power": "",
        "Reception": "General",
        "Office": "HR",
        "Dormitory": "Rest",
    }.get(facility_type, "")


def _room_count_for(ctx: "SlotContext", facility_type: str) -> int:
    if ctx.layout is None:
        return 4 if facility_type == "Dormitory" else 3 if facility_type == "Power" else 1
    count = sum(
        1 for r in ctx.layout.rooms if r.room_type == facility_type
    )
    return count


def _find_room_with_space(
    ctx: "SlotContext",
    window_idx: int,
    facility_type: str,
    room_count: int,
) -> int:
    """找到第一个有空位的房间索引"""
    from steward_core.models import LayoutConfig
    layout = ctx.layout if ctx.layout else LayoutConfig.layout_243()
    for room_idx in range(room_count):
        room_slots_config = 0
        for r in layout.rooms:
            if r.room_type == facility_type and r.room_index == room_idx:
                room_slots_config = r.slots
                break
        actual = len(ctx.room_ops(window_idx, facility_type, room_idx))
        if actual < room_slots_config:
            return room_idx
    return 0


def _next_slot_in_room(
    ctx: "SlotContext",
    window_idx: int,
    facility_type: str,
    room_idx: int,
) -> int:
    """获取房间内下一个空槽位索引"""
    return len(ctx.room_ops(window_idx, facility_type, room_idx))


_PREFIX_MAP = {
    "Mfg": "mfg", "Trade": "trade", "Control": "control",
    "Power": "power", "Reception": "reception", "Office": "office",
    "Dormitory": "dorm",
}


def _make_slot_id_inline(facility_type: str, room_index: int, slot_index: int) -> str:
    prefix = _PREFIX_MAP.get(facility_type, facility_type.lower())
    return f"{prefix}_{room_index}_{slot_index}"
