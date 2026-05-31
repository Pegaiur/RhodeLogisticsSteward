# 时间槽排班模型评估

> 状态：设计草案，基于换班问题诊断→λ 双层修复→模型重新定义的全链路调研。

---

## 一、问题溯源链

### 1.1 起点：不换班

运行 `report.py`（3×8h）时，班次 0 和班次 1 的分配完全相同，班次 2 仅有局部变化，核心岗位（如 Trade[0] 巫恋-但书-龙舌兰）跨三班一直不动。

### 1.2 第一层诊断：λ 偏离

对比设计文档 [slot-processing-model-draft.md](./slot-processing-model-draft.md) §9.5 与实现代码，发现 λ 的结构性偏离：

- **设计**：λ 是双层 —— per-op bisection 惩罚（`λ[op]`）+ 标量锚定（`λ_k`，始终为正）
- **实现**：塌缩为单层 —— 仅 per-op bisection，宿舍恢复奖励用 per-op `lambda_ops` 且有 `>0` 守卫

后果：`pool_hard ≈ 26.7h`，2-3 班次总时长 ≤ 24h 未超池，所有 `λ[op]` 恒为 0。宿舍恢复奖励永不触发，恢复型干员无经济价值，宿舍选择不受恢复驱动。

### 1.3 修复尝试：λ_k 标量锚定

两轮 TDD 提交（`1eb5d0d`、`0d44821`）：
- 新增 `_compute_lambda_k`：基于 Phase A/B Mfg/Trade 槽位每小时边际 LMD 中位数，始终为正
- 修改 `_dorm_contribution`：恢复奖励改用 `ctx.lambda_k`（标量）
- 全量 539 测试通过

**修复后效果**：宿舍恢复型干员获得正经济估值。但换班仍未发生。

### 1.4 第二层诊断：λ 与外部约束双双失效

深入追踪 3×8h 场景下的数值：

| 窗口 | 入局 mood | t_red = mood/burn | vs 8h 班次 | λ[op] | 结果 |
|:--:|:--:|:--:|:--:|:--:|------|
| W0 | 24.0 | 36.9h | 36.9 > 8 → 满分 | 0 | 选中 |
| W1 | 18.8 | 28.9h | 28.9 > 8 → 满分 | 0 | 选中 |
| W2 | 13.6 | 20.9h | 20.9 > 8 → 满分 | 0 | 选中 |

`t_red` 始终远大于班次时长——心情截断仅在 `mood/burn < shift_hours` 时触发，对 8h 班次需要 mood < 5.2，但 3 班后仍有 13.6。λ 的激活条件 `hours_used > pool` 要求 burn ≥ 1.0，但游戏 `base_burn` 上限为 1.0（单人工位），3 人工位仅 0.90——**游戏机制决定 pool 永远 ≥ 24h**。

结论：2-3 班次场景下，λ 定价和心情约束双双落入盲区。这不是参数问题，是模型假设的稀缺性在短班次下不成立。

---

## 二、模型重新定义

### 2.1 从窗口到时间槽

当前窗口模型：

```
N 个等长窗口 →  每窗口独立求解  →  心情跨窗口耦合  →  λ 间接定价
```

核心假设是"每个窗口的分配从零开始，上一窗口的分配状态不影响当前决策"。这个假设在 2-3 班次场景下产生两个致命后果：

- 稀缺性不成立 → λ 不激活
- 没有留下"当前谁在岗"的信息 → 无法做"换不换"的增量决策

新模型改为时间槽：

```
72h × 1h 粒度  →  全时间轴统一求解
每个时刻 t：决定哪些槽位换人（增量决策）
目标：最大化 Σ(产出 - 换班惩罚)
约束：每个干员的心情消耗 ≤ 心情上限 + 恢复
```

核心假设变为"换班本身是成本，干员留任是默认状态"。换班惩罚模拟玩家懒于频繁操作的倾向。

### 2.2 正交分层

| 层 | 职责 | 窗口模型 | 时间槽模型 | 复用？ |
|----|------|---------|-----------|:--:|
| 求值引擎 | 给定状态下每干员的边际价值 | D[d] + contribution | D[d] + contribution | ✅ |
| 决策骨架 | 组织"如何分配"的计算 | Phase A→B→C→D 顺序贪心 | 逐时步增量替换 | ❌ |
| 跨期约束 | 跨班次的资源分配 | λ bisection 间接定价 | 心情硬约束 + λ 对偶定价 | ❌ 替换 |

**求值引擎完全不动**——`evaluate_room`、synergy 联动体系、buff_pool、D[d] 偏导数都是"给一组干员+房间+时长→算贡献"的无状态函数，不关心调用方是窗口模型还是时间槽模型。

**决策骨架重写**——从"每窗口从零构建分配"变为"每时步对每个槽位做留/换二选一"。

### 2.3 换班惩罚

换班成本建模为逐干员操作次数的函数：

```
swap_cost(t) = Σ_{槽位 j} penalty[op_j(t) ≠ op_j(t-1)]

penalty(k) = base_cost × (1 + escalation)^(k-1)
            k = 该槽位累计换班次数
```

- `base_cost`：单次换班的基准 LMD 等值（如 500 LMD）
- `escalation`：惩罚增长率（如 0.3，即每次比上次贵 30%）
- 累积惩罚模拟"用户越来越不想再操作"的边际效应

参数由 `SolverParams` 管理，用户可覆写（如 `swap_cost=0` 即允许无限换班）。

---

## 三、λ 的新角色：从惩罚到机会成本

### 3.1 角色转换

