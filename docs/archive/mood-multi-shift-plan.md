# 心情建模与多班次排班计划

> **版本**: 2026-05-29 · 已实施 · 合并至 master（未打 tag）
> **归档日期**: 2026-05-30
> 
> Steps 1-7 全部实施完毕（29 commits），含 MoodContext、MoodModifiers、宿舍恢复评估、反硬编码、
> mood_burn 截断 + ~~蓝脸衰减~~（**⚠️ 已于 2026-05-31 撤销，见下文**）、fill_dorm_with_scheduling、solve_multi_shift() 编排器、菲亚梅塔输出激活。
> 
> **已知未完成**：跨班次轮换调度（中枢干员重复分配）、菲亚梅塔交换决策、测试套件。
> 后续由 `slot-processing-model-draft.md` 槽位加工模型替代。

> ## ⚠️ 重要更正（2026-05-31）
> 
> **§ 蓝脸效率衰减（64a8c65）已推翻。**
> 
> 游戏内 **蓝脸（mood≤12）仅为 UI 视觉标记，绝不干员效率**。红脸（mood=0）才是唯一导致效率归零的游戏机制。
> 本计划在 64a8c65 中引入的 `效率 × (mood/12)` 线性衰减是 **建模错误**，已于 2026-05-31 从全部代码中清除；
> `SolverParams.mood_blue_face` 参数及 `constant_efficiency` / `ramping_efficiency` 中的蓝脸分支已移除。
> 
> **§ interval_hours=8.0 班间间隔假设已推翻。**
> 
> 游戏内班次之间无间隔（结束即开始），恢复通过宿舍在位实现。`interval_hours` 默认值已改为 0，
> `after_recovery` 调用加 `interval_hours>0` 守卫。见 inbox#L17 和 `params.py`。
> 令/夕等干员的 per-operator 心情阈值（硬编码 12.0）不受影响——那是游戏原生机制，与通用蓝脸衰减无关。

## 实施笔记

### 2026-05-29 · Step 2 完成（f64ffdd）

- `steward_core/mood_flow.py` 新增（325行）：`MoodModifiers`(7字段) + `compute_mood_modifiers()` + `compute_global_burn()` + `MoodContext`(11字段+10方法)
- **审查修复**：`ensure_modifiers()` 原用伪 Operator(char_id="", name=name) 无 skills，玛恩纳 mlynar_spread 检测永久失效。修复方案：新增 `_op_lookup: dict[str, Operator]` 内部字段，`fresh()` 时注入，`_resolve_control_operators()` 解析时优先查表
- `work_burn()` 原使用 `_BASE_BURN_3=0.75`（已于 `761995d` 迁移至动态公式 `1.0-0.05×(slots-1)=0.90`）
- `dorm_recovery()` 返回 0.0 占位，`after_recovery()` 实质空操作——**偏差记录**，依赖 Step 1
- `after_shift()` 对所有设施硬编码 room_type="Mfg"/room_slots=3——**偏差记录**，待 per-room burn 修正
- `synergy/mood.py` 委托至 `mood_flow`（保留旧 `compute_global_burn` 签名，`worker_count` 参数未传递——旧签名中此参数从未被使用，兼容无影响）
- `solver/config.py` 新增 `mood_ctx: MoodContext | None = None`
- `solver/params.py` 新增多班次/心情参数（已在 1318aba 提交中一并更新）：`shift_count`, `interval_hours`, `fiammetta_enabled`, `mood_work_threshold`, `mood_blue_face`, `mood_red_face`
- 存量 428 测试全部通过

### 2026-05-29 · Step 1 完成（5f777b5）

- `steward_core/dorm_recovery.py` 新增（80行）：`evaluate_dorm_recovery()` 实现 6 条聚合规则
- 聚合规则：菲亚梅塔自律(+2.0隔离) → 自身恢复(max) → 单体恢复(max) → 全体恢复(sum) → 中枢全局加成 → 人间烟火
- `MoodContext.dorm_recovery()` 从占位改为委托 `evaluate_dorm_recovery()`
- 支持 dorm_assignments 模式（从内部查同宿舍）和 dorm_mates 模式（评估候选配置）

### 2026-05-29 · Step 3 完成（3c0ea48）

- `synergy/buff_pool.py`：新增 `xi_mood_below_12: bool | None = None` 参数，None=向后兼容无条件+10
- `solver/context.py`：`from_estimated()` 和 `from_plan()` 新增 `mood_ctx` 参数，不为 None 时从实值提取心情门控；`from_plan()` 中 `ling_mood_below_12 = has_rosmontis` 代理仅在 mood_ctx=None 时作为回退
- `solver/strategies/iterative.py`：`_initial_pool()` 从 config.mood_ctx 读取真实心情，无 config 时保持硬编码 True

### 2026-05-29 · Step 4 完成（a6b22b3）

- `efficiency_fn.py`：`ramping_efficiency()` 新增 `t_initial` 参数（暖机偏移）；新增 `stepped_efficiency()`（铅踝梯级衰减）
- `synergy/mfg_linkages.py`：`operator_ramp_segments()` 新增 `t_initial` 参数透传
- `evaluate.py`：`evaluate_room()` 新增 `mood_ctx` 参数，不为 None 时启用：
  - mood_burn 截断 → `constant_efficiency(mood_burn=...)`
  - warmup_map → `operator_ramp_segments(t_initial=...)`
  - 铅踝 → `stepped_efficiency(mood_burn=..., mood_initial=...)`
- `evaluate_room()` 内 `TYPE_CHECKING` 块导入 `MoodContext` 避免循环依赖

### 2026-05-29 · Step 5 完成（f23e81d）

- `solver/fill_dorm.py`：新增 `fill_dorm_with_scheduling()`（94行）
- 从 assignments 识别工作干员（Mfg/Trade/Power/Reception/Office）
- 排除工作干员+中枢干员后的剩余干员作为宿舍候选
- B 层生成者优先（`get_system_contributors("Dormitory")`）→ 高星优先
- 轮询填充 4 间宿舍至满员，更新 `mood_ctx.dorm_assignments` 映射

### 2026-05-29 · Step 6+7 完成（7f8e686）

- `solver/__init__.py`：新增 `solve_multi_shift()`（105行）
  - `MoodContext.fresh()` 初始化 → 循环 shift_count 次 → `solve_mvp()` 求解 → `_collect_control_from_plan()` + `_collect_working_from_plan()` 应用心情消耗 → `fill_dorm_with_scheduling()` 覆盖宿舍 → `after_recovery()` 班间恢复
  - 辅助函数 `_collect_control_from_plan()` / `_collect_working_from_plan()`
  - 心情过滤：`mood_of(name) >= mood_work_threshold` 才进入候选池
- `output.py`：`_shift_to_json()` 新增 `mood_ctx` 参数，`Fiammetta.enable` 从 `mood_ctx.fiammetta_swap_planned` 读取（默认 False）

### 实施偏差摘要

| 偏差 | 详情 | 影响 |
|------|------|------|
| `work_burn` 使用 0.75 非 plan 的 0.90 | 与 `compute_global_burn` 保持兼容，待 mood_burn 激活后统一修正 | 多班次 burn 值偏低 0.15 |
| `after_shift` 硬编码 room_type/slots | Caused by `work_burn` 不按 room_type 区分 | 非 Mfg 设施 burn 值不准 |
| `dorm_recovery` yanhuo_bonus 使用 modifiers.yanhuo_recovery | plan 中 `yanhuo_recovery = 0.05 + yanhuo//20*0.05` 已含基础+烟火部分，宿舍恢复中 yanhuo 联动应为纯烟火÷20×0.05 | 多算了 0.05 基础值 |
| `fill_dorm_with_scheduling` 菲亚梅塔交换未实现 | plan §5 的"选择最需要恢复的核心干员作为交换目标"逻辑未实现 | 菲亚梅塔价值未挖掘 |
| 测试套件未新增 | plan §10 的 150+80+40+30 行新测试未编写 | 覆盖率缺口，待后续补充 |

### 2026-05-29 · 审查修复（f5cbb16）

4 路 solution-evaluator 并行审查发现 5 个阻塞/高优先级问题，已全部修复：

| 修复 | 文件 | 详情 |
|------|------|------|
| work_burn 公式一致性 | `mood_flow.py` | `recovery` 新增 `modifiers.control_recovery`（中枢每干员 +0.05/h），与 `compute_global_burn` 对齐 |
| modifiers 跨班次缓存 | `solver/__init__.py` | `_collect_control_from_plan` 中 `replace(..., modifiers=None)` 强制下一轮重新计算 |
| fill_dorm 旧分配清理 | `solver/fill_dorm.py` | `fill_dorm_with_scheduling` 开头清除已有 Dormitory 类型 assignment，避免重复条目 |
| mood_ctx 输出传递 | `solver/__init__.py` | `solve_multi_shift` 返回 `_build_output_config(config, mood_ctx)` 替代原始 config，使 `output.py` 能读取最终 Fiammetta 状态 |
| 死代码/文档修正 | `context.py`/`buff_pool.py` | 移除 `effective_power is not None` 冗余检查；修正 `mood>=12` docstring 阈值

