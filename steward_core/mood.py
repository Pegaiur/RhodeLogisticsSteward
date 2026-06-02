"""心情消耗计算模块 (Phase A: 工作消耗 + 控制中枢减免)

基于 PRTS Wiki 公式:
  https://prts.wiki/w/罗德岛基建/制造站  (心情消耗/时)
  https://prts.wiki/w/罗德岛基建/控制中枢 (全局减免)

阶段范围: 工作侧心情消耗计算，覆盖任意班次数。
         宿舍恢复暂不纳入 (MAA 宿舍技能 efficient 全为 0，Phase B 另行处理)。
"""

from dataclasses import dataclass, field

from steward_core.models import Operator, ShiftPlan

# 心情上限
_MOOD_MAX = 24.0
# 红脸阈值 (效率为 0)
_RED_FACE_THRESHOLD = 0.0


@dataclass
class RoomMood:
    """单个工作设施房间的心情消耗分析"""
    room_type: str
    room_index: int
    operators: list[str] = field(default_factory=list)
    base_burn: float = 0.0
    net_burn: float = 0.0
    remaining_after_shift: float = 24.0
    is_red_face: bool = False

    def status(self) -> str:
        if self.is_red_face:
            return "🔴 红脸"
        return "🟢 正常"


@dataclass
class MoodReport:
    """心情分析报告"""
    shift_hours: float
    shift_name: str
    control_operators: list[str] = field(default_factory=list)
    control_bonus: float = 0.0
    rooms: list[RoomMood] = field(default_factory=list)

    red_face_count: int = 0

    def all_pass(self) -> bool:
        """是否所有工作干员均未红脸"""
        return self.red_face_count == 0

    def summary(self) -> str:
        lines = [
            f"控制中枢: {self.control_operators} → 全局减免 {self.control_bonus:.2f}/时",
            f"班次时长: {self.shift_hours:.0f}h",
        ]
        for room in self.rooms:
            ops_str = ", ".join(room.operators)
            lines.append(
                f"  {room.room_type}[{room.room_index}]: "
                f"{ops_str}"
                f" → 净消耗={room.net_burn:.2f}/时, "
                f"剩余={room.remaining_after_shift:.1f} ({room.status()})"
            )
        lines.append(
            f"结果: 红脸{self.red_face_count}间"
        )
        if self.all_pass():
            lines.append("✅ 全部通过，无需轮换")
        else:
            lines.append("❌ 存在红脸，需要缩短班次或增加轮换")
        return "\n".join(lines)


def _operator_lookup(operators: list[Operator]) -> dict[str, Operator]:
    return {op.name: op for op in operators}


def _is_work_facility(room_type: str) -> bool:
    """工作设施：干员在此处于工作状态，会消耗心情"""
    return room_type in ("Mfg", "Trade", "Power", "Reception", "Office")


def calculate(
    plan: ShiftPlan,
    operators: list[Operator],
    shift_hours: float = 24.0,
    *,
    base_burn_per_hour: float = 1.0,
    control_recovery_per_op: float = 0.05,
) -> MoodReport:
    """计算班次心情消耗

    Args:
        plan: 排班计划
        operators: 全量干员池
        shift_hours: 班次时长 (默认 24h)
    """
    op_lookup = _operator_lookup(operators)

    # 1. 收集控制中枢干员，计算全局减免
    control_ops: list[str] = []
    control_bonus = 0.0

    for assignment in plan.assignments:
        if assignment.room_type == "Control":
            control_ops.extend(assignment.operators)

    # 基础: 每个控制中枢干员 +0.05/时
    control_bonus += len(control_ops) * control_recovery_per_op

    # 额外: 排除 bskill_ctrl_cost (基础值) 后，其他 Control 技能中 0<val<1 的值为额外加成
    for name in control_ops:
        op = op_lookup.get(name)
        if op is None:
            continue
        for skill in op.skills:
            if skill.room_type != "Control":
                continue
            if skill.skill_icon == "bskill_ctrl_cost":
                continue  # 已在基础值中计入
            val = skill.efficient.max_value()
            if 0.0 < val < 1.0:
                control_bonus += val

    # 2. 逐工作设施计算心情消耗
    report = MoodReport(
        shift_hours=shift_hours,
        shift_name=plan.name,
        control_operators=control_ops,
        control_bonus=control_bonus,
    )

    for assignment in plan.assignments:
        if not _is_work_facility(assignment.room_type):
            continue

        op_count = len(assignment.operators)
        if op_count == 0:
            continue

        # 基础消耗: 1.0 - 0.05 × (人数-1)，1人无减免
        base_burn = base_burn_per_hour - control_recovery_per_op * max(0, op_count - 1)

        # 净消耗 = 基础消耗 - 控制中枢减免 (最低为 0)
        net_burn = max(0.0, base_burn - control_bonus)

        remaining = _MOOD_MAX - net_burn * shift_hours

        room_mood = RoomMood(
            room_type=assignment.room_type,
            room_index=assignment.room_index,
            operators=assignment.operators,
            base_burn=base_burn,
            net_burn=net_burn,
            remaining_after_shift=remaining,
            is_red_face=remaining <= _RED_FACE_THRESHOLD,
        )

        report.rooms.append(room_mood)
        if room_mood.is_red_face:
            report.red_face_count += 1

    return report
