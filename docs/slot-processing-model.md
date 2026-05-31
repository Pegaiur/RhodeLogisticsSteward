# 统一槽位加工模型

> **状态**：已实施（v0.6.0-dev）。14×12h 基线已跑通，求解器代码位于 `steward_core/solver/slot/`。
>
> V1 SlotIterationStrategy → V2 SlotSolver 的演进记录见 `archive/slot-iteration-notes.md`。

---

## 1. 理论基础

### 1.1 槽位：最小生产单元

基建由若干**槽位**（slot）组成。每个槽位是一个独立的产能计算单元，由唯一 ID 标识。

```
槽位 = { id, facility_type, product_type, base_rate }
```

槽位之间可能存在**效果共享关系**——某些技能的作用域覆盖多个槽位。共享同一效果组的槽位集合称为**效果组**（effect group）。游戏中的"房间"是效果组的一种物理实现：一间制造站的 3 个槽位天然同属一个效果组，但理论不依赖"房间"概念——只需要槽位之间能互相引用。

**关键**：产能公式以槽位为单位。所有技能的效果最终作用于槽位。

> **实现注**：当前代码以 `RoomAssignment`（room_type + operators 列表）为基本单位，尚无槽位 ID 体系。本文档的槽位模型是理论框架，为后续实现提供设计目标。

| 设施     | 房间数 | 每间槽位 | 总槽位 |
|----------|:------:|:--------:|:------:|
| Control  | 1      | 5        | 5      |
| Trade    | 2      | 3        | 6      |
| Mfg      | 4      | 3        | 12     |
| Power    | 3      | 1        | 3      |
| Reception| 1      | 2        | 2      |
| Office   | 1      | 1        | 1      |
| Dormitory| 4      | 5        | 20     |
> 核心工位 29 个。全 box 415 干员中精 2 可用 ≥ 225 名。Dormitory 20 槽位中，仅部分用于宿舍恢复 buff 提供者，其余供工作干员恢复使用。

```
槽位产能 = base_rate × efficiency × effective_hours × drone_multiplier
```

### 1.2 工作时长：续航池与恢复

干员可工作的总时数由两个独立资源组成：

```
续航池 pool_hard  = mood_full / mood_burn     ← 硬约束：跨周期可持续性上限（约束基线 H6）
最大可用 pool_max  = pool_hard + Σ(recovery_rate × rest_hours)  ← 含恢复的理论最大值
```

- `mood_burn` 受类型 5a 技能修正（中枢减免、烟火联动）
- `recovery_rate` 受类型 5b 技能修正（宿舍 buff、中枢全局宿舍加成）
- 菲亚梅塔自律：`recovery_rate = 2.0/h`，不依赖他人

**关键区分**：`pool_hard` 是可持续性的硬约束（干员心情不能退化），λ 影子乘子对此约束进行经济性惩罚（§9.5）。`pool_max` 中的恢复部分是独立资源，由 Phase D 宿舍分配竞争，通过 `+ recovery × λ × hours` 独立估值——**不纳入 λ 的池容检查**，避免"假设所有干员都能获得宿舍恢复"的过度乐观。

干员将工作时长分配到具体槽位。分配后，该槽位的 `effective_hours = 分配的时长`。

### 1.3 技能：槽位状态的变换函数

干员是**技能的容器**。一个干员持有若干技能，各技能独立参与分类。

```
每个技能 = 一个变换函数: f(输入) → (输出, 作用域)
```

体系内不存在"生产者→消费者"的定向管道。技能通过共享数据结构通信：某些技能修改全局状态向量，另一些技能读取它。烟火（yanhuo）不是令"生产"给黍"消费"的 token——令的技能将其心情变换为 yanhuo 增量，黍的技能将 yanhuo 维度变换为槽位效率。两者是函数复合关系。

### 1.4 跨类型统一：类型 6/7 的定量折算

不同产品类型（战斗记录、赤金、龙门币）的槽位产能不直接可比。折算方向由外部约束决定。赤金在体系内作为中间 token——由制造站产出，由贸易站消耗。

#### 赤金→龙门币：类型 6 的三类定量模型

类型 6（订单机制）不通过汇率折算，而是直接改变贸易站订单参数：每单赤金消耗、LMD 产出、订单耗时。三类机制：

| 类别 | 机制 | 干员 | 订单参数变化 |
|------|------|------|-------------|
| 固定订单结构 | 独占/投资改变特定订单的参数 | 可露希尔、龙舌兰 | 直接改变 LMD/单、赤金/单、耗时 |
| 期望值贸易效率 | 随机违约产生期望效率增益 | 但书 | 2/3 赤金订单 LMD 翻倍，赤金收支净值 0 |
| 期望值订单分布 | 提升高品质订单出现概率 | 裁缝系列 | P4 从 0.20 爬升至 0.53(α)/0.85(β)/0.88(α+β) |

优先级：可露希尔独占 → 但书+龙舌兰组合 → 但书/龙舌兰/裁缝单独。任一类别生效时，贸易站输出直接用订单参数计算：

```
LMD/天    = Σ(每单 LMD × 该类订单日频次)
赤金消耗/天 = Σ(每单赤金 × 该类订单日频次)
等效赤金产出 = 仅投资 bonus 部分 / 500（龙舌兰）
```

其中日频次 = `24h / 加权平均订单耗时`，加权权重为各订单类型的概率分布。但书的赤金以金换金净值为 0——不产生也不消耗额外赤金，只产出额外 LMD。

#### 发电站→制造站/贸易站：无人机桥的经验书等价

**关键事实**：无人机加速为纯时间加速，不涉及目标设施效率。制造站与贸易站均为 **3 分钟/架**。

**经验书锚定**：60 架无人机 = 3 小时 → 1 中级经验书（1000 经验）。由此：

```
1 架无人机 = 1000/60 ≈ 16.67 经验等值
日均基础无人机 = 240 架 → 4000 经验等值/天
```

发电效率每 +1%，日均无人机 +2.4 架 → **+40 经验等值/天**。

对标制造站（Lv3 中级经验书，3h/本）：

```
1 个制造站槽位（0% 效率）: 8000 经验/天
+1% 制造站效率（单槽位） : +80  经验/天
+1% 发电效率              : +40  经验/天  →  相当于 0.5% 制造站效率（单槽位）
```

因此 **+1% 发电效率 ≈ +0.5% 制造站单槽位效率**（以经验书为基准）。贸易站等值可同理从基础贸易参数折算（60 架 = 3h 贸易时间 ≈ 1283 LMD 期望等值）。

类型 7（发电站）与类型 1（制造站/贸易站）可在同一尺度比较——这是模型"统一"的核心论据。

#### 经验→龙门币：依赖布局的参数比

战斗记录（经验）和龙门币不可在游戏内直接兑换。等效价值由制造站→贸易站的产出比间接决定，并随布局变化：

| 布局 | 制造站数 | 贸易站数 | 经验:LMD 价值比 | 说明 |
|:----:|:------:|:------:|:------------:|------|
| 243 | 4 | 2 | **1.3 : 1** | 经验产出相对充裕 |
| 153 | 1 | 3 | **1.0 : 1** | 经验与 LMD 大致等值 |

```
参数化:
  xp_lmd_ratio = 布局 == "243" ? 1.3 : 1.0   ←  工程常量，用户可覆写

经验等值 → LMD 等值:  除以 xp_lmd_ratio
LMD 等值 → 经验等值:  乘以 xp_lmd_ratio
```

统一计价单位取 **LMD 等值/天**。所有产能比较均在此量纲下进行。

#### 会客室→信用商店：线索效率→等效制造站效率

会客室（Reception）线索搜集速度通过以下链路产生价值：

```
Reception 效率% → 线索获取加速 → 信用点获取加速
  → 信用商店购买 LMD/经验书 → LMD 等值/天
```

信用商店每日刷新，LMD 和经验书是常见商品。基准折算（源自玩家社区长期测算）：

```
20% Reception 效率 → 等效 2% 制造站效率（单槽位）
```

推导：1% Reception 效率 → 0.1% Mfg 等效效率。参数化如下：

```
参数化:
  reception_to_mfg_ratio = 0.10   ←  1% Reception ≡ 0.1% Mfg 单槽效率
  contribution(op, Reception) = reception_eff × reception_to_mfg_ratio
                              × mfg_base_rate_avg ÷ xp_lmd_ratio 等值 → LMD等值
                              + Σ(写入S[d] × D[d])
```

#### 办公室→凭证→理智：公招效率→等效制造站+贸易站效率

