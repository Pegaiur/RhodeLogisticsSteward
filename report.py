"""排班生产报表 — 7天14班次轮换分析"""

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


def _plan_names(plan):
    names = set()
    for a in plan.assignments:
        if a.operators:
            names.update(a.operators)
    return names


def main():
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    shifts = int(sys.argv[2]) if len(sys.argv) > 2 else 14
    root = Path(__file__).parent
    ops = load_operators_v2(root / "character_identity.json",
                            root / "buffs_infrastructure.json")
    params = SolverParams(shift_count=shifts, shift_hours=hours)

    pipe = run_pipeline(ops, params)
    plans = pipe.solve_result.plans

    print(f"\n[参数]")
    print(params.summary())
    print(f"  周期: {shifts}x{hours:.0f}h = {shifts * hours:.0f}h ({shifts * hours / 24:.1f}天)")

    # ═══ 一、重叠矩阵 ─────────────────────────────
    print(f"\n{'=' * 64}")
    print(f"  重叠矩阵  (x,y)=Wx与Wy的共有干员数，49人满编")
    print(f"{'=' * 64}")
    header = "   W    | " + " ".join(f"W{w:<2}" for w in range(shifts)) + " | 变化"
    print(header)
    print("  " + "-" * (7 + 5 * shifts))
    for wi in range(shifts):
        ni = _plan_names(plans[wi])
        row = f"  W{wi:<2}   | "
        for wj in range(shifts):
            nj = _plan_names(plans[wj])
            row += f"{len(ni & nj):<4}"
        if wi == 0:
            row += " | --"
        else:
            prev = _plan_names(plans[wi - 1])
            diff = len(ni) - len(ni & prev)
            row += f" | 换{diff}人"
        print(row)

    # ═══ 二、设施换班详情 ─────────────────────────
    tracked = [
        ("Control", 0), ("Trade", 0), ("Trade", 1),
        ("Mfg", 0), ("Mfg", 1), ("Mfg", 2), ("Mfg", 3),
    ]
    print(f"\n{'=' * 64}")
    print(f"  设施换班详情  + 表示与上一班人员不同")
    print(f"{'=' * 64}")
    for ft, ri in tracked:
        print(f"\n  {ft}[{ri}]:")
        prev_ops = []
        for pi, plan in enumerate(plans):
            for a in plan.assignments:
                if a.room_type == ft and a.room_index == ri:
                    cur = a.operators
                    tag = ""
                    if pi > 0 and set(cur) != set(prev_ops):
                        tag = " +"
                    elif pi > 0:
                        tag = "  "
                    print(f"    W{pi}{tag}: {cur}")
                    prev_ops = cur
                    break

    # ═══ 三、换班统计 ────────────────────────────
    print(f"\n{'=' * 64}")
    print(f"  换班统计")
    print(f"{'=' * 64}")
    for ft, ri in tracked:
        prev_ops = set()
        swaps = 0
        for pi, plan in enumerate(plans):
            for a in plan.assignments:
                if a.room_type == ft and a.room_index == ri:
                    cur = set(a.operators)
                    if pi > 0 and cur != prev_ops:
                        swaps += 1
                    prev_ops = cur
                    break
        rate = swaps / max(shifts - 1, 1) * 100
        bar_n = round(swaps / 2)
        bar = "#" * bar_n + "-" * (6 - bar_n) if bar_n <= 6 else "#" * 6
        print(f"  {ft}[{ri}]: {swaps}/{shifts - 1} 换班 ({rate:.0f}%)  [{bar}]")

    overlaps = []
    for wi in range(1, shifts):
        ni = _plan_names(plans[wi])
        nj = _plan_names(plans[wi - 1])
        overlaps.append(len(ni & nj))
    avg_o = sum(overlaps) / max(len(overlaps), 1)
    print(f"\n  相邻重叠: {avg_o:.1f}/49 (范围 {min(overlaps) if overlaps else 49}-{max(overlaps) if overlaps else 49})")
    print(f"  平均换人: {49 - avg_o:.1f}/班")

    # ═══ 四、产能分析 ────────────────────────────
    print(f"\n{'=' * 64}")
    print(f"  产能分析  {shifts} x {hours:.0f}h")
    print(f"{'=' * 64}")

    prod_rows = []
    for pi, plan in enumerate(plans):
        dp = pipe.productions[pi]
        exp = dp.total_records_per_day * _RECORD_EXP_PER_UNIT
        lmd = dp.effective_lmd_per_day
        prod_rows.append((pi, exp, lmd))
    me = max(r[1] for r in prod_rows)
    ml = max(r[2] for r in prod_rows)

    print(f"\n  [产能汇总]")
    hdr_hours = str(int(hours))
    print(f"  {'W':<4}{'经验/' + hdr_hours + 'h':>10}{'LMD/' + hdr_hours + 'h':>10}"
          f"{'vs W0 经验':>12}{'vs W0 LMD':>12}  产能条")
    print(f"  {'-' * 68}")
    for pi, exp, lmd in prod_rows:
        de = exp - prod_rows[0][1]
        dl = lmd - prod_rows[0][2]
        print(f"  {pi:<4}{exp:>10,.0f}{lmd:>10,.0f}"
              f"{de:>+12,.0f}{dl:>+12,.0f}  "
              f"E:{_bar(exp, me)} L:{_bar(lmd, ml)}")

    total_hours = shifts * hours
    scale = 24.0 / total_hours if total_hours > 0 else 0.0
    sum_exp = sum(dp.total_records_per_day for dp in pipe.productions) * _RECORD_EXP_PER_UNIT * scale
    sum_gold = sum(dp.total_gold_produced_per_day for dp in pipe.productions) * _GOLD_LMD_PER_UNIT * scale
    sum_lmd = sum(dp.total_lmd_per_day for dp in pipe.productions) * scale
    sum_eff_lmd = sum(dp.effective_lmd_per_day for dp in pipe.productions) * scale
    sum_gold_consumed = sum(dp.total_gold_consumed_per_day for dp in pipe.productions) * _GOLD_LMD_PER_UNIT * scale

    print(f"\n  [24h折算]")
    print(f"  作战记录经验: {sum_exp:>12,.0f} /天")
    print(f"  赤金制造等值: {sum_gold:>12,.0f} LMD /天")
    labeled = f"  龙门币收入:   {sum_eff_lmd:>12,.0f} /天"
    if sum_lmd != sum_eff_lmd:
        labeled += f"  (理论 {sum_lmd:,.0f}，赤金不足缩减)"
    print(labeled)

    surplus_gold = sum(dp.total_gold_produced_per_day for dp in pipe.productions) * scale \
        - sum_gold_consumed / _GOLD_LMD_PER_UNIT
    surplus_lmd = surplus_gold * _GOLD_LMD_PER_UNIT
    if surplus_gold >= 0:
        print(f"  赤金盈余:     {surplus_lmd:>12,.0f} LMD等值 /天")
    else:
        print(f"  赤金缺口:     {abs(surplus_lmd):>12,.0f} LMD等值 /天")

    print()


if __name__ == "__main__":
    main()
