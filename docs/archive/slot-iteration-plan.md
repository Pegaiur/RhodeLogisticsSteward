# 槽位迭代求解器实施计划

> **理论依据**：[slot-processing-model-draft.md](slot-processing-model-draft.md)（统一槽位加工模型，v1 草案）
> **分支**：`feat/slot-iteration`
> **原则**：建模草案保持纯理论不膨胀；本文档仅记录实施细节与架构决策；现有策略零破坏。

---

## 1. 架构防腐规则

### 1.1 不可修改模块清单（零破坏红线）

以下模块在新功能开发中**禁止任何修改**——它们是 BaselineStrategy / KBeamStrategy / IterativeStrategy 的运行时依赖，任何改动都会污染对照基线：

| 模块 | 原因 |
|------|------|
| `fill_control.py` | BaselineStrategy 依赖其 `fill_control()` 函数 |
| `fill_remaining.py` | BaselineStrategy 依赖其 `fill_remaining()` 函数 |
| `fill_dorm.py` | BaselineStrategy 依赖其 `fill_dorm()` 函数 |
| `global_state.py` | BaselineStrategy 依赖其稀缺度评分注入 |
| `refine.py` | BaselineStrategy 依赖其后处理 |
| `strategies/baseline.py` | 对照基线，零改动 |
| `strategies/kbeam.py` | 对照基线，零改动 |
| `strategies/iterative.py` | 对照基线，零改动 |
| `evaluate.py` | 所有策略共享的 `evaluate_room()`，零改动 |
| `models.py` | 所有策略共享的数据模型 |

### 1.2 允许的轻量修改

| 模块 | 改动 | 向后兼容 |
|------|------|:---:|
| `exhaust_mfg.py` | 函数签名新增可选参数 `precomputed_support=None` | ✅ 默认 None 走原逻辑 |
| `exhaust_trade.py` | 同上 | ✅ |
| `support.py` | `_evaluate_with_support()` 新增 `precomputed_support: SupportResult\|None=None` 参数 | ✅ 默认 None 走原逻辑 |
| `config.py` | 新增 2 个字段 | ✅ 默认值不影响现有策略 |
| `strategies/__init__.py` | 注册新条目 | ✅ 纯追加 |

### 1.3 模块边界规则

- `solver/slot_iteration.py`：纯函数模块，**禁止导入任何 solver/ 下的模块**（仅可导入 `models` + `synergy/` + 标准库）
- `solver/strategies/slot_iteration.py`：Strategy 子类，可以导入 solver/ 下的模块，**禁止修改全局状态**
- 新增模块不超过 3 个文件，每个 ≤ 300 行

---

## 2. 范围界定

### 2.1 第一期：最小可行实现（验证 P_new ≥ P_BL）

| # | 任务 | 文件 | 新/改 | 行数 |
|:--:|------|------|:---:|:---:|
| 1 | IterationContext + S/D 提取 + D 计算 + 统一 `contribution()` 入口（按 facility 分派到 5 个 helper） | `solver/slot_iteration.py` | 新 | ~280 |
| 2 | SlotIterationStrategy 子类 + 迭代循环 + Phase C/D 贪心（作为私有方法） | `solver/strategies/slot_iteration.py` | 新 | ~250 |
| 3 | SolverConfig 新增 `slot_max_rounds: int = 5`、`slot_cold_start: bool = False` | `solver/config.py` | 改 | ~15 |
| 4 | 注册 `slot_iter` / `slot_iter_cold` | `solver/strategies/__init__.py` | 改 | ~10 |
| 5 | `exhaust_mfg()` 新增 `precomputed_support=None` 参数 | `solver/exhaust_mfg.py` | 改 | ~40 |
| 6 | `exhaust_trade()` 新增 `precomputed_support=None` 参数 | `solver/exhaust_trade.py` | 改 | ~25 |
| 6b | `_evaluate_with_support()` 新增 `precomputed_support=None` 参数 | `solver/support.py` | 改 | ~15 |
| 7 | 测试：回归 + 收敛 + 对比 | `tests/test_slot_iteration.py` | 新 | ~220 |

