r"""MVP 全 box 满练度求解器

用法:
    python run_solver.py

数据文件 (character_identity.json + buffs_infrastructure.json) 需在项目根目录。
输出 output/custom_infrast/mvp_12h.json。
"""

from pathlib import Path

from steward_core.data_loader import load_operators_v2
from steward_core.output import save_json
from steward_core.solver import solve_mvp


def main():
    project_root = Path(__file__).resolve().parent
    ci_path = project_root / "character_identity.json"
    bi_path = project_root / "buffs_infrastructure.json"

    for path, label in [(ci_path, "character_identity"), (bi_path, "buffs_infrastructure")]:
        if not path.exists():
            print(f"[错误] 找不到数据文件: {path}")
            print("[提示] 请确保两个文件已放置在项目根目录")
            return

    print("[加载] 正在解析 character_identity.json + buffs_infrastructure.json ...")
    all_operators = load_operators_v2(ci_path, bi_path)

    total_skills = sum(len(op.skills) for op in all_operators)
    ops_with_skills = sum(1 for op in all_operators if op.skills)
    print(f"[加载] 干员总数: {len(all_operators)}, 有基建技能: {ops_with_skills}, 技能条目: {total_skills}")

    mfg_ops = [op for op in all_operators if op.has_skill_for("Mfg")]
    trade_ops = [op for op in all_operators if op.has_skill_for("Trade")]
    ctrl_ops = [op for op in all_operators if op.has_skill_for("Control")]
    print(f"[统计] 制造站: {len(mfg_ops)}, 贸易站: {len(trade_ops)}, 控制中枢: {len(ctrl_ops)}")

    print("\n[求解] 运行 MVP 求解器 (制造站穷举+剪枝+贪心, 12h)...")
    result = solve_mvp(all_operators)

    print(f"[结果] 补位房间数: {result.autofill_count}\n")
    for a in result.plans[0].assignments:
        tag = " [autofill]" if a.autofill else ""
        product_str = f" ({a.product})" if a.product else ""
        print(f"  {a.room_type}[{a.room_index}]{product_str}: {a.operators}{tag}")

    output_path = project_root / "output" / "custom_infrast" / "mvp_12h.json"
    save_json(result, output_path, title="MVP 全box满练度 12h排班")


if __name__ == "__main__":
    main()
