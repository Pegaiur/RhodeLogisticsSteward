---
alwaysApply: false
globs: steward_core/synergy/*.py,character_identity.json
---

# 硬编码数据维护

修改协同表或干员数据后，运行生成脚本并提交产出：

```bash
python scripts/derive.py
```

产出 `steward_core/synergy/_derived.py`（锚点表 + 名称集合），提交时一并加入。

CI 通过 `tests/test_artifacts.py` 检查 `_derived.py` 是否与源码一致。
