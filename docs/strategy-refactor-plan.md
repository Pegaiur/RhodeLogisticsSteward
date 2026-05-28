# Strategy 策略层重构：约束 → 效率模型 → 策略 → 产出

> **版本**: 2026-05-28 · 待实施 · 路由自 `docs/inbox.md#L23`、`#L24`、`#L25`

## 问题诊断

### 1. 策略逻辑嵌在编排函数中

当前 `solve_mvp()` 直接硬编码 Phase 顺序 + 后处理流程。每新增一种求解算法（K-Beam、瓶颈枚举、MILP）都需要新增一个顶层函数或在 `solve_mvp()` 内加 if-else 分支——这正是 [solver-improvement-plan.md](./archive/solver-improvement-plan.md) §远期待办 中警告的"开关膨胀"模式。

### 2. SolverConfig bool 开关达到阈值

`SolverConfig` 已有 3 个 bool 开关（`exclusive_support_check`、`local_search_enabled`、`global_state_scoring`）。K-Beam 需要第 4 个（`beam_width`），触发 inbox L23 的 Strategy 抽象条件。3-way 交互（K-Beam × exclusive_check × global_state）在布尔开关模式下无法表达。

### 3. Phase 间数据流依赖可变状态

所有 Phase 通过 6 个可变参数（`assigned_ids`、`assigned_names`、`assignments`、`locked_support`、`op_lookup`、`config`）传递状态。K-Beam 需要克隆状态以分叉多路径，当前无标准化的状态快照机制。

### 4. 效率模型层无明确 API 边界

`solver/` 模块从 `synergy/` 的 9 个子模块直导入 30+ 符号，没有明确的"策略可调用 API"契约。新策略开发者需要遍历所有 synergy 模块才能理解可用的评估函数。

---

## 目标架构

```
┌──────────────────────────────────────────────────────┐
│ 约束层                                                 │
│ constants.py  │  models.py                           │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│ 效率模型层 （稳定 API）                                  │
│ synergy/ (16 函数)  │  evaluate.py  │  production.py  │
│ efficiency_fn.py     │  mood.py                       │
│                                                       │
│ 公开分组：                                              │
│   干员分类: classify_mfg_operators, classify_trade_   │
│             operators, build_candidate_pool,          │
│             get_synergy_enablers                       │
│   房间评估: evaluate_room()                             │
│   产出计算: production.calculate(),                    │
│             _get_trade_order_multiplier()              │
│   效率函数: constant_efficiency, rank_by_dominance     │
│   全局上下文: compute_control_global_bonus,             │
│              compute_buff_pool, GlobalContext           │
│   支撑计算: compute_optimal_support,                    │
│             compute_trade_support                       │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│ 策略层 （本次重构目标）                                   │
│                                                       │
│ solver/                                               │
│ ├── strategy.py         ← Strategy ABC + PartialSol.  │
│ ├── strategies/                                       │
│ │   ├── baseline.py     ← BaselineStrategy (当前行为)   │
│ │   └── kbeam.py        ← KBeamStrategy (后续)         │
│ ├── config.py           ← 简化: strategy + params      │
│ │                                                     │
│ └── (不改) phase*.py / greed.py / support.py / ...    │
│           ↑                                           │
│           └── "积木"：策略组合，不改签名                   │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│ 结果产出                                               │
│ output.py (MAA 基建排班协议 JSON)                       │
└──────────────────────────────────────────────────────┘
```

**核心设计原则**：
- **Phase 是积木，Strategy 是图纸**——Phase 模块签名和行为完全不变，Strategy 子类决定如何编排它们
- **策略之间零耦合**——一个策略的实现变更不影响其他策略
- **效率模型不变**——`synergy/`、`evaluate.py`、`production.py` 本次重构零改动

---

## 实施步骤

### Step 0: Strategy 抽象层 + PartialSolution

**文件变更**:

| 文件 | 操作 | 说明 |
|------|:---:|------|
| `solver/strategy.py` | **新建** | `Strategy` ABC + `PartialSolution` 数据类 |
| `solver/strategies/__init__.py` | **新建** | 重导出 |
| `solver/strategies/baseline.py` | **新建** | `BaselineStrategy`——从 `solve_mvp()` body 搬迁 |
| `solver/__init__.py` | **修改** | `solve_mvp()` → 策略委托的薄封装 |
| `solver/config.py` | **修改** | 新增 `strategy: Strategy` 字段 |

