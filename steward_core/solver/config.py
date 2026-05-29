"""求解器配置开关

功能开关（SolverConfig）与可调参数（SolverParams）分离：
- SolverConfig: 策略选择 + 功能开关
- SolverParams: 数值型可调参数，支持 JSON 覆盖
"""

from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING

from .params import SolverParams

if TYPE_CHECKING:
    from .strategy import Strategy
    from steward_core.mood_flow import MoodContext


@dataclass
class SolverConfig:
    """求解器配置——功能开关 + 策略选择 + 可调参数

    所有开关默认 False，保证向后兼容。
    数值型调参请使用 SolverParams。
    策略选择通过 strategy 字段注入自定义 Strategy 实现 A/B 测试。
    """

    # 策略选择
    strategy: "Strategy | None" = None
    """求解策略——None 时 solve_mvp() 自动使用 BaselineStrategy"""

    # Step 1b: 独占支撑冲突检查 — 仅检查独占支撑（Trade/Office），共享支撑不冲突
    exclusive_support_check: bool = False

    # Step 2: 局部搜索后处理
    local_search_enabled: bool = False

    # Step 3: 全局状态评分注入
    global_state_scoring: bool = False

    # 心情上下文（多班次框架层注入，单班次为 None）
    mood_ctx: "MoodContext | None" = None
    """多班次心情上下文，通过 Config 传递到 Phase 层，避免修改 Strategy 签名"""

    # 可调参数
    params: SolverParams = field(default_factory=SolverParams)

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

    @classmethod
    def with_params(cls, params: SolverParams) -> "SolverConfig":
        """使用自定义参数的基线配置"""
        return cls(params=params)

    def diff(self, other: "SolverConfig") -> list[str]:
        """比较两个配置，返回差异字段列表

        每项格式: "field_name: self_value → other_value"
        """
        diffs = []
        for f in fields(self):
            if f.name == "params":
                param_diffs = self.params.diff(other.params)
                if param_diffs:
                    diffs.extend(f"params.{d}" for d in param_diffs)
                continue
            a = getattr(self, f.name)
            b = getattr(other, f.name)
            if a != b:
                diffs.append(f"{f.name}: {a!r} → {b!r}")
        return diffs
