"""方案A对比测试 v2 —— 含调试点"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from steward_core.data_loader import load_operators_v2
from steward_core.evaluate import evaluate_room
from steward_core.production import _get_trade_order_multiplier


def lmd_12h(ops, hours=12.0):
    n = len(ops)
    eff_int = evaluate_room(ops, "Trade", "Money", power_count=3,
                            T=hours, global_bonus=None, buff_pool=None)
    efficiency_integrated = hours * (1.0 + 0.01 * n) + eff_int / 100.0
    lmd_per_day, _, _ = _get_trade_order_multiplier(ops)
    return efficiency_integrated / 24.0 * lmd_per_day


def greedy_marginal(candidates, slots=3, hours=12.0):
    taken = []
    remaining = list(candidates)
    for _ in range(slots):
        best_op, best_val = None, -1.0
        for op in remaining:
            test_room = taken + [op]
            val = lmd_12h(test_room, hours)
            if val > best_val:
                best_val = val
                best_op = op
        if best_op is None:
            break
        taken.append(best_op)
        remaining.remove(best_op)
    return taken, lmd_12h(taken, hours) if taken else 0.0


def main():
    all_ops = load_operators_v2(
        Path("character_identity.json"),
        Path("buffs_infrastructure.json"),
    )
    trade_ops = [op for op in all_ops if op.has_skill_for("Trade", "Money")]

    a7_names = {"但书", "龙舌兰", "巫恋", "柏喙", "卡夫卡", "可露希尔"}
    for op in all_ops:
        if op.name in a7_names and op not in trade_ops:
            lmd_per_day, _, _ = _get_trade_order_multiplier([op])
            if lmd_per_day > 10265.0:
                trade_ops.append(op)

    pool_names = {
        "但书", "龙舌兰", "巫恋", "柏喙", "卡夫卡", "可露希尔",
        "能天使", "海蒂", "维娜·维多利亚", "空弦",
    }
    pool = [op for op in trade_ops if op.name in pool_names]

    # 调试: 打印每个人的偏置
    print("─── 个人偏置排行 ───")
    ranked = []
    for op in pool:
        lmd, _, _ = _get_trade_order_multiplier([op])
        a7 = (lmd / 10265.0 - 1.0) * 100  # LMD倍数→等效效率
        be = op.best_efficiency("Trade", "Money")
        eff = be if be > 0 else a7
        ranked.append((eff, a7, be, op))
    ranked.sort(key=lambda x: -x[0])
    for eff, a7, be, op in ranked:
        print(f"  {op.name:<8} bias={eff:>5.0f}  (a7={a7:>5.0f}, best_eff={be:>5.0f})")
    print()

    # 当前贪心
    taken_cur = []
    seen = set()
    for _, _, _, op in ranked:
        if op.char_id in seen:
            continue
        taken_cur.append(op.name)
        seen.add(op.char_id)
        if len(taken_cur) >= 3:
            break
    print(f"[当前] 个人偏置 top3: {taken_cur}")

    taken_cur_ops = [op for op in pool if op.name in taken_cur]
    lmd_cur = lmd_12h(taken_cur_ops)
    print(f"       12h LMD = {lmd_cur:.0f}")

    # 方案A
    taken_a_ops, lmd_a = greedy_marginal(pool)
    print(f"[方案A] 边际LMD: {[op.name for op in taken_a_ops]}")
    print(f"       12h LMD = {lmd_a:.0f}")
    print(f"       差异: {lmd_a - lmd_cur:+.0f} LMD/12h  ({(lmd_a/lmd_cur - 1)*100:+.1f}%)")

    # 基线验证
    print("\n─── 参考基线对照 ───")
    refs = {
        ("但书",): "但书-3级站 15929",
        ("龙舌兰", "柏喙", "巫恋"): "龙舌兰+裁缝β 12740",
        ("但书", "龙舌兰"): "但书+龙舌兰 16637",
        ("可露希尔",): "可露希尔 12000",
    }
    for names, label in refs.items():
        combo = [op for op in pool if op.name in names]
        if len(combo) != len(names):
            continue
        lpd, _, _ = _get_trade_order_multiplier(combo)
        print(f"  {label:<25} → 代码={lpd:.1f}")


if __name__ == "__main__":
    main()
