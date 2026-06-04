"""制造站/贸易站干员分类"""

import warnings
from dataclasses import dataclass, field

from steward_core.models import Operator
from .helpers import _DURIN_NAMES, _ORDER_ANCHOR_PREFIXES
from .mfg_linkages import skill_class, _ZEROING_VARIANT_TABLE
from .ramping import operator_estimated_efficiency
from .buff_pool import _B_BUFF_CONSUMER_TABLE
from .facility_linkages import _A_FACILITY_LINK_TABLE


def _detect_unregistered_contributors(op_name: str, room_type: str) -> bool:
    """检测干员是否为未注册的系统贡献者

    仅在 _derived.py 过期（MFG_ANCHORS/TRADE_ANCHORS 缺失）时触发。
    静默兜底 → 显式告警，提示开发者运行 scripts/derive.py。
    """
    if op_name in _B_BUFF_CONSUMER_TABLE and _B_BUFF_CONSUMER_TABLE[op_name].target_room == room_type:
        warnings.warn(
            f"干员 {op_name} 是 {room_type} buff 消费者但未在 _derived.py 注册，请运行 python scripts/derive.py",
            stacklevel=2,
        )
        return True
    if op_name in _A_FACILITY_LINK_TABLE and _A_FACILITY_LINK_TABLE[op_name].target_room == room_type:
        warnings.warn(
            f"干员 {op_name} 是 {room_type} 设施联动者但未在 _derived.py 注册，请运行 python scripts/derive.py",
            stacklevel=2,
        )
        return True
    return False


@dataclass
class MfgClassification:
    """制造站干员分类结果"""
    pure_efficiency: list = field(default_factory=list)
    anchors: list = field(default_factory=list)
    providers: list = field(default_factory=list)


def classify_mfg_operators(
    operators: list, product: str, anchor_names: set[str],
) -> "MfgClassification":
    """将制造站干员分类为 纯效率/联动锚点/技能提供者"""
    result = MfgClassification()
    for op in operators:
        is_anchor = op.name in anchor_names

        has_skill_label = False
        has_zeroing = False
        for sk in op.skills:
            if sk.room_type != "Mfg":
                continue
            if skill_class(sk.buff_name):
                has_skill_label = True
            if sk.buff_id in _ZEROING_VARIANT_TABLE:
                has_zeroing = True

        if is_anchor:
            result.anchors.append(op)
        elif has_skill_label or has_zeroing:
            result.providers.append(op)
        elif _detect_unregistered_contributors(op.name, "Mfg"):
            result.providers.append(op)
        else:
            result.pure_efficiency.append(op)

    return result


def prune_equivalent(pure_ops: list, room_type: str, product: str | None = None, top_k: int = 3) -> list:
    """等价类合并 — 纯效率只保留 top_k 名"""
    sorted_ops = sorted(pure_ops, key=lambda op: -operator_estimated_efficiency(op, room_type, product))
    return sorted_ops[:top_k]


def build_candidate_pool(
    all_ops: list, classification: "MfgClassification",
    room_type: str | None = None,
    product: str | None = None,
) -> list:
    """锚点池筛选 — anchors + providers + top_k 纯效率

    锚点按 best_efficiency 降序排列，确保高产能锚点优先参与组合生成。
    """
    seen = {op.char_id for op in classification.anchors}
    if room_type is not None:
        anchors = sorted(classification.anchors, key=lambda op: -operator_estimated_efficiency(op, room_type, product))
    else:
        anchors = list(classification.anchors)
    pool = list(anchors)

    for op in classification.providers:
        if op.char_id not in seen:
            seen.add(op.char_id)
            pool.append(op)

    top_pure = prune_equivalent(classification.pure_efficiency, room_type or "Mfg", product, top_k=5)
    for op in top_pure:
        if op.char_id not in seen:
            seen.add(op.char_id)
            pool.append(op)

    # Trade: 裁缝类干员 (trade_ord_wt&cost) 订单质量加成——efficient=0 但真实价值高，
    # top_k=5 按效率排序会排除。纳入全部有订单质量技能的 pure_efficiency 干员。
    if room_type == "Trade" and product == "Money":
        for op in classification.pure_efficiency:
            if op.char_id in seen:
                continue
            for sk in op.skills:
                if sk.buff_id.startswith("trade_ord_wt"):
                    seen.add(op.char_id)
                    pool.append(op)
                    break

    # Mfg: 容量加成干员 (capacity_bonus > 0) —— efficient=0 但提供仓库容量/降本等非效率价值，
    # top_k=5 按效率排序会排除。纳入全部有 capacity_bonus 的 pure_efficiency 干员。
    if room_type == "Mfg":
        for op in classification.pure_efficiency:
            if op.char_id in seen:
                continue
            for sk in op.skills:
                if sk.room_type == "Mfg" and sk.capacity_bonus > 0:
                    seen.add(op.char_id)
                    pool.append(op)
                    break

    return pool


def classify_trade_operators(
    operators: list, anchor_names: set[str],
) -> "MfgClassification":
    """将 Trade 干员分类为 纯效率/联动锚点/技能提供者

    与 Mfg 同架构，复用 MfgClassification。
    锚点包含注册锚点（反馈型/配对型）+ 订单机制型（但书/龙舌兰/可露希尔）。
    裁缝 (trade_ord_wt&cost) 不视为锚点——裁缝是支撑工具人。
    """
    result = MfgClassification()

    for op in operators:
        is_registered = op.name in anchor_names
        is_order_anchor = any(
            s.room_type == "Trade" and s.buff_id.startswith(_ORDER_ANCHOR_PREFIXES)
            for s in op.skills
        )

        if is_registered or is_order_anchor:
            result.anchors.append(op)
        elif _detect_unregistered_contributors(op.name, "Trade"):
            result.providers.append(op)
        else:
            result.pure_efficiency.append(op)

    return result
