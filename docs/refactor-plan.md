# 重构方案

> **版本**: 2026-05-27 · v0.2.0 MVP 后

## 背景

MVP（v0.2.0）完成后，`steward_core/` 整体 3612 行、11 个文件，结构清晰但存在两个明确的维护热点：

| 模块 | 行数 | 占比 | 近 30 commit 修改次数 |
|------|------|------|----------------------|
| synergy.py | 1307 | 36% | 16 次 |
| solver.py | 653 | 18% | 10 次 |
| 其余 9 个文件 | 1652 | 46% | 零星 |

synergy.py 内含 **24 张硬编码数据结构**（含表、集合、常量），其中 10 张使用匿名异构元组；solver.py 的 `solve_mvp()` 为 240 行单体函数，内联全部 5 个 Phase。

**目标**：在进入 MV5 多班次开发前，将两个热点文件拆分为可独立理解与测试的子包，同时将硬编码表从匿名元组升级为带语义的 NamedTuple。

## 重构范围

分五个 Phase：

```
Phase 0: A_{DESC} 命名（消去 A1/C3 等不透明代号）
    │
Phase 1: NamedTuple 类型化 + TABLES 注册器（synergy.py 内部）
    │
Phase 2: 拆分 synergy.py → steward_core/synergy/ 子包
    │
Phase 3: 拆分 solver.py → steward_core/solver/ 子包
    │
Phase 4: 横向重构 _greedy_remaining
```

---

## Phase 0：A_{DESC} 命名 — 消除不透明代号

### 问题

synergy.py 中 16 个联动体系使用 A1/A2/.../B1/.../C2 数字代号作为变量名和注释前缀（约 120 行），agent 需要查表（`docs/synergy-systems.md`）才能理解含义：

```python
_A1_PAIR_TABLE         # A1 是什么？
_A3_COUNTER_TABLE      # A3 是什么？counter 是"计数器"还是"计数"？
_B5_EBNHLZ = "黑键"    # EBNHLZ 完全不可推断
```

### 方案

保留 `A_/B_/C_` 前缀（承载"同设施/跨设施/中枢全局"的层次语义），将数字替换为描述性英文词：

| 当前 | 改为 | 语义 |
|------|------|------|
| `_A1_PAIR_TABLE` | `_A_PAIR_TABLE` | A层·干员配对 |
| `_A2_FACTION_TABLE` | `_A_ROOM_FACTION_TABLE` | A层·同房阵营计数 |
| `_A2_EXTRA_TABLE` | `_A_ROOM_FACTION_EXTRA` | A层·同房阵营额外加成 |
| `_A3_COUNTER_TABLE` | `_A_SKILL_COUNT_TABLE` | A层·技能计数锚点 |
| `_A3_BONUS_PER` | `_A_SKILL_COUNT_BONUS` | A层·技能计数每人加成 |
| `_A5_AUTO_FALLBACK` | `_A_AUTOMATION_FALLBACK` | A层·自动化回退值 |
| `_A6_FACILITY_TABLE` | `_A_FACILITY_LINK_TABLE` | A层·设施数量联动 |
| `_B_LAYER_CONSUMER_TABLE` | `_B_BUFF_CONSUMER_TABLE` | B层·buff点消费者 |
| `_B3_ROSEMARY` | `_B_ROSEMARY` | B层·迷迭香常量 |
| `_B5_EBNHLZ` | `_B_EBENHOLZ` | B层·黑键常量 |
| `_B6_GLOBAL_TABLE` | `_B_GLOBAL_FACTION_TABLE` | B层·全局阵营计数 |
| `_B7_CROSS_PAIR_TABLE` | `_B_CROSS_ROOM_PAIR_TABLE` | B层·跨房间配对 |
| `_C1_GLOBAL_TABLE` | `_C_CONTROL_GLOBAL_TABLE` | C层·中枢全局效率 |

函数名（`synergy_pair`、`synergy_whisper` 等）已自描述，不动。

分节注释同步简化：

```python
# Before
# ─── A3 技能类型计数 ───
# ─── A5b 低语（秩序低语/归零反馈型）───

# After
# ─── A·技能计数 ───
# ─── A·低语（巫恋·归零反馈）───
```

### synergy.py 模块 docstring 更新

当前 docstring 仍标注"A2/A7/B 层在后续迭代补充"（已过时），替换为完整体系概览：

