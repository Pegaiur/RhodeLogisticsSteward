"""排班生产报表"""

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


def _bar(v, ref, w=10):
    n = round(v / max(ref, 1) * w)
    return "#" * n + "-" * (w - n)


def _fmt_names(names, width=28):
    s = ", ".join(names)
    return s if len(s) <= width else s[:width - 2] + ".."


def _room_ops(plan, ftype, ridx):
    for a in plan.assignments:
        if a.room_type == ftype and a.room_index == ridx:
            return a.operators
    return []


def _ctrl_ops(plan):
    for a in plan.assignments:
        if a.room_type == "Control":
            return a.operators
    return []


def main():
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    root = Path(__file__).parent
    ops = load_operators_v2(root / "character_identity.json",
                            root / "buffs_infrastructure.json")
    params = SolverParams(shift_count=3, shift_hours=hours, interval_hours=8.0)
    mc = MoodContext.fresh(ops, params)
    result = solve_mvp(ops, config=SolverConfig(params=params, mood_ctx=mc))
    plans = result.plans

    ctrl_sets = [_ctrl_ops(p) for p in plans]
    mfg_rooms = [(0, "CombatRecord"), (1, "CombatRecord"),
                 (2, "PureGold"), (3, "PureGold")]
    trade_rooms = [(0,), (1,)]

    def _dp(plan):
        return production.calculate(plan, ops, hours=hours,
                                    external_gold_per_day=params.daily_task_lmd / _GOLD_LMD_PER_UNIT)

    # ════════════════════════════════════════════════════
    #  第一部分：轮班总览
    # ════════════════════════════════════════════════════
    print(f"\n{'=' * 64}")
    print(f"  轮班总览  {len(plans)} x {hours:.0f}h")
    print(f"{'=' * 64}")

    # 控制中枢
    print(f"\n  [控制中枢]")
    print(f"  {'Window':<8}{'Operators'}")
    print(f"  {'-' * 56}")
    for pi, c in enumerate(ctrl_sets):
        print(f"  {pi:<8}{', '.join(c)}")
    ov = [len(set(ctrl_sets[i]) & set(ctrl_sets[i + 1]))
          for i in range(len(ctrl_sets) - 1)]
    tag = "OK 完全互斥" if all(o == 0 for o in ov) else \
          f"!! 重叠 {', '.join(str(o) for o in ov)}"
    print(f"  {'':8}[{tag}]")

    # 制造站
    print(f"\n  [制造站]")
    print(f"  {'Room':<14}", end="")
    for pi in range(len(plans)):
        print(f"{'Window ' + str(pi):<30}", end="")
    print()
    print(f"  {'-' * 14}{'-' * (30 * len(plans))}")
    for ridx, prod in mfg_rooms:
        label = f"  Mfg[{ridx}] {prod}"
        print(f"{label:<14}", end="")
        for pi in range(len(plans)):
            names = _room_ops(plans[pi], "Mfg", ridx)
            print(f"{_fmt_names(names, 28):<30}", end="")
        print()

    # 贸易站
    print(f"\n  [贸易站]")
    print(f"  {'Room':<14}", end="")
    for pi in range(len(plans)):
        print(f"{'Window ' + str(pi):<30}", end="")
    print()
    print(f"  {'-' * 14}{'-' * (30 * len(plans))}")
    for (ridx,) in trade_rooms:
        label = f"  Trade[{ridx}]"
        print(f"{label:<14}", end="")
        for pi in range(len(plans)):
            names = _room_ops(plans[pi], "Trade", ridx)
            print(f"{_fmt_names(names, 28):<30}", end="")
        print()

    # ════════════════════════════════════════════════════
    #  第二部分：产能分析
    # ════════════════════════════════════════════════════
    print(f"\n{'=' * 64}")
    print(f"  产能分析  {len(plans)} x {hours:.0f}h")
    print(f"{'=' * 64}")

    # 汇总
    prod_rows = []
    for pi, plan in enumerate(plans):
        dp = _dp(plan)
        exp = dp.total_records_per_day * _RECORD_EXP_PER_UNIT
        lmd = dp.effective_lmd_per_day
        prod_rows.append((pi, exp, lmd))
    me = max(r[1] for r in prod_rows)
    ml = max(r[2] for r in prod_rows)

    print(f"\n  [产能汇总]")
    print(f"  {'Window':<8}{'经验/' + str(int(hours)) + 'h':>10}{'LMD/' + str(int(hours)) + 'h':>10}"
          f"{'vs W0 经验':>12}{'vs W0 LMD':>12}  {'产能条'}")
    print(f"  {'-' * 74}")
    for pi, exp, lmd in prod_rows:
        de = exp - prod_rows[0][1]
        dl = lmd - prod_rows[0][2]
        print(f"  {pi:<8}{exp:>10,.0f}{lmd:>10,.0f}"
              f"{de:>+12,.0f}{dl:>+12,.0f}  "
              f"E:{_bar(exp, me)} L:{_bar(lmd, ml)}")

    # 制造站分间
    print(f"\n  [制造站 分间产出]")
    for ridx, prod in mfg_rooms:
        unit = "经验" if prod == "CombatRecord" else "LMD"
        label = f"  Mfg[{ridx}] {prod}"
        print(f"  {'-' * 40}")
        print(f"{label}")
        for pi, plan in enumerate(plans):
            names = _room_ops(plan, "Mfg", ridx)
            dp = _dp(plan)
            val = 0
            rooms = dp.record_rooms if prod == "CombatRecord" else dp.gold_rooms
            for r in rooms:
                if r.room_index == ridx:
                    val = r.output_per_day * (_RECORD_EXP_PER_UNIT if prod == "CombatRecord" else _GOLD_LMD_PER_UNIT)
            print(f"    W{pi}: {_fmt_names(names, 24):<26} {val:>10,.0f} {unit}")

    # 贸易站分间
    print(f"\n  [贸易站 分间产出]")
    for (ridx,) in trade_rooms:
        print(f"  {'-' * 40}")
        print(f"  Trade[{ridx}]")
        for pi, plan in enumerate(plans):
            names = _room_ops(plan, "Trade", ridx)
            dp = _dp(plan)
            val = 0
            for r in dp.trade_rooms:
                if r.room_index == ridx:
                    val = r.output_per_day
            print(f"    W{pi}: {_fmt_names(names, 24):<26} {val:>10,.0f} LMD")

    print()


if __name__ == "__main__":
    main()
