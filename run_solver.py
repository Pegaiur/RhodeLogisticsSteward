r"""全 box 满练度求解器 — 槽位加工模型

用法:
    python run_solver.py                              # 默认 14班x12h (7天)
    python run_solver.py --hours 8 --shifts 3         # 3班x8h
    python run_solver.py --params custom.json          # 自定义参数文件
    python run_solver.py --brief                      # 简洁模式，跳过详细排班明细
    python run_solver.py --report                     # 只输出报表，不保存 JSON

数据文件 (character_identity.json + buffs_infrastructure.json) 需在项目根目录。
输出 output/custom_infrast/ 目录。
"""

from pathlib import Path

from steward_core.data_loader import load_operators_v2
from steward_core.output import save_json
from steward_core.solver.params import SolverParams
from steward_core.pipeline import run as run_pipeline
from steward_core.report import save_report_md


def _parse_cli():
    args = list(__import__("sys").argv[1:])

    params_file = None
    hours_override = 12.0
    shifts_override = 14
    brief_mode = False
    report_only = False

    i = 0
    while i < len(args):
        if args[i] == "--params" and i + 1 < len(args):
            params_file = args[i + 1]; i += 2
        elif args[i] == "--hours" and i + 1 < len(args):
            hours_override = float(args[i + 1]); i += 2
        elif args[i] == "--shifts" and i + 1 < len(args):
            shifts_override = int(args[i + 1]); i += 2
        elif args[i] == "--brief":
            brief_mode = True; i += 1
        elif args[i] == "--report":
            report_only = True; i += 1
        else:
            print(f"[警告] 未知参数: {args[i]}"); i += 1

    return params_file, hours_override, shifts_override, brief_mode, report_only


def main():
    params_file, hours_override, shifts_override, brief_mode, report_only = _parse_cli()

    if params_file:
        params = SolverParams.from_json(params_file)
        print(f"[参数] 已加载 {params_file}")
    else:
        params = SolverParams()

    shift_hours = hours_override
    shift_count = shifts_override
    params = params.apply_overrides(
        shift_hours=shift_hours,
        shift_count=shift_count,
    )

    project_root = Path(__file__).resolve().parent
    ci_path = project_root / "character_identity.json"
    bi_path = project_root / "buffs_infrastructure.json"

    for path, label in [(ci_path, "character_identity"), (bi_path, "buffs_infrastructure")]:
        if not path.exists():
            print(f"[错误] 找不到数据文件: {path}")
            print("[提示] 请确保两个文件已放置在项目根目录")
            return

    all_operators = load_operators_v2(ci_path, bi_path)

    ops_with_skills = sum(1 for op in all_operators if op.skills)
    mfg_ops = [op for op in all_operators if op.has_skill_for("Mfg")]
    trade_ops = [op for op in all_operators if op.has_skill_for("Trade")]
    ctrl_ops = [op for op in all_operators if op.has_skill_for("Control")]

    print(f"  [数据] 干员 {len(all_operators)} | "
          f"有技能 {ops_with_skills} | "
          f"制造 {len(mfg_ops)} | "
          f"贸易 {len(trade_ops)} | "
          f"中枢 {len(ctrl_ops)}")

    mode_desc = f"{shift_count}x{shift_hours:.0f}h"
    print(f"  [求解] SlotStrategy, {mode_desc}...")

    pipe = run_pipeline(all_operators, params)

    suffix = f"243_layout_slot_{shift_hours:.0f}h_x{shift_count}"
    output_path = project_root / "output" / "custom_infrast" / f"{suffix}.json"

    if not report_only:
        save_json(pipe.solve_result, output_path,
                  title=f"排班方案 slot {shift_count}x{shift_hours:.0f}h")
        opath = str(output_path)
    else:
        opath = ""

    report = save_report_md(pipe, output_path=opath, brief=brief_mode)
    print(f"  [报告] {report}")


if __name__ == "__main__":
    main()
