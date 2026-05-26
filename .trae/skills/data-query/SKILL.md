---
name: "data-query"
description: "对 character_identity/buffs_infrastructure 等数据源执行常见查询（干员技能、设施分类、buff 详情、组织筛选、统计等）。当 agent 需要查询干员数据、分析 buff 或统计信息时调用，替代每次写临时脚本的模式。"
---

# 数据查询 Skill

## 触发条件

当 agent 需要执行以下操作时，应使用 `scripts/query_data.py` 而非临时写 Python 脚本：

- 查询某个干员的基建技能和身份信息
- 列出某设施类型的所有干员
- 按组织/队伍/势力筛选干员
- 查找 buff 详情和拥有者
- 比较两个干员的基建技能差异
- 获取数据统计概览
- 搜索 buff 名称或描述

## 数据源

脚本默认使用轻量数据源（秒级加载）：

| 文件 | 大小 | 用途 |
|------|------|------|
| `character_identity.json` | ~120KB (415 干员) | 干员身份 + 基建技能列表 |
| `buffs_infrastructure.json` | 520 条 buff | 基建生产 buff 详情 |
| `buffs_non_production.json` | 207 条 buff | 训练室/加工站 buff 详情 |

如需 `skill_icon` 或 MAA 效率值（来自 `building_data.json` + `infrast.json`），应直接使用 `steward_core/data_loader.py` 而非本脚本。

## 可用子命令

### `operator <干员名或ID>` — 查干员身份与技能

```bash
python scripts/query_data.py operator 阿米娅
python scripts/query_data.py operator char_003_kalts
```

输出：星级、职业、势力/组织/队伍、附属势力、全部基建技能（含 buff 名称、设施、需求精英阶段、效率值、描述）。

### `facility <设施类型>` — 列出某设施类型的所有干员

```bash
python scripts/query_data.py facility MANUFACTURE
python scripts/query_data.py facility TRADING
python scripts/query_data.py facility CONTROL
```

设施类型：`CONTROL` / `MANUFACTURE` / `TRADING` / `POWER` / `MEETING` / `HIRE` / `DORMITORY`

输出：干员列表，按星级降序排列，包含需求精英阶段和技能名。

### `buff <buffId或名称>` — 查 buff 详情与拥有者

```bash
python scripts/query_data.py buff 最高权限
python scripts/query_data.py buff manu_prod_spd[000]
```

输出：buff 名称、设施类型、效率值、描述、目标、拥有干员列表（含星级）。

### `group <组织ID>` — 按组织筛选干员

```bash
python scripts/query_data.py group karlan
python scripts/query_data.py group abyssal
```

### `team <队伍ID>` — 按队伍筛选干员

```bash
python scripts/query_data.py team action4
```

### `nation <势力ID>` — 按势力筛选干员（含附属势力）

```bash
python scripts/query_data.py nation victoria
python scripts/query_data.py nation egir
```

### `search <关键词>` — 搜索 buff 名称/描述

```bash
python scripts/query_data.py search 标准化
python scripts/query_data.py search 骑士
```

输出：匹配的 buff 列表，含设施类型、拥有人数，名称匹配优先。

### `rarity <星级>` — 按星级筛选干员

```bash
python scripts/query_data.py rarity 6    # 6★
python scripts/query_data.py rarity 4    # 5★
```

星级映射：0=1★, 1=2★, 2=3★, 3=4★, 4=5★, 5=6★

### `compare <干员1> <干员2>` — 对比基建技能

```bash
python scripts/query_data.py compare 阿米娅 凯尔希
python scripts/query_data.py compare char_131_flame char_134_ifrit
```

输出：独有技能和共同技能对比。

### `stats` — 数据统计概览

```bash
python scripts/query_data.py stats
```

输出：星级/职业/势力/组织/队伍分布、技能数分布、设施分布、阶段分布。

### 列举类命令

```bash
python scripts/query_data.py list-groups      # 所有组织及人数
python scripts/query_data.py list-teams       # 所有队伍及人数
python scripts/query_data.py list-nations     # 所有势力及人数
python scripts/query_data.py list-facilities  # 所有设施类型及技能/干员数
```

## 注意事项

1. **必须先有数据文件**：`character_identity.json` 和 `buffs_infrastructure.json` 需要存在。如果缺失，先运行 `python scripts/extract_character_identity.py` 生成。
2. **输出可能较长**：`facility`、`stats` 等命令输出较多行，agent 应重定向到临时文件后读取，避免终端截断。
3. **干员名支持中文**：如"阿米娅"、"12F"均可直接使用。
4. **不依赖 MAA**：本脚本仅读取项目内的 JSON 文件，不需要 MAA 安装。
