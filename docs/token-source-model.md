# TokenSource 统一计数层设计

> **分支**: `feat/token-source` · **基线**: master (v0.6.1) · **版本**: 2026-06-07

## 动机

项目现有 28 张同步表（`steward_core/synergy/types.py` TABLES 注册器），所有联动类基建机制的"计数"逻辑分散在至少 5 种不同写法中：

- `_eval_per_op` — control_linkages.py 逐房间计数
- `synergy_skill_count` — mfg_linkages.py 技能标签计数
- `compute_buff_pool` — buff_pool.py BuffPool 生产者/消费者两遍扫描
- `synergy_global_faction` — global_linkages.py 全局阵营计数
- `compute_cluster_hunting_bonus` — control_linkages.py 站级深海猎人计数

同一本质（"统计符合条件的干员数量"）被反复实现，每次新增干员机制需要在 3-5 个消费点同步更新。历史上产生了 16 次同类模式问题（冷启动死锁、跨模块信息断裂、评分/分类断层）。

**核心假说**：所有计数类联动效果可统一为"Token 生产→Token 消费"模型，将 28 张表的计数逻辑归一为一张 `TokenSource` 描述符表。

## 模型

### TokenSource 定义

```python
@dataclass
class TokenSource:
    token: str                         # token 名
    condition: str = "*"               # 匹配条件（格式见 §条件语法）
    scope: str = "room"                # "room" | "facility" | "global"
    aggregate: str = "count"           # "count" | "efficiency_sum" | "max_efficiency" | "attribute_sum" | "passthrough" | "distinct"
    aggregate_unit: float = 1.0        # 聚合除数
    depends_on: str | None = None      # None | "layout" | "facility" | token_name
    target_room: str | None = None     # depends_on 时的目标设施
    attr: str | None = None            # depends_on="layout" 时的属性名
    exclude_self: bool = False
    partner_facility: str | None = None
    cap: float | None = None           # token 值上限
```

### 条件语法

`condition` 字段使用 `key=value` 格式：

| 格式 | 示例 | 含义 |
|------|------|------|
| `group_id=v` | `group_id=pinus` | 匹配 `character_table.groupId` |
| `nation_id=v` | `nation_id=siracusa` | 匹配 `character_table.nationId` |
| `team_id=v` | `team_id=reserve1` | 匹配 `character_table.teamId` |
| `char_id=v` | `char_id=char_140_white` | 匹配 `character_identity` 键名（精确干员） |
| `is_knight` | `is_knight` | 派生布尔：`nation_id=kazimierz ∨ group_id=pinus ∨ name∈_KNIGHT_NAMES` |
| `pair=A:B` | `pair=char_103_angel:char_140_white` | 二元配对（双方均为 char_id） |
| `skill_class=v` | `skill_class=红松骑士团` | 技能类别标签（`building_data.buff.skill_class`） |
| `count_ge:g=N` | `count_ge:karlan=3` | 阈值条件（N 及以上），g 为 group_id |
| `*` | `*` | 无条件（全体） |

#### 条件解析器

`condition` 字符串在引擎内由 `parse_condition()` 解析为 `(field, value)` 或 `(fn_name,)` 两种形式：

```python
def parse_condition(condition: str) -> tuple[str, str] | tuple[str]:
    """解析条件字符串。
    - "group_id=pinus"  → ("group_id", "pinus")
    - "is_knight"        → ("is_knight",)     # 无值，调用 _FN_CONDITIONS
    - "pair=A:B"         → ("pair", "A:B")     # A、B 均为 char_id
    """
```

#### 匹配规则

| 条件 field | 匹配方式 | 数据来源 |
|-----------|---------|---------|
| `group_id` | `op.has_group(value)` | `character_table.groupId` |
| `nation_id` | `op.has_nation(value)` | `character_table.nationId` |
| `team_id` | `op.has_team(value)` | `character_table.teamId` |
| `char_id` | `op.char_id == value` | `character_identity` 键名 |
| `is_knight` | `_FN_CONDITIONS["is_knight"](op)` | 派生布尔：from nation_id + group_id + 名称集合 |
| `pair` | 成对存在性检查 | 双方 char_id 均需在当前 scope 内 |
| `skill_class` | 技能类别标签匹配 | `building_data.buff.skill_class` |
| `count_ge` | `count_ge:g=N` 形式 | g=group_id，N=阈值整数 |
| `*` | 无条件通过 | — |

