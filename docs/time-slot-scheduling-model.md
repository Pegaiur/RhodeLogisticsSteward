# 机会成本补充覆盖方案

> 状态：Phase 1 已实施（2026-05-31）。Phase 2（λ_mood + swap_cost）为设计草案。

---

## 一、现状

### 1.1 窗口模型能力范围

| 能力 | 14×12h（7 天） | 3×8h（1 天） |
|------|:------:|:----:|
| 跨班次轮换 | ✅ λ 激活，宿舍恢复正常 | ⚠️ λ 未激活（pool 未超） |
| 宿管数量控制 | ✅ room-aware 机会成本 | ✅ room-aware 机会成本 |
| C 类冗余自动排除 | ✅ Rule 3 取 max | ✅ Rule 3 取 max |

### 1.2 短班次 λ 盲区

`pool_hard = mood_full / burn ≥ 24.0 / 1.0 = 24.0h`。`base_burn ≤ 1.0`
（3 人工位仅 0.90）是游戏机制天花板，pool 永不低于 24h。

3×8h 总时长 24h 恰好不超越 pool，`λ[op]` 的激活条件 `hours_used > pool` 不满足：

| 窗口 | 入局 mood | t_red | vs 8h | λ[op] |
|:--:|:--:|:--:|:--:|:--:|
| W0 | 24.0 | 36.9h | 36.9 > 8 → 满分 | 0 |
| W1 | 18.8 | 28.9h | 28.9 > 8 → 满分 | 0 |
| W2 | 13.6 | 20.9h | 20.9 > 8 → 满分 | 0 |

### 1.3 窗口模型未覆盖的维度

1. **组合级归零机会成本** —— whisper/automation/归零变体将室友效率归零，但穷举评分不扣除被归零者的替代价值
2. **换班成本** —— 每窗口从零构建分配，不表达"让人留在岗位上"的惯性
3. **λ_mood（单位心情影子价格）** —— `λ[op]` 是"你用了多少小时"的惩罚，非"每多用 1 心情值多少"的边际定价
4. **短班次 λ 盲区** —— 需要不依赖 `hours_used > pool` 的替代定价

---

## 二、Phase 1：组合级机会成本（✅ 已实施）

### 2.1 覆盖范围

对三类归零联动（whisper / automation / zeroing_variant），在穷举评分循环中逐组合计算被归零干员的替代价值，以 LMD 等值从组合评分中扣除。

| 归零类型 | 归零者 | 室友补偿 | 公式 | sensitivity |
|----------|--------|:---:|------|:---:|
| whisper | 巫恋(trade_ord_vodfox) | +45%/人 | `max(own_eff - 45%, 0)` 逐室友 | — |
| automation | 森蚺/温蒂/异客/掠风 | 无 | `own_eff` 全额 | 0.5 |
| zeroing_variant | 科学改造/流程优化 | 无 | `own_eff` 全额 | 0.5 |

不覆盖：红云/泡泡/槐琥（非归零，evaluate_room 已精确计算室友贡献）。

### 2.2 架构定位

```
求值层（不变）              新增模块
─────────────────────────   ──────────────────
evaluate_room()              opportunity.py
contribution()               compute_opportunity_cost_lmd()
partials.py D[d]             

消费方：
trade.py 评分循环 ── lmd -= compute_opportunity_cost_lmd(...)
mfg.py   评分循环 ── score -= compute_opportunity_cost_lmd(...) / scale
```

`opportunity.py` 位于求值层，是评估"这个组合值不值得"的无状态纯函数。与 `evaluate_room` 归类同层——归零逻辑在 evaluate_room 内部（效率归零），机会成本在外部（被归零者的替代价值）。

### 2.3 实施文件

| 文件 | 改动 | 行数 |
|------|------|:---:|
| **新增** `solver/slot/opportunity.py` | 统一机会成本模块：1 公开函数 + 4 私有辅助，三种归零模式自动检测 | +140 |
| `solver/slot/trade.py` | 删除旧 `_has_whisper`/`_zeroed_efficiency_sum`/`_apply_whisper_opportunity`（~50行）；评分循环加一行内联调用 | +2/-54 |
| `solver/slot/mfg.py` | 评分循环加一行内联调用 | +2 |
| `synergy/__init__.py` | 新增 `_ZEROING_VARIANT_TABLE` 重导出 | +1 |
| **新增** `tests/solver/slot/test_opportunity.py` | 21 测试：公式数值验证 + 边界条件 + 常量一致性 | +180 |
| `tests/solver/slot/test_trade.py` | 删除旧 whisper 测试 | -15 |

净增 ~260 行，全量 566 测试零回归。机会成本逻辑收敛到单模块单入口，`trade.py` 和 `mfg.py` 各一行调用，无需知道归零类型。

### 2.4 与现有体系的关系

- **与 `evaluate_room`**：互补——evaluate_room 正确归零室友效率，opportunity.py 补充"如果不归零这些人的替代价值"
- **与 `contribution.py` 宿舍机会成本**：概念同构，实现独立——两者都遵循机会成本的基本定价模式（牺牲率 × 价格 × 时间），但因量纲（生产效率% vs 心情恢复率）和价格来源（产品市值 vs 影子价格 λ）不同，保持独立实现
- **与 λ 惩罚**：正交——λ 管跨窗口用量（hours_used vs pool），机会成本管单窗口内组合质量
- **与 Phase 2**：返回 LMD 等值，与 λ_mood/swap_cost 同量纲，可直接参与留/换决策
- **"窗口模型"的定义**：指 slot-processing-model-draft.md §3.3 的"窗口展开：选择权的分配"，即每窗口独立 Phase A→D 贪心求解 + λ bisection 跨窗口耦合。本文档的 Phase 1/2 均在此窗口模型基础上叠加，不替换其决策骨架

