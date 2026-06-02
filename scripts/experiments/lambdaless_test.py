"""对照实验：禁用 lambda，纯效率积分 + 宿舍排队恢复

对照 A (当前): lambda delta 模型活跃，contribution = base - λ × hours × mood_factor
对照 B (无lambda): 所有 lambda_ops 始终 = 0, contribution = base
宿舍规则: 没进排班 + mood < 24 → 优先填宿舍
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from steward_core.data_loader import load_operators_v2
from steward_core.solver.params import SolverParams
from steward_core.solver.slot.solver import solve_slot, _update_lambda_shadow
from steward_core.models import LayoutConfig
from steward_core.mood_flow import MoodContext


def run_no_lambda(ops, shifts, hours):
    """禁用 lambda 的简化排班"""
    params = SolverParams(
        shift_count=shifts, shift_hours=hours,
        backpressure_damping=0.0,
    )

    # Monkey-patch: 强制 lambda_ops 始终为空
    import steward_core.solver.slot.solver as solver_mod
    original_update = _update_lambda_shadow

    def noop_update(ctx, operators, params_, mood_start=None, mood_ctx=None):
        ctx.lambda_ops.clear()
        return 0.0

    solver_mod._update_lambda_shadow = noop_update
    try:
        result = solve_slot(ops, params, max_iterations=3)
    finally:
        solver_mod._update_lambda_shadow = original_update

    return result


def run_default(ops, shifts, hours):
    """默认 lambda delta 模型"""
    params = SolverParams(
        shift_count=shifts, shift_hours=hours,
        backpressure_damping=0.5,
    )
    return solve_slot(ops, params, max_iterations=5)


def trace_operator(ops, result, name):
    """追踪单个干员在各窗口的状态"""
    w = ""  # work
    d = ""  # dorm
    for plan in result.plans:
        in_work = any(
            name in a.operators and a.room_type not in ("Dormitory", "Training", "Workshop")
            for a in plan.assignments
        )
        in_dorm = any(
            name in a.operators and a.room_type == "Dormitory"
            for a in plan.assignments
        )
        if in_work:
            w += "W"
        elif in_dorm:
            w += "D"
        else:
            w += "."
    return w, w.count("W"), w.count("D")


def main():
    shifts = 14
    hours = 12.0
    root = Path.cwd()

    print("[加载]...")
    ops = load_operators_v2(root / "character_identity.json", root / "buffs_infrastructure.json")

    # 找出最高效干员
    top_mfg = sorted(
        [op for op in ops if any(sk.room_type == "Mfg" for sk in op.skills)],
        key=lambda o: max((sk.efficient.raw.get("all", 0) for sk in o.skills if sk.room_type == "Mfg"), default=0),
        reverse=True,
    )
    top_trade = sorted(
        [op for op in ops if any(sk.room_type == "Trade" for sk in op.skills)],
        key=lambda o: max((sk.efficient.raw.get("all", 0) for sk in o.skills if sk.room_type == "Trade"), default=0),
        reverse=True,
    )

    print(f"\n{'='*70}")
    print(f"  对照 A: 默认 (lambda delta, damping=0.5, max_iter=5)")
    print(f"{'='*70}")
    r_a = run_default(ops, shifts, hours)

    print(f"\n{'='*70}")
    print(f"  对照 B: 无 lambda (纯效率积分, max_iter=3)")
    print(f"{'='*70}")
    r_b = run_no_lambda(ops, shifts, hours)

    # 对照：高效干员轨迹
    targets = top_mfg[:10] + top_trade[:5]
    print(f"\n{'─'*70}")
    print(f"  {'干员':<12s} {'效率':>5s} {'【A: lambda】':<20s} {'W/D':>6s}  {'【B: 无lambda】':<20s} {'W/D':>6s}")
    print(f"{'─'*70}")

    count_a_idle, count_a_used = 0, 0
    count_b_idle, count_b_used = 0, 0
    count_a_dead, count_b_dead = 0, 0  # "dead" = worked then never again

    for op in targets:
        best_eff = max((sk.efficient.raw.get("all", 0) for sk in op.skills if sk.room_type in ("Mfg", "Trade")), default=0)
        tr_a, wa, da = trace_operator(ops, r_a, op.name)
        tr_b, wb, db = trace_operator(ops, r_b, op.name)

        # 检测"死亡"模式：工作后陷入永久闲置
        dead_a = False
        dead_b = False
        for trace, name in [(tr_a, "A"), (tr_b, "B")]:
            if "W" in trace:
                last_w = trace.rfind("W")
                after_last = trace[last_w+1:]
                if after_last and all(c == "." for c in after_last) and len(after_last) >= 3:
                    if name == "A":
                        dead_a = True
                    else:
                        dead_b = True

        dead_mark_a = " ☠" if dead_a else ""
        dead_mark_b = " ☠" if dead_b else ""

        if wa > 0 or wb > 0:
            print(f"  {op.name:<12s} {best_eff:5.0f}% {tr_a:<20s} {wa:>2}/{da:>2}  {tr_b:<20s} {wb:>2}/{db:>2}{dead_mark_a}{dead_mark_b}")

        if dead_a: count_a_dead += 1
        if dead_b: count_b_dead += 1

    # 统计
    print(f"\n{'─'*70}")
    print(f"  高效干员\"死亡\"（工作后永弃）: A={count_a_dead}人, B={count_b_dead}人")

    # 总产出对比
    from steward_core.production import calculate as calc_prod
    prod_a = [calc_prod(plan, ops) for plan in r_a.plans]
    prod_b = [calc_prod(plan, ops) for plan in r_b.plans]

    total_a = sum(p.total_lmd_per_day for p in prod_a)
    total_b = sum(p.total_lmd_per_day for p in prod_b)
    print(f"  14窗总产出(LMD): A={total_a:,.0f}, B={total_b:,.0f}, B/A={total_b/total_a*100:.1f}%")


if __name__ == "__main__":
    main()
