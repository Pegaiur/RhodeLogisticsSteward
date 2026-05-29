---
alwaysApply: false
globs: steward_core/solver/strategies/*.py,steward_core/solver/config.py,run_solver.py
---

# 策略注册与 CLI 配置规范

## 新增 Strategy 的步骤

1. 在 `steward_core/solver/strategies/<name>.py` 中实现 Strategy 子类
2. 设置 `cli_key`（短键名）、`cli_desc`（一行描述）、`default_kwargs`（构造参数默认值）
3. 在 `steward_core/solver/strategies/__init__.py` 中：
   - import 新类
   - 注册到 `STRATEGY_REGISTRY` 字典
   - 加入 `__all__`
4. 编写测试 `tests/solver/test_<name>.py`，使用 `tests/strategy_helpers.py`
5. 运行 `python -m pytest tests/ -v` 确认全绿

## 新增 SolverConfig 开关的步骤

1. 在 `steward_core/solver/config.py` 的 `SolverConfig` dataclass 中新增字段（默认 `False`）
2. 更新 `SolverConfig.all_on()` 方法
3. `run_solver.py` 的 `--all-on` 自动覆盖 `all_on()`，无需额外改动
4. 运行 `python -m pytest tests/ -v` 确认全绿

## CLI 参数优先级

```
CLI --hours / --kw 显式参数 > SolverParams JSON 文件 > Preset 默认值 > 出厂默认值
```

## 文件职责

| 文件 | 职责 |
|------|------|
| `strategies/__init__.py` | `STRATEGY_REGISTRY` 策略注册表（唯一真相源） |
| `run_solver.py` | CLI 解析 + 组装 SolverConfig，不定义预设 |
| `config.py` | SolverConfig 字段 + 工厂方法 |
| `params.py` | SolverParams 字段 + `from_json()` / `apply_overrides()` |
