"""局部搜索优化详情：对比 baseline vs 局部搜索的每个房间变化"""

from pathlib import Path

from steward_core.data_loader import load_operators_v2
from steward_core.solver import solve_mvp
from steward_core.solver.config import SolverConfig
from steward_core import production
from steward_core.production import _RECORD_EXP_PER_UNIT, _GOLD_LMD_PER_UNIT


def main():
    project_root = Path(__file__).resolve().parent
    ci_path = project_root / "character_identity.json"
    bi_path = project_root / "buffs_infrastructure.json"

    if not ci_path.exists() or not bi_path.exists():
        print("[跳过] 真数据文件不存在")
        return

    all_ops = load_operators_v2(ci_path, bi_path)

    bl = solve_mvp(all_ops, config=SolverConfig.baseline())
    ls = solve_mvp(all_ops, config=SolverConfig(local_search_enabled=True))

    bl_plan = bl.plans[0]
    ls_plan = ls.plans[0]

    # 逐房间对比
    bl_map = {}
    for a in bl_plan.assignments:
        bl_map[(a.room_type, a.room_index)] = a
    ls_map = {}
    for a in ls_plan.assignments:
        ls_map[(a.room_type, a.room_index)] = a

    print("=" * 70)
    print("基线 (baseline)  →  局部搜索后 (local_search)")
    print("=" * 70)

    for key in bl_map:
        b = bl_map[key]
        l = ls_map[key]
        same = b.operators == l.operators
        marker = "" if same else "  ← 变更"
        product = f" ({b.product})" if b.product else ""
        print(f"\n{b.room_type}[{b.room_index}]{product}:")
        print(f"  BL: {b.operators}")
        print(f"  LS: {l.operators}{marker}")

    # ---- 逐房间产出细节 ----
    print("\n" + "=" * 70)
    print("逐房间产出对比")
    print("=" * 70)

    bl_dp = production.calculate(bl_plan, all_ops, hours=12.0)
    ls_dp = production.calculate(ls_plan, all_ops, hours=12.0)

    def room_output(dp, room_type, index):
        for room in dp.trade_rooms:
            if room.room_index == index:
                return room.output_per_day
        for room in dp.gold_rooms:
            if room.room_index == index:
                return room.output_per_day * _GOLD_LMD_PER_UNIT
        for room in dp.record_rooms:
            if room.room_index == index:
                return room.output_per_day * _RECORD_EXP_PER_UNIT
        return 0.0

    for key in bl_map:
        b = bl_map[key]
        l = ls_map[key]
        if b.operators == l.operators:
            continue
        rt = b.room_type
        ri = b.room_index
        bl_val = room_output(bl_dp, rt, ri)
        ls_val = room_output(ls_dp, rt, ri)
        product = f" ({b.product})" if b.product else ""
        print(f"\n{rt}[{ri}]{product}:")
        print(f"  BL: {b.operators} → {bl_val:,.0f}")
        print(f"  LS: {l.operators} → {ls_val:,.0f}  (Δ={ls_val-bl_val:+,.0f})")

    print(f"\n{'='*70}")
    print(f"汇总: BL LMD={bl_dp.effective_lmd_per_day:,.0f},  LS LMD={ls_dp.effective_lmd_per_day:,.0f}")
    print(f"      ΔLMD={ls_dp.effective_lmd_per_day - bl_dp.effective_lmd_per_day:+,.0f}")
    print(f"      BL 赤金剩余={bl_dp.gold_surplus:.1f}, LS 赤金剩余={ls_dp.gold_surplus:.1f}")


if __name__ == "__main__":
    main()