**不改动的文件**: 所有 `phase*.py`、`greed.py`、`support.py`、`refine.py`、`pipeline.py`、`context.py`、`params.py`、`global_state.py`、`bundle.py`

#### `solver/strategy.py` — Strategy ABC + PartialSolution（~60 行）

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from steward_core.models import Operator, SolveResult
    from .config import SolverConfig


@dataclass
class PartialSolution:
    """排班求解过程中的状态快照——可在 Phase 间传递和克隆"""

    assigned_ids: set[str] = field(default_factory=set)
    assigned_names: set[str] = field(default_factory=set)
    assignments: list = field(default_factory=list)
    locked_support: dict[str, set[str]] = field(default_factory=dict)

    def clone(self) -> "PartialSolution":
        """深拷贝当前状态，供 K-Beam 等多路径策略分叉使用"""
        return PartialSolution(
            assigned_ids=set(self.assigned_ids),
            assigned_names=set(self.assigned_names),
            assignments=list(self.assignments),
            locked_support={k: set(v) for k, v in self.locked_support.items()},
        )

    @classmethod
    def empty(cls) -> "PartialSolution":
        """创建带默认 locked_support 键的空状态"""
        return cls(locked_support={
            "Control": set(), "Trade": set(),
            "Dormitory": set(), "Office": set(),
        })


class Strategy(ABC):
    """求解策略基类

    每个子类实现 execute() 定义自己的排班求解流程。
    策略之间互相独立——一个策略的实现变更不影响其他策略。

    子类应通过 PartialSolution 管理状态快照，
    通过效率模型层的公开 API 进行评估和分类。
    """

    name: str = "abstract"

    @abstractmethod
    def execute(
        self,
        operators: list["Operator"],
        config: "SolverConfig",
        op_lookup: dict[str, "Operator"],
    ) -> "SolveResult":
        """执行排班求解

        Args:
            operators: 全量干员列表
            config: 求解器配置（含 params 和 strategy 自身引用）
            op_lookup: {name → Operator} 查找表（由 solve_mvp 预构建）

        Returns:
            完整的 SolveResult，含至少一个 ShiftPlan
        """
        ...
```

#### `solver/strategies/baseline.py` — BaselineStrategy（~70 行）

```python
"""基线策略：Phase 贪心 + C(n,3) 穷举 + 局部搜索

等价于当前 solve_mvp() 的完整逻辑，纯搬迁，零行为变更。
"""

from steward_core.models import Operator, ShiftPlan, SolveResult

from ..config import SolverConfig
from ..pipeline import Pipeline
from ..refine import local_search_refine
from ..strategy import PartialSolution, Strategy


class BaselineStrategy(Strategy):
    """当前生产行为——Phase 贪心 + 穷举 + 局部搜索"""

    name = "baseline"

    def execute(
        self,
        operators: list[Operator],
        config: SolverConfig,
        op_lookup: dict[str, Operator],
    ) -> SolveResult:
        params = config.params

        state = PartialSolution.empty()

        pipeline = Pipeline.default()
        autofill_count = pipeline.run(
            operators, config,
            state.assigned_ids, state.assigned_names, state.assignments,
            op_lookup, state.locked_support,
        )

        half_hours = int(params.shift_hours / 2.0)
        plan = ShiftPlan(
            name=f"MVP-{int(params.shift_hours)}h",
            assignments=state.assignments,
            period_from=f"{half_hours:02d}:00",
            period_to=f"{half_hours + int(params.shift_hours) - 1:02d}:59",
        )
        result = SolveResult(
            plans=[plan],
            autofill_count=autofill_count,
            config_used=config,
        )
        result = local_search_refine(result, operators, config)
        return result
```

#### `solver/__init__.py` — solve_mvp 瘦身（~30 行 → ~20 行）

```python
from steward_core.models import Operator, ShiftPlan, SolveResult

from .config import SolverConfig
from .greed import _greedy_allocate, _generate_combos, _upper_bound_ok, _evaluate_trade_combo
from .pipeline import Pipeline
from .refine import local_search_refine
from .strategies import BaselineStrategy


