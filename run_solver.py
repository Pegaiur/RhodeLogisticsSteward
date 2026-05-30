r"""全 box 满练度求解器 — 槽位加工模型

用法:
    python run_solver.py                              # 默认 3班×8h+8h
    python run_solver.py --hours 12                   # 3班×12h+8h
    python run_solver.py --params custom.json         # 自定义参数文件

数据文件 (character_identity.json + buffs_infrastructure.json) 需在项目根目录。
输出 output/custom_infrast/ 目录。
"""

from pathlib import Path

from steward_core.data_loader import load_operators_v2
from steward_core.output import save_json
from steward_core.solver import solve_mvp
from steward_core.solver.config import SolverConfig
from steward_core.solver.params import SolverParams
from steward_core import production
from steward_core.production import _RECORD_EXP_PER_UNIT, _GOLD_LMD_PER_UNIT


def _parse_cli():
    args = list(__import__("sys").argv[1:])

    params_file = None
    hours_override = 8.0

    i = 0
    while i < len(args):
        if args[i] == "--params" and i + 1 < len(args):
            params_file = args[i + 1]; i += 2
        elif args[i] == "--hours" and i + 1 < len(args):
            hours_override = float(args[i + 1]); i += 2
        else:
            print(f"[警告] 未知参数: {args[i]}"); i += 1

    return params_file, hours_override


def main():
    params_file, hours_override = _parse_cli()

    if params_file:
        params = SolverParams.from_json(params_file)
        print(f"[参数] 已加载 {params_file}")
    else:
        params = SolverParams()

    shift_hours = hours_override
    interval_hours = 8.0
    shift_count = 3
    params = params.apply_overrides(
        shift_hours=shift_hours,
        shift_count=shift_count,
        interval_hours=interval_hours,
    )

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

    mode_desc = f"{shift_count}x{shift_hours:.0f}h+{interval_hours:.0f}h"
    print(f"\n[求解] SlotStrategy, {mode_desc}...")

    from steward_core.mood_flow import MoodContext
    mood_ctx = MoodContext.fresh(all_operators, params)
    config = SolverConfig(params=params, mood_ctx=mood_ctx)
    result = solve_mvp(all_operators, config=config)
    all_plans = result.plans

    print(f"[结果] 班次数: {len(all_plans)}\n")

    for pi, plan in enumerate(all_plans):
        print(f"── 班次 {pi + 1}: {plan.name} ──")
        for a in plan.assignments:
            tag = " [autofill]" if a.autofill else ""
            product_str = f" ({a.product})" if a.product else ""
            print(f"  {a.room_type}[{a.room_index}]{product_str}: {a.operators}{tag}")

    for pi, plan in enumerate(all_plans):
        print(f"\n[产出·班次{pi + 1}] {shift_hours:.0f}h 生产结果...\n")

        dp = production.calculate(
            plan, all_operators, hours=shift_hours,
            external_gold_per_day=params.daily_task_lmd / _GOLD_LMD_PER_UNIT,
        )

        print("── 作战记录（经验）──")
        for room in dp.record_rooms:
            drone = f" (含无人机+{room.drone_boost_pct:.0%})" if room.drone_boost_pct > 0 else ""
            head_base = 100 + room.head_count
            skill_pct = (room.productivity - 1.0) * 100
            exp_value = room.output_per_day * _RECORD_EXP_PER_UNIT
            print(f"  Mfg[{room.room_index}]: {room.operators} -> {exp_value:,.0f} 经验/{shift_hours:.0f}h (基础{head_base}%+{skill_pct:.0f}%){drone}")
        total_exp = dp.total_records_per_day * _RECORD_EXP_PER_UNIT
        print(f"  合计: {total_exp:,.0f} 经验/{shift_hours:.0f}h\n")

        print("── 赤金制造 ──")
        for room in dp.gold_rooms:
            drone = f" (含无人机+{room.drone_boost_pct:.0%})" if room.drone_boost_pct > 0 else ""
            head_base = 100 + room.head_count
            skill_pct = (room.productivity - 1.0) * 100
            lmd_value = room.output_per_day * _GOLD_LMD_PER_UNIT
            print(f"  Mfg[{room.room_index}]: {room.operators} -> {lmd_value:,.0f} LMD等值/{shift_hours:.0f}h (基础{head_base}%+{skill_pct:.0f}%){drone}")
        total_gold_lmd = dp.total_gold_produced_per_day * _GOLD_LMD_PER_UNIT
        print(f"  合计: {total_gold_lmd:,.0f} LMD等值/{shift_hours:.0f}h")
        if dp.external_gold_per_day > 0:
            external_gold_shift = dp.external_gold_per_day * (shift_hours / 24.0)
            external_lmd_shift = external_gold_shift * _GOLD_LMD_PER_UNIT
            print(f"  外部收入: +{external_lmd_shift:,.0f} LMD等值/{shift_hours:.0f}h ({external_gold_shift:.1f} 赤金)\n")
        else:
            print()

        print("── 贸易站（龙门币）──")
        for room in dp.trade_rooms:
            drone = f" (含无人机+{room.drone_boost_pct:.0%})" if room.drone_boost_pct > 0 else ""
            head_base = 100 + room.head_count
            skill_pct = (room.productivity - 1.0) * 100
            gold_use = room.output_per_day / dp.total_lmd_per_day * dp.total_gold_consumed_per_day
            print(f"  Trade[{room.room_index}]: {room.operators} -> {room.output_per_day:,.0f} LMD/{shift_hours:.0f}h (基础{head_base}%+{skill_pct:.0f}%){drone}  |  消耗赤金 {gold_use:.1f}/{shift_hours:.0f}h")
        print(f"  合计: {dp.total_lmd_per_day:,.0f} LMD/{shift_hours:.0f}h")
        print(f"  赤金消耗: {dp.total_gold_consumed_per_day:.1f} 个/{shift_hours:.0f}h (等值 {dp.total_gold_consumed_per_day * _GOLD_LMD_PER_UNIT:,.0f} LMD)")
        if dp.gold_surplus >= 0:
            print(f"  赤金盈余: +{dp.gold_surplus:.1f} 个/{shift_hours:.0f}h")
        else:
            print(f"  赤金缺口: {abs(dp.gold_surplus):.1f} 个 -> 有效收入 {dp.effective_lmd_per_day:,.0f} LMD/{shift_hours:.0f}h")

    suffix = f"243_layout_slot_{shift_hours:.0f}h_x{shift_count}"
    output_path = project_root / "output" / "custom_infrast" / f"{suffix}.json"
    save_json(result, output_path, title=f"排班方案 slot {shift_count}×{shift_hours:.0f}h")


if __name__ == "__main__":
    main()
