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
├── steward_core/                 # 排班核心库（待开发）
├── docs/
│   ├── constraints-and-data-baseline.md  # 约束体系与数据基线（含溯源核验）
│   ├── strategy-brief.md         # 精简策略概要（编码上下文用）
│   ├── efficiency-function-design.md  # 效率函数统一建模（草案）
│   ├── synergy-systems.md        # 联动体系建模（16个独立函数清单）
│   ├── archive/
│   │   └── roadmap-mvp.md         # 开发路线图（MV0-MV5，已归档）
│   └── refactor-plan.md           # 重构计划
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

### 硬编码表清单

以下模块包含不受 ArknightsGameData 驱动的硬编码映射表，每次游戏版本更新需人工审查：

**`steward_core/synergy/`** — 联动体系表

| 表名 | 维护内容 | 触发条件 |
|------|----------|----------|
| `_SYSTEM_CONTRIBUTORS` | 系统贡献者注册表（含锚点/全局/buff生成/设施修改器） | 新增效率为0但有系统贡献的干员 |
| `_A_PAIR_TABLE` | 干员配对组合 | 新增配对型联动 buff |
| `_A_ROOM_FACTION_TABLE` | 同房阵营计数联动 | 新增同房阵营计数型联动 buff |
| `_A_ROOM_FACTION_EXTRA` | 同房阵营额外加成（如摩根+推王→额外+35%） | 新增同房阵营额外加成 |
| `_A_SKILL_COUNT_TABLE` | 技能类型计数锚点 | 新增计数型联动 buff |
| `_A_AUTOMATION_FALLBACK` | 自动化名称→加成回退值（buff_id 不可用时） | 新增自动化干员或 buff 变更 |
| `_ZEROING_VARIANT_TABLE` | 归零变体（科学改造/流程优化） | 新增归零型变体 buff |
| `_TOKEN_PROD_TABLE` | 机械精通加成映射 | 新增作业平台联动 buff |
| `_RAMPING_SKILL_TABLE` | 爬升型效率技能参数 | 新增 manu_prod_spd_addition[*] 爬升型技能 |
| `_POWER_BUFF_BONUS` | 自动化 buff_id→加成映射 | 新增 manu_prod_spd&power[*] 类型 buff |
| `_A_FACILITY_LINK_TABLE` | 设施数量联动表 | 新增设施联动 buff |
| `_C_CONTROL_GLOBAL_TABLE` | 中枢全局效率 | 新增中枢全局 buff |
| `_KNIGHT_NAMES` | 骑士干员名称（安全网补全） | 新增卡西米尔但不属于 kazimierz 势力/pinus 组织的骑士 |
| `_B_BUFF_CONSUMER_TABLE` | buff 池消费者 | 新增 buff 池消费者 |
| `_B_GLOBAL_FACTION_TABLE` | 全局阵营计数 | 新增全局阵营计数型 buff |
| `_B_CROSS_ROOM_PAIR_TABLE` | 跨房间配对表 | 新增跨设施干员条件配对 buff |
| `ROSEMARY_SUPPORT` | 迷迭香支撑干员 | 新增迷迭香联动链参与者 |
| `_RAMPING_SKILL_TABLE` | 爬升型效率技能参数 | 新增 manu_prod_spd_addition[*] 爬升型技能 |
| `_ZEROING_VARIANT_TABLE` | 归零变体（科学改造/流程优化） | 新增归零型变体 buff |
| `_TOKEN_PROD_TABLE` | 机械精通加成映射 | 新增作业平台联动 buff |
| `_OP_PLATFORM_NAMES` | 作业平台干员名称 | 新增机器人/作业平台干员 |
| `_MH_NAMES` | 怪物猎人小队干员名 | 新增怪物猎人联动干员 |
| `_LUNG_MEN_GUARD_NAMES` | 龙门近卫局干员名 | 新增龙门近卫局干员 |
| `_BLACKSTEEL_HOLDERS` | 老友相聚中枢持有者 | 新增黑钢国际相关中枢干员 |
| `TABLES` | 硬编码表集中索引（`TableMeta` 注册器） | 任意硬编码表新增/改名时同步更新 |

### 维护流程

1. 游戏版本更新后，查阅 [PRTS Wiki 基建页面](https://prts.wiki/w/基建) 确认新增干员/技能
2. 对照上表逐项检查是否需要更新硬编码数据
3. 更新代码后运行 `python -m pytest tests/ -v` 确保现有测试通过
4. 提交时在 commit message 中注明更新了哪些表


## AI Agent 发现流程

当 AI Agent 进入本项目工作区时，按以下顺序发现上下文：

1. **读取 AGENTS.md**（本文件）→ 理解项目定位、技术栈、规则
2. **读取 `docs/strategy-brief.md`** → 理解当前策略与算法骨架
3. **按需读取**：
   - 需要约束体系与数据基线 → `docs/constraints-and-data-baseline.md`
   - 需要效率函数建模方案 → `docs/efficiency-function-design.md`
   - 实现排班求解器 → 关注 `steward_core/` 目录

**关键文件名索引**：

| 关键词 | 目标文件 |
|--------|----------|
| 排班策略/算法 | `docs/strategy-brief.md` |
| 约束/设施/联动 | `docs/constraints-and-data-baseline.md` |
| 数据源/覆盖度/效率值 | `docs/constraints-and-data-baseline.md` 附录 A |
| 效率函数/e(t) | `docs/efficiency-function-design.md` |
| 联动/体系建模 | `docs/synergy-systems.md` |
| 设施容量/约束/多班次 | `docs/strategy-brief.md` §设施容量/§约束/§策略 |
| 干员/buff 数据查询 | `.trae/skills/data-query/query_data.py` (通过 `data-query` skill) |
| 人工维护/硬编码数据/更新 | AGENTS.md §人工维护数据 |
| 重构/模块拆分/架构 | `docs/refactor-plan.md` |

## 技能 (Skills)

本项目使用 Trae IDE 的 Skill 机制辅助开发和文档编写。

### 已注册技能

| 技能 | 用途 | 触发条件 |
|------|------|----------|
| **commit-convention** | 生成中文约定式提交信息 + 版本号推算 + tag 管理 | 提交代码时自动拉起 |
| **mermaid-charting** | Mermaid 图表渲染（flowchart/sequence/er/pie/mindmap 等 13 种） | 需要可视化流程、架构、数据关系时 |
| **tdd-workflow** | TDD 红-绿-重构循环，3A 测试模板 | 编写求解器单元测试时 |
| **TRAE-debugger** | HTTP 日志收集 + 假设→插桩→复现→分析 科学调试 | 排班结果异常需运行时诊断时 |
| **data-query** | 对数据源执行常见查询，替代每次写临时脚本 | 需要查询干员数据、分析 buff 或统计信息时 |

### 技能约定

- `commit-convention` 产出中文 commit message，格式 `type(scope): 描述`
- `mermaid-charting` 图表使用 ` ```mermaid ` 代码块，优先 flowchart/mindmap
- 需要用户级技能时以用户侧注册为准，本文件仅声明项目级约定

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
| 通过 Step 4 全验证 | 1.0.0 | 首个正式版 |
| MAA 发版需适配 | PATCH +1 | 0.2.1 |

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
v1.0.0  → M4: 全验证通过
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