办公室（Office）人脉联络速度通过以下链路产生价值：

```
Office 效率% → 公招刷新加速 → 多余干员 → 绿票/黄票（凭证）
  → 凭证兑换抽卡资源 → 抽卡资源 → 理智
  → 理智刷取 CE-6(LMD)/LS-6(经验) → LMD 等值/天
```

基准折算（制造效率优先）：

```
20% Office 效率 → 等效 22% 制造站效率
```

贸易效率项暂不纳入。参数化如下：

```
参数化:
  office_to_mfg_ratio  = 1.10    ←  1% Office ≡ 1.1% Mfg 单槽效率

  contribution(op, Office) = office_eff × office_to_mfg_ratio
                           × mfg_base_rate_avg ÷ xp_lmd_ratio LMD等值
                           + Σ(写入S[d] × D[d])
```

以上 `xp_lmd_ratio`、`reception_to_mfg_ratio`、`office_to_mfg_ratio`、`drone_to_mfg_ratio`（§6.2）均为**工程常量**——源自玩家社区长期实践共识，参数化仅为代码可维护性，并非需要校准的可变参数。这些比值已在人类排班决策中隐式使用多年，本项目目标为逼近人类排班水平，直接采用逻辑自洽。

---

## 2. 槽位体系

### 2.1 槽位标识

每个槽位有全局唯一 ID。技能通过 ID 引用目标槽位或同组槽位。

```
槽位 ID 示例：
  mfg_cr_0      ← 制造站 0 号位，作战记录
  mfg_pg_1      ← 制造站 1 号位，赤金
  trade_0       ← 贸易站 0 号位
  control_2     ← 控制中枢 2 号位
  dorm_a_0      ← 宿舍 A 0 号位
```

### 2.2 效果组

效果组是槽位的集合，定义了技能效果的传播范围。效果组从槽位布局中导出，不作为理论原语。

| 效果组类型 | 构成 | 示例 |
|-----------|------|------|
| 同设施相邻槽位 | 同一制造站/贸易站的 3 个槽位 | mfg_0, mfg_1, mfg_2 |
| 全设施同类槽位 | 所有制造站槽位 | 全局注入（类型 3） |
| 同宿舍槽位 | 同一宿舍的 5 个槽位 | dorm 恢复 buff（类型 5b） |

### 2.3 槽位间引用

技能可通过以下方式引用其他槽位：

| 引用方式 | 示例技能 |
|---------|---------|
| **同组存在性** | 阿兰娜检查效果组内是否有温米的槽位（类型 1b） |
| **同组计数（阵营）** | 摩根统计效果组内格拉斯哥帮槽位数（类型 1c） |
| **同组计数（技能类别）** | 水月统计效果组内"标准化"技能数（类型 1d） |
| **全局计数（阵营）** | 缪尔赛思统计全基建莱茵槽位数（类型 1l） |
| **跨组目标** | 烈夏检查古米是否在任意贸易站槽位（类型 1m） |
| **设施计数** | 清流统计贸易站效果组数量（类型 1e） |

---

## 3. 工作时长模型

### 3.1 初始时长池

每个干员的初始工作时长由心情-消耗关系决定，即**跨周期可持续性硬约束**（约束基线 H6）：

```
pool_hard[op] = mood_full / mood_burn

其中:
  mood_burn = max(0, base_burn - recovery_modifiers)
  base_burn = 1.0 - 0.05 × (同组工作槽位数 - 1)    ← 3 工位 → 0.90/h
  recovery_modifiers = control_recovery + yanhuo_recovery + mlynar_spread
```

**含义**：单干员在排班周期内的可持续工作小时数上限。超过此值，干员心情将退化至无法在下个周期正常启动。此为**硬约束**——多窗口求解中，λ 影子乘子将此硬约束转化为经济信号（§9.5），使 contribution 评分中自动惩罚超池行为。

**注意**：宿舍恢复是独立资源（由 Phase D 宿舍分配竞争），**不纳入 pool_hard 计算**——避免"假设所有干员都能获得宿舍恢复"的过度乐观。宿舍恢复的价值由 §9.5 的 `+ recovery_rate × λ × hours` 独立估值。

### 3.2 时长修正技能

类型 5a 技能修改 `mood_burn`，间接扩大工作时长池：

| 技能 | 修正方式 |
|------|---------|
| 中枢干员基础（每人 +0.05/h） | control_recovery ↑ → mood_burn ↓ |
| 重岳·孤光共照 | yanhuo_recovery = 0.05 + yanhuo/20×0.05/h |
| 玛恩纳·公事公办 | control_recovery 扩散 + 额外 +0.1/h |

类型 5b 技能通过宿舍恢复**补充**工作时长池（见 §3.4）。

### 3.3 窗口展开：选择权的分配

多窗口不引入状态机。其本质是**工作时长池在时间轴上的分配**。

```
排班周期 = 若干连续时间窗口 [T₁, T₂, ..., Tₙ]

每个窗口 Tᵢ:
  - 可将干员分配到槽位（消耗工作时长池）
  - 可将干员分配到宿舍（恢复工作时长池）
  - 可重新布置槽位分配（选择权）

目标: 最大化 Σ 所有槽位在所有窗口的产能
约束: 每个干员的总消耗 ≤ 初始时长池 + 恢复补充
```

窗口边界只是**重新布置槽位的选择权**——求解器可以在此处改变干员→槽位的映射，也可以保持不变。选择权越多（窗口越多），解空间越大，但理论上限不变。

> **"窗口模型"是本文档定义的求解框架**。基于该框架的 Phase A→D 贪心 + λ bisection
> 跨期约束构成当前求解器（`solver/slot/solver.py`）的实现骨架。
> [机会成本补充覆盖方案](./time-slot-scheduling-model.md) 在此骨架之上叠加正交维度
> （组合级归零机会成本、跨窗口 λ_mood + swap_cost），不替换骨架本身。

### 3.4 宿舍恢复：时长池的补充

宿舍槽位不产生产能，但为其中干员提供工作时长池的恢复。

```
恢复速率 = Σ(类型 5b 技能效果)

聚合规则:
  1. 菲亚梅塔自律: 固定 2.0/h，隔离其他加成
  2. 自身恢复 (dorm_rec_oneself*): 取 max
  3. 单体恢复 (dorm_rec_single*): 同宿舍他人提供，取 max
  4. 全体恢复 (dorm_rec_all*): 同宿舍他人提供，累加
  5. 中枢全局宿舍加成: 按稀有度区分
  6. 烟火联动: +yanhuo_bonus/h

恢复补充 = recovery_rate × rest_hours  ← 加入工作时长池
```

---

## 4. 技能函数体系

### 4.1 函数签名

```
f(输入) → (输出, 作用域)

输入   ∈ { 自身标量, 自身心情, 同组槽位集合, 设施计数, 全局状态维度, 时间, 仓库容量, 他人效率, ... }
输出   ∈ { 槽位效率, 全局状态增量, 规则修正, 槽位屏蔽, 心情速率增量, 基础产出率修正, 有效时长缩放 }
作用域 ∈ { 同组, 全局, 同宿舍, 目标房间 }
```

### 4.2 输出类型枚举

```
           ┌── 1. 槽位效率 ───── 加入目标槽位的 efficiency 积分
           │
           ├── 2. 全局状态增量 ── 修改全局状态向量的一个维度
           │
           ├── 3. 规则修正 ────── 改变其他技能的计算参数
输出类型 ──┼── 4. 槽位屏蔽 ────── 归零同组其他槽位
           │
           ├── 5. 心情速率修正 ── 改变 mood_burn 或 mood_recovery
           │
           ├── 6. 基础产出率修正 ─ 改变 base_rate 换算逻辑
           │
           └── 7. 有效时长缩放 ── 无人机加速等工期缩放
```

### 4.3 输入类型速查

| 输入类型 | 含义 | 被哪些技能使用 |
|---------|------|-------------|
| 自身标量 | 技能的 `efficient` 字段 | 1a |
| 同组槽位集合 | 同一效果组内的槽位/干员 | 1b, 1c, 1d, 4 |
| 设施计数 | 全基建某类设施的数量 | 1e |
| 全局状态维度 | 全局状态向量的一个分量 | 1f, 2e |
| 自身心情 | 干员当前 mood 值 | 1g, 2a, 2b |
| 时间 | 排班已进行小时数 | 1h |
| 仓库容量 | 房间总仓库容量 | 1i |
| 他人效率 | 同组其他槽位的效率值 | 1j |
| 作业平台数 | 发电站中作业平台干员数 | 1k |
| 全基建阵营计数 | 全基建范围阵营统计 | 1l |
| 跨组目标存在 | 指定干员是否在任意槽位 | 1m |
| 宿舍干员列表 | 同宿舍的干员集合 | 5b |
| 招募位数 | Office 的招募位数量 | 2a, 2b |