派生布尔注册表（`_FN_CONDITIONS: dict[str, Callable]`）：

```python
_FN_CONDITIONS = {
    "is_knight": _is_knight,
}
```

新增派生函数时只需加一行注册。派生函数应尽可能从解包数据字段推导（如 `is_knight` 从 `nation_id + group_id` 推导），仅在游戏标签无法机械提取时使用名称集合兜底（见 AGENTS.md §人工维护数据）。

### 聚合模式

| aggregate | 语义 | 示例 |
|-----------|------|------|
| `count` | 干员计数 | pinus Mfg 人数 |
| `efficiency_sum` | 效率值聚合 ÷ unit | 雪雉 `trade_eff/5` |
| `max_efficiency` | 最高效率值 | 槐琥同房最高 |
| `attribute_sum` | 干员/布局属性聚合 | 泡泡 capacity_bonus, 空弦 dorm_levels |
| `passthrough` | 透传上游 token 值 | `depends_on="perception"` → silent_resonance |
| `distinct` | 去重计数 | 石英 mfg_recipe_types |

### scope 与跨房间

| scope | 含义 | 配合字段 |
|-------|------|---------|
| `room` | 同房间计数 | — |
| `facility` | 同设施类型全站 | `target_room`, `partner_facility` (pair) |
| `global` | 全基建 | — |

### depends_on 与拓扑排序

```python
# cascade: perception → silent_resonance
TokenSource(token="silent_resonance",
            depends_on="perception",
            aggregate="passthrough",
            condition="skill_class=silent_cascade")

# facility: 统计 Trade 设施数
TokenSource(token="trade_rooms",
            depends_on="layout",
            target_room="Trade",
            aggregate="count")

# facility: 统计含 sui 的设施数
TokenSource(token="sui_rooms",
            depends_on="facility",
            condition="group_id=sui",
            aggregate="count")
```

执行引擎按 `depends_on` 做拓扑排序，保证依赖先于被依赖计算。无 `depends_on` 的 token 为第一遍；`depends_on` 指向已计算 token 的为第二遍。

### buff_id → Token 映射

黑键等干员一个 buff_id 同时产出多个 token，需要 1:N 映射：

```python
_BUFF_TO_TOKENS: dict[str, list[str]] = {
    "trade_ord_spd_bd_n1[000]": ["perception", "silent_resonance"],
    "manu_prod_spd_bd_n1[000]": ["perception"],
    ...
}
```

约 40 条映射，替代当前 `_OPERATOR_BUFF_PRODUCERS` 中 `dimension + cascade` 字段组合。

### char_id 迁移策略

TokenSource 是项目从"干员名键"迁移到"char_id 键"的**桥接层**：

**当前状态**：全部 28 张 synergy 表以干员名 (`op.name`) 为键；所有名称集合（`_KNIGHT_NAMES` 等）为 `set[str]`（干员名）；配对表 `_A_PAIR_TABLE` / `_B_CROSS_ROOM_PAIR_TABLE` / `_TRADE_PAIR_TABLE` 均用干员名匹配。

**TokenSource 方向**：
1. `condition="char_id=..."` 使用 char_id 精确匹配（无条件退化问题）
2. `condition="pair=char_id_A:char_id_B"` 双方使用 char_id 配对
3. `group_id` / `nation_id` 条件通过 `op.has_group()` / `op.has_nation()` 间接使用 char_id 无关的语义字段
4. 执行引擎通过 `ctx.find_by_char_id(char_id) → Operator` 解析 char_id 到干员实例
5. 名称集合类条件（`is_knight`）通过 `_FN_CONDITIONS` 注册表封装，内部实现逐步从名称集合迁移到解包数据字段

**不纳入 TokenSource 的部分**：旧 synergy 表的键迁移（11 张干员名键表 + 7 个名称集合 + 心情表）是独立工程，TokenSource 层新建后旧表逐步标记 deprecated，全量迁移作为 Phase E 独立执行。详见实施计划 §Phase E。

## 覆盖范围

### 纳入 TokenSource

