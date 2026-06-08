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

    # 第二遍：layout/facility 依赖（在常规 token 之后计算）
    # 注：layout/facility 源在第一遍按默认 aggregate="count" 被计算，第二遍用
    # _evaluate_context_dependent 覆写。第一遍结果是占位值，最终以第二遍为准。
    for s in sources:
        if s.depends_on in ("layout", "facility"):
            tokens[s.token] = _evaluate_context_dependent(s, operators, ctx)

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


def _evaluate_context_dependent(
    source: TokenSource,
    operators: list["Operator"],
    ctx: "SlotContext | None",
) -> float:
    """处理 depends_on="layout" 或 "facility" 的 TokenSource

    layout: 从 ctx.layout 查询布局属性
    facility: 从 ctx.build_all_assignments() 查询设施级干员分布
    """
    if source.depends_on == "layout":
        return _evaluate_layout(source, ctx)

    if source.depends_on == "facility":
        return _evaluate_facility(source, ctx)

    return 0.0


def _evaluate_layout(source: TokenSource, ctx: "SlotContext | None") -> float:
    """布局依赖：根据 aggregate 模式查询 ctx.layout

    支持模式：
    - count（默认）：统计 target_room 类型的房间数
    - attribute_sum + attr="level"：对 target_room 类型房间的 level 属性求和
    - distinct + attr="product"：统计 target_room 类型房间的 product 去重数
    """
    if ctx is None or ctx.layout is None:
        return 0.0

    room_type = source.target_room or ""
    matching = [r for r in ctx.layout.rooms if r.room_type == room_type]

    if source.aggregate == "attribute_sum" and source.attr:
        result = float(sum(getattr(r, source.attr, 0) for r in matching))
    elif source.aggregate == "distinct" and source.attr:
        values = {getattr(r, source.attr) for r in matching if getattr(r, source.attr) is not None}
        result = float(len(values))
    else:
        result = float(len(matching))

    if source.cap is not None:
        result = min(result, source.cap)
    return result


def _evaluate_facility(source: TokenSource, ctx: "SlotContext | None") -> float:
    """设施依赖：统计含匹配干员的设施类型数

    注：build_all_assignments() 以 facility_type 分组（如所有 Trade 站合并为 "Trade" 键），
    因此统计的是"设施类型数"而非"房间数"。此语义与 _FACILITY_GROUP_TABLE 的
    count_facilities_with_group 一致，但与游戏"各房间独立计数"机制有差异。
    """
    if ctx is None:
        return 0.0

    assignments = ctx.build_all_assignments(window_idx=0)
    matcher = _build_matcher(source.condition)

    count = 0
    for facility_type, ops in assignments.items():
        if any(matcher(op) for op in ops):
            count += 1

    result = float(count)
    if source.cap is not None:
        result = min(result, source.cap)
    return result


def _evaluate_count(
    source: TokenSource,
    operators: list["Operator"],
    tokens: dict[str, float],
    ctx: "SlotContext | None",
) -> float:
    """count aggregate：统计符合条件的干员数

    当前 scope 仅区分 pair/count_ge 特殊处理，尚未实现 room/facility/global 的三级过滤。
    所有干员均参与计数（等同于 scope="global" 语义）。
    scope="room" 限制将在求解器接入（Phase C）时通过调用方传入子集干员列表实现。
    """
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
    if source.exclude_self:
        count = max(0, count - 1)
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
    """匹配 skill_class：干员任一技能的 buff_name 包含指定类别名

    使用子串匹配（如 "标准化" 可匹配 "标准化·α"/"标准化·β"）。
    假设 buff_name 中类别名字面唯一（当前游戏数据成立）。
    若未来出现歧义（如 "莱茵" 同时匹配 "莱茵科技" 和 "莱茵生命"），
    需改为精确前缀匹配。
    """
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


# ─── 求解器接入：Token 预计算 ──────────────────────────────────────────


def compute_room_tokens(
    operators: list["Operator"],
    ctx: "SlotContext | None" = None,
) -> dict[str, float]:
    """单次调用计算全部已注册 TokenSource 的 token 值（含 layout/facility 依赖）

    evaluate_room() 的接入点：在 room 级评估开始时调用一次，后续所有计数函数
    直接读取 token 值，避免重复遍历 operators。

    Args:
        operators: 房间内干员列表
        ctx: 求解器上下文（含 layout 用于 depends_on="layout" 查询）

    Returns:
        {token_name: value} 字典
    """
    # 惰性导入：打破 token_source ↔ token_maps 循环引用
    from steward_core.synergy.token_maps import (
        PHASE_A_SOURCES, PHASE_B_SOURCES,
        PHASE_B_A_PAIRS, PHASE_B_TRADE_PAIRS, PHASE_B_ALIAS,
        PHASE_B_EFF_AMPLIFIER, PHASE_B_CONDITIONAL_EFF,
        PHASE_B_FACILITY_ATTRS, PHASE_B_FACTORY_COUNT,
        PHASE_B_FACILITY_GROUP, PHASE_B_TRADE_SHARE,
        PHASE_B_CONTROL_TRADE_LIMIT,
    )

    all_sources = (
        PHASE_A_SOURCES + PHASE_B_SOURCES
        + PHASE_B_A_PAIRS + PHASE_B_TRADE_PAIRS + PHASE_B_ALIAS
        + PHASE_B_EFF_AMPLIFIER + PHASE_B_CONDITIONAL_EFF
        + PHASE_B_FACILITY_ATTRS + PHASE_B_FACTORY_COUNT
        + PHASE_B_FACILITY_GROUP + PHASE_B_TRADE_SHARE
        + PHASE_B_CONTROL_TRADE_LIMIT
    )
    # 注：ctx=None 时 depends_on 源返回 0.0（layout/facility 依赖在无 ctx 时静默降级）
    return evaluate_tokens(all_sources, operators, ctx)