def solve_mvp(
    operators: list[Operator],
    config: SolverConfig | None = None,
    pipeline: Pipeline | None = None,
) -> SolveResult:
    """MVP 完整求解——委托给 config.strategy 执行

    不传 strategy 时使用 BaselineStrategy（等价于当前生产行为）。
    通过 SolverConfig.strategy 注入自定义策略进行 A/B 测试。
    """
    if config is None:
        config = SolverConfig()
    if config.strategy is None:
        config.strategy = BaselineStrategy()

    op_lookup = {op.name: op for op in operators}
    return config.strategy.execute(operators, config, op_lookup)
```

#### `solver/config.py` — 新增 strategy 字段（+5 行）

```python
@dataclass
class SolverConfig:
    """求解器配置——功能开关 + 策略选择 + 可调参数"""

    # 策略选择
    strategy: "Strategy | None" = None
    """求解策略——None 时 solve_mvp() 自动使用 BaselineStrategy"""

    # 功能开关（保持向后兼容——逐步向 Strategy 属性迁移）
    exclusive_support_check: bool = False
    local_search_enabled: bool = False
    global_state_scoring: bool = False

    # 可调参数
    params: SolverParams = field(default_factory=SolverParams)

    # baseline / all_on / with_params / diff 方法保持不变
```

**验证**:

```powershell
python -m pytest tests/ -v
```

`BaselineStrategy.execute()` 的 body 与当前 `solve_mvp()` 一字不差。所有现有测试必须不加修改直接通过。

**Pivot**: 无。此步骤纯结构重构，不改变任何行为。

---

### Step 1: Pipeline 状态适配层（顺带优化）

**文件变更**:

| 文件 | 操作 | 说明 |
|------|:---:|------|
| `solver/pipeline.py` | **修改** | 新增 `run_on_state()` 方法——接受 PartialSolution 而非 6 个分散参数 |

**动机**: 当前 `Pipeline.run()` 接受 7 个参数（含 operators + config + 6 个可变状态参数）。`run_on_state()` 接受 `(operators, config, state: PartialSolution, op_lookup)` 作为语法糖，内部将 `state` 解包后调用 Phases，完成后将状态写回 `state`。

```python
class Pipeline:
    """... 已有文档 ..."""

    def run_on_state(
        self,
        operators: list,
        config: "SolverConfig | None",
        state: PartialSolution,
        op_lookup: dict[str, "Operator"],
    ) -> int:
        """等价于 run()，但接受 PartialSolution 作为状态载体

        用于 Strategy 子类——比手动解包 6 个参数更清晰。
        """
        return self.run(
            operators, config,
            state.assigned_ids, state.assigned_names, state.assignments,
            op_lookup, state.locked_support,
        )
```

**验证**: `Pipeline.default().run_on_state()` 与 `Pipeline.default().run()` 在相同输入下输出完全一致。

**Pivot**: 极低风险——纯语法糖，不改变 Pipeline 或 Phase 的任何逻辑。

---

### Step 2: GlobalContext 公共构造提取（顺带优化）

**文件变更**:

| 文件 | 操作 | 说明 |
|------|:---:|------|
| `solver/context.py` | **修改** | 提取 `_compute_buff_pool_kwargs()` 和 `_compute_effective_power()` 两个私有辅助函数 |

**动机**: `from_estimated()` 和 `from_plan()` 中存在 ~40 行的重复逻辑——`compute_buff_pool()` 的布尔参数推断和 `effective_power` 的 Lancet-2 检查。提取为两个私有函数后，`from_estimated` 和 `from_plan` 各减少 ~15 行，且新策略（如 K-Beam）构造 GlobalContext 时可复用这些辅助函数。

**不改动公开接口**: `from_estimated()` 和 `from_plan()` 签名和返回值完全不变。

**验证**: 现有依赖 `GlobalContext.from_estimated()` / `from_plan()` 的代码行为不变。

**Pivot**: 极低风险——纯内部重构。

---

### Step 2.5: SolverConfig 开关迁移方案（设计先行）

此为**设计产物**而非代码改动。在 SolverConfig 开关从 `SolverConfig` 迁移到 `Strategy` 属性之前，先文档化迁移路径，确保每一位开发者理解：

| 开关 | 当前位置 | 迁移目标 | 迁移时机 |
|------|---------|---------|---------|
| `exclusive_support_check` | `SolverConfig` bool | `BaselineStrategy.__init__`（默认 True） | K-Beam 落地后 |
| `local_search_enabled` | `SolverConfig` bool | `BaselineStrategy.__init__`（默认 True） | K-Beam 落地后 |
| `global_state_scoring` | `SolverConfig` bool | `BaselineStrategy.__init__`（默认 True） | K-Beam 落地后 |
| `beam_width`（新增） | — | `KBeamStrategy.__init__` | K-Beam 实现时 |
| `params` | `SolverConfig.params` | 保留在 `SolverConfig`——所有策略共享 | 永久 |

迁移后 `SolverConfig` 退化为：

```python
@dataclass
class SolverConfig:
    strategy: Strategy = field(default_factory=BaselineStrategy)
    params: SolverParams = field(default_factory=SolverParams)
