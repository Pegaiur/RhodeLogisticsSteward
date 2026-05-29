"""求解器可调参数注册表

所有硬编码数值集中于此，支持外部 JSON 覆盖，使 A/B 测试和权重调参零代码改动。
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
import json


@dataclass
class SolverParams:
    """求解器全局可调参数

    字段按语义分组，每个字段有默认值保证向后兼容。
    通过 from_json() 加载覆盖文件即可 A/B 测试不同参数组合，
    无需修改任何 Python 代码。
    """

    # === 排班基础 ===
    shift_hours: float = 12.0
    """单班次时长（小时），默认 12h"""

    # === 设施布局（243 默认值） ===
    base_power_count: int = 3
    """物理发电站数"""
    control_max_slots: int = 5
    """中枢最大工位"""
    dorm_room_count: int = 4
    """宿舍房间数"""
    dorm_room_size: int = 5
    """每间宿舍工位数"""
    dorm_max_operators: int = 20
    """宿舍最大干员总数"""
    dorm_estimated_count: int = 20
    """宿舍估计人数（Phase 3a Trade 评估时宿舍尚未填充，用此估计值）"""
    facility_level: int = 3
    """设施默认等级（Lv3）"""
    dorm_level: int = 5
    """宿舍默认等级"""
    dorm_levels_sum: int = 20
    """宿舍总等级（4间 × Lv5）"""

    # === 心情/消耗 ===
    base_burn_per_hour: float = 1.0
    """基础心情消耗率（/h）"""
    base_burn_rate: float = 0.75
    """3人工位基础消耗率（中枢净恢复前）"""
    control_recovery_per_op: float = 0.05
    """中枢每名干员提供的心情恢复（/h）"""
    mood_full: float = 24.0
    """满心情值（h）"""
    mood_work_threshold: float = 0.0
    """可参与工作的最低心情值（低于此值不可用）"""
    mood_blue_face: float = 12.0
    """蓝脸阈值（效率下降的边界，不影响 e(t) 但标记状态）"""
    mood_red_face: float = 0.0
    """红脸阈值（效率归零）"""

    # === 多班次 ===
    shift_count: int = 1
    """班次数（1=单班次，2=双班次）"""
    interval_hours: float = 8.0
    """班间间隔（小时），用于恢复模拟"""
    fiammetta_enabled: bool = False
    """是否启用菲亚梅塔心情交换"""

    # === Buff 池 ===
    suich_count: int = 5
    """岁阵营默认计数（重岳烟火生成用）"""
    office_perception_base: int = 20
    """絮雨办公室感知信息基础值（243 Lv3: 2额外招募位 × 10）"""

    # === 外部收入 ===
    daily_task_lmd: float = 5000.0
    """日常任务等外部来源等效赤金收入（LMD/天，按每赤金=500LMD折算）"""

    # === 算法调优 ===
    combo_upper_bound_threshold: float = 0.95
    """穷举上界预判阈值（规则 3：总效率 ≥ best_known × threshold）"""
    control_global_sort_bias: float = 1000.0
    """中枢全局加成者排序偏置（C1 效率为 0，需大偏置强制排前）"""
    global_state_alpha: float = 0.3
    """全局状态评分权重（0=忽略全局状态, 1=完全平衡）"""

    # === 制造站穷举预筛选 ===
    rough_score_keep_top: int = 0
    """粗评分预筛选保留的组合数（0 或负数表示禁用预筛选，全量评估）"""

    # === 局部搜索 ===
    local_search_max_rounds: int = 3
    """局部搜索最大轮次"""

    @classmethod
    def baseline(cls) -> "SolverParams":
        """基线参数（默认值）"""
        return cls()

    @classmethod
    def from_json(cls, path: str | Path) -> "SolverParams":
        """从 JSON 文件加载参数覆盖

        只覆盖 JSON 中存在的字段，未提及的保留默认值。
        加载后自动校验合法性。
        示例 JSON:
        {
            "shift_hours": 24.0,
            "combo_upper_bound_threshold": 0.90
        }
        """
        with open(path, "r", encoding="utf-8") as f:
            overrides = json.load(f)
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in overrides.items() if k in valid_fields}
        result = cls(**filtered)
        errors = result.validate()
        if errors:
            raise ValueError(f"参数校验失败 ({path}):\n" + "\n".join(f"  - {e}" for e in errors))
        return result

    def to_json(self, path: str | Path) -> None:
        """将当前参数导出为 JSON 文件（用于保存实验配置）"""
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def apply_overrides(self, **kwargs) -> "SolverParams":
        """返回新实例，仅覆盖显式传入的非 None 字段（用于 CLI 参数优先级合并）"""
        updates = {k: v for k, v in kwargs.items() if v is not None}
        if not updates:
            return self
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        data.update(updates)
        result = SolverParams(**data)
        errors = result.validate()
        if errors:
            raise ValueError(f"参数覆盖后校验失败: {errors}")
        return result

    def diff(self, other: "SolverParams") -> list[str]:
        """比较两个参数集，返回差异字段列表"""
        diffs = []
        for f in fields(self):
            a = getattr(self, f.name)
            b = getattr(other, f.name)
            if a != b:
                diffs.append(f"{f.name}: {a!r} → {b!r}")
        return diffs

    def validate(self) -> list[str]:
        """校验参数合法性，返回错误信息列表"""
        errors = []
        if self.shift_hours <= 0:
            errors.append("shift_hours 必须 > 0")
        if self.control_max_slots < 1:
            errors.append("control_max_slots 必须 >= 1")
        if self.combo_upper_bound_threshold < 0 or self.combo_upper_bound_threshold > 1:
            errors.append("combo_upper_bound_threshold 必须在 [0, 1] 区间")
        if self.global_state_alpha < 0 or self.global_state_alpha > 1:
            errors.append("global_state_alpha 必须在 [0, 1] 区间")
        if self.local_search_max_rounds < 1:
            errors.append("local_search_max_rounds 必须 >= 1")
        if self.dorm_max_operators < self.dorm_room_size:
            errors.append("dorm_max_operators 应 >= dorm_room_size")
        if self.daily_task_lmd < 0:
            errors.append("daily_task_lmd 必须 >= 0")
        return errors