| 原表 | 条目数 | 映射方式 |
|------|--------|---------|
| _OPERATOR_BUFF_PRODUCERS | 14 | buff→token 映射 + TokenSource |
| _B_BUFF_CONSUMER_TABLE | 9 | 消费侧，不属计数层 |
| _CONTROL_PER_OP_TABLE | 7 | TokenSource (per-op 计数) |
| _CLUSTER_HUNTING_TABLE | 1 | TokenSource (abyssal 全站计数) |
| _A_ROOM_FACTION_TABLE | 3 | TokenSource (同房阵营计数) |
| _A_SKILL_COUNT_TABLE | 3 | TokenSource (技能标签计数) |
| _FACILITY_GROUP_TABLE | 3 | TokenSource (depends_on="facility") |
| _A_FACILITY_LINK_TABLE | 8 | TokenSource (depends_on="layout") |
| A·配对 (pair) 共 9 条 | 9 | TokenSource (condition="pair"，双方使用 char_id) |
| A·归零 (自动化等) | 6 | TokenSource (count) + 消费侧副作用 |
| A·贸易分享/放大/条件 | 5+2+4 | TokenSource (计数部分) |
| B·全局阵营 | 3 | TokenSource (scope="global") |
| B·跨房间配对 | 3 | TokenSource (condition="pair" + partner_facility，双方使用 char_id) |
| **合计** | **~75** | |

### 不纳入（保留独立函数）

| 机制 | 原因 |
|------|------|
| 爬升 e(t) | 时间函数，非计数 |
| 菲亚梅塔自律 | 固定值 + 隔离，非计数 |
| 冲突互斥 | meta-rule |
| 订单覆盖 | 产出模型替换 |
| 裁缝豁免 | 技能去重规则 |

## 架构定位

```
求解器评估管道:
┌─────────────────────────────────┐
│ 1. 机制守卫层                   │ 归零/覆盖/冲突/互斥
├─────────────────────────────────┤
│ 2. Token 计数层  ← 本模型在此   │ 统一计数 → Token 值
├─────────────────────────────────┤
│ 3. 消费层                       │ 非线性公式、效率放大、订单压缩
├─────────────────────────────────┤
│ 4. 产出层                       │ LMD/经验折算
└─────────────────────────────────┘
```

TokenSource 只负责第二层：将"符合条件的干员数"、"房间效率聚合"、"布局属性提取"统一为 Token 值。消费端的多样性（线性 / floor / 分段 / 归零副作用）保留在各自 consumer 函数中。

## 实施计划

> 符号约定：每个步骤末尾标注 `{Est}` 为估算新增代码行数，`{+N}` 为修改行数。

### Phase A: 原型验证（~365 行）

**目标**：TokenSource 执行引擎可用，10 条注册通过单元测试，与旧函数输出对齐。

| 步骤 | 内容 | 产出文件 | 行数 |
|:---:|------|---------|:---:|
| A1 | 新建 `steward_core/token_source.py`：`TokenSource` dataclass（9 字段）、`ConditionMatcher` Callable 类型别名、`evaluate_tokens(sources, ctx) → dict[str, float]` 拓扑排序执行引擎 | `token_source.py` | ~120 |
| A2 | 实现 `parse_condition(condition_str) → tuple` 条件解析器，覆盖全部 8 种语法（group_id / nation_id / char_id / is_knight / pair / skill_class / count_ge / `*`） | `token_source.py` | ~50 |
| A3 | 向 `SlotContext` 新增 `find_by_char_id(char_id) → Operator | None` 方法；`GlobalContext` 同步新增 | `slot/context.py`, `context.py` | ~15 |
| A4 | 注册 11 条 TokenSource：A 层同房阵营 4（`_A_ROOM_FACTION_TABLE` 映射，含 team_id=reserve1）+ C 层 PerOp 8（`_CONTROL_PER_OP_TABLE` 映射）——作为先行探针验证 `condition=team_id`/`group_id`/`nation_id`/`is_knight`/`count_ge` 五种语法 | `token_source.py` | ~50 |
| A5 | 单元测试：每种 aggregate 模式 ≥1 个测试（count / efficiency_sum / max_efficiency / attribute_sum / passthrough / distinct）+ 拓扑排序依赖正确性 + `*` 无条件通配 | `tests/test_token_source.py` | ~100 |
| A6 | 集成测试：TokenSource 输出与旧函数（`synergy_faction_room` / `_eval_per_op`）的 **全量干员池** 输出逐条对齐 | `tests/test_token_source.py` | ~30 |

