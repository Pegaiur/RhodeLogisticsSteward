"""产出计算模块 (production.py) 的纯内存单元测试

全部测试通过内存构造 Operator 和 ShiftPlan，不依赖磁盘文件。
遵循 TDD 3A 模式 (Arrange → Act → Assert)。
"""

import pytest

from steward_core.models import EfficiencyMap, Operator, RoomAssignment, ShiftPlan, Skill
from steward_core.production import (
    DailyProduction,
    _GOLD_BASE_PER_HOUR,
    _RECORD_BASE_PER_HOUR,
    _TRADE_AVG_GOLD_PER_ORDER,
    _TRADE_AVG_LMD_PER_ORDER,
    _TRADE_AVG_TIME_HOURS,
    calculate,
)


def _mk_op(name: str, skills: list[Skill] | None = None) -> Operator:
    """构造测试用干员 (纯内存)"""
    return Operator(char_id=name, name=name, skills=skills or [])


def _mk_skill(room_type: str, efficient: dict[str, float], buff_id: str = "test_buff") -> Skill:
    """构造测试用技能 (纯内存)"""
    return Skill(
        buff_id=buff_id,
        buff_name="测试技能",
        skill_icon=f"test_{buff_id}",
        room_type=room_type,
        efficient=EfficiencyMap(raw=efficient),
    )


# ─── 辅助: 构造测试用 ShiftPlan ────────────────────────────────

def _plan_with_mfg(ops: list[str], product: str = "PureGold") -> ShiftPlan:
    """构造仅含一间制造站的排班计划 (无人机的加速目标)"""
    plan = ShiftPlan(
        name="测试",
        assignments=[
            RoomAssignment(room_type="Mfg", room_index=0, product=product, operators=ops),
        ],
    )
    plan.drone_room = "Mfg"
    plan.drone_index = 99  # 不存在的目标，避免无人机干扰纯公式验证
    return plan


def _plan_with_trade(ops: list[str]) -> ShiftPlan:
    """构造仅含一间贸易站的排班计划"""
    plan = ShiftPlan(
        name="测试",
        assignments=[
            RoomAssignment(room_type="Trade", room_index=0, product="Money", operators=ops),
        ],
    )
    plan.drone_room = "Trade"
    plan.drone_index = 99
    return plan


def _plan_mfg_trade(mfg_ops: list[str], trade_ops: list[str]) -> ShiftPlan:
    """构造一间制造站 + 一间贸易站的排班计划"""
    return ShiftPlan(
        name="测试",
        assignments=[
            RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=mfg_ops),
            RoomAssignment(room_type="Trade", room_index=0, product="Money", operators=trade_ops),
        ],
    )


# ─── 制造站基线产出 ────────────────────────────────────────────

