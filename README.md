# RhodeLogisticsSteward（罗德基建管家）

基于 MAA（MaaAssistantArknights）API 的《明日方舟》基建排班求解器。读取玩家干员数据，计算 243 布局下最优排班方案，输出 MAA 基建排班协议 JSON。

## 快速开始

```powershell
# 默认 14x12h (7天周期)
python run_solver.py

# 精简报告（只显示概览/换班/产能）
python run_solver.py --brief

# 自定义班次（双班 12h）
python run_solver.py --shifts 2 --hours 12

# K-Beam 策略（制造站 top-K 多路径保留）
python run_solver.py --strategy kbeam3
python run_solver.py --strategy kbeam5

# 不动点迭代策略（BuffPool 自洽）
python run_solver.py --strategy iterative

# 查看所有可用策略
python run_solver.py --list

# 三件套开关全开（独占冲突检查 + 局部搜索 + 全局状态评分）
python run_solver.py --strategy baseline --all-on

# 自定义参数文件
python run_solver.py --params my_params.json

# 覆盖策略默认参数
python run_solver.py --strategy kbeam5 --kw "beam_width=7"
```

## 数据文件

项目根目录已包含所需的三个清洗文件，无需额外下载：

| 文件 | 说明 |
|------|------|
| `character_identity.json` | 干员身份与技能映射 |
| `buffs_infrastructure.json` | 基建 buff 效率值 |
| `buffs_non_production.json` | 非生产设施 buff（宿舍/会客室等） |

输出目录：`output/custom_infrast/`，将生成的 JSON 放入 MAA `resource/custom_infrast/` 即可使用。
