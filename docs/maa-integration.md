# MAA 集成方案与干员数据采集

## 1. 概述

本项目（RhodeLogisticsSteward）定位为 MAA（MaaAssistantArknights）的**基建增强模块**，通过 MAA 提供的 API 获取玩家干员数据，基于干员练度和基建技能计算最优排班方案，最终输出符合 MAA `custom_infrast` 协议的 JSON 文件供 MAA 执行。

本项目的核心原则是**不额外增加使用者部署负担**——利用 MAA 已有的图像识别能力做数据采集，本项目精力集中在排班算法这个核心价值上。

## 2. MAA 集成方式

### 2.1 依赖关系

```
用户已安装 MAA（MAA.exe + MaaCore.dll + resource/）
         │
         ▼
  RhodeLogisticsSteward（本项目）
    ├── 通过 MAA Python API 调用 OperBox / Infrast
    ├── 读取 MAA 的 resource/infrast.json 获取基建技能数据
    └── 输出 custom_infrast/*.json 供 MAA 执行排班
```

### 2.2 关键技术点

| 能力 | MAA 机制 | 本项目用法 |
|------|----------|-----------|
| 干员数据采集 | `OperBox` 任务 + `SubTaskExtraInfo` 回调 | 获取 `own_opers` JSON（id/name/rarity/elite/level/potential） |
| 基建技能数据 | `resource/infrast.json`（191KB） | 解析每名干员的基建技能效率值 |
| 排班执行 | `Infrast` 任务（mode=10000 自定义模式） | 读取本项目生成的 `custom_infrast/*.json` |
| 自定义配置扩展 | `_custom.json` 自动补丁机制 | 可选：对 MAA 内置基建数据进行修正 |
| 增量资源加载 | `Asst.load(incremental_path=...)` | 可选：将本项目资源作为增量包注入 |

### 2.3 Python API 调用模式

```python
from asst.asst import Asst
from asst.utils import InstanceOptionType

# 加载 MAA DLL + 资源（从用户已有的 MAA 安装目录）
Asst.load(path=r"G:\Tools\MAA-v4.28.4-win-x64")

# 创建实例（注册回调函数）
asst = Asst(callback=my_callback)
asst.set_instance_option(InstanceOptionType.touch_type, "minitouch")

# 连接模拟器
asst.connect(adb_path, "127.0.0.1:16384", "MuMuEmulator12")

# 添加任务
asst.append_task("StartUp", ...)   # 回到主界面
asst.append_task("OperBox", {})    # 扫描干员
asst.start()
```

## 3. 干员数据采集（OperBox）

### 3.1 脚本

`scan_operators.py` — 干员扫描工具，位于项目根目录。

**用法**：
```powershell
cd d:\Dev\RhodeLogisticsSteward
python scan_operators.py
```

**前置条件**：
- MuMu 模拟器已启动
- 明日方舟已打开
- MAA 已安装在 `G:\Tools\MAA-v4.28.4-win-x64`
- `pip install maafw` 已完成

### 3.2 回调数据格式

MAA 通过 `SubTaskExtraInfo` 回调返回干员数据，`what` 字段为 `OperBoxInfo`（注意不是 `OperBox`）。

```json
{
  "what": "OperBoxInfo",
  "details": {
    "done": false,
    "all_opers": [
      {
        "id": "char_002_amiya",
        "name": "阿米娅",
        "own": true,
        "rarity": 5
      }
    ],
    "own_opers": [
      {
        "id": "char_1016_agoat2",
        "name": "纯烬艾雅法拉",
        "own": true,
        "elite": 2,
        "level": 90,
        "potential": 5,
        "rarity": 6
      }
    ]
  }
}
```

### 3.3 注意事项

| 问题 | 说明 | 处理方式 |
|------|------|----------|
| **回调命名** | `what` 字段为 `"OperBoxInfo"` 而非 `"OperBox"` | 兼容两种命名 |
| **数据重复** | MAA 每次回调发送**累积**数据（非增量） | 按 `id` 字段去重 |
| **页面残留** | 扫描后停留在干员列表最后一页，再次扫描会失败 | 每次扫描前先执行 `StartUp` 回到主界面 |
| **done 标志** | `done: true` 表示扫描完成 | 收到 `done: true` 后可安全停止任务 |

### 3.4 实际采集结果

| 维度 | 数据 |
|------|------|
| 总干员数 | **415** 名 |
| 6★ / 5★ / 4★ / 3★ / 2★ / 1★ | 131 / 191 / 61 / 17 / 5 / 10 |
| 精英2 / 精英1 / 未精英 | 170 / 55 / 190 |

## 4. 基建排班协议

### 4.1 MAA Infrast 任务三种模式

| 模式 | `mode` 值 | 说明 |
|------|----------|------|
| Default（默认） | `0` | MAA 内置算法，单设施最优解 |
| Custom（自定义） | `10000` | 读取 `custom_infrast/*.json`，精准换班 |
| Rotation（轮换） | `20000` | 一键轮换，跳过中枢/发电/宿舍/办公室 |

