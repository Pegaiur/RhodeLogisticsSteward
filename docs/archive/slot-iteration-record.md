# 槽位模型演进记录

> 分支：`feat/slot-iteration`
> 归档日期：2026-05-31
> 说明：V1 SlotIterationStrategy 实施计划 + 实施笔记合并归档。V2 SlotSolver 已替代两者。

---

## 一、架构路线变更

SlotIterationStrategy（前四期）已验证 D[d] 反馈框架在真实数据上成立——单班次积分反超 BaselineStrategy（+1,356）。但架构负重过大：

| 问题 | 表现 |
|------|------|
| Pipe 式加工 | Pipeline 线性串联，Phase 间通过 `locked_support` / `assigned_ids` / `assigned_names` 三个可变 dict 通信 |
| 信息断裂 | Phase A/B 穷举在空白中枢上下文中计算 buff_pool，Phase C 结果对穷举不可见（需 override_pool 补丁） |
| 补丁累积 | per-operator 贡献、type3 互斥、边际差分——每一项都是事后发现事后补 |
| 策略层增生 | `strategies/slot_iteration.py` 作为 `baseline.py` 的 fork，复用 exhaust_* 的 Phase 函数签名但覆盖控制流 |

**决策：不修 SlotIterationStrategy，改做 SlotSolver。**

SlotSolver 直接实现 `slot-processing-model.md` §9.5 混合状态迭代策略：

- `solver/slot/` 子包，SlotSolver 类为唯一求解入口
- SlotContext 统一状态载体（替代 `locked_support` + `assigned_ids` + `assigned_names`）
- Mfg/Trade 穷举逻辑提取到 `slot/mfg.py` / `slot/trade.py`（复用 `evaluate_room`）
- 中枢/宿舍/发电/会客/办公室统一用 D[d]-based contribution 贪心
- 机会成本内置于贡献评分
- 迭代 + 记忆 → 收敛于邻域局部最优

---

## 二、V1 架构约束（已废弃）

V1 SlotIterationStrategy 的零破坏红线——以下模块在新功能开发中不可修改（被 SlotSolver 完全绕过）：

| 模块 | 原因 |
|------|------|
| `fill_control.py` | BaselineStrategy 依赖 |
| `fill_remaining.py` | BaselineStrategy 依赖 |
| `fill_dorm.py` | BaselineStrategy 依赖 |
| `global_state.py` | BaselineStrategy 依赖 |
| `refine.py` | BaselineStrategy 依赖 |
| `strategies/baseline.py` | 对照基线 |
| `strategies/kbeam.py` | 对照基线 |
| `strategies/iterative.py` | 对照基线 |
| `evaluate.py` | 所有策略共享 |
| `models.py` | 所有策略共享 |

V1 计划分两期：一期最小可行实现（热启动 + D 反馈），二期完整实现（λ bisection + 联合扰动 + 冷启动 + 心情展平）。

---

## 三、V1 实施关键节点

**一期**：`slot_iteration.py`（~280 行纯函数）+ `SlotIterationStrategy`（~250 行）。热启动（A₀ = BaselineStrategy 结果），λ ≡ 0，固定 2×12h+8h 窗口，`mood_ctx=None` 走乐观假设。

**二期**：λ bisection（单窗口简化版：移出→翻倍/移入→减半/不变→衰减），S₀_max 冷启动（18 间空房间模板），多启动取 ΣD 和择优选，联合扰动（~25 耦合对 × top-3×3 替换）。

**三期**：验收发现产出退化（-25%），诊断修复 F1-F5（边际差分/基数修正/槽位计算/D 向量重算），SL1-SL4（link_value/reader_marginal_prod/IterationContext）。

**四期**：建模补全 F6-F10（望外势互斥/type3 同种取最高/override_pool/Power 条件加成/per-operator 贡献）。终态：EXP 18,000/12h，积分 21,480 反超 baseline（+1,356）。

各期详细修复记录见原 `slot-iteration-notes.md`（归档前版本）。
