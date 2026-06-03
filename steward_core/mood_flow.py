"""心情流转引擎 — MoodContext + MoodModifiers

统一的心情状态容器，替代分散的硬编码 bool（ling_mood_below_12 等）。
MoodModifiers 是全局心情修正器，与 BuffPool 同构：全局生成 → 不可变传递 → 逐设施消费。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from steward_core.models import Operator
    from steward_core.synergy.buff_pool import BuffPool
    from steward_core.solver.params import SolverParams


@dataclass
class RoomBurnContext:
    """房间心情消耗上下文 — 从槽位模型传递至心情引擎的数据载体

    每个工作干员一份，包含其所在房间的槽位信息和同房间干员名单，
    供 work_burn() 检测房间级 mp_cost buff（如槐琥 manu_cost_all[000]）。
    """

    room_type: str
    room_slots: int
    room_index: int
    co_workers: list[str] = field(default_factory=list)


@dataclass
class MoodModifiers:
    """全局心情修正器 — 一次计算，供所有工作/宿舍干员使用

    与 BuffPool 同构：全局生成 → 不可变传递 → 逐设施消费。
    差异：这里是速率修正（浮点），不是可消耗资源（整数）。
    """

    control_recovery: float = 0.0
    """中枢内部恢复速率（control_mp_cost 系列：每名中枢干员 +0.05/h）"""

    mlynar_spread: bool = False
    """玛恩纳公事公办：将 control_recovery 扩散至工作设施"""

    global_work_recovery: float = 0.0
    """工作设施全局恢复（玛恩纳直接提供 +0.1/h）"""

    yanhuo_recovery: float = 0.0
    """重岳孤光共照：+0.05 + 烟火÷20×0.05/h"""

    wisdel_recovery: float = 0.0
    """维什戴尔巴别塔之帜：工作设施干员 +0.1/h 恢复。
    与重岳 yanhuo_recovery 取 max（特殊比较规则：同类型中枢全局 buff 不叠加）。"""

    dorm_bonus_all: float = 0.0
    """中枢→宿舍恢复加成，适用全体宿舍干员（control_dorm_rec[000]~[002]、control_dorm_rec2[000]）"""

    dorm_bonus_elite: float = 0.0
    """中枢→宿舍恢复加成，仅适用精英干员（control_dorm_rec_tag[001] 阿斯卡纶）"""

    def dorm_bonus_for(self, op: "Operator") -> float:
        """根据干员类型返回适用的宿舍恢复加成"""
        bonus = self.dorm_bonus_all
        if op.rarity >= 5:
            bonus = max(bonus, self.dorm_bonus_elite)
        return bonus


def compute_mood_modifiers(
    control_operators: list["Operator"],
    buff_pool: "BuffPool | None",
    *,
    control_recovery_per_op: float = 0.05,
) -> MoodModifiers:
    """从控制中枢配置计算全局心情修正器

    覆盖：control_mp_cost 系列（9条）、control_mp_lonely（1条）、
          control_dorm_rec 系列（5条）、重岳孤光共照。
    未覆盖：Per-operator 恢复（菲亚梅塔/塑心/车尔尼）— 由 evaluate_dorm_recovery() 处理。
    """
    mods = MoodModifiers()
    names = {op.name for op in control_operators}

    mods.control_recovery = len(control_operators) * control_recovery_per_op

    if any(
        s.buff_id == "control_mp_lonely[000]"
        for op in control_operators
        for s in op.skills
    ):
        mods.mlynar_spread = True
        mods.global_work_recovery = 0.1

    if "重岳" in names and buff_pool is not None:
        mods.yanhuo_recovery = 0.05 + (buff_pool.yanhuo // 20) * 0.05

    if any(
        s.buff_id == "control_mp_expand_double[000]"
        for op in control_operators
        for s in op.skills
    ):
        mods.wisdel_recovery = 0.1

    mods.dorm_bonus_all, mods.dorm_bonus_elite = _extract_dorm_ctrl_bonuses(control_operators)

    return mods


def _extract_dorm_ctrl_bonuses(
    ctrl_ops: list,
) -> tuple[float, float]:
    """扫描中枢干员 skills 提取 dorm_bonus_all / dorm_bonus_elite

    从 compute_mood_modifiers 和 _dorm_contribution 共用，
    消除两处独立维护 control_dorm_rec* 扫描逻辑的信息泄露。
    不涉及 yanhuo_bonus——两处 yanhuo 来源不同（BuffPool vs 状态快照）。
    """
    dorm_bonus_all = 0.0
    dorm_bonus_elite = 0.0
    for op in ctrl_ops:
        for s in op.skills:
            if s.buff_id.startswith("control_dorm_rec_tag"):
                val = s.efficient.max_value()
                if val > dorm_bonus_elite:
                    dorm_bonus_elite = val
            elif s.buff_id.startswith("control_dorm_rec"):
                val = s.efficient.max_value()
                if val > dorm_bonus_all:
                    dorm_bonus_all = val
    return dorm_bonus_all, dorm_bonus_elite


def compute_global_burn(
    control_operators: list["Operator"],
    buff_pool: "BuffPool",
    worker_count: int = 3,
    *,
    base_burn_per_hour: float = 1.0,
    control_recovery_per_op: float = 0.05,
) -> float:
    """计算工作干员的心情消耗率净值 (mood_burn)

    迁移自 synergy/mood.py，保留原接口以兼容存量调用方。
    最终将被 MoodContext.work_burn() 替代。
    """
    base = base_burn_per_hour - control_recovery_per_op * max(0, worker_count - 1)

    modifiers = compute_mood_modifiers(
        control_operators, buff_pool, control_recovery_per_op=control_recovery_per_op,
    )
    recovery = modifiers.control_recovery + max(modifiers.yanhuo_recovery, modifiers.wisdel_recovery)
    if modifiers.mlynar_spread:
        recovery += modifiers.control_recovery + modifiers.global_work_recovery
    return max(0.0, base - recovery)


# ─── 房间级 mp_cost buff 修正表 ──────────────────────────────────

_MP_COST_ROOM_ZERO: set[str] = {
    "manu_cost_all[000]",
}
"""持有者在场时，同房间全员心情消耗归零（如槐琥 团队精神）"""

_MP_COST_ROOM_REDUCE: dict[str, float] = {
    "manu_cost[000]": 0.1,
    "trade_cost[000]": 0.1,
    "trade_ord_vodfox[000]": -0.25,
}
"""持有者在场时，同房间全员心情消耗减少（buff_id → 减免量/h）。

