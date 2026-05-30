"""槽位迭代测试共享 fixtures"""

import pytest
from steward_core.models import RoomAssignment, LayoutConfig


@pytest.fixture
def layout_243():
    return LayoutConfig.layout_243()


@pytest.fixture
def empty_assignments():
    return []


@pytest.fixture
def sample_operators():
    """小型测试干员池：含中枢 buff 生成者 + Mfg/Trade 消费者"""
    ops = [
        make_op("令", "ling", "Control", buff_id="control_mood[001]"),
        make_op("夕", "xi", "Control", buff_id="control_mood[002]"),
        make_op("重岳", "chongyue", "Control", buff_id="control_mood[003]"),
        make_op("迷迭香", "rosmontis", "Mfg", buff_id="manu_prod_buff", efficiency=0.0),
        make_op("黍", "shu", "Mfg", buff_id="manu_prod_buff[001]", efficiency=0.0),
        make_op("普通制造", "mfg_001", "Mfg", efficiency=25.0, product="CombatRecord"),
        make_op("普通赤金", "pg_001", "Mfg", efficiency=20.0, product="PureGold"),
        make_op("普通贸易", "trade_001", "Trade", efficiency=30.0, product="Money"),
    ]
    return ops
