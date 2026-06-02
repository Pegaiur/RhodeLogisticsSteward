r"""排班生产报表 — 多班次轮换分析

用法:
    python report.py 12 14       # 14班x12h (7天)
    python report.py 8 3         # 3班x8h

此脚本复用 steward_core.report 统一格式化模块。
如需保存 JSON 排班文件，请使用 run_solver.py。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from steward_core.data_loader import load_operators_v2
from steward_core.solver.params import SolverParams
from steward_core.pipeline import run as run_pipeline
from steward_core.report import save_report_md


def main():
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    shifts = int(sys.argv[2]) if len(sys.argv) > 2 else 14
    root = Path(__file__).parent

    ops = load_operators_v2(
        root / "character_identity.json",
        root / "buffs_infrastructure.json",
    )
    params = SolverParams(shift_count=shifts, shift_hours=hours)

    print(f"  [求解] SlotStrategy, {shifts}x{hours:.0f}h...")
    pipe = run_pipeline(ops, params)

    filepath = save_report_md(pipe, output_path="", brief=False)
    print(f"  [报告] {filepath}")


if __name__ == "__main__":
    main()
