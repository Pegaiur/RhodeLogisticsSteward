# Strategy 策略层重构：实施笔记

> 对标 `docs/strategy-refactor-plan.md`，记录实施过程中的细节决策、偏离与实际产出。

---

## Step 0: Strategy ABC + PartialSolution + BaselineStrategy

### 实施时间

2026-05-28

### 决策记录

- **`ShiftPlan` 从 `__init__.py` 移除**：审查 agent 发现重构后 `ShiftPlan` 在 `solve_mvp()` 中不再使用（构造逻辑迁至 `BaselineStrategy`），已清理死 import。
+- **`pipeline` 参数从 `solve_mvp()` 签名中移除**：分支审查 agent 发现 `pipeline` 参数静默失效（`BaselineStrategy.execute()` 内部硬编码 `Pipeline.default()`），对应的 `Pipeline` re-export 一并移除。需要自定义 Phase 顺序时通过 Strategy 子类实现。

### 偏离 plan 的情况

（无）

---

## Step 1: Pipeline 状态适配层

### 实施时间

2026-05-28

### 决策记录

（无——纯语法糖，~15 行新增，不改任何 Phase 逻辑）

### 偏离 plan 的情况

（无）

---

## Step 2: GlobalContext 去重 — **有意跳过**

### 实施时间

2026-05-28

### 决策记录

**决定不提取共享辅助函数**。理由：

- `from_estimated()` 和 `from_plan()` 虽然结构平行，但 `compute_buff_pool()` 的布尔参数来源根本不同——前者来自函数参数（预评估阶段的推测值），后者来自 Plan 的逐房间扫描
- `effective_power` 的 Lancet-2 检查逻辑也不同：`from_estimated` 检查全量干员池，`from_plan` 检查特定房间
- 提取共享 helper 需要传入分支参数（如 `lancet_check_mode`），增加间接层而不减少实质重复
- 两条路径服务根本不同的场景（搜索时的预评估 vs 产出时的精确评估），保持独立更符合单一职责

### 偏离 plan 的情况

Step 2（GlobalContext 去重，plan 预计约 30 行）被跳过。plan 文档 §"可顺带优化的架构脆弱点" 第 2 项标记为完成但不改动。
