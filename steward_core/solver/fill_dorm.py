"""宿舍填充与恢复调度"""

from steward_core.models import Operator, RoomAssignment

from .config import SolverConfig


def fill_dorm(
    operators: list[Operator],
    assigned_ids: set[str],
    assigned_names: set[str],
    assignments: list,
    op_lookup: dict[str, Operator],
    locked_support: dict[str, set[str]],
    *,
    dorm_names_list: list[str],
    config: SolverConfig | None = None,
) -> int:
    """Phase 4: 宿舍填充（优先B层生成者 → 任意填充）

    返回本阶段新增的 autofill_count。
    """
    if config is None:
        config = SolverConfig()
    params = config.params
    autofill_count = 0

    dorm_names: list[str] = list(locked_support["Dormitory"])
    for name in dorm_names:
        if name in op_lookup:
            assigned_ids.add(op_lookup[name].char_id)

    for name in dorm_names_list:
        if name not in dorm_names and name in op_lookup and op_lookup[name].char_id not in assigned_ids:
            dorm_names.append(name)
            assigned_ids.add(op_lookup[name].char_id)

    for op in operators:
        if len(dorm_names) >= params.dorm_max_operators:
            break
        if op.char_id not in assigned_ids:
            dorm_names.append(op.name)
            assigned_ids.add(op.char_id)

    for room_idx in range(params.dorm_room_count):
        start = room_idx * params.dorm_room_size
        room_ops = dorm_names[start:start + params.dorm_room_size] if start < len(dorm_names) else []
        assignments.append(RoomAssignment(
            room_type="Dormitory", room_index=room_idx,
            operators=room_ops, autofill=(len(room_ops) < params.dorm_room_size),
        ))
        if len(room_ops) < params.dorm_room_size:
            autofill_count += 1

    return autofill_count


def fill_dorm_with_scheduling(
    operators: list[Operator],
    assignments: list,
    op_lookup: dict[str, Operator],
    *,
    config: SolverConfig | None = None,
    mood_ctx = None,
) -> int:
    """多班次宿舍恢复调度 — 替代 fill_dorm()

    从 plan.assignments 识别工作干员（Mfg/Trade/Power/Reception/Office），
    将可用宿舍干员分配到 4 间宿舍以最大化工作干员的心情恢复效率。

    Args:
        operators: 全部干员池
        assignments: 已有的 RoomAssignment 列表（不含宿舍），原地追加 Dormitory 分配
        op_lookup: 干员名 → Operator 对象
        config: 求解器配置（含 mood_ctx）
        mood_ctx: 心情上下文（用于查询恢复速率和已分配控制中枢）

    Returns:
        本阶段新增的 autofill_count
    """
    if config is None:
        config = SolverConfig()
    params = config.params
    autofill_count = 0

    # 0. 清除旧的 Dormitory 分配（Strategy 阶段可能已产生旧条目）
    assignments[:] = [a for a in assignments if a.room_type != "Dormitory"]

    # 1. 识别工作干员（需要恢复的目标）
    working_names: list[str] = []
    working_rooms: dict[str, str] = {}
    for a in assignments:
        if a.room_type in ("Mfg", "Trade", "Power", "Reception", "Office"):
            working_names.extend(a.operators)
            for n in a.operators:
                working_rooms[n] = a.room_type

    # 2. 可用宿舍干员：全部干员 - 已分配（工作设施 + 中枢）
    if mood_ctx is not None and mood_ctx.control_operators:
        excluded = set(working_names) | set(mood_ctx.control_operators)
    else:
        excluded = set(working_names)

    available_dorm = [op for op in operators if op.name not in excluded and op.name in op_lookup]

    # 3. 按 buff_producer 优先排序（B 层生成者优先）
    from steward_core.synergy import get_system_contributors
    dorm_producers = set(get_system_contributors("Dormitory"))

    def _dorm_sort_key(op: Operator) -> tuple[int, int]:
        is_producer = 0 if op.name in dorm_producers else 1
        return (is_producer, -op.rarity)

    available_dorm.sort(key=_dorm_sort_key)

    # 4. 填充宿舍至满员
    dorm_assignments: list[list[str]] = [[] for _ in range(params.dorm_room_count)]
    room_idx = 0
    for op in available_dorm:
        if room_idx >= params.dorm_room_count:
            room_idx = 0
        if len(dorm_assignments[room_idx]) >= params.dorm_room_size:
            room_idx = (room_idx + 1) % params.dorm_room_count
            if sum(len(r) for r in dorm_assignments) >= params.dorm_max_operators:
                break
            continue
        dorm_assignments[room_idx].append(op.name)
        room_idx += 1
        if room_idx >= params.dorm_room_count:
            room_idx = 0

    # 5. 输出宿舍分配
    for room_idx in range(params.dorm_room_count):
        room_ops = dorm_assignments[room_idx]
        assignments.append(RoomAssignment(
            room_type="Dormitory", room_index=room_idx,
            operators=room_ops,
            autofill=(len(room_ops) < params.dorm_room_size),
        ))
        if len(room_ops) < params.dorm_room_size:
            autofill_count += 1

    # 6. 更新 mood_ctx 的宿舍分配映射
    if mood_ctx is not None:
        dorm_map: dict[str, str] = {}
        for ri, room in enumerate(dorm_assignments):
            for name in room:
                dorm_map[name] = f"Dorm_{ri}"
        object.__setattr__(mood_ctx, "dorm_assignments", dorm_map)

    return autofill_count
