# RhodeLogisticsSteward（罗德基建管家）

基于 MAA（MaaAssistantArknights）API 的《明日方舟》基建排班求解器。读取玩家干员数据，计算最优排班方案，输出 MAA 基建排班协议 JSON。

## 快速开始

```powershell
# 默认 14×12h (7 天周期)，生成 JSON + 报告
python run_solver.py

# 自定义班次
python run_solver.py --shifts 3 --hours 8

# 自定义参数
python run_solver.py --params custom.json

# 仅控制台报告（暂存第一班 JSON）
python run_solver.py --brief

# 只出报表，不保存 JSON
python run_solver.py --report

# 轻量报表工具（复用相同求解器）
python report.py 12 14      # 14×12h
python report.py 8 3        # 3×8h
```

运行过程中自动输出各阶段耗时（`[计时] pipeline` / `[计时] phase_*`），便于性能分析。

## 数据文件

项目根目录已包含所需的三个清洗文件，无需额外下载：

| 文件 | 说明 |
|------|------|
| `character_identity.json` | 干员身份与技能映射 |
| `buffs_infrastructure.json` | 基建 buff 效率值 |
| `buffs_non_production.json` | 非生产设施 buff（宿舍/会客室等） |

输出目录：`output/custom_infrast/`，将生成的 JSON 放入 MAA `resource/custom_infrast/` 即可使用。

报告默认保存在 `output/` 目录，文件名格式 `report_<shift_hours>h.md`。