### 4.4 全局状态向量

技能通过共享数据结构通信——类型 2 技能写入，类型 1f 技能读取。这是 §9 偏导数框架的核心数据对象：

```
{
  yanhuo:            int,  ← 人间烟火
  perception:        int,  ← 感知信息
  engineering_robots: int, ← 工程机器人
  monster_cuisine:    int, ← 魔物料理
  silent_resonance:   int, ← 无声共鸣
}
// 派生维度（不独立存储）:
//   wushu_crystal = yanhuo // 5
//   thought_chains = perception  (1:1)
```

### 4.5 类型概要

**类型 1（槽位效率）**：线性叠加到目标槽位的 efficiency 积分。含 13 种子类型（1a-1m），覆盖自身标量、配对、阵营计数、技能计数、设施计数、状态读取（类型 1f，读取 S[d] 变换为效率）、心情门控、时变爬升、仓库容量、效率放大、作业平台、全局阵营、跨组配对。输出形式为 `list[LinearSegment]`，积分得贡献值。

**类型 2（全局状态增量）**：修改 S 的 5 个维度（§4.4），供类型 1f 读取。写入量取决于心情门控、宿舍人数、招募位数等输入。

**类型 3（规则修正）**：改变其他技能的计算参数（全局注入、per-operator 修正、心情消耗规则）。由 Control 槽位提供，作用于全局或特定阵营/干员。

**类型 4（槽位屏蔽）**：自身输出效率同时归零同组其他槽位。求值优先级最高，必须在效率叠加前确定屏蔽集。

**类型 5（心情修正）**：5a 修改 work_burn（中枢减免、烟火联动），5b 提供 dorm_recovery（宿舍 buff 聚合，6 条聚合规则见 §3.4）。

**类型 6（订单参数）**：改变贸易站订单参数（三类机制：独占/概率/分布），不通过汇率折算。详细建模见 §1.4。现有实现：`_get_trade_order_multiplier()`。

**类型 7（纯时间加速）**：无人机缩放 effective_hours（3 分钟/架）。通过经验书锚定折算为等效 Mfg/Trade 效率（§1.4）。

> 具体的 buff_id 映射、干员列表和分类逻辑不在本文档枚举。权威来源是代码中的注册表
> （`synergy/types.py` 的 TABLES 注册器 + ArknightsGameData 的 `character_table.json`/`building_data.json`）。
> 分类规则与代码的衔接见 §8。

---

## 5. 类型 5 技能（心情修正）

类型 5a（工作时长修正）详见 §3.2；类型 5b（宿舍恢复补充）详见 §3.4。本节无独立内容。

---

## 6. 产能度量

### 6.1 生产设施（Mfg/Trade）

```
槽位产能 = base_rate × efficiency × effective_hours × drone_multiplier

base_rate       = 设施基础产出率。贸易站受类型 6 技能修正。
efficiency      = 1 + Σ(类型 1 技能输出 + 类型 3 全局注入) / 100
effective_hours = 从工作时长池分配到该槽位的小时数
drone_multiplier = 1 + drone_boost（类型 7）
```

**求值顺序**：

```
类型 4（屏蔽集） → 类型 1b/c/d（同组组成判定，不受屏蔽）
→ 类型 1a/e/f/g/h/i/j/k/l/m（效率叠加，受屏蔽槽位跳过）
→ 类型 3（全局注入）
```

**统一计价单位**：**LMD 等值/天**。赤金 = 500 LMD/个，经验通过 `xp_lmd_ratio` 参数折算（243 布局 1.3:1，153 布局 1.0:1）。

**等效制造站基准产出** `mfg_base_rate_avg`：非 Mfg/Trade 设施的 contribution 计算需要将效率折算为 LMD 等值。取制造站两种产品的加权日均产出为基准：

```
mfg_base_rate_avg = w_CR × 8000 经验/天 ÷ xp_lmd_ratio    ← CR 基准: 1个/3h, 1000经验/个
                  + w_PG × 20000 赤金等值/天               ← PG 基准: 1个/1.2h, 500LMD/赤金

权重: 243 布局下 w_CR = 0.5, w_PG = 0.5（2间CR + 2间PG）
      153 布局下 w_CR = 1.0, w_PG = 0.0（1间CR，PG 为 0）
```

该值为常数——仅依赖布局和 `xp_lmd_ratio`，不随分配变化。

### 6.2 发电站（Power）

```
Power 产能 = daily_drones × 3 min/架 × base_rate_target ÷ 60 min/h ÷ 24h/d
           × (1 if Mfg else 1/xp_lmd_ratio)  ← LMD 等值

其中 daily_drones = 240 × (1 + Σ power_efficiency / 100)
      base_rate_target = 目标槽位的 base_rate × unit_value（经验→LMD或直接LMD）
```

> 详细推导见 §1.4 无人机桥。核心结论：+1% 发电效率 ≡ +0.5% 制造站单槽效率（经验书基准）。

### 6.3 会客室（Reception）

```
Reception 产能 = Σ reception_eff × reception_to_mfg_ratio
               × mfg_base_rate_avg ÷ xp_lmd_ratio LMD等值/天

其中 reception_to_mfg_ratio = 0.10  ←  1% Reception效率 ≡ 0.1% Mfg单槽效率
     基准: 20% Reception效率 → 等效 2% Mfg效率
```

价值链路：线索搜集→信用点→信用商店(LMD/经验书)。基准折算源自玩家社区长期测算，参数化可覆写。

### 6.4 办公室（Office）

```
Office 产能 = Σ office_eff × office_to_mfg_ratio
            × mfg_base_rate_avg ÷ xp_lmd_ratio LMD等值/天

其中 office_to_mfg_ratio = 1.10   ←  1% Office效率 ≡ 1.1% Mfg单槽效率
     基准: 20% Office效率 → 等效 22% Mfg效率
```

价值链路：公招刷新→多余干员→绿票/黄票→抽卡资源→理智→CE-6(LMD)/LS-6(经验)。基准折算源自玩家社区长期测算，参数化可覆写。

### 6.5 控制中枢（Control）

控制中枢不直接产生产能。其贡献通过以下渠道间接量化：

```
Control 贡献 = Σ(写入S[d] × D[d])                          ← 类型 2 状态写入
             + Σ(类型 3 全局注入 × 受影响槽位数 × 槽位均值)  ← 类型 3
             + Σ(类型 5a burn修正 × 工作时长等值)            ← 类型 5a
```

### 6.6 宿舍（Dormitory）

```
Dormitory 贡献 = Σ(写入S[d] × D[d])              ← 类型 2 状态写入
               + Σ(recovery_rate × hours × λ)    ← 类型 5b 恢复贡献

其中 λ = 当前 Mfg/Trade 槽位的边际产出中位数（LMD等值/h）
```

### 6.7 总产能

```
P(A) = Σ Mfg/Trade 槽位产能
     + Σ Power 等效产能
     + Σ Reception 等效产能
     + Σ Office 等效产能
     + Σ Control 等效贡献
     + Σ Dormitory 等效贡献
```

所有设施在同一量纲（LMD 等值/天）下求和。

---

## 7. 心情展平

心情门控技能（类型 2 的令/夕，类型 1g 的铅踝）在窗口中的 mood 连续变化，需将离散门控展平为有效值。以下公式以窗口 w 为上下文，窗口时长为 `window_hours[w]`。

### 7.1 夕的感知有效通量

```
夕的技能: mood >= 12 → perception_delta = 10
          mood < 12  → perception_delta = 0

t_cross = (mood_initial - 12.0) / control_burn
effective_perception = 10 × min(1.0, t_cross / window_hours[w])
```

### 7.2 令的双态展平

```
令的技能: mood >= 12 → yanhuo_delta = 15
          mood < 12  → perception_delta = 10

t_switch = (mood_initial - 12.0) / burn

effective_yanhuo      = 15 × t_switch / window_hours[w]        （t_switch 在 [0, window_hours[w]] 内）
effective_perception  = 10 × (window_hours[w] - t_switch) / window_hours[w]
```

令的杯莫停（类型 3，**未实现**）消除自身消耗后 burn 降低，t_switch 延后。

### 7.3 铅踝的心情落差展平

