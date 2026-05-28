# 需求收件箱

> 原始想法、改进提议、架构疑虑在此登记。评估后路由到版本计划(plan)、或关闭。
> 不区分优先级，不分表，所有需求都登记在此。

## 待处理

<!-- 格式: - [ ] 简短标题 — 描述 — 提出日期 — 可能路由 -->
<!-- 完成后标记 [x]，发版时清理已完成条目  -->

- [ ] **热情值 buff 池建模** — Mortis(中枢→trade+1%/8热情值) + 消极怠工(中枢→PG+1%/20热情值)，需新增 `ardor` 字段；满配 trade+7%，无若麦时可降到 +3% — 2026-05-28 — `synergy/buff_pool.py` + `control_linkages.py`
| 干员 | buffId | 效果 |
|------|--------|------|
| Mortis | `control_mp_bd&trade[000]` | 热情值+20；每8热情值→贸易站+1% |
| 消极怠工 | `control_prod_bd_spd[010]` | PG Mfg+1%；每20热情值→PG Mfg+1% |
| 若麦 | `control_dorm_bd[000]` | 宿舍每1人→热情值+1 |
| Amoris | `control_meeting_spd&bd[000]` | 热情值+10 |
- [ ] 木天蓼/情报储备/乌萨斯特饮 — 仅心情/非产出 buff，12h 单班次不触发 — 2026-05-28 — 不路由
- [ ] 维什戴尔 订单上限联动 — 赫德雷贸易站+1~2订单上限，非孑房间无模型意义 — 2026-05-28 — 不路由
- [x] 至简工程机器人 — `44bffd4` `feat(synergy): 实现B2-B5跨设施体系+C2全局恢复` — producer+consumer 双端齐全
- [ ] **基建布局可配置化** — `LayoutConfig.layout_243()` 硬编码了所有房间、工位数和等级（`RoomConfig.level`），如需适配 252/153 等布局需改 Python 代码。应支持外部 JSON 配置驱动：房间列表、每间房的类型/工位/等级/产物均由配置文件定义，求解器从 `SolverParams` 或独立 JSON 读取 — 2026-05-28 — `models.py` + `params.py`
- [ ] **B7 跨房间配对被评估遗漏** — `synergy_cross_room_pair` 在 `evaluate_room` 中存在但 `all_assignments` 从未由组合评估阶段传入（Phase 1 `_evaluate_with_support` 和 Phase 3a `_evaluate_trade_combo` 均不传），导致烈夏↔古米(Mfg↔Trade)和深巡↔乌尔比安(Trade↔任意)的组合评分不含 B7 加成。深巡可接线修复（Trade 评估时 Mfg 已求解），烈夏需算法升级（Mfg 评估时 Trade 未求解，待 k-beam 或迭代 refine 落地后覆盖）。既有经验表明烈夏的组合非当前最优，但深巡可用，待 k-beam 算法实现后一并验证 — 2026-05-28 — `refine.py` / k-beam / 迭代坐标下降
- [ ] **Strategy 策略组合器** — 当前 `SolverConfig` 用独立 bool 开关 + `SolverParams` 数值参数控制行为，无法表达策略间互锁（如"全局状态评分仅在独占检查开启时生效"）或元策略（如"同时跑两种算法取最高分"）。引入 `Strategy` 抽象层——每个 Strategy 封装一个完整的求解流水线（预处理 + 主求解 + 后处理 + 目标函数），`SolverConfig` 引用 Strategy 而非直接含开关。触发条件：SolverConfig 中 bool 开关 ≥ 4 个时 — 2026-05-28 — `solver/` + `models.py`
- [ ] **瓶颈枚举（互补件一）** — 识别 8-12 个关键瓶颈干员（如黑键该去 Mfg 支撑还是 Trade 主力），枚举所有可行分配方案，对每种方案跑完整求解取最优。与全局状态评分互补——前者处理少量关键决策的精确分配，后者处理大规模资源竞争的启发式引导。触发条件：跨 Phase 资源分配成为显著瓶颈时 — 2026-05-28 — `solver/`
- [ ] **局部搜索策略化** — 支持 best-improvement、simulated annealing、或基于房间类型的加权搜索，超越当前 first-improvement 策略。策略选择通过 `Strategy.scoring` 配置。触发条件：当前 first-improvement 策略无法满足需求时 — 2026-05-28 — `solver/greed.py` + `models.py`
