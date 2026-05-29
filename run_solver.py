r"""MVP 全 box 满练度求解器

用法:
    python run_solver.py                              # 默认 baseline 12h
    python run_solver.py --strategy kbeam3            # K-Beam K=3
    python run_solver.py --strategy iterative         # 不动点迭代
    python run_solver.py --strategy baseline --all-on # 三开关全开
    python run_solver.py --hours 24                   # 24h 班次
    python run_solver.py --params custom.json         # 自定义参数文件
    python run_solver.py --list                       # 列出可用策略

数据文件 (character_identity.json + buffs_infrastructure.json) 需在项目根目录。
输出 output/custom_infrast/ 目录。
"""

from pathlib import Path

from steward_core.data_loader import load_operators_v2
from steward_core.output import save_json
from steward_core.solver import solve_mvp
from steward_core.solver.config import SolverConfig
from steward_core.solver.strategies import STRATEGY_REGISTRY
from steward_core import production
from steward_core.production import _RECORD_EXP_PER_UNIT, _GOLD_LMD_PER_UNIT


def _parse_cli():
    args = []
    for a in __import__("sys").argv[1:]:
        args.append(a)

    strategy_key = "baseline"
    params_file = None
    hours_override = None
    all_on = False
    strategy_kwargs = {}

    i = 0
    while i < len(args):
        if args[i] == "--strategy" and i + 1 < len(args):
            strategy_key = args[i + 1]; i += 2
        elif args[i] == "--params" and i + 1 < len(args):
            params_file = args[i + 1]; i += 2
        elif args[i] == "--hours" and i + 1 < len(args):
            hours_override = float(args[i + 1]); i += 2
        elif args[i] == "--kw" and i + 1 < len(args):
            kw_val = args[i + 1]
            if kw_val.startswith("-"):
                print(f"[错误] --kw 的值不能以 '-' 开头: {kw_val}")
                return None
            for kv in kw_val.split(","):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    try:
                        strategy_kwargs[k] = int(v) if v.lstrip("-").isdigit() else float(v)
                    except ValueError:
                        strategy_kwargs[k] = v
            i += 2
        elif args[i] in ("--all-on",):
            all_on = True; i += 1
        elif args[i] in ("--list",):
            _print_strategies(); return None
        else:
            print(f"[警告] 未知参数: {args[i]}"); i += 1

    return strategy_key, params_file, hours_override, all_on, strategy_kwargs


def _print_strategies():
    print("可用策略:")
    for key, (cls, kwargs) in STRATEGY_REGISTRY.items():
        kw_str = ", ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else "默认参数"
        print(f"  {key:14s} {cls.name:10s}  ({kw_str})")


def _build_config(strategy_key, all_on, strategy_kwargs, params_file, hours_override):
    from steward_core.solver.params import SolverParams

    if strategy_key not in STRATEGY_REGISTRY:
        print(f"[错误] 未知策略 '{strategy_key}'，可用: {list(STRATEGY_REGISTRY)}")
        return None

    strategy_cls, default_kwargs = STRATEGY_REGISTRY[strategy_key]
    merged_kwargs = {**default_kwargs, **strategy_kwargs}
    strategy = strategy_cls(**merged_kwargs)

    if params_file:
        params = SolverParams.from_json(params_file)
        print(f"[参数] 已加载 {params_file}")
    else:
        params = strategy_kwargs.get("params", SolverParams())

    if hours_override is not None:
        params = params.apply_overrides(shift_hours=hours_override)

    if all_on:
        config = SolverConfig.all_on()
    else:
        config = SolverConfig()
    config.strategy = strategy
    config.params = params
    return config


def main():
    parsed = _parse_cli()
    if parsed is None:
        return
    strategy_key, params_file, hours_override, all_on, strategy_kwargs = parsed

    config = _build_config(strategy_key, all_on, strategy_kwargs, params_file, hours_override)
    if config is None:
        return

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

    shift_hours = config.params.shift_hours
    strategy_name = strategy_key
    print(f"\n[求解] 策略={strategy_name}, {shift_hours:.0f}h, 开关={'all-on' if all_on else 'baseline'}...")
    result = solve_mvp(all_operators, config=config)

    print(f"[结果] 补位房间数: {result.autofill_count}\n")
    for a in result.plans[0].assignments:
        tag = " [autofill]" if a.autofill else ""
        product_str = f" ({a.product})" if a.product else ""
        print(f"  {a.room_type}[{a.room_index}]{product_str}: {a.operators}{tag}")

    # ── 产出计算 ──
    print(f"\n[产出] 计算 {shift_hours:.0f}h 生产结果...\n")
    dp = production.calculate(
        result.plans[0], all_operators, hours=shift_hours,
        external_gold_per_day=config.params.daily_task_lmd / _GOLD_LMD_PER_UNIT,
    )

    print("── 作战记录（经验）──")
    for room in dp.record_rooms:
        drone = f" (含无人机+{room.drone_boost_pct:.0%})" if room.drone_boost_pct > 0 else ""
        head_base = 100 + room.head_count
        skill_pct = (room.productivity - 1.0) * 100
        exp_value = room.output_per_day * _RECORD_EXP_PER_UNIT
        print(f"  Mfg[{room.room_index}]: {room.operators} → {exp_value:,.0f} 经验/{shift_hours:.0f}h (基础{head_base}%+{skill_pct:.0f}%){drone}")
    total_exp = dp.total_records_per_day * _RECORD_EXP_PER_UNIT
    print(f"  合计: {total_exp:,.0f} 经验/{shift_hours:.0f}h\n")

    print("── 赤金制造 ──")
    for room in dp.gold_rooms:
        drone = f" (含无人机+{room.drone_boost_pct:.0%})" if room.drone_boost_pct > 0 else ""
        head_base = 100 + room.head_count
        skill_pct = (room.productivity - 1.0) * 100
        lmd_value = room.output_per_day * _GOLD_LMD_PER_UNIT
        print(f"  Mfg[{room.room_index}]: {room.operators} → {lmd_value:,.0f} LMD等值/{shift_hours:.0f}h (基础{head_base}%+{skill_pct:.0f}%){drone}")
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
        print(f"  Trade[{room.room_index}]: {room.operators} → {room.output_per_day:,.0f} LMD/{shift_hours:.0f}h (基础{head_base}%+{skill_pct:.0f}%){drone}  |  消耗赤金 {gold_use:.1f}/{shift_hours:.0f}h")
    print(f"  合计: {dp.total_lmd_per_day:,.0f} LMD/{shift_hours:.0f}h")
    print(f"  赤金消耗: {dp.total_gold_consumed_per_day:.1f} 个/{shift_hours:.0f}h (等值 {dp.total_gold_consumed_per_day * _GOLD_LMD_PER_UNIT:,.0f} LMD)")
    if dp.gold_surplus >= 0:
        print(f"  赤金盈余: +{dp.gold_surplus:.1f} 个/{shift_hours:.0f}h")
    else:
        print(f"  赤金缺口: {abs(dp.gold_surplus):.1f} 个 → 有效收入 {dp.effective_lmd_per_day:,.0f} LMD/{shift_hours:.0f}h")

    suffix = f"243_layout_单班_a_day_{strategy_key}_{shift_hours:.0f}h"
    output_path = project_root / "output" / "custom_infrast" / f"{suffix}.json"
    save_json(result, output_path, title=f"排班方案 {strategy_key} {shift_hours:.0f}h")


if __name__ == "__main__":
    main()