```
落差 = 24.0 - mood_initial
有效工作时长 = mood_initial / mood_burn

模糊视线: 基础 +30%, 每 4 点落差 -5%
窗外雪啸: 落差 > 12 → +10% + 仓库+6

effective_productivity = base × effective_hours / window_hours[w]
```

---

## 8. 代码驱动分类

技能分类不由本文档人工维护，而是编码在数据加载与分类逻辑中。本文档描述分类规则——规则的真值在代码。

### 8.1 分类规则（按 buff_id 前缀 + room_type）

| 类型 | 判定规则 |
|------|---------|
| 1a | `room_type in {Mfg, Trade}` 且不在其他规则中 → `constant_efficiency(eff)` |
| 1b | 在 `_A_PAIR_TABLE` 中 → `synergy_pair()` |
| 1c | 在 `_A_ROOM_FACTION_TABLE` 中 → `synergy_faction_room()` |
| 1d | 在 `_A_SKILL_COUNT_TABLE` 中 → `synergy_skill_count()` |
| 1e | 在 `_A_FACILITY_LINK_TABLE` 中 → `synergy_facility_count()` |
| 1f | 在 `_B_BUFF_CONSUMER_TABLE` 中 → `synergy_buff_pool_consumer()` |
| 1g | `buff_id == "manu_prod_spd_reduce[000]"` 或 `"窗外雪啸"` → `stepped_efficiency()` |
| 1h | `buff_id` 匹配 `ramping_efficiency()` 的注册表 → `ramping_efficiency()` |
| 1i | `buff_id` 匹配红云/泡泡 → `synergy_capacity_to_eff()` |
| 1j | `buff_id` 匹配槐琥 → `synergy_efficiency_amplifier()` |
| 1k | `buff_id` 匹配阿兰娜机械精通 → `synergy_token_prod()` |
| 1l | 在 `_B_GLOBAL_FACTION_TABLE` 中 → `synergy_global_faction()` |
| 1m | 在 `_B_CROSS_ROOM_PAIR_TABLE` 中 → `synergy_cross_room_pair()` |
| 2 | `room_type in {Control, Trade, Mfg, Dormitory, Office}` 且 buff_id 匹配 BuffPool 生成规则 → `compute_buff_pool()` |
| 3 | `room_type == Control` 且 buff_id 匹配全局注入/规则修正规则 → `compute_mood_modifiers()` / `compute_control_global_bonus()` |
| 4 | 在 `_A_AUTOMATION_FALLBACK` / `_ZEROING_VARIANT_TABLE` / whisper 表中 → `synergy_automation()` / `synergy_zeroing_variant()` / `synergy_whisper()` |
| 5a | `room_type == Control` 且 buff_id 匹配心情消耗修正规则 → `compute_mood_modifiers()` |
| 5b | `room_type == DORMITORY` → `evaluate_dorm_recovery()` |
| 6 | `buff_id` 以 `trade_ord_closure/law/long` 开头 或 匹配裁缝 → `_get_trade_order_multiplier()` |
| 7 | `room_type == Power` 且 `efficient >= 1.0` → `_calc_drone_daily()` |

### 8.2 完备性保证

新增基建技能时，代码通过 buff_id 前缀匹配自动归入对应类型。若 buff_id 不匹配任何已知规则，日志输出警告，开发者据此更新分类规则。

---

## 附录：完备性自检

| 检查项 | 状态 |
|--------|:----:|
| 每个 Mfg/Trade 技能可归入类型 1/4/6？ | ✅ |
| 每个 Control 技能可归入类型 2/3/5a？ | ✅ |
| 每个 Dormitory 技能可归入类型 2/5b？ | ✅ |
| 每个 Power 技能可归入类型 1a/7？ | ✅ |
| 每个 Office/Reception 技能可归入类型 2？ | ✅ |
| 类型 4 求值顺序（先屏蔽后累加）？ | ✅ |
| 多技能干员跨类归属完整？ | ✅ |
| 分类规则编码在代码中（非手工维护）？ | — 待实现 |

> **注**：以上完备性自检基于人工审查。分类规则编码后（§8.1）将通过自动化完备性测试验证。

---

## 9. 决策过程推导

> **实现路线**：§9.5 的混合策略（Mfg/Trade 穷举 + Control/Dorm contribution 贪心 +
> λ bisection）已实施于 `solver/slot/solver.py`。V1 SlotIterationStrategy →
> V2 SlotSolver 的演进记录见 `archive/slot-iteration-notes.md`。
> Phase 1 归零机会成本（whisper/automation/zeroing）见 [opportunity.py](../steward_core/solver/slot/opportunity.py)。

本节从状态向量的不动点结构推导求解策略。

### 9.1 问题形式化：状态不动点

基建系统有一个**全局状态向量**（§4.5）：

```
S = { yanhuo, perception, engineering_robots, monster_cuisine, silent_resonance }
```

分配方案 A（每个槽位放哪个干员）产生两类技能求值：

```
状态写入:  若 op 有类型 2 技能 → S[d] += Δ(op, mood)
状态读取:  若 op 有类型 1f 技能 → slot_eff += f(S[d])
其他技能:  类型 1a-e/g-m（直接效率）、类型 3（全局注入）、类型 4（屏蔽）、
          类型 5（心情修正）、类型 6（订单参数）、类型 7（纯时间加速）
```

产能函数 P 同时依赖 A 和 S：

```
P(A) = Σ_{slot j} base_rate(j) × (1 + Σ eff(S, A, j) / 100) × hours × drone(A)
S = G(A)    ←  状态由分配唯一确定
```

目标：

```
max_A  P(A)  使得  S = G(A)  ←  这是一个不动点约束
```

**不动点**：分配 A 产生状态 S，P 在 S 处的值决定了哪个 A 最优——但最优的 A 又产生不同的 S。求解等价于寻找：

```
S* = G( argmax_A P(A; S = S*) )
```

### 9.2 边际价值：产能对状态的偏导数

状态维度的价值定义为 P 对该维度的偏导数：

```
D[d] = ∂P / ∂S[d]
```

偏导数**不是假设、不是价格、不是锚定值**——它是产能函数在该分配方案下的数学导数，完全由"哪些技能在读取 S[d]"决定。

**具体计算**——给定分配 A[w]，迷迭香在窗口 w 的 Mfg CR 槽位时：

```
∂P / ∂S[w][perception]
  = ∂(迷迭香所在 Mfg CR 槽位产能) / ∂S[w][perception]    ← 其他槽位不含 perception 读取
  = base_rate_CR × window_hours[w] × ∂(1 + S[w][perception]×1%/100) / ∂S[w][perception] × drone
  = base_rate_CR × window_hours[w] × 0.01 × drone
  = 0.333 经验卡/h × window_hours[w] × 0.01          ← 0% 效率基线
```

例如 window_hours[w] = 12h 时，≈ 0.04 经验卡 = 40 经验等值 / perception。

如果迷迭香不在任何槽位（没有任何技能读取 perception）：

```
∂P / ∂S[w][perception] = 0   ←  该维度在当前窗口分配下的边际价值为零
```

**这条规则自动处理了所有状态维度的估值**：偏导数的值取决于"谁在读取这个维度"——这正是游戏数据给出的数学事实，不存在"鸡生蛋蛋生鸡"的判断困境。

### 9.3 状态写入者的价值

掌握了偏导数 D 之后，任何状态写入（类型 2 技能）的贡献就可以直接计算：

```
令（mood≥12，写入 S[yanhuo] += 15）的边际价值:
  = 15 × D[yanhuo]
  = 15 × ∂P/∂S[yanhuo]
```

这个值和类型 1（+30% 制造站效率）在同一量纲——都是对 P 的增量。当 D[yanhuo] = 0（无任何技能读取 yanhuo），令的边际价值 = 0——她不会贡献任何产能。当 D[yanhuo] > 0，她的贡献自动为正。

### 9.4 与 BaselineStrategy 的本质区别