```python
"""联动体系函数

A层（同设施内联动）:
  PAIR          — 干员配对（阿兰娜↔温米 等）
  ROOM_FACTION  — 同房阵营计数（摩根/新约能天使 等）
  SKILL_COUNT   — 技能类型计数（水月/多萝西/苍苔）
  SKILL_ALIAS   — 技能别名（海沫·意识兼容）
  AUTOMATION    — 自动化（森蚺/温蒂/异客 等）
  WHISPER       — 巫恋·低语（归零反馈型）
  FACILITY_LINK — 设施数量联动（清流/空弦/伺夜 等）
  ORDER         — 订单压缩（孑）

B层（跨设施 buff 消费链）:
  BUFF_POOL     — 感知信息/烟火/巫术结晶/机器人/思维链环/魔物料理/无声共鸣
  GLOBAL_FACTION — 全局阵营计数（缪尔赛思/杏仁/娜斯提）
  CROSS_ROOM    — 跨房间配对（烈夏↔古米 等）

C层（中枢全局）:
  CONTROL_GLOBAL — 中枢全局效率（凯尔希/望/布丁 等）
  MOOD_BURN      — 中枢心情恢复（重岳·孤光共照）

每个体系一个独立函数，同层并行计算后线性叠加。
"""
```

### 可行性

- 每个代号 1:1 对应一个独特体系，去数字后无命名冲突
- A2 同房阵营 vs B6 全局阵营 → `_A_ROOM_FACTION_*` vs `_B_GLOBAL_FACTION_*` 通过前缀区分
- A1 配对 vs B7 跨房配对 → `_A_PAIR_*` vs `_B_CROSS_ROOM_PAIR_*` 通过前缀区分

### 影响

- 文件：`synergy.py`（14 变量 + 注释）、`evaluate.py`（3 处）、`solver.py`（4 处）、`production.py`（2 处）
- 测试：`test_synergy.py`（~15 处 import/引用）
- 改动量：约 60 行，纯改名，零逻辑变化

---

## Phase 1：NamedTuple 类型化 + TABLES 注册器

### 问题

synergy.py 中 10 张异构表使用匿名 `tuple` 作为值类型，agent 无法从类型签名理解字段含义，必须跳转到消费函数看解包赋值。

```python
# 匿名 tuple：agent 只能看到裸类型
_A6_FACILITY_TABLE: dict[str, tuple[str, float, str, str | None, float | None]] = {
    "清流": ("trade_count", 20.0, "Mfg", "PureGold", None),
```

### 方案

每张异构表定义一个 `NamedTuple` 子类，字段名即文档：

```python
class FacilityLinkEntry(NamedTuple):
    """A6 设施数量联动条目"""
    count_source: str           # "trade_count"|"dorm_levels"|"meeting_level"|"mfg_recipe_types"|"train_level"
    bonus_per_unit: float       # 每单位加成%
    target_room: str            # 生效设施
    target_product: str | None  # 生效产物，None=通用
    cap: float | None           # 上限，None=无上限

_A6_FACILITY_TABLE: dict[str, FacilityLinkEntry] = {
    "清流": FacilityLinkEntry("trade_count", 20.0, "Mfg", "PureGold", None),
```

同时在 synergy.py 顶部增加 `TABLES` 注册器，提供全部 24 张表的统一索引：

```python
TABLES: dict[str, TableMeta] = {
    "A1-配对":         TableMeta(_A1_PAIR_TABLE,         ["synergy_pair"],               "新增配对型联动 buff"),
    "A2-阵营计数":     TableMeta(_A2_FACTION_TABLE,      ["synergy_faction_room", "get_synergy_enablers"], "新增同房阵营计数型 buff"),
    "A3-技能计数":     TableMeta(_A3_COUNTER_TABLE,      ["synergy_skill_count"],         "新增技能计数锚点"),
    "A6-设施联动":     TableMeta(_A6_FACILITY_TABLE,     ["synergy_facility_count"],      "新增设施数量联动 buff"),
    "C1-全局效率":     TableMeta(_C1_GLOBAL_TABLE,       ["compute_control_global_bonus"],"新增中枢全局 buff"),
    # ...
}
```

### 需要定义的 NamedTuple