同房间多个持有者叠加生效（如两人各持 manu_cost[000] 则全房 -0.2/h）。
"""


_MP_COST_FACTION_ZERO: dict[str, str] = {
    "control_facCostReset[000]": "sui",
}
"""持有者在场时，同房间符合阵营的干员心情消耗归零（buff_id → group_id）。
如令 杯莫停 消除中枢内所有岁干员心情消耗。
"""

# ─── 自身 mp_cost buff 映射表 ──────────────────────────────────

_SELF_MP_COST: dict[str, float] = {
    # === MANUFACTURE (26) ===
    "manu_prod_limit&cost[000]": -0.25,       # 清道夫 拾荒者
    "manu_prod_limit&cost[0000]": -0.25,      # 红云 拾荒者
    "manu_prod_limit&cost[001]": -0.25,       # 豆苗 磐蟹·阿盘
    "manu_prod_limit&cost[002]": -0.25,       # 刻俄柏 "都想要"
    "manu_prod_limit&cost[003]": -0.25,       # 帕拉斯 智慧之境
    "manu_prod_limit&cost[010]": -0.25,       # 泡泡 囤积者
    "manu_prod_limit&cost[011]": -0.25,       # 娜仁图亚 无畏豪情
    "manu_prod_limit&cost[012]": -0.25,       # Miss.Christine 午休好去处
    "manu_prod_limit&cost[020]": -0.25,       # 石棉 探险者
    "manu_prod_limit&cost[1020]": -0.25,      # 钼铅 收纳达人
    "manu_formula_cost[000]": -0.25,          # 卡达 Vlog
    "manu_prod_spd&limit&cost[000]": -0.15,   # 火神 工匠精神·α
    "manu_prod_spd&limit&cost[001]": -0.25,   # 火神 工匠精神·β
    "manu_prod_spd&limit&cost[010]": 0.25,    # 泡普卡 麻烦制造者
    "manu_prod_spd&limit&cost[011]": 0.25,    # 石棉 特立独行
    "manu_prod_spd&limit&cost[020]": -0.25,   # 贝娜 "可靠"助手
    "manu_prod_spd&limit&cost[100]": 0.25,    # 裁度 量体裁衣
    "manu_prod_spd&limit&cost[101]": 0.25,    # 雪猎 虔信
    "manu_prod_spd&limit&cost[110]": 0.25,    # 雪猎 独当一面
    "manu_prod_limit&cost[021]": -0.25,       # 洋灰 掘进工程
    "manu_formula_spd&limit&cost[000]": -0.25,  # 酒神 镜中影
    "manu_formula_spd&limit&cost[010]": -0.25,  # 酒神 戏中人
    "manu_formula_spd&limit&cost[100]": 0.25,   # 裂响 "连轴转"
    "manu_formula_spd&cost[000]": 0.25,         # 杏仁 小奇思
    "manu_formula_spd&cost[001]": 0.25,         # 阿罗玛 净味香氛
    "manu_formula_spd&cost_bd[000]": -0.15,     # 杏仁 挑大梁
    # === POWER (2) ===
    "power_rec_spd&cost[000]": -0.52,        # THRM-EX 热情澎湃
    "power_rec_spd&cost[010]": -0.3,         # 空构 外卖水果挞
    # === TRADING (11) ===
    "trade_ord_spd&cost[000]": -0.25,        # 古米/空爆/月见夜 交际
    "trade_ord_limit&cost[000]": -0.25,      # 桃金娘/史都华德/暗索 谈判
    "trade_ord_wt&cost[000]": -0.25,         # 柏喙/巫恋/贝娜/明椒 裁缝·α
    "trade_ord_wt&cost[010]": -0.25,         # 柏喙/明椒 裁缝·β
    "trade_ord_wt&cost[001]": -0.25,         # 卡夫卡 手工艺品·α
    "trade_ord_wt&cost[011]": -0.25,         # 卡夫卡 手工艺品·β
    "trade_ord_wt&cost[002]": -0.25,         # 折光 鉴定师的眼光
    "trade_ord_wt&cost[012]": -0.25,         # 折光 鉴定师的手段
    "trade_ord_wt&cost[003]": -0.25,         # 渡桥 懂行
    "trade_ord_long[000]": -0.25,            # 龙舌兰 投资·α
    "trade_ord_long[010]": -0.25,            # 龙舌兰 投资·β
    # === HIRE (13) ===
    "hire_spd_cost[200]": 2.0,               # 地灵 准时下班
    "hire_spd_cost[210]": 0.5,               # 斥罪 法为正典
    "hire_spd_cost[220]": 1.0,              # 水灯心 永不停歇·α
    "hire_spd_cost[230]": 1.0,              # 水灯心 永不停歇·β
    "hire_spd_cost[100]": -0.25,             # 桑葚 救援队·珠算
    "hire_spd_cost[110]": -0.25,             # 桑葚 救援队·资源清点
    "hire_spd_cost[111]": -0.25,             # 林 特殊渠道
    "hire_spd_cost[101]": -0.25,             # 深律 宫廷礼仪
    "hire_spd_cost[120]": -0.25,             # 深律 威权谕使
    "hire_spd_cost[112]": -0.25,             # 行箸 踏坊寻味·α
    "hire_spd_cost[121]": -0.25,             # 行箸 踏坊寻味·β
    "hire_spd_cost&char[000]": -0.25,        # 圣聆初雪 圣女声望
    "hire_spd_cost&char[001]": -0.25,        # 圣聆初雪 雪境归心
    # === MEETING (5) ===
    "meet_spd&sami[000]": 0.5,              # 提丰 冰原游弋
    "meet_spd&sami[100]": 0.5,              # 寻澜 人情练达
    "meet_spd&bd[000]": 0.5,                # 凛视 远见
    "meet_spd&bd[010]": 0.5,                # 凛视 未来之途
    "meet_spd&cost[100]": 2.0,              # 见行者 逻辑推理
    # === CONTROL (8) ===
    "control_bd_spd[000]": 0.5,             # 涤火杰西卡 老友相聚
    "control_meeting_bd[000]": 0.5,          # 怒潮凛冬 "是，团长！"
    "control_mp_cost&bd2[000]": 0.5,         # 夕 "不以己悲"
    "control_mp_cost&bd_up[000]": 0.5,       # 重岳 知我为我
    "control_mp_cost&bd2[010]": 0.5,         # 麒麟R夜刀 耐力回复
    "control_clue_cost&faction[990]": 0.25,  # 艾拉 反抗者
    "control_mp&meet_spd[000]": 0.05,        # 祐天寺若麦 成效优先
    "control_mp_cost_reset[000]": 0.0,       # 若叶睦 互为半身（mp_cost 归零标记）
}
"""干员自身 mp_cost buff → 心情消耗修正量（delta/h）。