---

## 三、Phase 2：跨窗口定价与换班惩罚（设计草案）

窗口模型负责"每窗口放谁最优"，Phase 2 负责三个它不表达的跨窗口维度：

```
窗口模型（现有，不变）               Phase 2（设计草案）
─────────────────────────         ─────────────────────────
Phase A→D 顺序贪心                不影响 Phase 决策
contribution 评分                  新增 λ_mood 维度
λ bisection 跨窗口约束             新增 swap_cost 换班成本
per-window 独立求解                跨窗口留/换增量决策
```

### 3.1 三层关系

| 层 | 职责 | 窗口模型 | Phase 2 |
|----|------|---------|---------|
| 求值引擎 | 算边际价值 | `contribution()` + `opportunity.py` | 不变 |
| 槽位分配 | 每窗口放谁 | Phase A→D 贪心 | 不变 |
| 跨期约束 | 谁该休息、换班成本 | `λ[op]` bisection | `λ_mood` + `swap_cost` |

`λ[op]` 和 `λ_mood` 正交：

| | λ[op] | λ_mood[op] |
|------|--------|------------|
| 语义 | 使用小时惩罚 | 心情消耗定价 |
| 量纲 | LMD 等值/h 使用 | LMD 等值/心情 |
| 触发 | `hours_used > pool` | 始终激活 |
| 更新 | 离散 bisection | 随心情连续变化 |

### 3.2 核心机制

**λ_mood：单位心情的影子价格**
```
λ_mood[op] = contribution(op, best_facility) / (shift_hours × burn_rate(op))
```
干员 op 每消耗 1 点心情，放弃在最佳岗位上工作 `1/burn` 小时的 LMD 等值。

**与现有 dorm Part 2/3 的对齐**：

Part 2 当前：`室友恢复增量 × roommate_λ × hours / 24`
若 `roommate_λ` 替换为 `λ_mood[roommate]`：`室友恢复增量 × λ_mood[roommate] × hours / 24`
结构相同，λ 来源不同。`λ_mood` 在 `λ[op] = 0` 时仍有值。

Part 3 当前：`baseline_rate × hours × θ / 24  （θ = 未分配干员 λ 平均）`
θ 改用 `λ_mood` 平均后，定价更精确。

**swap_cost：换班惩罚**
```
swap_cost = Σ_{槽位 j} penalty[op_j(t) ≠ op_j(t-1)]
penalty(k) = base_cost × (1 + escalation)^(k-1)
```
参数由 `SolverParams` 管理（`swap_cost_base=500`、`swap_cost_escalation=0.3`）。

**留/换决策**（窗口求解后后处理，仅 Phase A/B）：
```
留任净收益 = λ(op) - burn(op) × λ_mood(op)
替换净收益 = λ(alt) - burn(alt) × λ_mood(alt) - swap_cost
若 替换净收益 > 留任净收益 → 换人
```

### 3.3 实现评估

| 模块 | 改动 | 行数 | 说明 |
|------|:--:|:---:|------|
| `solver/slot/contribution.py` | 修改 | ~15 | Part 2/3 可选使用 `λ_mood` |
| `solver/slot/solver.py` | 新增 | ~60 | `_compute_lambda_mood()` + 留/换后处理 |
| `solver/params.py` | 新增 | ~10 | `swap_cost_base`、`swap_cost_escalation` |
| `solver/slot/context.py` | 新增 | ~10 | `ctx.prev_assignments`（上一窗口快照） |
| **净增** | | **~95** | |

**不动**：`remaining.py`、`dorm_recovery.py`、`mood_flow.py`、`evaluate.py`、
`synergy/`、`production.py`、`efficiency_fn.py`、`models.py`、`data_loader.py`、
`output.py`、`opportunity.py`。`_update_lambda_shadow`、`_compute_lambda_k` 保留（与 `λ_mood` 互补）。

---

## 四、待讨论（Phase 2）

1. **λ_mood 冷启动**：首次窗口无 Phase A/B 分配，初值取 `λ_k` 还是 `S₀_max / burn`？
2. **swap_cost 校准**：`base_cost = 500 LMD` 的合理性？
3. **λ_mood 与 λ[op] 的分工**：Part 2 建议用 `λ_mood`（始终激活），`λ[op]` 保留在 `contribution()` 外层扣除（超池惩罚）。
4. **留/换是否仅在 Mfg/Trade 生效**：Control/Power/Dorm 已有 contribution 框架驱动，留/换显式比较对它们可能多余。
5. **3×8h 效果预估**：需要一笔推演验证 `λ_mood` 在短班次下产生有意义的恢复定价。
6. **Phase 1 sensitivity 参数升级**：`_AUTOMATION_SENSITIVITY = 0.5` 可升级为 `SolverParams` 可调参数。

---

## 五、关联文档

- [slot-processing-model-draft.md](./slot-processing-model-draft.md) — 槽位加工模型设计
- [strategy-brief.md](./strategy-brief.md) — 排班策略概要
- [constraints-and-data-baseline.md](./constraints-and-data-baseline.md) — 约束体系与数据基线
- `steward_core/solver/slot/opportunity.py` — Phase 1 实现源码
