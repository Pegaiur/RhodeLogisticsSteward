"""A层·设施数量联动"""

from steward_core.models import LinearSegment, Operator, LayoutConfig
from .types import FacilityLinkEntry
from .helpers import _DEFAULT_DORM_LEVELS


_A_FACILITY_LINK_TABLE: dict[str, FacilityLinkEntry] = {
    "清流": FacilityLinkEntry("trade_count", 20.0, "Mfg", "PureGold", None),
    "引星棘刺": FacilityLinkEntry("trade_count", 3.0, "Mfg", "PureGold", None),
    "娜仁图亚": FacilityLinkEntry("dorm_levels", 1.0, "Mfg", "PureGold", None),
    "空弦": FacilityLinkEntry("dorm_levels", 2.0, "Trade", "Money", None),
    "伺夜": FacilityLinkEntry("meeting_level", 5.0, "Trade", "Money", 40.0),
    "渡桥": FacilityLinkEntry("meeting_level", 5.0, "Trade", "Money", 30.0),
    "石英": FacilityLinkEntry("mfg_recipe_types", 2.0, "Trade", "Money", None),
    "维伊": FacilityLinkEntry("train_level", 10.0, "Mfg", None, 30.0),
}


def synergy_facility_count(
    operators: list[Operator],
    room_type: str,
    product: str,
    layout: LayoutConfig,
    dorm_levels: int = _DEFAULT_DORM_LEVELS,
    T: float = 12.0,
) -> list[LinearSegment]:
    """根据全基建设施数量/等级为当前房间提供联动加成

    Returns:
        联动加成段列表，每个非零加成对应一个常数段
    """
    names = {op.name for op in operators}
    segments = []

    trade_count = sum(1 for r in layout.rooms if r.room_type == "Trade")
    meeting_level = sum(
        r.level for r in layout.rooms if r.room_type == "Reception"
    )
    mfg_products = {
        r.product for r in layout.rooms
        if r.room_type == "Mfg" and r.product is not None
    }
    mfg_recipe_types = len(mfg_products)
    train_level = sum(
        r.level for r in layout.rooms if r.room_type == "Training"
    )

    for name in names:
        if name not in _A_FACILITY_LINK_TABLE:
            continue
        entry = _A_FACILITY_LINK_TABLE[name]
        count_key = entry.count_source
        bonus_per = entry.bonus_per_unit
        target_room = entry.target_room
        target_product = entry.target_product
        cap = entry.cap

        if room_type != target_room:
            continue
        if target_product is not None and product != target_product:
            continue

        if count_key == "trade_count":
            count = trade_count
        elif count_key == "dorm_levels":
            count = dorm_levels
        elif count_key == "meeting_level":
            count = meeting_level
        elif count_key == "mfg_recipe_types":
            count = mfg_recipe_types
        elif count_key == "train_level":
            count = train_level
        else:
            continue

        bonus = count * bonus_per
        if cap is not None:
            bonus = min(bonus, cap)

        if bonus > 0:
            segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))

    return segments


def _has_power_count_modifier(op: Operator) -> bool:
    """检查干员是否持有发电站数量修改器（如承曦格雷伊"晨曦"）"""
    for sk in op.skills:
        if sk.buff_id == "power_count[000]":
            return True
    return False


def compute_effective_power_count(
    power_operators: list[Operator],
    physical_count: int,
    control_operators: list[Operator] | None = None,
) -> int:
    """计算有效发电站数量（含设施数量修改器）

    承曦格雷伊"晨曦"（power_count[000]）：发电站额外+1。
    森蚺"我寻思能行"（control_pow_bot[000]）：Lancet-2在发电站时额外+2。
    """
    count = physical_count
    for op in power_operators:
        if _has_power_count_modifier(op):
            count += 1
    if control_operators:
        power_names = {op.name for op in power_operators}
        if "Lancet-2" in power_names:
            for op in control_operators:
                if any(s.buff_id == "control_pow_bot[000]" for s in op.skills):
                    count += 2
                    break
    return count
