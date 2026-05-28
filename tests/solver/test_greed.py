"""贪心分配正确性测试

测试 _greedy_allocate 跨间贪心分配逻辑。
"""


class TestGreedyAllocation:
    """制造站跨间贪心分配"""

    def test_无冲突_直接取前N(self):
        """两间房无冲突 → 直接取前2组合"""
        from steward_core.solver import _greedy_allocate

        # Arrange: 三个独立组合，互不冲突
        combos = [
            (100.0, ["A", "B", "C"]),
            (90.0, ["D", "E", "F"]),
            (80.0, ["G", "H", "I"]),
        ]

        # Act
        result = _greedy_allocate(combos, room_count=2)

        # Assert
        assert len(result) == 2
        assert result[0] == ["A", "B", "C"]
        assert result[1] == ["D", "E", "F"]

    def test_有冲突_跳过选下一个(self):
        """组合1和2共享D → 跳过组合2选组合3"""
        from steward_core.solver import _greedy_allocate

        # Arrange
        combos = [
            (100.0, ["A", "B", "C"]),
            (90.0, ["C", "D", "E"]),   # 冲突: C 已被占
            (85.0, ["F", "G", "H"]),   # 无冲突
        ]

        # Act
        result = _greedy_allocate(combos, room_count=2)

        # Assert: 第二间跳到组合3
        assert len(result) == 2
        assert result[0] == ["A", "B", "C"]
        assert result[1] == ["F", "G", "H"]

    def test_候选不足_提前终止(self):
        """仅1个组合可用 → 只分配1间"""
        from steward_core.solver import _greedy_allocate

        # Arrange
        combos = [(100.0, ["A", "B", "C"])]

        # Act
        result = _greedy_allocate(combos, room_count=2)

        # Assert
        assert len(result) == 1