### 4.2 自定义排班 JSON 核心字段

```json
{
  "title": "方案名称",
  "plans": [{
    "name": "早班",
    "period": [["08:00", "20:00"]],
    "drones": {"room": "trading", "index": 1, "order": "pre"},
    "rooms": {
      "control":    [{"operators": ["阿米娅", "夕", "令"]}],
      "manufacture": [
        {"operators": ["野鬃", "远牙", "灰毫"], "sort": true, "product": "Battle Record"},
        {"operators": ["Castle-3"], "autofill": true},
        {"skip": true}
      ],
      "trading":    [{"operators": ["巫恋", "龙舌兰", "卡夫卡"]}],
      "power":      [{"operators": ["承曦格雷伊"]}],
      "dormitory":  [{"operators": [], "autofill": true}],
      "meeting":    [{"autofill": true}],
      "hire":       [{"operators": ["斥罪"]}],
      "processing": [{"skip": true}]
    }
  }]
}
```

### 4.3 设施名映射

| 中文 | JSON Key | MAA API Key |
|------|----------|-------------|
| 控制中枢 | `control` | `Control` |
| 制造站 | `manufacture` | `Manufacture` / `Mfg` |
| 贸易站 | `trading` | `Trading` / `Trade` |
| 发电站 | `power` | `Power` |
| 宿舍 | `dormitory` | `Dormitory` / `Dorm` |
| 会客室 | `meeting` | `Meeting` / `Reception` |
| 办公室 | `hire` | `Hire` / `Office` |
| 加工站 | `processing` | `Processing` |

### 4.4 MAA 内置排班模板

`MAA/resource/custom_infrast/` 下提供了参考模板：

| 文件 | 布局 | 换班频率 |
|------|------|----------|
| `243_layout_3_times_a_day.json` | 2贸易/4制造/3电站 | 8H 一换 |
| `243_layout_4_times_a_day.json` | 2贸易/4制造/3电站 | 6H 一换 |
| `153_layout_3_times_a_day.json` | 1贸易/5制造/3电站 | 8H 一换 |
| `153_layout_4_times_a_day.json` | 1贸易/5制造/3电站 | 6H 一换 |
| `333_layout_for_Orundum_3_times_a_day.json` | 3贸易/3制造/3电站（搓玉） | 8H 一换 |

## 5. 基建技能数据（infrast.json）

MAA 的 `resource/infrast.json`（约 191KB）包含所有干员基建技能的效率数值，按设施分类组织：

```
infrast.json
├── Control      → 控制中枢技能（心情恢复、全局加成）
├── Manufacture  → 制造站技能（作战记录/贵金属/源石碎片等效率）
├── Trading      → 贸易站技能（订单获取效率）
├── Power        → 发电站技能（无人机恢复）
├── Meeting      → 会客室技能（线索搜集）
├── Hire         → 办公室技能（人脉联络）
├── Dormitory    → 宿舍技能（心情恢复）
├── Processing   → 加工站技能（副产品概率）
└── Training     → 训练室技能（专精速度）
```

效率值示例：
```json
{
  "bskill_man_exp2": {
    "name": ["自动化·β"],
    "efficient": {
      "manufacture": 0.25,
      "trading": 0.25
    }
  }
}
```

## 6. 部署架构（推荐）

```
RhodeLogisticsSteward/
├── scan_operators.py          # 干员扫描工具（通过 MAA API）
├── steward_core/              # 核心逻辑
│   ├── operator.py            # 干员数据模型
│   ├── infrast_loader.py      # infrast.json 解析器
│   ├── efficiency.py          # 效率计算引擎
│   └── scheduler.py           # 排班求解器
├── output/                    # 生成的排班文件
│   └── custom_infrast/
│       └── generated_*.json
└── docs/
    └── maa-integration.md     # 本文档

用户环境：
  G:\Tools\MAA-v4.28.4-win-x64\   ← 用户已有的 MAA 安装
  %APPDATA%\MAA\                   ← MAA 用户数据
```

用户使用流程：
1. 运行 `scan_operators.py` → 获取干员数据
2. 运行排班求解器 → 生成 `custom_infrast/*.json`
3. 在 MAA 中设置基建为自定义模式，选择生成的排班方案
4. MAA 自动执行排班

## 7. 参考链接

| 资源 | 链接 |
|------|------|
| MAA 集成文档 | https://docs.maa.plus/zh-cn/protocol/integration.html |
| MAA 回调消息协议 | https://docs.maa.plus/zh-cn/protocol/callback-schema.html |
| MAA 基建排班协议 | https://docs.maa.plus/zh-cn/protocol/base-scheduling-schema.html |
| 可视化排班生成器 | https://ark.yituliu.cn/tools/schedule |
| MAA GitHub | https://github.com/MaaAssistantArknights/MaaAssistantArknights |
| MaaFramework | https://github.com/MaaXYZ/MaaFramework |
