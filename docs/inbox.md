# 需求收件箱

> 原始想法、改进提议、架构疑虑在此登记。评估后路由到版本计划(plan)、或关闭。
> 不区分优先级，不分表，所有需求都登记在此。

## 待处理

<!-- 格式: - [ ] 简短标题 — 描述 — 提出日期 — 可能路由 -->
<!-- 完成后标记 [x]，发版时清理已完成条目  -->

[x] **粗评分预筛选优化** — 旧求解器功能，随 exhaust_mfg.py 在 SlotSolver 重构中一并删除。SlotSolver 使用贡献模型 D[d] 偏导数直接评分，无需粗筛捷径。 — 2026-05-29 → 2026-06-01 关闭
- [ ] 维什戴尔 订单上限联动 — 赫德雷贸易站+1~2订单上限，非孑房间无模型意义 — 2026-05-28 — 不路由
- [ ] **基建布局可配置化** — `LayoutConfig.layout_243()` 硬编码了所有房间、工位数和等级（`RoomConfig.level`），如需适配 252/153 等布局需改 Python 代码。应支持外部 JSON 配置驱动：房间列表、每间房的类型/工位/等级/产物均由配置文件定义，求解器从 `SolverParams` 或独立 JSON 读取 — 2026-05-28 — `models.py` + `params.py`
- [ ] **B7 跨房间配对被评估遗漏** — `synergy_cross_room_pair` 在 `evaluate_room` 中存在但 `all_assignments` 从未由组合评估阶段传入（Phase 1 `_evaluate_with_support` 和 Phase 3a `_evaluate_trade_combo` 均不传），导致烈夏↔古米(Mfg↔Trade)和深巡↔乌尔比安(Trade↔任意)的组合评分不含 B7 加成。深巡可接线修复（Trade 评估时 Mfg 已求解），烈夏需算法升级（Mfg 评估时 Trade 未求解，待 k-beam 或迭代 refine 落地后覆盖）。既有经验表明烈夏的组合非当前最优，但深巡可用，待 k-beam 算法实现后一并验证 — 2026-05-28 — `refine.py` / k-beam / 迭代坐标下降
- [ ] **瓶颈枚举（互补件一）** — 识别 8-12 个关键瓶颈干员（如黑键该去 Mfg 支撑还是 Trade 主力），枚举所有可行分配方案，对每种方案跑完整求解取最优。将在 Strategy 重构完成后作为 `BottleneckEnumStrategy` 实现 — 2026-05-28 — `solver/strategies/`
- [ ] **局部搜索策略化** — 支持 best-improvement、simulated annealing、或基于房间类型的加权搜索。`refine_mode` 将作为 Strategy 属性（见 [strategy-refactor-plan §Step 2.5](./archive/strategy-refactor-plan.md)），SolverConfig 开关迁移后实施 — 2026-05-28 — `solver/refine.py`
- [x] **interval_hours 外生日历约束去除** — `interval_hours` 参数已彻底移除。根因是建模错误：游戏内班次之间无间隔，恢复通过宿舍在位实现。见 `3b945e0` 及相关提交 — 2026-05-31 — `params.py` + `slot/solver.py` + tests
- [ ] **夕·不以物喜（烟火分支）未建模** — 夕的 `control_mp_cost&bd1[000]`（mood<12 → 烟火+15）在 `compute_buff_pool` 中完全遗漏，仅建模了 `control_mp_cost&bd2[000]`（不以己悲，mood>=12 → 感知+10）。需在 buff_pool.py 中补充检测逻辑。注意夕的两个 buff 是条件互补非互斥——同一干员两独立 buff — 2026-05-31 — `buff_pool.py`
- [ ] **桑葚·灾后普查（Office 烟火）未建模** — `hire_spd_bd_n1_n1[200]`：243 布局 Office Lv3 下 2 额外招募位 → 烟火+20。桑葚有 E2+20% Office 直接效率 + E2 烟火注入，与絮雨竞争唯一 Office 槽位。`_office_contribution` 当前无法感知烟火注入能力。AGENTS.md L81 记录了桑葚→絮雨的排除逻辑但代码未实现 — 2026-05-31 — `buff_pool.py` + `contribution.py`
- [ ] **深律·心声图绘（Office 无声共鸣）未建模** — `hire_spd_bd_n1_n1[300]`：243 布局 Office Lv3 下 2 额外招募位 → 无声共鸣+30。有 E2+30% Office 直接效率，同样是 Office 槽位竞争者 — 2026-05-31 — `buff_pool.py` + `contribution.py`
- [ ] **BuffPool 生产侧全量表驱动化** — 17 个生产者（迷迭香/黑键/乌有/爱丽丝/车尔尼/塑心/森西/絮雨/桑葚/深律/夕/令/重岳/截云等）均可统一为 `BuffProducerEffect` 表驱动，消除 `compute_buff_pool` 内所有名字/buff_id 硬编码分支。关键字段：`dimension`(token)、`amount_source`(fixed/dorm_count/dorm_level/suich_count/office_slots)、`condition`(mood gate)、`exclusive_group`(互斥)、`cascade_to`(级联)。路线：①签名 bool→operator 列表 ②建表替代 if/elif — 2026-05-31 — `buff_pool.py` + `types.py`
- [ ] **P1 自身 mp_cost buff 接入** — 当前仅接入 P0 范围（39 条 MFG+TRADE+POWER 无条件自身 buff），尚有 49 条未建模。P1 范围（22 条）：HIRE 14 条（地灵+2.0/斥罪+0.5/桑葚-0.25等）+ TRADING 条件配对 5 条（德克萨斯+拉普兰德同僚条件）+ TRADING 动态 3 条（铎铃烟火联动/巫恋低语）。P1 的关键难点在于动态条件 buff 需要 BuffPool 参数（烟火计数）和 co_worker 条件检测。P2（CONTROL 15条）和 P3（MEETING 12条）优先级更低。详见 `mood_flow.py` `_SELF_MP_COST` 表后的 TODO 注释块 — 2026-05-31 — `mood_flow.py`
- [x] **订单机制互斥的算法级建模** — Phase A 修复完成（2026-06-01）：新增 `synergy/conflicts.py` `resolve_efficiency_conflicts()` + `_EFF_MECH_DISABLERS` 字典驱动冲突表。`evaluate.py` 归零步骤前插入冲突解析，`opportunity.py` `_detect_mode` 复用同一解析器。Closure 在场时 whisper 不再激活归零+45%。Phase B（订单层机会成本表）待 v0.6.0。 — 2026-05-31 → 2026-06-01 Phase A 完成
