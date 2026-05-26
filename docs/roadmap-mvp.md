# 开发路线图

> **版本**: 2026-05-26 · MVP — 制造站穷举+剪枝+贪心，全box满练，单次12h排班

## MV0：基础建设（数据层 + 模型）

**目标**：新数据源正确加载，模型定义就绪。

**输入**：`character_identity.json` + `buffs_infrastructure.json`

**任务**：

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| 1 | 扩展 `Operator` | `models.py` | 增加 `group_id`, `nation_id`, `team_id` 三个可选字段（用于体系联动判定） |
| 2 | 增加 `LinearSegment` | `models.py` | `a/b/t_start/dt` 字段 + `integrate()` 方法，约 20 行 |
| 3 | 增加全局上下文类型 | `models.py` | `BuffPool`(烟火/感知信息/巫术结晶), `GlobalBonus`(中枢加成), `GlobalContext` |
| 4 | 重写 `data_loader.py` | `data_loader.py` | 从 `character_identity.json` 解析身份字段；从 `buffs_infrastructure.json` 解析 `roomType/efficiency/description`；产物匹配由 `description` 文本判定（至少区分作战记录/贵金属/通用）；约 150 行 |
| 5 | 验证数据加载 | 临时脚本 | 统计 415 干员、520 buff、各设施候选人数（与 `constraints-and-data-baseline.md` 交叉核验） |

**产出验证**：

```
Mfg candidate: CR=60, PG=56
Trade candidate: 74
Control candidate: 64
Power candidate: 30
Reception candidate: 51
Office candidate: 31
```

---

## MV1：效率函数（e(t) 核心）

**目标**：`efficiency_fn.py` 就绪，支配偏序能对制造站 60 人正确排序。

**依赖**：MV0

**任务**：

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| 1 | `constant_efficiency(value, mood_burn)` | `efficiency_fn.py` | 常数技能 → `[LinearSegment(a=value, dt=T), LinearSegment(a=0, dt=max(0,T-t_red))]`（两段） |
| 2 | `ramping_efficiency(k0, r, ceiling, mood_burn)` | `efficiency_fn.py` | 7 条时变技能，线性爬升到 saturation 再截断 |
| 3 | `_dominates_simple(seg_a, seg_b, T)` | `efficiency_fn.py` | O(1) 二维支配：`k_a ≥ k_b AND t_red_a ≥ t_red_b` |
| 4 | `rank_by_dominance(candidates, T)` | `efficiency_fn.py` | 支配偏序排序（多趟 Kahn），互不支配时退化为全积分比较 |
| 5 | `integrate_segments(segments, T)` | `efficiency_fn.py` | 对已排序段在 [0, T] 上积分 |
| 6 | 单元测试 | `tests/test_efficiency.py` | 常数技能截断、ramping 饱和、支配排序正确性 |

**产出验证**：对制造站 60 人按 `rank_by_dominance` 排序，确认 Top-10 均为 eff≥30 的 A-tier 干员。

---

## MV2：联动函数（A 层核心，B/C 占位）

**目标**：A1/A3/A4/A5 联动正确计算，A2/A6/A7 留占位，B/C 层用常数。

**依赖**：MV0（需要 Operator 的身份字段和技能标签）

**文件**：新建 `steward_core/synergy.py`，约 200 行（MVP）。

**任务**：

| # | 任务 | 函数签名 | 核心逻辑 |
|---|------|----------|----------|
| 1 | A1 干员配对 | `synergy_pair(operators, room_type, product) → list[LinearSegment]` | 硬编码配对表：阿兰娜↔温米(+15%贵金属)、Christine↔酒神(+30%作战记录)、怒潮凛冬↔乌萨斯学生自治团(+10%) |
| 2 | A2 阵营计数 | `synergy_faction_room(operators, room_type) → list[LinearSegment]` | 同房间格拉斯哥帮/拉特兰/A1小队计数 → 每人加成 |
| 3 | A3 技能类型计数 | `synergy_skill_count(operators, room_type) → list[LinearSegment]` | 水月(标准化)、多萝西(莱茵科技)、苍苔(金属工艺)，按同房该类型技能数 × 每人加成 |
| 4 | A4 技能别名 | `synergy_skill_alias(operators) → dict` | 海沫：莱茵科技+红松骑士团 → 标准化；返回别名映射供 A3 展开 |
| 5 | A5 自动化 | `synergy_automation(operators, room_type, power_count) → tuple[list[LinearSegment], set[str]]` | 森蚺/温蒂/掠风/异客，归零他人 + 发电站×N% 效率 |
| 6 | A6 设施数量联动 | `synergy_facility_count(operators, room_type, product, layout) → list[LinearSegment]` | 清流(贸易站数×20%)、空弦(宿舍级数)、伺夜(会客室级数) 等 |
| 7 | B/C 占位常数 | `compute_control_global_bonus()` / `compute_buff_pool()` | 返回硬编码值：`GlobalBonus(mfg=+2%, trade=+7%)`, `BuffPool(0,0,0)` |
| 8 | 单元测试 | `tests/test_synergy.py` | 各体系基础验证（已知最优组合产出 > 纯效率组合） |

