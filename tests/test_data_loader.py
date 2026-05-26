"""数据加载器单元测试 (data_loader.py 重写)

全部测试通过内存构造 character_identity + buffs_infrastructure，不依赖磁盘文件。
遵循 TDD 3A 模式 (Arrange → Act → Assert)。
"""

import json
from pathlib import Path

import pytest

from steward_core.data_loader import load_operators_v2


def _write_json(tmp_path: Path, name: str, data: dict) -> Path:
    """将内存数据写入临时 JSON 文件"""
    file_path = tmp_path / name
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return file_path


# ─── 基础加载 ────────────────────────────────────────────────────

class TestBasicLoading:
    """MV0-3: 从新数据源正确加载干员"""

    def test_加载单干员_含基本身份信息(self, tmp_path):
        """character_identity 的单干员 → 一个 Operator 对象"""
        # Arrange
        ci = {
            "char_003_kalts": {
                "name": "凯尔希",
                "rarity": 5,
                "nationId": "rhodes",
                "groupId": None,
                "teamId": None,
                "skills": [],
            }
        }
        bi = {}
        ci_path = _write_json(tmp_path, "character_identity.json", ci)
        bi_path = _write_json(tmp_path, "buffs_infrastructure.json", bi)

        # Act
        ops = load_operators_v2(ci_path, bi_path)

        # Assert
        assert len(ops) == 1
        op = ops[0]
        assert op.char_id == "char_003_kalts"
        assert op.name == "凯尔希"
        assert op.rarity == 5
        assert op.nation_id == "rhodes"
        assert op.group_id is None
        assert op.team_id is None

    def test_加载干员_含阵营信息(self, tmp_path):
        """groupId 和 teamId 正确映射到 group_id / team_id"""
        # Arrange
        ci = {
            "char_010_chen": {
                "name": "陈",
                "rarity": 5,
                "nationId": "lungmen",
                "groupId": "lgd",
                "teamId": "action4",
                "skills": [],
            }
        }
        bi = {}
        ci_path = _write_json(tmp_path, "character_identity.json", ci)
        bi_path = _write_json(tmp_path, "buffs_infrastructure.json", bi)

        # Act
        ops = load_operators_v2(ci_path, bi_path)

        # Assert
        op = ops[0]
        assert op.nation_id == "lungmen"
        assert op.group_id == "lgd"
        assert op.team_id == "action4"


# ─── 技能解析 ────────────────────────────────────────────────────