**验收条件**：
- [x] `evaluate_tokens()` 是纯函数，零副作用
- [x] 拓扑排序：`depends_on` 引用的 token 一定先于依赖方计算
- [x] 循环依赖检测（`a depends_on b, b depends_on a`）抛出明确异常
- [x] 11 条注册的输出与旧函数输出在 `pytest tests/ -v -k token_source` 下**逐条一致**（允许浮点误差 ±1e-6）
- [x] 不会破坏现有测试（`pytest tests/ -v` 全绿，Phase A 交付时 874 passed）

---

### Phase B: 全量映射（~440 行）

**目标**：~75 条 TokenSource 全部注册，buff_id→token 映射表就绪，条件解析器完善，引擎支持布局/设施依赖。

| 步骤 | 内容 | 产出文件 | 行数 | 状态 |
|:---:|------|---------|:---:|:---:|
| B1 | 补齐 TokenSource 注册：A 层配对 3 + 技能标签 3 + 自动化 5（含归零变体 2）+ 工厂数量 8 + 贸易分享/放大/条件 11 + B 层全局阵营 3 + 跨房间配对 3 + 深海猎人 1 + 设施 group 3 | `token_maps.py` | ~150 | 已完成 |
| B2 | 新增 `_BUFF_TO_TOKENS: dict[str, list[str]]` 映射表（14 条），替代 `_OPERATOR_BUFF_PRODUCERS` 的 `dimension + cascade` 字段组合。执行引擎支持 `depends_on="token"` 级联时通过此表查找上游 buff 的生产 token | `token_maps.py` / `token_source.py` | ~60 | 已完成 |
| B3 | 新增 `_FN_CONDITIONS` 注册表：`is_knight`（已有）+ 预留 `is_abyssal_hunter`（深海猎人派生）等扩展槽位 | `token_source.py` | ~20 | 已完成 |
| B4 | 条件解析器补充 `pair` 配对解析（冒号分隔 → char_id 对）、`count_ge` 阈值解析（冒号分隔 → group_id + N） | `token_source.py` | ~30 | 已完成 |
| **B5** | **引擎支持 `depends_on="layout"/"facility"`**：`evaluate_tokens()` 接收 `ctx: SlotContext` → 通过 `ctx.layout` 查询布局数据（工厂数量、宿舍等级、发电站数等）；通过 `ctx.build_all_assignments()` 查询设施级干员分布（如含 sui 的设施数）。拓扑排序中 `depends_on="layout"/"facility"` 的 token 在第一遍计算完成后执行布局/设施注入 | `token_source.py` | ~40 | 已完成 |
| B6 | 补齐 B1 中依赖 `depends_on="layout"/"facility"` 的 TokenSource 注册：工厂数量联动 8 + 自动化 3（森蚺/掠风/异客/温蒂通过 `depends_on="layout"` 查询发电站数）+ 设施 group 3（`depends_on="facility"`）| `token_maps.py` | ~60 | 已完成 |
| B7 | 集成测试：TokenSource 输出与旧函数（`synergy_skill_count` / `synergy_global_faction` / `compute_cluster_hunting_bonus` / `synergy_facility_count` / `synergy_facility_group`）全量对齐。`compute_buff_pool`（BuffPool 生产者端）的替代正确性由 B2 映射表 + B8 级联测试覆盖 | `tests/test_token_source.py` | ~50 | 已完成 |
| B8 | `buff_id → token` 级联正确性测试（黑键 perception→silent_resonance、令 yanhuo→wushu_crystal） | `tests/test_token_source.py` | ~30 | 已完成 |

**验收条件**：
- [ ] 全部 ~75 条 TokenSource 注册完成，无遗漏（对照 `types.py` TABLES 注册器逐项核对）（当前 36/53：11 条可立即完成已注册，18 条阻塞性延期）
- [x] `_BUFF_TO_TOKENS` 覆盖 `_OPERATOR_BUFF_PRODUCERS` 的全部 16 条 entries（14 个唯一 buff_id）
- [x] 条件解析器对所有语法抛出明确错误（未知 key、格式错误等）而非静默失败
- [ ] TokenSource 输出与 **全部 5 个旧计数函数**（含级联场景）输出对齐（当前 3/5：`synergy_skill_count` / `synergy_global_faction` / `compute_cluster_hunting_bonus` 已对齐，`synergy_facility_count` / `synergy_facility_group` 待 Phase C）
- [x] `pytest tests/ -v -k token_source` 覆盖 ≥80 个测试用例（实际 106）
- [x] 引擎正确解析 `depends_on="layout"` 和 `depends_on="facility"`，从 `SlotContext.layout` 和 `build_all_assignments()` 注入布局/设施数据

