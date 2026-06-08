"""A层·制造站联动体系

含：干员配对、阵营计数、技能计数/别名、自动化、低语、
归零变体、机械精通、爬升效率、仓库容量→效率、配合意识等。
"""

from steward_core.models import LinearSegment, Operator, LayoutConfig
from .types import FacilityLinkEntry, FactionEntry, ExtraFactionEntry, ZeroingVariantEntry
from .helpers import _OP_PLATFORM_NAMES
from .ramping import operator_estimated_efficiency

# ─── A·干员配对 ─────────────────────────────────────────────────

_A_PAIR_TABLE: dict[tuple[str, str, str], float] = {
    ("阿兰娜", "温米", "PureGold"): 15.0,
    ("Miss.Christine", "酒神", "CombatRecord"): 30.0,
    ("怒潮凛冬", "乌萨斯学生自治团", "CombatRecord"): 10.0,
}


def synergy_pair(
    operators: list[Operator],
    room_type: str,
    product: str,
    T: float,
    room_tokens: dict[str, float] | None = None,
) -> list[LinearSegment]:
    """识别同房间干员配对组合，输出聚合常数段

    room_tokens 已接收但当前不使用——配对检查本质是 set membership，
    不涉及可币化的遍历开消。
    """
    if room_type != "Mfg":
        return []

    names = {op.name for op in operators}
    segments = []

    for (holder_name, target_name, p_type), bonus in _A_PAIR_TABLE.items():
        if product != p_type:
            continue
        if holder_name in names and target_name in names:
            segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))

    return segments


# ─── 仓库容量→效率 ─────────────────────────────────────────────────

def synergy_capacity_to_eff(
    operators: list[Operator],
    room_type: str,
    product: str,
    T: float,
) -> list[LinearSegment]:
    """房间内仓库容量转化为效率加成

    红云回收利用(每格+2%) / 泡泡大就是好！(≤16格 1%/格, >16格 3%/格)。
    大就是好！与回收利用互斥，优先生效。
    """
    if room_type != "Mfg":
        return []

    names = {op.name for op in operators}
    has_paopao = "泡泡" in names
    has_hongyun = "红云" in names
    if not has_paopao and not has_hongyun:
        return []

    total_cap = sum(sk.capacity_bonus for op in operators for sk in op.active_skills_for("Mfg"))

    if has_paopao:
        eff = min(total_cap, 16) * 1.0 + max(0, total_cap - 16) * 3.0
    else:
        eff = total_cap * 2.0

    return [LinearSegment(a=eff, b=0.0, t_start=0.0, dt=T)] if eff > 0 else []


# ─── 配合意识（效率放大器） ──────────────────────────────────────

def synergy_efficiency_amplifier(
    operators: list[Operator],
    room_type: str,
    product: str,
    T: float,
) -> list[LinearSegment]:
    """槐琥配合意识：其他干员每5%效率额外提供5%，上限40%

    计算房间内除槐琥外干员的效率总和后取整。
    """
    if room_type != "Mfg":
        return []

    names = {op.name for op in operators}
    if "槐琥" not in names:
        return []

    others_eff = sum(
        operator_estimated_efficiency(op, room_type, product)
        for op in operators if op.name != "槐琥"
    )
    bonus = (int(others_eff) // 5) * 5
    bonus = min(bonus, 40.0)

    return [LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T)] if bonus > 0 else []


# ─── 归零变体 ─────────────────────────────────────────────────────

_ZEROING_VARIANT_TABLE: dict[str, tuple[float, int, bool]] = {
    "manu_prod_spd&manu[000]": (0.0, 0, True),   # 科学改造: 归零他人，每干员+5容量
    "manu_prod_spd&manu[100]": (10.0, 0, True),   # 流程优化: 归零他人，每干员+10%效率
}


