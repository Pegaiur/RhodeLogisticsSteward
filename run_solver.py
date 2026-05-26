r"""Step 1: 全 box 满练度基线求解器

用法:
    python run_solver.py --maa-path "G:\Tools\MAA-v4.28.4-win-x64"

在未指定数据文件时，自动从 ArknightsGameData 下载（首次运行）。
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from steward_core.data_loader import load_operators
from steward_core.models import LayoutConfig
from steward_core.output import compare_with_baseline, save_json
from steward_core.production import calculate as calculate_production
from steward_core.solver import solve_single_shift

BUILDING_DATA_URL = (
    "https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/zh_CN/gamedata/excel/building_data.json"
)
CHARACTER_TABLE_URL = (
    "https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/zh_CN/gamedata/excel/character_table.json"
)


def _download(url: str, target: Path) -> None:
    """下载文件，失败则 exit"""
    if target.exists():
        print(f"[数据] {target.name} 已存在: {target}")
        return
    print(f"[数据] 下载 {target.name} ...")
    try:
        urllib.request.urlretrieve(url, target)
        print(f"[数据] 下载完成: {target}")
    except Exception as e:
        print(f"[错误] 下载失败: {e}")
        print(f"[提示] 请手动下载到: {target}")
        print(f"       URL: {url}")
        sys.exit(1)


def _build_name_lookup(character_table_path: Path) -> dict[str, str]:
    """从 character_table.json 构建 char_id → name 映射"""
    with open(character_table_path, "r", encoding="utf-8") as f:
        table = json.load(f)
    lookup: dict[str, str] = {}
    for char_id, data in table.items():
        name = data.get("name", char_id)
        lookup[char_id] = name
    return lookup


def main():
    parser = argparse.ArgumentParser(description="Step 1: 全 box 满练度基线求解器")
    parser.add_argument(
        "--maa-path",
        required=True,
        help="MAA 安装路径（用于读取 resource/infrast.json）",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="输出 JSON 路径（默认 output/custom_infrast/step1_single_shift.json）",
    )
    parser.add_argument(
        "--baseline",
        default=None,
        help="MAA 基准模板路径（用于对比报告），默认自动查找",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    maa_path = Path(args.maa_path)

    infrast_path = maa_path / "resource" / "infrast.json"
    if not infrast_path.exists():
        print(f"[错误] 找不到 infrast.json: {infrast_path}")
        sys.exit(1)

    # 确保数据文件存在
    building_data_path = project_root / "building_data.json"
    character_table_path = project_root / "character_table.json"
    _download(BUILDING_DATA_URL, building_data_path)
    _download(CHARACTER_TABLE_URL, character_table_path)

    # 构建名称映射
    print("[数据] 构建干员名称映射 ...")
    name_lookup = _build_name_lookup(character_table_path)
    print(f"[数据] 名称映射条目: {len(name_lookup)}")

    # 加载数据
    print("[加载] 正在解析 building_data.json + infrast.json ...")
    all_operators = load_operators(building_data_path, infrast_path, name_lookup=name_lookup)

    total_skills = sum(len(op.skills) for op in all_operators)
    ops_with_skills = sum(1 for op in all_operators if op.skills)
    print(f"[加载] 干员总数: {len(all_operators)}, 有基建技能: {ops_with_skills}, 技能条目: {total_skills}")

    # 求解
    print("[求解] 运行单班次贪心求解器 (243 布局)...")
    layout = LayoutConfig.layout_243()
    result = solve_single_shift(all_operators, layout, shift_name="Step1 全 box 满练度")

    # 无人机加速：对准第一间经验房（最高产能）
    result.plans[0].drone_room = "Mfg"
    result.plans[0].drone_index = 0

    print(f"[结果] 补位房间数: {result.autofill_count}")

    for plan in result.plans:
        for a in plan.assignments:
            tag = " [autofill]" if a.autofill else ""
            product_str = f" ({a.product})" if a.product else ""
            print(f"  {a.room_type}[{a.room_index}]{product_str}: {a.operators}{tag}")

    # 精确产出计算
    print("\n[产出] 基于 PRTS 公式的日产出估算：")
    production = calculate_production(result.plans[0], all_operators)
    for room in production.record_rooms:
        print(f"  {room}")
    for room in production.gold_rooms:
        print(f"  {room}")
    for room in production.trade_rooms:
        print(f"  {room}")
    print(f"\n{production.summary()}")

    # 保存
    output_path = (
        Path(args.output) if args.output
        else project_root / "output" / "custom_infrast" / "step1_single_shift.json"
    )
    save_json(result, output_path, title="Step1 全box满练度单班次")

    # 基准对比
    baseline_path = (
        Path(args.baseline) if args.baseline
        else maa_path / "resource" / "custom_infrast" / "243_layout_3_times_a_day.json"
    )
    if baseline_path.exists():
        print(f"\n[对比] 基准模板: {baseline_path.name}")
        comparison = compare_with_baseline(result, baseline_path)
        print(f"[对比] 总匹配率: {comparison['overall_match_rate']:.1%}")
        print(f"[对比] 匹配/总工位: {comparison['total_matched']}/{comparison['total_slots']}")
        if comparison.get("mismatched_pairs"):
            print(f"[对比] 不匹配项 ({len(comparison['mismatched_pairs'])} 处):")
            for m in comparison["mismatched_pairs"]:
                print(f"  {m['facility']}: 我们={m['our']}, 基准={m['baseline']}")
    else:
        print(f"\n[对比] 基准模板未找到: {baseline_path}")


if __name__ == "__main__":
    main()
