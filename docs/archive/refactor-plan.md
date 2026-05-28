# 重构方案（已归档）

> **版本**: 2026-05-27 · v0.2.0 MVP 后
> **状态**: 已完成，2026-05 执行完毕。本文件仅供追溯参考。

## 背景

MVP（v0.2.0）完成后，`steward_core/` 整体 3612 行、11 个文件，结构清晰但存在两个明确的维护热点：

| 模块 | 行数 | 占比 | 近 30 commit 修改次数 |
|------|------|------|----------------------|
| synergy.py | 1307 | 36% | 16 次 |
| solver.py | 653 | 18% | 10 次 |
| 其余 9 个文件 | 1652 | 46% | 零星 |

synergy.py 内含 **24 张硬编码数据结构**（含表、集合、常量），其中 10 张使用匿名异构元组；solver.py 的 `solve_mvp()` 为 240 行单体函数，内联全部 5 个 Phase。

**目标**：在进入 MV5 多班次开发前，将两个热点文件拆分为可独立理解与测试的子包，同时将硬编码表从匿名元组升级为带语义的 NamedTuple。

## 重构范围

分五个 Phase：

```
Phase 0: A_{DESC} 命名（消去 A1/C3 等不透明代号）
    │
Phase 1: NamedTuple 类型化 + TABLES 注册器（synergy.py 内部）
    │
Phase 2: 拆分 synergy.py → steward_core/synergy/ 子包
    │
Phase 3: 拆分 solver.py → steward_core/solver/ 子包
    │
Phase 4: 横向重构 _greedy_remaining
```

---

## Phase 0：A_{DESC} 命名 — 消除不透明代号

### 问题

synergy.py 中 16 个联动体系使用 A1/A2/.../B1/.../C2 数字代号作为变量名和注释前缀（约 120 行），agent 需要查表（`docs/synergy-systems.md`）才能理解含义。

### 方案

保留 `A_/B_/C_` 前缀（承载"同设施/跨设施/中枢全局"的层次语义），将数字替换为描述性英文词。

### 影响

- 文件：`synergy.py`（14 变量 + 注释）、`evaluate.py`（3 处）、`solver.py`（4 处）、`production.py`（2 处）
- 改动量：约 60 行，纯改名，零逻辑变化

---

## Phase 1：NamedTuple 类型化 + TABLES 注册器

### 方案

每张异构表定义一个 `NamedTuple` 子类，字段名即文档。同时在 synergy.py 顶部增加 `TABLES` 注册器。

### 需要定义的 NamedTuple

| NamedTuple | 替代的表 | 字段数 |
|-----------|---------|--------|
| `FacilityLinkEntry` | `_A_FACILITY_LINK_TABLE` | 5 |
| `BuffConsumerEntry` | `_B_BUFF_CONSUMER_TABLE` | 4 |
| `FactionEntry` | `_A_ROOM_FACTION_TABLE` | 5 |
| `ExtraFactionEntry` | `_A_ROOM_FACTION_EXTRA` | 4 |
| `GlobalFactionEntry` | `_B_GLOBAL_FACTION_TABLE` | 7 |
| `CrossRoomPairEntry` | `_B_CROSS_ROOM_PAIR_TABLE` | 4 |
| `ZeroingVariantEntry` | `_ZEROING_VARIANT_TABLE` | 3 |
| `RampingSkillEntry` | `_RAMPING_SKILL_TABLE` | 3 |
| `GlobalBonusEntry` | `_C_CONTROL_GLOBAL_TABLE` | 2 |
| `TableMeta` | TABLES 注册器 | 3 |

### 影响

- 文件：`steward_core/synergy.py`
- 改动量：约 190 行
- 新增依赖：无

---

## Phase 2：拆分 synergy.py → 子包

### 目标结构

```
steward_core/synergy/
├── __init__.py           # 重导出全部公开符号
├── types.py              # 所有 NamedTuple + TableMeta + TABLES
├── registry.py           # SystemContributor + get_system_contributors
├── mfg_linkages.py       # A层制造站联动
├── trade_linkages.py     # A7 孑订单 + 鸿雪宣发
├── facility_linkages.py  # A层设施数量联动 + 发电站计数
├── control_linkages.py   # C层中枢全局加成
├── global_linkages.py    # B层全局阵营 + 跨房间配对
├── buff_pool.py          # BuffPool + 计算 + 消费
├── classification.py     # Mfg/Trade 干员分类 + 剪枝 + 候选池
├── helpers.py            # 工具函数 + 常量
└── mood.py               # compute_global_burn
```

---

## Phase 3：拆分 solver.py → 子包

### 目标结构

```
steward_core/solver/
├── __init__.py            # solve_mvp() 编排器
├── support.py             # compute_optimal_support + _evaluate_with_support
├── greed.py               # _greedy_allocate + _generate_combos + _evaluate_trade_combo
├── phase1_mfg.py          # Phase 1: 制造站穷举
├── phase2_control.py      # Phase 2: 中枢填充
├── phase3_trade.py        # Phase 3a: 贸易站穷举
├── phase3_remaining.py    # Phase 3b: 剩余设施贪心
└── phase4_dorm.py         # Phase 4: 宿舍填充
```

---

## Phase 4：横向重构 _greedy_remaining

### 方案

采用 `room_type` 分支的 `get_effective_efficiency` 模式，替代当前 if-elif-else 链。

---

## 测试文件独立拆分

- `test_production.py` → `test_production.py` + `test_trade_orders.py`
- `test_mood.py` → `test_mood.py` + `test_mood_report.py`

---

## 执行结果

所有 Phase 0-4 已于 2026-05 执行完毕。最终结构见 `AGENTS.md` §项目结构。
