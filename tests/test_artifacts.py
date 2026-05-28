"""硬编码数据一致性测试"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _run_derive() -> dict:
    from scripts.derive import (
        _derive_mfg_anchors,
        _derive_trade_anchors,
        _derive_name_sets,
    )
    return {
        "MFG_ANCHORS": _derive_mfg_anchors(),
        "TRADE_ANCHORS": _derive_trade_anchors(),
        "name_sets": _derive_name_sets(),
    }


def test_mfg_anchors_up_to_date():
    from steward_core.synergy._derived import MFG_ANCHORS
    expected = _run_derive()["MFG_ANCHORS"]
    missing = expected - MFG_ANCHORS
    extra = MFG_ANCHORS - expected
    assert not missing, (
        f"MFG_ANCHORS 已过期，请运行 python scripts/derive.py\n"
        f"  缺失: {sorted(missing)}"
    )
    assert not extra, (
        f"MFG_ANCHORS 含多余条目，请运行 python scripts/derive.py\n"
        f"  多余: {sorted(extra)}"
    )


def test_trade_anchors_up_to_date():
    from steward_core.synergy._derived import TRADE_ANCHORS
    expected = _run_derive()["TRADE_ANCHORS"]
    missing = expected - TRADE_ANCHORS
    extra = TRADE_ANCHORS - expected
    assert not missing, (
        f"TRADE_ANCHORS 已过期，请运行 python scripts/derive.py\n"
        f"  缺失: {sorted(missing)}"
    )
    assert not extra, (
        f"TRADE_ANCHORS 含多余条目，请运行 python scripts/derive.py\n"
        f"  多余: {sorted(extra)}"
    )


def test_name_sets_up_to_date():
    from steward_core.synergy._derived import (
        KNIGHT_NAMES, DURIN_NAMES, OP_PLATFORM_NAMES,
        MH_NAMES, LUNG_MEN_GUARD_NAMES,
    )
    derived = _run_derive()["name_sets"]
    current = {
        "KNIGHT_NAMES": KNIGHT_NAMES,
        "DURIN_NAMES": DURIN_NAMES,
        "OP_PLATFORM_NAMES": OP_PLATFORM_NAMES,
        "MH_NAMES": MH_NAMES,
        "LUNG_MEN_GUARD_NAMES": LUNG_MEN_GUARD_NAMES,
    }
    for var_name in derived:
        missing = derived[var_name] - current[var_name]
        extra = current[var_name] - derived[var_name]
        assert not missing, (
            f"{var_name} 已过期，请运行 python scripts/derive.py\n"
            f"  缺失: {sorted(missing)}"
        )
        assert not extra, (
            f"{var_name} 含多余条目，请运行 python scripts/derive.py\n"
            f"  多余: {sorted(extra)}"
        )