**B7 完成后待办（延后至 Phase C）**：

| 待办 | 原因 | 目标 Phase |
|------|------|:---:|
| `synergy_facility_count` 集成对齐 | 需 `depends_on="layout"` 查询 dorm_level / recipe_types 等属性 | C |
| `synergy_facility_group` 集成对齐 | 需 `depends_on="facility"` 完整支持 | C |
| `exclude_self` 语义 | 当前由消费层处理，TokenSource 返回原始计数 | C（接入时决定归属） |
| `skill_class` alias 机制 | 旧函数支持红松骑士团↔红松别名，TokenSource 当前不处理 | C |
| `compute_cluster_hunting` 完整集成 | 需 control_ops + per-room buff_id 检查上下文 | C |
| 剩余 ~28 条注册补齐 | 工厂联动/自动化/贸易条件等复杂条目 | C |
| B8 `buff_id→token` 级联测试 | 已提前完成（提交 47b7212） | ✅ |
| **阻塞 18 条需引擎能力** | 见下表 | |

**阻塞性延期的引擎能力需求**：

| 引擎能力 | 影响条目数 | 说明 |
|------|:---:|------|
| `depends_on="layout"` + `attr` 属性聚合 | 5 | `_evaluate_layout` 需支持 `aggregate="attribute_sum"` + `attr="level"`（dorm/meeting/train level 求和） |
| `depends_on="layout"` + `distinct` 聚合 | 1 | `_evaluate_layout` 需支持 `aggregate="distinct"` + `attr="product"`（mfg_recipe_types 去重） |
| `exclude_self` 计数排除 | 3 | `_evaluate_count` 需消费 `TokenSource.exclude_self` 字段（贸易分享 3 条） |
| `scope="workspace"` 跨设施组合 | 2 | 需 Control+Mfg+Trade 三种设施类型的组合 scope（贸易条件效率 2 条） |
| `_FN_CONDITIONS` 派生函数 | 5 | 自动化/归零变体需 `has_automation`/`has_zeroing_variant` 派生布尔（5 条） |
| `partner_facility` 跨设施 pair | 1 | 中枢→贸易上限（维什戴尔→赫德雷）需跨房间配对 |
| `per-op` 属性提取 | 5 | 自动化干员 bonus 各不相同（5/5/5/15/10），消费侧需持有者属性查表 |

---

### Phase C: 接入求解器（~150 行）

**目标**：TokenSource 替代求解器中的旧计数函数，回归测试全绿，性能不低于旧方式。

| 步骤 | 内容 | 产出文件 | 行数 |
|:---:|------|---------|:---:|
| C1 | `warm_start` 接入：替代 `compute_consumer_driven_D0` 中的逐函数计数调用和 `_estimate_per_op_pool_value` 中的 `_count_pool_matching` 遍历——两处均替换为单次 `evaluate_tokens()` 调用 | `slot/rooms.py`, `slot/partials.py` | ~30 |
| C2 | 坐标下降接入：`_dispatch_optimize` → `optimize_mfg_room` / `optimize_trade_room` 中的 `synergy_pair` / `synergy_skill_count` / `synergy_automation` / `synergy_faction_room` 逐函数计数，替换为 TokenSource + 消费层保留 | `slot/mfg.py`, `slot/trade.py` | ~60 |
| C3 | Control 层接入：`compute_control_global_bonus` 中 `_eval_per_op` / `compute_cluster_hunting_bonus` 替换为 TokenSource；per-operator 条件加成的**消费侧**（线性公式）保留在 control_linkages | `synergy/control_linkages.py` | ~40 |
| C4 | 不做替换的声明：爬升 `e(t)`、菲亚梅塔自律、冲突互斥、订单覆盖、裁缝豁免 —— 在接入点加注释标注"非计数层，保留旧路径" | 各相关文件 | ~10 |
| C5 | 回归验证：`pytest tests/ -v` 全量测试通过；`python run_solver.py` 端到端无异常 | — | — |
| C6 | 性能基准：`_timing.py` 埋点对比 `evaluate_tokens()` 总耗时 vs 旧 5 个计数函数耗时之和，确认无退化（允许 ±5% 内） | `_timing.py` | ~10 |

