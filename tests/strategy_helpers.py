"""策略测试辅助工具

降低新 Strategy 的测试编写成本，避免每个测试文件重复构造 Operator 和验证排班结构。
"""

from steward_core.models import Operator, Skill, EfficiencyMap, SolveResult
from steward_core.solver import solve_mvp


def make_op(
    name: str,
    char_id: str,
    room_type: str,
    *,
    efficiency: float = 0.0,
    product: str | None = None,
    buff_id: str = "",
    rarity: int = 5,
    phase: int = 2,
    nation_id: str = "test",
    group_id: str = "test",
) -> Operator:
    """快速构造测试用 Operator

    buff_id 非空时效率从 buff 表查询（需完整数据环境），
    否则使用 efficiency 参数直接指定。

    常用场景：
      make_op("温蒂", "wendy", "Mfg", buff_id="manu_prod_spd&power[020]")
        → 自动化干员，效率来自 buff 表查询

      make_op("普通制造", "mfg_001", "Mfg", efficiency=25.0, product="PureGold")
        → 纯效率干员，25% 贵金属加成

      make_op("无技能", "empty_001", "Mfg")
        → 无技能干员，仅用于填位
    """
    skills = []
    if buff_id or efficiency > 0:
        eff_raw = {}
        if product:
            eff_raw[product] = efficiency
        else:
            eff_raw["all"] = efficiency
        skills = [Skill(
            buff_id=buff_id or f"test_{char_id}",
            buff_name="",
            skill_icon="",
            room_type=room_type,
            efficient=EfficiencyMap(raw=eff_raw),
            phase=phase,
        )]
    return Operator(
        char_id=char_id,
        name=name,
        rarity=rarity,
        skills=skills,
        nation_id=nation_id,
        group_id=group_id,
    )


def make_ops(*specs: tuple) -> list[Operator]:
    """批量构造 Operator

    每个 spec 为 make_op 的位置参数元组 + 可选关键字参数字典：
      make_ops(
          ("温蒂", "wendy", "Mfg", {"buff_id": "manu_prod_spd&power[020]"}),
          ("普通", "mfg_001", "Mfg", {"efficiency": 25.0, "product": "PureGold"}),
      )
    """
    result = []
    for spec in specs:
        args = list(spec[:3])
        kwargs = spec[3] if len(spec) > 3 else {}
        result.append(make_op(*args, **kwargs))
    return result


def assert_plan_structure(result: SolveResult, expected: dict[str, int]):
    """验证 SolveResult 的房间结构

    expected 如 {"Mfg": 4, "Trade": 2, "Control": 1, "Power": 3, ...}
    """
    plan = result.plans[0]
    actual = {}
    for a in plan.assignments:
        actual[a.room_type] = actual.get(a.room_type, 0) + 1
    assert actual == expected, f"房间结构不匹配: {actual} != {expected}"


def assert_operator_in_room(result: SolveResult, room_type: str, name: str):
    """验证某干员被分配到指定房间类型"""
    plan = result.plans[0]
    for a in plan.assignments:
        if a.room_type == room_type and name in a.operators:
            return
    all_ops = {}
    for a in plan.assignments:
        for n in a.operators:
            all_ops[n] = a.room_type
    raise AssertionError(
        f"干员 {name} 不在 {room_type} 中"
        + (f"，实际在 {all_ops.get(name, '未分配')}" if name in all_ops else "")
    )


def assert_no_duplicate_operators(result: SolveResult):
    """验证全方案无重复干员（H2 约束）"""
    plan = result.plans[0]
    seen = {}
    for a in plan.assignments:
        for name in a.operators:
            if name in seen:
                raise AssertionError(
                    f"干员 {name} 重复出现在 {seen[name]} 和 {a.room_type}"
                )
            seen[name] = a.room_type


def strategy_runner(strategy_class, operators: list[Operator], **strategy_kwargs):
    """一键跑策略：构造 SolverConfig → 注入 Strategy → 执行 solve_mvp

    strategy_kwargs 传递给 strategy_class 构造器（如 beam_width=5）。
    """
    from steward_core.solver.config import SolverConfig
    strategy = strategy_class(**strategy_kwargs)
    config = SolverConfig(strategy=strategy)
    return solve_mvp(operators, config=config)