```

**为什么现在不迁移**：当前代码中 `_greedy_allocate_with_support`、`_phase1_mfg`、`refine.py` 多处通过 `config.xxx` 读取开关。迁移需要将所有读取点从 `config.xxx` 改为 `strategy.xxx` 或以参数传入。这超出了 Step 0 的"零行为变更"范围。待 K-Beam 落地、开关重要性明确后，再一次性搬移。

---

### Step 3: Strategy 测试助手

**新建文件**: `tests/strategy_helpers.py`（~50 行）

#### 设计目标

降低新 Strategy 的测试编写成本。当前测试文件各自独立构造 `Operator` 对象，存在大量重复的样板代码。

#### API 设计

```python
"""策略测试辅助工具

降低新 Strategy 的测试编写成本，避免每个测试文件重复构造 Operator 和验证排班结构。
"""

from steward_core.models import Operator, Skill, SolveResult


def make_op(
    name: str,
    char_id: str,
    room_type: str,
    efficiency: float = 0.0,
    product: str | None = None,
    buff_id: str = "",
    rarity: int = 5,
    phase: str = "PHASE_2",
    nation_id: str = "test",
    group_id: str = "test",
) -> Operator:
    """快速构造测试用 Operator

    常用场景：
      make_op("温蒂", "wendy", "Mfg", buff_id="manu_prod_spd&power[020]")
        → 自动化干员，效率来自 buff 表查询

      make_op("普通制造", "mfg_001", "Mfg", efficiency=25.0, product="PureGold")
        → 纯效率干员，25% 贵金属加成

      make_op("无技能", "empty_001", "Mfg")
        → 无技能干员，仅用于填位
    """
    ...


def assert_plan_structure(result: SolveResult, expected: dict[str, int]):
    """验证 SolveResult 的房间结构

    expected: {"Mfg": 4, "Trade": 2, "Control": 1, "Power": 3, ...}
    """
    ...


def assert_operator_in_room(result: SolveResult, room_type: str, name: str):
    """验证某干员被分配到指定房间类型"""
    ...


def assert_no_duplicate_operators(result: SolveResult):
    """验证全方案无重复干员（H2 约束）"""
    ...


def strategy_runner(strategy_class, operators, **strategy_kwargs):
    """一键跑策略：构造 SolverConfig → 执行 → 返回 SolveResult

    消除每个测试中重复的 solve_mvp 样板代码。
    """
    ...
```

#### 使用示例（K-Beam 测试）

```python
from tests.strategy_helpers import make_op, assert_plan_structure, strategy_runner
from steward_core.solver.strategies.kbeam import KBeamStrategy


def test_kbeam_produces_valid_plan():
    ops = [
        make_op("温蒂", "wendy", "Mfg", buff_id="manu_prod_spd&power[020]"),
        make_op("清流", "qingliu", "Mfg", buff_id="manu_prod_spd&trade[000]"),
        make_op("德克萨斯", "texas", "Trade", buff_id="trade_ord_spd&limit[022]"),
        # ... 更多测试干员
    ]
    result = strategy_runner(KBeamStrategy, ops, beam_width=3)
    assert_plan_structure(result, {"Mfg": 4, "Trade": 2, "Control": 1, "Power": 3,
                                    "Reception": 1, "Office": 1, "Dormitory": 4})
    assert_no_duplicate_operators(result)
