# RhodeLogisticsSteward（罗德基建管家）

基于 MAA（MaaAssistantArknights）API 的《明日方舟》基建排班求解器。读取玩家干员数据，计算最优排班方案，输出 MAA 基建排班协议 JSON。

## 快速开始

```powershell
# 轻量报表（推荐） — 求解 + 输出 Markdown 报告
python report.py 12 14      # 14×12h (7 天)
python report.py 8 3        # 3×8h

# 完整排班 — 同上 + 保存 JSON 排班文件
python run_solver.py                     # 默认 14×12h
python run_solver.py --hours 8 --shifts 3
python run_solver.py --params custom.json  # 自定义参数

# 运行模式
python run_solver.py --brief             # 精简报告（跳过详细排班明细，JSON 照常保存）
python run_solver.py --report            # 只出报表，不保存 JSON
```

关闭阶段耗时输出（默认开启）：`$env:RHO_TIMING=0`

## 数据文件

项目根目录已包含所需的三个清洗文件，无需额外下载：

| 文件 | 说明 |
|------|------|
| `character_identity.json` | 干员身份与技能映射 |
| `buffs_infrastructure.json` | 基建 buff 效率值 |
| `buffs_non_production.json` | 非生产设施 buff（宿舍/会客室等） |

输出：
- 报告 → `output/report_SlotStrategy_<shifts>x<hours>h_<timestamp>.md`
- JSON 排班文件 → `output/custom_infrast/`，放入 MAA `resource/custom_infrast/` 即可使用
