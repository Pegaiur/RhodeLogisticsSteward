# Strategy 策略层重构：实施笔记

> 对标 `docs/strategy-refactor-plan.md`，记录实施过程中的细节决策、偏离与实际产出。

---

## Step 0: Strategy ABC + PartialSolution + BaselineStrategy

### 实施时间

2026-05-28

### 决策记录

- **`ShiftPlan` 从 `__init__.py` 移除**：审查 agent 发现重构后 `ShiftPlan` 在 `solve_mvp()` 中不再使用（构造逻辑迁至 `BaselineStrategy`），已清理死 import。
- **`pipeline` 参数从 `solve_mvp()` 签名中移除**：分支审查 agent 发现 `pipeline` 参数静默失效，对应的 `Pipeline` re-export 一并移除。自定义 Phase 顺序通过 Strategy 子类实现。

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

---

## Step 4: K-Beam Strategy 实现

### 实施时间

2026-05-28

### 决策记录

- **迭代排斥法选择**：采用"排斥完整 combo 集合 + 逐项跳过"而非 DFS 回溯。原因——排斥集合方式简单、可预测、每轮只需一次贪心扫描。K=5 时 5 次扫描仍可接受。
- **CR 做 K 条、PG 做 1 条**：`_phase1_kbeam` 中 CR 的 top-K 分配是分叉点，PG 在每条 CR 路径上只取 1 条——防止 K² 爆炸（K 条 CR × K 条 PG = 25 条路径）。
- **测试池 prune_equivalent 冲突**：`classify_mfg_operators` → `prune_equivalent(top_k=3)` 将测试干员全标记为纯效率 → 仅保留 3 人 → C(3,3)=1 个组合。集成测试调整为验证"至少 1 间 Mfg"而非"4 间满员"。全量数据下锚点充足，不受影响。
- **择优选 `_production_score` 而非 `evaluate_room`**：因为 Trade 订单机制（孑/但书/可露希尔）将效率积分非线性转换为 LMD 产出，`production.calculate()` 才能准确比较不同路径的真实产出。
- **Phase 函数直接调用**：KBeamStrategy 不通过 Pipeline，直接调用 `_phase2_control`、`_phase3_trade` 等——树状数据流无法用线性 Pipeline 表达。
