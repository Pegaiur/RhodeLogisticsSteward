# 需求收件箱

> 原始想法、改进提议、架构疑虑在此登记。评估后路由到版本计划(plan)、或关闭。
> 不区分优先级，不分表，所有需求都登记在此。

## 待处理

<!-- 格式: - [ ] 简短标题 — 描述 — 提出日期 — 可能路由 -->
<!-- 完成后标记 [x]，发版时清理已完成条目  -->

- [ ] **粗评分预筛选优化** — Phase 1 制造站组合预筛选已实现但默认关闭（`rough_score_keep_top=0`）。当前粗评分仅含个人效率 + 四种硬编码标签红利（迷迭香/骑士/红松/杜林），四种红利值（+200/+100/+40/+50）量级合理但未覆盖 A2 技能计数、A6 设施数量等联动。需补充联动红利、验证全面性后再开启。详见 `steward_core/solver/phase1_mfg.py` `_rough_mfg_score` — 2026-05-29 — `phase1_mfg.py` + `params.py`
- [ ] **热情值 buff 池建模** — Mortis(中枢→trade+1%/8热情值) + 消极怠工(中枢→PG+1%/20热情值)，需新增 `ardor` 字段；满配 trade+7%，无若麦时可降到 +3% — 2026-05-28 — `synergy/buff_pool.py` + `control_linkages.py`
| 干员 | buffId | 效果 |
|------|--------|------|
| Mortis | `control_mp_bd&trade[000]` | 热情值+20；每8热情值→贸易站+1% |
| 消极怠工 | `control_prod_bd_spd[010]` | PG Mfg+1%；每20热情值→PG Mfg+1% |
| 若麦 | `control_dorm_bd[000]` | 宿舍每1人→热情值+1 |
| Amoris | `control_meeting_spd&bd[000]` | 热情值+10 |
- [ ] 木天蓼/情报储备/乌萨斯特饮 — 仅心情/非产出 buff，12h 单班次不触发 — 2026-05-28 — 不路由
- [ ] 维什戴尔 订单上限联动 — 赫德雷贸易站+1~2订单上限，非孑房间无模型意义 — 2026-05-28 — 不路由
- [ ] **基建布局可配置化** — `LayoutConfig.layout_243()` 硬编码了所有房间、工位数和等级（`RoomConfig.level`），如需适配 252/153 等布局需改 Python 代码。应支持外部 JSON 配置驱动：房间列表、每间房的类型/工位/等级/产物均由配置文件定义，求解器从 `SolverParams` 或独立 JSON 读取 — 2026-05-28 — `models.py` + `params.py`
- [ ] **B7 跨房间配对被评估遗漏** — `synergy_cross_room_pair` 在 `evaluate_room` 中存在但 `all_assignments` 从未由组合评估阶段传入（Phase 1 `_evaluate_with_support` 和 Phase 3a `_evaluate_trade_combo` 均不传），导致烈夏↔古米(Mfg↔Trade)和深巡↔乌尔比安(Trade↔任意)的组合评分不含 B7 加成。深巡可接线修复（Trade 评估时 Mfg 已求解），烈夏需算法升级（Mfg 评估时 Trade 未求解，待 k-beam 或迭代 refine 落地后覆盖）。既有经验表明烈夏的组合非当前最优，但深巡可用，待 k-beam 算法实现后一并验证 — 2026-05-28 — `refine.py` / k-beam / 迭代坐标下降
- [→] **Strategy 策略组合器** — 已路由到 [`docs/strategy-refactor-plan.md`](./strategy-refactor-plan.md) (v0.5.0)，Step 0-2.5 覆盖 Strategy ABC + PartialSolution + Pipeline 适配 + SolverConfig 开关迁移方案。实施中 — 2026-05-28
- [ ] **瓶颈枚举（互补件一）** — 识别 8-12 个关键瓶颈干员（如黑键该去 Mfg 支撑还是 Trade 主力），枚举所有可行分配方案，对每种方案跑完整求解取最优。将在 Strategy 重构完成后作为 `BottleneckEnumStrategy` 实现 — 2026-05-28 — `solver/strategies/`
- [ ] **局部搜索策略化** — 支持 best-improvement、simulated annealing、或基于房间类型的加权搜索。`refine_mode` 将作为 Strategy 属性（见 [strategy-refactor-plan §Step 2.5](./strategy-refactor-plan.md)），SolverConfig 开关迁移后实施 — 2026-05-28 — `solver/refine.py`
- [ ] **JSON 输出格式符合 MAA 基建排班协议** — 当前 `output.py` 生成的 JSON 与 [MAA 协议规范](https://docs.maa.plus/zh-cn/protocol/base-scheduling-schema.html) 及[官方模板 153_layout_3_times_a_day.json](https://github.com/MaaAssistantArknights/MaaAssistantArknights/blob/master-v2/resource/custom_infrast/153_layout_3_times_a_day.json) 存在以下差距：
  1. **顶层缺失字段**：`id`（随机 GUID）、`buildingType`（243/252/153）、`planTimes`（如 "3班"）、`scheduleType`（`planTimes`/`trading`/`manufacture`/`power`/`dormitory` 数量）
  2. **plan 缺失字段**：`description`、`description_post`、`Fiammetta.enable/target/order`（菲亚梅塔技能，当前单班次可不启用）
  3. **drones 缺失 `enable` 字段**：当前只输出 `room`/`index`/`order`
  4. **rooms 条目字段对齐**：MAA 协议要求 `sort: false` 为默认、支持 `candidates` 备选列表、`skip` 字段语义验证、`product` 值需与 MAA 枚举对齐（已对齐）
  5. **输出文件命名规范**：参考 MAA 模板命名 `{layout}_layout_{plan_times}_a_day.json`
  — 2026-05-28 — `steward_core/output.py`
