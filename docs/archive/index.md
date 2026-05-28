# 里程碑索引

> 记录项目各阶段的完成时间、版本号与核心变更。

| 版本 | 日期 | 里程碑 | 核心变更 |
|------|------|--------|----------|
| [v0.2.0](https://github.com/Pegaiur/RhodeLogisticsSteward/tree/v0.2.0) | 2026-05-28 | MVP完成 | 全box满练243单班次排班，A1-A7/B1-B7/C1-C2联动体系全覆盖 |
| [v0.3.0](https://github.com/Pegaiur/RhodeLogisticsSteward/tree/v0.3.0) | 2026-05-28 | 模块化重构 | synergy/solver 子包拆分 + NamedTuple类型化 + 硬编码表注册器 |
| [v0.4.0](https://github.com/Pegaiur/RhodeLogisticsSteward/tree/v0.4.0) | 2026-05-28 | 求解器三件套 | 支撑包(独占冲突检查) + 局部搜索(单房间替换/干员交换) + 全局状态(包级稀缺度评分)，全部通过 SolverConfig 开关控制 |

## 已归档文档

| 文档 | 归档版本 | 说明 |
|------|---------|------|
| [roadmap-mvp.md](./roadmap-mvp.md) | v0.2.0 | 开发路线图，MVP完成后归档 |
| [refactor-plan.md](./refactor-plan.md) | v0.3.0 | 子包拆分重构计划，完成后归档 |
| [solver-improvement-plan.md](./solver-improvement-plan.md) | v0.4.0 | 求解器三件套优化计划，全部实施后归档 |
