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
from steward_core import production
from steward_core.production import _RECORD_EXP_PER_UNIT, _GOLD_LMD_PER_UNIT


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

    # ── 12h 产出计算 ──
    print("\n[产出] 计算 12h 生产结果...\n")
    dp = production.calculate(
        result.plans[0], all_operators, hours=12.0,
        external_gold_per_day=result.config_used.params.daily_task_lmd / _GOLD_LMD_PER_UNIT,
    )

    print("── 作战记录（经验）──")
    for room in dp.record_rooms:
        drone = f" (含无人机+{room.drone_boost_pct:.0%})" if room.drone_boost_pct > 0 else ""
        head_base = 100 + room.head_count
        skill_pct = (room.productivity - 1.0) * 100
        exp_value = room.output_per_day * _RECORD_EXP_PER_UNIT
        print(f"  Mfg[{room.room_index}]: {room.operators} → {exp_value:,.0f} 经验/12h (基础{head_base}%+{skill_pct:.0f}%){drone}")
    total_exp = dp.total_records_per_day * _RECORD_EXP_PER_UNIT
    print(f"  合计: {total_exp:,.0f} 经验/12h\n")

    print("── 赤金制造 ──")
    for room in dp.gold_rooms:
        drone = f" (含无人机+{room.drone_boost_pct:.0%})" if room.drone_boost_pct > 0 else ""
        head_base = 100 + room.head_count
        skill_pct = (room.productivity - 1.0) * 100
        lmd_value = room.output_per_day * _GOLD_LMD_PER_UNIT
        print(f"  Mfg[{room.room_index}]: {room.operators} → {lmd_value:,.0f} LMD等值/12h (基础{head_base}%+{skill_pct:.0f}%){drone}")
    total_gold_lmd = dp.total_gold_produced_per_day * _GOLD_LMD_PER_UNIT
    print(f"  合计: {total_gold_lmd:,.0f} LMD等值/12h")
    if dp.external_gold_per_day > 0:
        shift_hours = result.config_used.params.shift_hours
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
        print(f"  Trade[{room.room_index}]: {room.operators} → {room.output_per_day:,.0f} LMD/12h (基础{head_base}%+{skill_pct:.0f}%){drone}  |  消耗赤金 {gold_use:.1f}/12h")
    print(f"  合计: {dp.total_lmd_per_day:,.0f} LMD/12h")
    print(f"  赤金消耗: {dp.total_gold_consumed_per_day:.1f} 个/12h (等值 {dp.total_gold_consumed_per_day * _GOLD_LMD_PER_UNIT:,.0f} LMD)")
    if dp.gold_surplus >= 0:
        print(f"  赤金盈余: +{dp.gold_surplus:.1f} 个/12h")
    else:
        print(f"  赤金缺口: {abs(dp.gold_surplus):.1f} 个 → 有效收入 {dp.effective_lmd_per_day:,.0f} LMD/12h")

    output_path = project_root / "output" / "custom_infrast" / "mvp_12h.json"
    save_json(result, output_path, title="MVP 全box满练度 12h排班")


if __name__ == "__main__":
    main()
