# 效率函数统一建模

> **版本**: 2026-05-28 · 已实现 — 通过 `efficiency_fn.py` 的 `LinearSegment` + `constant_efficiency`/`ramping_efficiency` 构造器 + `evaluate.py` 的 `evaluate_room()` 统一积分
>
> **简化**：单班次 12h 内心情截断不触发（`t_red ≥ 16h`），e(t) 在单窗口内退化为全常数段。跨窗口场景下 `mood_burn` 参与工作时长池计算（见 slot-processing-model.md §3.1 / §9.5），但不在 e(t) 中引入截断。

## 1. 动机

### 1.1 为什么需要 e(t)

`buffs_infrastructure.json` 中存在 **7 条随时间变化的技能**，无法用一个标量 `efficiency` 字段描述：

| buff_id | 形态 | 描述 |
|---------|------|------|
| `power_rec_spd&addition[000]`~`[001]` | 首小时 10~15%, +1%/h, 上限 15~20% | 发电站无人机充能爬升（2条） |
| `manu_prod_spd_addition[030]`~`[041]` | 首小时 15~20%, +1~2%/h, 上限 25% | 制造站生产力爬升（4条） |
| `meet_spd_hast[000]` | 首小时 20%, +2%/h, 上限 30% | 会客室线索搜集爬升（1条） |

此外，~150 条体系联动 buff（"与推进之王同贸易站时+35%"）的 e(t) 不能由单个干员独立求出，需以全房间干员列表为输入。

### 1.2 设计目标

将 Mfg / Trade / Power 的效率计算统一归约为同一个数学对象：效率对时间的函数 `e(t)`，产出 = `∫ e(t) · base_rate dt`。

## 2. 数学模型

### 2.1 核心定义

设排班时长 `[0, T]`，房间有 `n` 名干员，其技能效率函数为 `e₁(t), e₂(t), ..., eₙ(t)`（百分值），则房间总生产力：

```
P(t) = 1 + 0.01·n + Σ eᵢ(t) / 100
```

房间在 `[0, T]` 内的总产出：

```
产出 = base_rate × ∫₀ᵀ P(t) dt
```

### 2.2 分类学

所有技能属于以下四种基本形态之一：

| 形态 | e(t) 表达式 | 数量 | 示例 |
|------|------------|:---:|------|
| 常数 | `k` | ~555 | `manu_prod_spd[000]` efficiency=15 |
| 线性爬升 | `min(k₀ + r·t, ceiling)` | 7 | "首小时+15%, 此后+1%/h, 上限+20%" |
| 心情门控 | `k₁` 或 `k₂`（mood 阈值切换） | ~15 | mood<12→人间烟火+15 |
| 体系联动 | 跨干员聚合后输出常数段 | ~150 | "与推进之王同贸易站时+35%" |

体系联动与前三种有本质区别：条件不是干员自身状态，而是同房间其他干员的存在性。此类技能归入联动体系（`synergy/`），由 `evaluate_room()` 以全房间干员列表为输入计算。

### 2.3 心情与 12h 班次

心情-效率的边界是 `mood = 0` 时注意力涣散（效率归零）。`mood(t) = 24 - burn·t`，截断点 `t_red = 24 / burn`。

12h 单班次下，最差单人工位 `burn = 1.5/h` → `t_red = 16h > 12h`。心情截断不触发，e(t) 全程为常数段。

> 多班次轮换策略下每班 ≤ 12h，且班间干员不重复使用（`mood(0) = 24`），因此 MVP 阶段 `mood_burn = 0.0`，无需 t_red 截断逻辑。

### 2.4 梯级衰减

`manu_prod_spd_reduce[000]`（铅踝"模糊视线"）是唯一直接产生 mood→e(t) 连续衰减的技能：`e(t) = 30 - 5 × ⌊(24 - mood(t)) / 4⌋`。12h 班次下 mood 从 24 降至 ~16.2（burn=0.65），仅触发 1 次 -5% 衰减。`to_segments()` 在 burn>0 时自动切出中间截断段。

## 3. 实现：分段线性积分

### 3.1 核心数据结构

```python
@dataclass
class LinearSegment:
    """e(t) 的一个线性片段: e(t) = a + b·t, t ∈ [t_start, t_start + dt]"""
    a: float       # 截距（百分值）
    b: float       # 斜率（百分值/h）
    t_start: float # 起始时间 (h)
    dt: float      # 持续时间 (h)

    def integrate(self) -> float:
        """∫(a + b·t) dt over [t_start, t_start+dt]"""
        t0, t1 = self.t_start, self.t_start + self.dt
        return self.a * self.dt + self.b * (t1**2 - t0**2) / 2.0
```

四种形态在分段后都是 `a + b·t` 的线性函数，闭式积分 `a·Δt + b·(t₁² - t₀²)/2`。**无需数值积分库**。

### 3.2 主要构造器

| 构造器 | 输入 | 用途 |
|--------|------|------|
| `constant_efficiency(value, mood_burn, T)` | 技能值 + 心情消耗率 | 常数技能。mood_burn>0 时在 t_red 截断为两段 |
| `ramping_efficiency(initial, gain, ceiling, mood_burn, T)` | 起始/增量/上限 | 7 条时变技能，饱和后由 mood_burn 附加截断段 |
| `evaluate_room(operators, ...)` | 全房间干员列表 + 全局上下文 | 联动体系聚合 + 个体效率求和 → 积分值 |

### 3.3 支配偏序排序

贪心阶段使用 e(t) 支配偏序而非标量排序：

```
A 支配 B  ⇔  e_A(t) ≥ e_B(t)  for all t ∈ [0, T]
```

对常数型技能退化为 O(1) 二维比较（效率值 + 有效时长）。互不支配时退化为全积分比较。

算法为多趟 Kahn 拓扑排序，仅严格支配（A 支配 B 且 B 不支配 A）建边，等价干员退化为互不支配走全积分比较。

## 4. 覆盖度验证

| 机制实例 | 能否表达为 e(t)？ | 方式 |
|----------|:---:|------|
| 制造站简单加成 (efficiency=15) | ✅ | `constant_efficiency(15, 0, T)` |
| 贸易站简单加成 (efficiency=30) | ✅ | `constant_efficiency(30, 0, T)` |
| 发电站无人机 (efficiency=20) | ✅ | `constant_efficiency(20, 0, T)` — 发电站不耗心情 |
| 时变制造效率 | ✅ | `ramping_efficiency(15, 2, 25, 0, T)` |
| 心情门控 | ✅ | 两段 constant，以 mood=12 为界 |
| 同设施配对 | ✅ | `evaluate_room()` 识别房间成员后输出聚合段 |
| 阵营计数（每名格拉斯哥帮+20%) | ✅ | `synergy_faction_room()` 跨干员计数 |
| 跨设施 buff（中枢→buff池→消费） | ✅ | `compute_buff_pool()` → `synergy_buff_pool_consumer()` |

## 参考

- 策略概要: [`slot-processing-model.md`](./slot-processing-model.md)
- 联动体系建模: [`synergy-systems.md`](./synergy-systems.md)
- 约束体系基线: [`constraints-and-data-baseline.md`](./constraints-and-data-baseline.md)