```

#### 实施时机

Step 0 完成后、K-Beam 开发前。K-Beam 的测试直接依赖此模块。

---

### Step 4: K-Beam Strategy（详细设计）

#### 4.1 算法定位

K-Beam 是 Phase 1（Mfg 穷举）的**分配层升级**——将唯一的贪心分配替换为 top-K 保留，其余 Phase（2-5）逻辑完全不变。

```
BaselineStrategy:
  Phase 1: 穷举 → 贪心取 1-best → Phase 2-5

KBeamStrategy:
  Phase 1: 穷举 → 贪心取 K-best → K 条路径
  For each path:
    Phase 2-3a: 中枢填充 + 贸易站穷举 → 完整排班
  择优（production.calculate）
  优胜路径: Phase 3b-4 → 最终方案
```

**不改动任何 Phase 模块**。K-Beam 是纯编排层逻辑。

#### 4.2 路径定义

```
一条 "Mfg 路径" = (CR 2间 + PG 2间) 的分配方案 + 对应支撑干员

路径快照 = PartialSolution 包含:
  assigned_ids    = CR 6人 + PG 6人 + 支撑干员
  assignments     = [RoomAssignment×4] (Mfg)
  locked_support  = 所有 4 间 Mfg 需要的支撑（Control/Trade/Dormitory/Office）
```

K=5 时，Phase 1 产出 5 个 `PartialSolution`，每个有不同的 Mfg 分配。

#### 4.3 核心算法：top-K 贪心分配

当前 `_greedy_allocate_with_support` 扫描排序后的 evaluated 列表，贪心取第一个完整分配。K-Beam 扩展为 **迭代排斥法**：

```python
def _greedy_allocate_top_k(
    evaluated: list[tuple[float, list[str], list[str], dict]],
    room_count: int,
    k: int,
    **kwargs,
) -> list[list[tuple[list[str], dict]]]:
    """迭代排斥：每次运行贪心，排除上一次的首选组合，生成 K 条不同路径"""
    results = []
    used_combo_sets: list[frozenset[tuple]] = []

    for _ in range(k):
        result = _greedy_allocate_with_support_excluding(
            evaluated, room_count,
            exclude_sets=used_combo_sets,
            **kwargs,
        )
        if not result:
            break
        results.append(result)
        used_combo_sets.append(
            frozenset(tuple(names) for names, _ in result)
        )

    return results