### 2026-05-29 · §7 下游透传补齐（c236347→3ed0d8c）

4 笔提交完成 plan §7 标记的 7 个 mood_ctx 未透传文件的衔接工作：

| 提交 | 文件 | 改动 |
|------|------|------|
| `c236347` fix | `mood_flow.py` `synergy/mood.py` | `compute_global_burn` 新增 `worker_count` 参数并透传，消除静默丢弃隐患 |
| `60b9af0` feat | `greed.py` `fill_remaining.py` `exhaust_trade.py` | `_evaluate_trade_combo`/`_greedy_remaining` 新增 mood_ctx 参数，激活 constant_efficiency 的 mood_burn 截断；`fill_remaining`/`exhaust_trade` 透传 config.mood_ctx |
| `bae1b75` feat | `production.py` `refine.py` `kbeam.py` | `_CalcCtx` 新增 mood_ctx 字段；`calculate()`/`_production_score()`/`evaluate_full_plan()`/`_select_best()` 全链路透传；`_CalcCtx.mood_ctx` 类型标注 `MoodContext \| None` 与 evaluate.py 一致 |
| `3ed0d8c` feat | `support.py` `exhaust_mfg.py` `kbeam.py` | `_evaluate_with_support` 新增 mood_ctx 参数，非 None 时从 `mood_ctx.is_below()` 提取令/夕门控替代 `has_rosmontis` 代理；透传至 `from_estimated` + `evaluate_room` |

**未完成的 §7 文件（无需 mood_ctx 透传）**：
- `solver/strategies/baseline.py`：Pipeline 通过 config 被动携带 mood_ctx，各 Phase 函数已独立消费，无需显式改动
- `solver/global_state.py`：纯 bundle_availability 计数，与心情无关
- `steward_core/models.py`：SteppedSegment 不需要，铅踝梯级衰减通过 `stepped_efficiency()` 已就绪

### 2026-05-29 · ~~blue face 效率衰减（64a8c65）~~ ⚠️ 已推翻

> **此节描述的内容已于 2026-05-31 全部撤销。** 蓝脸衰减是建模错误——游戏内蓝脸仅为 UI 视觉标记，不影响效率。
> 仅红脸（mood=0）导致效率归零。

根因：`constant_efficiency` 有两处缺陷导致双班次产出相同：

（以下为历史记录，不再生效）

1. `t_red = 24.0 / mood_burn` 写死满心情 → 多班次下 mood_initial=13.2 时 t_red 被高估为 26.67h（实际 14.67h）
2. 缺少蓝脸衰减建模 → mood<12 时效率不下降

修复：
- `constant_efficiency` 新增 `mood_initial`/`mood_blue_face` 参数；mood≥12 满效率，0<mood<12 线性衰减 (× mood/12)
- `evaluate_room` 从 mood_ctx 提取 per-operator mood 并传入 constant_efficiency
- `after_recovery()` 清除 warmup_hours（宿舍恢复重置爬升进度，菲亚梅塔交换是唯一保留途径）

验证：2×12h 双班次不再相同——蓝脸惩罚使 shift1 工作干员在 shift2 效率降至 56%，求解器自动选择新鲜干员替代。

### 偏差更新

| 偏差 | 状态 | 说明 |
|------|:---:|------|
| ~~`work_burn` 使用 0.75 非 0.90~~ | ✅ 已修复 | `761995d` 迁移至 `1.0-0.05×(slots-1)` |
| `after_shift` 硬编码 room_type/slots | 持续 | 需 per-room burn 计算，burn 公式已修复但 after_shift 仍用单值 |
| ~~`dorm_recovery` yanhuo_bonus 多算 0.05~~ | ✅ 已修复 | `73a4967` yanhuo_recovery 扣除重岳基值 0.05，仅保留烟火联动 |
| 菲亚梅塔交换未实现 | 持续 | `fill_dorm_with_scheduling` 尚未实现交换逻辑 |
| 测试套件未新增 | 持续 | plan §10 测试未编写 |
| ~~worker_count 静默丢弃~~ | ✅ 已修复 | `c236347` 已透传 |
| ~~mood_work_threshold 默认 0.0~~ | ✅ 已修复 | `761995d` 多班次自动使用 mood_blue_face=12.0 |
| ~~`_BASE_BURN_3` 死代码残留~~ | ✅ 已修复 | `73a4967` 从 helpers/__init__/params 清理 |

### 2026-05-29 · burn 公式修正 + 阈值激活（761995d）

- `work_burn()` 与 `compute_global_burn()` 迁移至动态公式：`base = 1.0 - 0.05 × (slots-1)`，3 工位 → 0.90
- `solve_multi_shift()`：`mood_work_threshold=0` 时自动使用 `mood_blue_face=12.0` 作为有效阈值
- 2×12h 班次验证：shift1 后工作干员 mood=13.2 > 12.0，仍可通过阈值。两班次产出相同是数学最优解（干员有余量完成两班），非 bug。3 班次模式下 shift3 才会自然触发过滤

## 1. 问题诊断

### 1.1 硬编码心情门控 — "令 mood<12" 传染链

当前令的心情门控 (`mood ≤ 12 → 烟火→感知切换`) 以布尔值形式通过 **4 个调用层** 硬编码传播：

```
┌──────────────────────────────────────────────────────────────────┐
│ buff_pool.py:102-106                                              │
│   if "令" in names:                                               │
│       if ling_mood_below_12:                                      │
│           perception += 10                                        │
│       else:                                                       │
│           yanhuo += 15                                            │
│                                                                   │
│   compute_buff_pool(..., ling_mood_below_12: bool = False)        │
└────────────┬──────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ context.py:54                     ← GlobalContext.from_estimated  │
│   ling_mood_below_12: bool = False                                │
│                                                                   │
│ context.py:150                    ← GlobalContext.from_plan        │
│   ling_mood_below_12 = has_rosmontis   ← 用迷迭香存在性代理心情！   │
└────────────┬──────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ support.py:146                    ← _evaluate_with_support        │
│   ling_mood_below_12=has_rosmontis                                │
│                                                                   │
│ iterative.py:95                   ← IterativeStrategy._initial_pool│
│   ling_mood_below_12=True           ← 乐观假设，永远 mood>12       │
└──────────────────────────────────────────────────────────────────┘
```

**两个具体问题**：

| 位置 | 硬编码内容 | 多班次风险 |
|------|-----------|-----------|
| `context.py:L150` | `ling_mood_below_12 = has_rosmontis` — 用"迷迭香在制造站"代理"令心情<12" | 12h单班次下迷迭香在场≈令心情已经消耗12h，但2班次下shift1头几小时令心情仍>24-(0.75-0.25)×t |
| `iterative.py:L95` | `ling_mood_below_12=True` — 永远假设令心情>12 | 迭代策略始终以"令产出烟火"的乐观Pool为基准，shift2下与实际不符 |
| `buff_pool.py:L111-112` | `if "夕" in names: perception += 10` — **夕的心情门控完全未建模**（游戏内夕也是mood>12才给感知） | 12h单班次下永远成立，2班次下shift2可能不成立 |

### 1.2 菲亚梅塔机制未被建模

菲亚梅塔的两条宿舍技能构成全游戏最强心情管理机制，但当前求解器完全未使用：

| buffId | 名称 | 效果 | 建模状态 |
|--------|------|------|:---:|
| `dorm_recExcludeOther[000]` | 自律 | 自身心情恢复 **+2.0/h**（隔离外部加成） | ❌ 未建模 |
| `dorm_exchangeAp[000]` | 患难之交 | 满心情时与前一位干员交换心情值 | ❌ 仅输出层 `enable: false` |

### 1.3 心情衰减技能休眠

