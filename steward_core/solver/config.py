"""求解器配置开关

功能开关（SolverConfig）与可调参数（SolverParams）分离：
- SolverConfig: 布尔型功能开关 + 策略选择
- SolverParams: 数值型可调参数，支持 JSON 覆盖
"""

from dataclasses import dataclass, field, fields

from .params import SolverParams


@dataclass
class SolverConfig:
    """求解器配置，功能开关与策略选择

    所有开关默认 False，保证向后兼容。
    数值型调参请使用 SolverParams。
    """

    # Step 1b: 独占支撑冲突检查 — 仅检查独占支撑（Trade/Office），共享支撑不冲突
    exclusive_support_check: bool = False

    # Step 2: 局部搜索后处理
    local_search_enabled: bool = False

    # Step 3: 全局状态评分注入
    global_state_scoring: bool = False

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
