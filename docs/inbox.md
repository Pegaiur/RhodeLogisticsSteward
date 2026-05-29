# 需求收件箱

> 原始想法、改进提议、架构疑虑在此登记。评估后路由到版本计划(plan)、或关闭。
> 不区分优先级，不分表，所有需求都登记在此。

## 待处理

<!-- 格式: - [ ] 简短标题 — 描述 — 提出日期 — 可能路由 -->
<!-- 完成后标记 [x]，发版时清理已完成条目  -->

- [ ] **粗评分预筛选优化** — Phase 1 制造站组合预筛选已实现但默认关闭（`rough_score_keep_top=0`）。当前粗评分仅含个人效率 + 四种硬编码标签红利（迷迭香/骑士/红松/杜林），四种红利值（+200/+100/+40/+50）量级合理但未覆盖 A2 技能计数、A6 设施数量等联动。需补充联动红利、验证全面性后再开启。详见 `steward_core/solver/exhaust_mfg.py` `_rough_mfg_score` — 2026-05-29 — `exhaust_mfg.py` + `params.py`
- [ ] **热情值 buff 池建模** — Mortis(中枢→trade+1%/8热情值) + 消极怠工(中枢→PG+1%/20热情值)，需新增 `ardor` 字段；满配 trade+7%，无若麦时可降到 +3% — 2026-05-28 — `synergy/buff_pool.py` + `control_linkages.py`
| 干员 | buffId | 效果 |
|------|--------|------|
| Mortis | `control_mp_bd&trade[000]` | 热情值+20；每8热情值→贸易站+1% |
| 消极怠工 | `control_prod_bd_spd[010]` | PG Mfg+1%；每20热情值→PG Mfg+1% |
| 若麦 | `control_dorm_bd[000]` | 宿舍每1人→热情值+1 |
| Amoris | `control_meeting_spd&bd[000]` | 热情值+10 |
- [→] 木天蓼/情报储备/乌萨斯特饮 — 仅心情/非产出 buff，12h 单班次不触发。2 班次下心情压力触发后，这些 buff 将影响宿舍恢复速率和工作时长，需重新评估路由 — 2026-05-28 → 2026-05-29 — 2 班次 `mood.py` 心情流转模型
- [ ] 维什戴尔 订单上限联动 — 赫德雷贸易站+1~2订单上限，非孑房间无模型意义 — 2026-05-28 — 不路由
- [ ] **基建布局可配置化** — `LayoutConfig.layout_243()` 硬编码了所有房间、工位数和等级（`RoomConfig.level`），如需适配 252/153 等布局需改 Python 代码。应支持外部 JSON 配置驱动：房间列表、每间房的类型/工位/等级/产物均由配置文件定义，求解器从 `SolverParams` 或独立 JSON 读取 — 2026-05-28 — `models.py` + `params.py`
- [ ] **B7 跨房间配对被评估遗漏** — `synergy_cross_room_pair` 在 `evaluate_room` 中存在但 `all_assignments` 从未由组合评估阶段传入（Phase 1 `_evaluate_with_support` 和 Phase 3a `_evaluate_trade_combo` 均不传），导致烈夏↔古米(Mfg↔Trade)和深巡↔乌尔比安(Trade↔任意)的组合评分不含 B7 加成。深巡可接线修复（Trade 评估时 Mfg 已求解），烈夏需算法升级（Mfg 评估时 Trade 未求解，待 k-beam 或迭代 refine 落地后覆盖）。既有经验表明烈夏的组合非当前最优，但深巡可用，待 k-beam 算法实现后一并验证 — 2026-05-28 — `refine.py` / k-beam / 迭代坐标下降
- [x] **Strategy 策略组合器** — 已实施于 v0.5.0。Baseline/KBeam/Iterative 三条策略 + PartialSolution + Pipeline 迁入 BaselineStrategy + CLI 策略选择。详见 [`docs/archive/strategy-refactor-plan.md`](./archive/strategy-refactor-plan.md) — 2026-05-28 → 2026-05-29
- [ ] **瓶颈枚举（互补件一）** — 识别 8-12 个关键瓶颈干员（如黑键该去 Mfg 支撑还是 Trade 主力），枚举所有可行分配方案，对每种方案跑完整求解取最优。将在 Strategy 重构完成后作为 `BottleneckEnumStrategy` 实现 — 2026-05-28 — `solver/strategies/`
- [ ] **局部搜索策略化** — 支持 best-improvement、simulated annealing、或基于房间类型的加权搜索。`refine_mode` 将作为 Strategy 属性（见 [strategy-refactor-plan §Step 2.5](./archive/strategy-refactor-plan.md)），SolverConfig 开关迁移后实施 — 2026-05-28 — `solver/refine.py`
- [ ] **多班次心情流转模型** — `mood.py` 当前仅有单班次分析（`MoodReport`），缺少多班次所需的完整生命周期：工作消耗 → 宿舍恢复 → 再工作。需扩展为：① 宿舍恢复速率建模（聚合宿舍内所有恢复 buff，计算每干员恢复时间）；② 两班间隔窗口计算（Shift 1 结束 → 宿舍恢复时长 → Shift 2 开始前的心情状态）；③ 心情截断触发效率惩罚（蓝脸=效率下降，红脸=效率归零）；④ 中枢心情减免的跨班次累积效应。当前 `strategy-brief.md` 明确"12h 单班次下心情截断不触发（最差单人工位 t_red=16h>12h）"，2 班次下此假设不再成立 — 2026-05-29 — `mood.py` + `models.py`
- [ ] **宿舍 Phase 从填充升级为恢复调度** — 当前 `fill_dorm` 仅填充 20 个空位（优先 B 层生成者），2 班次下宿舍需要精确调度：哪些工作干员进入哪间宿舍、恢复多少小时、何时可重返工作。决策维度从"填满"变为"最小化整体轮换空窗期" — 2026-05-29 — `fill_dorm.py`
- [ ] **MultiShiftPlan 数据模型** — 当前 `ShiftPlan` 和 `SolveResult.plans` 为单班次设计，2 班次需要：① `ShiftSchedule` 或 `MultiShiftPlan` 建模多班次时间线（每班的起止时间、干员分配、宿舍分配）；② 班次间的 operator 状态追踪（工作→宿舍→空闲）；③ 全周期产出评估（两班合计产能，而非单班独立最大化）。SolveResult.plans 已是 list 形式，可直接放两个 ShiftPlan，但 solving pipeline 需感知多班次语义 — 2026-05-29 — `models.py`
- [ ] **Phase 多班次轮换感知** — 当前各 Phase 通过 `assigned_ids`/`assigned_names` 互斥干员，2 班次下此机制需升级：① Shift 1 已工作的干员在 Shift 2 中不可用（除非宿舍恢复完毕）；② 中枢干员可跨班次常驻（无心情消耗）；③ Trade/Mfg 的"最优组合"在两个班次间需要 trade-off——把最强组合放 Shift 1 可能导致 Shift 2 无人可用。K-Beam 的多路径保留在此场景下价值放大（可同时探索两个班次的组合分配） — 2026-05-29 — 所有 `exhaust_*`/`fill_*` 模块
- [ ] **JSON 输出格式符合 MAA 基建排班协议** — 当前 `output.py` 生成的 JSON 与 [MAA 协议规范](https://docs.maa.plus/zh-cn/protocol/base-scheduling-schema.html) 及[官方模板 153_layout_3_times_a_day.json](https://github.com/MaaAssistantArknights/MaaAssistantArknights/blob/master-v2/resource/custom_infrast/153_layout_3_times_a_day.json) 存在以下差距：
  1. **顶层缺失字段**：`id`（随机 GUID）、`buildingType`（243/252/153）、`planTimes`（如 "3班"）、`scheduleType`（`planTimes`/`trading`/`manufacture`/`power`/`dormitory` 数量）
  2. **plan 缺失字段**：`description`、`description_post`、`Fiammetta.enable/target/order`（菲亚梅塔技能，当前单班次可不启用）
  3. **drones 缺失 `enable` 字段**：当前只输出 `room`/`index`/`order`
  4. **rooms 条目字段对齐**：MAA 协议要求 `sort: false` 为默认、支持 `candidates` 备选列表、`skip` 字段语义验证、`product` 值需与 MAA 枚举对齐（已对齐）
  5. **输出文件命名规范**：参考 MAA 模板命名 `{layout}_layout_{plan_times}_a_day.json`
  — 2026-05-28 — `steward_core/output.py`