| buffId | 干员 | 效果 | 代码状态 |
|--------|------|------|:---:|
| `manu_prod_spd_reduce[000]` | 铅踝 | `e(t) = 30 - 5×⌊(24-mood(t))/4⌋` | [efficiency_fn.py](file://d:/Dev/RhodeLogisticsSteward/steward_core/efficiency_fn.py) mood_burn=0.0 → 永不触发表退 |

---

## 2. 心情门控技能完整清单

### 2.1 BuffPool 层门控（改变全局资源池构成）

| 干员 | 条件 | 产出A (mood>12) | 产出B (mood≤12) | 当前状态 |
|------|------|:---:|:---:|:---:|
| **令** | mood≤12 切换 | +15 烟火 | +10 感知信息 | 硬编码 `ling_mood_below_12: bool` |
| **夕** | mood>12 有效 | +10 感知信息 | 0 | **门控未建模**（无条件+10）|

### 2.2 e(t) 层门控（改变干员自身效率曲线）

| buffId | 干员 | 机制 | 表达式 |
|--------|------|------|--------|
| `manu_prod_spd_reduce[000]` | 铅踝 | 梯级衰减 | `30 - 5×⌊(24-mood)/4⌋` |

### 2.3 心情恢复层（改变消耗/恢复速率）

| 机制 | 干员 | 效果 | 建模难度 |
|------|------|------|:---:|
| 中枢减免 | 全部中枢干员 | 每人 +0.05/h | ✅ 已实现 `synergy/mood.py` |
| 重岳孤光共照 | 重岳 | +0.05 + 烟火÷20×0.05/h | ✅ 已实现 |
| **玛恩纳公事公办** | 玛恩纳 | 工作设施 +0.1/h + 中枢恢复扩散到工作设施 | ❌ 待建模 |
| **control_dorm_rec 系列** | 苇草/灰毫/妮芙/阿斯卡纶/多萝西 | 中枢→宿舍恢复 +0.05~+0.1/h（5条） | ❌ 待建模 |
| 宿舍自身恢复 | 菲亚梅塔 | +2.0/h（隔离） | ❌ 待建模 |
| 宿舍单/群体恢复 | 塑心/车尔尼等 | +0.55~+1.0/h | ❌ 待建模 |
| 心情交换 | 菲亚梅塔 | 满心情↔目标互换 | ❌ 待建模 |

### 2.4 要害遗漏：玛恩纳 `control_mp_lonely[000]`

玛恩纳 Phase 2 技能 **"公事公办"** (`control_mp_lonely[000]`) 是中枢体系唯一的**心情恢复扩散**机制：

| 效果 | 目标 | 数值 |
|------|------|------|
| 工作设施心情恢复 | 部分设施内工作干员 | **+0.1/h** |
| 中枢恢复扩散 | 中枢内控制类技能（每人+0.05）扩散至工作设施 | 每人+0.05/h × N人 |

当前 `synergy/mood.py` 的 `compute_global_burn()` 只计算了中枢基础减免和重岳加成，**完全未建模此扩散机制**。

### 2.5 暖机跨班连续 — 爬升型技能的跨班价值

游戏中 7 条爬升型技能（如 `manu_prod_spd_addition[030]~[041]`，首小时 15~20% + 1~2%/h，上限 25%）存在**跨班连续价值**：

```
Shift 1 (12h):  0h→10h 爬升至上限，10h→12h 上限运行
               ↓
               如果换了新干员 Shift 2 → 重新从 0 开始爬升
               如果保持原干员 Shift 2 → 全程上限运行（前提：心情恢复）
```

爬升技能的 12h 平均效率 ≈ (k0 + ceiling) / 2（如果未达饱和），而全程上限则是 `ceiling`。跨班保持的额外收益约为 `(ceiling - k0) / 2 × 饱和前时数`。

**菲亚梅塔的关键作用**：普通宿舍恢复会重置暖机状态（干员离开工作岗位 = 爬升进度归零），但菲亚梅塔的"患难之交"心情交换让干员**不下工位直接满心情**——暖机状态被保留。这是跨班常驻的物理前提。

| 场景 | 暖机状态 | 心情恢复方式 | Shift 2 效率 |
|------|:---:|------|------|
| 隔班轮换 | 归零 | 宿舍自然恢复 | 重新爬升 |
| 菲亚梅塔满充 | **保持** | 心情交换（不下工位） | 全程上限 |
| 跨班连续（无Fia） | 归零 | 中枢扩散/玛恩纳 | 重新爬升 |



---

## 3. 通用化方案：从硬编码到 `MoodContext`

### 3.1 核心数据结构

```python
@dataclass
class MoodContext:
    """统一的心情状态上下文，替代所有分散的硬编码 bool

    所有需要心情感知的函数从本结构读取，不再接受散列的心情 bool 参数。
    不可变操作：after_shift()/after_recovery() 返回新实例，适合 K-Beam 分叉。
    """
    operator_moods: dict[str, float] = field(default_factory=dict)
    """干员名 → 当前心情值 (0.0 ~ 24.0)"""

    modifiers: MoodModifiers | None = None
    """全局心情修正器（惰性计算，首次访问时从 control_operators + buff_pool 生成）"""

    warmup_hours: dict[str, float] = field(default_factory=dict)
    """干员名 → 已连续工作小时数（离开工位归零，菲亚梅塔交换后保持）"""

    fiammetta_swap_planned: bool = False
    """求解器已规划菲亚梅塔交换（用于输出层 Fiammetta.enable）"""

    fiammetta_target: str = ""
    """菲亚梅塔交换目标干员名（用于输出层 Fiammetta.target）"""

    control_operators: list[str] = field(default_factory=list)
    """中枢干员名列表（用于计算全局减免）"""

    dorm_assignments: dict[str, str] | None = None
    """宿舍分配: {干员名 → 宿舍编号}。None 表示宿舍尚未分配"""

    shift_hours: float = 12.0
    """当前班次时长"""

    params: SolverParams | None = None
    """求解器参数（用于读取心情阈值等配置）"""

    # ── 查询方法 ──

    def mood_of(self, name: str) -> float:
        """获取干员心情值，未记录则返回满值"""
        return self.operator_moods.get(name, 24.0)

    def is_below(self, name: str, threshold: float = 12.0) -> bool:
        """心情是否低于阈值"""
        return self.mood_of(name) < threshold

    def work_burn(self, name: str, room_type: str, room_slots: int = 3) -> float:
        """计算单干员工作消耗率净值 (mood_burn)

        公式: base - recovery_modifiers
          base = 1.0 - 0.05 × (room_slots - 1)
          recovery = MoodModifiers 提供的全局恢复（玛恩纳扩散/重岳）
        """
        ...

    def room_burn(self, operators: list[Operator], room_type: str) -> float:
        """计算房间内工作干员的平均净消耗率（供 evaluate_room 使用）

        取所有干员 work_burn 的最大值（最差者决定截断时点）。
        """
        ...

    def dorm_recovery(self, name: str, dorm_mates: list[Operator] | None = None) -> float:
        """计算干员在宿舍中的恢复速率 (mood_recovery/h)

        当 dorm_assignments 已设置时从内部查询同宿舍干员；
        当 dorm_assignments=None 时使用传入的 dorm_mates（评估候选配置）。
        委托给 evaluate_dorm_recovery() 独立函数执行实际计算。

        聚合规则：
        1. 自身恢复技能 (dorm_rec_oneself / dorm_recExcludeOther)
        2. 单体恢复技能 (dorm_rec_single) — 同宿舍其他干员提供
        3. 全体恢复技能 (dorm_rec_all) — 累加
        4. MoodModifiers.dorm_bonus_for(op) — 中枢→宿舍全局加成
        5. 菲亚梅塔自律: +2.0/h 但隔离外部加成
        """

    @classmethod
    def fresh(cls, operators: list[Operator], params: SolverParams) -> "MoodContext":
        """从全量干员池构造初始心情上下文（所有干员满心情 24.0）

        operator_moods: 所有干员 mood=24.0, warmup_hours 为空。
        modifiers: None（惰性计算，首次访问时从 control_ops 生成）。
        """
```

### 3.2 门控触发点统一

将 `buff_pool.py` 中令/夕的硬编码替换为调用方从 `MoodContext` 提取 bool 后传入（避免 BuffPool→MoodContext 循环依赖，详见 §3.4）：

```python
# Before (buff_pool.py):
#   if "令" in names:
#       if ling_mood_below_12:
#           perception += 10
#       else:
#           yanhuo += 15

# After（调用方代码，如 GlobalContext.from_estimated）:
#   ling_below = mood_ctx.is_below("令", 12.0)
#   xi_below  = mood_ctx.is_below("夕", 12.0)
#   pool = compute_buff_pool(control_ops, ..., ling_mood_below_12=ling_below)
#
# buff_pool.py 内部（签名不变）:
#   if "令" in names:
#       if ling_mood_below_12:
#           perception += 10
#       else:
#           yanhuo += 15
#
#   if "夕" in names:
#       if xi_mood_below_12 is not None:   # 新增参数，向后兼容
#           if not xi_mood_below_12:
#               perception += 10
#       else:
#           perception += 10               # 未传则保持原行为（单班次兼容）
```

**传播链简化**：

```
Before: ling_mood_below_12: bool → 4个调用层逐层传递
After:  MoodContext 对象 → 所有层统一读取 mood_ctx.mood_of("令")
```

### 3.3 调用链影响范围

| 当前函数签名 | 改动 | 策略层影响 |
|-------------|------|:---:|
| `compute_buff_pool(..., ling_mood_below_12)` | **签名不变** — 调用方从 MoodContext 提取 bool 后传入 | 0 行 |
| `compute_buff_pool(...)` | 新增 `xi_mood_below_12: bool | None = None` 参数 | 0 行 |
| `GlobalContext.from_estimated(..., ling_mood_below_12)` | → 内部改为从 mood_ctx 查询 mood → 提取 bool → 传递 | 0 行 |
| `GlobalContext.from_plan(plan, ...)` | 内部从 plan + params 构造 MoodContext | 0 行 |
| `_evaluate_with_support(..., ling_mood_below_12=has_rosmontis)` | → 改为 `ling_mood_below_12=mood_ctx.is_below("令", 12.0)` | 0 行 |
| `IterativeStrategy._initial_pool()` | → 构造带初始心情的 MoodContext | ~5 行 |

### 3.4 全局心情修正器：`MoodModifiers`（类比 BuffPool 模式）

**循环依赖处理**：`compute_buff_pool` 需要令的心情状态（决定烟火/感知产出），`compute_mood_modifiers` 需要 BuffPool（重岳烟火→恢复）。多班次下这会形成循环。解耦方案：

```
compute_mood_modifiers()  ← 不依赖 MoodContext（纯从 control_ops + buff_pool 计算）
compute_buff_pool()       ← 保持当前 ling_mood_below_12: bool 参数
                             调用方（GlobalContext）从 MoodContext 计算出 bool 后传入
```

调用时序：
```python
ling_below = mood_ctx.is_below("令", 12.0)
xi_below  = mood_ctx.is_below("夕", 12.0)
buff_pool = compute_buff_pool(control_ops, ..., ling_mood_below_12=ling_below)
mood_mods = compute_mood_modifiers(control_ops, buff_pool)
# 两值可并行计算，无循环依赖
```

心情全局影响层（中枢→全设施/中枢→宿舍的恢复加成）与 BuffPool 的架构完全同构：

```
BuffPool 模式                     MoodModifiers 模式
─────────────────────────────────────────────────────
compute_buff_pool()              compute_mood_modifiers()
  扫描 Control + Dorm              扫描 Control
  → BuffPool (7 字段)              → MoodModifiers (~5 字段)
         │                                │
         ▼                                ▼
synergy_buff_pool_consumer()     MoodContext.work_burn()
  按干员名匹配                        / dorm_recovery()
  → 消耗点数→效率段                  → 读取修正器→计算速率
```

**为什么不用完整 `MoodPool` 命名**：BuffPool 的核心语义是"生产→消费"（点数被扣除），但心情恢复是"普遍作用"（所有干员同时受益）。命名为 `MoodModifiers` 强调它是**全局速率修正器**而非"可消费资源池"。

```python
@dataclass
class MoodModifiers:
    """全局心情修正器 — 一次计算，供所有工作/宿舍干员使用

    与 BuffPool 同构：全局生成 → 不可变传递 → 逐设施消费。
    差异：这里是速率修正（浮点），不是可消耗资源（整数）。
    """
    control_recovery: float = 0.0
    """中枢内部恢复速率（control_mp_cost 系列：每名中枢干员 +0.05/h）"""

    mlynar_spread: bool = False
    """玛恩纳公事公办：将 control_recovery 扩散至工作设施"""

    global_work_recovery: float = 0.0
    """工作设施全局恢复（玛恩纳直接提供 +0.1/h）"""

    yanhuo_recovery: float = 0.0
    """重岳孤光共照：+0.05 + 烟火÷20×0.05/h"""

    dorm_bonus_all: float = 0.0
    """中枢→宿舍恢复加成，适用全体宿舍干员（control_dorm_rec[000]~[002]、control_dorm_rec2[000]）"""

    dorm_bonus_elite: float = 0.0
    """中枢→宿舍恢复加成，仅适用精英干员（control_dorm_rec_tag[001] 阿斯卡纶）"""

    def dorm_bonus_for(self, op: "Operator") -> float:
        """根据干员类型返回适用的宿舍恢复加成"""
        bonus = self.dorm_bonus_all
        if op.rarity >= 5:  # 精英干员判定（近似：5★+）
            bonus = max(bonus, self.dorm_bonus_elite)
        return bonus


def compute_mood_modifiers(
    control_operators: list[Operator],
    buff_pool,
) -> MoodModifiers:
    """从控制中枢配置计算全局心情修正器

    覆盖：control_mp_cost 系列（9条）、control_mp_lonely（1条）、
          control_dorm_rec 系列（5条）、重岳孤光共照。
    未覆盖：Per-operator 恢复（菲亚梅塔/塑心/车尔尼）— 由 evaluate_dorm_recovery() 处理。
    """
    mods = MoodModifiers()
    names = {op.name for op in control_operators}

    # 中枢基础恢复（每人 +0.05/h）
    mods.control_recovery = len(control_operators) * 0.05

    # 玛恩纳公事公办 (control_mp_lonely[000])
    if any(s.buff_id == "control_mp_lonely[000]"
           for op in control_operators for s in op.skills):
        mods.mlynar_spread = True
        mods.global_work_recovery = 0.1

    # 重岳孤光共照
    if "重岳" in names and buff_pool is not None:
        mods.yanhuo_recovery = 0.05 + (buff_pool.yanhuo // 20) * 0.05

    # control_dorm_rec 系列（按目标群体分类取最高）
    for op in control_operators:
        for s in op.skills:
            if s.buff_id.startswith("control_dorm_rec_tag"):
                val = s.efficient.max_value()
                if val > mods.dorm_bonus_elite:
                    mods.dorm_bonus_elite = val
            elif s.buff_id.startswith("control_dorm_rec"):
                val = s.efficient.max_value()
                if val > mods.dorm_bonus_all:
                    mods.dorm_bonus_all = val

    return mods
```

**消费端示例**（在 MoodContext 中使用）：

```python
def work_burn(self, name: str, room_type: str, room_slots: int = 3) -> float:
    """工作干员心情消耗率"""
    base = 1.0 - 0.05 * max(0, room_slots - 1)
    recovery = 0.0
    if self.modifiers and self.modifiers.mlynar_spread:
        recovery = self.modifiers.control_recovery + self.modifiers.global_work_recovery
    if self.modifiers:
        recovery += self.modifiers.yanhuo_recovery
    return max(0.0, base - recovery)
```

**与 per-operator 恢复的关系**：

| 层级 | 处理对象 | 覆盖机制 |
|------|----------|----------|
| **MoodModifiers（全局）** | 中枢→全设施/中枢→宿舍 | 玛恩纳扩散、control_dorm_rec（按精英/全体分类）、重岳 |
| **MoodContext（per-operator）** | 宿舍→单干员/群体 | 菲亚梅塔自律、塑心单体、车尔尼群体 |

两者互补，不重叠。MoodModifiers 提供**全局基线**（通过 `MoodModifiers.dorm_bonus_for(op)` 按干员类型区分），per-operator 函数在基线上**叠加个体修正**。

### 3.5 暖机状态建模 — `t_initial` 注入

暖机机制本质上是 `ramping_efficiency(k0, r, ceiling)` 的 **`t_initial` 偏移**——已在岗 X 小时的干员，其 e(t) 从 X 小时处开始计算，而非从 0 重新爬升。

**改动范围极窄**：

```
efficiency_fn.py:ramping_efficiency()  ← 新增 t_initial: float = 0.0 参数
    ↓
synergy/mfg_linkages.py:operator_ramp_segments()  ← 透传 warmup_hours
    ↓
evaluate.py:evaluate_room()  ← 从 MoodContext 查询 per-operator warmup_hours
```

**核心改动**（[efficiency_fn.py](file:///d:/Dev/RhodeLogisticsSteward/steward_core/efficiency_fn.py#L51-L74)）：

```python
def ramping_efficiency(
    k0: float, r: float, ceiling: float,
    mood_burn: float = 0.0, T: float = 12.0,
    t_initial: float = 0.0,  # ⭐ 新增
) -> list[LinearSegment]:
    segments: list[LinearSegment] = []
    t_sat = (ceiling - k0) / r if r > 0 else float("inf")

    remaining_sat = max(0.0, t_sat - t_initial)
    if t_initial >= t_sat:
        # 已经暖机完成 → 全程上限
        segments.append(LinearSegment(a=ceiling, b=0.0, t_start=0.0, dt=T))
    elif remaining_sat < T:
        segments.append(LinearSegment(a=k0 + r * t_initial, b=r, t_start=0.0, dt=remaining_sat))
        segments.append(LinearSegment(a=ceiling, b=0.0, t_start=remaining_sat, dt=T - remaining_sat))
    else:
        segments.append(LinearSegment(a=k0 + r * t_initial, b=r, t_start=0.0, dt=T))
    ...
```

**对求解器的影响：零**。策略不感知暖机——它们只是评估 combo，而评估函数如果正确注入了 `warmup_hours`，暖机干员的组合评分自然会更高。K-Beam 的多路径选择、Baseline 的贪心排序都会自然偏好"保持暖机干员"的方案。

**MoodContext 中的暖机状态追踪**（已在 §3.1 定义 `warmup_hours` 字段）：

```python
def after_shift(self, assignments, shift_hours) -> "MoodContext":
     """应用班次后：暖机小时累加，离开工位的干员暖机归零"""
     new_warmup = {}
     working_names = set()
     for a in assignments:
         for name in a.operators:
             if a.room_type in ("Mfg", "Trade"):
                 working_names.add(name)
                 new_warmup[name] = self.warmup_hours.get(name, 0.0) + shift_hours
     # 非工作干员的暖机状态归零（在宿舍/中枢/其它设施）
     return replace(self, warmup_hours=new_warmup, ...)

 def after_recovery(self, hours, fiammetta_swaps=None) -> "MoodContext":
     """应用恢复后：菲亚梅塔交换的干员暖机保持，宿舍恢复的干员暖机归零"""
     ...
```

**改动量**：~35 行（efficiency_fn 5行 + mfg_linkages 5行 + evaluate 8行 + mood_flow 15行 + production透传 2行）。策略层改动：0 行。

### 3.6 `mood_ctx` 注入路径 — 通过 `SolverConfig` 传递

`mood_ctx` 需要从 `solve_multi_shift()` 传递到 Strategy 内部的 Phase 函数。直接修改 `Strategy.execute()` 签名会破坏策略接口。推荐通过 `SolverConfig` 传递：

```python
@dataclass
class SolverConfig:
    ...
    mood_ctx: MoodContext | None = None  # 多班次框架层注入
```

**传递链**：

```
solve_multi_shift()                   ← MoodContext 的创建者
  │  config.mood_ctx = mood_ctx
  ▼
Strategy.execute(available, config)   ← 不改签名
  │  config.mood_ctx 可读取
  ▼
Phase 函数 (exhaust_mfg / trade / ...)
  │  config.mood_ctx → 传给 evaluate_room / compute_buff_pool
  ▼
evaluate_room(..., mood_ctx=config.mood_ctx)
efficiency_fn.constant_efficiency(..., mood_burn=mood_ctx.room_burn(...))
```

**为什么通过 Config 而非 execute 参数**：
- 不改 `Strategy.execute()` 签名 → 三条策略接口层零改动
- Config 已是所有 Phase 函数的透传参数 → Phase 层改动最小
- `mood_ctx` 对于单班次是 `None`（向后兼容），对于多班次是实值

**PhaseFunction Protocol 的改动**（仅基线策略内部影响）：
- `PhaseFunction.__call__` 签名不变 — mood_ctx 通过 config 参数隐式传递
- Baseline 的 Pipeline 不需要感知 mood_ctx
- KBeam/Iterative 在构建 `SolverConfig.shift_config(mood_ctx)` 时注入

---

## 4. 目标架构

```
┌──────────────────────────────────────────────────────────────────┐
│ 约束层 (不变)                                                      │
│ constants.py  │  models.py  │  params.py (新增 mood/shift 字段)    │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│ 心情模型层 (新增)                                                  │
│                                                                   │
│ mood_flow.py                  ← 心情流转引擎                       │
│ ├── MoodContext               ← 统一心情状态容器                    │
│ ├── compute_work_burn()       ← 工作消耗率 (迁移自 mood.py)         │
│ ├── compute_dorm_recovery()   ← 宿舍恢复速率 ⭐ 新增                 │
│ ├── apply_shift()             ← 应用班次 → 心情衰减                 │
│ ├── apply_recovery()          ← 应用恢复 → 心情恢复                 │
│ └── fiammetta_swap()          ← 菲亚梅塔交换 ⭐ 新增                 │
│                                                                   │
│ buff_pool.py (改动)             ← ×1: ling_mood_below_12 → mood_ctx │
│ context.py (改动)               ← ×2: from_estimated/from_plan      │
│ evaluate.py (改动)              ← ×1: mood_burn 激活               │
│ efficiency_fn.py (改动)         ← ×1: mood_burn 默认值保留, 改为    │
│                                      evaluate_room 内部计算后传入   │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│ 求解器层 (改动 ~90 行)                                             │
│                                                                   │
│ fill_dorm.py (最大改动)          ← 从"填满20坑"→"恢复调度"          │
│ exhaust_mfg.py (透传)           ← mood_ctx 透传到 evaluate_room    │
│ exhaust_trade.py (透传)         ← 同上                             │
│ fill_control.py (零改动)        ← 中枢无心情消耗                    │
│ fill_remaining.py (零改动)      ← Power/Reception/Office 不耗心情  │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│ 多班次框架 (新增 ~50 行)                                          │
│                                                                   │
│ solver/__init__.py: solve_multi_shift()                           │
│   for shift_idx in range(shift_count):                            │
│       1. 按 MoodContext 过滤可用干员                                │
│       2. 调用 Strategy.execute(available_operators, ...)           │
│       3. 收集 ShiftPlan → apply_shift(mood_ctx)                   │
│       4. apply_recovery(mood_ctx, interval) → 下一轮               │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│ 策略层 (改动 ~25 行)                                               │
│                                                                   │
│ BaselineStrategy:  ~5 行 (Pipeline 透传 config.mood_ctx)           │
│ KBeamStrategy:    ~10 行 (评估链从 config 读取 mood_ctx)            │
│ IterativeStrategy: ~10 行 (_initial_pool 用真实心情)                │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. 实施步骤

### Step 1: 宿舍恢复速率评估 `dorm_recovery.py`（纯新增，~120行）

优先级：**高** — 多班次心情流转的必要前提。

```python
def evaluate_dorm_recovery(
    dorm_ops: list[Operator],
    target_op: Operator,
    mood_ctx: MoodContext,
    dorm_level: int = 5,
) -> float:
    """评估目标干员在给定宿舍中的心情恢复速率（/h）

    聚合规则：
    1. 自身恢复技能 (dorm_rec_oneself / dorm_recExcludeOther)
    2. 单体恢复技能 (dorm_rec_single) — 同宿舍其他干员提供
    3. 全体恢复技能 (dorm_rec_all) — 累加
    4. 中枢全局宿舍加成 (control_dorm_rec) — 通过 mood_ctx 查询
    5. 菲亚梅塔自律: +2.0/h 但隔离外部加成（特殊处理）

    注意：同种效果取最高是 MAA infrast.json 的 efficient 字段语义，
    宿舍恢复 buff 的 efficient 值聚合规则需与此一致。

    非效率 buff（如木天蓼/情报储备/乌萨斯特饮等仅影响心情的道具类技能）
    在实施时查阅 PRTS Wiki 确认数值后按各自语义纳入。
    """
```

**83 条 DORM buff 分类扫描**：

| buff 类别 | buff 数 | 聚合规则 | 示例 |
|-----------|:---:|----------|------|
| `dorm_rec_oneself` 自身恢复 | 8 | 取 max (部分可选) | 斯卡蒂悲歌 +1.0/h |
| `dorm_recExcludeOther` 自律 | 1 | 固定 +2.0，隔离外部 | 菲亚梅塔 |
| `dorm_rec_single` 单体恢复 | 6 | 取 max (同类中) | 安赛尔医疗服务 +0.65/h |
| `dorm_rec_all` 全体恢复 | ~15 | 累加 | 车尔尼琴键漫步 +0.25/h |
| `control_dorm_rec` 中枢全局 | 5 | 取 max (同类中) | 焰影苇草领袖 +0.05/h |
| 人间烟火联动 | — | +0.05/20烟火 | 从 buff_pool 查询 |
| 其他(无效率值) | ~48 | 不参与计算 | 线索偏置/特殊效果 |

### Step 2: `MoodContext` 统一容器（新增 `mood_flow.py`，~150行）

优先级：**高** — 替代所有散落的心情 bool。

```python
@dataclass
class MoodContext:
    operator_moods: dict[str, float]          # 初始心情→运行中追踪
    modifiers: MoodModifiers | None = None     # 全局心情修正器（惰性计算）
    warmup_hours: dict[str, float]             # 已连续工作小时数（跨班常驻/菲亚梅塔保序）
    fiammetta_swap_planned: bool = False       # 是否规划了菲亚梅塔交换
    fiammetta_target: str = ""                 # 交换目标干员名
    control_operators: list[str]               # 中枢干员列表
    dorm_assignments: dict[str, str] | None     # 干员名→宿舍号
    shift_hours: float = 12.0
    params: SolverParams | None = None

    # 查询
    def mood_of(self, name: str) -> float: ...
    def is_below(self, name: str, threshold: float) -> bool: ...

    # 消耗/恢复
    def work_burn(self, name: str, room_type: str, room_slots: int = 3) -> float: ...
    def room_burn(self, operators, room_type: str) -> float: ...
    def dorm_recovery(self, name: str) -> float: ...

    # 状态转换（不可变，返回新实例）
    def after_shift(self, assignments: list[RoomAssignment]) -> "MoodContext": ...
    def after_recovery(self, hours: float) -> "MoodContext": ...
```

关键设计决策：**不可变操作** — `after_shift()` 和 `after_recovery()` 返回新 `MoodContext` 而非原地修改，使 K-Beam 能轻松克隆分叉。

### Step 3: 反硬编码 — 消除 `ling_mood_below_12`（改动 ~30行）

| 文件 | 改动 |
|------|------|
| `synergy/buff_pool.py` | `compute_buff_pool(ling_mood_below_12)` → `compute_buff_pool(mood_ctx)` |
| `solver/context.py` | `from_estimated()` / `from_plan()` → 构造 MoodContext 代替散 bool |
| `solver/support.py` | `_evaluate_with_support()` → 删除 `ling_mood_below_12` 参数 |
| `solver/strategies/iterative.py` | `_initial_pool()` → 构造初始心情 MoodContext |

**同时修正夕的门控缺失**：

```python
# Before (buff_pool.py): 夕无条件 +10 感知
#   if "夕" in names:
#       perception += 10

# After (buff_pool.py，通过新增 xi_mood_below_12 参数):
#   if "夕" in names:
#       if xi_mood_below_12 is not None:
#           if not xi_mood_below_12:
#               perception += 10
#       else:
#           perception += 10  # 向后兼容单班次
```

调用方（GlobalContext）负责提取：
```python
# context.py 内:
xi_below = mood_ctx.is_below("夕", 12.0) if mood_ctx else None
pool = compute_buff_pool(control_ops, ..., xi_mood_below_12=xi_below)
```

### Step 4: 激活 `mood_burn` 截断 + 铅踝梯级衰减（改动 ~30行）

`efficiency_fn.py` 的 `mood_burn` 参数已就绪，只需在 `evaluate_room()` 中从 `MoodContext` 计算后传入：

```python
# evaluate.py evaluate_room() 新增:
if mood_ctx is not None:
    mood_burn = mood_ctx.room_burn(operators, room_type)
    # 铅踝梯级衰减：e(t) = 30 - 5×⌊(24-mood(t))/4⌋
    qiangan_step = mood_ctx.qiangan_decay_basis(operators, room_type)
else:
    mood_burn = 0.0
    qiangan_step = None
```

**铅踝"模糊视线"梯级衰减实现**（[efficiency_fn.py](file:///d:/Dev/RhodeLogisticsSteward/steward_core/efficiency_fn.py) 新增）：

```python
def stepped_efficiency(
    base: float, step_size: float = 5.0, step_interval: float = 4.0,
    mood_burn: float = 0.0, T: float = 12.0,
) -> list[LinearSegment]:
    """梯级衰减效率：e(t) = base - step_size × ⌊(24 - mood(t)) / step_interval⌋

    mood(t) = mood_initial - burn × t, 每 step_interval 点心情落差触发一级衰减。
    将连续时间轴拆为 mood 阶梯段，每段内效率为常数。
    """
```

对 12h 单班次：`mood_burn` 不会触发截断，梯级衰减仅触发 1 次 (-5%)，行为退化为略低于 +30% 的常数。  
对多班次：shift2 中干员心情残留可能触发多级衰减（至多 24/4 = 6 级）。

### Step 5: `fill_dorm` 升级为恢复调度（改动 ~80行）

优先级：**高** — 多班次求解的必要前提。`solve_multi_shift()` 依赖本步骤提供恢复后的干员心情状态。

当前逻辑：
```python
# fill_dorm.py: 优先 B 层生成者 → 任意填充至 20 人
```

升级后逻辑：
```python
def fill_dorm_with_scheduling(
    working_operators: list[str],    # 需要恢复的工作干员
    available_dorm_ops: list[Operator],  # 可用宿舍干员池
    mood_ctx: MoodContext,
    recovery_target_hours: float,    # 目标恢复时长
) -> list[RoomAssignment]:
    """调度宿舍以最小化整体轮换空窗期

    1. 对每个工作干员，计算在不同宿舍配置下的恢复时间
    2. 菲亚梅塔分配决策：分配给最需要恢复的核心干员
    3. 输出每间宿舍的最佳人员组合
    """
```

### Step 6: 多班次求解器 `solve_multi_shift()`（新增 ~50行）

```python
def solve_multi_shift(
    operators: list[Operator],
    config: SolverConfig,
) -> SolveResult:
    """多班次编排器 — 对任意 Strategy 透明

    Args:
        config.params.shift_count: 班次数 (默认 2)
        config.params.interval_hours: 班间间隔 (默认 8h)
    """
    strategy = config.strategy or BaselineStrategy()
    op_lookup = {op.name: op for op in operators}
    mood_ctx = MoodContext.fresh(operators, config.params)

    all_plans = []
    for shift_idx in range(config.params.shift_count):
        # 1. 按心情过滤可用干员
        available = [op for op in operators
                     if mood_ctx.mood_of(op.name) >= config.params.mood_work_threshold]

        # 2. 求解（策略只排 Mfg/Trade/Power/Control，宿舍由框架层分配）
        result = strategy.execute(available, config, op_lookup)
        plan = result.plans[0]

        # 3. 框架层覆盖宿舍分配 — 基于工作干员的心情状态做恢复调度
        plan = reallocate_dorms_after_solve(plan, operators, mood_ctx, config)

        all_plans.append(plan)

        # 4. 应用工作消耗
        mood_ctx = mood_ctx.after_shift(plan.assignments, config.params.shift_hours)

        # 5. 班间恢复（非最后班次）
        if shift_idx < config.params.shift_count - 1:
            mood_ctx = mood_ctx.after_recovery(config.params.interval_hours)

    return SolveResult(plans=all_plans, ...)
```

`reallocate_dorms_after_solve()` 的责任：
1. 从 plan.assignments 识别工作干员（Mfg/Trade/Power/Reception/Office）
2. 对每个需要恢复的工作干员，计算在可用宿舍配置下的恢复时间
3. 菲亚梅塔分配决策：选择最需要恢复的核心干员作为交换目标
4. 覆盖 plan 中的 Dormitory assignment，输出恢复调度后的宿舍方案

### Step 7: 菲亚梅塔输出协议激活（改动 ~5行）

当前 `output.py` 硬编码 `enable: false`。多班次下从 `MoodContext` 读取真实的 Fiammetta 配置：

```python
"Fiammetta": {
    "enable": mood_ctx.fiammetta_swap_planned,  # §3.1 中定义
    "target": mood_ctx.fiammetta_target or "",
    "order": "pre",
}
```

`fiammetta_swap_planned` 和 `fiammetta_target` 由 `reallocate_dorms_after_solve()` 在宿舍调度阶段设置。

---

## 6. 新增参数（SolverParams）

```python
# === 多班次 ===
shift_count: int = 1
"""班次数（1=单班次，2=双班次）"""

interval_hours: float = 8.0
"""班间间隔（小时），用于恢复模拟"""

fiammetta_enabled: bool = False
"""是否启用菲亚梅塔心情交换"""

# === 心情阈值 ===
mood_work_threshold: float = 0.0
"""可参与工作的最低心情值（低于此值不可用）"""

mood_blue_face: float = 12.0
"""蓝脸阈值（效率下降的边界，不影响 e(t) 但标记状态）"""

mood_red_face: float = 0.0
"""红脸阈值（效率归零）"""
```

参数均保留默认值以保证向后兼容：`shift_count=1` → 行为完全不变。

> **SolverConfig 配套变更**（非 SolverParams）：
> ```python
> @dataclass
> class SolverConfig:
>     ...
>     mood_ctx: MoodContext | None = None  # 多班次框架层注入，单班次为 None
> ```

---

## 7. 文件清单

| 操作 | 文件 | 行数 |
|------|------|:---:|
| 新增 | `steward_core/mood_flow.py` | ~300 |
| 新增 | `solver/__init__.py` `solve_multi_shift()` | ~50 |
| 删除 | `steward_core/synergy/mood.py` — `compute_global_burn` 迁移到 `mood_flow.py` | — |
| 改动 | `steward_core/synergy/__init__.py` — 移除 `compute_global_burn` 重导出 | ~5 |
| 改动 | `steward_core/synergy/buff_pool.py` — 新增 `xi_mood_below_12` 参数 | ~15 |
| 改动 | `steward_core/evaluate.py` — `evaluate_room()` 接收 `mood_ctx` 参数 | ~15 |
| 改动 | `steward_core/efficiency_fn.py` — `t_initial` + `stepped_efficiency` | ~20 |
| 改动 | `steward_core/synergy/mfg_linkages.py` — `operator_ramp_segments` 收 `t_initial` | ~5 |
| 改动 | `steward_core/mood.py` — MoodReport/RoomMood 保留，`calculate()` 内部从 mood_flow 导 `compute_global_burn` | ~10 |
| 改动 | `solver/context.py` — `from_estimated/from_plan` 新增 mood_ctx + 提取 bool 传给 buff_pool | ~20 |
| 改动 | `solver/support.py` — `_evaluate_with_support` 接收 mood_ctx | ~10 |
| 改动 | `solver/config.py` — `SolverConfig` 新增 `mood_ctx` 字段 | ~5 |
| 改动 | `solver/params.py` — 新增多班次/心情阈值参数 | ~15 |
| 重构 | `solver/fill_dorm.py` — 填满→恢复调度 | ~80 |
| 改动 | `solver/exhaust_mfg.py` — 透传 config.mood_ctx | ~5 |
| 改动 | `solver/exhaust_trade.py` — 透传 config.mood_ctx | ~5 |
| 改动 | `solver/greed.py` — `_evaluate_trade_combo` 接收 mood_ctx | ~10 |
| 改动 | `solver/refine.py` — `evaluate_full_plan`/`local_search_refine` 从 config 读取 mood_ctx | ~15 |
| 改动 | `solver/global_state.py` — 透传（如需要） | ~5 |
| 改动 | `steward_core/production.py` — `calculate()` 透传 mood_ctx | ~5 |
| 改动 | `solver/strategies/baseline.py` — Pipeline 透传（mood_ctx 在 config 内，协议签名不变） | ~5 |
| 改动 | `solver/strategies/kbeam.py` — `_evaluate_and_allocate_k` 读取 config.mood_ctx | ~10 |
| 改动 | `solver/strategies/iterative.py` — `_initial_pool` 使用真实心情 | ~10 |
| 改动 | `steward_core/output.py` — Fiammetta 字段激活 | ~5 |
| 改动 | `steward_core/models.py` — 新增 `SteppedSegment` 或复用 `LinearSegment` | ~5 |
| 新增 | `tests/test_mood_flow.py` — MoodContext + MoodModifiers 单元测试 | ~150 |
| 新增 | `tests/test_dorm_recovery.py` — 宿舍恢复速率单元测试 | ~80 |
| 新增 | `tests/mood_fixtures.py` — 测试 fixture（可选） | ~40 |
| 改动 | `tests/test_efficiency_fn.py` — t_initial + stepped_efficiency 增量 | ~40 |
| 改动 | `tests/test_end_to_end.py` — 多班次端到端断言 | ~30 |
| 改动 | `tests/test_output.py` — Fiammetta 多班次启用断言 | ~10 |
| **合计** | | **~990** |

策略层总计改动：~25 行（Baseline 5 + KBeam 10 + Iterative 10）。mood_ctx 通过 `SolverConfig` 注入避免了修改 `Strategy.execute()` 签名和 `PhaseFunction` 协议。

### 双 mood.py 处置

| 文件 | 当前内容 | 处置 |
|------|----------|------|
| `steward_core/synergy/mood.py` | `compute_global_burn()` 中枢心情恢复计算 | 迁移到 `mood_flow.py` 的 `MoodModifiers` 中，原文件**删除**，`synergy/__init__.py` 移除重导出 |
| `steward_core/mood.py` | `MoodReport`/`RoomMood`/`calculate()` 单班次分析报告 | **保留**，`calculate()` 内部改为从 `mood_flow` 导入 `compute_global_burn`（薄包装）。`MoodReport` 供 `run_solver.py` 心情分析输出使用，不参与多班次求解 |

---

## 8. 验证路径

| 步骤 | 验证方法 |
|------|----------|
| Step 2 (MoodContext) | 单元测试：`MoodContext.fresh()` 构造、`work_burn()` 计算与 PRTS Wiki 公式一致、`is_below("令", 12)` 门控正确 |
| Step 1+3 (dorm_recovery + 反硬编码) | 单班次 12h 回归测试：`python -m pytest tests/ -v` 全绿，产出不变 |
| Step 4 (mood_burn 激活) | 人工构造 24h 单班次（`shift_hours=24`）：验证 `t_red` 截断在 ≥16h 触发，铅踝衰减生效 |
| Step 5 (fill_dorm 重构) | 人工构造宿舍配置：验证恢复速率计算与 PRTS Wiki 公式一致 |
| Step 6 (solve_multi_shift) | 双班次 2×12h+8h：验证 shift2 候选池正确过滤心情不足干员、K-Beam 多路径在双班次下不爆炸 |
| Step 7 (输出) | 检查输出 JSON：Fiammetta 字段在多班次下 `enable=true, target` 非空 |
| 端到端 | `python -m pytest tests/ -v` 全绿 + 手动对比 MAA 内置 243×4 模板方案 |

**实施依赖顺序**：Step 2（MoodContext）→ Step 1（dorm_recovery）→ Step 3（反硬编码）→ Step 4（mood_burn + 铅踝）→ Step 5（fill_dorm 重构）→ Step 6（solve_multi_shift）→ Step 7（输出激活）。Step 1 和 Step 3 可并行，Step 4 和 Step 5 可并行，其余严格顺序。

---

## 9. 风险与注意事项

1. **夕的心情门控修正可能改变单班次结果** — 当前 12h 单班次下夕心情始终 >12，修正后行为不变。但需验证。
2. **菲亚梅塔建模不等于直接+2心情/h** — "自律"隔离外部加成，"患难之交"需要满心情才能触发，建模时需精确复现时序。
3. **K-Beam 在双班次下路径爆炸** — K=3 的一阶段已有 K 条 Manufacturing 路径，双班次若每班独立 K-Beam 则组合数为 K²。建议 first K=5, second K=2 或由 solve_multi_shift 统一控制。
4. **宿舍恢复速率验证用数据** — PRTS Wiki 公式为本项目心情模型的权威来源，恢复速率需与实际游戏行为一致。
5. **测试套件冲击** — `synergy/mood.py` 删除后，引用了 `compute_global_burn` 的测试需更新导入路径；`fill_dorm.py` 重构后宿舍分配测试需重写；端到端测试（`test_end_to_end.py`）需要考虑多班次模式下的新断言。建议在每个 Step 完成后立即运行 `python -m pytest tests/ -v` 确认增量不破坏。
6. **木天蓼/情报储备/乌萨斯特饮** — 这些 buff 仅影响心情恢复速率（不参与 e(t) 计算），需在 Step 1 实施时查阅 PRTS Wiki 确认具体数值后纳入 `evaluate_dorm_recovery()`。

---

## 10. 测试计划与验收标准

### 10.1 新增单元测试

#### `tests/test_mood_flow.py`（新增，~150行）

| 测试用例 | 覆盖内容 | 验收标准 |
|----------|----------|----------|
| `test_fresh_all_full` | `MoodContext.fresh()` 构造 | 所有 415 干员 `mood_of(name) == 24.0` |
| `test_work_burn_3slot` | 3人工位（Mfg/Trade）消耗率计算 | `base - 0.05*2 - modifiers` 与 PRTS Wiki 一致 |
| `test_work_burn_2slot` | 2人工位（Reception）消耗率 | 基础 1.0 - 0.05×1 |
| `test_work_burn_1slot` | 1人工位（Power/Office）消耗率 | 基础 1.0（无减免） |
| `test_mlynar_spread` | 玛恩纳扩散：`mlynar_spread=True` 时 work_burn 含 control_recovery | 中枢 5人=0.25+玛恩纳+0.1=0.35 恢复 |
| `test_yanhuo_recovery` | 重岳孤光共照：烟火 40→恢复 +0.1 | `yanhuo_recovery == 0.05 + 40//20*0.05` |
| `test_ling_gate_mood_above_12` | 令 mood>12→烟火 | `is_below("令", 12.0) == False` |
| `test_ling_gate_mood_below_12` | 令 mood≤12→感知 | `is_below("令", 12.0) == True` |
| `test_xi_gate` | 夕门控：mood>12→+10 感知 | `xi_mood_below_12` 参数传递正确 |
| `test_after_shift_burn` | 单班次后心情衰减 | mood(0)=24, burn=0.75, 12h → mood(12)=15.0 |
| `test_after_shift_no_burn_control` | 中枢干员不消耗心情 | 中枢干员 shift 后 mood 仍为 24 |
| `test_after_recovery_full` | 恢复至满心情上限 | 心情+恢复速率×hours，上限 24 |
| `test_warmup_accumulate` | 暖机小时累加 | shift1 12h → warmup=12, shift2 12h → warmup=24 |
| `test_warmup_reset_on_leave` | 离开工位暖机归零 | 进入宿舍/中枢后 warmup=0 |
| `test_fiammetta_preserve_warmup` | 菲亚梅塔交换后暖机保持 | Fia 交换 → warmup 不归零 |

#### `tests/test_dorm_recovery.py`（新增，~80行）

| 测试用例 | 覆盖内容 | 验收标准 |
|----------|----------|----------|
| `test_self_recovery` | 自身恢复 (dorm_rec_oneself) | 取 max，如斯卡蒂 +1.0/h |
| `test_fiammetta_self` | 菲亚梅塔自律 | +2.0/h，且外部加成隔离（dorm_bonus 不生效） |
| `test_single_recovery_max` | 单体恢复 (dorm_rec_single) | 同类取 max |
| `test_all_recovery_sum` | 全体恢复 (dorm_rec_all) | 累加（车尔尼+杜林族） |
| `test_dorm_bonus_all` | control_dorm_rec 全体 | 中枢→宿舍 +0.05/h |
| `test_dorm_bonus_elite` | control_dorm_rec_tag 精英 | 仅 5★+ 干员可获得 |
| `test_yanhuo_bonus` | 人间烟火联动 | +0.05/20 烟火 |
| `test_recovery_capped_24` | 恢复不会超过 24 | 即使恢复速率极高 |

#### `tests/test_efficiency_fn.py`（增量，~40行）

| 测试用例 | 覆盖内容 | 验收标准 |
|----------|----------|----------|
| `test_ramp_t_initial_zero` | t_initial=0 等价于原行为 | 积分值与不加 t_initial 一致 |
| `test_ramp_t_initial_half` | 从半饱和位置开始 | e(0) = k0 + r×5, 5h后达 ceiling |
| `test_ramp_t_initial_ceiling` | 已暖机完成 | 全程常数 ceiling |
| `test_stepped_efficiency_1step` | 梯级衰减单级 | mood_burn=0.65, 12h→1级衰减 (-5%) |
| `test_stepped_efficiency_3step` | 梯级衰减多级 | mood_burn=2.0, 12h→3级衰减 (-15%) |

---

### 10.2 现有测试改造

| 测试文件 | 改动原因 | 行数 |
|----------|----------|:---:|
| `tests/test_synergy_mood.py` | 如果存在：`compute_global_burn` 迁移至 `mood_flow`，需更新 import 路径 | ~5 |
| `tests/test_solver.py` | 单班次回归：所有排班产出不变 | 不变 |
| `tests/test_end_to_end.py` | 新增双班次模式断言：`SolveResult.plans` length=2，Fiammetta 字段启用 | ~30 |
| `tests/test_production.py` | `calculate()` 新增 `mood_ctx` 可选参数，单班次下传 None→行为不变 | ~5 |
| `tests/test_output.py` | 已有 `test_Fiammetta_单班次不启用`，新增 `test_Fiammetta_多班次启用` | ~10 |
| `tests/test_refine.py` | `evaluate_full_plan()` 从 config 读取 mood_ctx，单班次为 None→不变 | ~5 |

---

### 10.3 按 Step 的验收标准

| Step | 验收门禁 | 通过条件 |
|------|----------|----------|
| Step 1 (dorm_recovery) | `python -m pytest tests/test_dorm_recovery.py -v` 全绿 + 恢复速率与 PRTS Wiki 对照 | 8 个用例通过，手动验证塑心+菲亚梅塔组合 |
| Step 2 (MoodContext) | `python -m pytest tests/test_mood_flow.py -v` 全绿 | 15 个用例通过 |
| Step 3 (反硬编码) | `python -m pytest tests/ -v` 全绿 | 单班次 12h 产出与前版本一致（差异 < 0.1%） |
| Step 4 (mood_burn + 铅踝) | `python -m pytest tests/test_efficiency_fn.py -v` 全绿 | 10 个用例通过，24h 单班次 t_red 触发 |
| Step 5 (fill_dorm 重构) | `python -m pytest tests/ -v` 全绿 | 宿舍生成 4×5=20 人，恢复速率可计算 |
| Step 6 (solve_multi_shift) | `python -m pytest tests/test_end_to_end.py -v` 全绿 | 双班次 plans length=2，shift2 候选池不含心情不足干员 |
| Step 7 (Fiammetta 输出) | `python -m pytest tests/test_output.py -v` 全绿 | 双班次下 `Fiammetta.enable==True, target` 非空 |
| 端到端 | `python -m pytest tests/ -v` 全部通过 | 回归无破坏 + 多班次产出 > 单班次单次产出（因为利用了双倍工位时间） |

---

### 10.4 手工验收清单

| # | 验收项 | 方法 | 通过标准 |
|---|--------|------|----------|
| 1 | 单班次产出不变 | 对比 plan v0.5.1 基线方案的 `effective_lmd_per_day` | 差异 < 1 LMD/天 |
| 2 | 中枢干员不消耗心情 | 检查 shift1 后 Control 干员 mood | 全部 = 24.0 |
| 3 | 菲亚梅塔自律隔离外部加成 | 构造宿舍：菲亚梅塔+control_dorm_rec 持有者在中枢 | 菲亚梅塔恢复 = 2.0（不含 dorm_bonus） |
| 4 | 菲亚梅塔交换有效性 | 双班次：shift1 后工作干员 mood↓，Fia 交换→目标满心情重回 shift2 | 目标干员 shift2 开始时 mood=24 |
| 5 | 暖机跨班价值 | K-Beam 双班次：保持暖机干员 vs 替换的产出差 | 保持暖机产出 > 替换（差值 ≥ (ceiling-k0)/2） |
| 6 | 令的门控切换 | 双班次 shift2：令 mood 降至 ≤12 → 产出从烟火变为感知信息 | BuffPool 中 yanhuo 减少 15，perception 增加 10 |
| 7 | 夕的门控切断 | 双班次 shift2：夕 mood 降至 ≤12 → 不再产出感知信息 | BuffPool 中 perception 减少 10 |
| 8 | 玛恩纳扩散作用 | 构造中枢含玛恩纳 → 工作干员 work_burn 含扩散恢复 | work_burn 含 max(0, 1.0-0.05×(n-1) - 0.35) |
| 9 | 输出 JSON 合规 | 双班次输出 JSON 对照 MAA 基建排班协议 v5.x | 顶层字段完整，plan 数组 length=shift_count |
| 10 | 对比公孙长乐参考方案 | 双班次 2×12h 输出 vs MAA 内置 `243_layout_3_times_a_day.json` | 核心干员分配方向一致（不要求数值完全相同） |

---

### 10.5 测试辅助工具

需要新增的测试 fixture（建议放入 `tests/conftest.py` 或 `tests/mood_fixtures.py`）：

```python
@pytest.fixture
def fresh_mood_ctx(all_operators):
    """全满心情的 MoodContext"""
    return MoodContext.fresh(all_operators, SolverParams.baseline())

@pytest.fixture
def depleted_mood_ctx(all_operators):
    """shift1 12h 后的心情上下文（模拟工作消耗）"""
    ctx = MoodContext.fresh(all_operators, SolverParams(shift_hours=12))
    # 模拟 2 间 Mfg + 2 间 Trade 各 3 人工位消耗
    ...

@pytest.fixture
def mlynar_control_ops():
    """含玛恩纳的中枢干员列表"""
    ...

@pytest.fixture
def dorm_with_fiammetta():
    """含菲亚梅塔的宿舍干员列表"""
    ...
```

---

## 参考

- 策略概要: [`strategy-brief.md`](./strategy-brief.md) — 单班次 12h 约束
- 效率函数建模: [`efficiency-function-design.md`](./efficiency-function-design.md) — e(t) 心情截断机制
- 约束体系基线: [`constraints-and-data-baseline.md`](./constraints-and-data-baseline.md) — 宿舍恢复链 (§2.3.3)
- 需求收件箱: [`inbox.md`](./inbox.md) — 多班次相关需求条目
- MAA 基建排班协议: https://docs.maa.plus/zh-cn/protocol/base-scheduling-schema.html — Fiammetta 协议字段

## 附录：Inbox 覆盖清单

以下 inbox 条目被本计划完全覆盖或部分覆盖：

| Inbox 条目 | 覆盖章节 | 覆盖程度 |
|------------|----------|:---:|
| 多班次心情流转模型 | §1-9 全量 | ✅ 完全 |
| 宿舍 Phase 从填充升级为恢复调度 | §5 Step 5 fill_dorm 重构 | ✅ 完全 |
| MultiShiftPlan 数据模型 | §3.1 MoodContext + §5 Step 6 solve_multi_shift() | ✅ 完全（用 MoodContext 替代独立 MultiShiftPlan） |
| Phase 多班次轮换感知 | §5 Step 6 solve_multi_shift() + §3.4 MoodModifiers | ✅ 完全 |
| 木天蓼/情报储备/乌萨斯特饮 | §5 Step 1 宿舍恢复评估 | ✅ 完全（dorm_recovery.py 聚合所有 DORM buff） |
| 热情值 buff 池建模 | §7 文件清单（buff_pool.py 改动） | 🟡 依赖同期（ardor 字段需额外新增） |

**不覆盖的 inbox 条目**（独立路由，与本计划无关）：

| Inbox 条目 | 路由 |
|------------|------|
| 粗评分预筛选优化 | `exhaust_mfg.py` + `params.py`（独立） |
| 基建布局可配置化 | `models.py` + `params.py`（独立） |
| B7 跨房间配对被评估遗漏 | k-beam / refine.py（独立） |
| 瓶颈枚举 | `solver/strategies/`（独立） |
| 局部搜索策略化 | `solver/refine.py`（独立） |
