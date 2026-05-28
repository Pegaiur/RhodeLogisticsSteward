# 求解器优化计划：消除局部最优陷阱

> **版本**: 2026-05-28 · 计划阶段，尚未实施

## 问题诊断

当前四阶段贪心求解器存在"独立评估 + 贪心分配 + 硬锁定"导致的局部最优陷阱，详见 [solver 架构分析](#)。

五个维度：
1. **同产品双房间独立评分**：CR 两间房的 combo 在 `assigned_ids=∅` 下独立评分，分配时单次遍历不回溯
2. **支撑全部视为独占**：Dormitory/Control 支撑是跨房间共享的，但分配层扁平冲突检查将其视为独占
3. **跨产品单向可见**：CR 先跑锁资源，PG 只能接盘，无互相调优
4. **跨 Phase 不可逆**：Mfg → Control → Trade 顺序固化，无交叉补贴机制
5. **评分无全局感知**：每个 combo 评分时看不到"选了它之后还剩什么"

## 改进架构：三件套互补

```
全局状态注入 (L1-L4)    瓶颈枚举             局部搜索
     │                      │                    │
管理"多对多"资源竞争   管理"少对少"关键决策   修正残差 + 非线性
     │                      │                    │
     └──────────────────────┼────────────────────┘
                            │
                    全部通过 SolverConfig 开关控制
                    每个模块独立可丢弃
```

## 实施步骤

### Step 0: 灵活性基础设施

**文件**: `steward_core/solver/config.py` (新增)

引入 `SolverConfig` 数据类作为所有功能的总开关：

```python
@dataclass
class SolverConfig:
    exclusive_support_check: bool = False
    local_search_enabled: bool = False
    local_search_max_rounds: int = 3
    global_state_scoring: bool = False
    global_state_alpha: float = 0.3

    @classmethod
    def baseline(cls): ...
    @classmethod
    def all_on(cls): ...
    def diff(self, other) -> list[str]: ...
```

改造 `solve_mvp(operators, config=None)` 接受 `config` 参数，默认全部关闭（行为不变）。

**验证**: 所有现有测试不加任何修改直接通过。

**Pivot**: 无。此步骤纯骨架，不改变行为。

---

### Step 1a: 支撑包数据结构

**文件**: `steward_core/solver/bundle.py` (新增)

把 `compute_optimal_support()` 中隐式的包结构显式化：

| 包名 | 独占支撑 | 共享支撑 | 触发条件 |
|------|---------|---------|---------|
| 迷迭香包 | Trade: [黑键], Office: [絮雨] | Control: [令,夕], Dormitory: [爱丽丝,车尔尼,森西,塑心] | 迷迭香 in combo |
| 骑士包 | (无) | Control: [薇薇安娜,焰尾] | any_knight in combo |

**验证**: `compute_optimal_support()` 返回新的 `SupportResult(support_map, bundles)`，分配行为不变（旧代码解包 `.support_map`）。

**Pivot**: 若后续游戏更新新增锚点体系 → `BUNDLES` 注册表加一行。

---

### Step 1b: 独占冲突检查

**文件**: `steward_core/solver/greed.py` (修改)

- `_greedy_allocate_with_support` 根据 `SolverConfig.exclusive_support_check` 选择冲突策略
- 旧逻辑：`all_support_names` 全部检查 → 扁平冲突（当前行为）
- 新逻辑：只检查 Trade + Office 独占支撑，Dormitory + Control 共享支撑不产生冲突
- 保持 Control 容量限制（5 人上限）

**验证**: 开关关 → 旧行为；开关开 → 两个骑士 combo 不再冲突。

**Pivot**: 若新逻辑产出反而低于旧逻辑（说明共享支撑确实存在容量竞争）→ 关开关，细化包模型。

---

### Step 2: 局部搜索

**文件**: `steward_core/solver/refine.py` (新增)

纯后处理模块，在 `solve_mvp()` 末尾插入，不动 solver 内部：

- **算子 1**: 单房间替换 → 用次优候选替换当前分配
- **算子 2**: 干员交换 → 两房间交换兼有双设施的干员
- 接受策略：`first-improvement`（当前最佳）
- 最大轮数：`SolverConfig.local_search_max_rounds`

**验证**: 开关关 → 跳过；开关开 → 手工构造可改进的 SolveResult 验证搜索能发现。

**Pivot**: 若太慢 → 减轮数；若无效 → 关开关或优化算子。

---

### Step 3: 全局状态包级稀缺度

**文件**: `steward_core/solver/global_state.py` (新增)

在 Phase 1 评分中注入"选了它之后，相容候选还剩多少"：

- 以包为单位计算稀缺度（迷迭香包: 1 次，骑士包: 2 次）
- `adjusted_score = base_score - alpha × scarcity_penalty`
- 分配时同步更新 GlobalState

**验证**: 开关关 → 旧评分；开关开 → 迷迭香 combo 在排序中劣后于同等积分的无包 combo。

**Pivot**: 若保守性陷阱 → 调 alpha 或换 penalty 公式。

---

## 开发原则

| 原则 | 措施 |
|------|------|
| 每步可独立丢弃 | 各自独立模块 + 独立开关 |
| 任何时候可退回旧行为 | `SolverConfig()` 全部默认 False |
| A/B 对比 | `solve_mvp(ops, baseline)` vs `solve_mvp(ops, all_on)` |
| 现有测试不透改 | 开关关 = 旧行为 |
| TDD 纪律 | 红灯（写测试→失败）→ 绿灯（实现→通过）→ 审查→提交 |

## 执行状态

| Step | 状态 | 提交 |
|------|------|------|
| Step 0: SolverConfig | ✅ 完成 | `infra: 引入 SolverConfig 开关机制 (Step 0)` |
| Step 1a: 支撑包 | ✅ 完成 | `feat(bundle): 支撑包数据结构 (SupportBundle + SupportResult)` |
| Step 1b: 独占冲突检查 | 待开始 | — |
| Step 2: 局部搜索 | 待开始 | — |
| Step 3: 全局状态 | 待开始 | — |