偏导数框架的核心改变：Control/Dorm 的选人从"Mfg/Trade 穷举后反向计算支撑需求"变为"正向计算 contribution = 写入量 × D[d]"，使令和阿米娅可以在同一量纲下比较。完整的对比和命题见 [§9.12](#912-与-baselinestrategy-的对比分析)。

### 9.5 状态不动点迭代（混合策略）

**根本限制**：δP/δS 是线性近似——用标量 D[d] 概括维度 d 的全部价值。对于迷迭香这种唯一状态读取者的情形这没问题，但对于**效果组内的互补配对**（迷迭香 + 令的组合价值 >> 各自单独价值之和），槽位级贪心会错过。同时纯 slot 级 contribution 无法精确处理类型 4（屏蔽）和类型 6（订单参数变换）。

**混合策略**：在组合爆炸可接受的范围（Mfg/Trade 的 C(n,3) ≤ 1140 组合）保留穷举 + 完整联动求值；在组合爆炸不可接受的范围（Control/Power/Office/Reception/Dormitory 的全局分配）用偏导数迭代传导。

#### 可持续性约束与 λ 影子乘子

跨周期可持续性（约束基线 H6）是多班次排班的核心硬约束：

```
对每名干员 op:
  Σ_w hours_used(op, w) × mood_burn ≤ mood_full
  ⇔ Σ_w hours_used(op, w) ≤ mood_full / mood_burn = pool_hard[op]
```

λ 是此约束的影子乘子（shadow multiplier），通过离散 bisection 将硬约束转化为经济信号：

| 机制 | 说明 |
|------|------|
| λ 更新 | 每轮迭代后：`hours_used > pool_hard` → λ 翻倍（收紧）；`hours_used ≤ pool_hard` 且 λ>0 → λ 减半（释放）。λ 跨迭代保持，逐步收敛 |
| λ 惩罚 | contribution 中 `- λ[op] × hours`——超池干员在所有设施中被压低评分，迭代中被替代 |
| λ 奖励 | dorm contribution 中 `+ recovery_rate × hours × λ`——λ 越高，恢复越值钱，宿舍干员获得更高优先级 |
| λ 锚定 | `λ_k = median(base_rate × efficiency × unit_value / window_hours)`——取 Phase A/B 已分配槽位的每小时边际 LMD 等值，保证 λ 与 contribution 同一量纲 |
| 收敛 | λ 的离散 bisection 保证 O(log₂(值域/粒度)) 步收敛。λ≈0 时约束全部满足，迭代终止 |

**注意**：宿舍恢复是独立资源（由 Phase D 宿舍分配竞争），不纳入 pool_hard 计算。pool_hard 仅由心情续航决定——避免"假设所有干员都能获得宿舍恢复"的过度乐观。

#### 迭代框架

```
初始化: A₀[w] = BaselineStrategy 结果逐窗口展平（热启动，默认）或 S₀_max 冷启动（见 §9.7）
        S₀[w] = G(A₀[w])
        D₀[w][d] = δP/δS[w]|_{S=S₀, A=A₀}
        λ₀[op] = 0  （初始时长池充裕假设）

循环 k (状态不动点迭代):
  对每个窗口 w ∈ [1..W]:
    ― Phase A[w]: Mfg 效果组穷举（含完整联动求值） ―
    对每间制造站效果组（CR×2 + PG×2）:
      候选人池 = {op | has_skill_for("Mfg", product)}  ← 含类型 1f 读取者
      对每个 C(n,3) 组合:
        room_production = evaluate_room(ops, "Mfg", product, power_count,
                                         window_hours[w], global_bonus, buff_pool, ...)
        ← 联动体系全链路求值（类型 4 屏蔽集、1f 读取 S[w][d]、1b/c/d 交叉条件）
      选 room_production 最高组合 → 写入 A_{k+1}[w]

    ― Phase B[w]: Trade 效果组穷举（含类型 6 精确计算） ―
    对每间贸易站效果组（×2）:
      候选人池 = {op | has_skill_for("Trade")}
      对每个 C(n,3) 组合（≤120）:
        lmd_base, gold_base, equiv = _get_trade_order_multiplier(ops)
          ← 类型 6 三类机制精确计算，O(1) 纯算术
        total_eff = 1 + Σ(类型 1a-m 效率) / 100    ← 读取 S[w][d] 含 1f 消费
                  + 类型 3 全局注入 / 100
        room_production = lmd_base × total_eff × window_hours[w]/24 × drone
        等效等值 = room_production 折算到统一尺度（§1.4 定量折算）
      选 room_production 最高组合 → 写入 A_{k+1}[w]

    ― Phase C[w]: Control 槽位贪心 ―
    候选人池 = {op | has_skill_for("Control")}
    对每个候选人 op:
      contribution(op, w) = Σ(写入 S[w][d] × D_k[w][d])         ← 类型 2 状态写入
                          + 类型 3 全局注入 × 受影响槽位数
                          + 类型 5a burn 修正 × 工作时长等值
                          - λ_k[op] × window_hours[w]           ← 工作时长池约束
    对每个 Control 槽位，选 contribution 最高 → 写入 A_{k+1}[w]

    > **设计决策：类型 3 全局注入的后置求值**。Phase C 在 Phase A/B 之后执行，"受影响槽位数"
    > 取已填充的 Mfg/Trade 槽位精确值，无循环依赖。后置的另一层意图是让类型 3 注入者
    > （阿米娅 +42% Trade、杜宾 +30% 三星 Mfg 等）获得其完整边际价值评估——它们的贡献
    > 乘以精确槽位数后可能远超单个 Control 槽位的替代者。下一轮迭代中，Phase A/B 将
    > 在类型 3 注入生效的条件下重算穷举，排序可能改变，从而制造推翻当前局部最优的扰动。
    > 类型 3 注入是分段常数的（生效或不生效），此性质保证扰动不会产生需要阻尼更新的连续振荡。
    > **跨 Phase 机会成本**：24 名 Control 干员中仅森蚺同时持有 Mfg 生产技能（自动化），
    > 概率性忽略；其余 23 人均为纯中枢定位，无 Mfg/Trade 直接效率可被放弃。

    ― Phase D[w]: Power/Office/Reception/Dormitory 槽位级贪心 ―
    对每个槽位 j（按 facility_type 分支）:

    **Power**:
      contribution(op, w) = Σ(写入S[w][d] × D_k[w][d])              ← 类型 2
                          + power_eff × drone_to_mfg_ratio           ← 类型 7，§6.2
                          × mfg_base_rate_avg ÷ xp_lmd_ratio         ← LMD等值
                          - λ_k[op] × window_hours[w]               ← 时长池约束

    **Reception**:
      contribution(op, w) = Σ(写入S[w][d] × D_k[w][d])              ← 类型 2
                          + reception_eff × reception_to_mfg_ratio   ← §6.3
                          × mfg_base_rate_avg ÷ xp_lmd_ratio         ← LMD等值
                          - λ_k[op] × window_hours[w]

    **Office**:
      contribution(op, w) = Σ(写入S[w][d] × D_k[w][d])              ← 类型 2
                          + office_eff × office_to_mfg_ratio         ← §6.4
                          × mfg_base_rate_avg ÷ xp_lmd_ratio         ← LMD等值
                          - λ_k[op] × window_hours[w]

    **Dormitory**:
      contribution(op, w) = Σ(写入S[w][d] × D_k[w][d])              ← 类型 2
                          + recovery_rate × window_hours[w] × λ_k   ← 类型 5b
                          - λ_k[op] × window_hours[w]               ← 时长池约束

    参数默认值（工程常量，用户可覆写）:
      reception_to_mfg_ratio  = 0.10      ← 1% Reception ≡ 0.1% Mfg 单槽
      office_to_mfg_ratio     = 1.10      ← 1% Office ≡ 1.1% Mfg 单槽
      xp_lmd_ratio            = 1.3(243) / 1.0(153)
      drone_to_mfg_ratio      = 0.5       ← 1% Power ≡ 0.5% Mfg 单槽，§1.4
      λ_k                     = median(base_rate × efficiency × unit_value / window_hours[w])
                                （当前轮 Phase A/B 已分配槽位的每小时边际 LMD 等值）

    选 contribution 最高 → 写入 A_{k+1}[w]

  ― Step 更新: 从 A_{k+1}[w] 计算新状态和偏导数 ―
  S_{k+1}[w] = G(A_{k+1}[w])
  D_{k+1}[w][d] = δP/δS[w]|_{S=S_{k+1}, A=A_{k+1}}

  ― λ 更新: 影子乘子（离散 bisection） ——
  检查 Σ_w hours_used(op, w) ≤ pool_hard[op]（可持续性约束，见上文）:
    若违反: λ ← λ × 2  （若 λ=0 则设初始步长 hourly_value × 0.25）
    若满足且 λ > 0: λ ← λ / 2
  λ 跨迭代保持，O(log₂(值域/粒度)) 步收敛。

  ― 记忆与收敛检查 ―
  V_{k+1} = V_k ∪ {A_k}                                  ← 记录已访问状态

  while P(A_{k+1}) <= P(A_k) 或 A_{k+1} ∈ V_{k+1}:      ← 退化、同 P、或重访
    A_{k+1} = 探索 N(A_k) \ V_{k+1} 中下一个可行分配
    若 N(A_k) \ V_{k+1} = ∅:
      ― 联合扰动: 攻击跨 Phase 鞍点 ―
      耦合对 = 所有 (1f读取者所在房间, 写入其消费维度的类型2写入者所在槽位)，
              合计 ~25 对（迷迭香↔令/夕/絮雨/...，黍/桑葚/乌有↔令/重岳/...）
      对每个耦合对:
        A' = A_k 副本，同时替换读者（top-3 替代者）和写入者（top-3 替代者）
        若 P(A') > P(A_k): A_{k+1} = A', V_{k+1} = V_{k+1} ∪ {A_k}，回到 while 循环
      若所有耦合对均无提升: 终止于 A_k（关于 N(A) + 耦合对的局部最优）

  若 k ≥ K_max: 终止                                      ← 性能上限（可选，非正确性依赖）
  否则 k ← k+1，回到窗口循环

  收敛性保证: 见 §9.11 定理证明

#### 邻域结构

当记忆触发"探索下一个可行分配"时，搜索范围限定在 A_k 的邻域 N(A_k) 内：

```
N(A) = ∪_{w, phase} { A' | A' 与 A 仅在窗口 w 的 phase 内不同，使用该 phase 的 top-K 候选 }
```

| Phase | 搜索空间 | top-K | 每窗口邻域子集大小 |
|-------|:------:|:-----:|:----------:|
| Mfg CR | C(n,3) | 3 | ≤ 3M (M=制造站 CR 间数) |
| Mfg PG | C(n,3) | 3 | ≤ 3M |
| Trade | C(n,3) | 3 | ≤ 3M (M=贸易站间数) |
| Control | n | 3 | ≤ 3×5 槽位 |
| Power | n | 3 | ≤ 3×3 槽位 |
| Office | n | 3 | ≤ 3×1 槽位 |
| Reception | n | 3 | ≤ 3×1 槽位 |
| Dormitory | n | 3 | ≤ 3×20 槽位 |

总 |N(A)| ≤ W × 1800（W=窗口数）。Top-K 候选为各 Phase 内按产能/contribution 降序的前 K 个选择。

**性质**：若存在 A' ∈ N(A) 使得 P(A') > P(A)，则记忆机制在至多 |N(A)| 次尝试内找到提升。若 N(A) 中无可提升分配 → A 是关于此邻域的**局部最优**。

精确求值:
  按最终 A*，调用 evaluate_room 逐房间计算真实产能
  （含心情展平 §7、爬升积分、完整跨槽位约束）
```

#### 偏导数的具体计算规则（在 Step 更新 执行）

```
对每个窗口 w、每个全局状态维度 d:
  D[w][d] = 0
  遍历窗口 w 中 Phase A/B 已分配的 Mfg/Trade 槽位:
    若该槽位干员有类型 1f 技能读取 S[w][d]:
      D[w][d] += base_rate × window_hours[w] × 换算率 × drone / 100

例如 perception:
  窗口 w 中迷迭香在 Mfg CR → D[w][perception] += base_rate_CR × window_hours[w] × 0.01 × drone
  无其他 perception 读者 → D[w][perception] 等于上述单项
```

#### 为什么 Mfg/Trade 保留穷举而其余设施只需要 contribution

| 设施 | 每效果组候选数 | C(n,3) | 必须穷举的原因 |
|------|:---------:|:-----:|--------------|
| Mfg CR | ≤20 | ≤1140 | 类型 4 屏蔽（森蚺/温蒂）是效果组级决策；1f 读取者（迷迭香/黍/截云）无直接效率，需组合探索 |
| Mfg PG | ≤10 | ≤120 | 同上（阿兰娜/温米配对等） |
| Trade | ≤12 | ≤220 | 类型 6（可露希尔/但书/龙舌兰）只能房间级求值；孑订单压缩是效果组级 |
| Control | ≤15 | — | 无效果组级约束（每槽位独立），偏导数 D 传导足够 |
| Power | ≤8 | — | 纯 drone 贡献，无跨槽位互补 |
| Office | ≤5 | — | 单槽位 |
| Reception | ≤6 | — | 单槽位 |
| Dormitory | ≤30 | — | 4 间各 5 槽，状态写入 vs 恢复 buff 通过 D 和 λ 权衡，组合搜索无收益 |

#### 为什么不需要供过于求/供不应求的价格调整

偏导数是 P 在**当前分配 S 点**的真实斜率，不是假设的市场价格。新增 1 单位 yanhuo 带来的额外产能就是 δP/δS[yanhuo] 本身——不因为 yanhuo 的总量"太多"而打折。如果所有读取 S[d] 的技能都有消费上限（如迷迭香的 thought_chains 通过 perception 1:1 转换后，意识实体对 thought_chains 的消费无上限），偏导数不会随 S 增大而归零，只会随"读取者被挤出槽位"而变为 0。

### 9.6 负反馈机制

移除令之后，S[perception] 下降（少了 +10）。偏导数 D[perception] 本身**不因此改变**——它仍然由迷迭香的转换率决定。但总产能 P 下降了：

```
ΔP[w] = ΔS[w][perception] × D[w][perception]
```

例如 window_hours[w]=12h 时，ΔP[w] = -10 × 0.04 经验卡 = -0.4 经验卡。总产能影响为 Σ_w ΔP[w]。

这个下降在下一轮迭代中自动表达：令在 Control 的 contribution = 10 × D[perception]（仅 perception 项，yanhuo 同理）仍然是正值。她与阿米娅在 Control 槽位上直接比较——偏导数框架**不需要令有非 Control 技能**，它只需要知道令在 Control 的边际价值是否高于她的竞争对手。

若阿米娅的 42% Trade 等值 > 令的状态写入总值，令被挤出 Control——如果她无处可去（仅有 Control 技能且槽位已满），这是正确的。迷迭香承受 10% 效率损失，但被阿米娅的全局注入超额补偿。反之若令的总值更高，迭代会让她保持在 Control。

### 9.7 初始分配与冷启动

所有类型 1f 读取者（迷迭香、黍、乌有、截云）的**直接效率为 0**——其贡献完全来自状态读取。若 D=0（无状态读取者在场），他们永远不会被选中。纯空分配无法自举。

**解决方案**：第一轮使用**潜在 S 上界**计算 D，不依赖实际分配。

#### S₀_max 初始化

```
对每个全局状态维度 d:
  S_max[d] = 所有可用类型 2 写入者的最大可能增量（仅计入不依赖其他分配的独立项）

  S_max[perception]:
    令(mood<12): +10
    夕(mood>12): +10           ←  仅取心情门控的最优区间
    迷迭香念力:  +5 (假设 5 人宿舍)  ←  保守估计宿舍填充
    黑键倚音:    +5
    爱丽丝梦境:  +5 (假设 Lv5 宿舍)
    车尔尼琴键:  +5
    絮雨巡游:   +20 (假设 2 招募位)
    S_max[perception] ≈ 60

  S_max[yanhuo]:
    令(mood≥12): +15
    夕(mood<12): +15
    重岳知我:    +25 (假设 5 岁干员在场)
    乌有市井:    +5  (假设 5 人宿舍)
    桑葚慈悲:    +30 (假设 3 招募位)
    塑心:        +5
    S_max[yanhuo] ≈ 95

  S_max[engineering_robots]:  = 64  ←  至简等所有可用机器人等级和，上限 64
  S_max[monster_cuisine]:     = 5   ←  森西，Lv5 宿舍
  S_max[silent_resonance]:    = 10  ←  塑心 5 + 黑键 echo 5

D₀[w] = δP/δS[w]|_{S=S_max}    ←  基于此上界计算各窗口偏导数
```

**为什么 S_max 不会过度高估**：D 是**分段常数**——它只取决于"谁在读取 S[d]"，与 S[d] 的实际值无关。迷迭香在 Mfg CR → D[w][perception] = base_rate_CR × window_hours[w] × 0.01 × drone。S=60 和 S=10 时 D 完全相同。D 的值只随分配变化（读取者入场/退场）。

#### 多启动策略

```
启动点 1: BaselineStrategy 结果（热启动，默认）
启动点 2: S₀_max（冷启动，全部状态维度乐观上界）
启动点 3-5: 随机可行分配（增加覆盖度）

对每个启动点运行状态迭代 → 取 max P(A*)
```

冷启动的开销 ≈ 5 轮迭代 ≈ 5 × W × (Mfg 1140×4 + Trade 220×2 + Control 15×5 + 其余 30) ≈ 5W × 6000 次轻量评估（W=窗口数）。每窗口每轮穷举已在 Phase A/B 完成，总计算量可控。

### 9.8 （已合并至 §9.5）

原多窗口扩展的内容（A[w]/S[w]/D[w][d] 窗口化、λ 影子乘子、离散 bisection）已融入 §9.5 迭代框架的窗口循环与 λ 更新步骤。本节保留编号，无独立内容。

### 9.9 策略选择

| 场景 | 推荐策略 |
|------|---------|
| 默认 | 热启动：A₀ = BaselineStrategy 结果逐窗口展平 → 混合状态迭代（§9.5） |
| 追求最优性 | 多启动（热启动 + S₀_max 冷启动 + 随机×3）→ 取 max P(A*) |
| 无法热启动 | S₀_max 冷启动 → 混合状态迭代 |
| 验证框架正确性 | 收敛解 vs 小规模全穷举对比 |

### 9.10 已知缺陷与边界条件

#### 收敛性：局部最优而非全局最优

记忆机制（§9.5, §9.11）保证算法有限步终止于关于 Phase 分解邻域 N(A) 的局部最优——即"任何单 Phase 改变都无法提升 P"。联合扰动（§9.5 记忆检查末尾）将邻域扩展至已知的跨 Phase 耦合对（类型 1f 读取者 ↔ 类型 2 写入者，~25 对），进一步缩小潜在鞍点范围。坐标下降在非凸分配空间上不能保证全局最优，多启动策略增加覆盖度但非穷举。

> **理论完备性备份**：若联合扰动仍遗留不可接受的 gap，可将耦合干员（迷迭香、桑葚、乌有、黑键）的角色分配（读者 vs 写入者）作为顶层枚举——仅 16 条分支，内层迭代因无耦合而收敛更快。此方案在本文档中保留论证但不实现，待实证验证确定必要性后启用。

#### 邻域覆盖度：共享 BaselineStrategy 的限制

N(A) 定义（§9.5）将邻域限定为单 Phase 变化 + 联合扰动覆盖的跨 Phase 耦合对（~25 对）。若存在未覆盖的鞍点——如必须同时改两个不在耦合对清单中的 Phase 才能提升 P——则 N(A) 无法发现该提升。耦合对清单覆盖了所有已知的类型 1f 读取者—类型 2 写入者关系，未覆盖的鞍点概率极低。BaselineStrategy（无迭代单次通过）同样受此限制。

#### 状态维度有限性

偏导数框架覆盖 5 个全局状态维度（yanhuo, perception, engineering_robots, monster_cuisine, silent_resonance）。对于这些维度以外的跨槽位耦合（如烈夏检查古米在 Trade 的跨组配对 1m），contribution 函数检查目标槽位分配状态来做近似——这不如穷举精确但在此规模下可接受。

#### 心情门控依赖展平预处理

令/夕/铅踝的心情门控在偏导数计算前由 §7 的心情展平预处理为连续有效值。若未来出现更复杂的门控（如"mood 在区间 [8,16] 时触发"），展平的精度需重新评估。

#### D[d] 分段常数的例外

§9.7 指出 D[d] 是分段常数——仅当读取者入场/退场时才变化。截云（`wushu_crystal = yanhuo // 5`）在 S[yanhuo] 跨越 5 的倍数时 D 突变。至简的 `engineering_robots // 8` 在满级布局中恒为 64（触及代码上限 64），消费量恒为 40%，不构成例外。工程上可接受（仅影响类型 2 写入者的初始估值，迭代会修正）。

#### 冷启动：可选加速手段

S₀_max 冷启动（§9.7）的 D₀ 基于"所有类型 2 写入者均在场"的乐观假设，可能高估某些状态维度的边际价值，导致首轮分配偏向类型 1f 读取者。此偏向在后续迭代中可能被修正，也可能因槽位级贪心逐轮不可回退而固化。

然而冷启动并非正确性依赖——以 BaselineStrategy 结果热启动（A₀ = BaselineStrategy 结果）可保证 P_new ≥ P_BL（§9.12 命题）。冷启动的角色是可选加速手段：当它导向更高不动点时提供额外收益，失败时热启动兜底。多启动策略（§9.7）进一步增加覆盖度。建议默认使用热启动，冷启动作为可选的"追求最优性"开关。

#### 与 BaselineStrategy 的兼容性

混合策略的 Mfg/Trade 穷举阶段约 80% 代码可复用 BaselineStrategy 的 `exhaust_mfg`/`exhaust_trade`。Control/Power/Office/Reception/Dormitory 的 contribution 贪心需要新实现（约 200 行），但每个槽位的评估函数是现有的 `best_efficiency()` + D 向量的线性叠加。

#### 框架适用边界

| 有效覆盖 | 精度说明 |
|---------|---------|
| 类型 1a-m（效率 + 状态读取 + 跨槽位配对） | Mfg/Trade 通过 evaluate_room 精确；其余通过 contribution 近似 |
| 类型 2（状态写入） | 通过 D[d] 估值 + S₀_max 冷启动 |
| 类型 3（全局注入/规则修正） | 直接计入 contribution 或 evaluate_room；per-operator 规则在 contribution 阶段用当前分配近似 |
| 类型 4（屏蔽） | 在 Mfg 效果组穷举中精确处理 |
| 类型 5（心情修正） | work_burn 通过工作时长等值计入，dorm_recovery 通过 λ 权衡 |
| 类型 6（订单参数） | 在 Trade 效果组穷举中精确处理 |
| 类型 7（无人机） | drone 等值计入 contribution，经验书锚定 |
| Office 直接效率 | 通过凭证→理智→关卡链折算为等效 Mfg 效率（§6.4），参数化 |
| Reception 直接效率 | 通过信用商店链折算为等效 Mfg 效率（§6.3），参数化 |
| 跨产品比较 | xp_lmd_ratio 参数化（§1.4），默认 243:1.3, 153:1.0 |

---

### 9.11 记忆机制与收敛性证明

#### 9.11.1 记忆的数学定义

定义**记忆增强转移函数** T_mem。在原始转移 T（§9.5 循环体）的基础上，T_mem 维护一个已访问状态集合 V：

```
T_mem(A_k, V_k):
  (A_next, _) = T(A_k)                          ← 原始一步转移
  V_{k+1} = V_k ∪ {A_k}

  while P(A_next) <= P(A_k) 或 A_next ∈ V_{k+1}: ← 退化、同 P、或重访
    A_next = 探索 N(A_k) \ V_{k+1} 中下一个可行分配
    若 N(A_k) \ V_{k+1} = ∅: return (A_k, "local_optimum")

  return (A_next, V_{k+1})
```

其中 N(A) 为 §9.5 定义的 Phase 分解邻域，|N(A)| ≤ 1800。

**V 集合的等价性定义**：A₁ ≡ A₂ 当且仅当它们在每个槽位的干员分配完全相同——即标准化为槽位 ID → 干员 ID 的映射后逐键比较。热启动时，BaselineStrategy 的房间级分配（RoomAssignment）展平为槽位映射后加入 V。此定义保证不同表示形式（房间捆绑 vs 逐个槽位）在比较前归一化。

#### 9.11.2 有限终止性定理

**定理**：T_mem 必定在有限步内终止于一个关于邻域 N(A) 的局部最优解。

**证明**：

1. **P 的值域有限**。P 是有限分配空间上的函数——干员池有限、槽位有限、窗口数有限，因此可行分配数量有限。P 将每个分配映射到一个实数值，像集 Im(P) ≤ 可行分配数，必然有限。

2. **P 严格单调递增**。统一 while 条件保证任何 P(A_next) ≤ P(A_k) 或已访问重访均被拒绝——算法持续探索邻域直到找到严格更优且未访问的分配，或邻域耗尽。while 循环放行后必有 P(A_next) > P(A_k)。因此每一步 P 严格上升。

3. **有限上升链必终止**。有限值域上的严格递增序列长度 ≤ |值域(P)|。因此迭代次数有上界，算法必然终止。

**实务收敛速度**：理论上 |Im(P)| 可能较大（效率颗粒度为 1%，Σ eff 可取数百种值），但实战中收敛轮数不由值域密度决定——由坐标下降的几何结构决定。两个实务因子进一步压缩了有效步数：

- **1 小时换班颗粒度**。`hours ∈ {1, 2, ..., 24}`，base_rate × hours 的有效组合仅约 20 种。在离散小时域上，每个有效 `effective_hours` 为整数，进一步粗化了 P 的值域，收敛步数被约束在一个远比 |Im(P)| 小的上界内。
- **邻域规模**。|N(A)| ≤ 1800，且 D 反馈通常在 2-3 轮后稳定（因为 Mfg/Trade 穷举结果不会剧烈变动）。剩余步数来自 Control ↔ Dorm 的来回调整，而非在值域中缓慢爬升。

因此 §9.13 预期热启动 1-2 轮、冷启动 ≤5 轮收敛，这不是依赖值域稀疏的乐观估计，而是邻域结构 + D 稳定速率联合给出的工程判断。

**注释**：
- 此证明不依赖迭代上限 K_max（K_max 退化为纯性能优化）。
- 此证明不依赖 D 向量是否稳定（D 稳定是收敛的**表现**，而非收敛的**原因**）。
- 空间代价：每轮记录一个分配 A（约 50 个干员名 → 数百字节），总空间 ≤ |值域(P)| × |A|，远小于可行分配空间。

#### 9.11.3 终止状态的类型保证

当 T_mem 终止于 A* 时，while 循环的条件 `P(A_next) <= P(A_k) 或 A_next ∈ V_{k+1}` 对所有邻域中的分配均触发——除非邻域耗尽（含联合扰动耗尽）。因此终止时满足：**对于邻域 N(A*) 及联合扰动覆盖的耦合对中的任意未访问分配 A'，有 P(A') ≤ P(A*)**。这等价于：**不存在任何单 Phase 改变或已知耦合对联合替换能严格提升总产能**。