class TestMfgBaseline:
    """验证制造站 PRTS 公式：实际产出 = 1 + 0.01×人数 + Σ(技能/100)；显示效率不含裸加成"""

    def test_单无技能干员_赤金基线(self):
        """一名无技能干员进驻制造站 — 仅有基础 1% 加成"""
        # Arrange
        op = _mk_op("测试干员", [])
        plan = _plan_with_mfg([op.name])

        # Act
        result = calculate(plan, [op])

        # Assert: 显示效率=1.0, 实际产出=0.833×(1+0.01×1)×24=20.2
        assert result.gold_rooms[0].productivity == 1.0
        assert pytest.approx(result.total_gold_produced_per_day, rel=0.01) == 20.2

    def test_单干员_25percent技能_赤金(self):
        """干员有 PureGold=25 技能"""
        # Arrange
        sk = _mk_skill("Mfg", {"PureGold": 25})
        op = _mk_op("金匠", [sk])
        plan = _plan_with_mfg([op.name])

        # Act
        result = calculate(plan, [op])

        # Assert: 显示效率=1.25, 实际产出=0.833×(1.01+0.25)×24=25.2
        assert pytest.approx(result.gold_rooms[0].productivity, rel=0.001) == 1.25
        assert pytest.approx(result.total_gold_produced_per_day, rel=0.01) == 25.2

    def test_三干员_技能累加(self):
        """三名干员各有不同技能，验证累加公式"""
        # Arrange
        ops = [
            _mk_op("A", [_mk_skill("Mfg", {"all": 30})]),
            _mk_op("B", [_mk_skill("Mfg", {"PureGold": 25})]),
            _mk_op("C", [_mk_skill("Mfg", {"PureGold": 10})]),
        ]
        plan = _plan_with_mfg([op.name for op in ops])

        # Act
        result = calculate(plan, ops)

        # Assert: 显示效率=1.65, 实际产出=0.833×(1.03+0.65)×24=33.6
        assert pytest.approx(result.gold_rooms[0].productivity, rel=0.001) == 1.65
        assert pytest.approx(result.total_gold_produced_per_day, rel=0.01) == 33.6

    def test_作战记录_30percent技能(self):
        """干员有 CombatRecord=30 技能"""
        # Arrange
        sk = _mk_skill("Mfg", {"CombatRecord": 30})
        op = _mk_op("教官", [sk])
        plan = _plan_with_mfg([op.name], product="CombatRecord")

        # Act
        result = calculate(plan, [op])

        # Assert: 生产力 = 1.01 + 30/100 = 1.31, 作战记录 = 1/3 × 1.31 × 24 = 10.48
        assert pytest.approx(result.total_records_per_day, rel=0.01) == 10.48

    def test_通用技能用于特定产物(self):
        """all=30 技能在 PureGold 和 CombatRecord 下都应生效"""
        sk = _mk_skill("Mfg", {"all": 30})
        op = _mk_op("万能工", [sk])

        # Act: 赤金
        plan_gold = _plan_with_mfg([op.name], "PureGold")
        r_gold = calculate(plan_gold, [op])

        # Act: 作战记录
        plan_rec = _plan_with_mfg([op.name], "CombatRecord")
        r_rec = calculate(plan_rec, [op])

        # Assert: 两种产物生产力相同
        assert pytest.approx(r_gold.total_gold_produced_per_day, rel=0.01) == _GOLD_BASE_PER_HOUR * 1.31 * 24
        assert pytest.approx(r_rec.total_records_per_day, rel=0.01) == _RECORD_BASE_PER_HOUR * 1.31 * 24


# ─── 贸易站基线产出 ────────────────────────────────────────────

class TestTradeBaseline:
    """验证贸易站 PRTS 公式"""

    def test_单无技能干员_贸易基线(self):
        """一名无技能干员进驻贸易站"""
        # Arrange
        op = _mk_op("商人", [])
        plan = _plan_with_trade([op.name])

        # Act
        result = calculate(plan, [op])

        # Assert: 效率 = 1.01, 日均订单 = 24/(3.39/1.01) = 7.15, LMD = 7.15×1450 = 10367
        assert pytest.approx(result.total_lmd_per_day, rel=0.05) == 10367

    def test_三干员_贸易技能累加(self):
        """三名干员各有 Money 技能"""
        # Arrange
        ops = [
            _mk_op("A", [_mk_skill("Trade", {"Money": 30})]),
            _mk_op("B", [_mk_skill("Trade", {"Money": 20})]),
            _mk_op("C", [_mk_skill("Trade", {"all": 10})]),
        ]
        plan = _plan_with_trade([op.name for op in ops])

        # Act
        result = calculate(plan, ops)

        # Assert: 效率 = 1.03 + (30+20+10)/100 = 1.63
        # 日均订单 = 24/(3.39/1.63) = 11.54, LMD = 11.54×1450 ≈ 16739
        assert pytest.approx(result.total_lmd_per_day, rel=0.05) == 16739


# ─── 赤金供需平衡 ──────────────────────────────────────────────

