# 槽位迭代第一期实施笔记

> 实施日期：2026-05-30
> 分支：`feat/slot-iteration`

## 偏离决策

### D1: SolverParams 代替 SolverConfig
计划 §2.1 第 3 项要求 `SolverConfig 新增 slot_max_rounds/slot_cold_start`，实际将两个字段放入 `SolverParams`。
理由：`local_search_max_rounds` 等同类数值参数已在 SolverParams 中，保持一致性。Strategy 通过 `config.params.slot_max_rounds` 访问。

### D2: slot_iteration.py 不导入 solver/ 任何模块
计划 §3.3 规定"禁止导入任何 solver/ 下的模块"。初始实现中 `extract_state_vector()` / `_compute_state_delta_for_control()` / `_compute_state_delta_for_dorm()` 内部动态导入了 `SolverParams`，违反规则。
修复：将默认值 `suich_count=5`、`dorm_level=5` 硬编码为模块常量 `_DEFAULT_SUICH_COUNT` / `_DEFAULT_DORM_LEVEL`，消除 solver/ 导入依赖。

### D3: Control Phase 单槽位而非多槽位
计划 §9.5 Phase C 描述为"对每个 Control 槽位，选 contribution 最高"，实际实现中 Control 的 5 个槽位依序填充得分最高的 5 名干员。这是因为 `RoomAssignment` 模型中 Control 只有一个 assignment（含 5 个 operator 名），而非 5 个独立 assignment。
影响：槽位间无差异化竞争——第 1-5 名统一按 contribution 排序，不模拟工位特异性。

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

1. **冷启动未实现**：`slot_iter_cold` 已注册但 `SlotIterationStrategy(cold_start=True)` 仍走热启动路径（待第二期 §2.2 #10）
   -> **第二期已实现**：`_cold_start_init()` 构建空填充初始分配，`_execute_cold_start()` 多启动取 max(S, D)
2. **λ bisection 未实现**：contribution 公式中不含 `-λ×hours` 项（待第二期 §2.2 #8）
   -> **第二期已实现**：`update_lambda_bisection()` + contribution 含 `-λ×hours`
3. **联合扰动未实现**：跨 Phase 耦合对替换（待第二期 §2.2 #9）
   -> **第二期已实现**：`_joint_perturbation()` 对 1f 读者↔类型 2 写入者耦合对做 top-3×3 替换
4. **心情展平未实现**：令/夕/铅踝的心情门控展平（待第二期 §2.2 #11）
   -> **第二期已实现**：`effective_perception_mood()` + `effective_yanhuo_ling()`（mood_ctx 通路已就绪，铅踝展平依赖 stepped_efficiency 已编码未激活）
5. **precomputed_support 实际电线**：exhaust_mfg/exhaust_trade 仅接受参数，Phase A/B 尚未实际传入预计算支撑（留待性能优化时启用）


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
