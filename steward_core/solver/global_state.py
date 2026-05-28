"""全局求解状态 — 包级稀缺度

维护支撑包的可用性余量，为评分注入"选择此 combo 后还剩什么"的信息，
使贪心排序不再完全无视资源竞争。
"""

from dataclasses import dataclass


@dataclass
class GlobalState:
    """全局求解状态快照

    跟踪每个支撑包的剩余可用次数。
    迷迭香包受黑键独占限制（一次只能满足一个房间），
    骑士包仅受中枢容量限制（薇薇安娜+焰尾共享）。
    """

    bundle_availability: dict[str, int]

    @classmethod
    def for_layout_243(cls) -> "GlobalState":
        """243 布局下的初始包可用性

        迷迭香包: 1 次（黑键独占 Trade 工位）
        骑士包: 2 次（中枢 5 人中可同时容纳薇薇安娜+焰尾，留余量 2）
        """
        return cls(bundle_availability={"迷迭香包": 1, "骑士包": 2})

    def can_allocate(self, bundles: list[str]) -> bool:
        """检查所有包是否还有余量"""
        return all(self.bundle_availability.get(b, 0) > 0 for b in bundles)

    def allocate(self, bundles: list[str]) -> None:
        """消耗包余量（每次分配 -1）"""
        for b in bundles:
            if b in self.bundle_availability:
                self.bundle_availability[b] -= 1

    def scarcity_penalty(self, bundles: list[str], alpha: float = 0.3) -> float:
        """计算稀缺度惩罚值

        惩罚 = α × Σ per_bundle_penalty
        - 余量 ≤ 1: 0.15（重罚——最后一个）
        - 余量 ≤ 3: 0.05（轻罚——紧张）
        - 余量 > 3: 0（充裕）

        alpha 控制全局惩罚强度，0 = 关闭全局状态效果。
        采用加法偏置而非乘法打折，避免保守性陷阱。
        """
        if alpha <= 0 or not bundles:
            return 0.0

        total = 0.0
        for b in bundles:
            remaining = self.bundle_availability.get(b, 1)
            if remaining <= 1:
                total += 0.15
            elif remaining <= 3:
                total += 0.05
        return alpha * total
