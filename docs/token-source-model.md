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

**不纳入 TokenSource 的部分**：旧 synergy 表不必立即迁移键类型 —— TokenSource 层新建后，旧表逐步标记 deprecated 即可。详见 inbox "synergy 子系统全量 char_id 迁移"。

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

### Phase A: 原型验证（~300 行）

1. **新建 `steward_core/token_source.py`** — TokenSource dataclass + 执行引擎
2. **选取 10 条 TokenSource 注册**（A层同房阵营 3 + PerOp 7）
3. **实现拓扑排序执行引擎**：`evaluate_tokens(sources, ctx) → dict[str, float]`
4. **单元测试**：每个 aggregate 模式至少 1 个测试

### Phase B: 全量映射（~200 行）

5. **补齐 ~46 条 TokenSource 注册**
6. **buff_id → token 1:N 映射表**（~40 条）
7. **条件解析器**：`parse_condition(condition_str) → matcher`
8. **集成测试**：TokenSource 输出与现有 5 个计数函数的输出对齐

### Phase C: 接入求解器

9. **warm_start 接入**：替代 `compute_consumer_driven_D0` 和 `_estimate_per_op_pool_value` 的计数部分
10. **坐标下降接入**：替换 `_eval_per_op`、`synergy_skill_count` 等逐函数计数
11. **回归验证**：全量 793 测试通过
12. **性能基准**：图与现有方式的耗时对比

### Phase D: 文档与清理

13. 更新 `AGENTS.md` 项目结构索引
14. 标记旧计数函数为 deprecated
15. 合并到 master → 单向合并到 feat/market-iteration

## 设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| condition 格式 | `key=value` 统一字符串 | 吞并 condition_field + condition_value，减少字段数 |
| cascade 处理 | `depends_on + passthrough` | 拓扑排序替代 BuffPool 两遍扫描 |
| facility 计数 | `depends_on="layout"/"facility"` | 统一 operator-based 和 layout-based 两种源头 |
| 二元配对 | `condition="pair"` 纳入 | 本质是 count∈{0,1}，与 aggregate="count" 一致 |
| **配对标识符** | **双方使用 char_id** | 干员名非稳定标识（异格/联动可能重名）; char_id 是 `character_identity.json` 的自然主键；与 inbox "synergy 子系统全量 char_id 迁移" 方向一致 |
| **条件字段溯源** | **映射到 Operator 模型字段** | group_id/nation_id/char_id 直接从 `character_table`/`character_identity` 字段读取；`is_knight` 等派生布尔从解包数据推导，仅在无法机械提取时使用名称集合兜底 |
| cap 归属 | Token 生产侧截断 | 计数→cap→输出，消费侧不再重复截断 |
| resolver 注册 | 独立 `_FN_CONDITIONS` 映射表 | 避免 condition 字符串暴露内部函数名 |
| 不纳入归零副作用 | 保留在消费侧 | 副作用不是 token 值，是机制守卫层语义 |

## 开发原则

- **独立可测**：TokenSource 执行引擎是纯函数，输入 ctx + sources，输出 dict
- **渐进替换**：每个 Phase 可独立回滚，不删除旧代码直到验证通过
- **TDD 纪律**：红灯（写测试 → 失败）→ 绿灯（实现 → 通过）→ 审查 → 提交
- **不引入外部依赖**：纯 Python dataclass + dict + 拓扑排序