正值 = 消耗增加（如阿罗玛 +0.25）, 负值 = 消耗减少（如泡泡 -0.25）。
覆盖: Mfg(26) + Power(2) + Trade(11) + Hire(13) + Meeting(5) + Control(8) = 65 条。
暂缓: P1 条件配对 (20条) + P2 CONTROL 条件型 (7条) + P3 MEETING 条件型 (7条)。
"""
# ─── TODO: 未建模的 mp_cost buff（按优先级） ──────────────────────
# 以下 buff 尚未接入，待后续版本实现。
# 格式: buff_id [ROOM]: 修正量/h  干员名  技能名
#
# === P1: 动态条件 + 条件配对 (20 条) ===
# HIRE 动态条件:
#   "hire_spd_cost&clue[000]": -0.1/h  雪绒  救援队·保证体力  (动态: 每招募位 -0.1)
# TRADING 动态条件 buff:
#   "trade_cost&bd2[000]" [ROOM]: -0.1/h  铎铃  跋山涉水  (动态: 每10烟火额外 -0.01)
#   "trade_cost&bd2[001]" [ROOM]: -0.1/h  铎铃  万里传书  (动态: 每10烟火额外 -0.02)
# TRADING 同僚条件配对 (_P 后缀, 需 co_worker 检测):
#   "trade_ord_spd&cost_P[000]": +0.3/h  德克萨斯  恩怨  (条件: 拉普兰德同房)
#   "trade_ord_limit&cost_P[020]": -0.1/h  贝洛内  未偿还的债务  (条件: 伺夜同房)
#   "trade_ord_limit&cost_P[010]": -0.3/h  德克萨斯  默契  (条件: 能天使同房)
#   "trade_ord_limit&cost_P[000]": -0.1/h  拉普兰德  醉翁之意·α  (条件: 德克萨斯同房)
#   "trade_ord_limit&cost_P[001]": -0.1/h  拉普兰德  醉翁之意·β  (条件: 德克萨斯同房)
#
# === P2: CONTROL 条件型 buff (7 条) ===
#   "control_meeting&mp_cost[000]": +0.02/h  摆渡人  英雄的骄傲·α  (条件: 萨尔贡干员同中枢)
#   "control_meeting&mp_cost[100]": +0.02/h  摆渡人  英雄的骄傲·β  (条件: 萨尔贡干员同中枢)
#   "control_clue_cost[000]" [ROOM]: +1.5/h  阿  神经质  (ROOM 级, 需中枢 room 表)
#   "control_clue_cost[010]" [ROOM]: +0.5/h  惊蛰  至察  (ROOM 级, 需中枢 room 表)
#   "control_mp_cost&bd3[000]": +0.05/h  丰川祥子  生活的重压  (动态: 热情值>=40)
#   "control_mp_aegir1[000]": ±0.5/h  歌蕾蒂娅  潮汐守望  (双向条件: 深海猎人在宿舍外/内)
#   "control_mp_bd&trade[000]": +0.01/h  若叶睦  演技的怪物  (动态: 每8热情值 +0.01)
#
# === P3: MEETING 条件型 buff (7 条) ===
#   "meet_spd&cost_condChar[000]": +2.0/h  和弦  双面间谍  (条件: solo)
#   "meet_spd&cost_condChar[001]": +1.0/h  霍尔海雅,奥达  "职业操守"·α  (条件: solo)
#   "meet_spd&cost_condChar[011]": +1.0/h  霍尔海雅,奥达  "职业操守"·β  (条件: solo)
#   "meet_spd&cost_condChar[020]": +1.0/h  复奏  专业经理·α  (条件: solo)
#   "meet_spd&cost_condChar[021]": +1.0/h  复奏  专业经理·β  (条件: solo)
#   "meet_spd&condChar_mustget[000]": 0.0/h  霍尔海雅  文献学顾问  (mp_cost=0, 无影响)
#   "meet_spd&condChar_mustget[100]": 0.0/h  奥达  暗线  (mp_cost=0, 无影响)


def _compute_self_mp_cost(
    op_name: str,
    op_lookup: dict[str, "Operator"],
) -> float:
    """计算干员自身技能的 mp_cost 总和修正量

    扫描干员所有 skill，累加 _SELF_MP_COST 表中的修正值。
    多条技能叠加生效（如精英化前后的不同 buff）。

    已知限制：对升级型技能（如火神 manu_prod_spd&limit&cost[000]→[001]）
    会 double-count mp_cost（应为 -0.25 却得 -0.40）。
    裁缝 trade_ord_wt&cost 则恰好正确（α+β 在游戏中叠加，不同于效率计算）。
    正确修复需 per-prefix 豁免机制（类似 _extract_tailor_level），
    偏离量仅 0.15-0.25，排班影响边际，暂缓处理。
    """
    op = op_lookup.get(op_name)
    if op is None:
        return 0.0
    total = 0.0
    for sk in op.skills:
        total += _SELF_MP_COST.get(sk.buff_id, 0.0)
    return total


def _apply_mp_cost(
    burn: float,
    op_name: str,
    co_workers: list[str],
    op_lookup: dict[str, "Operator"],
    *,
    self_cost_delta: float = 0.0,
) -> float:
    """应用同房间干员的 mp_cost buff 修正

    扫描 co_workers 中每个人的 skills，依次匹配 _MP_COST_ROOM_ZERO、
    _MP_COST_FACTION_ZERO、_MP_COST_ROOM_REDUCE 表。

    self_cost_delta 是干员自身技能的 mp_cost 修正量，用于消除 buff（槐琥/令）
    精确还原——消除仅作用于自身技能效果，不影响全局减免和房间级减免。
    """
    op = op_lookup.get(op_name)
    for cw_name in co_workers:
        cw_op = op_lookup.get(cw_name)
        if cw_op is None:
            continue
        for sk in cw_op.skills:
            if sk.buff_id in _MP_COST_ROOM_ZERO:
                burn = max(0.0, burn - self_cost_delta)
                continue
            if sk.buff_id in _MP_COST_FACTION_ZERO:
                if op is not None and op.group_id == _MP_COST_FACTION_ZERO[sk.buff_id]:
                    burn = max(0.0, burn - self_cost_delta)
                    continue
            if sk.buff_id in _MP_COST_ROOM_REDUCE:
                burn = max(0.0, burn - _MP_COST_ROOM_REDUCE[sk.buff_id])
    return burn


@dataclass
class MoodContext:
    """统一的心情状态上下文，替代所有分散的硬编码 bool

    所有需要心情感知的函数从本结构读取，不再接受散列的心情 bool 参数。
    不可变操作：after_shift() 返回新实例，适合 K-Beam 分叉。
    """

    operator_moods: dict[str, float] = field(default_factory=dict)
    """干员名 → 当前心情值 (0.0 ~ 24.0)"""

    modifiers: MoodModifiers | None = None
    """全局心情修正器（惰性计算或显式设置）"""

    warmup_hours: dict[str, float] = field(default_factory=dict)
    """干员名 → 已连续工作小时数（离开工位归零，菲亚梅塔交换后保持）"""

    fiammetta_swap_planned: bool = False
    """求解器已规划菲亚梅塔交换（用于输出层 Fiammetta.enable）"""

    fiammetta_target: str = ""
    """菲亚梅塔交换目标干员名（用于输出层 Fiammetta.target）"""

    control_operators: list[str] = field(default_factory=list)
    """中枢干员名列表（用于计算全局减免）"""

    dorm_assignments: dict[str, str] | None = None
    """宿舍分配: {干员名 → 宿舍编号}。None 表示宿舍尚未分配"""

    shift_hours: float = 12.0
    """当前班次时长"""

    params: "SolverParams | None" = None
    """求解器参数（用于读取心情阈值等配置）"""

    _op_lookup: dict[str, "Operator"] = field(default_factory=dict, repr=False)
    """干员名 → Operator 对象（内置查找表，供 ensure_modifiers 解析 skills）"""

    @classmethod
    def fresh(
        cls,
        operators: list["Operator"],
        params: "SolverParams | None" = None,
    ) -> "MoodContext":
        """从全量干员池构造初始心情上下文（所有干员满心情 24.0）"""
        return cls(
            operator_moods={op.name: 24.0 for op in operators},
            warmup_hours={},
            params=params,
            _op_lookup={op.name: op for op in operators},
        )

    def mood_of(self, name: str) -> float:
        """获取干员心情值，未记录则返回满值"""
        return self.operator_moods.get(name, 24.0)

    def is_below(self, name: str, threshold: float = 12.0) -> bool:
        """心情是否低于阈值"""
        return self.mood_of(name) < threshold

    def _resolve_control_operators(self) -> list["Operator"]:
        """将 control_operators 名列表解析为 Operator 对象列表

        优先使用 _op_lookup，缺失时构造伪对象（仅含 name，无 skills）。
        调用方应确保在 fresh() 时注入 _op_lookup 以获得完整的 modifiers 计算。
        """
        from steward_core.models import Operator as OpModel

        result = []
        for name in self.control_operators:
            op = self._op_lookup.get(name)
            if op is None:
                op = OpModel(char_id="", name=name)
            result.append(op)
        return result

    def ensure_modifiers(self, buff_pool: "BuffPool | None" = None) -> MoodModifiers:
        """惰性初始化全局心情修正器

        首次调用时从 control_operators + _op_lookup 计算并缓存到 self.modifiers。
        需要 _op_lookup 已填充（通过 fresh() 或显式设置），
        否则玛恩纳扩散/dorm_bonus 检测无法生效（伪 Operator 无 skills）。
        """
        if self.modifiers is not None:
            return self.modifiers
        ops = self._resolve_control_operators()
        recovery_per_op = self.params.control_recovery_per_op if self.params else 0.05
        object.__setattr__(self, "modifiers", compute_mood_modifiers(
            ops, buff_pool, control_recovery_per_op=recovery_per_op,
        ))
        return self.modifiers

    def work_burn(
        self,
        name: str,
        room_type: str,
        room_slots: int = 3,
        buff_pool: "BuffPool | None" = None,
        *,
        co_workers: list[str] | None = None,
    ) -> float:
        """计算单干员工作消耗率净值 (mood_burn)

        公式: base - recovery_modifiers
          base = base_burn_per_hour - control_recovery_per_op × (room_slots - 1)
          recovery = control_recovery + max(yanhuo_recovery, wisdel_recovery) + (mlynar spread)

        co_workers 为同房间干员名列表，用于检测房间级 mp_cost buff
        （槐琥 manu_cost_all[000] 消除全房间消耗等）。
        为 None 时跳过检测。
        """
        burn_per_hour = self.params.base_burn_per_hour if self.params else 1.0
        recovery_per_op = self.params.control_recovery_per_op if self.params else 0.05
        base = burn_per_hour - recovery_per_op * max(0, room_slots - 1)
        modifiers = self.ensure_modifiers(buff_pool)
        recovery = modifiers.control_recovery + max(modifiers.yanhuo_recovery, modifiers.wisdel_recovery)
        if modifiers.mlynar_spread:
            recovery += modifiers.control_recovery + modifiers.global_work_recovery
        burn = max(0.0, base - recovery)

        self_cost_delta = _compute_self_mp_cost(name, self._op_lookup)
        burn = max(0.0, burn + self_cost_delta)

        if co_workers:
            burn = _apply_mp_cost(
                burn, name, co_workers, self._op_lookup,
                self_cost_delta=self_cost_delta,
            )

        return burn

    def room_burn(
        self,
        operators: list["Operator"],
        room_type: str,
        buff_pool: "BuffPool | None" = None,
    ) -> float:
        """计算房间内工作干员的平均净消耗率（供 evaluate_room 使用）

        取所有干员 work_burn 的最大值（最差者决定截断时点）。
        """
        if not operators:
            return 0.0
        slots = len(operators)
        return max(
            self.work_burn(op.name, room_type, slots, buff_pool)
            for op in operators
        )

    def dorm_recovery(
        self,
        name: str,
        dorm_mates: list["Operator"] | None = None,
    ) -> float:
        """计算干员在宿舍中的恢复速率 (mood_recovery/h)

        当 dorm_assignments 已设置时从内部查询同宿舍干员；
        当 dorm_assignments=None 时使用传入的 dorm_mates（评估候选配置）。
        委托给 evaluate_dorm_recovery() 独立函数执行实际计算。
        """
        from steward_core.dorm_recovery import evaluate_dorm_recovery
        from steward_core.models import Operator as OpModel

        op = self._op_lookup.get(name)
        if op is None:
            op = OpModel(char_id="", name=name)

        if dorm_mates is None and self.dorm_assignments is not None:
            target_dorm = self.dorm_assignments.get(name)
            if target_dorm is not None:
                dorm_mates = [
                    self._op_lookup[n] for n, d in self.dorm_assignments.items()
                    if d == target_dorm and n in self._op_lookup
                ]
            else:
                dorm_mates = [op]

        if dorm_mates is None:
            dorm_mates = [op]

        modifiers = self.ensure_modifiers()
        yanhuo_bonus = 0.0
        if self.modifiers and self.modifiers.yanhuo_recovery > 0.0:
            yanhuo_bonus = max(0.0, self.modifiers.yanhuo_recovery - 0.05)

        dorm_level = self.params.dorm_level if self.params else 5
        amb_per_room = self.params.dorm_ambiance_per_room if self.params else 5000

        return evaluate_dorm_recovery(
            dorm_ops=dorm_mates,
            target_op=op,
            dorm_bonus_all=modifiers.dorm_bonus_all,
            dorm_bonus_elite=modifiers.dorm_bonus_elite,
            yanhuo_bonus=yanhuo_bonus,
            dorm_level=dorm_level,
            dorm_ambiance_per_room=amb_per_room,
        )

    def _control_burn(self, name: str = "") -> float:
        """计算控制中枢干员的心情消耗率净值 (mood_burn/h)

        公式：base - control_recovery - yanhuo_recovery。
        mlynar_spread 不纳入——玛恩纳扩散效果是将 control_recovery
        传播至其他设施，中枢干员本身已在控制中枢内天然享受减免。

        name 不为空时，应用同中枢干员的 mp_cost buff（如令杯莫停消除岁干员消耗）。
        """
        control_count = len(self.control_operators)
        if control_count < 1:
            control_count = 5
        burn_per_hour = self.params.base_burn_per_hour if self.params else 1.0
        recovery_per_op = self.params.control_recovery_per_op if self.params else 0.05
        base = burn_per_hour - recovery_per_op * max(0, control_count - 1)
        modifiers = self.ensure_modifiers()
        burn = max(0.0, base - modifiers.control_recovery - modifiers.yanhuo_recovery)

        self_cost_delta = _compute_self_mp_cost(name, self._op_lookup)
        burn = max(0.0, burn + self_cost_delta)

        if name and self.control_operators:
            burn = _apply_mp_cost(
                burn, name, list(self.control_operators), self._op_lookup,
                self_cost_delta=self_cost_delta,
            )

        return burn

    def after_shift(
        self,
        working_names: set[str],
        shift_hours_override: float | None = None,
        *,
        working_slots: dict[str, "RoomBurnContext"] | None = None,
    ) -> "MoodContext":
        """应用一个班次后的心情变化（不可变，返回新实例）

        working_names: 本班次工作的干员名集合（含中枢干员）
        shift_hours_override: 覆盖默认班次时长（用于测试/自定义班次）
        working_slots: 干员名 → RoomBurnContext，用于计算正确的 burn 率
                       （含同房间干员名单，供 mp_cost buff 检测）。
                       未提供时回退到 3 工位 Mfg（历史兼容）。

        工作设施干员按 work_burn 消耗，中枢干员按 _control_burn 消耗。
        """
        hours = shift_hours_override if shift_hours_override is not None else self.shift_hours
        new_moods = dict(self.operator_moods)
        new_warmup = dict(self.warmup_hours)

        default_ctx = RoomBurnContext(room_type="Mfg", room_slots=3, room_index=0)

        for name in self.operator_moods:
            if name in working_names:
                if name in self.control_operators:
                    burn = self._control_burn(name)
                else:
                    rbc = (working_slots or {}).get(name, default_ctx)
                    burn = self.work_burn(
                        name, rbc.room_type, rbc.room_slots,
                        co_workers=rbc.co_workers,
                    )
                new_moods[name] = max(0.0, new_moods[name] - burn * hours)
                new_warmup[name] = self.warmup_hours.get(name, 0.0) + hours
            else:
                new_warmup.pop(name, None)

        return replace(
            self,
            operator_moods=new_moods,
            warmup_hours=new_warmup,
        )

    def qianhuai_decay_basis(
        self,
        operators: list["Operator"],
        room_type: str,
        buff_pool: "BuffPool | None" = None,
    ) -> float | None:
        """返回铅踝梯级衰减的初始心情值（供 stepped_efficiency 使用）

        仅在房间内有铅踝时返回非 None。
        """
        names = {op.name for op in operators}
        if "铅踝" not in names:
            return None
        return self.mood_of("铅踝")
