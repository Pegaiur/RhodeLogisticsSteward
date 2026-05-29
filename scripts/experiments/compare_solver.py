r"""优化策略 A/B 对比测试

对比 baseline vs 各种开关组合的排班效果。
用法: python compare_solver.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from steward_core.data_loader import load_operators_v2
from steward_core.solver import solve_mvp
from steward_core.solver.config import SolverConfig
from steward_core.solver.refine import evaluate_full_plan
from steward_core.solver.params import SolverParams
from steward_core.solver.strategies import KBeamStrategy
from steward_core import production


def run_and_score(operators, config, label):
    """运行求解器并计算全量效率积分 + 产出"""
    result = solve_mvp(operators, config=config)
    plan = result.plans[0]
    score = evaluate_full_plan(plan, operators, config.params)
    dp = production.calculate(
        plan, operators, hours=config.params.shift_hours,
        external_gold_per_day=config.params.daily_task_lmd / 500.0,
    )
    return {
        "label": label,
        "score": score,
        "autofill": result.autofill_count,
        "total_exp": dp.total_records_per_day * 1000,
        "total_lmd": dp.effective_lmd_per_day,
        "gold_surplus": dp.gold_surplus,
        "mfg_rooms": sum(1 for a in plan.assignments if a.room_type == "Mfg" and not a.autofill),
        "trade_combo": [
            a.operators for a in plan.assignments
            if a.room_type == "Trade" and not a.autofill
        ],
        "mfg_combo": [
            (a.product, a.operators) for a in plan.assignments
            if a.room_type == "Mfg" and not a.autofill
        ],
    }


def main():
    project_root = Path(__file__).resolve().parent.parent.parent
    ci_path = project_root / "character_identity.json"
    bi_path = project_root / "buffs_infrastructure.json"

    if not ci_path.exists() or not bi_path.exists():
        print("[跳过] 真数据文件不存在，无法运行对比")
        return

    print("[加载] 正在解析数据...")
    all_operators = load_operators_v2(ci_path, bi_path)
    print(f"[加载] 干员总数: {len(all_operators)}")

    configs = [
        (SolverConfig.baseline(), "baseline (全部关闭)"),
        (SolverConfig(exclusive_support_check=True),
         "独占冲突检查 (exclusive_support_check)"),
        (SolverConfig(local_search_enabled=True),
         "局部搜索 (local_search_enabled)"),
        (SolverConfig(global_state_scoring=True),
         "全局状态评分 (global_state_scoring)"),
        (SolverConfig(
            exclusive_support_check=True,
            local_search_enabled=True,
         ), "独占检查 + 局部搜索"),
        (SolverConfig.all_on(), "all_on (三项全开)"),
        (SolverConfig(strategy=KBeamStrategy(beam_width=3)), "K-Beam K=3"),
        (SolverConfig(strategy=KBeamStrategy(beam_width=5)), "K-Beam K=5"),
    ]

    results = []
    for config, label in configs:
        print(f"\n{'='*60}")
        print(f"[运行] {label}")
        r = run_and_score(all_operators, config, label)
        results.append(r)
        print(f"  效率积分: {r['score']:,.0f}")
        print(f"  经验产出: {r['total_exp']:,.0f} 经验/12h")
        print(f"  LMD产出:  {r['total_lmd']:,.0f} LMD/12h")
        print(f"  赤金剩余: {r['gold_surplus']:.1f} 个")
        print(f"  autofill: {r['autofill']} 间")

    # 对比汇总
    print(f"\n{'='*60}")
    print("对比汇总")
    print(f"{'配置':<40} {'效率积分':>10} {'经验':>10} {'LMD':>10} {'autofill':>8}")
    print("-" * 80)
    baseline = results[0]
    for r in results:
        exp = f"{r['total_exp']:,.0f}"
        lmd = f"{r['total_lmd']:,.0f}"
        score = f"{r['score']:,.0f}"
        flag = ""
        if r is not baseline:
            delta = r['score'] - baseline['score']
            if delta > 1:
                flag = " ▲"
            elif delta < -1:
                flag = " ▼"
        print(f"{r['label']:<40} {score:>10} {exp:>10} {lmd:>10} {r['autofill']:>8}{flag}")

    # 排班差异
    print(f"\n{'='*60}")
    print("制造站排班差异（vs baseline）")
    for r in results[1:]:
        print(f"\n── {r['label']} ──")
        for (prod, names) in r['mfg_combo']:
            # 找 baseline 中同产品的房间
            bl_names = []
            for (bp, bn) in baseline['mfg_combo']:
                if bp == prod:
                    bl_names = bn
                    break
            changed = names != bl_names
            marker = "  ← 变更" if changed else ""
            print(f"  {prod}: {names}{marker}")


if __name__ == "__main__":
    main()