def synergy_zeroing_variant(
    operators: list[Operator],
    room_type: str,
    product: str,
    T: float,
) -> tuple[list[LinearSegment], set[str]]:
    """归零变体：类似 A5 自动化但补偿机制不同

    Returns:
        (效率加成段列表, 需归零的干员名集合)
    """
    if room_type != "Mfg":
        return [], set()

    best_eff = 0.0
    has_zeroing = False

    for op in operators:
        for sk in op.skills:
            if sk.room_type != "Mfg":
                continue
            if sk.buff_id in _ZEROING_VARIANT_TABLE:
                has_zeroing = True
                peff, _, _ = _ZEROING_VARIANT_TABLE[sk.buff_id]
                if peff > best_eff:
                    best_eff = peff

    if not has_zeroing:
        return [], set()

    head_count = len(operators)
    bonus = best_eff * head_count
    segments = [LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T)] if bonus > 0 else []

    zero_names = set()
    for op in operators:
        has_holder = any(
            sk.buff_id in _ZEROING_VARIANT_TABLE for sk in op.skills if sk.room_type == "Mfg"
        )
        if not has_holder:
            zero_names.add(op.name)

    return segments, zero_names


# ─── 机械精通（作业平台） ──────────────────────────────────────────

_TOKEN_PROD_TABLE: dict[str, float] = {
    "manu_token_prod_spd[000]": 5.0,
    "manu_token_prod_spd[010]": 10.0,
}


def synergy_token_prod(
    operators: list[Operator],
    room_type: str,
    product: str,
    power_platforms: dict[str, bool] | None = None,
    T: float = 12.0,
) -> list[LinearSegment]:
    """阿兰娜机械精通：作业平台进驻发电站时提供贵金属加成

    power_platforms: {名称: 是否在发电站}
    """
    if room_type != "Mfg":
        return []
    if product != "PureGold":
        return []
    if power_platforms is None:
        power_platforms = {}

    platform_count = sum(1 for name in _OP_PLATFORM_NAMES if power_platforms.get(name))

    for op in operators:
        for sk in op.skills:
            if sk.room_type != "Mfg":
                continue
            if sk.buff_id in _TOKEN_PROD_TABLE:
                bonus = platform_count * _TOKEN_PROD_TABLE[sk.buff_id]
                if bonus > 0:
                    return [LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T)]

    return []


# ─── A·技能计数 ─────────────────────────────────────────────

_A_SKILL_COUNT_TABLE: dict[str, str] = {
    "水月": "标准化",
    "多萝西": "莱茵科技",
    "苍苔": "金属工艺",
}
_A_SKILL_COUNT_BONUS = 5.0  # 每个该类技能 +5%


def skill_class(buff_name: str) -> str | None:
    """从 buff 名称提取技能类别，供 solver 制造站干员分类和 A3 体系使用"""
    for cls_name in ("标准化", "莱茵科技", "金属工艺", "红松骑士团"):
        if cls_name in buff_name:
            return cls_name
    return None


def synergy_skill_count(
    operators: list[Operator],
    room_type: str,
    alias: dict[str, list[str]] | None = None,
    T: float = 12.0,
    room_tokens: dict[str, float] | None = None,
) -> list[LinearSegment]:
    """统计同房间内技能类型数量，为持有者提供效率加成

    room_tokens 非 None 时从 TokenSource 预计算值读取计数，跳过 operator 遍历。
    """
    if room_type != "Mfg":
        return []

    if room_tokens is not None:
        # TokenSource 快速路径：从预计算字典中读取技能类计数
        segments = []
        for op in operators:
            target_cls = _A_SKILL_COUNT_TABLE.get(op.name)
            if target_cls is None:
                continue
            # 映射 A_SKILL_COUNT 类别 → TokenSource token 名
            cls_token_map = {
                "标准化": "standardization_count",
                "莱茵科技": "rhine_tech_count",
                "金属工艺": "metal_craft_count",
            }
            token_name = cls_token_map.get(target_cls)
            if token_name is None:
                continue
            count = int(room_tokens.get(token_name, 0))
            if count > 0:
                bonus = count * _A_SKILL_COUNT_BONUS
                segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))
        return segments

    if alias is None:
        alias = {}

    op_classes: dict[str, set[str]] = {}
    for op in operators:
        classes: set[str] = set()
        for sk in op.skills:
            if sk.room_type != "Mfg":
                continue
            sc = skill_class(sk.buff_name)
            if sc:
                classes.add(sc)
                for aliased in alias.get(sc, []):
                    classes.add(aliased)
        op_classes[op.name] = classes

    segments = []

    for op in operators:
        if op.name not in _A_SKILL_COUNT_TABLE:
            continue
        target_cls = _A_SKILL_COUNT_TABLE[op.name]

        count = 0
        for other in operators:
            if target_cls in op_classes.get(other.name, set()):
                count += 1

        if count > 0:
            bonus = count * _A_SKILL_COUNT_BONUS
            segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))

    return segments