**产出验证**：

```python
# 水月+白面鸮+杰西卡 → A3 标准化计数=3 → 水月+15%
# Miss.Christine+酒神+任意 → A1 配对 → +30% 作战记录
# 森蚺+空房 → A5 自动化 → 发电站3×5%=15%
```

---

## MV3：制造站穷举求解（Phase 2-4）

**目标**：端到端求解器可运行，输出完整的 29 人工位排班。

**依赖**：MV1 + MV2

**文件**：重写 `steward_core/solver.py`，约 250 行。

**任务**：

| # | 任务 | 要点 |
|---|------|------|
| 1 | 干员角色分类 | 扫描 `all_mfg` → 分拣为 `pure_efficiency / a_tier / anchors / providers` |
| 2 | 剪枝规则 1-3 | 等价类合并 → 锚点池筛选 → 上界预判（`upper_bound < best_known × 0.95` 跳过） |
| 3 | 制造站穷举评估 | 对每个产物（CR/PG）→ 对每个过剪枝的 3 人组合 → `per_op + Σ synergy` → 积分排序 |
| 4 | 跨间贪心分配 | 产物内排序列表遍历，取无冲突组合，凑满 2 间 |
| 5 | 剩余设施贪心 | Trade/Power/Reception/Office 从剩余池贪心；Control 固定方案 |
| 6 | 单元测试 | `tests/test_solver.py`：穷举不丢联动最优解、剪枝不丢上界、跨间不冲突 |

**产出验证**：输出 `custom_infrast/*.json`，核心工位（Mfg 12 人 + Trade 6 人）与社区最优模板匹配率 ≥ 80%。

---

## MV4：产出计算适配 + 入口整合

**目标**：端到端可运行，命令行产出 MAA 可执行 JSON。

**依赖**：MV3

**任务**：

| # | 任务 | 文件 | 要点 |
|---|------|------|------|
| 1 | 适配 `production.py` | `production.py` | 12h 参数、调用 `efficiency_fn` 积分替代标量乘、保留赤金供需平衡逻辑 |
| 2 | 简化 `mood.py` | `mood.py` | 仅保留中枢减免计算 → `global_burn` 常数（12h 内不触发截断） |
| 3 | 重写 `run_solver.py` | `run_solver.py` | 新数据源入口、Phase 1-4 串联、输出 JSON、基准对比 |
| 4 | 端到端验证 | 手动 | 对比一图流排班生成器 / MAA 内置 243 模板 |

---

## MV5（MVP 之后，不阻塞主干）

| # | 任务 | 说明 |
|---|------|------|
| 1 | A7 订单机制 | `synergy_order_mechanics()`：但书违约、诗怀雅/雪雉/孑、赤金生产线、期望值建模 |
| 2 | A6 完整实施 | 设施数量联动（当前占位跳过） |
| 3 | B1 人间烟火完整链 | 中枢↔宿舍↔工作设施全链路 |
| 4 | B2-B7 剩余跨设施体系 | 工程机器人、思维链环、魔物料理、无声共鸣、全局阵营、跨房间配对 |
| 5 | Phase 5 精确验证 | B 层实际注入，全方案重积分，偏差调整 |
| 6 | D 层会客室/办公室 | 线索搜集/人脉联络联动建模（不影响产能，排序稳定性验证用） |

---

## 依赖图

```
MV0(数据+模型) → MV1(效率函数) → MV3(求解器) → MV4(入口整合)
                      ↘                ↗
                        MV2(联动函数)
                              │
                              └──→ MV5(后补: A7+B/D层)
```

MV0 → MV1 串行。MV2 可与 MV1 并行开发（联动函数不需要效率函数，只需要干员身份标签）。MV3 合并 MV1+MV2 产物。

---

## 编码规范

- 所有注释和 docstring 使用中文
- PEP 8，缩进 4 空格
- 仅在标准库不满足需求时引入第三方依赖
- 每个新建模块配对应的 `tests/test_*.py`
- 函数粒度：每个体系一个独立函数（见 `docs/synergy-systems.md` §体系函数总清单）

---

## 里程碑与版本

| 里程碑 | 版本 | 标准 |
|--------|------|------|
| MV0 + MV1 完成 | v0.1.0 | 数据加载正确 + 效率函数可排序 |
| MV2 + MV3 完成 | v0.2.0 | 制造站穷举可输出完整排班 |
| MV4 完成 | v0.3.0 | 端到端可运行，产出 MAA JSON |
| MV5 完成 | v1.0.0 | 全体系联动建模完成 |

---

## 参考

- 策略概要: [`strategy-brief.md`](./strategy-brief.md)
- 联动体系建模: [`synergy-systems.md`](./synergy-systems.md)
- 效率函数建模: [`efficiency-function-design.md`](./efficiency-function-design.md)
- 约束体系与数据基线: [`constraints-and-data-baseline.md`](./constraints-and-data-baseline.md)
