"""排班生产报表 — 运行求解器并输出格式化报表"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from steward_core.data_loader import load_operators_v2
from steward_core.solver.params import SolverParams
from steward_core.solver.config import SolverConfig
from steward_core.solver import solve_mvp
from steward_core.mood_flow import MoodContext
from steward_core import production
from steward_core.production import _RECORD_EXP_PER_UNIT, _GOLD_LMD_PER_UNIT


def _bar(val, ref, w=8):
    n = int(val / max(ref, 1) * w)
    return "\u2588" * n + "\u2591" * (w - n)


def main():
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0

    root = Path(__file__).parent
    ops = load_operators_v2(root / "character_identity.json", root / "buffs_infrastructure.json")

    params = SolverParams(shift_count=3, shift_hours=hours, interval_hours=8.0)
    mood_ctx = MoodContext.fresh(ops, params)
    result = solve_mvp(ops, config=SolverConfig(params=params, mood_ctx=mood_ctx))
    plans = result.plans

    def _ctrl(plan):
        for a in plan.assignments:
            if a.room_type == "Control":
                return a.operators
        return []

    def _room_ops(plan, ftype, ridx):
        for a in plan.assignments:
            if a.room_type == ftype and a.room_index == ridx:
                return a.operators
        return []

    # ── 控制中枢轮换矩阵 ──
    print()
    print("\u250c" + "\u2500" * 74 + "\u2510")
    print("\u2502  \u63a7\u5236\u4e2d\u67a2\u8f6e\u6362\u77e9\u9635" + " " * 57 + "\u2502")
    print("\u251c" + "\u2500" * 74 + "\u2524")
    print("\u2502 \u7a97\u53e3 | \u4e2d\u67a2\u5e72\u5458" + " " * 55 + "\u2502")
    print("\u251c" + "\u2500" * 74 + "\u2524")
    all_sets = []
    for pi, plan in enumerate(plans):
        c = _ctrl(plan)
        all_sets.append(set(c))
        print(f"\u2502  {pi}   | {', '.join(c):<60}\u2502")
    print("\u2514" + "\u2500" * 74 + "\u2518")

    ov = [len(all_sets[i] & all_sets[i + 1]) for i in range(len(all_sets) - 1)]
    tag = "\u2714 \u5b8c\u5168\u4e92\u65a5" if all(o == 0 for o in ov) else f"\u26a0 \u91cd\u53e0 " + "/".join(map(str, ov))
    print(f"  \u8f6e\u6362: {tag}\n")

    # ── 产能表 ──
    prod_data = []
    for pi, plan in enumerate(plans):
        dp = production.calculate(plan, ops, hours=hours,
                                  external_gold_per_day=params.daily_task_lmd / _GOLD_LMD_PER_UNIT)
        prod_data.append((pi, dp.total_records_per_day * _RECORD_EXP_PER_UNIT, dp.effective_lmd_per_day))

    me, ml = max(r[1] for r in prod_data), max(r[2] for r in prod_data)

    print("\u250c" + "\u2500" * 74 + "\u2510")
    print("\u2502  \u4ea7\u80fd\u6c47\u603b" + " " * 65 + "\u2502")
    print("\u251c" + "\u2500" * 74 + "\u2524")
    print(f"\u2502 \u7a97\u53e3 | \u7ecf\u9a8c/{hours:.0f}h       | LMD/{hours:.0f}h        | vs\u7a97\u53e30   | \u4ea7\u80fd\u6761" + " " * 17 + "\u2502")
    print("\u251c" + "\u2500" * 74 + "\u2524")
    for pi, exp, lmd in prod_data:
        de = exp - prod_data[0][1]
        dl = lmd - prod_data[0][2]
        se = f"{de:+,.0f}"
        sl = f"{dl:+,.0f}"
        print(f"\u2502  {pi}   | {exp:>7,.0f}         | {lmd:>7,.0f}         | {se:>8s} {sl:>8s} | {_bar(exp, me)} {_bar(lmd, ml)} \u2502")
    print("\u2514" + "\u2500" * 74 + "\u2518")

    # ── 制造站 ──
    print(f"\n\u250c" + "\u2500" * 74 + "\u2510")
    print("\u2502  \u5236\u9020\u7ad9 \u623f\u95f4\u8be6\u60c5 (\u7ecf\u9a8c \u2192 \u8d64\u91d1)" + " " * 39 + "\u2502")
    print("\u251c" + "\u2500" * 74 + "\u2524")
    for pt, (ridx, label, unit) in enumerate([(0, "\u7ecf\u9a8c CR", "\u7ecf\u9a8c"), (1, "\u7ecf\u9a8c CR", "\u7ecf\u9a8c"),
                                               (2, "\u8d64\u91d1 PG", "LMD"), (3, "\u8d64\u91d1 PG", "LMD")]):
        print(f"\u2502 Mfg[{ridx}] {label}\u2502")
        for pi, plan in enumerate(plans):
            n = _room_ops(plan, "Mfg", ridx)
            dp = production.calculate(plan, ops, hours=hours,
                                      external_gold_per_day=params.daily_task_lmd / _GOLD_LMD_PER_UNIT)
            if pt < 2:
                val = dp.total_records_per_day * _RECORD_EXP_PER_UNIT
                for room in [r for r in dp.record_rooms if r.room_index == ridx]:
                    val = room.output_per_day * _RECORD_EXP_PER_UNIT
            else:
                val = 0
                for room in [r for r in dp.gold_rooms if r.room_index == ridx]:
                    val = room.output_per_day * _GOLD_LMD_PER_UNIT
            print(f"\u2502   \u7a97\u53e3{pi}: {', '.join(n):<40} {val:>8,.0f} {unit}\u2502")
        print("\u251c" + "\u2500" * 74 + "\u2524")

    # ── 贸易站 ──
    print(f"\n\u250c" + "\u2500" * 74 + "\u2510")
    print("\u2502  \u8d38\u6613\u7ad9 \u623f\u95f4\u8be6\u60c5" + " " * 57 + "\u2502")
    print("\u251c" + "\u2500" * 74 + "\u2524")
    for ridx in (0, 1):
        print(f"\u2502 Trade[{ridx}]\u2502")
        for pi, plan in enumerate(plans):
            n = _room_ops(plan, "Trade", ridx)
            dp = production.calculate(plan, ops, hours=hours,
                                      external_gold_per_day=params.daily_task_lmd / _GOLD_LMD_PER_UNIT)
            val = 0
            for room in [r for r in dp.trade_rooms if r.room_index == ridx]:
                val = room.output_per_day
            print(f"\u2502   \u7a97\u53e3{pi}: {', '.join(n):<40} {val:>8,.0f} LMD\u2502")
        print("\u251c" + "\u2500" * 74 + "\u2524")
    print()


if __name__ == "__main__":
    main()
