# 基建排班：约束体系与数据基线

> **版本**: 2026-05-26 · 基于 `character_identity.json` + `buffs_infrastructure.json` 交叉核验

## 1. 数据全景图

排班问题的完整数据链路：

```mermaid
flowchart LR
    subgraph 数据源["清洗数据源（跨平台盲区）"]
        A["character_identity.json<br/>415 干员 × 892 技能条目"]
        B["buffs_infrastructure.json<br/>520 基建 buff（7 设施）"]
    end
    subgraph 本项目["RhodeLogisticsSteward"]
        C["steward_core/data_loader.py<br/>解析数据 → Operator / Skill 模型"]
        D["steward_core/solver/<br/>四阶段穷举+支撑+贪心求解"]
        E["output/custom_infrast/*.json<br/>供 MAA 执行排班"]
    end
    A -->|"charId → buffId → phase"| C
    B -->|"buffId → roomType + efficiency"| C
    C --> D
    D -->|"生成"| E
```

### 1.1 数据文件说明

| 文件 | 内容 | 条目数 | 备注 |
|------|------|:---:|------|
| `character_identity.json` | 干员身份 + 技能列表 | 415 干员 / 892 技能 | 按 `charId` 索引，含 rarity/phase/roomType |
| `buffs_infrastructure.json` | 基建生产 buff 详情 | 520 buff | 按 `buffId` 索引，含 roomType/efficiency/description/charId |
| `buffs_non_production.json` | 训练室/加工站 buff | 207 buff | TRAINING=103 + WORKSHOP=104，排班求解不涉及 |

### 1.2 干员池概览（character_identity.json）

| 维度 | 数值 |
|------|------|
| 总干员 | **415** 名 |
| 6★ / 5★ / 4★ / 3★ / 2★ / 1★ | 131 / 191 / 61 / 17 / 5 / 10 |
| 总基建技能条目 | **892** 条（平均 2.15/人） |
| PHASE_0 / PHASE_1 / PHASE_2 | 451 / 87 / 354 |
| 生产相关设施技能 | 639 条（排除 TRAINING 131 + WORKSHOP 122） |

```mermaid
pie title 技能条目按设施分布 (892条)
    "制造站 143" : 143
    "训练室 131" : 131
    "加工站 122" : 122
    "贸易站 117" : 117
    "宿舍 103" : 103
    "控制中枢 95" : 95
    "会客室 87" : 87
    "发电站 48" : 48
    "办公室 46" : 46
```

### 1.3 基建 Buff 池（buffs_infrastructure.json）

| 设施 | buff 数 | 直接效率 (e>0) | 条件/联动 (e=0) | 惩罚 (e<0) |
|------|:---:|:---:|:---:|:---:|
| MANUFACTURE | 109 | 51 | 55 | 3 |
| TRADING | 91 | 45 | 46 | 0 |
| CONTROL | 88 | 0 | 88 | 0 |
| DORMITORY | 83 | 0 | 83 | 0 |
| MEETING | 67 | 37 | 30 | 0 |
| HIRE | 43 | 39 | 4 | 0 |
| POWER | 39 | 29 | 10 | 0 |
| **合计** | **520** | **201** | **316** | **3** |

> CONTROL 和 DORMITORY 的 buff 效率值**全部为 0**——它们通过条件/联动机制间接影响全局（心情恢复、中枢减免等）。直接效率 buff 集中在 MANUFACTURE / TRADING / POWER / HIRE / MEETING 五类设施。MANUFACTURE 有 3 条负值 buff，对应干员基建技能的副作用（如心情消耗增加）。

**交叉核验**：`character_identity.json` 中引用的所有 `buffId` 与 `buffs_infrastructure.json` **100% 匹配**（520/520 个 buff 均被至少一名干员持有）。

### 1.4 设施容量（以 243 布局为例）