**首期约束**：热启动（A₀ = BaselineStrategy 结果）、λ 项从 contribution 公式中省略（非写 λ=0，留待二期添加）、固定 2×12h+8h 窗口、`mood_ctx=None` 走乐观门控假设、跳过联合扰动。

### 2.2 第二期：完整实现

| # | 任务 | 行数 |
|:--:|------|:---:|
| 8 | λ 离散 bisection | ~50 |
| 9 | 联合扰动（~25 耦合对 × 3×3 替换） | ~80 |
| 10 | S₀_max 冷启动 | ~60 |
| 11 | 心情展平 §7（夕/令/铅踝） | ~80 |
| 12 | 多启动策略 | ~50 |
| 13 | 扩展测试 | ~100 |

---

## 3. 关键架构决策

### 3.1 Phase C/D 不修改原模块——由 Strategy 子类自实现

`fill_control.py` 等 6 个模块列入 §1.1 不可修改清单。SlotIterationStrategy 在其 `solve()` 方法中**直接实现 Phase C/D 的 contribution 贪心逻辑**，作为私有方法：

```python
class SlotIterationStrategy(Strategy):
    def _phase_c_control(self, ctx, pool, assignments):
        """Control contribution 贪心，替代 fill_control() 调用"""
        ...

    def _phase_d_remaining(self, ctx, pool, assignments):
        """Power/Office/Reception/Dorm contribution 贪心，替代 fill_remaining()+fill_dorm()"""
        ...
```

`BaselineStrategy.solve()` 继续调用 `fill_control()` / `fill_remaining()` / `fill_dorm()`，完全不受影响。

### 3.2 exhaust_mfg/exhaust_trade 支撑逻辑外部化（最小侵入）

仅修改函数签名，默认行为不变：

```python
# exhaust_mfg.py / exhaust_trade.py
from .bundle import SupportResult

def exhaust_mfg(
    operators, layout, params,
    precomputed_support: SupportResult | None = None,  # 新增
    ...
):
    if precomputed_support is not None:
        support = precomputed_support           # 跳过内部 compute_optimal_support
    else:
        support = compute_optimal_support(...)  # 原逻辑

# support.py 的 _evaluate_with_support() 同模式新增:
def _evaluate_with_support(
    ...,
    precomputed_support: SupportResult | None = None,
):
    # 若传入则跳过内部 compute_optimal_support() 调用
```

`SupportResult` 类型包含 `.support_map: dict[str, list[str]]` + `.bundles: list[str]` 两个字段，覆盖 `exhaust_mfg` 第 123 行（`scarcity_penalty`）和第 151 行（`gs.allocate`）的 bundles 消费。

### 3.3 IterationContext 统一传递

`evaluate_room` 签名不修改。创建独立的 `IterationContext` dataclass 仅在 slot_iteration 模块内使用：

```python
# solver/slot_iteration.py
@dataclass(frozen=True)  # 不可变，防止副作用
class IterationContext:
    window_index: int
    window_hours: float
    S: dict[str, float]
    D: dict[str, float]
    lambda_op: dict[str, float]
    ratios: _Ratios              # 嵌套不可变 dataclass
```

`frozen=True` 防止迭代过程中意外修改上下文。

### 3.4 与 IterativeStrategy 的正交关系

首期不内嵌 BuffPool 迭代。外层每轮 Step 更新时直接调用 `GlobalContext.from_plan()` 重算 BuffPool。若后续实证表明双层迭代有价值，通过组合模式合并。

---

## 4. 新增模块接口契约

### 4.1 `solver/slot_iteration.py`