| NamedTuple | 替代的表 | 字段数 |
|-----------|---------|--------|
| `PairKey` | `_A1_PAIR_TABLE` 的 key | 3 |
| `FacilityLinkEntry` | `_A6_FACILITY_TABLE` | 5 |
| `BuffConsumerEntry` | `_B_LAYER_CONSUMER_TABLE` | 4 |
| `FactionEntry` | `_A2_FACTION_TABLE` | 5 |
| `ExtraFactionEntry` | `_A2_EXTRA_TABLE` | 4 |
| `GlobalFactionEntry` | `_B6_GLOBAL_TABLE` | 7 |
| `CrossPairEntry` | `_B7_CROSS_PAIR_TABLE` | 4 |
| `ZeroingVariantEntry` | `_ZEROING_VARIANT_TABLE` | 3 |
| `RampingSkillEntry` | `_RAMPING_SKILL_TABLE` | 3 |
| `GlobalBonusEntry` | `_C1_GLOBAL_TABLE` | 2 |
| `TableMeta` | TABLES 注册器 | 3 |

### 名称集合标准化注释

所有 `set[str]` 类型的名称集合添加标准注释块：

```python
# 【硬编码集合】_KNIGHT_NAMES — 骑士标签安全网补全
# 推导规则: nation_id == "kazimierz" OR group_id == "pinus"
# 补全原因: 部分骑士干员无法通过以上规则推导
# 上次同步: 2026-05
# 触发更新: 新增卡西米尔骑士但不属于 kazimierz 势力/pinus 组织
_KNIGHT_NAMES: set[str] = {"砾", "野鬃", "白金", ...}
```

### 影响

- 文件：`steward_core/synergy.py`
- 改动量：约 190 行
- 新增依赖：无（`NamedTuple` 来自 `typing`，标准库）
- 消费函数适配：`t[0]` → `entry.count_source` 等属性访问

---

## Phase 2：拆分 synergy.py → 子包

### 目标结构

```
steward_core/synergy/
├── __init__.py           # 重导出全部公开符号
├── types.py              # 所有 NamedTuple 定义 + TableMeta + TABLES 注册器
├── registry.py           # SystemContributor + get_system_contributors
├── mfg_linkages.py       # A1/A2同房/A3/A4/A5/A5b/归零变体/容量/放大器/机械精通/爬升
├── trade_linkages.py     # A7 孑订单 + 鸿雪宣发
├── facility_linkages.py  # A6 设施数量联动 + 发电站计数
├── control_linkages.py   # C1 中枢全局加成 + per-operator 条件加成
├── global_linkages.py    # B6 全局阵营 + B7 跨房间配对
├── buff_pool.py          # BuffPool + compute_buff_pool + B1-B5 消费
├── classification.py     # Mfg/Trade 干员分类 + 剪枝 + 候选池
├── helpers.py            # _is_knight/_is_glasgow/名称集合/常量
└── mood.py               # compute_global_burn（从当前 synergy.py 移入）
```

### 文件行数预估

| 文件 | 预估行数 | 来源 |
|------|----------|------|
| `__init__.py` | ~50 | 重导出 |
| `types.py` | ~120 | NamedTuple + TableMeta + TABLES |
| `registry.py` | ~70 | SystemContributor 相关 |
| `mfg_linkages.py` | ~400 | A1-A5 + 归零变体等 Mfg 专属 |
| `trade_linkages.py` | ~170 | A7 + 鸿雪 |
| `facility_linkages.py` | ~120 | A6 + power count |
| `control_linkages.py` | ~120 | C1 |
| `global_linkages.py` | ~120 | B6 + B7 |
| `buff_pool.py` | ~200 | BuffPool + 计算 + 消费 |
| `classification.py` | ~120 | 分类 + 剪枝 |
| `helpers.py` | ~50 | 工具函数 + 常量 |
| `mood.py` | ~30 | compute_global_burn |

### 兼容性保证

`__init__.py` 重导出所有公开 API，外部引用零改动：

```python
# steward_core/synergy/__init__.py
from steward_core.synergy.registry import SystemContributor, get_system_contributors
from steward_core.synergy.mfg_linkages import synergy_pair, synergy_faction_room, ...
from steward_core.synergy.trade_linkages import synergy_jie_order, synergy_trade_gold_lines
# ...
```

### 内部引用调整