#### 9.11.4 假设清单

以下假设全部可逐条验证。H1-H2 由游戏系统保证，H3-H4 为建模假设：

| # | 假设 | 状态 | 验证方式 |
|:--:|------|:----:|---------|
| H1 | 干员池和槽位数均有限 → 分配空间有限 | ✅ 游戏保证 | 无需额外验证 |
| H2 | P 的值域有限（分配空间有限 → Im(P) 有限） | ✅ 游戏保证 | 无需额外验证 |
| H3 | N(A) 中 top-K 候选覆盖了单 Phase 内所有可能的 P 提升 | ⚠️ 共享限制 | K 增大可逼近完全覆盖，K=3 为工程折衷 |
| H4 | D[d] 分段常数（仅当读取者入场/退场时变化） | ⚠️ 有例外 | 截云 yanhuo//5 阶梯在 §9.10 已登记，至简经验证为常数 |

H3 和 H4 是坐标下降路径上的固有边界——它们与 BaselineStrategy 共享，不是新模型引入的新限制。详见 §9.12。

---

### 9.12 与 BaselineStrategy 的对比分析

#### 核心差异

| 维度 | BaselineStrategy | 混合状态迭代（本文档） |
|------|-----------------|----------------------|
| 基本单元 | 房间（3 槽位捆绑） | 槽位（通过效果组穷举 + contribution 贪心） |
| 状态技能估值 | 从 Mfg/Trade combo 反向计算支撑需求（`compute_optimal_support()`） | 正向：写入量 × D[d]，与直接效率同一量纲 |
| Control 选人时机 | Mfg/Trade 穷举后一次性决定 | 每轮迭代重新评估，D 反馈传导 |
| 反馈机制 | 无（一次通过） | D → contribution → 新分配 → 新 D（闭合反馈环） |
| 终止保证 | 无（单次通过，不保证是任何意义上的最优） | 记忆保证有限步终止于邻域局部最优（§9.11） |
| 令 vs 阿米娅 | 不可比——在不同阶段被选择 | 可比——D-based contribution 直接比较 |
| 窗口化支持 | 每窗口独立求解，时长池不可见 | D[w][d] + λ 乘子，工作时长池跨窗口耦合（§9.5） |

