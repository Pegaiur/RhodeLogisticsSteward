"""排班生产报表"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from steward_core.data_loader import load_operators_v2
from steward_core.solver.params import SolverParams
from steward_core.pipeline import run as run_pipeline
from steward_core.production import _RECORD_EXP_PER_UNIT, _GOLD_LMD_PER_UNIT


def _bar(v, ref, w=10):
    n = round(v / max(ref, 1) * w)
    return "#" * n + "-" * (w - n)


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
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    root = Path(__file__).parent
    ops = load_operators_v2(root / "character_identity.json",
                            root / "buffs_infrastructure.json")
    params = SolverParams(shift_count=3, shift_hours=hours, interval_hours=8.0)

    pipe = run_pipeline(ops, params)
    plans = pipe.solve_result.plans

    print(f"\n[参数]")
    print(params.summary())

    ctrl_sets = [_ctrl_ops(p) for p in plans]
    mfg_rooms = [(0, "CombatRecord"), (1, "CombatRecord"),
                 (2, "PureGold"), (3, "PureGold")]
    trade_rooms = [(0,), (1,)]

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
    for ridx, prod in mfg_rooms:
        print(f"  Mfg[{ridx}] {prod}")
        for pi, plan in enumerate(plans):
            names = _room_ops(plan, "Mfg", ridx)
            print(f"    W{pi}  {', '.join(names)}")

    # 贸易站
    print(f"\n  [贸易站]")
    for (ridx,) in trade_rooms:
        print(f"  Trade[{ridx}]")
        for pi, plan in enumerate(plans):
            names = _room_ops(plan, "Trade", ridx)
            print(f"    W{pi}  {', '.join(names)}")

    # ════════════════════════════════════════════════════
    #  第二部分：产能分析
    # ════════════════════════════════════════════════════
    print(f"\n{'=' * 64}")
    print(f"  产能分析  {len(plans)} x {hours:.0f}h")
    print(f"{'=' * 64}")

    # 汇总
    prod_rows = []
    for pi, plan in enumerate(plans):
        dp = pipe.productions[pi]
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
        print(f"  Mfg[{ridx}] {prod}")
        for pi, plan in enumerate(plans):
            names = _room_ops(plan, "Mfg", ridx)
            dp = pipe.productions[pi]
            val = 0
            rooms = dp.record_rooms if prod == "CombatRecord" else dp.gold_rooms
            for r in rooms:
                if r.room_index == ridx:
                    val = r.output_per_day * (_RECORD_EXP_PER_UNIT if prod == "CombatRecord" else _GOLD_LMD_PER_UNIT)
            print(f"    W{pi}  {val:>10,.0f} {unit}")

    # 贸易站分间
    print(f"\n  [贸易站 分间产出]")
    for (ridx,) in trade_rooms:
        print(f"  Trade[{ridx}]")
        for pi, plan in enumerate(plans):
            dp = pipe.productions[pi]
            val = 0
            for r in dp.trade_rooms:
                if r.room_index == ridx:
                    val = r.output_per_day
            print(f"    W{pi}  {val:>10,.0f} LMD")

    # ════════════════════════════════════════════════════
    #  第三部分：总日生产（24h 折算）
    # ════════════════════════════════════════════════════
    total_hours = len(plans) * hours
    scale = 24.0 / total_hours if total_hours > 0 else 0.0

    sum_exp = sum(dp.total_records_per_day for dp in pipe.productions) * _RECORD_EXP_PER_UNIT * scale
    sum_gold = sum(dp.total_gold_produced_per_day for dp in pipe.productions) * _GOLD_LMD_PER_UNIT * scale
    sum_lmd = sum(dp.total_lmd_per_day for dp in pipe.productions) * scale
    sum_eff_lmd = sum(dp.effective_lmd_per_day for dp in pipe.productions) * scale
    sum_gold_consumed = sum(dp.total_gold_consumed_per_day for dp in pipe.productions) * _GOLD_LMD_PER_UNIT * scale

    print(f"\n{'=' * 64}")
    print(f"  总日生产（{len(plans)}x{hours:.0f}h → 24h 折算）")
    print(f"{'=' * 64}")
    print(f"\n  作战记录经验: {sum_exp:>12,.0f} /天")
    print(f"  赤金制造等值: {sum_gold:>12,.0f} LMD /天")
    lmd_label = f"  龙门币收入:   {sum_eff_lmd:>12,.0f} /天"
    if sum_lmd != sum_eff_lmd:
        lmd_label += f"  (理论 {sum_lmd:,.0f}，赤金不足缩减)"
    print(lmd_label)
    print(f"  赤金消耗等值: {sum_gold_consumed:>12,.0f} LMD /天")

    surplus_gold = sum(dp.total_gold_produced_per_day for dp in pipe.productions) * scale \
        - sum_gold_consumed / _GOLD_LMD_PER_UNIT
    surplus_lmd = surplus_gold * _GOLD_LMD_PER_UNIT
    if surplus_gold >= 0:
        print(f"  赤金盈余:     {surplus_lmd:>12,.0f} LMD等值 /天  ({surplus_gold:+.1f} 个)")
    else:
        print(f"  赤金缺口:     {abs(surplus_lmd):>12,.0f} LMD等值 /天  ({surplus_gold:+.1f} 个)")

    print()


if __name__ == "__main__":
    main()