| 旧引用 | 新引用 |
|--------|--------|
| `from steward_core.synergy import synergy_pair` | 不变（通过 `__init__.py`） |
| 内部 `_A1_PAIR_TABLE` 跨函数引用 | `from steward_core.synergy.types import _A1_PAIR_TABLE` |
| `from steward_core.synergy import _is_knight` | `from steward_core.synergy.helpers import _is_knight` |

### 影响

- 文件：`steward_core/synergy.py`（删除）→ `steward_core/synergy/`（新建 11 个文件）
- 测试：`tests/test_synergy.py` → `tests/synergy/` 对应拆分
- 依赖方：`evaluate.py`、`solver.py`、`production.py`——import 路径不变

---

## Phase 3：拆分 solver.py → 子包

### 目标结构

```
steward_core/solver/
├── __init__.py            # solve_mvp() 编排器
├── support.py             # compute_optimal_support + _evaluate_with_support
├── greed.py               # _greedy_allocate + _greedy_allocate_with_support + _greedy_remaining
├── evaluate.py            # _evaluate_trade_combo + _generate_combos + _upper_bound_ok
├── phase1_mfg.py          # Phase 1: 制造站穷举
├── phase2_control.py      # Phase 2: 中枢填充
├── phase3_trade.py        # Phase 3a: 贸易站穷举
├── phase3_remaining.py    # Phase 3b: 剩余设施贪心
└── phase4_dorm.py         # Phase 4: 宿舍填充
```

### 文件行数预估

| 文件 | 预估行数 | 说明 |
|------|----------|------|
| `__init__.py` | ~80 | `solve_mvp()` 五阶段编排 |
| `support.py` | ~120 | 支撑干员计算 |
| `greed.py` | ~150 | 贪心分配逻辑 |
| `evaluate.py` | ~60 | Trade 组合评估 |
| `phase1_mfg.py` | ~80 | 制造站穷举 |
| `phase2_control.py` | ~40 | 中枢填充 |
| `phase3_trade.py` | ~100 | 贸易站穷举 |
| `phase3_remaining.py` | ~60 | 剩余设施 |
| `phase4_dorm.py` | ~40 | 宿舍填充 |

### 关键重构

Phase 1 和 Phase 3a 的穷举逻辑高度相似（Mfg 和 Trade 均使用 C(n,3) 穷举 + 贪心），在拆分为独立文件后抽取共享的 `exhaustive_allocate()` 到 `greed.py`。

### 影响

- 文件：`steward_core/solver.py`（删除）→ `steward_core/solver/`（新建 9 个文件）
- 测试：`tests/test_solver.py` → `tests/solver/` 对应拆分
- 外部引用：`from steward_core import solve_mvp` 不变

---

## Phase 4：横向重构 _greedy_remaining

### 问题

`_greedy_remaining` 单个函数处理 Power/Reception/Office 三种设施，候选池构建中存在跨设施语义泄漏风险——过去已修复过"Trade 干员泄漏到 Power"的 bug。

### 方案

采用 `room_type` 分支的 `get_effective_efficiency` 模式：

```python
def _get_effective_efficiency(op, room_type, product, layout):
    """按设施类型路由到对应的效率计算，替代当前 if-elif-else 链"""
    match room_type:
        case "Power":
            return _power_efficiency(op)
        case "Reception":
            return _reception_efficiency(op, layout)
        case "Office":
            return _office_efficiency(op, layout)
```

这个 Phase 放在最后，等子包拆分稳定后单独进行。

---

## 测试文件独立拆分

以下拆分不与源文件 Phase 绑定——test_production.py 和 test_mood.py 自身已膨胀到有自然边界。

### test_production.py → test_production.py + test_trade_orders.py

| 拆分 | 保留类 | 方法 | 说明 |
|------|--------|------|------|
| `test_production.py` | MfgBaseline + TradeBaseline + GoldSupplyBalance + Drone + EdgeCases | 19 | 制造站/贸易站基线公式 + 无人机 + 赤金供需 |
| `test_trade_orders.py` | TradeOrderMultiplier + TradeEquivalentGold | 13 | A7 订单机制（`_get_trade_order_multiplier()`），依赖精确 buff_id 构造 |

两个分组的构造模式不同——基础产出用简洁的 `_mk_op`，订单机制需要构造 `trade_ord_law`/`trade_ord_closure` 等 buff_id。

