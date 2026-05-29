# 里程碑索引

> 记录项目各阶段的完成时间、版本号与核心变更。

| 版本 | 日期 | 里程碑 | 核心变更 |
|------|------|--------|----------|
| [v0.2.0](https://github.com/Pegaiur/RhodeLogisticsSteward/tree/v0.2.0) | 2026-05-28 | MVP完成 | 全box满练243单班次排班，A1-A7/B1-B7/C1-C2联动体系全覆盖 |
| [v0.3.0](https://github.com/Pegaiur/RhodeLogisticsSteward/tree/v0.3.0) | 2026-05-28 | 模块化重构 | synergy/solver 子包拆分 + NamedTuple类型化 + 硬编码表注册器 |
| [v0.4.0](https://github.com/Pegaiur/RhodeLogisticsSteward/tree/v0.4.0) | 2026-05-28 | 求解器三件套 | 支撑包(独占冲突检查) + 局部搜索(单房间替换/干员交换) + 全局状态(包级稀缺度评分)，全部通过 SolverConfig 开关控制 |
| v0.5.0 | 2026-05-29 | Strategy 策略层重构 | 约束→效率模型→策略→产出四层架构；Baseline/KBeam/Iterative 三条策略；Phase 文件重命名为动作语义(exhaust_*/fill_*)；BuffPool 可组合化 + 不动点迭代；Pipeline 迁入 BaselineStrategy；CLI 策略选择与 STRATEGY_REGISTRY；制造站性能优化三件套 |
| v0.5.1 | 2026-05-29 | JSON 输出协议对齐 | 输出符合 MAA 基建排班协议 v5.x（id/buildingType/planTimes/scheduleType/drones.enable/Fiammetta）；README.md 新增；strategy-refactor-notes 合并入 plan；inbox 清理 2 条已完成条目 |

## 已归档文档

| 文档 | 归档版本 | 说明 |
|------|---------|------|
| [roadmap-mvp.md](./roadmap-mvp.md) | v0.2.0 | 开发路线图，MVP完成后归档 |
| [refactor-plan.md](./refactor-plan.md) | v0.3.0 | 子包拆分重构计划，完成后归档 |
| [solver-improvement-plan.md](./solver-improvement-plan.md) | v0.4.0 | 求解器三件套优化计划，全部实施后归档 |
| [strategy-refactor-plan.md](./strategy-refactor-plan.md) | v0.5.0 | Strategy 策略层重构计划 + 实施笔记（合并），全部实施后归档 |
| [buffpool-iteration-plan.md](./buffpool-iteration-plan.md) | v0.5.0 | BuffPool 不动点迭代 + Phase 命名计划，全部实施后归档 |
