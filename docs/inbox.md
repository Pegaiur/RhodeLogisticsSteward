# 需求收件箱

> 原始想法、改进提议、架构疑虑在此登记。评估后路由到版本计划(plan)、或关闭。
> 不区分优先级，不分表，所有需求都登记在此。

## 待处理

<!-- 格式: - [ ] 简短标题 — 描述 — 提出日期 — 可能路由 -->
<!-- 完成后标记 [x]，发版时清理已完成条目  -->

[x] **数据加载器 product 映射 roomType 驱动化** — 已修复 (7d8a5ff): Trade→直接 Money、Mfg→targets 结构判定、其他→all。候选池 63→74 (+11人)，全部 7 名裁缝干员入池。 — 2026-06-01 → 2026-06-01 完成
[x] **制造站侧数据加载 product 映射审计** — Trade 侧已修，Mfg 侧 MANUFACTURE buff 描述含"贵金属/赤金"是否也存在同类误映射？审计完成：当前 109 条 Mfg buff targets 与 description 100% 一致无误判。已切换为 targets 结构化字段判定，删除 _determine_product + _build_efficiency_map。 — 2026-06-01 — `data_loader.py`
- [ ] **贸易站未建模技能补全** — 91 个 TRADING buff 中约 20% 仅有基础效率建模，特殊加成未覆盖。详见 `synergy/trade_linkages.py` 模块 docstring。主要缺口：赫德雷 per-operator 缩放、琳琅诗怀雅/锏 可变效率、拉普兰德/德克萨斯 订单上限+配对、贝洛内 limit+cost_P 配对。 — 2026-06-01 — `trade_linkages.py` + `evaluate.py`
- [ ] **贸易站候选池 0 贡献干员过滤** — 塑心/芳汀 无任何 TRADING buff 却通过 has_skill_for 进入候选池。铎铃/火哨/史都华德/暗索/桃金娘/佩佩/雪雉 eff=0 且无 trade_ord_* 机制。候选池中约 11 人贡献为 0。应在 phase_trade 或 candidate_pool 构建阶段过滤。 — 2026-06-01 — `trade.py` + `classification.py`
- [ ] **宿舍恢复不覆盖高效率生产干员** — `phase_remaining` 中宿舍填充只看 dorm_rec_* 技能（`has_skill_for("Dormitory","Rest")`），无宿舍技能的高效生产干员（Mfg/Trade eff≥30）根本无法竞争宿舍槽位。14 班排班中 Mfg 0/高职入宿舍、Trade 仅 1/高。高效干员工作 2-3 班后心情耗尽被丢弃，从未进宿舍恢复。修复方向：宿舍 contribution 评分应包含被恢复者的替代生产力（λ 影子乘子），或放宽候选池准入条件。 — 2026-06-01 — `remaining.py` + `contribution.py` + `context.py`
- [ ] 维什戴尔 订单上限联动 — 赫德雷贸易站+1~2订单上限，非孑房间无模型意义 — 2026-05-28 — 不路由
- [ ] **基建布局可配置化** — `LayoutConfig.layout_243()` 硬编码了所有房间、工位数和等级（`RoomConfig.level`），如需适配 252/153 等布局需改 Python 代码。应支持外部 JSON 配置驱动：房间列表、每间房的类型/工位/等级/产物均由配置文件定义，求解器从 `SolverParams` 或独立 JSON 读取 — 2026-05-28 — `models.py` + `params.py`
- [ ] **B7 跨房间配对被评估遗漏** — `synergy_cross_room_pair` 在 `evaluate_room` 中存在但 `all_assignments` 从未由组合评估阶段传入（Phase 1 `_evaluate_with_support` 和 Phase 3a `_evaluate_trade_combo` 均不传），导致烈夏↔古米(Mfg↔Trade)和深巡↔乌尔比安(Trade↔任意)的组合评分不含 B7 加成。深巡可接线修复（Trade 评估时 Mfg 已求解），烈夏需算法升级（Mfg 评估时 Trade 未求解，待 k-beam 或迭代 refine 落地后覆盖）。既有经验表明烈夏的组合非当前最优，但深巡可用，待 k-beam 算法实现后一并验证 — 2026-05-28 — `refine.py` / k-beam / 迭代坐标下降
- [ ] **瓶颈枚举（互补件一）** — 识别 8-12 个关键瓶颈干员（如黑键该去 Mfg 支撑还是 Trade 主力），枚举所有可行分配方案，对每种方案跑完整求解取最优。将在 Strategy 重构完成后作为 `BottleneckEnumStrategy` 实现 — 2026-05-28 — `solver/strategies/`
- [ ] **局部搜索策略化** — 支持 best-improvement、simulated annealing、或基于房间类型的加权搜索。`refine_mode` 将作为 Strategy 属性（见 [strategy-refactor-plan §Step 2.5](./archive/strategy-refactor-plan.md)），SolverConfig 开关迁移后实施 — 2026-05-28 — `solver/refine.py`
- [ ] **夕·不以物喜（烟火分支）未建模** — 夕的 `control_mp_cost&bd1[000]`（mood<12 → 烟火+15）在 `compute_buff_pool` 中完全遗漏，仅建模了 `control_mp_cost&bd2[000]`（不以己悲，mood>=12 → 感知+10）。需在 buff_pool.py 中补充检测逻辑。注意夕的两个 buff 是条件互补非互斥——同一干员两独立 buff — 2026-05-31 — `buff_pool.py`
- [ ] **桑葚·灾后普查（Office 烟火）未建模** — `hire_spd_bd_n1_n1[200]`：243 布局 Office Lv3 下 2 额外招募位 → 烟火+20。桑葚有 E2+20% Office 直接效率 + E2 烟火注入，与絮雨竞争唯一 Office 槽位。`_office_contribution` 当前无法感知烟火注入能力。AGENTS.md L81 记录了桑葚→絮雨的排除逻辑但代码未实现 — 2026-05-31 — `buff_pool.py` + `contribution.py`
- [ ] **深律·心声图绘（Office 无声共鸣）未建模** — `hire_spd_bd_n1_n1[300]`：243 布局 Office Lv3 下 2 额外招募位 → 无声共鸣+30。有 E2+30% Office 直接效率，同样是 Office 槽位竞争者 — 2026-05-31 — `buff_pool.py` + `contribution.py`
- [ ] **BuffPool 生产侧全量表驱动化** — 17 个生产者（迷迭香/黑键/乌有/爱丽丝/车尔尼/塑心/森西/絮雨/桑葚/深律/夕/令/重岳/截云等）均可统一为 `BuffProducerEffect` 表驱动，消除 `compute_buff_pool` 内所有名字/buff_id 硬编码分支。关键字段：`dimension`(token)、`amount_source`(fixed/dorm_count/dorm_level/suich_count/office_slots)、`condition`(mood gate)、`exclusive_group`(互斥)、`cascade_to`(级联)。路线：①签名 bool→operator 列表 ②建表替代 if/elif — 2026-05-31 — `buff_pool.py` + `types.py`
- [ ] **P1 自身 mp_cost buff 接入** — 当前仅接入 P0 范围（39 条 MFG+TRADE+POWER 无条件自身 buff），尚有 49 条未建模。P1 范围（22 条）：HIRE 14 条（地灵+2.0/斥罪+0.5/桑葚-0.25等）+ TRADING 条件配对 5 条（德克萨斯+拉普兰德同僚条件）+ TRADING 动态 3 条（铎铃烟火联动/巫恋低语）。P1 的关键难点在于动态条件 buff 需要 BuffPool 参数（烟火计数）和 co_worker 条件检测。P2（CONTROL 15条）和 P3（MEETING 12条）优先级更低。详见 `mood_flow.py` `_SELF_MP_COST` 表后的 TODO 注释块 — 2026-05-31 — `mood_flow.py`
- [x] **订单机制互斥的算法级建模** — Phase A 修复完成（2026-06-01）：新增 `synergy/conflicts.py` `resolve_efficiency_conflicts()` + `_EFF_MECH_DISABLERS` 字典驱动冲突表。`evaluate.py` 归零步骤前插入冲突解析，`opportunity.py` `_detect_mode` 复用同一解析器。Closure 在场时 whisper 不再激活归零+45%。Phase B（订单层机会成本表）待 v0.6.0。 — 2026-05-31 → 2026-06-01 Phase A 完成