class TestSkillParsing:
    """MV0-3: 技能从 buffs_infrastructure 正确解析效率值"""

    def test_单制造站技能_效率值正确(self, tmp_path):
        """技能 efficiency=30, roomType=MANUFACTURE → 解析后 skill.efficient=30"""
        # Arrange
        ci = {
            "char_test": {
                "name": "测试工",
                "rarity": 3,
                "nationId": "rhodes",
                "groupId": None,
                "teamId": None,
                "skills": [
                    {"buffId": "manu_prod_spd[000]", "roomType": "MANUFACTURE", "phase": 0}
                ],
            }
        }
        bi = {
            "manu_prod_spd[000]": {
                "buffName": "标准化·α",
                "roomType": "MANUFACTURE",
                "description": "进驻制造站时，生产力+15%",
                "efficiency": 15,
            }
        }
        ci_path = _write_json(tmp_path, "character_identity.json", ci)
        bi_path = _write_json(tmp_path, "buffs_infrastructure.json", bi)

        # Act
        ops = load_operators_v2(ci_path, bi_path)

        # Assert
        assert len(ops) == 1
        op = ops[0]
        assert len(op.skills) == 1
        sk = op.skills[0]
        assert sk.buff_id == "manu_prod_spd[000]"
        assert sk.buff_name == "标准化·α"
        assert sk.room_type == "Mfg"
        assert sk.phase == 0
        # 效率值从 buffs_infrastructure 的 efficiency 字段直接读取
        assert sk.efficient.get("PureGold") == 15.0  # all=15

    def test_无制造站技能的干员_跳过该技能(self, tmp_path):
        """干员只有 WORKSHOP 技能 → 不加载（排班不涉及）"""
        # Arrange
        ci = {
            "char_test": {
                "name": "工匠",
                "rarity": 3,
                "nationId": "rhodes",
                "groupId": None,
                "teamId": None,
                "skills": [
                    {"buffId": "workshop_x", "roomType": "WORKSHOP", "phase": 0}
                ],
            }
        }
        bi = {
            "workshop_x": {
                "buffName": "加工",
                "roomType": "WORKSHOP",
                "description": "加工站技能",
                "efficiency": 10,
            }
        }
        ci_path = _write_json(tmp_path, "character_identity.json", ci)
        bi_path = _write_json(tmp_path, "buffs_infrastructure.json", bi)

        # Act
        ops = load_operators_v2(ci_path, bi_path)

        # Assert: 干员存在但无技能（WORKSHOP 被过滤）
        assert len(ops) == 1
        assert len(ops[0].skills) == 0

    def test_多技能干员_逐一解析(self, tmp_path):
        """干员有多个基建技能（Mfg + Trade + Control），全部正确解析"""
        # Arrange
        ci = {
            "char_test": {
                "name": "多面手",
                "rarity": 5,
                "nationId": "rhodes",
                "groupId": None,
                "teamId": None,
                "skills": [
                    {"buffId": "manu_a", "roomType": "MANUFACTURE", "phase": 0},
                    {"buffId": "trade_a", "roomType": "TRADING", "phase": 2},
                    {"buffId": "ctrl_a", "roomType": "CONTROL", "phase": 0},
                ],
            }
        }
        bi = {
            "manu_a": {"buffName": "制造技能", "roomType": "MANUFACTURE", "description": "生产力+20%", "efficiency": 20},
            "trade_a": {"buffName": "贸易技能", "roomType": "TRADING", "description": "订单效率+30%", "efficiency": 30},
            "ctrl_a": {"buffName": "中枢技能", "roomType": "CONTROL", "description": "心情恢复", "efficiency": 0},
        }
        ci_path = _write_json(tmp_path, "character_identity.json", ci)
        bi_path = _write_json(tmp_path, "buffs_infrastructure.json", bi)

        # Act
        ops = load_operators_v2(ci_path, bi_path)

        # Assert
        assert len(ops[0].skills) == 3
        rooms = {s.room_type for s in ops[0].skills}
        assert rooms == {"Mfg", "Trade", "Control"}


# ─── 产物匹配 ────────────────────────────────────────────────────

