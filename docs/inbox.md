# 需求收件箱

> 原始想法、改进提议、架构疑虑在此登记。评估后路由到版本计划(plan)、或关闭。
> 不区分优先级，不分表，所有需求都登记在此。

## 待处理

<!-- 格式: - [ ] 简短标题 — 描述 — 提出日期 — 可能路由 -->
<!-- 完成后标记 [x]，发版时清理已完成条目  -->

[ ] **宿舍恢复不覆盖高效率生产干员** — `phase_remaining` 中宿舍填充只看 dorm_rec_* 技能（`has_skill_for("Dormitory","Rest")`），无宿舍技能的高效生产干员（Mfg/Trade eff≥30）根本无法竞争宿舍槽位。14 班排班中 Mfg 0/高职入宿舍、Trade 仅 1/高。高效干员工作 2-3 班后心情耗尽被丢弃，从未进宿舍恢复。修复方向：宿舍 contribution 评分应包含被恢复者的替代生产力（λ 影子乘子），或放宽候选池准入条件。 — 2026-06-01 — `remaining.py` + `contribution.py` + `context.py`
[ ] **菲亚梅塔交换机制建模** — `dorm_recExcludeOther` 固定 2.0/h 且在贡献评分中 λ=0（始终在宿舍不入计 hours_used），导致她被所有宿管（Part 2 室友贡献）压制、永远排最后入宿。现有经验表明她应具有更高的优先级（通过交换替代高 λ 干员入宿恢复）。需在编排层建模"菲亚梅塔 ↔ 高 λ 干员"交换机制：被交换者的 λ 转入菲亚梅塔的 Part 2（δ_rec=2.0），被交换者 λ 归零退出宿舍竞争。当前贡献评分层面不加——交换是跨窗口编排决策。 — 2026-06-01 — `solver.py` + `mood_flow.py`
[ ] **真言精英小队（基建全局精英设施计数）** — `trade_ord_spd&tag[010]`（phase 2）：固定 +25% + 每间有精英干员（`groupId=="elite"`）的设施 +2%（cap 10间）。无现有机制可复用，需新建 B 层函数 `synergy_elite_facility_count()`：遍历 `all_assignments` 统计含精英干员的设施数，评估阶段注入。规模约 60 行 + 测试。 — 2026-06-02 — `trade_linkages.py` + `evaluate.py`
[ ] **基建布局可配置化** — `LayoutConfig.layout_243()` 硬编码了所有房间、工位数和等级（`RoomConfig.level`），如需适配 252/153 等布局需改 Python 代码。应支持外部 JSON 配置驱动：房间列表、每间房的类型/工位/等级/产物均由配置文件定义，求解器从 `SolverParams` 或独立 JSON 读取 — 2026-05-28 — `models.py` + `params.py`
[ ] **B7 跨房间配对被评估遗漏** — `synergy_cross_room_pair` 在 `evaluate_room` 中存在但 `all_assignments` 从未由组合评估阶段传入（Phase 1 `_evaluate_with_support` 和 Phase 3a `_evaluate_trade_combo` 均不传），导致烈夏↔古米(Mfg↔Trade)和深巡↔乌尔比安(Trade↔任意)的组合评分不含 B7 加成。深巡可接线修复（Trade 评估时 Mfg 已求解），烈夏需算法升级（Mfg 评估时 Trade 未求解，待 k-beam 或迭代 refine 落地后覆盖）。既有经验表明烈夏的组合非当前最优，但深巡可用，待 k-beam 算法实现后一并验证。现状：仅 `refine.py` post-processing 传了 `all_assignments`，主力求解路径（Mfg/Trade 穷举 + 贪心）均缺失。 — 2026-05-28 — `refine.py` / k-beam / 迭代坐标下降
[ ] **瓶颈枚举（互补件一）** — 识别 8-12 个关键瓶颈干员（如黑键该去 Mfg 支撑还是 Trade 主力），枚举所有可行分配方案，对每种方案跑完整求解取最优。将在 Strategy 重构完成后作为 `BottleneckEnumStrategy` 实现 — 2026-05-28 — `solver/strategies/`
[ ] **局部搜索策略化** — 支持 best-improvement、simulated annealing、或基于房间类型的加权搜索。`refine_mode` 将作为 Strategy 属性（见 [strategy-refactor-plan §Step 2.5](./archive/strategy-refactor-plan.md)），SolverConfig 开关迁移后实施 — 2026-05-28 — `solver/refine.py`
[ ] **Office D 向量校准：烟火/无声共鸣影子价格** — 桑葚/深律的 BuffPool 生产链路已完整，但能否在 Office 竞争中胜过絮雨取决于 `D["yanhuo"]` / `D["silent_resonance"]` 的影子价格是否足够高。絮雨产出 perception（1:1→思维链环供迷迭香），桑葚产出烟火（供黑键/乌有/黍）、深律产出无声共鸣（供黑键）。当前 D 向量由 `compute_partial_derivatives` 计算，需在典型 243 布局下跑对照实验确认桑葚/深律在 Office 的实际排名。—— `partials.py` + 对照实验 — 2026-06-02 — `buff_pool.py` + `contribution.py`
[ ] **BuffPool 生产侧全量表驱动化** — 17 个生产者（迷迭香/黑键/乌有/爱丽丝/车尔尼/塑心/森西/絮雨/桑葚/深律/夕/令/重岳/截云等）均可统一为 `BuffProducerEffect` 表驱动，消除 `compute_buff_pool` 内所有名字/buff_id 硬编码分支。关键字段：`dimension`(token)、`amount_source`(fixed/dorm_count/dorm_level/suich_count/office_slots)、`condition`(mood gate)、`exclusive_group`(互斥)、`cascade_to`(级联)。路线：①签名 bool→operator 列表 ②建表替代 if/elif — 2026-05-31 — `buff_pool.py` + `types.py`
[ ] **P1 自身 mp_cost buff 接入** — 当前仅接入 P0 范围（39 条 MFG+TRADE+POWER 无条件自身 buff），尚有 49 条未建模。P1 范围（22 条）：HIRE 14 条（地灵+2.0/斥罪+0.5/桑葚-0.25等）+ TRADING 条件配对 5 条（德克萨斯+拉普兰德同僚条件）+ TRADING 动态 3 条（铎铃烟火联动/巫恋低语）。P1 的关键难点在于动态条件 buff 需要 BuffPool 参数（烟火计数）和 co_worker 条件检测。P2（CONTROL 15条）和 P3（MEETING 12条）优先级更低。详见 `mood_flow.py` `_SELF_MP_COST` 表后的 TODO 注释块 — 2026-05-31 — `mood_flow.py`
- [ ] **mp_cost 累加对升级型技能 double-count** — `_compute_self_mp_cost` 遍历 raw `op.skills` 累加所有 buff 的 mp_cost，对升级型技能（同前缀不同 phase）会重复计算。火神 `manu_prod_spd&limit&cost[000]→[001]` 应得 -0.25 却累加为 -0.40；龙舌兰 `trade_ord_long[000]→[010]` 应得 -0.25 却累加为 -0.50。但裁缝 `trade_ord_wt&cost` α+β 恰好需要叠加（-0.25-0.25=-0.50 正确）——同前缀判定在此处产生双关困境。修复需 per-prefix 豁免机制（类似 `_extract_tailor_level` 对裁缝的 raw skills 豁免）。偏离量仅 0.15-0.25，排班影响边际。代码已加已知限制注释（`mood_flow.py` L305-L311）。 — 2026-06-02 — `mood_flow.py` + `models.py`
- [ ] **synergy 子系统全量 char_id 迁移** — 2026-06-02 完成了 C 层中枢技能的表驱动重构（A/B/C 三表分离），但保留了名称键以与现有 20+ 张 synergy 表保持一致。后续应统一将全子系统表键从干员名切换为 char_id（`control_linkages.py`、`mfg_linkages.py`、`global_linkages.py`、`buff_pool.py`、`trade_linkages.py`、`helpers.py` 名称集合等），一次统一迁移避免"双键宇宙"。需同步更新 `scripts/derive.py` 生成逻辑和 `_derived.py`。需评估 `compute_control_global_bonus` 的 `power_platforms: dict[str,bool]` 参数签名变更的调用链。 — 2026-06-02 — `synergy/` 全子包 + `scripts/derive.py`