```python
# 依赖：仅 models, synergy/__init__, 标准库
# 禁止导入：solver/ 下任何模块

STATE_DIMENSIONS = ("perception", "yanhuo", "engineering_robots",
                    "monster_cuisine", "silent_resonance")

@dataclass(frozen=True)
class IterationContext:
    ...

def extract_state_vector(
    assignments: list[RoomAssignment],
    operators: dict[str, Operator],
    layout: LayoutConfig,
    mood_ctx: MoodContext | None = None,
) -> dict[str, float]:
    """返回 STATE_DIMENSIONS 中各维度的值。
       mood_ctx=None 时走乐观假设（令/夕取最优门控区间）。"""

def _get_S_readers(
    assignments: list[RoomAssignment],
    operators: dict[str, Operator],
) -> dict[str, set[str]]:
    """返回 {dimension: {reader_names}}，从 _B_BUFF_CONSUMER_TABLE 获取映射"""

def compute_partial_derivatives(
    assignments: list[RoomAssignment],
    window_hours: float,
    operators: dict[str, Operator],
    drone_multiplier: float = 1.0,
) -> dict[str, float]:
    """返回 P 对每个 S[d] 的偏导数 D[d]。
       仅遍历有类型 1f 技能的干员（通过 _get_S_readers 判定）。"""

def contribution(
    op_name: str,
    facility: str,
    ctx: IterationContext,
    operators: dict[str, Operator],
    assignments: list[RoomAssignment],
) -> float:
    """统一的 contribution 计算入口，按 facility 分派到内部 helper。
       首期 λ≡0，公式中不含 -λ×hours 项（留待第二期添加）。"""
```

### 4.2 `solver/strategies/slot_iteration.py`

```python
class SlotIterationStrategy(Strategy):
    def solve(self, operators, layout, params) -> list[RoomAssignment]:
        # 1. 热启动
        baseline = BaselineStrategy(self.config).solve(operators, layout, params)
        A = [copy(a) for a in baseline]
        # 2. 提取初始 S, D
        S = extract_state_vector(A, operators, layout)
        D = compute_partial_derivatives(A, WINDOW_HOURS, operators)
        V: set[tuple] = set()  # 记忆集合
        # 3. 迭代
        for _ in range(self.config.slot_max_rounds):
            ctx = IterationContext(...)
            A = self._phase_a_b_mfg_trade(ctx, operators, layout, params)
            A = self._phase_c_control(ctx, operators, A)
            A = self._phase_d_remaining(ctx, operators, layout, params, A)
            S = extract_state_vector(A, operators, layout)
            D = compute_partial_derivatives(A, WINDOW_HOURS, operators)
            # 记忆检查
            key = self._assignment_key(A)  # key = tuple(sorted((a.room_type, a.room_index, a.product, tuple(sorted(a.operators))) for a in A if a.operators))
            if key in V:
                break
            V.add(key)
        return A
```

---

## 5. 测试计划

### 5.1 测试文件与结构

```
tests/
├── test_slot_iteration/
│   ├── __init__.py
│   ├── conftest.py              # 共享 fixtures：小型干员池、mock 数据
│   ├── test_pure_functions.py   # slot_iteration.py 纯函数单元测试（无 Strategy 依赖）
│   ├── test_strategy.py         # SlotIterationStrategy 集成测试
│   └── test_regression.py       # 回归测试：BaselineStrategy 输出不变
```

### 5.2 单元测试：纯函数

| 测试 | 验证内容 |
|------|---------|
| `test_extract_state_vector_empty` | 空分配 → 全零 S |
| `test_extract_state_vector_ling_only` | 仅有令(Control, mood>12)时 S[yanhuo]=15, S[perception]=0 |
| `test_extract_state_vector_full` | 完整中枢 (令+夕+重岳+塑心+絮雨) + 桑葚(Office) → 各维度预期值 |
| `test_compute_D_no_readers` | 无类型 1f 读取者时 D 全零 |
| `test_compute_D_rosemary_only` | 迷迭香在 Mfg CR → D[perception] = base×hours×0.01 |
| `test_compute_D_multiple_readers` | 迷迭香+黍同时在场 → 各自维度 D 正确 |
| `test_contribution_control_ling` | 令在 Control 的 contribution = 15×D[yanhuo]（无类型 3 时） |
| `test_contribution_control_amiya` | 阿米娅 = 类型 3 注入 × 6 Trade 槽位（无状态写入时） |
| `test_contribution_power` | 发电站 contribution 包含 drone_to_mfg_ratio 折算 |
| `test_contribution_reception` | 会客室 contribution 包含 reception_to_mfg_ratio 折算 |
| `test_contribution_office` | 办公室 contribution 包含 office_to_mfg_ratio 折算 |
| `test_contribution_dorm` | 宿舍 contribution 包含恢复速率 × hours × λ |
| `test_iteration_context_immutable` | frozen=True 防止运行时修改 |