| | 窗口模型中的 λ | 时间槽模型中的 λ |
|------|-------------|-------------|
| 语义 | 事后惩罚：你用太多了 | 事前估价：你每多工作 1h 值多少 |
| 触发 | `hours_used > pool` 翻倍 | 始终存在 |
| 用途 | 压低超池干员的 contribution | 量化"去休息"的机会成本 |
| 更新 | 离散 bisection，跨迭代收敛 | 随心情连续更新 |

### 3.2 核心决策：留 vs 换

```
对每个在岗干员 op：
  留任净收益 = λ(op) - burn(op) × λ_mood(op)
  替换净收益 = λ(alt) - burn(alt) × λ_mood(alt) - swap_cost
  若 替换净收益 > 留任净收益 → 换人
```

其中 `λ_mood(op)` 是干员 op 的单位心情影子价格——"这一点心情如果留到以后用，能产多少 LMD"。

### 3.3 对偶结构

问题是标准的资源分配对偶：

```
主问题：  max Σ_t (产出_t - swap_cost_t)
          s.t. Σ_t burn(op, t) ≤ mood_full + recovery(op)

对偶变量：λ_mood[op] = 干员 op 的单位心情影子价格
```

对偶定价下自然导出"高效率留场、低效率顶班"的模式：

- **高效率干员**：`λ_mood` 高 → 心情贵 → 该休息时就去休息（后续还能高产出），但不到临界点尽量留场（替换者不如他们）
- **低效率干员**：`λ_mood` 低 → 心情便宜 → 作为顶班耗材，专门在高效率干员休息时填补

宿舍恢复的估值与 `λ_mood` 完全对偶：`recovery × λ_mood` = 恢复的心情 × 单位心情价值，与 Mfg/Trade 生产在同一量纲（LMD 等值）下可比。

---

## 四、实现评估

### 4.1 改动映射

| 模块 | 改动 | 行数 | 说明 |
|------|:--:|:---:|------|
| `solver/time_slot.py` | **新增** | ~350 | 1h 粒度求解器：逐时步增量替换 + 换班惩罚 + 心情硬约束 |
| `solver/slot/contribution.py` | 修改 | ~20 | 留任/替换比较逻辑：`λ - burn × λ_mood` |
| `solver/params.py` | 新增 | ~15 | `swap_cost_base`、`swap_cost_escalation`、`total_hours`、`slot_minutes` |
| `mood_flow.py` | 修改 | ~30 | 1h 步进的 `after_one_hour()` / `recover_one_hour()` 方法 |
| `solver/slot/solver.py` | 修改 | ~50 | `solve_slot` 入口改为调用 `solve_time_slot` |
| `solver/slot/solver.py` | **删除** | ~150 | `_update_lambda_shadow`、`_reset_ctx`、`_compute_lambda_k`（不再需要） |
| **净增** | | **~320** | |

### 4.2 完全复用的模块

- `evaluate.py`：`evaluate_room()` — 房间效率求值（0 行变更）
- `synergy/`：全量联动体系（0 行变更）
- `production.py`：产出计算、订单机制（0 行变更）
- `efficiency_fn.py`：e(t) 分段函数（0 行变更）
- `dorm_recovery.py`：宿舍恢复评估（0 行变更）
- `models.py`：Operator / Skill / LayoutConfig（0 行变更）
- `data_loader.py`：数据加载（0 行变更）
- `output.py`：MAA 协议输出（0 行变更）
- `synergy/_derived.py`、`registry.py`、`helpers.py`、`types.py`（0 行变更）
- `solver/slot/context.py`、`mfg.py`、`trade.py`、`control.py`、`remaining.py`、`partials.py`（0 行变更）

### 4.3 可删减的模块

| 模块 | 原因 |
|------|------|
| `solver/slot/solver.py` 中 `_update_lambda_shadow` | λ bisection 改为对偶定价 |
| `solver/slot/solver.py` 中 `_reset_ctx` | 不再有迭代重置 |
| `solver/slot/solver.py` 中 `_compute_lambda_k` | λ_k 标量锚定由 λ_mood 替代 |
| `solver/slot/solver.py` 中 `_pool_for`、`_facility_slots_for` | pool_hard 硬约束由心情硬约束替代 |

---

## 五、待讨论

1. **换班惩罚的参数校准**：`base_cost` 和 `escalation` 的实际游戏映射？需要用户调研还是社区经验值？

2. **宿舍在时间槽中的角色**：宿舍是"工作期间提供 buff_pool 的设施"还是"恢复干员的场所"（或两者兼顾）？当前模型两者混杂，时间槽下可能需要明确分离。

3. **求解策略**：72h × 50 槽位的决策空间极大，用贪心（逐时步独立决策）还是滚动窗口（每 k 步做一次优化）？对偶定价下贪心是否足够逼近最优？

4. **与 MAA 协议的衔接**：当前输出 `ShiftPlan` 列表（每班一张），时间槽输出 72 步如何映射回 MAA 协议？可能需要在输出层做时间槽→班次的降采样。

5. **`λ_mood` 的初值**：对偶定价需要初始 λ_mood 值，冷启动方案是什么？参考 S₀_max ？还是从已知 pool_hard 推导？

---

## 六、关联文档

- [slot-processing-model-draft.md](./slot-processing-model-draft.md) — 槽位加工模型设计（当前求解器理论基础）
- [strategy-brief.md](./strategy-brief.md) — 排班策略概要
- [constraints-and-data-baseline.md](./constraints-and-data-baseline.md) — 约束体系与数据基线
- [docs/archive/mood-multi-shift-plan.md](./archive/mood-multi-shift-plan.md) — 心情建模与多班次计划（历史文档）
