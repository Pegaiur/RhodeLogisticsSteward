"""辅助判定函数与名称常量"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from steward_core.models import Operator

# ─── 名称集合 ──────────────────────────────────────────────────────────

# 骑士标签持有者（name 集合作为数据驱动判定的安全网）
_KNIGHT_NAMES: set[str] = {
    "砾", "野鬃", "白金", "鞭刃", "暴雨", "耀骑士临光",
    "瑕光", "临光", "远牙", "灰毫", "焰尾", "薇薇安娜",
}

# 怪物猎人小队干员名（中枢条件型加成判定用）
_MH_NAMES: set[str] = {"麒麟R夜刀", "炼金术士"}

# 龙门近卫局干员名（中枢条件型加成判定用）
_LUNG_MEN_GUARD_NAMES: set[str] = {"陈", "星熊", "诗怀雅", "斩业星熊"}

# 黑钢国际持有者（老友相聚）
_BLACKSTEEL_HOLDERS: set[str] = {"涤火杰西卡"}

# 作业平台（机器人）干员名
_OP_PLATFORM_NAMES: set[str] = {
    "Lancet-2", "Castle-3", "THRM-EX", "正义骑士号",
}

# 杜林族干员名（硬编码，character_identity.json 无 raceId 字段）
_DURIN_NAMES: set[str] = {"杜林", "桃金娘", "褐果", "至简"}

# ─── 组 ID 常量 ───────────────────────────────────────────────────────

_PINUS_GROUP = "pinus"
_BLACKSTEEL_GROUP = "blacksteel"
_GLASGOW_GROUP = "glasgow"

# ─── 设施常量 ─────────────────────────────────────────────────────────

_FACILITY_LEVEL = 3  # 已弃用：请使用 RoomConfig.level 代替，由 LayoutConfig 驱动
_DEFAULT_DORM_LEVELS = 20  # 4 间 Lv5 宿舍
_BASE_BURN_3 = 0.75

# ─── Trade 订单机制型锚点 buff_id 前缀 ────────────────────────────────

_ORDER_ANCHOR_PREFIXES = ("trade_ord_law", "trade_ord_long", "trade_ord_closure", "trade_ord_limit_count")

# ─── 加成包 ───────────────────────────────────────────────────────────

ROSEMARY_SUPPORT: dict[str, list[str]] = {
    "Control": ["令", "夕"],
    "Trade": ["黑键"],
    "Dormitory": ["爱丽丝", "车尔尼", "森西", "塑心"],
    "Office": ["絮雨"],
}

_B_ROSEMARY = "迷迭香"
_B_EBENHOLZ = "黑键"


def _is_glasgow(op: "Operator") -> bool:
    """判定干员是否属于格拉斯哥帮（通过 group_id）"""
    return getattr(op, "group_id", None) == "glasgow"


def _is_knight(op: "Operator") -> bool:
    """游戏内骑士 = kazimierz 势力 + 红松骑士团 + 硬编码补全"""
    return op.name in _KNIGHT_NAMES or op.nation_id == "kazimierz" or op.group_id == _PINUS_GROUP