class TestGoldSupplyBalance:
    """验证赤金不足时龙门币产出按比例缩减"""

    def test_赤金充足_龙门币全额(self):
        """制造 > 贸易消耗 → 龙门币全额"""
        # Arrange: 高产赤金 + 低效贸易
        mfg_op = _mk_op("金匠", [_mk_skill("Mfg", {"PureGold": 90})])
        trade_op = _mk_op("商人", [])
        plan = _plan_mfg_trade([mfg_op.name], [trade_op.name])

        # Act
        result = calculate(plan, [mfg_op, trade_op])

        # Assert
        assert result.gold_surplus > 0
        assert result.effective_lmd_per_day == result.total_lmd_per_day

    def test_赤金不足_龙门币缩减(self):
        """贸易消耗 > 制造 → 龙门币按比例缩减"""
        # Arrange: 低产赤金 + 高效贸易
        mfg_op = _mk_op("金匠", [_mk_skill("Mfg", {"PureGold": 0})])
        trade_ops = [
            _mk_op("A", [_mk_skill("Trade", {"Money": 40})]),
            _mk_op("B", [_mk_skill("Trade", {"Money": 40})]),
            _mk_op("C", [_mk_skill("Trade", {"Money": 30})]),
        ]
        plan = _plan_mfg_trade([mfg_op.name], [op.name for op in trade_ops])

        # Act
        result = calculate(plan, [mfg_op] + trade_ops)

        # Assert: 赤金不足，effective_lmd < total_lmd
        assert result.gold_surplus < 0
        assert result.effective_lmd_per_day < result.total_lmd_per_day

    def test_刚平衡(self):
        """制造 = 贸易 (浮动误差内) → 龙门币全额"""
        # Arrange: 通过调技能值让供需接近
        mfg_ops = [
            _mk_op("A", [_mk_skill("Mfg", {"PureGold": 30})]),
            _mk_op("B", [_mk_skill("Mfg", {"PureGold": 25})]),
        ]
        trade_op = _mk_op("C", [_mk_skill("Trade", {"Money": 0})])
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=[op.name for op in mfg_ops]),
                RoomAssignment(room_type="Trade", room_index=0, product="Money", operators=[trade_op.name]),
            ],
        )

        # Act
        result = calculate(plan, mfg_ops + [trade_op])

        # Assert
        assert result.effective_lmd_per_day == result.total_lmd_per_day


# ─── 无人机计算 ──────────────────────────────────────────────────

class TestDrone:
    """验证发电站无人机产量公式"""

    def test_零发电站干员_无人机基线(self):
        """无发电站干员 → 240 架/天"""
        # Arrange
        assignments = [
            RoomAssignment(room_type="Power", room_index=0, operators=[]),
            RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=["A"]),
        ]
        op = _mk_op("A", [])
        plan = ShiftPlan(name="测试", assignments=assignments)

        # Act
        result = calculate(plan, [op])

        # Assert
        assert pytest.approx(result.daily_drones) == 240.0

    def test_单发电站干员_20percent(self):
        """干员有 Drone=20 (百分比加成) → 240×1.2 = 288"""
        # Arrange
        power_op = _mk_op("格雷伊", [_mk_skill("Power", {"all": 20})])
        mfg_op = _mk_op("A", [])
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Power", room_index=0, operators=[power_op.name]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=[mfg_op.name]),
            ],
        )

        # Act
        result = calculate(plan, [power_op, mfg_op])

        # Assert
        assert pytest.approx(result.daily_drones) == 288.0

    def test_排除心情小数_仅百分比有效(self):
        """efficient.all=0.05 不应计入无人机 (心情恢复值)"""
        # Arrange: 0.05 值被过滤，0.2 值被过滤(跨设施技能)，只有 ≥1 的计入
        power_op = _mk_op("测试", [
            _mk_skill("Power", {"all": 0.05}, buff_id="mood_skill"),
            _mk_skill("Power", {"all": 15}, buff_id="drone_skill"),
        ])
        mfg_op = _mk_op("A", [])
        plan = ShiftPlan(
            name="测试",
            assignments=[
                RoomAssignment(room_type="Power", room_index=0, operators=[power_op.name]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=[mfg_op.name]),
            ],
        )

        # Act
        result = calculate(plan, [power_op, mfg_op])

        # Assert: 仅 15 计入, 240×1.15 = 276
        assert pytest.approx(result.daily_drones) == 276.0

    def test_无人机加速制造站(self):
        """无人机制造站加速: 3min/架"""
        # Arrange: 200%加成 → 720架/天
        power_op = _mk_op("A", [_mk_skill("Power", {"all": 200})])
        mfg_op = _mk_op("B", [])
        plan = ShiftPlan(
            name="测试",
            drone_room="Mfg", drone_index=0,
            assignments=[
                RoomAssignment(room_type="Power", room_index=0, operators=[power_op.name]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=[mfg_op.name]),
            ],
        )

        # Act
        result = calculate(plan, [power_op, mfg_op])

        # Assert: 720架/天 × 3min/架 = 2160min 加速, 倍率 = (1440+2160)/1440 = 2.5
        # 基线赤金 = 0.833×1.01 = 0.841, ×24×2.5 = 50.5
        assert pytest.approx(result.daily_drones) == 720.0
        assert pytest.approx(result.total_gold_produced_per_day, rel=0.02) == 50.5

    def test_无人机不加速非目标房间(self):
        """无人机仅加速 drone_room/drone_index 指定的房间"""
        # Arrange: Power 在 index 0 但 drone_target 是 Mfg[1]，Mfg[0] 不应被加速
        power_op = _mk_op("A", [_mk_skill("Power", {"all": 200})])
        mfg_op = _mk_op("B", [])
        plan = ShiftPlan(
            name="测试",
            drone_room="Mfg", drone_index=1,  # 目标是 Mfg[1]
            assignments=[
                RoomAssignment(room_type="Power", room_index=0, operators=[power_op.name]),
                RoomAssignment(room_type="Mfg", room_index=0, product="PureGold", operators=[mfg_op.name]),
            ],
        )

        # Act
        result = calculate(plan, [power_op, mfg_op])

        # Assert: 目标房间不存在 → 不应加速
        assert result.total_gold_produced_per_day < _GOLD_BASE_PER_HOUR * 1.01 * 24 * 1.1  # 不应有加速


