"""TokenSource 统一计数层

所有计数类联动效果归一为"Token 生产→Token 消费"模型。
执行引擎通过拓扑排序保证依赖正确的计算顺序。

设计文档: docs/token-source-model.md
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from steward_core.models import Operator
    from steward_core.solver.slot.context import SlotContext

# ─── 核心类型 ──────────────────────────────────────────────────────────

ConditionMatcher = Callable[["Operator"], bool]
"""条件匹配器：给定 Operator，返回是否匹配"""


@dataclass(slots=True)
class TokenSource:
    """Token 生产描述符

    定义一条"计数→Token"规则，描述如何从干员池/布局中提取一个 token 值。
    """

    token: str
    """token 名（唯一标识）"""

    condition: str = "*"
    """匹配条件字符串（格式见 token-source-model.md §条件语法）"""

    scope: str = "room"
    """"room" | "facility" | "global" """

    aggregate: str = "count"
    """"count" | "efficiency_sum" | "max_efficiency" | "attribute_sum" | "passthrough" | "distinct" """

    aggregate_unit: float = 1.0
    """聚合除数（efficiency_sum / unit 等）"""

    depends_on: str | None = None
    """None | "layout" | "facility" | token_name"""

    target_room: str | None = None
    """depends_on 时的目标设施类型"""

    attr: str | None = None
    """depends_on="layout" 时的属性名"""

    exclude_self: bool = False
    """是否排除自身"""

    partner_facility: str | None = None
    """跨设施配对时的对方设施类型"""

    cap: float | None = None
    """token 值上限（None = 无上限）"""


# ─── 执行引擎 ──────────────────────────────────────────────────────────


def evaluate_tokens(
    sources: list[TokenSource],
    operators: list["Operator"],
    ctx: "SlotContext | None" = None,
) -> dict[str, float]:
    """对一组 TokenSource 执行拓扑排序 → 计算全部 token 值

    Args:
        sources: TokenSource 注册列表
        operators: 当前 scope 内的干员列表
        ctx: 求解器上下文（可选，用于依赖 layout/facility 的 source）

    Returns:
        {token_name: value, ...}

    Raises:
        ValueError: 循环依赖、depends_on 指向不存在的 token
    """
    # 构建 token 索引
    source_by_token: dict[str, TokenSource] = {}
    for s in sources:
        source_by_token[s.token] = s

    # 拓扑排序
    order = _topological_sort(sources, source_by_token)

    # 按序执行
    tokens: dict[str, float] = {}
    for token_name in order:
        source = source_by_token[token_name]
        value = _evaluate_single(source, operators, tokens, ctx)
        tokens[token_name] = value

    return tokens


def _topological_sort(
    sources: list[TokenSource],
    source_by_token: dict[str, TokenSource],
) -> list[str]:
    """拓扑排序 + 循环依赖检测

    Kahn 算法：入度为 0 的节点入队，依次出队。
    最终出队数 < 节点数 → 存在环。
    """
    # 构建邻接表 + 入度
    adj: dict[str, list[str]] = defaultdict(list)
    indeg: dict[str, int] = defaultdict(int)

    for s in sources:
        indeg.setdefault(s.token, 0)
        dep = s.depends_on
        # depends_on 指向 layout/facility 不需要 token 存在 —— 跳过
        if dep and dep not in ("layout", "facility"):
            if dep not in source_by_token:
                raise ValueError(
                    f"TokenSource '{s.token}' 依赖的 token '{dep}' 不存在"
                )
            adj[dep].append(s.token)
            indeg[s.token] += 1

    # Kahn
    queue: deque[str] = deque(t for t, d in indeg.items() if d == 0)
    order: list[str] = []

    while queue:
        u = queue.popleft()
        order.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)

    if len(order) != len(source_by_token):
        # 找出剩余未出队的节点 → 循环依赖
        remaining = [t for t in source_by_token if t not in order]
        raise ValueError(f"TokenSource 存在循环依赖: {remaining}")

    return order


def _evaluate_single(
    source: TokenSource,
    operators: list["Operator"],
    tokens: dict[str, float],
    ctx: "SlotContext | None",
) -> float:
    """计算单个 TokenSource 的 token 值"""
    aggregate = source.aggregate

    if aggregate == "passthrough":
        # 透传上游 token 值
        dep = source.depends_on
        if dep is None:
            return 0.0
        return tokens.get(dep, 0.0)

    # ── 计数类 aggregate ──
    if aggregate == "count":
        return _evaluate_count(source, operators, tokens, ctx)

    # ── 效率/属性类 aggregate ──
    if aggregate == "efficiency_sum":
        return _evaluate_efficiency_sum(source, operators, tokens, ctx)
    if aggregate == "max_efficiency":
        return _evaluate_max_efficiency(source, operators, tokens, ctx)
    if aggregate == "attribute_sum":
        return _evaluate_attribute_sum(source, operators, tokens, ctx)
    if aggregate == "distinct":
        return _evaluate_distinct(source, operators, tokens, ctx)

    # 其他 aggregate 暂未实现
    raise NotImplementedError(f"aggregate '{aggregate}' 尚未实现")


def _evaluate_count(
    source: TokenSource,
    operators: list["Operator"],
    tokens: dict[str, float],
    ctx: "SlotContext | None",
) -> float:
    """count aggregate：统计符合条件的干员数"""
    condition = source.condition

    # count_ge 特殊处理：统计后做阈值判定，返回 0 或 1
    if condition.startswith("count_ge"):
        if not condition.startswith("count_ge:"):
            raise ValueError(
                f"count_ge 期望格式 count_ge:group_id=N，收到 '{condition}'"
            )
        _, group_id, _, n_str = _parse_count_ge(condition)
        try:
            threshold = int(n_str)
        except ValueError:
            raise ValueError(
                f"count_ge 阈值必须是整数，收到 'count_ge:{group_id}={n_str}'"
            ) from None
        count = sum(1 for op in operators if op.has_group(group_id))
        result = 1.0 if count >= threshold else 0.0
        if source.cap is not None:
            result = min(result, source.cap)
        return result

    # pair 特殊处理：双方都在 → 1，否则 → 0
    if condition.startswith("pair="):
        _, value = _parse_condition(condition)
        if ":" not in value:
            raise ValueError(
                f"pair 期望格式 char_id_A:char_id_B，收到 'pair={value}'"
            )
        a, b = value.split(":", 1)
        char_ids = {op.char_id for op in operators}
        result = 1.0 if (a in char_ids and b in char_ids) else 0.0
        if source.cap is not None:
            result = min(result, source.cap)
        return result

    matcher = _build_matcher(source.condition)
    count = sum(1 for op in operators if matcher(op))
    if source.cap is not None:
        count = min(count, source.cap)
    return float(count)


def _evaluate_efficiency_sum(
    source: TokenSource,
    operators: list["Operator"],
    _tokens: dict[str, float] | None = None,
    _ctx: "SlotContext | None" = None,
) -> float:
    """efficiency_sum aggregate：匹配干员的目标房间效率值之和 ÷ unit"""
    room = source.target_room or "Mfg"
    matcher = _build_matcher(source.condition)
    total = 0.0
    for op in operators:
        if not matcher(op):
            continue
        active = op.active_skills_for(room)
        if active:
            # 使用 raw.get("all", 0) 而非 efficient.get("all")，
            # 后者在无 "all" 键时返回哨兵值 -999.0（仅产品专属技能场景）
            total += max(s.efficient.raw.get("all", 0.0) for s in active)
    unit = source.aggregate_unit if source.aggregate_unit != 0 else 1.0
    result = total / unit
    if source.cap is not None:
        result = min(result, source.cap)
    return result


def _evaluate_max_efficiency(
    source: TokenSource,
    operators: list["Operator"],
    _tokens: dict[str, float] | None = None,
    _ctx: "SlotContext | None" = None,
) -> float:
    """max_efficiency aggregate：匹配干员中的最高效率值"""
    room = source.target_room or "Mfg"
    matcher = _build_matcher(source.condition)
    best = float("-inf")
    for op in operators:
        if not matcher(op):
            continue
        active = op.active_skills_for(room)
        if active:
            eff = max(s.efficient.raw.get("all", 0.0) for s in active)
            if eff > best:
                best = eff
    if best == float("-inf"):
        best = 0.0
    if source.cap is not None:
        best = min(best, source.cap)
    return best


def _evaluate_attribute_sum(
    source: TokenSource,
    operators: list["Operator"],
    _tokens: dict[str, float] | None = None,
    _ctx: "SlotContext | None" = None,
) -> float:
    """attribute_sum aggregate：匹配干员的指定属性值之和"""
    attr = source.attr
    if attr is None:
        return 0.0
    room = source.target_room
    matcher = _build_matcher(source.condition)
    total = 0.0
    for op in operators:
        if not matcher(op):
            continue
        if room and attr == "capacity_bonus":
            active = op.active_skills_for(room)
            if active:
                total += sum(s.capacity_bonus for s in active)
        else:
            total += float(getattr(op, attr, 0))
    if source.cap is not None:
        total = min(total, source.cap)
    return total


def _evaluate_distinct(
    source: TokenSource,
    operators: list["Operator"],
    _tokens: dict[str, float] | None = None,
    _ctx: "SlotContext | None" = None,
) -> float:
    """distinct aggregate：匹配干员的指定属性去重计数"""
    attr = source.attr
    if attr is None:
        return 0.0
    room = source.target_room
    matcher = _build_matcher(source.condition)
    seen: set[str] = set()
    for op in operators:
        if not matcher(op):
            continue
        if room and attr == "skill_icon":
            active = op.active_skills_for(room)
            for s in active:
                seen.add(s.skill_icon)
        else:
            val = getattr(op, attr, None)
            if val is not None:
                seen.add(str(val))
    result = float(len(seen))
    if source.cap is not None:
        result = min(result, source.cap)
    return result


# ─── 条件匹配器构建 ────────────────────────────────────────────────────

# 派生布尔函数注册表（条件 key → 判定函数）
_FN_CONDITIONS: dict[str, ConditionMatcher] = {}

# ── 初始注册 is_knight + is_abyssal_hunter ──
from steward_core.synergy.helpers import _is_knight
_FN_CONDITIONS["is_knight"] = lambda op: _is_knight(op)
_FN_CONDITIONS["is_abyssal_hunter"] = lambda op: op.has_group("abyssal")


def _parse_condition(condition: str) -> tuple[str, str] | tuple[str]:
    """解析 condition 字符串

    Returns:
        ("field", "value")   — key=value 格式
        ("fn_name",)          — 无值格式（如 "is_knight"）
    """
    if "=" not in condition:
        return (condition,)

    key, _, value = condition.partition("=")
    return (key, value)


def _build_matcher(condition: str) -> ConditionMatcher:
    """解析 condition 字符串 → 条件匹配器

    支持的语法（Phase A2 覆盖前 7 种，skill_class 留 Phase B）：

    | 格式 | 匹配方式 |
    |------|---------|
    | `*` | 无条件通过 |
    | `group_id=v` | op.has_group(v) |
    | `nation_id=v` | op.has_nation(v) |
    | `char_id=v` | op.char_id == v |
    | `is_knight` | _FN_CONDITIONS["is_knight"](op) |
    | `pair=A:B` | 双方 char_id 均在 operators 内 |
    | `count_ge:g=N` | ≥N 个 has_group(g) → 1.0，否则 0.0 |
    | `skill_class=v` | 暂未实现（Phase B） |
    """
    if condition == "*":
        return lambda _op: True

    parsed = _parse_condition(condition)

    if len(parsed) == 1:
        # 无值格式
        fn_name = parsed[0]
        if fn_name in _FN_CONDITIONS:
            return _FN_CONDITIONS[fn_name]
        raise ValueError(f"未知的条件函数 '{fn_name}'")

    key, value = parsed

    if key == "group_id":
        return lambda op, v=value: _match_group_id(op, v)
    elif key == "nation_id":
        return lambda op, v=value: _match_nation_id(op, v)
    elif key == "team_id":
        return lambda op, v=value: _match_team_id(op, v)
    elif key == "char_id":
        return lambda op, v=value: op.char_id == v
    elif key == "pair":
        # pair 由 _evaluate_count 直接处理（需要 scope 级知识：双方均在才返回 1）
        raise NotImplementedError("pair 条件由 _evaluate_count 直接处理，不应通过 _build_matcher 调用")
    elif key == "count_ge":
        # count_ge 由 _evaluate_count 直接处理（需要全量计数 + 阈值判定）
        raise NotImplementedError("count_ge 条件由 _evaluate_count 直接处理，不应通过 _build_matcher 调用")
    elif key == "skill_class":
        return lambda op, v=value: _match_skill_class(op, v)

    # count_ge 作为 key 前缀处理（"count_ge:karlan"）
    if key.startswith("count_ge:"):
        raise NotImplementedError("count_ge 条件由 _evaluate_count 直接处理，不应通过 _build_matcher 调用")

    raise ValueError(f"未知的条件 key '{key}'")


def _match_group_id(op, group_id: str) -> bool:
    """匹配 group_id（兼容 has_group 方法）"""
    return op.has_group(group_id)


def _match_nation_id(op, nation_id: str) -> bool:
    """匹配 nation_id（兼容 has_nation 方法）"""
    return op.has_nation(nation_id)


def _match_team_id(op, team_id: str) -> bool:
    """匹配 team_id（兼容 has_team 方法）"""
    return op.has_team(team_id)


def _match_skill_class(op, class_name: str) -> bool:
    """匹配 skill_class：干员任一技能的 buff_name 包含指定类别名"""
    for sk in op.skills:
        if class_name in sk.buff_name:
            return True
    return False


def _parse_count_ge(condition: str) -> tuple[str, str, str, str]:
    """解析 count_ge 条件字符串

    'count_ge:karlan=3' → ('count_ge', 'karlan', '=', '3')
    """
    # condition 格式: "count_ge:group_id=N"
    after_prefix = condition[len("count_ge:"):]
    if "=" not in after_prefix:
        raise ValueError(
            f"count_ge 期望格式 count_ge:group_id=N，收到 '{condition}'"
        )
    group_id, n_str = after_prefix.split("=", 1)
    return ("count_ge", group_id, "=", n_str)


# ─── Phase A TokenSource 注册列表 ────────────────────────────────────────

# 以下 11 条覆盖 A 层同房阵营 3 + C 层 per-operator 条件加成 8，
# 用于 Phase A 原型验证：与旧函数 synergy_faction_room / _eval_per_op 输出对齐。

PHASE_A_SOURCES: list[TokenSource] = [
    # ── A 层同房阵营 ──
    TokenSource(token="reserve1_mfg", condition="team_id=reserve1"),
    TokenSource(token="glasgow_trade", condition="group_id=glasgow"),
    TokenSource(token="laterano_trade", condition="nation_id=laterano"),

    # ── C 层 per-operator ──
    TokenSource(token="pinus_cr", condition="group_id=pinus"),
    TokenSource(token="pinus_pg_penalty", condition="group_id=pinus"),
    TokenSource(token="knight_mfg", condition="is_knight"),
    TokenSource(token="blacksteel_mfg", condition="group_id=blacksteel"),
    TokenSource(token="siracusa_trade", condition="nation_id=siracusa"),
    TokenSource(token="karlan3_trade", condition="count_ge:karlan=3"),
    TokenSource(token="glasgow_trade_bonus", condition="group_id=glasgow"),
    TokenSource(token="karlan_trade_penalty", condition="group_id=karlan"),
]


# ─── Phase B TokenSource 注册列表 ────────────────────────────────────────

# A 层技能标签计数（A3）
# 水月/多萝西/苍苔 对同房内持有相同 skill_class 的干员计数 +5%/人
PHASE_B_SKILL_CLASS: list[TokenSource] = [
    TokenSource(token="standardization_count", condition="skill_class=标准化"),
    TokenSource(token="rhine_tech_count", condition="skill_class=莱茵科技"),
    TokenSource(token="metal_craft_count", condition="skill_class=金属工艺"),
]

# B 层全局阵营计数（B6）
# 缪尔赛思/杏仁/娜斯提 每名符合条件的全基建干员提供效率加成
PHASE_B_GLOBAL_FACTION: list[TokenSource] = [
    TokenSource(token="rhine_global", condition="group_id=rhine", scope="global", cap=5),
    TokenSource(token="blacksteel_global", condition="group_id=blacksteel", scope="global", cap=3),
    TokenSource(token="rhine_global_mfg", condition="group_id=rhine", scope="global", cap=5),
]

# B 层跨房间配对（B7）
# 烈夏↔古米 / 深巡↔乌尔比安 / 贝洛内↔伺夜 — 跨设施配对
PHASE_B_CROSS_PAIRS: list[TokenSource] = [
    TokenSource(token="liexia_gumi", condition="pair=烈夏:古米"),
    TokenSource(token="shenxun_wuerbian", condition="pair=深巡:乌尔比安"),
    TokenSource(token="beiluo_siye", condition="pair=贝洛内:伺夜"),
]

# C 层集群狩猎
# 歌蕾蒂娅 每 Mfg 站内深海猎人提供 +10%/人
PHASE_B_CLUSTER: list[TokenSource] = [
    TokenSource(token="abyssal_mfg", condition="is_abyssal_hunter", scope="facility"),
]

# 全量 B 层注册（不含需要 depends_on="layout"/"facility" 的条目）
PHASE_B_SOURCES: list[TokenSource] = (
    PHASE_B_SKILL_CLASS
    + PHASE_B_GLOBAL_FACTION
    + PHASE_B_CROSS_PAIRS
    + PHASE_B_CLUSTER
)

