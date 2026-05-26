# MVP 实施笔记

> 记录开发过程中的偏差决策、发现、未决问题。
> 每个条目标注日期和对应里程碑。

---

## MV0 (数据模型) — 2026-05-26

### 决策 1: 保留旧版 `load_operators`
- **背景**: 审查发现删除旧函数会破坏 `run_solver.py`
- **决策**: 保留为兼容层，标注 `MV4 后移除`
- **影响**: data_loader.py 从 ~140 行膨胀到 ~230 行（+90 行旧代码）

### 决策 2: `integrate_segments` T 参数
- **背景**: MV0 占位实现中 T 未被使用
- **修复**: 增加 T 裁剪逻辑（段尾超出 T 时截断），与 efficiency-function-design 对齐
- **影响**: 解决了审查 P3 建议项

### 发现 1: `skill_icon` 字段改用 `buff_id`
- 旧版 data_loader 从 `building_data.json` 的 `skillIcon` 字段获取
- 新版 `character_identity.json` 不包含 `skillIcon`，改用 `buff_id` 填入
- **风险**: `mood.py` 中 `bskill_ctrl_cost` 的 `skill_icon` 过滤逻辑依赖此字段格式
- **状态**: 旧版兼容层未改动，`load_operators_v2` 路径尚未被 `mood.py` 使用 → 无影响

---

## MV1 (效率函数) — 2026-05-26

### 决策 3: MVP 不实现 mood_gate
- `efficiency-function-design.md` 中定义了心情门控形态（如 mood<12→+15, mood>12→+10）
- MVP 12h 班次下 mood 从 24 降到最低 ~16（三人房 0.65/h）→ mood 始终 > 12 → 心情门控不切换
- **决策**: `efficiency_fn.py` 只实现 `constant_efficiency` 和 `ramping_efficiency`，mood_gate 归入联动函数（`synergy.py` B1 层）
- **影响**: 减少约 30 行实现，符合 MVP 聚焦原则

### 决策 4: 支配偏序在 12h 场景下退化
- 12h 内所有 e(t) 为常数段（无 mood 截断）→ 支配退化为 O(1) 比较: `k_A ≥ k_B AND t_red_A ≥ t_red_B`
- 由于 t_red 全部 > 12h，支配退化为纯效率值比较
- **决策**: 先实现通版 `_dominates()` 和 O(1) 简化版 `_dominates_simple()`，MVP 默认走简化版
- **影响**: 排序实际就是 `sorted(candidates, key=lambda x: x[0], reverse=True)`

### 偏差 1: `_dominates_simple` 的 `_key_values` 实现
- **问题**: 文档 `efficiency-function-design.md` 中的 `_key_values` 取 `seg[-1].t_start + seg[-1].dt` 作为 t_end。
  这导致 mood_burn 截断场景下 t_end 取到了归零段的终点（如 24h），而非有效段的终点（如 16h）。
- **修正**: `_key_values` 改为取**最后一个非零段**的终点：
  ```python
  for s in segments:
      if s.a > 0 or s.b > 0:
          t_end = s.t_start + s.dt
  ```
  这使得支配关系在截断场景下正确工作（如 eff=40/8h vs eff=25/12h → 互不支配）。
- **影响**: 与文档描述有偏差，但更正确。记录以备文档同步。

### 偏差 2: 互支配时 DAG 不加边
- **问题**: `rank_by_dominance` 中两节点互支配时（如 eff=30 vs eff=30），原实现给两边都加边 → 形成循环 → DAG 拓扑排序失败。
- **修正**: 仅在**严格**支配（A 支配 B 且 B 不支配 A）时加入有向边：
  ```python
  a_dom_b = _dominates_simple(A, B)
  b_dom_a = _dominates_simple(B, A)
  if a_dom_b and not b_dom_a:
      graph[A].add(B)
  ```
- **影响**: 等价干员同时出现在 in_degree=0 的极大元中，通过全积分退化解决定序。

---

## MV2 (联动函数) — 2026-05-26

### 决策 5: 联动用干员名匹配而非 buff_id
- **背景**: 测试中构造的 Operator 无 skills 列表，无法从 buff_id 判定联动角色
- **决策**: A1(配对)、A4(别名)、A5(自动化) 使用硬编码干员名查找表；A3(技能计数) 使用 `buff_name` 中的关键词（标准化/莱茵科技/金属工艺）匹配
- **权衡**: 干员名硬编码意味着异格干员（如麒麟R夜刀 vs 夜刀）需要单独加入表。但 MVP 全box 场景下此问题不突出
- **影响**: ~30 行硬编码表，MV 后续可改为从 buff 元数据自动生成

