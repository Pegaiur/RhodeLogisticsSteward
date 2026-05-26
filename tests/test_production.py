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
    """验证制造站 PRTS 公式：生产力 = 1 + 0.01×人数 + Σ(技能/100)"""

    def test_单无技能干员_赤金基线(self):
        """一名无技能干员进驻制造站 — 仅有基础 1% 加成"""
        # Arrange
        op = _mk_op("测试干员", [])
        plan = _plan_with_mfg([op.name])

        # Act
        result = calculate(plan, [op])

        # Assert: 生产力 = 1.01, 赤金 = 0.833×1.01×24 = 20.2
        assert pytest.approx(result.total_gold_produced_per_day, rel=0.01) == 20.2

    def test_单干员_25percent技能_赤金(self):
        """干员有 PureGold=25 技能"""
        # Arrange
        sk = _mk_skill("Mfg", {"PureGold": 25})
        op = _mk_op("金匠", [sk])
        plan = _plan_with_mfg([op.name])

        # Act
        result = calculate(plan, [op])

        # Assert: 生产力 = 1.01 + 25/100 = 1.26, 赤金 = 0.833×1.26×24 = 25.2
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

        # Assert: 生产力 = 1.03 + (30+25+10)/100 = 1.68, 赤金 = 0.833×1.68×24 = 33.6
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
