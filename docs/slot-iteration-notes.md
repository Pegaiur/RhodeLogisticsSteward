# 槽位模型实施笔记

> 分支：`feat/slot-iteration`
> 最新更新：2026-05-30

## 架构路线变更（2026-05-30）

SlotIterationStrategy（本分支前四期）已验证 D[d] 反馈框架在真实数据上成立——单班次积分反超 BaselineStrategy（+1,356）。但架构负重过大：

| 问题 | 表现 |
|------|------|
| Pipe 式加工 | Pipeline 线性串联，Phase 间通过 `locked_support` / `assigned_ids` / `assigned_names` 三个可变 dict 通信 |
| 信息断裂 | Phase A/B 穷举在空白中枢上下文中计算 buff_pool，Phase C 结果对穷举不可见（需 override_pool 补丁） |
| 补丁累积 | per-operator 贡献、type3 互斥、边际差分——每一项都是事后发现事后补 |
| 策略层增生 | `strategies/slot_iteration.py` 作为 `baseline.py` 的 fork，复用 exhaust_* 的 Phase 函数签名但覆盖控制流 |

**决策：不修 SlotIterationStrategy，改做 SlotSolver。**

SlotSolver 直接实现 [slot-processing-model-draft.md](slot-processing-model-draft.md) §9.5 混合状态迭代策略。新架构：

- `solver/slot/` 子包，SlotSolver 类为唯一求解入口
- SlotContext 统一状态载体（替代 `locked_support` + `assigned_ids` + `assigned_names`）
- Mfg/Trade 穷举逻辑提取到 `slot/mfg.py` / `slot/trade.py`（复用 `evaluate_room`）
- 中枢/宿舍/发电/会客/办公室统一用 D[d]-based contribution 贪心
- 机会成本内置于贡献评分（巫恋 whisper 不再吃错人）
- 迭代 + 记忆 → 收敛于邻域局部最优

以下为 V1 实验（SlotIterationStrategy）的完整实施记录，作为 V2 设计的经验基线保留。

---

## SlotSolver 实施记录

### Step 1: slot/context.py（2026-05-30）

新增 `solver/slot/` 子包，实现统一状态载体：

- **StateVector**：5 维全局状态向量（yanhuo/perception/engineering_robots/monster_cuisine/silent_resonance），`__getitem__`/`__setitem__` 接口 + `to_dict`/`from_dict` 序列化 + `s_max()` 冷启动上界
- **SlotAssignment**：单槽位分配记录（slot_id/facility_type/product/operator_name/room_index）
- **WindowState**：单窗口状态快照（assignments + S + D）
- **SlotContext**：统一状态载体，替代旧的 locked_support/assigned_ids/assigned_names/GlobalContext 四个碎片化结构。提供 `place()`/`vacate()`/`get_op()` 槽位读写 + `slots_of_type()`/`room_ops()` 按类型查询 + `signature()` 迭代去重 + `clone()` 深拷贝

**偏离记录**：
- 槽位 ID 格式统一为 `{prefix}_{room_index}_{slot_index}`（如 `mfg_0_0`），不区分 CR/PG（product 由 `SlotAssignment.product` 字段存储）
- `op_lookup` 以 `char_id` 为键，`assigned_ids()` 内部构建 `name_to_id` 反向映射
- SlotContext 设计为 mutable（通过 `place`/`vacate` 原地修改），迭代分支通过 `clone()` 深拷贝

**测试**：tests/solver/slot/test_context.py — 27 例全绿（StateVector 7 + SlotID 4 + SlotAssignment 2 + SlotContext 14）

---

# 槽位迭代第一期实施笔记（历史实验）

> 实施日期：2026-05-30

## 偏离决策

### D1: SolverParams 代替 SolverConfig
计划 §2.1 第 3 项要求 `SolverConfig 新增 slot_max_rounds/slot_cold_start`，实际将两个字段放入 `SolverParams`。
理由：`local_search_max_rounds` 等同类数值参数已在 SolverParams 中，保持一致性。Strategy 通过 `config.params.slot_max_rounds` 访问。

### D2: slot_iteration.py 不导入 solver/ 任何模块
计划 §3.3 规定"禁止导入任何 solver/ 下的模块"。初始实现中 `extract_state_vector()` / `_compute_state_delta_for_control()` / `_compute_state_delta_for_dorm()` 内部动态导入了 `SolverParams`，违反规则。
修复：将默认值 `suich_count=5`、`dorm_level=5` 硬编码为模块常量 `_DEFAULT_SUICH_COUNT` / `_DEFAULT_DORM_LEVEL`，消除 solver/ 导入依赖。