### 偏差 3: A5 自动化只取最高等级
- 森蚺同时持有 α(5%/站) 和 β(10%/站)
- 当前实现按名查表取得固定值，未检测实际持有的 buff 版本
- **决策**: 真数据加载后，通过检测干员 skills 中的 `manu_prod_spd&power` buff_id 版本判定等级
- **影响**: 当前硬编码温蒂=15%/站，森蚺=5%/站。真数据下森蚺应走 β(10%/站)

---

## MV3 (求解器) — 2026-05-26

### 偏差 4: 真数据下制造站候选人数超出文档预期
- **预期**: 文档 `strategy-brief.md` 写 CR≈60, PG≈56（基于 description 文本分析）
- **实际**: `has_skill_for("Mfg", "CombatRecord")` 判定下 CR=82, PG=83
- **原因**: `EfficiencyMap` 中 `all` 键让所有通用技能对双产物均可用，而早期脚本仅用 description 文本判定
- **决策**: 82 人 × C(82,3) 仍可接受（~88k 组合），剪枝后约 4-5k。不修正 EfficiencyMap 判定逻辑
- **影响**: 实际组合数比预期高约 30%，但仍在 MV3 计算预算内（< 1 秒）

### 偏差 5: 分类测试用 Operator 对象比较 vs 干员名比较
- `_classify_mfg_operators` 返回 `MfgClassification(anchors=list[Operator])`，测试中 `assert "水月" in result.anchors` 失败（字符串 vs Operator 对象）
- **修正**: 测试改为 `{op.name for op in result.anchors}` 比较
- **影响**: 测试修正，代码逻辑不变

### 发现 2: 真数据下 Control 固定方案的干员不存在
- `solve_mvp` 中 `FIXED_CONTROL = ["令", "重岳", "夕", "凯尔希", "焰尾"]`
- 从 `character_identity.json` 加载后，这些干员名可能不全匹配（如 Mon3tr 替代凯尔希）
- **状态**: MV4 入口整合时需验证并调整

---

## MV5 Phase 5a (A6 设施数量联动) — 2026-05-26

### 实现范围
- `synergy_facility_count()`: 7 名干员的设施数量联动，基于 `LayoutConfig` 提取 Trade/Meeting/Mfg recipe 统计，宿舍等级默认 12（4×Lv3）
- 接入 solver `_evaluate_room_combo()` 和 production `_room_efficiency_integral()`
- 8 个单元测试（TDD：红灯→绿灯）

### 决策 7: 宿舍等级硬编码为默认参数
- LayoutConfig 不包含宿舍信息（宿舍不属于 243 工作设施）
- **决策**: `synergy_facility_count(dorm_levels=12)` 作为默认参数，后续可由求解器传入实际配置
- **影响**: 切换布局（如 252）时需同步调整默认值

### 发现 3: A6 Trade 干员未被贪心分配选中
- 空弦/伺夜/渡桥/石英的 A6 buff 在 buffs_infrastructure.json 中 efficiency=0（条件型）
- `op.best_efficiency("Trade", "Money")` 对这些干员返回 0 → `_greedy_remaining` 中 `eff > 0` 过滤掉
- **根因**: `_greedy_remaining` 不调用 synergy 函数，只依赖原始效率值
- **状态**: 制造站 Mfg[2]（引星棘刺 +3%/贸易站）已生效。Trade 端待后续优化，可用 `_evaluate_room_combo` 替代 `rank_by_dominance` 方式

### 偏差 6: 引星棘刺的 A6 buff 数据确认
- `manu_prod_spd&trade[1000]` (原质塑金副产物) efficiency=0，description 含"每个贸易站贵金属+3%"
- `_A6_FACILITY_TABLE` 中硬编码为 3.0%/贸易站，与 A3 技能计数（金属工艺·α）独立叠加
- Mfg[2] 总加成: 个体效率(A3+metal) + synergy_skill_count(金属工艺) + synergy_facility_count(引星棘刺 6%) = 214%

---

## MV5 Phase 5b (C1 中枢全局效率) — 2026-05-26

### 实现范围
- `GlobalBonus` dataclass + `compute_control_global_bonus()` 函数
- 硬编码中枢全局效率表：凯尔希(最高权限) → 制造站+2%，同种取最高
- 注入 `solver._evaluate_room_combo()` 和 `production._room_efficiency_integral()`，全局加成 = bonus × T
- 3 个单元测试（TDD：红灯→绿灯）

### 决策 8: 全局加成作为 e(t) 积分附加项
- 全局效率加成不影响 per-operator e(t)，而是直接加到房间总积分
- `total += global_bonus.mfg_bonus * T` 在 operator loop 之后执行
- **影响**: 与 per-operator 技能加成正交叠加，数学等价于 P(t)=1+0.01n+Σeᵢ/100+global/100

### 效果
- 固定中枢（令+重岳+夕+凯尔希+焰尾）→ 仅凯尔希触发 → 4 间制造站各 +2%
- CombatRecord: 208%→210%, 203%→205%；PureGold: 214%→216%, 193%→195%

