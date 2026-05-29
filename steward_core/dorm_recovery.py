"""宿舍心情恢复速率评估

聚合 DORMITORY 类型 buff（约 83 条中的 ~35 条有效率值）计算目标干员的恢复速率。
"""

from steward_core.models import Operator


def evaluate_dorm_recovery(
    dorm_ops: list[Operator],
    target_op: Operator,
    dorm_bonus_all: float = 0.0,
    dorm_bonus_elite: float = 0.0,
    yanhuo_bonus: float = 0.0,
) -> float:
    """评估目标干员在给定宿舍中的心情恢复速率（/h）

    Args:
        dorm_ops: 宿舍内全部干员（含 target_op）
        target_op: 被评估恢复速率的目标干员
        dorm_bonus_all: 中枢→宿舍全员恢复加成
        dorm_bonus_elite: 中枢→宿舍精英恢复加成
        yanhuo_bonus: 人间烟火联动加成 (+0.05/20烟火)

    Returns:
        每小时心情恢复量

    聚合规则（按优先级）：
    1. 菲亚梅塔自律 (dorm_recExcludeOther): +2.0/h，隔离外部加成
    2. 自身恢复 (dorm_rec_oneself* / dorm_rec_*&oneself*): 取 max
    3. 单体恢复 (dorm_rec_single*): 同宿舍其他干员提供，取 max
    4. 全体恢复 (dorm_rec_all*): 同宿舍其他干员提供，累加
    5. 中枢全局宿舍加成: 按干员类型适用（全员/精英）
    6. 人间烟火联动: yanhuo_bonus
    """
    # Rule 1: 菲亚梅塔自律 — 固定 +2.0/h，隔离外部加成
    for sk in target_op.skills:
        if sk.room_type == "DORMITORY" and sk.buff_id.startswith("dorm_recExcludeOther"):
            return 2.0

    total = 0.0

    # Rule 2: 自身恢复技能（含 dorm_rec_oneself* / dorm_rec_*&oneself*）
    self_max = 0.0
    for sk in target_op.skills:
        if sk.room_type == "DORMITORY" and "oneself" in sk.buff_id:
            eff = _get_effective_dorm_value(sk)
            if eff > self_max:
                self_max = eff
    total += self_max

    # Peer buffs from other operators
    other_ops = [op for op in dorm_ops if op.name != target_op.name]

    # Rule 3: 单体恢复 — 同宿舍其他干员提供，取 max
    single_max = 0.0
    for op in other_ops:
        for sk in op.skills:
            if sk.room_type == "DORMITORY" and sk.buff_id.startswith("dorm_rec_single"):
                eff = _get_effective_dorm_value(sk)
                if eff > single_max:
                    single_max = eff
    total += single_max

    # Rule 4: 全体恢复 — 同宿舍其他干员提供，累加
    for op in other_ops:
        for sk in op.skills:
            if sk.room_type == "DORMITORY" and sk.buff_id.startswith("dorm_rec_all"):
                total += _get_effective_dorm_value(sk)

    # Rule 5: 中枢全局宿舍加成 — 按干员类型区分
    total += dorm_bonus_all
    if target_op.rarity >= 5:
        total += dorm_bonus_elite

    # Rule 6: 人间烟火联动
    total += yanhuo_bonus

    return total


def _get_effective_dorm_value(skill) -> float:
    """获取 DORM 技能的有效恢复值

    取 skill.efficient 中所有产品值的最大值。
    efficient.max_value() 可能返回 -999.0（哨兵值），此时跳过。
    """
    val = skill.efficient.max_value()
    return max(0.0, val)