### test_mood.py → test_mood.py + test_mood_report.py

| 拆分 | 保留类 | 方法 | 说明 |
|------|--------|------|------|
| `test_mood.py` | ControlBonus + WorkBurn + FaceThresholds + FacilityExclusion | 13 | 心情消耗计算链，共享 `_mk_ctrl_cost` 辅助函数 |
| `test_mood_report.py` | ReportInterface | 5 | 纯数据类接口验证，不调用 `calculate()` |

`TestReportInterface` 完全自包含——直接构造 `MoodReport`/`RoomMood` 对象验证字符串输出。

### 衍生拆分（伴随 Phase 2/3）

`test_synergy.py`（30 类）和 `test_solver.py`（7 类）的拆分是 Phase 2/3 的纯衍生——源文件按体系/Phase 拆，测试文件按同一维度切，无需独立方案。

---

## 顺带清理

以下问题在重构过程中一并修复，不单独开 Phase。

| # | 文件 | 行号 | 问题 | 修复 |
|---|------|------|------|------|
| C1 | `synergy.py` | L4-L5 | 模块 docstring 标注"A2/A7/B 层在后续迭代补充"——已过时 | 替换为 Phase 0 中定义的新 docstring |
| C2 | `synergy.py` | L1055-L1056 | 重复 import——文件尾部再次 `import dataclass as dc_field` 和 `Operator as OpModel` | 合并到文件顶部 L8/L10，消除中段 import |
| C3 | `synergy.py` | L559 | `TODO: Lancet-2 + 森蚺中枢 "我寻思能行"`——确认是否需要实现 | 若暂不实现，标注为已知限制而非 TODO |
| C4 | `synergy.py` | L970 | `TODO: B5 生成待实现`——但 B5 消费者（黑键）和测试（TestB5SilentResonance）已就位 | 确认生成侧状态，更新或移除 TODO |
| C5 | `data_loader.py` | L179-L320 | `load_operators()` v1 死代码——无任何引用，约 140 行 | 安全删除，含配套的 `_legacy_build_efficiency_index` |
| C6 | `test_synergy.py` | L640-L678 | C1 测试错误归属在 `TestBuffPool` 类中（注释自述"旧 C1 测试续"） | Phase 2 拆测试时移入 TestControlGlobalBonus |
| C7 | `test_solver.py` | L513 | 空节标题 `# ─── _greedy_remaining 正确性` 无测试体 | Phase 4 实现时补测试，或拆测试时删除占位 |

---

## 执行顺序与耗时

| 步骤 | 内容 | 预估改动 | 风险 |
|------|------|----------|------|
| 0 | Phase 0: A_{DESC} 变量改名 | ~60 行，5 文件 | 🟢 |
| 1 | Phase 1: NamedTuple + TABLES | ~190 行，1 文件 | 🟢 |
| 2 | C1-C5 顺带清理 | ~160 行删除 + 10 行修正 | 🟢 |
| 3 | Phase 2: 拆分 synergy → 子包 | ~11 新建 + 1 删除 | 🟡 |
| 4 | 拆分 tests/test_synergy.py + C6 | ~1373 行拆分 + 归属修复 | 🟡 |
| 5 | 拆分 tests/test_production.py | ~200 行移出 → test_trade_orders.py | 🟢 |
| 6 | 拆分 tests/test_mood.py | ~50 行移出 → test_mood_report.py | 🟢 |
| 7 | Phase 3: 拆分 solver → 子包 | ~9 新建 + 1 删除 | 🟡 |
| 8 | 拆分 tests/test_solver.py + C7 | ~383 行拆分 + 删除占位 | 🟡 |
| 9 | 全量测试验证 | `python -m pytest tests/ -v` | 🟢 |
| 10 | Phase 4: 横向重构 _greedy_remaining | ~100 行 | 🟡 |

每步完成后运行 `python -m pytest tests/ -v` 确保 250 测试通过。

## 风险缓解

| 风险 | 缓解 |
|------|------|
| import 循环 | Phase 2/3 保持当前依赖拓扑（models → 工具 → synergy → evaluate → solver），`__init__.py` 仅重导出 |
| 合并冲突 | 在 master 上直接创建 `refactor/split` 分支，避免与 dev 并行 |
| 测试遗漏 | 拆分测试文件时保留全部用例逻辑，仅调整 import 路径 |