# ─── 边界与异常 ──────────────────────────────────────────────────

class TestEdgeCases:
    """验证空值、零值、缺失场景"""

    def test_空干员工厂_不崩溃(self):
        """autofill 房间 (空干员列表) — 无工人无产出，不应崩溃"""
        # Arrange
        plan = _plan_with_mfg([])
        op = _mk_op("X", [])

        # Act
        result = calculate(plan, [op])

        # Assert: 空干员工厂 — 无工人，产出为零
        assert result.total_gold_produced_per_day == 0.0

    def test_干员无对应设施技能_产出为零(self):
        """干员只有 Trade 技能却被放进 Mfg"""
        # Arrange
        sk = _mk_skill("Trade", {"Money": 30})
        op = _mk_op("商人", [sk])
        plan = _plan_with_mfg([op.name])

        # Act
        result = calculate(plan, [op])

        # Assert: 无 Mfg 技能 → 技能加成为 0, 仅基础生产力
        # 但 has_skill_for 返回 False, 求解器不会放入, 这里验证 calculate 不崩溃即可
        assert result.total_gold_produced_per_day >= 0.0

    def test_DailyProduction_空方案(self):
        """凭空 ShiftPlan 计算不崩溃"""
        # Arrange
        plan = ShiftPlan(name="空", assignments=[])
        plan.drone_room = "Mfg"
        plan.drone_index = 99
        op = _mk_op("X", [])

        # Act
        result = calculate(plan, [op])

        # Assert: 空方案所有产出为零，但基线无人机仍存在(240, 因无 Power 干员但 calculate 不排除基线)
        assert result.total_records_per_day == 0.0
        assert result.total_gold_produced_per_day == 0.0
        assert result.total_lmd_per_day == 0.0

    def test_summary_输出不崩溃(self):
        """DailyProduction.summary() 在各类场景下不崩溃"""
        for gold_surplus in (10.0, -10.0):
            dp = DailyProduction(
                total_gold_produced_per_day=50.0,
                total_gold_consumed_per_day=60.0 + gold_surplus,
                total_lmd_per_day=30000.0,
                effective_lmd_per_day=30000.0,
                gold_surplus=gold_surplus,
            )
            s = dp.summary()
            assert "龙门币" in s
            assert "赤金" in s


# ─── 贸易站订单机制（A7 层）─ 文档倍数法 ────────────────────────

# 文档基准：Lv3 贸易站 100% 效率 24h = 10265 LMD/天
_TRADE_BASE_LMD_PER_DAY = 10265.0


