"""统一排班报告格式化模块

将 PipelineResult 渲染为 Markdown 报告，覆盖参数摘要、换班分析、
产能汇总、心情验证，一站式满足多班次（如 7 天 14x12h）测试需求。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from steward_core import mood as mood_calc
from steward_core.constants import FACILITY_SLOTS, NON_WORK_FACILITIES
from steward_core.production import _RECORD_EXP_PER_UNIT, _GOLD_LMD_PER_UNIT

if TYPE_CHECKING:
    from steward_core.pipeline import PipelineResult
    from steward_core.solver.params import SolverParams
    from steward_core.models import ShiftPlan, Operator, RoomAssignment
    from steward_core.production import DailyProduction
    from steward_core.mood import MoodReport

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def _strategy_name(pipe: "PipelineResult") -> str:
    config = pipe.config
    if config.strategy is not None:
        return config.strategy.name
    return "SlotStrategy"


def format_header(pipe: "PipelineResult", output_path: str = "") -> str:
    """排班报告头部"""
    params = pipe.params
    total_h = params.shift_count * params.shift_hours
    days = total_h / 24.0
    lines = [
        "# RhodeLogisticsSteward 排班报告",
        "",
        f"**策略**: {_strategy_name(pipe)}  ·  "
        f"{params.shift_count}x{params.shift_hours:.0f}h={total_h:.0f}h ({days:.1f}天)  ·  "
        f"干员 {len(pipe.operators)} 人",
        "",
    ]
    if output_path:
        lines.append(f"**排班文件**: `{output_path}`")
        lines.append("")
    return "\n".join(lines)


def format_params(params: "SolverParams") -> str:
    """求解参数摘要"""
    total_h = params.shift_count * params.shift_hours
    days = total_h / 24.0
    lines = [
        "## 求解参数",
        "",
        f"- **排班**: {params.shift_count}班 × {params.shift_hours:.0f}h = {total_h:.0f}h ({days:.1f}天)",
        f"- **心情**: 消耗率 {params.base_burn_rate3:.2f} (3人房), "
        f"满 {params.mood_full:.0f}h, 工作阈值 {params.mood_work_threshold:.1f}h",
        f"- **设施**: 中枢 {params.control_max_slots}槽, "
        f"发电 {params.base_power_count}间, "
        f"宿舍 {params.dorm_room_count}×{params.dorm_room_size}=Lv{params.dorm_levels_sum}",
        f"- **外部**: 日常任务 {params.daily_task_lmd:,.0f} LMD/天",
    ]
    solver_parts = [f"槽位迭代 ≤{params.slot_max_rounds}轮"]
    if params.slot_cold_start:
        solver_parts.append("冷启动=是")
    solver_parts.append(f"剪枝阈值 {params.combo_upper_bound_threshold:.2f}")
    lines.append(f"- **求解**: {', '.join(solver_parts)}")
    lines.append("")
    return "\n".join(lines)


def _compute_chained_mood_reports(
    plans: list["ShiftPlan"],
    operators: list["Operator"],
    shift_hours: float,
    params: "SolverParams | None" = None,
) -> list["MoodReport"]:
    """链式计算跨班次心情报告

    使用 MoodContext 正确传递班次间的心情状态（消耗+宿舍恢复），
    替代 mood_calc.calculate() 独立计算导致的"每个班次都从满心情开始"问题。
    与 solve_slot() 中 MoodContext 流转逻辑保持一致。
    """
    from steward_core.mood_flow import MoodContext, RoomBurnContext

    mc = MoodContext.fresh(operators, params)
    reports: list["MoodReport"] = []

    for plan in plans:
        report = mood_calc.calculate(
            plan, operators, shift_hours,
            initial_moods=dict(mc.operator_moods),
        )
        reports.append(report)

        # 更新 MoodContext 准备下一班次
        mc.control_operators = report.control_operators

        working_names: set[str] = set()
        working_slots: dict[str, "RoomBurnContext"] = {}
        for a in plan.assignments:
            if a.room_type in NON_WORK_FACILITIES or not a.operators:
                continue
            for name in a.operators:
                working_names.add(name)
                working_slots[name] = RoomBurnContext(
                    room_type=a.room_type,
                    room_slots=FACILITY_SLOTS.get(a.room_type, 3),
                    room_index=a.room_index,
                    co_workers=a.operators,
                )

        mc = mc.after_shift(working_names, working_slots=working_slots)

        # 应用宿舍恢复
        dorm_map: dict[str, str] = {}
        for a in plan.assignments:
            if a.room_type == "Dormitory":
                for name in a.operators:
                    dorm_map[name] = str(a.room_index)

        if dorm_map:
            mc = replace(mc, dorm_assignments=dorm_map)
            new_moods = dict(mc.operator_moods)
            for name in dorm_map:
                rate = mc.dorm_recovery(name)
                if rate > 0:
                    new_moods[name] = min(24.0, new_moods.get(name, 24.0) + rate * shift_hours)
            mc = replace(mc, operator_moods=new_moods)

    return reports


_PRODUCT_ABBR: dict[str, str] = {"CombatRecord": "CR", "PureGold": "PG"}


def _plan_names(plan: "ShiftPlan") -> set[str]:
    names: set[str] = set()
    for a in plan.assignments:
        if a.operators:
            names.update(a.operators)
    return names


def format_swaps(plans: list["ShiftPlan"]) -> str:
    """换班分析 — 相邻重叠统计 + 逐设施换班表"""
    n = len(plans)
    lines = ["## 换班分析", ""]

    # 相邻重叠摘要
    if n >= 2:
        diffs: list[int] = []
        overlaps: list[int] = []
        for wi in range(1, n):
            ni = _plan_names(plans[wi])
            nj = _plan_names(plans[wi - 1])
            overlaps.append(len(ni & nj))
            diffs.append(len(ni) - len(ni & nj))
        avg_o = sum(overlaps) / len(overlaps)
        avg_d = sum(diffs) / len(diffs)

        diff_parts = []
        overlap_parts = []
        for wi in range(1, n):
            diff_parts.append(f"W{wi - 1}→{wi}:{diffs[wi - 1]}")
            overlap_parts.append(f"W{wi - 1}→{wi}:{overlaps[wi - 1]}")
        lines.append(f"班间换人: {' '.join(diff_parts)}  (均值 {avg_d:.1f})")
        lines.append(f"相邻重叠: {' '.join(overlap_parts)}  (均值 {avg_o:.1f}, 范围 {min(overlaps)}-{max(overlaps)})")
        lines.append("")

    # 逐设施换班表
    tracked = [
        ("Control", 0), ("Trade", 0), ("Trade", 1),
        ("Mfg", 0), ("Mfg", 1), ("Mfg", 2), ("Mfg", 3),
    ]
    lines.extend([
        "| 设施 | 换班 | 比例 |",
        "|------|------|------|",
    ])
    shifts_n = max(n - 1, 1)
    for ft, ri in tracked:
        prev_ops: set[str] = set()
        swaps = 0
        for pi, plan in enumerate(plans):
            for a in plan.assignments:
                if a.room_type == ft and a.room_index == ri:
                    cur = set(a.operators)
                    if pi > 0 and cur != prev_ops:
                        swaps += 1
                    prev_ops = cur
                    break
        rate = swaps / shifts_n * 100
        lines.append(f"| {ft}[{ri}] | {swaps}/{shifts_n} | {rate:.0f}% |")

    lines.append("")
    return "\n".join(lines)


def format_production_table(
    productions: list["DailyProduction"],
    shift_hours: float,
    mood_reports: list["MoodReport"] | None = None,
) -> str:
    """各班次产能明细表"""
    h = int(shift_hours)
    cols = ["班次", f"经验/{h}h", f"LMD/{h}h", "赤金盈余", "vsW0经验", "vsW0LMD", "心情"]
    ml_header = "| " + " | ".join(cols) + " |"
    ml_sep = "|" + "|".join(["------:" for _ in cols]) + "|"
    lines = [
        "## 产能明细",
        "",
        ml_header,
        ml_sep,
    ]
    ref_exp = productions[0].total_records_per_day * _RECORD_EXP_PER_UNIT if productions else 0.0
    ref_lmd = productions[0].effective_lmd_per_day if productions else 0.0

    for pi, dp in enumerate(productions):
        exp = dp.total_records_per_day * _RECORD_EXP_PER_UNIT
        lmd = dp.effective_lmd_per_day
        de = exp - ref_exp
        dl = lmd - ref_lmd
        mood_str = ""
        if mood_reports and pi < len(mood_reports):
            mr = mood_reports[pi]
            mood_str = "OK" if mr.red_face_count == 0 else f"!{mr.red_face_count}"
        lines.append(
            f"| W{pi} | {exp:,.0f} | {lmd:,.0f} | "
            f"{dp.gold_surplus:+.1f} | {de:+,.0f} | {dl:+,.0f} | {mood_str} |"
        )

    lines.append("")
    return "\n".join(lines)


def format_24h_summary(productions: list["DailyProduction"], total_hours: float) -> str:
    """24h 折算产能汇总"""
    scale = 24.0 / total_hours if total_hours > 0 else 0.0
    sum_exp = sum(p.total_records_per_day for p in productions) * _RECORD_EXP_PER_UNIT * scale
    sum_gold = sum(p.total_gold_produced_per_day for p in productions) * _GOLD_LMD_PER_UNIT * scale
    sum_lmd = sum(p.total_lmd_per_day for p in productions) * scale
    sum_eff_lmd = sum(p.effective_lmd_per_day for p in productions) * scale
    surplus_gold = sum(p.gold_surplus for p in productions) * scale
    surplus_lmd = surplus_gold * _GOLD_LMD_PER_UNIT

    lines = [
        "## 24h 折算产能",
        "",
        f"- 作战记录经验: **{sum_exp:,.0f}** /天",
        f"- 赤金制造等值: **{sum_gold:,.0f}** LMD /天",
    ]
    labeled = f"- 龙门币收入:   **{sum_eff_lmd:,.0f}** /天"
    if sum_lmd != sum_eff_lmd:
        labeled += f" _(理论 {sum_lmd:,.0f}，赤金不足缩减)_"
    lines.append(labeled)
    if surplus_gold >= 0:
        lines.append(f"- 赤金盈余:     **{surplus_lmd:,.0f}** LMD等值 /天")
    else:
        lines.append(f"- 赤金缺口:     **{abs(surplus_lmd):,.0f}** LMD等值 /天")
    lines.append("")
    return "\n".join(lines)


_GROUP_LABELS: dict[str, str] = {
    "Control": "Ctl", "Trade": "Trade", "Power": "Power",
    "Reception": "Rec", "Office": "Ofc", "Dormitory": "Dorm",
}

_GROUP_ORDER = ["Ctl", "CR", "PG", "Trade", "Power", "Rec", "Ofc", "Dorm"]


def _group_shift_assignments(
    assignments: list["RoomAssignment"],
) -> list[tuple[str, list[str]]]:
    """将班次排班按类型+产物分组，返回 [(标签, [房间条目]), ...]

    同类型房间同行显示但不合并干员：CR[0]: [...]  CR[1]: [...]
    """
    groups: dict[str, list[tuple[int, list[str]]]] = {}
    for a in assignments:
        if not a.operators:
            continue
        rt = a.room_type
        if rt == "Mfg" and a.product:
            label = _PRODUCT_ABBR.get(a.product, a.product[:2])
        else:
            label = _GROUP_LABELS.get(rt, rt)
        if label not in groups:
            groups[label] = []
        groups[label].append((a.room_index, a.operators))

    result: list[tuple[str, list[str]]] = []
    for key in _GROUP_ORDER:
        if key not in groups:
            continue
        parts = []
        for ri, names in groups[key]:
            parts.append(f"{key}[{ri}]: {' '.join(names)}")
        result.append((key, parts))
    return result


def format_detail(
    plans: list["ShiftPlan"],
    productions: list["DailyProduction"],
    operators: list["Operator"],
    shift_hours: float,
    mood_reports: list["MoodReport"],
) -> str:
    """详细排班与产出明细 — 逐班次"""
    lines = ["## 详细排班", ""]

    for pi, plan in enumerate(plans):
        lines.append(f"### W{pi} ({plan.name})")
        lines.append("")

        groups = _group_shift_assignments(plan.assignments)
        for _label, parts in groups:
            lines.append(f"- {'  '.join(parts)}")

        # 不满员警告
        warnings = []
        for a in plan.assignments:
            if a.room_type in NON_WORK_FACILITIES:
                continue
            expected = FACILITY_SLOTS.get(a.room_type, 3)
            actual = len(a.operators)
            if actual < expected:
                label = a.room_type
                if a.room_type == "Mfg" and a.product:
                    label = _PRODUCT_ABBR.get(a.product, a.product[:2])
                warnings.append(f"- ⚠ {label}[{a.room_index}] 缺人: {actual}/{expected}")
        if warnings:
            lines.extend(warnings)

        if pi < len(productions):
            dp = productions[pi]
            total_exp = dp.total_records_per_day * _RECORD_EXP_PER_UNIT
            total_gold_lmd = dp.total_gold_produced_per_day * _GOLD_LMD_PER_UNIT

            parts = [
                f"CR {total_exp:,.0f}exp",
                f"PG {total_gold_lmd:,.0f} LMD",
                f"Trade {dp.total_lmd_per_day:,.0f} LMD",
            ]
            surplus = dp.gold_surplus
            if surplus >= 0:
                parts.append(f"赤金+{surplus:.1f}")
            else:
                parts.append(f"赤金{surplus:.1f}")
            lines.append(f"- 产出: {' | '.join(parts)} /{shift_hours:.0f}h")

        if pi < len(mood_reports):
            lines.append("")
            mr_text = mood_reports[pi].summary()
            for mr_line in mr_text.split("\n"):
                lines.append(f"> {mr_line}")

        lines.append("")

    return "\n".join(lines)


def format_report(
    pipe: "PipelineResult",
    *,
    output_path: str = "",
    brief: bool = False,
) -> str:
    """统一排班报告

    Args:
        pipe: 管道执行结果
        output_path: JSON 输出路径（显示在报告头部）
        brief: 简洁模式，跳过详细排班与产出明细

    Returns:
        格式化的 Markdown 报告字符串
    """
    params = pipe.params
    plans = pipe.solve_result.plans
    productions = pipe.productions
    operators = pipe.operators
    shift_hours = params.shift_hours

    mood_reports = _compute_chained_mood_reports(plans, operators, shift_hours, params=params)

    parts = [
        format_header(pipe, output_path),
        format_params(params),
        format_swaps(plans),
        format_production_table(productions, shift_hours, mood_reports),
        format_24h_summary(productions, params.shift_count * shift_hours),
    ]

    if not brief:
        parts.append(format_detail(plans, productions, operators, shift_hours, mood_reports))

    return "\n".join(parts) + "\n"


def save_report_md(
    pipe: "PipelineResult",
    output_path: str = "",
    brief: bool = False,
    output_dir: Path | None = None,
) -> Path:
    """将排班报告写入 output/*.md 文件

    Args:
        pipe: 管道执行结果
        output_path: JSON 输出路径（显示在报告头部）
        brief: 简洁模式，跳过详细排班与产出明细
        output_dir: 输出目录，默认项目根目录下的 output/

    Returns:
        写入的 .md 文件路径
    """
    if output_dir is None:
        output_dir = _OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    params = pipe.params
    strategy = _strategy_name(pipe)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{strategy}_{params.shift_count}x{params.shift_hours:.0f}h_{timestamp}.md"
    filepath = output_dir / filename

    report_text = format_report(pipe, output_path=output_path, brief=brief)
    filepath.write_text(report_text, encoding="utf-8")
    return filepath

