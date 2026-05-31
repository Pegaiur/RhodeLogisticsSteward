# 需求收件箱

> 原始想法、改进提议、架构疑虑在此登记。评估后路由到版本计划(plan)、或关闭。
> 不区分优先级，不分表，所有需求都登记在此。

## 待处理

<!-- 格式: - [ ] 简短标题 — 描述 — 提出日期 — 可能路由 -->
<!-- 完成后标记 [x]，发版时清理已完成条目  -->

- [ ] **粗评分预筛选优化** — Phase 1 制造站组合预筛选已实现但默认关闭（`rough_score_keep_top=0`）。当前粗评分仅含个人效率 + 四种硬编码标签红利（迷迭香/骑士/红松/杜林），四种红利值（+200/+100/+40/+50）量级合理但未覆盖 A2 技能计数、A6 设施数量等联动。需补充联动红利、验证全面性后再开启。详见 `steward_core/solver/exhaust_mfg.py` `_rough_mfg_score` — 2026-05-29 — `exhaust_mfg.py` + `params.py`
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