class TestProductMatching:
    """MV0-3: 根据 description 文本判定产物匹配"""

    def test_作战记录技能_产物匹配(self, tmp_path):
        """description 含"作战记录" → 判定为 CombatRecord 产物"""
        # Arrange
        ci = {
            "char_test": {
                "name": "教官",
                "rarity": 4,
                "nationId": "rhodes",
                "groupId": None,
                "teamId": None,
                "skills": [
                    {"buffId": "manu_rec", "roomType": "MANUFACTURE", "phase": 0}
                ],
            }
        }
        bi = {
            "manu_rec": {
                "buffName": "作战指导录像",
                "roomType": "MANUFACTURE",
                "description": "进驻制造站时，作战记录类配方的生产力+30%",
                "efficiency": 30,
            }
        }
        ci_path = _write_json(tmp_path, "character_identity.json", ci)
        bi_path = _write_json(tmp_path, "buffs_infrastructure.json", bi)

        # Act
        ops = load_operators_v2(ci_path, bi_path)

        # Assert: 作战记录专属技能，CombatRecord=30，PureGold=-999
        sk = ops[0].skills[0]
        assert sk.efficient.get("CombatRecord") == 30.0
        assert sk.efficient.get("PureGold") == -999.0

    def test_贵金属技能_产物匹配(self, tmp_path):
        """description 含"贵金属" → 判定为 PureGold 产物"""
        # Arrange
        ci = {
            "char_test": {
                "name": "金匠",
                "rarity": 4,
                "nationId": "rhodes",
                "groupId": None,
                "teamId": None,
                "skills": [
                    {"buffId": "manu_gold", "roomType": "MANUFACTURE", "phase": 0}
                ],
            }
        }
        bi = {
            "manu_gold": {
                "buffName": "贵金属工艺",
                "roomType": "MANUFACTURE",
                "description": "进驻制造站时，贵金属类配方的生产力+25%",
                "efficiency": 25,
            }
        }
        ci_path = _write_json(tmp_path, "character_identity.json", ci)
        bi_path = _write_json(tmp_path, "buffs_infrastructure.json", bi)

        # Act
        ops = load_operators_v2(ci_path, bi_path)

        # Assert
        sk = ops[0].skills[0]
        assert sk.efficient.get("PureGold") == 25.0
        assert sk.efficient.get("CombatRecord") == -999.0

    def test_通用技能_双产物均可用(self, tmp_path):
        """description 不含作战记录/贵金属 → 通用技能，双产物均返回效率值"""
        # Arrange
        ci = {
            "char_test": {
                "name": "万能工",
                "rarity": 4,
                "nationId": "rhodes",
                "groupId": None,
                "teamId": None,
                "skills": [
                    {"buffId": "manu_all", "roomType": "MANUFACTURE", "phase": 0}
                ],
            }
        }
        bi = {
            "manu_all": {
                "buffName": "标准化·β",
                "roomType": "MANUFACTURE",
                "description": "进驻制造站时，生产力+25%",
                "efficiency": 25,
            }
        }
        ci_path = _write_json(tmp_path, "character_identity.json", ci)
        bi_path = _write_json(tmp_path, "buffs_infrastructure.json", bi)

        # Act
        ops = load_operators_v2(ci_path, bi_path)

        # Assert: 通用技能 → all=25, CR和PG 都通过 all 获取
        sk = ops[0].skills[0]
        assert sk.efficient.get("CombatRecord") == 25.0
        assert sk.efficient.get("PureGold") == 25.0


# ─── 边界与异常 ──────────────────────────────────────────────────

class TestEdgeCases:
    """MV0-3: 边界场景"""

    def test_空数据_不崩溃(self, tmp_path):
        """空 character_identity → 返回空列表"""
        # Arrange
        ci_path = _write_json(tmp_path, "character_identity.json", {})
        bi_path = _write_json(tmp_path, "buffs_infrastructure.json", {})

        # Act
        ops = load_operators_v2(ci_path, bi_path)

        # Assert
        assert ops == []

    def test_buff不存在_跳过该技能(self, tmp_path):
        """技能引用的 buffId 不在 buffs_infrastructure 中 → 跳过"""
        # Arrange
        ci = {
            "char_test": {
                "name": "缺数据",
                "rarity": 3,
                "nationId": "rhodes",
                "groupId": None,
                "teamId": None,
                "skills": [
                    {"buffId": "ghost_buff", "roomType": "MANUFACTURE", "phase": 0}
                ],
            }
        }
        ci_path = _write_json(tmp_path, "character_identity.json", ci)
        bi_path = _write_json(tmp_path, "buffs_infrastructure.json", {})

        # Act
        ops = load_operators_v2(ci_path, bi_path)

        # Assert: 干员存在但技能为空
        assert len(ops) == 1
        assert len(ops[0].skills) == 0

    def test_TRAINING技能_被过滤(self, tmp_path):
        """训练室技能不参与排班 → 不加载"""
        # Arrange
        ci = {
            "char_test": {
                "name": "教官",
                "rarity": 4,
                "nationId": "rhodes",
                "groupId": None,
                "teamId": None,
                "skills": [
                    {"buffId": "train_x", "roomType": "TRAINING", "phase": 0}
                ],
            }
        }
        bi = {
            "train_x": {
                "buffName": "训练",
                "roomType": "TRAINING",
                "description": "训练室技能",
                "efficiency": 10,
            }
        }
        ci_path = _write_json(tmp_path, "character_identity.json", ci)
        bi_path = _write_json(tmp_path, "buffs_infrastructure.json", bi)

        # Act
        ops = load_operators_v2(ci_path, bi_path)

        # Assert
        assert len(ops) == 1
        assert len(ops[0].skills) == 0