```

**关键设计决策**：排斥完整的 combo 集合而非单个 combo——确保 K 条路径在至少一间 Mfg 房间上不同。

#### 4.4 路径多样性保证

迭代排斥法的问题：如果前 K 条路径都选了高分 combo A（因为 A 确实是最优的），排斥整个集合会导致路径 2 完全放弃 A，可能大幅劣于路径 1。这在实际场景中是可接受的——我们需要的正是"如果不选 A，什么样的替代方案最好？"。

K=5 时可能的路径形态：
```
路径 1: CR{迷迭香+t0+t1} + CR{水月+t2+t3} + PG{森蚺+温蒂+t4} + PG{...
路径 2: CR{迷迭香+t0+t1} + CR{杏仁+t2+t3} + PG{森蚺+温蒂+t4} + PG{...  ← 第二间CR不同
路径 3: CR{水月+t0+t1} + CR{杏仁+t2+t3} + PG{清流+t4+t5} + PG{...      ← 全部不同
...
```

#### 4.5 跨产物分配（CR 2间 → PG 2间）

当前 `_phase1_mfg` 先跑 CR 再跑 PG，PG 看到 CR 已占用的干员。K-Beam 需要：

```
Phase 1 K-Beam 编排:
  1. CR: 评估全部 CR combo → 贪心取 K 条 CR 路径
     → K 个 PartialSolution (仅含 CR 2间 + 支撑)
  
  2. For each CR 路径:
     PG: 评估 PG combo（排除 CR 路径已占用的干员）
       → 贪心取 1 条 PG 分配（此时 PG 不需要 K 条——CR 才是分叉点）
     → 合并为完整 Mfg 路径（CR + PG + 支撑）
  
  3. 得到 K 条 Mfg 路径，每条含 4 间 Mfg
```

**为什么 PG 不也做 K 条？** 因为 CR 的分叉已经覆盖了主要的跨产品冲突（如黑键同时被 CR 迷迭香体系和 PG 某体系需要）。PG 再分叉会导致 K² 爆炸且增量收益有限。

#### 4.6 路径评估与择优

每条 Mfg 路径在 Phase 2-3a 后得到完整方案（Mfg + Control + Trade）。择优使用 `_production_score()`——与 `local_search_refine` 相同的真实经济产出目标函数：

```python
def _select_best_path(paths, operators, params):
    """从 K 条路径中选真实经济产出最高的"""
    best_path = None
    best_score = -float("inf")
    for path in paths:
        plan = ShiftPlan(assignments=path.assignments, ...)
        score = _production_score(plan, operators, params)
        if score > best_score:
            best_score = score
            best_path = path
    return best_path
```

**为什么不用 evaluate_room 积分排序？** 因为 Trade 的订单机制（孑/但书/可露希尔）将效率积分非线性转换为 LMD 产出，`production.calculate()` 是唯一能准确比较两条路径产出的函数。

#### 4.7 KBeamStrategy 完整流程

```python
class KBeamStrategy(Strategy):
    name = "kbeam"
    beam_width: int = 5

    def execute(self, operators, config, op_lookup):
        params = config.params
        anchor_names = ...  # from synergy (same as Pipeline.default)

        # ── Phase 1: 制造站 K-Beam 展开 ──
        mfg_paths = self._phase1_kbeam(
            operators, config, op_lookup, anchor_names, K=self.beam_width
        )
        # mfg_paths: list[PartialSolution], 每个含 4 间 Mfg + 支撑

        # ── Phase 2-3a: 每条路径上填充中枢 + 贸易站 ──
        for path in mfg_paths:
            self._phase2_control_on_path(operators, config, op_lookup, path)
            self._phase3_trade_on_path(operators, config, op_lookup, path)

        # ── 择优 ──
        best = _select_best_path(mfg_paths, operators, params)

        # ── Phase 3b-4: 在优胜路径上继续 ──
        self._phase3_remaining_on_path(operators, config, op_lookup, best)
        self._phase4_dorm_on_path(operators, config, op_lookup, best)

        # ── 产出 ──
        plan = ShiftPlan(assignments=best.assignments, ...)
        result = SolveResult(plans=[plan], ...)
        result = local_search_refine(result, operators, config)
        return result
```

其中 `_phase1_kbeam` 会调用现有的 `_phase1_mfg` 的核心逻辑，但将 `_greedy_allocate_with_support` 替换为 `_greedy_allocate_top_k`。

#### 4.8 需要修改的文件

| 文件 | 操作 | 说明 |
|------|:---:|------|
| `solver/strategies/kbeam.py` | **新建** | KBeamStrategy，~150 行 |
| `solver/greed.py` | **修改** | 新增 `_greedy_allocate_with_support_excluding()`，~20 行 |
| `solver/strategies/__init__.py` | **修改** | 重导出 KBeamStrategy，+1 行 |
| `tests/strategy_helpers.py` | **新建** | 测试辅助工具，~50 行（Step 3） |
| `tests/test_kbeam.py` | **新建** | K-Beam 单元测试，~60 行 |

**不改动的文件**: 所有 Phase 模块、pipeline.py、support.py、refine.py

#### 4.9 计算复杂度

| 阶段 | Baseline | K-Beam (K=5) | 增幅 |
|------|:---:|:---:|:---:|
| Phase 1: Mfg 穷举 | ~1500 combos × 2 products | 同 Baseline（穷举不变） | ×1 |
| Phase 1: 分配 | 贪心 1 次 | 贪心 K 次（排斥迭代） | ×K |
| Phase 2: Control | 1 次 | K 次 | ×K |
| Phase 3a: Trade 穷举 | ~19600 combos | K × ~19600 ≈ 98000 | ×K |
| Phase 3b-4 | 1 次 | 1 次（仅优胜路径） | ×1 |
| **总计** | ~1s | ~5s | ×5 |

K=5 下约 5 秒——完全可接受。

#### 4.10 风险与缓解

| 风险 | 缓解 |
|------|------|
| K 条路径产出完全相同（排斥迭代收敛太慢） | 打印路径差异诊断日志；必要时换 DFS 回溯 |
| Trade C(n,3) × K 太慢 | 剪枝阈值从 0.95 收紧到 0.90（仅 K-Beam 模式） |
| K 条路径的 Control 都相同（支撑需求一致） | 这是合理的——中枢选人是确定性的；差异在 Mfg 和 Trade |
| 无 K 条不同路径（干员池太小） | 返回实际路径数（可能 < K），日志记录 |

---

## 开发原则

| 原则 | 措施 |
|------|------|
| 每步可独立回退 | 各自独立模块——删除 `strategy.py` 和 `strategies/` 即回退 |
| 任何时候可退回旧行为 | `SolverConfig()` 不设 strategy → 自动使用 BaselineStrategy |
| 现有测试不透改 | Step 0 搬迁 body 一字不改，所有测试直接通过 |
| Phase 积木不改动 | Phase 函数签名、行为完全不变——仅 Strategy 编排方式变化 |
| 效率模型层不动 | `synergy/`、`evaluate.py`、`production.py` 零改动 |

---

## 可顺带优化的架构脆弱点

以下改进与 Strategy 重构同步进行（成本低，不影响主线进度）：

| # | 改进 | 文件 | 动机 | 成本 |
|:---:|------|------|------|:---:|
| 1 | **Pipeline 状态适配层** | `pipeline.py` | 新增 `run_on_state(operators, config, state, op_lookup)`——消除 Phase 调用时手动解包 6 个参数 | ~10 行 |
| 2 | **GlobalContext 去重** | `context.py` | 提取 `_compute_buff_pool_kwargs()` + `_compute_effective_power()`——`from_estimated` 和 `from_plan` 各减 ~15 行 | ~30 行 |
| 3 | **SolverConfig 开关迁移方案** | 设计文档 | 明确开关从 `SolverConfig` → `Strategy` 的迁移路径与时机 | 0 行代码 |
| 4 | **Strategy 测试助手** | `tests/strategy_helpers.py` | `make_op()` + `assert_plan_structure()` 降低新策略测试成本 | ~40 行 |

**不纳入本次的范围**:
- `LayoutConfig` 配置化（inbox L21）——独立重构任务
- `evaluate_room` vs `production.calculate` 统一——两者服务于不同场景（搜索时的快速积分 vs 产出时的精确计算），是合理分工而非重复
- Phase 签名改造（改为接受 PartialSolution）——Phase 模块是"积木"，当前签名已经稳定；通过 `Pipeline.run_on_state()` 的适配层已经足够

---

## 执行状态

| Step | 状态 | 说明 |
|------|:---:|------|
| Step 0: Strategy ABC + PartialSolution | ⬜ 待实施 | 5 文件，~170 行 |
| Step 1: Pipeline 状态适配层 | ⬜ 待实施 | 1 文件，~10 行 |
| Step 2: GlobalContext 去重 | ⬜ 待实施 | 1 文件，~30 行 |
| Step 2.5: 开关迁移方案（设计） | ⬜ 待实施 | 本文档 §Step 2.5 |
| Step 3: 测试助手（设计） | ⬜ 待实施 | 1 文件，~40 行 |
| Step 4: K-Beam Strategy | ⬜ 后续 | 独立实施 |

---

## inbox 条目路由

执行本文档后，以下 inbox 条目更新状态：

| inbox 条目 | 路由 |
|-----------|------|
| L23 Strategy 策略组合器 | → 本文档 Step 0-2.5，实施后标记 `[x]` |
| L24 瓶颈枚举 | → `BottleneckEnumStrategy` 作为 K-Beam 之后的第三个策略，暂留 inbox |
| L25 局部搜索策略化 | → 开关迁移方案（Step 2.5）明确了 `refine_mode` 将作为 Strategy 属性，暂留 inbox |
| L22 B7 跨房间配对 | → K-Beam 的多路径展开使其自然修复，暂留 inbox |

---

## 里程碑索引更新

实施完成后更新 `docs/archive/index.md`:

```
| v0.5.0 | YYYY-MM-DD | Strategy 策略层重构 | Strategy ABC + PartialSolution + Pipeline 适配层 + 顺带优化，奠定约束→效率模型→策略→产出架构 |
```
