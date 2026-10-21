"""取修改说明：读最新一份 plan/changes/*.json 里该模块的记录，渲染成修改说明（修改需求 / 本模块计划条目与问题 / 新旧约定差异 / 范围规则）。
没有这个模块的记录返回空串。
例如 设 说明 = 取修改说明 vocab
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 取修改说明(模块: str) -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import modify as MD
    return MD.explanation(X.ctx().project, 模块.strip())
