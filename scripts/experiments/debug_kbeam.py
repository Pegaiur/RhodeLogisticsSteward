"""调试 K-Beam 路径数量问题"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tests.strategy_helpers import make_op
from steward_core.solver import solve_mvp
from steward_core.solver.config import SolverConfig
from steward_core.solver.strategies import KBeamStrategy
from steward_core.synergy import classify_mfg_operators, build_candidate_pool
from steward_core.solver.greed import _generate_combos, _greedy_allocate_with_support

ops = []
for i in range(6):
    ops.append(make_op(f"cr_{i}", f"cr_{i}", "Mfg", efficiency=25.0, product="CombatRecord"))
for i in range(6):
    ops.append(make_op(f"pg_{i}", f"pg_{i}", "Mfg", efficiency=25.0, product="PureGold"))
for i in range(6):
    ops.append(make_op(f"trade_{i}", f"trade_{i}", "Trade", efficiency=30.0, product="Money"))
for i in range(5):
    ops.append(make_op(f"ctrl_{i}", f"ctrl_{i}", "Control", efficiency=0.0))
for i in range(3):
    ops.append(make_op(f"power_{i}", f"power_{i}", "Power", efficiency=20.0))
for i in range(2):
    ops.append(make_op(f"rec_{i}", f"rec_{i}", "Reception", efficiency=25.0))
ops.append(make_op("off_0", "off_0", "Office", efficiency=0.0))

# Debug CR allocation
cr_ops = [op for op in ops if op.has_skill_for("Mfg", "CombatRecord")]
print(f"CR operators: {[op.name for op in cr_ops]}")
classification = classify_mfg_operators(cr_ops, "CombatRecord", set())
pool = build_candidate_pool(cr_ops, classification, room_type="Mfg", product="CombatRecord")
print(f"CR pool: {[op.name for op in pool]}")
combos = _generate_combos(pool, 3)
print(f"CR combos count: {len(combos)}")
print(f"CR combo[0]: {[op.name for op in combos[0]]}")
print(f"CR combo[-1]: {[op.name for op in combos[-1]]}")

# Build simple evaluated list for test
from steward_core.solver.support import _evaluate_with_support
evaluated = []
for combo_ops in combos:
    score, support_map = _evaluate_with_support(
        combo_ops, "Mfg", "CombatRecord", ops, set(),
        params=None,
    )
    combo_names = [op.name for op in combo_ops]
    all_support_names = []
    evaluated.append((score, combo_names, all_support_names, support_map))
evaluated.sort(key=lambda x: -x[0])
print(f"CR evaluated: {len(evaluated)} combos")
print(f"CR top score: {evaluated[0][0]:.1f} names: {evaluated[0][1]}")
print(f"CR last score: {evaluated[-1][0]:.1f} names: {evaluated[-1][1]}")

# Try greedy allocation
result = _greedy_allocate_with_support(evaluated, room_count=2)
print(f"CR allocated rooms: {len(result)}")
for names, sm in result:
    print(f"  room: {names}")