### D3: Control Phase 顺序贪心取代批量评分 ⚠️ 已演进
计划 §9.5 Phase C 描述为"对每个 Control 槽位，选 contribution 最高"。初期实现为批量评分取 Top-N（槽位间无差异化）。第三期改为**顺序贪心**：每选一人后重建中枢基线，下一人重算边际——type3 同种取最高和 per-operator 条件加成均依赖此机制生效。

### D4: Phase A/B 复用 exhaust_mfg/exhaust_trade 模块
计划要求 `fill_control.py` / `fill_remaining.py` / `fill_dorm.py` 零修改。Phase A/B 直接调用已有的 `exhaust_mfg()` / `exhaust_trade()` 函数，通过 PartialSolution 快照进行状态管理。这确保了 Mfg/Trade 的组合级穷举逻辑与 BaselineStrategy 完全一致。

### D5: Dormitory 恢复贡献 λ 留空
首期 λ ≡ 0，Dormitory 的 `_contribution_dorm()` 仅计算状态写入 × D 部分，宿舍恢复速率 × hours × λ 项待第二期实现。

## 关键实现细节

### slot_iteration.py 模块结构
- `STATE_DIMENSIONS`: 5 个全局状态维度
- `_BUFF_CONSUMER_DIMENSION`: 从 `_B_BUFF_CONSUMER_TABLE` 自动推导的 pool_key → dimension 映射（含 wushu_crystal → yanhuo、thought_chains → perception 的派生维度处理）
- `IterationContext`: `frozen=True` 不可变 dataclass，含 S/D/λ/ratios
- `extract_state_vector()`: 从分配方案计算 S 向量，复用 `compute_buff_pool()` + `compute_engineering_robots()`
- `compute_partial_derivatives()`: 遍历 Mfg/Trade 分配中的类型 1f 读取者，按公式 `base_rate × hours × (bonus_per/per_unit) / 100 × unit_lmd × drone` 累加各维度 D[d]
- `contribution()`: 统一入口，按 facility 分派到 5 个 helper（control/power/reception/office/dorm）

### Contribution 量纲
所有 contribution 返回值以 **LMD 等值/天** 为量纲：
- 状态写入贡献 = ΔS[d] × D[d]，其中 D[d] 已将 base_rate + product_LMD_per_unit 折算
- Power/Reception/Office 通过 drone_to_mfg/reception_to_mfg/office_to_mfg 比率折算到 Mfg 效率等值再乘 mfg_base_rate_avg_lmd × 24h
- 战斗记录通过 xp_lmd_ratio=1.3 折算为 LMD 等值

### 测试覆盖
- 纯函数测试: extract_state_vector(3), compute_partial_derivatives(3), contribution(8), IterationContext(2)
- 策略测试: 基本执行(1), 确定性(1), 最小池(1), 与 baseline 对比(1)
- 回归测试: Baseline/KBeam/Iterative 执行不变(3), 模块边界(2), exhaust 默认签名(2)

## 遗留问题

1. **✅ 冷启动已实现**：`slot_iter_cold` 已注册但 `SlotIterationStrategy(cold_start=True)` 仍走热启动路径（待第二期 §2.2 #10）
   -> **第二期已实现**：`_cold_start_init()` 构建空填充初始分配，`_execute_cold_start()` 多启动取 max(S, D)
2. **✅ λ bisection 已实现**：contribution 公式中不含 `-λ×hours` 项（待第二期 §2.2 #8）
   -> **第二期已实现**：`update_lambda_bisection()` + contribution 含 `-λ×hours`
3. **✅ 联合扰动已实现**：跨 Phase 耦合对替换（待第二期 §2.2 #9）
   -> **第二期已实现**：`_joint_perturbation()` 对 1f 读者↔类型 2 写入者耦合对做 top-3×3 替换
4. **✅ 心情展平已实现**：令/夕/铅踝的心情门控展平（待第二期 §2.2 #11）
   -> **第二期已实现**：`effective_perception_mood()` + `effective_yanhuo_ling()`（mood_ctx 通路已就绪，铅踝展平依赖 stepped_efficiency 已编码未激活）
