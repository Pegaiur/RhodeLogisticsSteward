# Trade C(n,3) 穷举重构方案

> 日期: 2026-05-27
> 目标: Trade 从单干员贪心 + A7 硬编码偏置 → C(n,3) 穷举，与 Mfg 同架构

---

## 动机

1. **A7 硬编码维护成本高**：`get_trade_order_equivalent_efficiency` 中 16 个硬编码值需人工校准
2. **贪心排序不准确**：2 人评估丢失第三席信息（如巫恋低语只算 1 室友）
3. **Strategy 不对称**：Mfg 已用穷举，Trade 仍用贪心，维护模式不统一

## 算法变更

| 维度 | 当前 | 新方案 |
|------|------|------|
| Trade 排序 | 单干员贪心 + A7 硬编码偏置 | C(n,3) 穷举 + `evaluate_room` + `_get_trade_order_multiplier` |
| 候选池 | 全员过滤（best_efficiency + A7 偏置） | classify → anchors + providers + top-N pure |
| 房间分配 | `rank_by_dominance` 逐个填 | `_greedy_allocate` 贪心取无冲突 2 间 |

---

## 执行步骤

### Step 1: synergy.py — `classify_trade_operators`

新增 Trade 干员分类函数，模仿 Mfg 的 `classify_mfg_operators`。

分类规则:
- 锚点: `_SYSTEM_CONTRIBUTORS` 注册的 Trade anchor + 订单机制型 buff (trade_ord_law/long/closure)
- 提供者: B 层消费者 / A6 设施联动（目标设施=Trade）
- 纯效率: 其余

复用 `MfgClassification` dataclass 和 `build_candidate_pool`。

### Step 2: solver.py — `_evaluate_trade_combo`

新增 Trade 3 人组合评估函数：

```
lmd_per_day = evaluate_room × efficiency_integrated → 扣减赤金约束
```

双通道：`evaluate_room` 算效率积分 + `_get_trade_order_multiplier` 算订单机制 LMD 基准。

### Step 3: solver.py — `_greedy_remaining` 简洁化

- 设施过滤改为正面匹配: `room.room_type in ("Power", "Reception", "Office")`
- 删除 Trade 专属 A7 逻辑 (L222-L235)
- 删除 `get_trade_order_equivalent_efficiency` 导入

### Step 4: solver.py — `solve_mvp` Phase 3 拆分

- **Phase 3a (新)**: Trade C(n,3) 穷举（释放 locked Trade 支撑 → 分类 → 组合 → 评估 → 贪心分配 2 间）
- **Phase 3b (旧精简)**: Power/Reception/Office 贪心

### Step 5: synergy.py — 删除 `get_trade_order_equivalent_efficiency`

整函数删除（L61-L150，含 `_partner_available`）。

### Step 6: 测试更新

- `test_synergy.py`: 移除 A7 硬编码相关用例，新增 `classify_trade_operators` 用例
- `test_solver.py`: 新增 Trade 穷举用例

### Step 7: 验证

`python -m pytest tests/ -v`

---

## 变更量预估

| 操作 | 行数 |
|------|:---:|
| 新增 | +105 |
| 删除 | -130 |
| **净变化** | **-25** |
| 硬编码值 | 16 → 0 |
