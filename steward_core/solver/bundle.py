"""支撑包数据结构

将 compute_optimal_support() 中隐式的包结构显式化为 SupportBundle，
区分独占支撑（Trade/Office 工位有限）和共享支撑（Dormitory/Control 全局服务）。
"""

from dataclasses import dataclass, field
from typing import NamedTuple


@dataclass(frozen=True)
class SupportBundle:
    """一个支撑包：同一锚点体系需要的全部支撑干员

    触发条件为组合级（如"迷迭香在 combo 中"即激活迷迭香包）。
    独占支撑每次只能服务一个房间（如黑键→Trade 仅 1 个工位），
    共享支撑可服务所有房间（如塑心→Dormitory 的 B5 buff 全局生效）。
    """

    name: str
    trigger_condition: str  # 触发条件描述（用于调试）
    exclusive: dict[str, list[str]] = field(default_factory=dict)
    shared: dict[str, list[str]] = field(default_factory=dict)


BUNDLES: dict[str, SupportBundle] = {
    "迷迭香包": SupportBundle(
        name="迷迭香包",
        trigger_condition="迷迭香在 combo 中",
        exclusive={
            "Trade": ["黑键"],
            "Office": ["絮雨"],
        },
        shared={
            "Control": ["令", "夕"],
            "Dormitory": ["爱丽丝", "车尔尼", "森西", "塑心"],
        },
    ),
    "骑士包": SupportBundle(
        name="骑士包",
        trigger_condition="任意骑士在 combo 中",
        exclusive={},
        shared={
            "Control": ["薇薇安娜", "焰尾"],
        },
    ),
}


class SupportResult(NamedTuple):
    """compute_optimal_support 的返回值

    support_map: 向后兼容的原始 dict，与旧接口一致
    bundles: 激活的包名列表，供全局状态和稀缺度计算使用
    """

    support_map: dict[str, list[str]]
    bundles: list[str]
