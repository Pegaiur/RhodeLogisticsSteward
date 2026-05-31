"""生成 P0 无条件自身 mp_cost 映射表 — 即抛脚本"""
import json
import re

with open("buffs_infrastructure.json", "r", encoding="utf-8") as f:
    bi = json.load(f)
with open("character_identity.json", "r", encoding="utf-8") as f:
    ci = json.load(f)

buff_owners = {}
for cid, cdata in ci.items():
    name = cdata.get("name", "?")
    for sk in cdata.get("skills", []):
        bid = sk.get("buffId", "")
        if bid:
            buff_owners.setdefault(bid, []).append(name)

# P0 生产设施: MANUFACTURE, TRADING, POWER
P0_ROOMS = {"MANUFACTURE", "TRADING", "POWER"}

# 已接入的房间级 buff（不在 P0 范围）
CONNECTED = {"manu_cost_all[000]", "control_facCostReset[000]", "manu_cost[000]", "trade_cost[000]"}

# 动态条件 buff（P1 范围 — 依赖运行时变量）
DYNAMIC_PATTERNS = [
    "trade_cost&bd2",       # 人间烟火联动
    "hire_spd_cost&clue",   # 招募位计数
    "_P[",                  # 同僚配对条件（德克萨斯+拉普兰德等）
]

results = []
skipped_dynamic = []
skipped_room = []
skipped_unknown_val = []
skipped_non_p0 = []

for bid, bdata in bi.items():
    desc = bdata.get("description", "")
    if "心情" not in desc:
        continue
    if "消耗" not in desc and "消除" not in desc:
        continue
    room = bdata.get("roomType", "?")
    if room not in P0_ROOMS:
        skipped_non_p0.append((bid, room))
        continue
    if bid in CONNECTED:
        continue

    # 房间级 buff 跳过（P0 仅处理自身 buff）
    if "所有干员" in desc or "全体干员" in desc or "内干员" in desc or "全体心情" in desc:
        skipped_room.append((bid, desc[:80]))
        continue

    # 动态条件跳过
    is_dynamic = False
    for pat in DYNAMIC_PATTERNS:
        if pat in bid:
            skipped_dynamic.append((bid, desc[:80]))
            is_dynamic = True
            break
    if is_dynamic:
        continue

    # 提取心情消耗值：找"心情"后最近的 <@cc.vup/down> 标签
    mood_pos = desc.find("心情")
    if mood_pos < 0:
        skipped_unknown_val.append((bid, desc[:100]))
        continue
    # 在"心情"之后搜索
    after_mood = desc[mood_pos:]
    val_match = re.search(r'<@cc\.v(up|down)>([+\-][\d.]+)</>', after_mood)
    if not val_match:
        skipped_unknown_val.append((bid, desc[:100]))
        continue

    direction = val_match.group(1)  # up=减免(负消耗), down=增加(正消耗)
    raw_val = float(val_match.group(2))
    # 统一为消耗修正: 正值=消耗增加, 负值=消耗减少
    #   <@cc.vup>-0.25 → 减免 0.25 → 消耗修正 = -0.25
    #   <@cc.vdown>+0.5 → 增加 0.5 → 消耗修正 = +0.5
    cost_delta = raw_val if direction == "down" else -abs(raw_val)

    owners = buff_owners.get(bid, [])
    results.append((bid, cost_delta, owners, room, desc[:120]))

# 输出
print("# P0 无条件自身 mp_cost 映射表")
print(f"# 生成命令: python scripts/_gen_self_mp_cost.py")
print(f"# 范围: {P0_ROOMS}")
print(f"# 总数: {len(results)}")
print()

# 按 room 分组输出
for room in sorted(P0_ROOMS):
    room_items = [(b, v, o) for b, v, o, r, d in results if r == room]
    if not room_items:
        continue
    print(f"# === {room} ===")
    for bid, cost_delta, owners in room_items:
        sign = "+" if cost_delta >= 0 else ""
        owners_str = ", ".join(owners)
        print(f'    "{bid}": {sign}{cost_delta},  # {owners_str}')

print()
print(f"# 跳过统计:")
print(f"#   动态条件: {len(skipped_dynamic)}")
for b, d in skipped_dynamic:
    print(f"#     {b}: {d}")
print(f"#   房间级: {len(skipped_room)}")
for b, d in skipped_room:
    print(f"#     {b}: {d}")
print(f"#   非P0设施: {len(skipped_non_p0)}")
print(f"#   无法提取值: {len(skipped_unknown_val)}")
for b, d in skipped_unknown_val:
    print(f"#     {b}: {d}")