# ─── A·技能别名 ─────────────────────────────────────────────

def synergy_skill_alias(
    operators: list[Operator],
) -> dict[str, list[str]]:
    """返回技能类型别名映射

    海沫(意识兼容): 莱茵科技 → 标准化, 红松骑士团 → 标准化
    """
    names = {op.name for op in operators}
    if "海沫" not in names:
        return {}
    return {
        "莱茵科技": ["标准化"],
        "红松骑士团": ["标准化"],
    }


# ─── A·自动化 ───────────────────────────────────────────────────

_POWER_BUFF_BONUS: dict[str, float] = {
    "manu_prod_spd&power[000]": 5.0,
    "manu_prod_spd&power[010]": 10.0,
    "manu_prod_spd&power[020]": 15.0,
}

_A_AUTOMATION_FALLBACK: dict[str, float] = {
    "森蚺": 5.0,
    "掠风": 5.0,
    "异客": 5.0,
    "温蒂": 15.0,
}


def _automation_bonus(op: Operator) -> float:
    """获取干员的自动化加成（优先从技能 buff_id 检测，回退到名称查找）"""
    best = 0.0
    for sk in op.skills:
        if sk.buff_id in _POWER_BUFF_BONUS:
            b = _POWER_BUFF_BONUS[sk.buff_id]
            if b > best:
                best = b
    if best <= 0:
        best = _A_AUTOMATION_FALLBACK.get(op.name, 0.0)
    return best


def synergy_automation(
    operators: list[Operator],
    room_type: str,
    power_count: int,
    T: float,
) -> tuple[list[LinearSegment], set[str]]:
    """若房间有自动化干员，返回 (自动化产出段, 需归零的干员名集合)

    自动化干员的加成直接叠加（森蚺+温蒂共存时两者均生效）。
    检测方式：从干员技能中扫描 manu_prod_spd&power[*] buff_id，回退到名称查找。
    """
    if room_type != "Mfg":
        return [], set()

    total_bonus = 0.0
    auto_op_names = set()
    for op in operators:
        bonus = _automation_bonus(op)
        if bonus <= 0:
            continue
        auto_op_names.add(op.name)
        total_bonus += power_count * bonus

    if not auto_op_names:
        return [], set()

    segments = [LinearSegment(a=total_bonus, b=0.0, t_start=0.0, dt=T)]

    zero_set = {op.name for op in operators if op.name not in auto_op_names}
    return segments, zero_set


# ─── A·低语（巫恋·归零反馈）───────────────────────────────

def synergy_whisper(
    operators: list[Operator],
    room_type: str,
    T: float,
) -> tuple[list[LinearSegment], set[str]]:
    """巫恋低语 (trade_ord_vodfox): 归零其他干员效率，自身每人+45%

    Returns:
        (效率加成段, 被归零的干员名集合)
    """
    if room_type != "Trade":
        return [], set()

    whisper_ops = []
    for op in operators:
        for sk in op.skills:
            if sk.buff_id.startswith("trade_ord_vodfox"):
                whisper_ops.append(op)
                break

    if not whisper_ops:
        return [], set()

    whisper_names = {op.name for op in whisper_ops}
    zero_set = {op.name for op in operators if op.name not in whisper_names}
    total_bonus = sum(len(operators) - 1 for _ in whisper_ops) * 45.0

    segments = [LinearSegment(a=total_bonus, b=0.0, t_start=0.0, dt=T)]
    return segments, zero_set


# ─── A·阵营计数（同房） ─────────────────────────────────────────