| 设施 | 房间数 | 每间人数 | 总工位 | 效率字段 |
|------|--------|----------|--------|----------|
| 控制中枢 Control | 1 | **5** | 5 | 心情恢复 |
| 贸易站 Trade | 2 | **3** | 6 | Money(龙门币)/SyntheticJade(源石碎片) |
| 制造站 Manufacture | 4 | **3** | 12 | CombatRecord/PureGold/OriginStone/Chip |
| 发电站 Power | 3 | **1** | 3 | Drone(无人机恢复) |
| 会客室 Reception | 1 | **2** | 2 | General/No1~No7(线索搜集) |
| 办公室 Office | 1 | **1** | 1 | HR(人脉联络) |
| 宿舍 Dormitory | 4 | 5 | 20 | 心情恢复(不参与效率) |

> 核心工位 = 29，干员/工位比 = **7.8:1**（415 干员中精1+可用 225 名）。  
> 约束复杂度不在"有没有人"，而在"选谁最好"——典型的**组合优化**问题。

```mermaid
mindmap
  root((243 布局))
    控制中枢
      1 间 × 5 人
    制造站
      Mfg1 3人
      Mfg2 3人
      Mfg3 3人
      Mfg4 3人
    贸易站
      Trade1 3人
      Trade2 3人
    发电站
      3 间 × 1人
    宿舍
      4 间 × 5人
    其他
      会客室 2人
      办公室 1人
```

---

## 2. 约束条件体系

排班问题中的约束分为三类：硬约束（不可违反）、软约束（需要优化）和联动约束（跨设施连锁）。

### 2.1 硬约束（Hard Constraints）

| # | 约束 | 说明 |
|---|------|------|
| H1 | 每设施人数上限 | Control≤5, Trade≤3/间, Mfg≤3/间, Power≤1/间, Reception≤2, Office≤1 |
| H2 | 每干员唯一占用 | 一个干员同时只能在**一个**设施的**一个**工位 |
| H3 | 技能解锁条件 | PHASE_0=451, PHASE_1=87, PHASE_2=354。精2 方可解锁 354 条技能 |
| H4 | 设施类型匹配 | 干员只能进驻其技能适用的设施（技能 `roomType` 决定） |
| H5 | 产物类型匹配 | 制造站的当前产物必须匹配干员技能（如做赤金时，仅赤金相关技能生效） |
| H6 | 跨周期可持续性 | Σ_w worked_hours(op, w) ≤ mood_full / mood_burn。排班周期结束后干员心情须不低于初始值，保证下一周期可正常启动。多班次排班的核心硬约束。即 §3.1 工作时长池。 |

### 2.2 软约束（Soft Constraints / 优化目标）

| # | 约束 | 说明 |
|---|------|------|
| S1 | 效率最大化 | 在合规前提下追求最高综合产出效率 |
| S2 | 心情平衡 | 控制同一设施干员的心情消耗节奏，避免集中耗尽。由 H6（跨周期可持续性）的形式化约束 + MoodContext 心情流转引擎共同保证 |
| S3 | 宿舍恢复 | 宿舍恢复是独立资源，通过 λ 影子乘子估值（+ recovery × λ × hours），不纳入 H6 的池容计算——避免"假设所有干员都能获得宿舍恢复"的过度乐观 |
| S4 | 会客室线索轮换 | 会客室只需凑齐线索，非效率优先场景可降低优先级 |

> **注意**：技能联动体系的详细分类见 [`synergy-systems.md`](./synergy-systems.md)。

---

## 附录 A: 数据溯源 — 全部断言核验记录

本附录逐条列出文档中所有数据断言的来源与交叉核验结果，构成项目的**可信数据基线**。

> 核验脚本（概念引用）：以下验证方式中提到的 `verify_coverage.py` / `verify_baseline.py` 为项目早期的独立验证脚本。

### A.1 干员池数据（§1.2）

| 断言 | 来源 | 核验 |
|------|------|------|
| 总干员 415 名 | `character_identity.json` → 顶层 key 计数 | `len(character_identity) = 415` ✅ |
| 6★=131 / 5★=191 / 4★=61 / 3★=17 / 2★=5 / 1★=10 | `character_identity.json` → `rarity` 字段 | rarity 5→6★(131), 4→5★(191), 3→4★(61), 2→3★(17), 1→2★(5), 0→1★(10) ✅ |
| 基建技能 892 条 | `character_identity.json` → 展开所有 `skills[]` 数组 | 实际 sum(len(c['skills']) for c in ci) = 892 ✅ |
| PHASE_0=451, PHASE_1=87, PHASE_2=354 | `character_identity.json` → `skills[].phase` | 逐条统计一致 ✅ |
| 技能-设施分布（饼图数据） | `character_identity.json` → `skills[].roomType` | 与旧版 `building_data.json` 统计完全一致 ✅ |

