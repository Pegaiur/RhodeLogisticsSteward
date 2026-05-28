"""求解器配置开关

所有可选功能通过 SolverConfig 统一控制，支持预设配置与差异比较。
"""

from dataclasses import dataclass, fields


@dataclass
class SolverConfig:
    """求解器配置，每个字段控制一个可选功能的开关

    所有开关默认 False，保证向后兼容。
    """

    # Step 1b: 独占支撑冲突检查 — 仅检查独占支撑（Trade/Office），共享支撑不冲突
    exclusive_support_check: bool = False

    # Step 2: 局部搜索后处理
    local_search_enabled: bool = False
    local_search_max_rounds: int = 3

    # Step 3: 全局状态评分注入
    global_state_scoring: bool = False
    global_state_alpha: float = 0.3

    @classmethod
    def baseline(cls) -> "SolverConfig":
        """基线配置：所有功能关闭，等价于当前生产行为"""
        return cls()

    @classmethod
    def all_on(cls) -> "SolverConfig":
        """全开配置：启用所有可选功能"""
        return cls(
            exclusive_support_check=True,
            local_search_enabled=True,
            global_state_scoring=True,
        )

    def diff(self, other: "SolverConfig") -> list[str]:
        """比较两个配置，返回差异字段列表
        
        每项格式: "field_name: self_value → other_value"
        """
        diffs = []
        for f in fields(self):
            a = getattr(self, f.name)
            b = getattr(other, f.name)
            if a != b:
                diffs.append(f"{f.name}: {a!r} → {b!r}")
        return diffs