**验收条件**：
- [ ] `pytest tests/ -v` **全量测试通过**（零回归）
- [ ] `python run_solver.py` 产出 JSON 与 Phase B 完成时的产出 **差异 ≤ 3 条干员**（允许因浮点排序边界导致的微小差异）
- [ ] `evaluate_tokens()` 总耗时 ≤ 旧 5 个函数耗时之和 × 1.05
- [ ] 所有未替换的旧路径有明确注释标注原因

---

### Phase D: 文档与清理（~50 行）

**目标**：旧代码标记 deprecated，文档索引更新，知识传递完整。

| 步骤 | 内容 | 产出文件 | 行数 |
|:---:|------|---------|:---:|
| D1 | 旧计数函数标注 `@deprecated` 装饰器 + docstring 迁移指引 → 新函数对照表 | 各 `synergy/*.py` | ~30 |
| D2 | `synergy/__init__.py` 新增 `evaluate_tokens` / `TokenSource` / `parse_condition` / `_BUFF_TO_TOKENS` 重导出 | `synergy/__init__.py` | ~5 |
| D3 | 更新 `AGENTS.md` 项目结构索引：新增 `token_source.py` + `token_maps.py` 文件描述 + 发现流程补充 | `AGENTS.md` | ~10 |
| D4 | 更新 `synergy-systems.md` §体系函数总清单：标注已被 TokenSource 替代的旧函数为 deprecated，追加 `evaluate_tokens()` 新条目 | `synergy-systems.md` | ~5 |
| D5 | 合并：`feat/token-source` → `master`（CR + squash merge），然后 `master` 单向合并到 `feat/market-iteration` | — | — |

**验收条件**：
- [ ] 所有 deprecated 函数有 `"""<deprecated> 使用 TokenSource.evaluate_tokens() 替代"""` 格式的 docstring
- [ ] `AGENTS.md` 索引新增 `token_source.py` + `token_maps.py` 条目，发现流程第 4 步包含"Token 计数层"
- [ ] `feat/token-source` squash merge 到一个 commit，message 格式 `feat(core): TokenSource 统一计数层`

---

### Phase E: 全量 char_id 迁移（正交阶段，~550 行）

**目标**：项目内全部干员标识符从 `op.name` 迁移到 `op.char_id`。本阶段依赖 Phase A（`find_by_char_id` 方法 + `char_id` 条件语法），但与 Phase B/C 变更面不重叠——可在 Phase A 完成后并行启动。TokenSource 的 `char_id` 条件和 `find_by_char_id` 方法为先行探针。

| 步骤 | 内容 | 产出文件 | 行数 |
|:---:|------|---------|:---:|
| E1 | `helpers.py` 7 个名称集合新增 char_id 版本（`_KNIGHT_CHAR_IDS` 等），`_is_knight()` 等判定函数内部同时兼容名称和 char_id 查询 | `synergy/helpers.py` | ~60 |
| E2 | `control_linkages.py` 6 张 C 层表键从干员名迁移到 char_id；`compute_control_global_bonus()` 等消费者查表逻辑从 `names = {op.name}` 改为 `ids = {op.char_id}` | `synergy/control_linkages.py` | ~120 |
| E3 | A/B 层 7 张干员名键表迁移（A 层 4：`_A_ROOM_FACTION_TABLE` / `_A_SKILL_COUNT_TABLE` / `_A_AUTOMATION_FALLBACK` / `_A_FACILITY_LINK_TABLE`；B 层 3：`_B_GLOBAL_FACTION_TABLE` / `_B_CROSS_ROOM_PAIR_TABLE` / `_B_BUFF_CONSUMER_TABLE`），同步更新消费方查表逻辑 | `mfg_linkages.py`, `global_linkages.py`, `buff_pool.py`, `facility_linkages.py` | ~100 |
| E4 | `mood_flow.py` 心情消耗修正表中名称键条目（~35 条）迁移到 char_id | `mood_flow.py` | ~40 |
| E5 | `registry.py` `_SYSTEM_CONTRIBUTORS` 键迁移到 char_id | `synergy/registry.py` | ~10 |
| E6 | `classification.py` Mfg/Trade 分类器内 `seen` 去重集合和名称匹配逻辑改为 `op.char_id` | `synergy/classification.py` | ~20 |
| E7 | `derive.py` 新增 `--output-char-id` 模式，`_derived.py` 新增 char_id 版本集合输出 | `scripts/derive.py`, `_derived.py` | ~100 |
| E8 | 测试 fixture 适配：`Operator(char_id=..., name=...)` 构造确保 char_id 正确；名称集合类断言更新 | `tests/synergy/test_*.py`, `tests/solver/slot/test_*.py` | ~100 |
| E9 | 非 synergy 审查：`evaluate.py` / `report.py` / `output.py` / `production.py` 中的干员名使用确认不需要迁移（输出层保留人类可读名称） | 各文件 | ~0 |