5. **✅ override_pool 已传入**：exhaust_mfg/exhaust_trade 仅接受参数，Phase A/B 尚未实际传入预计算支撑（留待性能优化时启用）
   -> **第四期已修复**：`_phase_ab_mfg_trade` 从 A 中实际中枢/宿舍/Office 构造 BuffPool 通过 `override_pool` 传入，对齐 IterativeStrategy 架构模式
6. **✅ type2 vs type3 已缓解**：Contribution 贪心排序中 type3 全局注入远超 type2 状态写入
   -> **第四期已修复**：望从 3376→1437（外势条件互斥），type3 同种取最高互斥消除冗余，per-operator 条件加成路径补全。当前中枢已能混合 type2+type3。
7. **153 布局 Trade 折扣**：`_reader_marginal_prod` 的 `layout_mfg_room_ratio` 参数已就绪但调用方未按布局差异化传入
8. **截云 wushu_crystal 维度转换**：`wushu_crystal = yanhuo // 5` 未在 `_reader_marginal_prod` 和 `compute_partial_derivatives` 中处理


## 第二期实施笔记（2026-05-30 追加）

### D6: λ bisection 简化
单窗口下 λ 的主要作用是控制 Control 槽位的干员竞争——通过惩罚跨轮变动的干员，迫使迭代收敛到稳定分配。多窗口下的完整 bisection（跨窗口 Σ hours ≤ pool）在当前单窗口框架中不适用，简化为"移出→翻倍/移入→减半/不变→衰减"的三态更新。

### D7: 冷启动仅填充空房间
`_cold_start_init()` 构建 18 间空房间的模板分配（Mfg 4间 + Trade 2间 + Control/Power/Reception/Office/Dormitory），不依赖 BaselineStrategy。第一轮迭代的 D 基于 S_MAX 上界计算，驱动 Control/Dorm 的 contribution 贪心选出状态写入者。

### D8: 多启动取 D 和
`_execute_cold_start()` 运行热启动和冷启动各一次，用 ΣD（偏导数和，反映状态读取者的边际价值）作为择优选指标——更高的 ΣD 意味着更强健的联动体系。此方案在不增加迭代成本的前提下提高覆盖度。

### D9: 联合扰动简化
完整模型中的耦合对枚举（~25 对 × 3×3 = 225 次尝试）在当前仅测试数据集中可能不触发。实现保留完整的耦合对检测和 top-3 替换框架，但仅在记忆重访（即单轮无法再找到新分配）时触发。

### 第二期新增测试（14 例）
- λ bisection: 5 例（空/新增/移除/不变/边界）
- S_MAX: 3 例（维度/正值/具体值）
- 心情展平: 2 例（无 mood_ctx 直通）
- contribution+λ: 2 例（惩罚生效/无关干员不受影响）
- 冷启动策略: 2 例（基本执行/不依赖 baseline）

---

## 第三期实施笔记（2026-05-30 验收与建模修复）

本次验收发现产出退化（经验 20,400→15,400, -25%），经诊断定位为三个层面的问题：
技能建模错误、状态向量盲区、贪心策略局限。

### 技能建模修复（slot_iteration.py）

#### F1: `_compute_state_delta_for_control` 边际差分修正
原逻辑：`op.name in control_names → return {全零}`。已在岗的中枢干员被误判为零贡献。
修正：计算 S(Control \ {op}) → S(Control) 的真实差分，即该干员在岗与不在岗的边际状态增量。
影响：夕 contribution 0→308，八幡海铃/焰尾/薇薇安娜 仍为零（百分比 buff，差分盲视）。

#### F2: `_compute_state_delta_for_dorm` 同模式修正
同 F1 模式修正，已在岗的宿舍干员不再返回全零。

#### F3: `_compute_type3_contribution` Trade 基数修正
原逻辑：`bonus.trade_bonus × trade_slots(槽位数=6) × _TRADE_BASE_LMD_PER_HOUR(房间级基数)`。
Trade 的 `_TRADE_BASE_LMD_PER_HOUR` 已是房间级基数（10265/24 LMD/h/站），
但乘的是槽位数(6)而非房间数(2)，导致 type3 贡献 3× 虚高。
Mfg 因 `slots×slot_base ≡ rooms×room_base` 碰巧抵消，未暴露此问题。
修正：`trade_slots`(6) → `trade_rooms`(2)。
影响：望 6250→3376，诗怀雅/阿斯卡纶 4311→1437。

