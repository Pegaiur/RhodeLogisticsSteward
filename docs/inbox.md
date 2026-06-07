# 需求收件箱

> 原始想法、改进提议、架构疑虑在此登记。评估后路由到版本计划(plan)、或关闭。
> 不区分优先级，不分表，所有需求都登记在此。

## 待处理

<!-- 格式: - [ ] 简短标题 — 描述 — 提出日期 — 可能路由 -->

<!-- 完成后标记 [x]，发版时清理已完成条目  -->

\[ ] **菲亚梅塔交换机制建模** — `dorm_recExcludeOther` 固定 2.0/h 且在贡献评分中 λ=0（始终在宿舍不入计 hours\_used），导致她被所有宿管（Part 2 室友贡献）压制、永远排最后入宿。现有经验表明她应具有更高的优先级（通过交换替代高 λ 干员入宿恢复）。需在编排层建模"菲亚梅塔 ↔ 高 λ 干员"交换机制：被交换者的 λ 转入菲亚梅塔的 Part 2（δ\_rec=2.0），被交换者 λ 归零退出宿舍竞争。当前贡献评分层面不加——交换是跨窗口编排决策。 — 2026-06-01 — `solver.py` + `mood_flow.py`

\[x] **真言精英小队（基建全局精英设施计数）** — ✅ 已实现。`synergy/facility_group.py` `synergy_facility_group()` 通过 `_FACILITY_GROUP_TABLE` 驱动，含 `trade_ord_spd&tag[010]`（真言，cap 10间）+ `hire_spd_tag[000]`（凯尔希异格）+ `trade_ord_spd&tag[020]`（风絮岁干员）。 — 2026-06-02 提出 → 2026-06-04 关闭

\[ ] **基建布局可配置化** — `LayoutConfig.layout_243()` 硬编码了所有房间、工位数和等级（`RoomConfig.level`），如需适配 252/153 等布局需改 Python 代码。应支持外部 JSON 配置驱动：房间列表、每间房的类型/工位/等级/产物均由配置文件定义，求解器从 `SolverParams` 或独立 JSON 读取 — 2026-05-28 — `models.py` + `params.py`

\[ ] **B7 跨房间配对：烈夏↔古米被阶段顺序遗漏** — `all_assignments` 已由 `phase_mfg`/`phase_trade` 通过 `ctx.build_all_assignments()` 传入（2026-06-03 核查确认）。但 `mfg→trade` 的执行顺序导致结构性遗漏：**烈夏(Mfg/CombatRecord)→古米(Trade) 35% 加成**在 Mfg 评估时 Trade 尚未分配，评分缺失。深巡/贝洛内正常（Trade 评估时 Mfg 已就位）。修复需两阶段联合评估或二趟传递。 — 2026-05-28 → 2026-06-03 更新 — `mfg.py` + `trade.py`

\[ ] **Office D 向量校准：烟火/无声共鸣影子价格** — 对照实验完成（2026-06-03）：D\[yanhuo]=51.3（黍+乌有驱动）、D\[perception]=30.8（迷迭香驱动）、D\[silent\_resonance]=0（黑键未入槽）。桑葚 1,915 > 絮雨 1,504（冷启动消费者 D 下已反超，+411），但斥罪纯效率 2,221 仍是最优解。深律的 silent\_resonance 存在二级冷启动问题——黑键需 D\[silent\_resonance]>0 才能被 Trade 估值，但深律未被选入 Office 就无 silent\_resonance 产出。 — 2026-06-02 → 2026-06-03 对照实验 — `buff_pool.py` + `contribution.py` + `partials.py`

\[ ] **BuffPool 生产侧全量表驱动化** — 步骤①已完成（`compute_buff_pool` 签名从 bool 代理改为 Operator 列表，commit `4606045`）。步骤②待做：17 个生产者统一为 `BuffProducerEffect` 表驱动，消除 `compute_buff_pool` 内名字/buff\_id 硬编码分支。关键字段：`dimension`(token)、`amount_source`(fixed/dorm\_count/dorm\_level/suich\_count/office\_slots)、`condition`(mood gate)、`exclusive_group`(互斥)、`cascade_to`(级联)。 — 2026-05-31 — `buff_pool.py` + `types.py`

\[ ] **P1 mp\_cost buff 接入** — P0 范围（39 条 MFG+TRADE+POWER 无条件自身 buff）已接入。P1 TRADING 条件配对 5 条已接入（`_MP_COST_SELF_PAIR` 表，commit `acf78c4`）。P1 剩余 3 条动态条件：`hire_spd_cost&clue[000]`（雪绒）、`trade_cost&bd2[000]/[001]`（铎铃烟火联动），需要 BuffPool 参数（烟火计数）。P2 CONTROL 条件型 7 条和 P3 MEETING 条件型 7 条优先级更低。详见 `mood_flow.py` `_SELF_MP_COST` 表后的 TODO 注释块。 — 2026-05-31 → 2026-06-03 更新 — `mood_flow.py`

\[ ] **mp\_cost 累加对升级型技能 double-count** — `_compute_self_mp_cost` 遍历 raw `op.skills` 累加所有 buff 的 mp\_cost，对升级型技能（同前缀不同 phase）会重复计算。火神 `manu_prod_spd&limit&cost[000]→[001]` 应得 -0.25 却累加为 -0.40；龙舌兰 `trade_ord_long[000]→[010]` 应得 -0.25 却累加为 -0.50。但裁缝 `trade_ord_wt&cost` α+β 恰好需要叠加（-0.25-0.25=-0.50 正确）——同前缀判定在此处产生双关困境。修复需 per-prefix 豁免机制（类似 `_extract_tailor_level` 对裁缝的 raw skills 豁免）。偏离量仅 0.15-0.25，排班影响边际。代码已加已知限制注释（`mood_flow.py` L305-L311）。 — 2026-06-02 — `mood_flow.py` + `models.py`

