"""实证分析：高效干员是否因评分缺乏宿舍恢复信息被提前替换

对照 A/B 测试：追踪每个工作干员的 mood 轨迹、combo 评分、
以及被替换时的替代者效率差额
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from steward_core.data_loader import load_operators_v2
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.solver import solve_slot
from steward_core.models import LayoutConfig
from steward_core.mood_flow import MoodContext


def _work_hours(plan, op_name):
    """统计干员在非宿舍/训练设施中的总槽位数（3人房=3槽位）"""
    for a in plan.assignments:
        if a.room_type in ("Dormitory", "Training", "Workshop"):
            continue
        if op_name in a.operators:
            return 1  # 被分配到工作设施
    return 0


def main():
    shifts = 14
    hours = 12.0
    root = Path.cwd()

    print("[加载] 解析数据...")
    ops = load_operators_v2(
        root / "character_identity.json",
        root / "buffs_infrastructure.json",
    )
    print(f"[加载] 干员总数: {len(ops)}")

    params = SolverParams(shift_count=shifts, shift_hours=hours)
    mc = MoodContext.fresh(ops, params)

    print(f"[求解] {shifts}×{hours:.0f}h...")
    result = solve_slot(ops, params, max_iterations=5)

    # 找出最高效的 Mfg 和 Trade 干员
    mfg_ops = sorted(
        [op for op in ops if any(sk.room_type == "Mfg" for sk in op.skills)],
        key=lambda o: max((sk.efficient.raw.get("all", 0) for sk in o.skills if sk.room_type == "Mfg"), default=0),
        reverse=True,
    )[:15]
    trade_ops = sorted(
        [op for op in ops if any(sk.room_type == "Trade" for sk in op.skills)],
        key=lambda o: max((sk.efficient.raw.get("all", 0) for sk in o.skills if sk.room_type == "Trade"), default=0),
        reverse=True,
    )[:10]

    # 追踪每个高效干员在各窗口的工作状态和 mood
    print(f"\n{'='*80}")
    print(f"  高效干员工作/mood 轨迹（窗口内 mood 为 after_shift 后的值）")
    print(f"{'='*80}")

    # 模拟 mood 流转来获取每窗口起始心情
    mc_trace = MoodContext.fresh(ops, params)
    window_moods: list[dict[str, tuple[float, float]]] = []  # (start, end) mood per window

    for pi, plan in enumerate(result.plans):
        # 收集本窗口工作干员
        workers = set()
        worker_room_slots = {}
        for a in plan.assignments:
            if a.room_type in ("Dormitory", "Training", "Workshop"):
                continue
            for name in a.operators:
                workers.add(name)
                worker_room_slots[name] = 3  # simplify

        # 收集宿舍干员
        dormers = set()
        for a in plan.assignments:
            if a.room_type == "Dormitory":
                dormers.update(a.operators)

        # 本窗口起始心情
        start_moods = {name: mc_trace.mood_of(name) for name in workers | dormers}

        # 模拟 after_shift + dorm recovery
        burn_map = {}
        for name in workers:
            burn = mc_trace.work_burn(name, "Mfg", 3)
            burn_map[name] = burn

        new_moods = dict(mc_trace.operator_moods)
        for name in workers:
            new_moods[name] = max(0, new_moods.get(name, 24.0) - burn_map.get(name, 1.0) * hours)
        for name in dormers:
            rate = mc_trace.dorm_recovery(name)
            new_moods[name] = min(24.0, new_moods.get(name, 24.0) + rate * hours)

        from dataclasses import replace
        mc_trace = replace(mc_trace, operator_moods=new_moods)

        end_moods = {name: mc_trace.mood_of(name) for name in workers | dormers}
        window_moods.append({name: (start_moods.get(name, 24.0), end_moods.get(name, 24.0)) for name in workers | dormers})

    # 追踪高效干员
    target_ops = mfg_ops[:8] + trade_ops[:5]
    for op in target_ops:
        best_eff = max((sk.efficient.raw.get("all", 0) for sk in op.skills if sk.room_type in ("Mfg", "Trade")), default=0)
        room = next((sk.room_type for sk in op.skills if sk.room_type in ("Mfg", "Trade")), "?")

        trace = ""
        mood_trace = ""
        for pi, plan in enumerate(result.plans):
            in_work = _work_hours(plan, op.name)
            in_dorm = op.name in [o for a in plan.assignments if a.room_type == "Dormitory" for o in a.operators]
            moods = window_moods[pi].get(op.name, (24.0, 24.0))

            if in_work:
                trace += "W"
                mood_trace += f" {moods[0]:.0f}→{moods[1]:.0f}"
            elif in_dorm:
                trace += "D"
                mood_trace += f" {moods[0]:.0f}→{moods[1]:.0f}"
            else:
                trace += "."
                mood_trace += f" {moods[0]:.0f}"

        work_count = trace.count("W")
        dorm_count = trace.count("D")
        if work_count > 0:
            print(f"  [{room}] {op.name:<10s} eff={best_eff:5.0f}%  {trace}  W/D={work_count}/{dorm_count}")
            print(f"         mood: {mood_trace}")

    # 检查：是否有"工作1窗后 mood=0"的干员，其替代者效率差异
    print(f"\n── 替代效率差额分析 ──")
    for pi in range(1, shifts):
        prev_workers = set()
        curr_workers = set()
        for a in result.plans[pi - 1].assignments:
            if a.room_type not in ("Dormitory", "Training", "Workshop"):
                prev_workers.update(a.operators)
        for a in result.plans[pi].assignments:
            if a.room_type not in ("Dormitory", "Training", "Workshop"):
                curr_workers.update(a.operators)

        dropped = prev_workers - curr_workers  # 被换下的
        added = curr_workers - prev_workers     # 换上的

        if dropped and added:
            for drop_name in list(dropped)[:5]:
                drop_op = next((o for o in ops if o.name == drop_name), None)
                if not drop_op:
                    continue
                drop_eff = max((sk.efficient.raw.get("all", 0) for sk in drop_op.skills if sk.room_type in ("Mfg", "Trade")), default=0)
                drop_moods = window_moods[pi - 1].get(drop_name, (24.0, 24.0))

                for add_name in list(added)[:3]:
                    add_op = next((o for o in ops if o.name == add_name), None)
                    if not add_op:
                        continue
                    add_eff = max((sk.efficient.raw.get("all", 0) for sk in add_op.skills if sk.room_type in ("Mfg", "Trade")), default=0)
                    add_moods = window_moods[pi].get(add_name, (24.0, 24.0))

                    eff_diff = drop_eff - add_eff
                    if eff_diff > 0:
                        print(f"  W{pi-1}→W{pi}: {drop_name}({drop_eff:.0f}%, mood={drop_moods[1]:.0f}) → "
                              f"{add_name}({add_eff:.0f}%, mood={add_moods[0]:.0f})  "
                              f"效率降 {eff_diff:.0f}%")


if __name__ == "__main__":
    main()
