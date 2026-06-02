# 技能建模缺口清单

> 基于 `character_identity.json` + `buffs_infrastructure.json` + `buffs_non_production.json` (2026-06-02 逐条核实)。
> 仅列出**产值相关**设施（Mfg/Trade/Control/Power/Reception/Office）。
> 训练室/加工站/宿舍无产值影响，不在此列。

## 一、制造站 Mfg — 143 条中 ~5 条未建模 (97%)

### 1.1 爬升型效率已全量建模（5 条，全部已修复 ✅）

`manu_prod_spd_addition[*]` 系列技能已全部通过 `_RAMPING_SKILL_TABLE` 覆盖。

| buff_id | 基础效率 | 爬升规则 | 持有者 | 现状 |
|---------|----------|----------|--------|------|
| `manu_prod_spd_addition[100]` | 0% | +2%/h → 上限 20% | 阿罗玛 | 已建模 |
| `manu_prod_spd_addition[030]` | 20% | +1%/h → 上限 25% | 芬 | ✅ 已修复 (2026-06-02) |
| `manu_prod_spd_addition[031]` | 20% | +1%/h → 上限 25% | 刻俄柏 | ✅ 已修复 (2026-06-02) |
| `manu_prod_spd_addition[040]` | 15% | +2%/h → 上限 25% | 克洛丝 | ✅ 已修复 (2026-06-02) |
| `manu_prod_spd_addition[041]` | 15% | +2%/h → 上限 25% | 稀音 | ✅ 已修复 (2026-06-02) |

### 1.2 心情落差条件型（1 条）

| buff_id | 效果 | 现状 |
|---------|------|------|
| `manu_prod_spd_addition&cost[000]` | 心情落差 >12 → +10% + 仓库+6 | eff=0，需心情上下文 |

### 1.3 注记

- `manu_token_prod_spd[000]/[010]`（阿兰娜·机械精通）：每台作业平台→PG+5/10%，**已在 `_TOKEN_PROD_TABLE` 中完全建模**。
- `manu_prod_spd_addition&cost[000]` 的 "仓库+6" 部分已通过 `Skill.capacity_bonus` 自动计入，仅效率部分未建模。

---

## 二、贸易站 Trade — 117 条中 ~4 条未建模 (97%)

### 2.1 跨房间条件型 ✅ 已全量修复

| 干员 | buff_id | 效果 | 现状 |
|------|---------|------|------|
| 深巡 | `trade_ord_spd_ext[000]` (E0) | 基础 +25%，乌尔比安在基建 +5% | `_B_CROSS_ROOM_PAIR_TABLE` 中已有 |
| 深巡 | `trade_ord_spd_ext[001]` (E2) | 基础 +30%，乌尔比安在基建 +10% | 同上 |
| 贝洛内 | `trade_ord_spd_ext[020]` (E0) | 基础 +25%，伺夜在基建 +5% | ✅ 已修复 (2026-06-02) |
| 贝洛内 | `trade_ord_spd_ext[021]` (E2) | 基础 +30%，伺夜在基建 +10% | ✅ 已修复 (2026-06-02) |

> 基础效率部分已通过 `operator_estimated_efficiency` 覆盖。跨房间加成（E2: 10%）已通过 `_B_CROSS_ROOM_PAIR_TABLE` 建模。slot 求解器中 Trade 阶段在 Mfg 之后执行，`all_assignments` 已包含 Mfg 分配，cross-room 加成在 `evaluate_room` 中自动生效。注：CrossRoomPairEntry 不区分精英阶段，E0 时 bonus 值偏高 5pp，为已知简化。

### 2.2 心情消耗配对（1 条，P1 心情范畴）

| buff_id | 效果 | 现状 |
|---------|------|------|
| `trade_ord_limit&cost_P[020]` | 伺夜同房时 -0.1/h | mood_flow P1 待接入 |

### 2.3 注记

- `trade_ord_spd_bd_n2[100]` **不存在于任何数据文件**。`trade_ord_spd_bd_n2[000]`（乌有）已在 BuffPool 消费者表中。
- `trade_ord_spd_ext[010]` **不存在**。

---

## 三、控制中枢 Control — 95 条中 ~9 条待建模 (96% 产值覆盖)

### 3.1 产值影响（1 条，唯一直接缺口）

| 干员 | buff_id | 效果 | 难度 |
|------|---------|------|------|
| 丰川祥子 | `control_prod_bd_spd[000]` (E0) | 每 20 点热情值 → PG 制造 +0.5% | 🔴 需建 Mujica BuffPool 维度 |
| 丰川祥子 | `control_prod_bd_spd[010]` (E2) | 每 20 点热情值 → PG 制造 +1% | 同上 |

> 热情值生产者：若叶睦(+20)、三角初华(+1/宿舍)、八幡海铃(+10)、祐天寺若麦(+10)。全中枢凑齐上限 ~60 点 → E2 +4% PG。

### 3.2 心情偏差（8 条，已记入 inbox）

见 `docs/inbox.md`「中枢心情建模补充」条目。

### 3.3 故意排除（26 条）

| 类别 | 条数 | 原因 |
|------|------|------|
| 线索派系/倾向 (`control_clue_*`) | 6 | 与产值无关 |
| 训练速度 (`control_train_spd`) | 3 | 求解器不分配训练室 |
| 心情消耗通用近似 (`control_mp_cost` + `control_mp_cost&faction`) | 17 | 已通过 `len(control)×0.05` 公式近似 |