\[ ] **synergy 子系统全量 char\_id 迁移** — 2026-06-02 完成了 C 层中枢技能的表驱动重构（A/B/C 三表分离），但保留了名称键以与现有 20+ 张 synergy 表保持一致。后续应统一将全子系统表键从干员名切换为 char\_id（`control_linkages.py`、`mfg_linkages.py`、`global_linkages.py`、`buff_pool.py`、`trade_linkages.py`、`helpers.py` 名称集合等），一次统一迁移避免"双键宇宙"。需同步更新 `scripts/derive.py` 生成逻辑和 `_derived.py`。需评估 `compute_control_global_bonus` 的 `power_platforms: dict[str,bool]` 参数签名变更的调用链。 — 2026-06-02 — `synergy/` 全子包 + `scripts/derive.py`

\[ ] **中枢心情建模补充** — 当前 CONTROL mood buff 用 `len(control)×0.05/h` 通用近似，有 8 条偏差。按难度分三档：🟢易（3 条，加 `_SELF_MP_COST`表项即可）— 涤火杰西卡+0.5、怒潮凛冬+0.5、夕+0.5；🟡中（3 条，需条件判定）— 老鲤阿同室+0.25（需同僚检测）、令消除岁消耗（需中枢名单遍历）、摆渡人+0.02条件型（需萨尔贡同僚检测）；🔴难（1 条，需新维度/新机制）— 若叶睦互为半身（祥子同僚消除）。已完成：歌蕾蒂娅潮汐守望（`_gladiia_aegir_delta`, commit `dd0b377`）。 — 2026-06-02 → 2026-06-03 更新 — `mood_flow.py`

\[ ] **无人机加速目标动态路由** — 当前 `drone_room`/`drone_index` 硬编码为 Mfg\[0]（CR 制造站），不随赤金供需变化。赤金短缺时加速 Trade 是无效加速（加速消耗→缺口更大→有效 LMD 被 ratio 打折），赤金盈余时加速 Mfg 浪费产能。应在 `production.calculate()` 或 solver 层根据各班次赤金供需平衡自动选择：赤字→加速 PG 增产赤金，盈余→加速 Trade 套现，平衡→加速 CR 冲经验。 — 2026-06-03 — `production.py` + `models.py`

\[ ] **Mujica 热情值维度建模（丰川祥子中枢→PG生产力）** — 当前唯一未建模的产值相关中枢技能。丰川祥子 E0/E2 的 `control_prod_bd_spd[000]/[010]` 根据热情值给所有 PG 制造站 +0.5\~4% 生产力。热情值生产者共 4 人：若叶睦(+20)、三角初华(+1/宿舍)、八幡海铃(+10)、祐天寺若麦(+10)，上限约 60 点。需新建 Mujica BuffPool 维度（STATE\_DIMS 新增 + BuffPool 新增生产/消费 + partials 新增 D\[d] 映射），估算 5 人在中枢凑齐时丰川祥子 E2 可达 +4% PG。优先级低于当前 Mfg/Trade 直接效率优化。 — 2026-06-02 — `buff_pool.py` + `partials.py` + `control_linkages.py` + `types.py`

\[ ] **心情恢复贡献续航校准** — 当前 recovery 用 \_compute\_recovery\_value 估算，乘 `params.recovery_damping=0.25` 临时抑制偏高估值。恢复的实际价值在多班次场景体现（续航+1窗口的等效 LMD），单班次无心情压力时 recovery 应接近 0。需建立 `burn × hours` 预期模型替代 damping 魔法常数。路由到 `contribution.py:_compute_recovery_value` + `params.py:recovery_damping`。 — 2026-06-03 — `contribution.py` + `mood_flow.py` + `params.py`

\[ ] **订单上限压缩估计反馈回路** — `compute_trade_order_limit` 用 `operator_estimated_efficiency` 计算孑压缩的 other\_eff，该函数只返回独立效率不含 room 级联动（swires/jie/degenbrecher 等订单上限消费者）。当 combo 含多个消费者时，实际 other\_eff 远大于估计值，导致压缩不足 → order\_limit 高估 → 孑/诗怀雅/锏效率高估。实测 "银灰+孑+诗怀雅(灵知)" 估值 153% vs 实际 \~121%（偏差 32pp），"德+孑+拉" 估值 130% vs 实际 110%（偏差 20pp）。消费者越多偏差越大。需在压缩估计中引入不动点迭代或至少将已知消费者的联动效率纳入 other\_eff。 — 2026-06-04 — `trade_linkages.py:compute_trade_order_limit` + `ramping.py:operator_estimated_efficiency`

\[x] **synergy-systems.md B3-B7 函数名与代码不一致** — ✅ 已修复。文档 B3/B4/B5 标注为已内化至 `BuffPool`/`compute_buff_pool`，B6 修正为 `synergy_global_faction()`，B7 修正为 `synergy_cross_room_pair()`。 — 2026-06-04 → 2026-06-07 关闭 — `synergy-systems.md` + `buff_pool.py` + `global_linkages.py`

\[x] **ramping_efficiency docstring 遗漏 meet 条目** — ✅ 已修复。`efficiency_fn.py` L68 docstring 从"5 条 manu_prod_spd_addition[*] + 发电站爬升预留"修正为"6 条目：5 mfg + 1 meet `meet_spd_hast[000]`"。 — 2026-06-04 → 2026-06-07 关闭 — `efficiency_fn.py`
