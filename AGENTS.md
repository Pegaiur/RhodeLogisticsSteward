# AGENTS.md

## 项目概述

**RhodeLogisticsSteward**（罗德物流管家）是 MAA（MaaAssistantArknights）的基建增强模块。通过 MAA API 获取《明日方舟》玩家干员数据，基于练度与基建技能计算最优排班方案，输出 MAA `custom_infrast` 协议 JSON 供执行。

**核心原则**：不增加使用者部署负担。利用用户已有的 MAA 安装完成图像识别与控制，本项目只负责排班算法。

**数据来源**：

| 数据 | 来源 | 说明 |
|------|------|------|
| 玩家干员练度 | MAA OperBox 回调 | `operators_data.json`，不入库（个人数据） |
| 干员→技能映射 | [ArknightsGameData](https://github.com/Kengxxiao/ArknightsGameData) | `building_data.json`，不入库（外部下载） |
| 技能→效率值 | MAA `resource/infrast.json` | 随 MAA 安装提供 |

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 运行环境 | Python 3.12+ | 纯 Python，无 C 扩展编译需求 |
| MAA 绑定 | `maafw` (pip) | MAA Python API，通过 ctypes 调用 MaaCore.dll |
| 图像识别 | MAA 内置 (OpenCV + PaddleOCR + onnxruntime) | 不直接调用，由 MAA OperBox/Infrast 任务间接使用 |
| 数据处理 | 标准库 json + pathlib | 解析 building_data.json / infrast.json |
| 求解算法 | 制造站穷举(含联动) + 剪枝 + 贪心 | 见 `docs/strategy-brief.md` |
| 输出格式 | MAA 基建排班协议 JSON | 见 [MAA 基建排班协议](https://docs.maa.plus/zh-cn/protocol/base-scheduling-schema.html) |

**版本锁**：

| 依赖 | 要求 | 备注 |
|------|------|------|
| MAA | v4.28+ | MaaCore.dll + resource/ 目录 |
| Python | 3.10+ | f-string / pathlib 兼容 |
| maafw | 5.x | 通过 `pip install maafw` 安装 |
| building_data.json | 国服最新 | 手动或脚本从 ArknightsGameData 下载 |

## 项目结构

```
RhodeLogisticsSteward/
├── AGENTS.md                     # 本文件
├── .gitignore
├── scan_operators.py             # 干员扫描工具
├── steward_core/                 # 排班核心库
│   ├── synergy/                  # 联动体系子包（14模块）
│   │   ├── __init__.py           #   ─ 全部公开符号重导出
│   │   ├── types.py              #   ─ NamedTuple类型 + TABLES注册器
│   │   ├── helpers.py            #   ─ 名称集合/常量/辅助函数
│   │   ├── mfg_linkages.py       #   ─ A层·制造站联动（配对/阵营/技能/自动化/低语/爬升/归零）
│   │   ├── trade_linkages.py     #   ─ A层·贸易站联动（订单压缩/销路宣发）
│   │   ├── facility_linkages.py  #   ─ A层·设施数量联动 + 发电站计数
│   │   ├── control_linkages.py   #   ─ C层·中枢全局效率 + per-operator条件加成
│   │   ├── global_linkages.py    #   ─ B层·跨房间配对 + 全局阵营计数
│   │   ├── buff_pool.py          #   ─ B层·BuffPool生成/消费 + 工程机器人
│   │   ├── classification.py     #   ─ 制造站/贸易站干员分类与候选池
│   │   ├── registry.py           #   ─ SystemContributor注册表
│   │   ├── _derived.py            #   ─ 脚本推导的锚点表+名称集合
│   │   └── mood.py               #   ─ 中枢心情恢复
│   ├── solver/                   # 排班求解器子包（15模块）
│   │   ├── __init__.py           #   ─ solve_mvp() 入口 + config/bundle/refine/LocalSearch 重导出
│   │   ├── config.py             #   ─ SolverConfig 开关机制（三件套总开关）
│   │   ├── params.py             #   ─ SolverParams 参数注册表（数值参数集中管理）
│   │   ├── pipeline.py           #   ─ Pipeline 可组合流水线（Phase 顺序可配置）
│   │   ├── context.py            #   ─ GlobalContext 统一上下文构造
│   │   ├── bundle.py             #   ─ 支撑包数据结构（SupportBundle + SupportResult）
│   │   ├── phase1_mfg.py         #   ─ Phase 1: 制造站穷举
│   │   ├── phase3_trade.py       #   ─ Phase 2: 贸易站穷举（中枢后置）
│   │   ├── phase2_control.py     #   ─ Phase 3: 中枢填充
│   │   ├── phase3_remaining.py   #   ─ Phase 4: 剩余设施贪心
│   │   ├── phase4_dorm.py        #   ─ Phase 5: 宿舍填充
│   │   ├── global_state.py       #   ─ 包级稀缺度评分注入（Step 3 全局状态注入）
│   │   ├── refine.py             #   ─ 局部搜索后处理（单房间替换 + 干员交换）
│   │   ├── support.py            #   ─ 支撑干员计算
│   │   └── greed.py              #   ─ 贪心分配/组合评估/条件验证
│   ├── models.py                 # 核心数据模型
│   ├── evaluate.py               # 房间效率评估
│   ├── production.py             # 产出/日产计算
│   ├── output.py                 # MAA 基建排班协议输出
│   ├── efficiency_fn.py          # 效率函数（常数/爬升）
│   ├── data_loader.py            # 数据加载器（v2）
│   ├── mood.py                   # 心情/消耗模型
│   └── constants.py              # 布局/设施常量
├── docs/
│   ├── constraints-and-data-baseline.md  # 约束体系与数据基线
│   ├── strategy-brief.md         # 精简策略概要
│   ├── efficiency-function-design.md  # 效率函数建模
│   ├── synergy-systems.md        # 联动体系建模
│   ├── inbox.md                  # 需求收件箱（远期待办登记）
│   ├── strategy-refactor-plan.md  # Strategy 策略层重构计划（v0.5.0）
│   ├── strategy-refactor-notes.md # 重构实施笔记
│   ├── archive/
│   │   ├── index.md               # 里程碑索引
│   │   ├── roadmap-mvp.md         # 开发路线图（已归档）
│   │   ├── refactor-plan.md       # 重构计划（已归档）
│   │   └── solver-improvement-plan.md  # 求解器优化计划（已实施，已归档）
└── output/                       # 生成的排班文件（不入库）
    └── custom_infrast/
```

## 全局规则

1. **注释与提交信息必须使用中文**。每个 commit 必须有具体变更描述，禁止空 message。
2. **不修改 MAA 源码**。本项目通过 MAA API 调用，不 fork、不重编译 MAA。
3. **玩家数据不入库**。`operators_data.json`、`building_data.json` 均被 `.gitignore` 排除。
4. **文档优先**。策略变更前先更新对应文档，再写代码。
5. **代码风格**：Python 遵循 PEP 8，缩进 4 空格，函数/类使用中文 docstring。
6. **新文件创建**前检查现有文件是否可复用，避免重复。
7. **不引入非必要依赖**。能用标准库解决的不引入第三方包。

## 人工维护数据

以下分类数据无法从 ArknightsGameData 直接提取，需手动维护。每次游戏更新新增此类干员/buff 时，须同步更新对应代码或本表。

### 基建分类标签

游戏基建 buff 描述中引用的 `<cc.tag.xxx>` 标签（如"骑士"、"杜林族"、"作业平台"等）**并非** `character_table.json` 的 `tagList` 字段（那是公招标签），而是由游戏引擎根据多个字段组合推导。推导规则无法从解包数据中自动化提取，因此本项目采用硬编码 + 推导回退的策略。

| 标签 | 游戏 ref | 判定逻辑 | 维护位置 | 更新触发条件 |
|------|---------|----------|----------|-------------|
| 骑士 | `tag.knight` | name 集合 + `nationId=="kazimierz"` + `groupId=="pinus"` | `synergy/helpers.py` `_KNIGHT_NAMES` | 新增卡西米尔骑士干员 |
| 杜林族 | `tag.durin` | `raceId == "DURIN"` | 由 `character_table.json` 自动推导 | — |
| 作业平台 | `tag.op` | 特定 profession | `synergy/helpers.py` `_OP_PLATFORM_NAMES` 硬编码 4 台 | 新增机器人/作业平台干员 |
| 怪物猎人小队 | `tag.mh` | 联动限定干员 | 尚未建模 | — |
| 莱欧斯小队 | `tag.dungeon` | 联动限定干员 | 尚未建模 | — |

### 硬编码数据清单

以下硬编码数据不受 ArknightsGameData 驱动，每次游戏版本更新需人工审查。**详情以源码为准，本文档不重复列出：**

| 数据类别 | 权威来源 | 说明 |
|----------|----------|------|
| 系统贡献者 | [`registry.py`](file:///d:/Dev/RhodeLogisticsSteward/steward_core/synergy/registry.py) `_SYSTEM_CONTRIBUTORS` | 效率为0但有系统贡献的干员，按 `contribution_type` 分类标注 |
| 联动映射表 | [`types.py`](file:///d:/Dev/RhodeLogisticsSteward/steward_core/synergy/types.py) `TABLES` 注册器 | 13 张 dict 表，含消费者函数和更新触发条件 |
| 名称集合 | [`helpers.py`](file:///d:/Dev/RhodeLogisticsSteward/steward_core/synergy/helpers.py) | `_KNIGHT_NAMES`、`_OP_PLATFORM_NAMES`、`_MH_NAMES` 等 10 个集合/常量 |
| 辅助常量 | [`helpers.py`](#) | `_PINUS_GROUP`、`_ORDER_ANCHOR_PREFIXES`、`_B_ROSEMARY` 等 |

### 维护流程

1. 游戏版本更新后，查阅 [PRTS Wiki 基建页面](https://prts.wiki/w/基建) 确认新增干员/技能
2. 对照上述权威来源逐项检查是否需要更新
3. 更新代码后运行 `python -m pytest tests/ -v` 确保现有测试通过
4. 修改了协同表或名称集合后，按 `.trae/rules/hardcoded-data.md` 中的规则运行对应生成脚本
5. 提交时在 commit message 中注明更新了哪些表


## AI Agent 发现流程

当 AI Agent 进入本项目工作区时，按以下顺序发现上下文：

1. **读取 AGENTS.md**（本文件）→ 理解项目定位、技术栈、规则、包结构
2. **读取 `docs/strategy-brief.md`** → 理解当前策略与算法骨架
3. **按需深入到子包**：
   - 联动体系逻辑 → `steward_core/synergy/`：先读 `__init__.py` 了解公开 API，再按需进入对应模块（A层→`mfg_linkages`/`trade_linkages`/`facility_linkages`，B层→`buff_pool`/`global_linkages`，C层→`control_linkages`/`mood`）
   - 求解/排班逻辑 → `steward_core/solver/`：先读 `__init__.py` 的 `solve_mvp()` Pipeline 编排，再按需进入 `pipeline.py`（Phase 顺序）、各 `phase*.py`（具体阶段）、`refine.py`（局部搜索）、`global_state.py`（全局状态评分）
   - 数据模型/常量 → `steward_core/models.py` / `constants.py`
   - 表维护/新增 → `synergy/types.py` TABLES 注册器 + `synergy/registry.py` 系统贡献者 + AGENTS.md §人工维护数据
   - 硬编码数据维护规则 → `.trae/rules/hardcoded-data.md`（锚点生成、名称集合同步、分类覆盖率）

**关键文件名索引**：

| 关键词 | 目标文件 / 位置 |
|--------|----------------|
| 排班策略/算法 | `docs/strategy-brief.md` |
| 约束/设施/联动 | `docs/constraints-and-data-baseline.md` |
| 数据源/覆盖度/效率值 | `docs/constraints-and-data-baseline.md` 附录 A |
| 效率函数/e(t) | `docs/efficiency-function-design.md` |
| 联动/体系建模 | `docs/synergy-systems.md` |
| 设施容量/约束/多班次 | `docs/strategy-brief.md` §设施容量/§约束/§策略 |
| 干员/buff 数据查询 | `.trae/skills/data-query/query_data.py` (通过 `data-query` skill) |
| 人工维护/硬编码数据/更新 | AGENTS.md §人工维护数据 |
| 硬编码数据生成规则 | `.trae/rules/hardcoded-data.md` |
| 策略注册与 CLI 配置 | `.trae/rules/strategy-config.md` |
| 重构/模块拆分/架构 | `docs/archive/refactor-plan.md`（已归档） |
| 求解器优化/三件套 | `docs/archive/solver-improvement-plan.md`（v0.4.0 已实施） |
| 远期待办/需求登记 | `docs/inbox.md` |
| 联动体系代码 | `steward_core/synergy/` → `__init__.py` 重导出一览，`types.py` TABLES 注册器索引全部表 |
| 求解/排班代码 | `steward_core/solver/` → `__init__.py` solve_mvp() 入口，各 `phase*.py` 按阶段独立，`pipeline.py` 配置 Phase 顺序 |

## 版本管理

### 分支策略

```
master ────────────────────────────● 稳定版本
  │
  ├── dev ────────────────────────● 开发主线
  │     │
  │     ├── feat/xxx ──────────── 功能分支
  │     └── fix/xxx ───────────── 修复分支
```

- `master`：通过全部验证的稳定版本
- `dev`：开发主线，功能完成后合并入
- `feat/*` / `fix/*`：单功能/单修复分支，完成后合并入 dev

### 版本号规则

采用语义化版本 `MAJOR.MINOR.PATCH`：

| 变更类型 | 版本段 | 示例 |
|----------|--------|------|
| 首次可用的排班求解器 | 0.1.0 | 起步 |
| 通过 Step 1 验证 | 0.2.0 | 核心算法验证 |
| 通过 Step 2 验证 | 0.3.0 | 横向重构完成 |
| 求解器三件套优化 | 0.4.0 | 支撑包+局部搜索+全局状态 |
| 首个正式版 | 1.0.0 | 全验证通过 |
| MAA 发版需适配 | PATCH +1 | 0.4.1 |

### 提交约定

使用 `commit-convention` 技能生成的中文 commit message：

```
feat(core): 实现单班次贪心求解器
fix(solver): 修复制造站产物类型匹配错误
docs(roadmap): 添加 Step 2 验证结果
```

### Tag

每个 milestone 完成后打 tag：

```
v0.1.0  → M1: Step 1 验证通过
v0.2.0  → M2: Step 2 验证通过
v0.3.0  → M3: Step 3 验证通过
v0.4.0  → M4: 求解器三件套优化（支撑包+局部搜索+全局状态）
v1.0.0  → 首个正式版
```

## 文档规范

| 规则 | 说明 |
|------|------|
| 语言 | **中文**，技术术语可保留英文 |
| 格式 | Markdown（.md），代码使用 ` ``` ` 块标语言 |
| 图表 | Mermaid，使用 `mermaid-charting` 技能规范 |
| 命名 | `lower-kebab-case.md`（如 `strategy-brief.md`） |
| 位置 | 全部放在 `docs/` 目录下 |
| 行宽 | 代码块无限制，正文建议 ≤120 字符 |
| 引用 | MAA 文档链接使用 `https://docs.maa.plus/...` |
| 数据 | 外部获取的大型数据文件不加文档，记录来源 URL 与获取方式 |

## 工作流

```
用户运行 scan_operators.py → 获取干员数据
           │
           ▼
排班求解器 (steward_core/) → 生成 custom_infrast/*.json
           │
           ▼
用户将 JSON 放入 MAA resource/custom_infrast/ 目录
           │
           ▼
MAA Infrast 任务 (mode=10000) → 自动执行排班
```

## 关键外部参考

| 资源 | URL | 说明 |
|------|-----|------|
| MAA 仓库 | https://github.com/MaaAssistantArknights/MaaAssistantArknights | MAA 源码与资源 |
| MAA 集成文档 | https://docs.maa.plus/zh-cn/protocol/integration.html | API 调用规范 |
| MAA 基建排班协议 | https://docs.maa.plus/zh-cn/protocol/base-scheduling-schema.html | 输出 JSON schema |
| ArknightsGameData | https://github.com/Kengxxiao/ArknightsGameData | 游戏解包数据 |
| PRTS Wiki 基建 | https://prts.wiki/w/基建 | 游戏机制参考 |
| 一图流排班生成器 | https://ark.yituliu.cn/tools/schedule | 可视化排班参考 |