---

## 四、发电站 Power — 48 条中 ~2 条未建模 (96%)

### 4.1 爬升型充电（2 条）

| 干员 | buff_id | 基础效率 | 爬升规则 |
|------|---------|----------|----------|
| 空构 | `power_rec_spd&addition[000]` | 10% | +1%/h → 上限 15% |
| 空构 | `power_rec_spd&addition[001]` | 15% | +1%/h → 上限 20% |

> 基础效率部分已覆盖，爬升增量未建模（Power 目前无 `operator_ramp_segments` 调用）。

### 4.2 故意排除（1 条）

| buff_id | 效果 | 原因 |
|---------|------|------|
| `power_rec_spd_P[001]` | 逻各斯在训练室时 +5% | 训练室 NON_WORK_FACILITY |

### 4.3 注记

- `power_rec_spd_NotGuard[000]` **无持有者**（不存在于 `character_identity.json` 中）。
- `power_rec_spd_ext&faction[001]` **不存在**；仅 `[000]` 属于 CONFESS-47，已通过 `_power_conditional_bonus` 覆盖。
- `power_rec_spd_ext&faction[000]`（CONFESS-47）已在 `_power_conditional_bonus` 中。

---

## 五、会客室 Reception — 87 条中 ~22 条未建模 (75%)

### 5.1 故意排除（17 条，与产值无关）

| 类别 | buff 前缀 | 条数 | 原因 |
|------|----------|------|------|
| 线索派系倾向 | `meet_team` | 5 | 与产值无关 |
| 线索派系补偿 | `meet_flag` | 5 | 与产值无关 |
| 线索拥有偏向 | `meet_spd_notOwned` | 5 | 与产值无关 |
| 线索拥有偏向 | `meet_spd_Owned` | 1 | 与产值无关 |
| 线索交流期间 | `meet_spd&exchange` | 2 | 无交流状态上下文 |
| 连续消耗后必定获得 | `meet_spd&condChar_mustget` | 2 | 需追踪连续消耗状态 |

> 以上 17 条全部为线索获取机制，无生产项影响。

### 5.2 条件型效率未覆盖（1 条）

| 干员 | buff_id | 效果 | 现状 |
|------|---------|------|------|
| 复奏 | `meet_spd&cost_condChar[021]` | solo → +35% + 心情消耗 +1/h | `_RECEPTION_CONDITIONAL` 表中缺少此条目 |
| 赫雅克 | `meet_spd&condChar_mustget[000]` | solo → solo +35% + **连续消耗>16 心情后下次必定莱茵** | 基础 solo 效率已被 [000] 覆盖；必定获得机制无追踪 |
| 奥达 | `meet_spd&condChar_mustget[100]` | 同上 → 罗德岛制药 | 同上；必定获得机制无追踪 |
| 凯珀 | `meet_spd&exchange[000]` | 线索交流时 +30% | 无交流状态 |
| 凯恩 | `meet_spd&exchange[001]` | 同上 | 无交流状态 |

> 除复奏外，其余 4 条主线效率已有覆盖（solo condChar[000]/[100] 已在 `_RECEPTION_CONDITIONAL` 中），缺口仅限于"必定获得"和"交流期间"等辅助机制。

---

## 六、办公室 Office — 46 条中 ~13 条未建模 (72%)

### 6.1 心情消耗（12 条，P1）

| buff 前缀 | 条数 | 效果 |
|-----------|------|------|
| `hire_spd_cost` | 12 | 各办公室干员自身心情消耗修正 |

> mood_flow `_SELF_MP_COST` 表 P1 待接入。其中 `hire_spd_cost[200]`（地灵）含 +45% 联络（效率已覆盖），消耗 +2/h。

### 6.2 故意排除（9 条）

| 类别 | buff 前缀 | 条数 | 原因 |
|------|----------|------|------|
| 线索获取 | `hire_spd&clue` | 6 | 与产值无关 |
| 线索获取 | `hire_spd&clue2` | 3 | 与产值无关 |

---

## 七、总结

```
设施      条目  已建模  故意排除  待建模   备注
───────────────────────────────────────────────────────────────
制造站     143    141      0       2     1 条心情落差+1 条心情落差条件型
贸易站     117    115      1       1     1 条心情P1
控制中枢    95     60     26       9     1 条 Mujica + 8 条心情偏差
发电站      48     45      1       2     2 条爬升增量
会客室      87     65     17       5     17 条线索(故意排除)+5 条条件型
办公室      46     33      9       4     12 条心情P1 + 9 条线索
───────────────────────────────────────────────────────────────
合计       536    453     54      29    (产相关)
```

**核心结论**：
- 三巨头（Mfg/Trade/Control）产值覆盖均 **>96%**，剩余缺口几乎全是爬升增量或缺注入路径
- **无虚构条目**（上版中的 `manu_token_spd` 机器人、`power_rec_spd_NotGuard` 等均为错误——已删除）
- 唯一新增 BuffPool 维度的缺口：丰川祥子 Mujica（已记入 inbox）
- 求解器得分计算中，已建模技能可完全驱动排班决策
