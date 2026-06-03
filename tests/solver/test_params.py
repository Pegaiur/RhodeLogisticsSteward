"""SolverParams 参数注册表测试"""

import json
import tempfile
from pathlib import Path

import pytest

from steward_core.solver.params import SolverParams


class TestSolverParamsDefaults:
    """默认构造"""

    def test_默认构造_使用预设值(self):
        """SolverParams() 所有字段为文档标注的默认值"""
        p = SolverParams()
        assert p.shift_hours == 12.0
        assert p.control_max_slots == 5
        assert p.dorm_max_operators == 20
        assert p.suich_count == 5
        assert p.combo_upper_bound_threshold == 0.95

    def test_baseline_等价于默认构造(self):
        """baseline() 返回默认参数"""
        assert SolverParams.baseline() == SolverParams()


class TestSolverParamsJSON:
    """JSON 序列化/反序列化"""

    def test_默认导出再加载_等价(self):
        """to_json → from_json 往返后参数不变"""
        p = SolverParams()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8",
        ) as f:
            p.to_json(f.name)
            path = f.name

        loaded = SolverParams.from_json(path)
        Path(path).unlink()
        assert loaded == p

    def test_部分覆盖_未提及字段保留默认(self):
        """JSON 只覆盖 shift_hours → 其他字段为默认值"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8",
        ) as f:
            json.dump({"shift_hours": 24.0}, f)
            path = f.name

        p = SolverParams.from_json(path)
        Path(path).unlink()
        assert p.shift_hours == 24.0
        assert p.control_max_slots == 5  # 未覆盖，默认值

    def test_未知字段_被忽略(self):
        """JSON 含 unknown_field → from_json 不报错，忽略"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8",
        ) as f:
            json.dump({"unknown_field": 999}, f)
            path = f.name

        p = SolverParams.from_json(path)
        Path(path).unlink()
        assert p == SolverParams()  # 完全等价于默认


class TestSolverParamsValidation:
    """validate() 参数合法性校验"""

    def test_默认参数_校验通过(self):
        """默认参数 validate 返回空列表"""
        assert SolverParams().validate() == []

    def test_负数班次_报错(self):
        """shift_hours ≤ 0 → 校验失败"""
        errors = SolverParams(shift_hours=0).validate()
        assert any("shift_hours" in e for e in errors)

    def test_中枢容量为零_报错(self):
        """control_max_slots < 1 → 校验失败"""
        errors = SolverParams(control_max_slots=0).validate()
        assert any("control_max_slots" in e for e in errors)

    def test_阈值超出范围_报错(self):
        """combo_upper_bound_threshold > 1 → 校验失败"""
        errors = SolverParams(combo_upper_bound_threshold=1.5).validate()
        assert any("combo_upper_bound_threshold" in e for e in errors)

    def test_宿舍容量小于单间_报错(self):
        """dorm_max_operators < dorm_room_size → 校验失败"""
        errors = SolverParams(dorm_max_operators=3, dorm_room_size=5).validate()
        assert any("dorm_max_operators" in e for e in errors)

    def test_from_json_非法参数_抛异常(self):
        """from_json 加载非法参数 → 校验失败抛 ValueError"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8",
        ) as f:
            json.dump({"shift_hours": -1}, f)
            path = f.name

        with pytest.raises(ValueError, match="参数校验失败"):
            SolverParams.from_json(path)
        Path(path).unlink()


class TestSolverParamsDiff:
    """diff() 差异比较"""

    def test_相同参数_diff为空(self):
        p = SolverParams()
        assert p.diff(SolverParams()) == []

    def test_一个字段不同_列出差异(self):
        a = SolverParams()
        b = SolverParams(shift_hours=24.0)
        diffs = a.diff(b)
        assert len(diffs) == 1
        assert "shift_hours" in diffs[0]