#### F4: `_phase_d_dormitory` 槽位计算修正
原逻辑：`dorm_configs = [(5, 4)]; total_slots = 5`（应为 4×5=20），
导致仅 5 名宿舍干员被选中，后 3 间空置。
修正：从 `config.params.dorm_room_size` / `config.params.dorm_max_operators` 读取。
影响：宿舍 4/4 满员，autofill 3→0。

#### F5: Phase A/B 后 D 向量重算（冷/热启动统一）
原逻辑：每轮末尾统一重算 S/D，Phase C/D 使用轮初的冻结 D。
若 Phase A/B 重新穷举改变了 Mfg/Trade 中的 type1f 消费者，D 已过时。
修正：Phase A/B 后立即重算 S/D 并重建 ctx，Phase C/D 使用最新偏导数。
冷启动因 Mfg/Trade 初空→D₀=0→Phase C/D 无引导信号的问题也由此修复。

### 槽位级链路系统（slot_iteration.py + strategies/slot_iteration.py）

#### SL1: `_build_slot_links()` 维度链路上界估算
背景：D[d]=0 时（无消费者在该维度），type2 中枢写入者 contribution=0。
根因是当前实现只看到"令写入 yanhuo=15"，看不到"黍可以消费 yanhuo"。
新增 `_build_slot_links(A, window_hours) → {dimension: best_marginal}`，
从 `_B_BUFF_CONSUMER_TABLE` 查询每个维度的所有可能 type1f 读者，
取最佳读者的单位边际产出作为该维度的链路上界估算。
链路值是乐观上界——不检查读者能否立即入岗（λ bisection 在迭代中自然纠正）。

#### SL2: `_reader_marginal_prod()` 读者边际产出锚定
计算 `base_rate_lmd × window_hours × (bonus_per/per_unit) / 100`，
仅从 `_B_BUFF_CONSUMER_TABLE` 取 type1f 消费贡献，不含读者的直接生产技能。
锚定：Mfg → CR+PG 加权均值（243→0.5:0.5），Trade → `_TRADE_BASE_LMD_PER_HOUR`。
迷迭香（通用生产力，CR+PG 双产品）的 50:50 均值正确。

#### SL3: `IterationContext.link_value` 字段
新增 `link_value: dict[str, float]` 字段（`frozen=True`，默认 `{}`）。
由 `_build_slot_links()` 在 Phase A/B 后生成，Phase C 的 `_contribution_control` 在 D[d]=0 时
用 `link_value[d]` 替代 state_value 的零分量（替代而非补充，避免双重计量）。

#### SL4: `_can_reader_join()` 容量检查的放弃
初版 `_build_slot_links` 通过 `_can_reader_join` 检查读者能否入岗（布局容量上限）。
测试发现热启动下 Mfg/Trade 满员（12/12），检查永远返回 False → link_value 全零。
改为乐观上界（假设读者可入岗），与冷启动用 S_MAX 的逻辑一致。

### 审计结论（其余函数，第四期修正）

| 函数 | 第三期结论 | 第四期修正 |
|------|-----------|-----------|
| `_contribution_power` | 基数一致性正确 | ✅ 已接入 `synergy_global_faction`，缪尔赛思莱茵生命加成生效 |
| `_contribution_reception` | 同 Power 模式 | 签名对齐，暂未接入 synergy |
| `_contribution_office` | 同 Power 模式 | 签名对齐，暂未接入 synergy |
| `compute_partial_derivatives` | Trade base_rate room/slot 不一致但无重复计数 | 不变 |

### 对比验收结果（第四期终态，12h 单班次）

| 阶段 | 经验/12h | 积分 | 中枢 | 关键修复 |
|------|---------|------|------|---------|
| 修复前 | 15,400 | — | 望(单) + 4空 | — |
| F1-F5 + SL1-SL4 | 16,600 | 19,704 | 望+凯尔希+Mon3tr+诗怀雅+阿斯卡纶 | 边际差分/link_value/宿舍修正 |
| +望外势互斥 | 16,600 | 19,704 | 凯尔希+重岳+Mon3tr+望+诗怀雅 | 望 3376→1437 |
| +type3 同种互斥+顺序贪心 | 15,600 | 19,704 | 凯尔希+重岳+望+令+灵知 | 冗余 type3 消除，令入选 |
| +override_pool | 17,000 | 19,884 | 凯尔希+重岳+望+令+灵知 | 信息断裂修复，Mfg 对齐 |
| +缪尔赛思条件加成 | 17,000 | 19,884 | 同上 | Power 换入缪尔赛思 |
| **+per-operator 贡献** | **18,000** | **21,480** | 凯尔希+重岳+望+**薇薇安娜**+令 | 骑士组入选，积分反超 baseline |