### A.2 基建 Buff 数据（§1.3）

| 断言 | 来源 | 核验 |
|------|------|------|
| `buffs_infrastructure.json` 含 520 条 buff | 文件 `len()` | `len(buffs_infrastructure) = 520` ✅ |
| 按设施分布: Mfg=109, Trade=91, Control=88, Dorm=83, Meeting=67, Hire=43, Power=39 | `buffs_infrastructure.json` → `roomType` 分组计数 | 逐设施计数一致 ✅ |
| efficiency=0 的 buff 316 条, >0 的 201 条, <0 的 3 条 | `buffs_infrastructure.json` → `efficiency` 字段 | 316 + 201 + 3 = 520 ✅ |
| 520 个 buff **全部**被 character_identity 中干员持有 | 交叉比对 `buffId` | `set(bi.keys()) ⊆ set(all_buff_ids_in_ci)` → 520/520 ✅ |
| CONTROL 设施的 88 个 buff 效率值全部为 0 | `buffs_infrastructure.json` → `roomType=CONTROL` 所有 entry | 88 条 `efficiency=0`，无例外 ✅ |

### A.3 设施容量（§1.4）

| 断言 | 来源 | 核验 |
|------|------|------|
| Control≤5, Trade≤3, Mfg≤3, Power≤1, Reception≤2, Office≤1 | 游戏机制 + MAA `custom_infrast` 协议 | 游戏内基建界面 + MAA 文档确认 |
| 243布局: 2Trade + 4Mfg + 3Power | 社区效率论共识 + MAA 内置模板 | MAA `resource/custom_infrast/243_layout_*.json` |
| 核心工位 = 29 | 5+2×3+4×3+3×1+2+1 | 算术验证 ✅ |

### A.4 硬约束 H3: 技能解锁条件（§2.1）

| 断言 | 来源 | 核验 |
|------|------|------|
| PHASE_0=451, PHASE_1=87, PHASE_2=354 | `character_identity.json` → `skills[].phase` | 等同 §A.1 ✅ |
| 精2 方可解锁 354 条技能 | phase=2 的 buff 要求干员 elite≥2 | 与 `buffs_infrastructure.json` 交叉：这些 buff 的 charId 对应的干员 rarity≥4 方有 elite=2 能力 |

### A.5 关键外部数据源

| 资源 | URL | 用途 |
|------|-----|------|
| **ArknightsGameData** | [GitHub](https://github.com/Kengxxiao/ArknightsGameData) | character_table.json + building_data.json（原始数据） |
| **MAA** | [GitHub Releases](https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases) | infrast.json + custom_infrast/ 模板（效率值 + 参考方案） |
| **PRTS Wiki** | [prts.wiki](https://prts.wiki/) | 基建机制（心情/消耗/恢复速率） |
| **一图流排班生成器** | [ark.yituliu.cn/tools/schedule](https://ark.yituliu.cn/tools/schedule) | 可视化排班方案参考 |
| **MAA 基建排班协议** | [docs.maa.plus](https://docs.maa.plus/zh-cn/protocol/base-scheduling-schema.html) | custom_infrast JSON schema |

### A.6 MAA 内置参考模板

| 文件 | 布局 | 换班频率 |
|------|------|----------|
| `243_layout_3_times_a_day.json` | 2贸易/4制造/3电站 | 8H 一换 |
| `243_layout_4_times_a_day.json` | 2贸易/4制造/3电站 | 6H 一换 |
| `153_layout_3_times_a_day.json` | 1贸易/5制造/3电站 | 8H 一换 |
| `153_layout_4_times_a_day.json` | 1贸易/5制造/3电站 | 6H 一换 |
| `333_layout_for_Orundum_3_times_a_day.json` | 3贸易/3制造/3电站（搓玉） | 8H 一换 |

---

## 参考

- 策略概要（编码上下文）: [strategy-brief.md](./strategy-brief.md)
- 效率函数统一建模: [efficiency-function-design.md](./efficiency-function-design.md)
