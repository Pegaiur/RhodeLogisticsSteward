"""Phase C: D-aware 中枢选择

替代旧的 fill_control.py——中枢干员通过 D[d]-based contribution 评分选出，
而非从 locked_support 累积 + best_efficiency 排序。

顺序贪心：每选一人后重建中枢上下文，下一人重算边际贡献。
type3 同种取最高和 per-operator 条件加成均依赖此机制生效。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .contribution import contribution

if TYPE_CHECKING:
    from .context import SlotContext


def phase_control(
    ctx: "SlotContext",
    window_idx: int = 0,
    D: dict[str, float] | None = None,
) -> None:
    """执行 D-aware 中枢填充

    1. 收集所有有中枢技能的未分配干员
    2. 若 D 为 None，从当前分配计算偏导数（Phase A/B 后已有赋值）
    3. 顺序贪心：每轮选 contribution 最高的干员，写入 ctx，下一轮重算

    中枢容量从 ctx.params.control_max_slots 读取（默认 5）。
    """
    from .partials import compute_partial_derivatives

    params = ctx.params
    max_slots = params.control_max_slots if params else 5

    existing = ctx.ops_of_type(window_idx, "Control")
    slots_filled = len(existing)

    if slots_filled >= max_slots:
        return

    if D is None:
        D = compute_partial_derivatives(ctx, window_idx)

    assigned_ids = ctx.assigned_ids(window_idx)

    for _ in range(max_slots - slots_filled):
        best_op_name = None
        best_score = float("-inf")

        for op in ctx.operators:
            if op.char_id in assigned_ids:
                continue
            if not op.has_skill_for("Control"):
                continue

            score = contribution(ctx, op.name, "Control", window_idx, D)
            if score > best_score:
                best_score = score
                best_op_name = op.name

        if best_op_name is None:
            break

        existing = ctx.ops_of_type(window_idx, "Control")
        slot_id = f"control_0_{len(existing)}"
        ctx.place(window_idx, slot_id, best_op_name)
        assigned_ids.add(ctx.op_lookup[best_op_name].char_id)

        D = compute_partial_derivatives(ctx, window_idx)
