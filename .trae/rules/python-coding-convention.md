# Python 编码规范

## 编码与字符集

文件编码 UTF-8。**代码逻辑层**（标识符、运行时字符串）仅允许 ASCII。

| 位置 | 禁止 | 替代 |
|------|------|------|
| 标识符（函数/类/变量） | `α` `β` `₀` | `alpha` `beta` `P0` |
| 运行时字符串（错误/f-string/日志） | `≥` `≤` `≠` `₀` | `>=` `<=` `!=` `P0` |
| 注释/docstring | — | 中文 `，。：（）→` 自由使用 |
| 字符串字面量 | — | 游戏数据标识符 `"标准化·α"` 须与 `building_data.json` 一致 |

## 风格

- 遵循 PEP 8，缩进 4 空格
- 行宽 ≤120 字符
- 行末无空白
- 每文件末尾一个空行

## 命名

| 类型 | 规范 | 示例 |
|------|------|------|
| 模块 | `snake_case` | `exhaust_mfg.py` |
| 类 | `PascalCase` | `SolverConfig` |
| 函数/方法 | `snake_case` | `solve_mvp()` |
| 变量 | `snake_case` | `op_lookup` |
| 常量 | `UPPER_SNAKE` | `TRADE_BASE_GOLD_PER_DAY` |
| 私有成员 | `_underscore` 前缀 | `_mk_op()` |

## 注释与文档

- 注释与提交信息必须使用中文
- `#` 后留一个空格
- 函数/类使用中文三引号 docstring
- 每个 commit 必须有具体变更描述

## 导入

标准库 → 第三方 → 本地，每组间空行。禁止 `import *`。

## 审计清单

- [ ] 标识符 / 运行时字符串是否含非 ASCII 字符？
- [ ] docstring 是否用中文？缩进是否正确？
- [ ] 导入是否分组且无 `import *`？
