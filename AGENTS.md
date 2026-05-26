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
| 求解算法 | 贪心 + 可选联动校验 | 见 `docs/strategy-brief.md` |
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
│   └── efficiency-function-design.md  # 效率函数统一建模（草案）
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
| 设施容量/约束/多班次 | `docs/strategy-brief.md` §设施容量/§约束/§策略 |

## 技能 (Skills)

本项目使用 Trae IDE 的 Skill 机制辅助开发和文档编写。

### 已注册技能

| 技能 | 用途 | 触发条件 |
|------|------|----------|
| **commit-convention** | 生成中文约定式提交信息 + 版本号推算 + tag 管理 | 提交代码时自动拉起 |
| **mermaid-charting** | Mermaid 图表渲染（flowchart/sequence/er/pie/mindmap 等 13 种） | 需要可视化流程、架构、数据关系时 |
| **tdd-workflow** | TDD 红-绿-重构循环，3A 测试模板 | 编写求解器单元测试时 |
| **TRAE-debugger** | HTTP 日志收集 + 假设→插桩→复现→分析 科学调试 | 排班结果异常需运行时诊断时 |

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