#### 解质量关系

**命题**：设 P_BL 为 BaselineStrategy 的解质量，P_new 为混合状态迭代（多启动取 max）的解质量，则 P_new ≥ P_BL。

**论证**：新模型的第一轮迭代中，Control 使用 D₀-based contribution 选人（而非 `compute_optimal_support()`），但 Mfg/Trade 穷举逻辑与 BaselineStrategy 同构。令第一轮结果为 P₁。若 P₁ ≥ P_BL，由记忆保障的单调性（§9.11.2）得 P_new ≥ P₁ ≥ P_BL。若 P₁ < P_BL（因 Control 选人差异），以 A₀ = BaselineStrategy 结果热启动可保证 P_new ≥ P_BL。

**实务提升**：提升幅度取决于"BaselineStrategy 的 Control 选人与 D 反馈修正后的 Control 选人之间的产能差异"。典型场景——当 Mfg/Trade 中有类型 1f 读取者时，D 反馈能纠正 support 需求计算中的方向性偏差。多窗口下优势被工作时长池耦合放大，详见下文。

#### 共享限制

新模型与 BaselineStrategy 共享以下限制（非新模型引入）：

| 限制 | 说明 |
|------|------|
| 坐标下降框架 | 每次改一个 Phase，可能漏掉需同时改多 Phase 的鞍点 |
| Phase 分解邻域 | N(A) 限定为单 Phase top-K 候选 |
| H3 邻域覆盖度 | K=3 可能未穷尽单 Phase 内所有 P 提升 |

