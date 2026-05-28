"""SolverConfig 开关机制测试"""

import pytest


class TestSolverConfigDefaults:
    """默认构造与预设"""

    def test_默认构造_全部功能关闭(self):
        """SolverConfig() 所有开关默认 False，保持旧行为"""
        from steward_core.solver.config import SolverConfig

        config = SolverConfig()

        assert config.exclusive_support_check is False
        assert config.local_search_enabled is False
        assert config.global_state_scoring is False

    def test_baseline预设_等价于默认构造(self):
        """baseline() 返回全部关闭的配置"""
        from steward_core.solver.config import SolverConfig

        baseline = SolverConfig.baseline()
        default = SolverConfig()

        assert baseline.exclusive_support_check == default.exclusive_support_check
        assert baseline.local_search_enabled == default.local_search_enabled
        assert baseline.global_state_scoring == default.global_state_scoring

    def test_all_on预设_全部功能启用(self):
        """all_on() 启用所有可选功能"""
        from steward_core.solver.config import SolverConfig

        config = SolverConfig.all_on()

        assert config.exclusive_support_check is True
        assert config.local_search_enabled is True
        assert config.global_state_scoring is True

    def test_自定义构造_混合开关(self):
        """可以单独开启任意功能"""
        from steward_core.solver.config import SolverConfig

        config = SolverConfig(
            exclusive_support_check=True,
            local_search_enabled=False,
            global_state_scoring=True,
        )

        assert config.exclusive_support_check is True
        assert config.local_search_enabled is False
        assert config.global_state_scoring is True


class TestSolverConfigDiff:
    """差异比较"""

    def test_diff_相同配置_返回空列表(self):
        """两个相同配置 diff 为空"""
        from steward_core.solver.config import SolverConfig

        a = SolverConfig.baseline()
        b = SolverConfig.baseline()

        diffs = a.diff(b)
        assert diffs == []

    def test_diff_一个开关不同_列出差异(self):
        """diff 报告所有不同的字段"""
        from steward_core.solver.config import SolverConfig

        a = SolverConfig.baseline()
        b = SolverConfig(exclusive_support_check=True)

        diffs = a.diff(b)
        assert len(diffs) == 1
        assert "exclusive_support_check" in diffs[0]

    def test_diff_全部不同_列出所有差异(self):
        """all_on vs baseline 应列出所有开关差异"""
        from steward_core.solver.config import SolverConfig

        a = SolverConfig.baseline()
        b = SolverConfig.all_on()

        diffs = a.diff(b)
        assert len(diffs) >= 3  # 至少 3 个 boolean 字段不同

    def test_diff_对称性(self):
        """a.diff(b) 和 b.diff(a) 内容一致（方向不同但差异对称）"""
        from steward_core.solver.config import SolverConfig

        a = SolverConfig.baseline()
        b = SolverConfig.all_on()

        diffs_ab = a.diff(b)
        diffs_ba = b.diff(a)
        assert len(diffs_ab) == len(diffs_ba)


class TestSolverConfigIntegration:
    """solve_mvp 集成：config 参数传播"""

    def test_solve_mvp_接受config参数_默认不报错(self):
        """solve_mvp(operators, config=b) 不改变旧签名兼容性"""
        from steward_core.solver import solve_mvp
        from steward_core.solver.config import SolverConfig

        ops = []
        result = solve_mvp(ops, config=SolverConfig())
        assert result is not None

    def test_solve_mvp_无config参数_等价于baseline(self):
        """不传 config 等价于传 SolverConfig.baseline()"""
        from steward_core.solver import solve_mvp
        from steward_core.solver.config import SolverConfig

        ops = []
        result_no_config = solve_mvp(ops)
        result_baseline = solve_mvp(ops, config=SolverConfig.baseline())

        assert result_no_config.autofill_count == result_baseline.autofill_count

    def test_SolveResult携带所使用的config(self):
        """SolveResult 记录求解时使用的配置"""
        from steward_core.solver import solve_mvp
        from steward_core.solver.config import SolverConfig

        config = SolverConfig(exclusive_support_check=True)
        result = solve_mvp([], config=config)

        assert result.config_used is not None
        assert result.config_used.exclusive_support_check is True
