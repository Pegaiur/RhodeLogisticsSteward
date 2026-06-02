"""制造站/贸易站干员分类"""

from dataclasses import dataclass, field

from steward_core.models import Operator
from .helpers import _DURIN_NAMES, _ORDER_ANCHOR_PREFIXES
from .mfg_linkages import skill_class, _ZEROING_VARIANT_TABLE, operator_expected_12h_efficiency
from .buff_pool import _B_BUFF_CONSUMER_TABLE
from .facility_linkages import _A_FACILITY_LINK_TABLE


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
        # 以下两步已被 MFG_ANCHORS 覆盖（derive.py 扫描同名表自动注册），
        # 保留作为防御性兜底：如果 _derived.py 过期未更新，此检查仍能防剪枝。
        elif op.name in _B_BUFF_CONSUMER_TABLE and _B_BUFF_CONSUMER_TABLE[op.name].target_room == "Mfg":
            result.providers.append(op)
        elif op.name in _A_FACILITY_LINK_TABLE and _A_FACILITY_LINK_TABLE[op.name].target_room == "Mfg":
            result.providers.append(op)
        else:
            result.pure_efficiency.append(op)

    return result


def prune_equivalent(pure_ops: list, top_k: int = 3) -> list:
    """等价类合并 — 纯效率只保留 top_k 名"""
    sorted_ops = sorted(pure_ops, key=lambda op: -operator_expected_12h_efficiency(op, "Mfg"))
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
        anchors = sorted(classification.anchors, key=lambda op: -operator_expected_12h_efficiency(op, room_type, product))
    else:
        anchors = list(classification.anchors)
    pool = list(anchors)

    for op in classification.providers:
        if op.char_id not in seen:
            seen.add(op.char_id)
            pool.append(op)

    top_pure = prune_equivalent(classification.pure_efficiency, top_k=5)
    for op in top_pure:
        if op.char_id not in seen:
            seen.add(op.char_id)
            pool.append(op)

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
        # 以下两步已被 TRADE_ANCHORS 覆盖，保留作为防御性兜底。
        elif op.name in _B_BUFF_CONSUMER_TABLE and _B_BUFF_CONSUMER_TABLE[op.name].target_room == "Trade":
            result.providers.append(op)
        elif op.name in _A_FACILITY_LINK_TABLE and _A_FACILITY_LINK_TABLE[op.name].target_room == "Trade":
            result.providers.append(op)
        else:
            result.pure_efficiency.append(op)

    return result