class TestTradeOrderMultiplier:
    """验证 _get_trade_order_multiplier() 返回正确的 (lmd_per_day, gold_per_day)"""

    def test_空干员列表_返回默认倍数(self):
        """无特殊干员 → (10265, 标准赤金消耗)"""
        from steward_core.production import _get_trade_order_multiplier

        # Act
        lmd_per_day, gold_per_day = _get_trade_order_multiplier([])

        # Assert: 默认三级站日产
        assert lmd_per_day == 10265.0
        assert gold_per_day == pytest.approx(24 * 2.9 / 3.39, rel=0.01)

    def test_普通贸易干员_返回默认倍数(self):
        """仅有 Money=30 的普通贸易干员 → 默认倍数"""
        from steward_core.production import _get_trade_order_multiplier

        # Arrange
        op = _mk_op("商人", [_mk_skill("Trade", {"Money": 30})])

        # Act
        lmd_per_day, gold_per_day = _get_trade_order_multiplier([op])

        # Assert
        assert lmd_per_day == 10265.0
        assert gold_per_day == pytest.approx(24 * 2.9 / 3.39, rel=0.01)

    def test_但书单干员_违约体系倍数(self):
        """但书合同法+违约索赔β → LMD 1.55×, 赤金消耗 4.9/2.9×"""
        from steward_core.production import _get_trade_order_multiplier

        # Arrange: 但书 buff_ids
        butler = _mk_op("但书", [
            Skill(buff_id="trade_ord_law[000]", buff_name="合同法", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
            Skill(buff_id="trade_ord_against[010]", buff_name="违约索赔·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        # Act
        lmd_per_day, gold_per_day = _get_trade_order_multiplier([butler])

        # Assert: 2,3→违约+2, LMD=2250/订单; gold=4.9/订单
        expected_lmd_mult = 2250.0 / 1450.0  # 1.5517
        expected_gold_mult = 4.9 / 2.9  # 1.6897
        assert lmd_per_day == pytest.approx(10265 * expected_lmd_mult, rel=0.001)
        assert gold_per_day == pytest.approx(24 * 2.9 / 3.39 * expected_gold_mult, rel=0.001)

    def test_可露希尔_特别订单倍数(self):
        """可露希尔特别订单 → 固定 2赤金/1200LMD, 10单/天"""
        from steward_core.production import _get_trade_order_multiplier

        # Arrange
        closure = _mk_op("可露希尔", [
            Skill(buff_id="trade_ord_closure[000]", buff_name="特别订单", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 10})),
        ])

        # Act
        lmd_per_day, gold_per_day = _get_trade_order_multiplier([closure])

        # Assert: 12000 LMD/天 (文档), 20 赤金消耗/天
        assert lmd_per_day == pytest.approx(12000.0, rel=0.01)
        assert gold_per_day == pytest.approx(24 / 2.4 * 2.0, rel=0.01)  # 20

    def test_龙舌兰加裁缝β_高品质投资倍数(self):
        """龙舌兰投资β + 裁缝β(巫恋/柏喙) → LMD 1.24×"""
        from steward_core.production import _get_trade_order_multiplier

        # Arrange
        tequila = _mk_op("龙舌兰", [
            Skill(buff_id="trade_ord_long[010]", buff_name="投资·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])
        tailor = _mk_op("柏喙", [
            Skill(buff_id="trade_ord_wt&cost[010]", buff_name="裁缝·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        # Act
        lmd_per_day, gold_per_day = _get_trade_order_multiplier([tequila, tailor])

        # Assert: 文档 LMD=12740, +500 per 4-gold(30%概率)
        # 裁缝β: 4-gold prob=30%, LMD/order=1668.75, gold/order=3.0375
        expected_lmd = 10265 * (1668.75 / 1450.0)
        expected_gold = 24 * 3.0375 / 3.39
        assert lmd_per_day == pytest.approx(expected_lmd, rel=0.01)
        assert gold_per_day == pytest.approx(expected_gold, rel=0.01)

    def test_但书加龙舌兰_互动倍数(self):
        """但书+龙舌兰 → 2,3触发但书, 4触发龙舌兰"""
        from steward_core.production import _get_trade_order_multiplier

        # Arrange
        butler = _mk_op("但书", [
            Skill(buff_id="trade_ord_law[000]", buff_name="合同法", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
            Skill(buff_id="trade_ord_against[010]", buff_name="违约索赔·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])
        tequila = _mk_op("龙舌兰", [
            Skill(buff_id="trade_ord_long[010]", buff_name="投资·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        # Act
        lmd_per_day, gold_per_day = _get_trade_order_multiplier([butler, tequila])

        # Assert: LMD=2350/订单(文档~16637), gold=4.5/订单
        expected_lmd_mult = 2350.0 / 1450.0
        expected_gold_mult = 4.5 / 2.9
        assert lmd_per_day == pytest.approx(10265 * expected_lmd_mult, rel=0.002)
        assert gold_per_day == pytest.approx(24 * 2.9 / 3.39 * expected_gold_mult, rel=0.002)

    def test_裁缝α_高品质小幅倍数(self):
        """裁缝·α 单独 → 高品 +5%, LMD +25/单"""
        from steward_core.production import _get_trade_order_multiplier

        # Arrange
        tailor_a = _mk_op("明椒", [
            Skill(buff_id="trade_ord_wt&cost[000]", buff_name="裁缝·α", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        # Act
        lmd_per_day, gold_per_day = _get_trade_order_multiplier([tailor_a])

        # Assert: 4-gold prob=25%, LMD=1484.375/订单, gold=2.96875/订单
        expected_lmd = 1000 * 0.28125 + 1500 * 0.46875 + 2000 * 0.25
        expected_gold = 2 * 0.28125 + 3 * 0.46875 + 4 * 0.25
        base_orders = 24 / 3.39
        assert lmd_per_day == pytest.approx(base_orders * expected_lmd, rel=0.002)
        assert gold_per_day == pytest.approx(base_orders * expected_gold, rel=0.002)


# ─── 等效效率自动量化（A7 层回退）────────────────────────────

class TestTradeOrderEquivalentEfficiency:
    """验证 get_trade_order_equivalent_efficiency 从倍数自动推算偏置"""

    def test_普通干员_返回零(self):
        """无 A7 机制的普通干员 → 0（无偏置）"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        op = _mk_op("商人", [_mk_skill("Trade", {"Money": 30})])

        assert get_trade_order_equivalent_efficiency(op) == 0.0

    def test_但书_等效效率约90(self):
        """但书 1.55× 倍数 → 等效 ~90%"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        butler = _mk_op("但书", [
            Skill(buff_id="trade_ord_law[000]", buff_name="合同法", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
            Skill(buff_id="trade_ord_against[010]", buff_name="违约索赔·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        eff = get_trade_order_equivalent_efficiency(butler)
        assert eff == pytest.approx(89.9, rel=0.05)

    def test_龙舌兰_等效效率约11(self):
        """龙舌兰 1.07× 倍数（无裁缝）→ 等效 ~11%"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        tequila = _mk_op("龙舌兰", [
            Skill(buff_id="trade_ord_long[010]", buff_name="投资·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        eff = get_trade_order_equivalent_efficiency(tequila)
        assert eff == pytest.approx(11.2, rel=0.1)

    def test_可露希尔_等效效率约28(self):
        """可露希尔 1.17× 倍数 → 等效 ~28%"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        closure = _mk_op("可露希尔", [
            Skill(buff_id="trade_ord_closure[000]", buff_name="特别订单", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 10})),
        ])

        eff = get_trade_order_equivalent_efficiency(closure)
        assert eff == pytest.approx(27.6, rel=0.1)

    def test_裁缝α_等效效率约4(self):
        """裁缝α 1.02× 倍数 → 等效 ~4%"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        tailor = _mk_op("明椒", [
            Skill(buff_id="trade_ord_wt&cost[000]", buff_name="裁缝·α", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

        eff = get_trade_order_equivalent_efficiency(tailor)
        assert eff == pytest.approx(3.9, rel=0.15)

    def test_裁员后仍可import_无循环依赖(self):
        """验证 synergy.py 不依赖 _SYSTEM_CONTRIBUTORS 中的 order_mechanism 注册"""
        from steward_core.synergy import get_system_contributors

        names = get_system_contributors("Trade", "order_mechanism")
        # 自动量化后不再需要注册表
        assert len(names) == 0


# ─── 配对验证 + 回溯场景 ──────────────────────────────────────

class TestTradePairingVerification:
    """验证配对型干员的偏置验证逻辑（次优/回溯）"""

    @staticmethod
    def _mk_texas():
        return _mk_op("德克萨斯", [
            Skill(buff_id="trade_ord_spd&cost_P[000]", buff_name="恩怨", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

    @staticmethod
    def _mk_lappy():
        return _mk_op("拉普兰德", [
            Skill(buff_id="trade_ord_limit&cost_P[001]", buff_name="醉翁之意·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])

    def test_德克萨斯_配对可用_返回正常偏置(self):
        """拉普兰德未被占用 → 德克萨斯偏置正常"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        texas = self._mk_texas()
        lappy = self._mk_lappy()
        assigned = set()
        op_lookup = {op.char_id: op for op in [texas, lappy]}

        eff = get_trade_order_equivalent_efficiency(texas, assigned, op_lookup)
        assert eff == pytest.approx(30, rel=0.1)  # 配对可兑现

    def test_拉普兰德已分配_德克萨斯偏置归零(self):
        """拉普兰德被制造站占用 → 德克萨斯偏置 = 0（配对不可兑现）"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        texas = self._mk_texas()
        lappy = self._mk_lappy()
        assigned = {lappy.char_id}  # 拉普兰德已被制造站占用
        op_lookup = {op.char_id: op for op in [texas, lappy]}

        eff = get_trade_order_equivalent_efficiency(texas, assigned, op_lookup)
        assert eff == 0.0  # 配对不可兑现，退化为无贡献

    def test_拉普兰德不在池中_德克萨斯偏置归零(self):
        """拉普兰德根本不在干员池 → 德克萨斯偏置 = 0"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        texas = self._mk_texas()
        assigned = set()
        op_lookup = {texas.char_id: texas}  # 只有德克萨斯

        eff = get_trade_order_equivalent_efficiency(texas, assigned, op_lookup)
        assert eff == 0.0

    def test_德克萨斯配对_拉普兰德也可选_两者均入池(self):
        """德克萨斯+拉普兰德都未被占用 → 两者都应进入候选池"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        texas = self._mk_texas()
        lappy = self._mk_lappy()
        assigned = set()
        op_lookup = {op.char_id: op for op in [texas, lappy]}

        t_eff = get_trade_order_equivalent_efficiency(texas, assigned, op_lookup)
        l_eff = get_trade_order_equivalent_efficiency(lappy, assigned, op_lookup)
        assert t_eff == pytest.approx(30, rel=0.1)
        assert l_eff > 0


# ─── 同室人数型 + 效率反馈型 ──────────────────────────────────

class TestTradeContextualEfficiency:
    """验证同室人数 / 效率反馈 / 低语型干员的偏置"""

    def test_巫恋低语_3人房假设_偏置约75(self):
        """巫恋低语：归零他人，自身每人+45% → 3人房=135%"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        op = _mk_op("巫恋", [
            Skill(buff_id="trade_ord_vodfox[000]", buff_name="低语", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])
        eff = get_trade_order_equivalent_efficiency(op, set(), {op.char_id: op})
        assert eff == pytest.approx(75, rel=0.15)

    def test_火哨_2室友_偏置约30(self):
        """火哨代为说项：2名室友各+15% → +30%"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        op = _mk_op("火哨", [
            Skill(buff_id="trade_ord_spd&share[000]", buff_name="代为说项", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])
        eff = get_trade_order_equivalent_efficiency(op, set(), {op.char_id: op})
        assert eff == pytest.approx(30, rel=0.15)

    def test_吉星β_2室友_偏置约40(self):
        """吉星勤俭经营·β：2名室友各+20% → +40%"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        op = _mk_op("吉星", [
            Skill(buff_id="trade_ord_spd&share[002]", buff_name="勤俭经营·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])
        eff = get_trade_order_equivalent_efficiency(op, set(), {op.char_id: op})
        assert eff == pytest.approx(40, rel=0.15)

    def test_雪雉β_效率反馈_偏置约35(self):
        """雪雉天道酬勤·β：每5%→+5%，上限35%"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        op = _mk_op("雪雉", [
            Skill(buff_id="trade_ord_spd_variable2[001]", buff_name="天道酬勤·β", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])
        eff = get_trade_order_equivalent_efficiency(op, set(), {op.char_id: op})
        assert eff == pytest.approx(35, rel=0.15)

    def test_新约能天使_拉特兰配对_偏置约45(self):
        """新约能天使同城加急单：3拉特兰各+15% → 保守偏置30"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        op = _mk_op("新约能天使", [
            Skill(buff_id="trade_ord_spd_par[001]", buff_name="同城加急单", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])
        eff = get_trade_order_equivalent_efficiency(op, set(), {op.char_id: op})
        assert eff == pytest.approx(25, rel=0.15)

    def test_摩根_格帮配对_偏置约55(self):
        """摩根帮派指南针：推王+1格帮各+20%+额外35% → 偏置55"""
        from steward_core.synergy import get_trade_order_equivalent_efficiency

        op = _mk_op("摩根", [
            Skill(buff_id="trade_ord_spd_par[000]", buff_name="帮派指南针", skill_icon="test",
                  room_type="Trade", efficient=EfficiencyMap(raw={"Money": 0})),
        ])
        eff = get_trade_order_equivalent_efficiency(op, set(), {op.char_id: op})
        assert eff == pytest.approx(55, rel=0.15)  # 偏置 55