### 已知限制（第四期更新）

1. **中枢组合穷举**：个体贡献评分选出中枢组合优于 baseline 单班次（积分 +1,356），但仍可能存在更优的 5 人组合。C(15,5) 组合穷举是下一步方向。

2. **百分比 buff 差分盲视**：✅ 已解决。per-operator 条件加成路径（`_compute_per_operator_contribution`）已覆盖焰尾/薇薇安娜/涤火杰西卡/八幡海铃/戴菲恩。

3. **153 布局 Trade 折扣缺失**：153 下 Trade=9 槽位（vs 243 的 6），乌有入场概率更高但未对称调整。
   `_reader_marginal_prod` 的 `layout_mfg_room_ratio` 参数已就绪，调用方可按布局传入。

4. **截云 wushu_crystal 维度单位**：`wushu_crystal = yanhuo // 5` 的中间转换在
   `_reader_marginal_prod` 和 `compute_partial_derivatives` 中均未处理，per-yanhuo 边际高估 5 倍。
   与现有代码共享的缺陷，非本次引入。


## 第四期实施笔记（2026-05-30 建模补全）

第四期围绕"贡献公式缺项"展开，从验收退化中识别出三条信息/建模缺口并逐一补齐。

### F6: 望的外势/实地条件互斥（655e5ae）
望从 `_C_CONTROL_GLOBAL_TABLE` 同时提供 mfg 2% + trade 7%，实际为条件互斥型（外势=Trade+Power间数 vs 实地=Mfg间数）。修正后 243 布局下仅 trade 7%（外势 5≥实地 4），contribution 3376→1437。

### F7: type3 同种取最高互斥 + 顺序贪心（a3bf576）
`_compute_type3_contribution` 对候选单独评估（simulated=[op]），未实现"同种取最高"——第二个 trade 7% 与第一个同分但边际为 0。
修复：边际差分（bonus_with - bonus_without）+ Phase C 顺序贪心（每选一人重算基线）。
隐藏 bug：`{op.name: op}` 而非完整 operators 字典，已选中枢对候选不可见。

### F8: 中枢信息断裂——override_pool（ed00ec5）
`_phase_ab_mfg_trade` 未传 override_pool → exhaust 在空白中枢上下文中计算 buff_pool → Phase C 选出的中枢对穷举不可见。
修复后 EXP 15,600→17,000（+9%），黑键回归 Trade，Mfg 配置与 baseline 对齐。

### F9: Power 条件加成——synergy_global_faction（1325b93）
缪尔赛思 Power 技能基础 10% + 莱茵生命条件加成（最高 25%），`_contribution_power` 仅取裸效率 → 排在 #5。
修复：委托 synergy 层已有的 `synergy_global_faction` 获取条件加成。缪尔赛思入选 Power[0]。

### F10: per-operator 条件加成——control_per_operator_bonus（82c8cd2）
焰尾/薇薇安娜/涤火杰西卡/八幡海铃/戴菲恩 五人的真实贡献在 `control_per_operator_bonus` 中，但贡献公式仅含 state_value + type3_value，缺失此路径。
修复：`_compute_per_operator_contribution`——边际差分模式与 type3 同构，遍历 Mfg/Trade 房间取 per-operator 加成边际。Mfg 用 product_rate × LMD，Trade 用 _TRADE_BASE_LMD_PER_HOUR。
验收：EXP 17,000→18,000，积分 19,884→21,480 反超 baseline（+1,356），薇薇安娜入选中枢。

### Contribution 公式全貌（最终态）
```
contribution = state_value       ← ΔS[d] × max(D[d], link_value[d])   [type2 buff写入]
             + type3_value       ← ΔGlobalBonus × capacity × rate     [type3 全局注入]
             + per_op_value      ← ΔPerOpBonus × rate × 24h           [type2 per-op条件]
             + per_op_value      ← 同模式，Trade 用 TRADE_BASE_LMD   [同上，Trade分支]
             - λ × hours         ← λ bisection 惩罚项                [跨轮收敛]
```