_A_ROOM_FACTION_TABLE: dict[str, FactionEntry] = {
    "历阵锐枪芬": FactionEntry("team_id", "reserve1", 10.0, None, "Mfg"),
    "摩根": FactionEntry("group_id", "glasgow", 20.0, "Money", "Trade"),
    "新约能天使": FactionEntry("nation_id", "laterano", 15.0, "Money", "Trade"),
}

_A_ROOM_FACTION_EXTRA: dict[str, ExtraFactionEntry] = {
    "摩根": ExtraFactionEntry("推进之王", 35.0, "Money", "Trade"),
}


def synergy_faction_room(
    operators: list[Operator],
    room_type: str,
    product: str,
    T: float,
    room_tokens: dict[str, float] | None = None,
) -> list[LinearSegment]:
    """统计同房间内特定阵营/队伍干员数量，为持有者提供效率加成

    A2 体系：持有者根据同房间内匹配阵营的干员数量获得加成。
    room_tokens 非 None 时从 TokenSource 预计算值读取计数。
    """
    names = {op.name for op in operators}
    segments = []

    if room_tokens is not None:
        # TokenSource 快速路径
        # FactionEntry field/value → TokenSource token 映射
        _FACTION_TOKEN_MAP = {
            ("team_id", "reserve1"): "reserve1_mfg",
            ("group_id", "glasgow"): "glasgow_trade",
            ("nation_id", "laterano"): "laterano_trade",
        }
        for holder_name, e in _A_ROOM_FACTION_TABLE.items():
            if holder_name not in names:
                continue
            if e.target_room is not None and room_type != e.target_room:
                continue
            if e.target_product is not None and product != e.target_product:
                continue
            token_name = _FACTION_TOKEN_MAP.get((e.field, e.value))
            count = int(room_tokens.get(token_name, 0)) if token_name else 0
            bonus = count * e.bonus_per
            if bonus > 0:
                segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))
    else:
        for holder_name, e in _A_ROOM_FACTION_TABLE.items():
            if holder_name not in names:
                continue
            if e.target_room is not None and room_type != e.target_room:
                continue
            if e.target_product is not None and product != e.target_product:
                continue
            count = sum(1 for op in operators if getattr(op, e.field, None) == e.value)
            bonus = count * e.bonus_per
            if bonus > 0:
                segments.append(LinearSegment(a=bonus, b=0.0, t_start=0.0, dt=T))

    for holder_name, e in _A_ROOM_FACTION_EXTRA.items():
        if holder_name not in names:
            continue
        if e.target_room is not None and room_type != e.target_room:
            continue
        if e.target_product is not None and product != e.target_product:
            continue
        if e.extra_name in names:
            segments.append(LinearSegment(a=e.extra_bonus, b=0.0, t_start=0.0, dt=T))

    return segments


def get_synergy_enablers(
    all_operators: list[Operator],
    room_type: str,
    product: str | None = None,
) -> list[Operator]:
    """从 _A_ROOM_FACTION_TABLE 反查联动使能者

    返回无目标设施技能、但属于 A2 阵营计数范围、能提升同房持有者效率的干员。
    特例：推进之王（无 Trade 技能，但能触发摩根帮派指南针额外+35%+A2计数）。

    这些干员被 Phase 1/Phase 3a 的 has_skill_for 门禁阻挡，需单独补充入池。
    """
    enablers: list[Operator] = []
    seen: set[str] = set()

    for holder_name, e in _A_ROOM_FACTION_TABLE.items():
        if e.target_room is not None and room_type != e.target_room:
            continue
        if e.target_product is not None and product is not None and product != e.target_product:
            continue

        for op in all_operators:
            if op.name in seen:
                continue
            if getattr(op, e.field, None) != e.value:
                continue
            if room_type == "Trade":
                if op.has_skill_for("Trade", "Money"):
                    continue
                if any(s.buff_id.startswith(("trade_ord_law", "trade_ord_long",
                                              "trade_ord_closure", "trade_ord_vodfox",
                                              "trade_ord_limit_count"))
                       for s in op.skills):
                    continue
            elif room_type == "Mfg":
                if op.has_skill_for("Mfg", product):
                    continue
            seen.add(op.name)
            enablers.append(op)

    return enablers
