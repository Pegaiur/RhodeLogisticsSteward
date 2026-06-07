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

    # 其他 aggregate 暂未实现
    raise NotImplementedError(f"aggregate '{aggregate}' 尚未实现")


def _evaluate_count(
    source: TokenSource,
    operators: list["Operator"],
    tokens: dict[str, float],
    ctx: "SlotContext | None",
) -> float:
    """count aggregate：统计符合条件的干员数"""
    matcher = _build_matcher(source.condition)
    count = sum(1 for op in operators if matcher(op))
    if source.cap is not None:
        count = min(count, source.cap)
    return float(count)


# ─── 条件匹配器构建 ────────────────────────────────────────────────────


def _build_matcher(condition: str) -> ConditionMatcher:
    """解析 condition 字符串 → 条件匹配器

    Phase A1 仅实现 * 通配，后续 Phase A2 扩展 8 种语法。
    """
    if condition == "*":
        return lambda _op: True

    raise NotImplementedError(f"条件 '{condition}' 尚未实现（Phase A2 待完成）")
