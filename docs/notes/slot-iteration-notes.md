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
2. **λ bisection 未实现**：contribution 公式中不含 `-λ×hours` 项（待第二期 §2.2 #8）
3. **联合扰动未实现**：跨 Phase 耦合对替换（待第二期 §2.2 #9）
4. **心情展平未实现**：令/夕/铅踝的心情门控展平（待第二期 §2.2 #11）
5. **precomputed_support 实际电线**：exhaust_mfg/exhaust_trade 仅接受参数，Phase A/B 尚未实际传入预计算支撑（留待性能优化时启用）