**验收条件**：
- [ ] `grep -rE "op\[.name.\]|\.name\b" steward_core/synergy/` 零匹配（除 deprecated/docstring 引用）
- [ ] `grep -rE "op\[.name.\]|\.name\b" steward_core/solver/` 仅允许 `report.py` / `output.py` 中的报告输出用
- [ ] `conflicts.py` `_EFF_MECH_DISABLERS` 以 buff 前缀为键，确认不受迁移影响（审查通过即可，无需代码改动）
- [ ] `pytest tests/ -v` 全量测试通过（零回归）
- [ ] `python run_solver.py` 产出 JSON 与迁移前一致（同一干员池，仅标识符内部变换）
- [ ] `derive.py --output-char-id` 产出与现有 `_derived.py` 名称集合项数一致

---

### 各阶段代码量预估

| Phase | 新增 | 修改 | 核心产出 |
|:---:|:---:|:---:|------|
| A | ~355 | ~10 | 执行引擎 + 10 条注册 + 测试 |
| B | ~440 | 0 | 全量注册 + buff 映射 + engine 扩展 |
| C | ~80 | ~70 | 求解器接入 |
| D | ~10 | ~40 | 文档/标注 |
| E | ~450 | ~100 | 全量 char_id 迁移 |
| **合计** | **~1335** | **~220** | |

## 设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| condition 格式 | `key=value` 统一字符串 | 吞并 condition_field + condition_value，减少字段数 |
| cascade 处理 | `depends_on + passthrough` | 拓扑排序替代 BuffPool 两遍扫描 |
| facility 计数 | `depends_on="layout"/"facility"` | 统一 operator-based 和 layout-based 两种源头 |
| 二元配对 | `condition="pair"` 纳入 | 本质是 count∈{0,1}，与 aggregate="count" 一致 |
| **配对标识符** | **双方使用 char_id**（当前 Phase B 注册用干员名占位，Phase E 迁移后替换为真实 char_id） | 干员名非稳定标识（异格/联动可能重名）; char_id 是 `character_identity.json` 的自然主键；与 inbox "synergy 子系统全量 char_id 迁移" 方向一致 |
| **条件字段溯源** | **映射到 Operator 模型字段** | group_id/nation_id/team_id/char_id 直接从 `character_table`/`character_identity` 字段读取；`is_knight` 等派生布尔从解包数据推导，仅在无法机械提取时使用名称集合兜底 |
| **team_id 条件语法** | **实施中自然扩展** | 原计划仅覆盖 group_id/nation_id/char_id，实施中因历阵锐枪芬的 reserve1 条目需要而新增；team_id 语法与 group_id/nation_id 模式一致 |
| cap 归属 | Token 生产侧截断 | 计数→cap→输出，消费侧不再重复截断 |
| resolver 注册 | 独立 `_FN_CONDITIONS` 映射表 | 避免 condition 字符串暴露内部函数名 |
| 不纳入归零副作用 | 保留在消费侧 | 副作用不是 token 值，是机制守卫层语义 |

## 开发原则

- **独立可测**：TokenSource 执行引擎是纯函数，输入 ctx + sources，输出 dict
- **渐进替换**：每个 Phase 可独立回滚，不删除旧代码直到验证通过
- **TDD 纪律**：红灯（写测试 → 失败）→ 绿灯（实现 → 通过）→ 审查 → 提交
- **不引入外部依赖**：纯 Python dataclass + dict + 拓扑排序
