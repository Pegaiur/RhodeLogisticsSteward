"""统一排班报告格式化模块

将 PipelineResult 渲染为结构化控制台报告，覆盖参数摘要、各班次概览、
换班分析、产能汇总、心情验证，一站式满足多班次（如 7 天 14x12h）测试需求。
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
    from steward_core.models import ShiftPlan, Operator
    from steward_core.production import DailyProduction
    from steward_core.mood import MoodReport

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


_HEADER_WIDTH = 72
_SEP = "=" * _HEADER_WIDTH


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
        _SEP,
        f"  RhodeLogisticsSteward 排班报告",
        f"  策略: {_strategy_name(pipe)}  ·  "
        f"{params.shift_count}x{params.shift_hours:.0f}h={total_h:.0f}h ({days:.1f}天)  ·  "
        f"干员 {len(pipe.operators)} 人",
        _SEP,
    ]
    return "\n".join(lines)


def format_params(params: "SolverParams") -> str:
    """求解参数摘要"""
    total_h = params.shift_count * params.shift_hours
    days = total_h / 24.0
    inner = params.summary()
    lines = [
        "\n── 求解参数 ──",
        inner,
        f"  周期: {params.shift_count}x{params.shift_hours:.0f}h "
        f"= {total_h:.0f}h ({days:.1f}天)",
    ]
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


def format_shift_overview(
    plans: list["ShiftPlan"],
    operators: list["Operator"],
    shift_hours: float,
    params: "SolverParams | None" = None,
) -> tuple[str, list["MoodReport"]]:
    """各班次紧凑概览表 — 每班一行，含心情状态"""
    mood_reports = _compute_chained_mood_reports(plans, operators, shift_hours, params=params)

    tracked = [
        ("Control", 0, "Ctl"),
        ("Trade", 0, "Tr0"),
        ("Trade", 1, "Tr1"),
        ("Mfg", 0, "Mf0"),
        ("Mfg", 1, "Mf1"),
        ("Mfg", 2, "Mf2"),
        ("Mfg", 3, "Mf3"),
    ]

    header_cols = ["班次"] + [abbr for _, _, abbr in tracked] + ["心情"]
    lines = [
        "\n── 各班次概览 ──",
        "  " + "  ".join(f"{h:<5}" for h in header_cols),
        "  " + "-" * (6 + 6 * len(header_cols)),
    ]

    for pi, plan in enumerate(plans):
        mr = mood_reports[pi]
        col_values = [f"W{pi:<2}"]
        for rt, ri, _ in tracked:
            found = ""
            for a in plan.assignments:
                if a.room_type == rt and a.room_index == ri:
                    p = a.product or ""
                    abbr = _PRODUCT_ABBR.get(p, p[:2]) if p else ""
                    product_tag = f"({abbr})" if abbr else ""
                    found = f"{len(a.operators)}人{product_tag}"
                    break
            col_values.append(found)
        if mr.red_face_count == 0:
            col_values.append("OK")
        else:
            col_values.append(f"!{mr.red_face_count}")
        lines.append("  " + "  ".join(f"{v:<5}" for v in col_values))

    lines.append("")
    return "\n".join(lines), mood_reports


def _plan_names(plan: "ShiftPlan") -> set[str]:
    names: set[str] = set()
    for a in plan.assignments:
        if a.operators:
            names.update(a.operators)
    return names


def _bar(v: float, ref: float, w: int = 10) -> str:
    n = round(v / max(ref, 1) * w)
    return "#" * n + "-" * (w - n)


def format_overlap_matrix(plans: list["ShiftPlan"]) -> str:
    """重叠矩阵 — NxN 显示每两班间共有干员数"""
    n = len(plans)
    lines = [
        "\n── 换班分析 ──",
        "",
        f"  重叠矩阵  (x,y) = Wx 与 Wy 共有干员数",
    ]
    header = "   W    | " + " ".join(f"W{w:<2}" for w in range(n)) + " | 变化"
    lines.append(header)
    lines.append("  " + "-" * (9 + 5 * n))
    for wi in range(n):
        ni = _plan_names(plans[wi])
        row = f"  W{wi:<2}   | "
        for wj in range(n):
            nj = _plan_names(plans[wj])
            row += f"{len(ni & nj):<4}"
        if wi == 0:
            row += " | --"
        else:
            prev = _plan_names(plans[wi - 1])
            diff = len(ni) - len(ni & prev)
            row += f" | 换{diff}人"
        lines.append(row)
    return "\n".join(lines)


def format_facility_swaps(plans: list["ShiftPlan"]) -> str:
    """设施换班统计"""
    tracked = [
        ("Control", 0), ("Trade", 0), ("Trade", 1),
        ("Mfg", 0), ("Mfg", 1), ("Mfg", 2), ("Mfg", 3),
    ]
    lines = [
        "",
        "  设施换班统计:",
    ]
    shifts_n = max(len(plans) - 1, 1)
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
        b = _bar(swaps, 7, 7)
        if swaps >= 7:
            b = "#" * 7
        lines.append(f"  {ft}[{ri}]: {swaps}/{shifts_n} 换班 ({rate:.0f}%)  [{b}]")

    overlaps = []
    for wi in range(1, len(plans)):
        ni = _plan_names(plans[wi])
        nj = _plan_names(plans[wi - 1])
        overlaps.append(len(ni & nj))
    if overlaps:
        avg_o = sum(overlaps) / len(overlaps)
        lines.append(f"\n  相邻重叠: {avg_o:.1f} 人  "
                     f"(范围 {min(overlaps)}-{max(overlaps)})")
        lines.append(f"  平均换人: {len(_plan_names(plans[0])) - avg_o:.1f} 人/班")
    return "\n".join(lines)


def format_production_table(
    productions: list["DailyProduction"],
    shift_hours: float,
    mood_reports: list["MoodReport"] | None = None,
) -> str:
    """各班次产能明细表"""
    lines = [
        "\n── 产能明细 ──",
        "",
        f"  {'班次':<5}{'经验/' + str(int(shift_hours)) + 'h':>10}"
        f"{'LMD/' + str(int(shift_hours)) + 'h':>10}"
        f"{'赤金盈余':>10}  {'vsW0经验':>10}{'vsW0LMD':>10}  {'心情':>6}",
        f"  {'-' * 68}",
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
            f"  W{pi:<4}{exp:>10,.0f}{lmd:>10,.0f}"
            f"{dp.gold_surplus:>+10.1f}{de:>+10,.0f}{dl:>+10,.0f}  "
            f"{mood_str:>6}"
        )

    return "\n".join(lines)


def format_24h_summary(productions: list["DailyProduction"], total_hours: float) -> str:
    """24h 折算产能汇总"""
    scale = 24.0 / total_hours if total_hours > 0 else 0.0
    sum_exp = sum(p.total_records_per_day for p in productions) * _RECORD_EXP_PER_UNIT * scale
    sum_gold = sum(p.total_gold_produced_per_day for p in productions) * _GOLD_LMD_PER_UNIT * scale
    sum_lmd = sum(p.total_lmd_per_day for p in productions) * scale
    sum_eff_lmd = sum(p.effective_lmd_per_day for p in productions) * scale
    sum_gold_consumed = (
        sum(p.total_gold_consumed_per_day for p in productions) * _GOLD_LMD_PER_UNIT * scale
    )
    surplus_gold = (
        sum(p.total_gold_produced_per_day for p in productions) * scale
        - sum_gold_consumed / _GOLD_LMD_PER_UNIT
    )
    surplus_lmd = surplus_gold * _GOLD_LMD_PER_UNIT

    lines = [
        "\n── 24h 折算产能 (周期日均) ──",
        f"  作战记录经验: {sum_exp:>12,.0f} /天",
        f"  赤金制造等值: {sum_gold:>12,.0f} LMD /天",
    ]
    labeled = f"  龙门币收入:   {sum_eff_lmd:>12,.0f} /天"
    if sum_lmd != sum_eff_lmd:
        labeled += f"  (理论 {sum_lmd:,.0f}，赤金不足缩减)"
    lines.append(labeled)
    if surplus_gold >= 0:
        lines.append(f"  赤金盈余:     {surplus_lmd:>12,.0f} LMD等值 /天")
    else:
        lines.append(f"  赤金缺口:     {abs(surplus_lmd):>12,.0f} LMD等值 /天")
    return "\n".join(lines)


def format_detail(
    plans: list["ShiftPlan"],
    productions: list["DailyProduction"],
    operators: list["Operator"],
    shift_hours: float,
    mood_reports: list["MoodReport"],
) -> str:
    """详细排班与产出明细 — 逐班次展开"""
    lines = ["\n── 详细排班与产出 ──"]

    for pi, plan in enumerate(plans):
        lines.append(f"\n  ── 班次 {pi + 1}: {plan.name} ──")
        for a in plan.assignments:
            tag = " [autofill]" if a.autofill else ""
            product_str = f" ({a.product})" if a.product else ""
            lines.append(f"    {a.room_type}[{a.room_index}]{product_str}: "
                         f"{a.operators}{tag}")

        if pi < len(productions):
            dp = productions[pi]
            lines.append("")
            lines.append(f"  ── 作战记录（经验）──")
            for room in dp.record_rooms:
                drone = f" (含无人机+{room.drone_boost_pct:.0%})" if room.drone_boost_pct > 0 else ""
                head_base = 100 + room.head_count
                skill_pct = (room.productivity - 1.0) * 100
                exp_value = room.output_per_day * _RECORD_EXP_PER_UNIT
                lines.append(
                    f"    Mfg[{room.room_index}]: {room.operators} -> "
                    f"{exp_value:,.0f} 经验/{shift_hours:.0f}h "
                    f"(基础{head_base}%+{skill_pct:.0f}%){drone}"
                )
            total_exp = dp.total_records_per_day * _RECORD_EXP_PER_UNIT
            lines.append(f"    合计: {total_exp:,.0f} 经验/{shift_hours:.0f}h")

            lines.append("")
            lines.append(f"  ── 赤金制造 ──")
            for room in dp.gold_rooms:
                drone = f" (含无人机+{room.drone_boost_pct:.0%})" if room.drone_boost_pct > 0 else ""
                head_base = 100 + room.head_count
                skill_pct = (room.productivity - 1.0) * 100
                lmd_value = room.output_per_day * _GOLD_LMD_PER_UNIT
                lines.append(
                    f"    Mfg[{room.room_index}]: {room.operators} -> "
                    f"{lmd_value:,.0f} LMD等值/{shift_hours:.0f}h "
                    f"(基础{head_base}%+{skill_pct:.0f}%){drone}"
                )
            total_gold_lmd = dp.total_gold_produced_per_day * _GOLD_LMD_PER_UNIT
            lines.append(f"    合计: {total_gold_lmd:,.0f} LMD等值/{shift_hours:.0f}h")
            if dp.external_gold_per_day > 0:
                ext_gold_shift = dp.external_gold_per_day * (shift_hours / 24.0)
                ext_lmd_shift = ext_gold_shift * _GOLD_LMD_PER_UNIT
                lines.append(
                    f"    外部收入: +{ext_lmd_shift:,.0f} LMD等值/{shift_hours:.0f}h "
                    f"({ext_gold_shift:.1f} 赤金)"
                )

            lines.append("")
            lines.append(f"  ── 贸易站（龙门币）──")
            for room in dp.trade_rooms:
                drone = f" (含无人机+{room.drone_boost_pct:.0%})" if room.drone_boost_pct > 0 else ""
                head_base = 100 + room.head_count
                skill_pct = (room.productivity - 1.0) * 100
                gold_use = room.output_per_day / max(dp.total_lmd_per_day, 1.0) * dp.total_gold_consumed_per_day
                lines.append(
                    f"    Trade[{room.room_index}]: {room.operators} -> "
                    f"{room.output_per_day:,.0f} LMD/{shift_hours:.0f}h "
                    f"(基础{head_base}%+{skill_pct:.0f}%){drone}  |  "
                    f"消耗赤金 {gold_use:.1f}/{shift_hours:.0f}h"
                )
            lines.append(f"    合计: {dp.total_lmd_per_day:,.0f} LMD/{shift_hours:.0f}h")
            lines.append(
                f"    赤金消耗: {dp.total_gold_consumed_per_day:.1f} 个/{shift_hours:.0f}h "
                f"(等值 {dp.total_gold_consumed_per_day * _GOLD_LMD_PER_UNIT:,.0f} LMD)"
            )
            if dp.gold_surplus >= 0:
                lines.append(f"    赤金盈余: +{dp.gold_surplus:.1f} 个/{shift_hours:.0f}h")
            else:
                lines.append(
                    f"    赤金缺口: {abs(dp.gold_surplus):.1f} 个 -> "
                    f"有效收入 {dp.effective_lmd_per_day:,.0f} LMD/{shift_hours:.0f}h"
                )

        if pi < len(mood_reports):
            lines.append("")
            lines.append(f"  ── 心情 ──")
            lines.append(mood_reports[pi].summary())

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
        output_path: JSON 输出路径（显示在报告末尾）
        brief: 简洁模式，跳过详细排班与产出明细

    Returns:
        格式化的多行报告字符串
    """
    params = pipe.params
    plans = pipe.solve_result.plans
    productions = pipe.productions
    operators = pipe.operators
    shift_hours = params.shift_hours

    overview_str, mood_reports = format_shift_overview(plans, operators, shift_hours, params=params)

    parts = [
        format_header(pipe, output_path),
        format_params(params),
        overview_str,
        format_overlap_matrix(plans),
        format_facility_swaps(plans),
        format_production_table(productions, shift_hours, mood_reports),
        format_24h_summary(productions, params.shift_count * shift_hours),
    ]

    if not brief:
        parts.append(format_detail(plans, productions, operators, shift_hours, mood_reports))

    if output_path:
        parts.append(f"\n[输出] 排班文件: {output_path}")
    parts.append("")

    return "\n".join(parts)


def save_report_md(
    pipe: "PipelineResult",
    output_path: str = "",
    brief: bool = False,
    output_dir: Path | None = None,
) -> Path:
    """将排班报告写入 output/*.md 文件

    Args:
        pipe: 管道执行结果
        output_path: JSON 输出路径（显示在报告末尾）
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

    md_content = (
        f"# 排班报告\n\n"
        f"**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"**策略**: {strategy}  ·  "
        f"{params.shift_count}x{params.shift_hours:.0f}h  ·  "
        f"干员 {len(pipe.operators)} 人\n\n"
        f"```text\n"
        f"{report_text}\n"
        f"```\n"
    )

    filepath.write_text(md_content, encoding="utf-8")
    return filepath