### 5.3 集成测试

| 测试 | 验证内容 |
|------|---------|
| `test_slot_iter_vs_baseline` | 10 个真实数据集上 P_slot ≥ P_baseline（100%） |
| `test_convergence_monotonic` | 每轮 P 严格递增（含退化路径记忆机制） |
| `test_convergence_rounds` | 热启动中位数 ≤ 2 轮收敛 |
| `test_hot_start_round1` | 第一轮迭代后 P ≥ P_baseline（验证热启动命题） |
| `test_memory_prevents_cycle` | 构造一个重访场景，验证终止而非死循环 |
| `test_slot_iter_deterministic` | 相同输入 → 相同输出（无随机性依赖） |

### 5.4 回归测试（零破坏验证）

| 测试 | 验证内容 |
|------|---------|
| `test_baseline_unchanged` | `BaselineStrategy.solve()` 在相同数据集上输出与 master 分支一致 |
| `test_kbeam_unchanged` | KBeamStrategy 输出不变 |
| `test_iterative_unchanged` | IterativeStrategy 输出不变 |
| `test_exhaust_mfg_default_unchanged` | 不传 `precomputed_support` 时 exhaust_mfg 行为与旧版一致 |
| `test_exhaust_trade_default_unchanged` | 同上 |
| `test_protected_modules_untouched` | `git diff master --stat` 对 §1.1 清单中所有文件为空 |
| `test_slot_iteration_no_solver_import` | ast 解析 `slot_iteration.py`，验证无 `solver` 导入 |
| `test_no_wildcard_imports` | `ruff check --select F403` 全项目通过 |

### 5.5 测试数据集

回归和集成测试使用以下数据集（需预先准备或从已有测试复用）：

| 数据集 | 说明 |
|--------|------|
| 全 box 满练度 | 模拟最优场景 |
| 中练度混合 | 部分关键干员缺失 |
| 低练度 | 仅基础干员，无联动体系 |
| 特定联动体系 | 仅含 perception 链干员 |
| 特定联动体系 | 仅含 yanhuo 链干员 |
| 全联动体系 | perception + yanhuo + 机器人 + 料理 + 共鸣 全覆盖 |

---

## 6. 验收标准

### 6.1 第一期验收门禁

| # | 标准 | 度量方式 |
|:--:|------|---------|
| A1 | 不可修改模块清单（§1.1）中所有文件的 `git diff master --stat` 为空 | CI 检查 |
| A2 | `test_regression.py` 全部通过 | pytest |
| A3 | `test_pure_functions.py` 全部通过 | pytest |
| A4 | `test_strategy.py` 全部通过 | pytest |
| A5 | P_slot ≥ P_baseline 在全部数据集上成立 | 测试断言 |
| A6 | 无新增 `import *`、无循环导入 | ruff / 人工审查 |
| A7 | `slot_iteration.py` 不导入 `solver/` 下任何模块 | ruff check + 人工审查 |
| A8 | `IterationContext` 为 `frozen=True` | 代码审查 |

### 6.2 第二期验收门禁

| # | 标准 |
|:--:|------|
| B1 | λ bisection 在所有数据集上收敛（不振荡） |
| B2 | 联合扰动在至少 1 个数据集上提升 P |
| B3 | S₀_max 冷启动可独立完成求解（不依赖 BaselineStrategy） |
| B4 | 心情展平输出与 §7 公式一致 |
| B5 | 多启动取 max ≥ 单热启动 |

---

## 7. 不在范围内的

- 槽位 ID 体系（Phase A/B 保留房间级穷举）
- `fill_control.py` / `fill_remaining.py` / `fill_dorm.py` 的任何修改
- K 扩展（K=3 保持基线）
- 耦合子空间穷举（理论备份已在建模草案登记）
- CP-SAT 全局验证
- 剪枝策略
- `evaluate.py` / `models.py` / `strategy.py` 的任何修改