**关键**：新模型在同等限制下，通过 D 反馈迭代 + 记忆保障单调性，比 BaselineStrategy 能探索更多有效配置。它不是突破限制，而是在限制内走得更远。

#### 窗口化放大效应

D 反馈迭代的核心优势——修正 Control 选人——在多窗口下被**工作时长池耦合**放大：每窗口独立求解时跨窗口时长池约束完全不可见；λ_op 影子乘子（§9.5 λ 更新）自动传导稀缺性。设 δ 为基础 D 反馈修正带来的提升，W 个窗口下相对优势随窗口数递增——窗口越多、时长池越紧张，λ_op 的耦合效应越强。以上为理论估计，L4 实证验证将提供真实数据。

---

### 9.13 实证验证计划

以下验证分层递进，默认在多窗口场景（2 × 12h + 8h 休息）下执行。

#### L0：收敛行为

**方法**：在 10+ 真实玩家数据集上运行窗口化混合状态迭代，记录 (k, P, S[w], D[w], λ) 轨迹。

**验证项**：
- 每轮 P 是否严格单调递增（确认记忆机制正确实现）
- 收敛所需轮数分布（均值、中位数、最大值）
- D[w] 和 λ 向量变化轨迹（确认收敛时稳定）

**预期**：热启动 1-2 轮收敛，冷启动 ≤5 轮收敛。

#### L1：解质量对比

**方法**：相同数据集上 BaselineStrategy（每窗口独立）vs 窗口化混合状态迭代（热启动 + 冷启动多启动）的 P 成对比较。

**验证项**：
- P_new / P_BL - 1 的分布（均值、中位数、p99）
- 提升为 0 的案例比例及原因分析
- 是否出现 P_new < P_BL（应不出现，若出现则表明 bug）

#### L2：启动点敏感性

**方法**：在 10 个数据集上，比较以下启动方式下的最终 P：
- BaselineStrategy 结果逐窗口展平（热启动）
- S₀_max（冷启动）
- S₀ = 0（悲观初始化）
- 随机可行分配 ×3

**验证项**：
- 不同启动方式下 P 的均值和方差
- 不同启动方式是否收敛到相同不动点
- 单一启动（热启动）是否已足够（若够，多启动退化为可选优化）

**预期**：热启动在所有场景中一致最优或接近最优。

#### L3：小规模穷举验证

**方法**：构造小型干员池（≤20 人，覆盖主要联动体系），全穷举所有可行分配，将全局最优 P* 与迭代结果 P_iter 比较。

**验证项**：
- 最优性间隙 gap = (P* - P_iter) / P* 是否可接受（目标 < 1%）
- 多启动是否缩小 gap

**难度**：中等。需实现小规模全穷举器，子集构造需覆盖代表性联动体系（至少含 1f 读取者 + 类型 4 屏蔽 + 类型 6 订单）。

#### L4：λ 收敛行为

**方法**：在 2 × 12h + 8h 休息场景下，运行窗口化混合状态迭代，记录 λ_op 轨迹。

**验证项**：
- λ 乘子阻尼更新的收敛行为（确认不振荡）
- 工作时长池约束是否在收敛解中满足
- 离散 bisection 替代方案 vs 阻尼更新的收敛速度对比

---


