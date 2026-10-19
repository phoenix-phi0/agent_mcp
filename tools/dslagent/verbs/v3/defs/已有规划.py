"""已有规划：项目里已存的规划文本（顶层 → plan/top.zs，约定 → contracts/<模块>.md），没有返回空串。续跑用。
例如 设 旧 = 已有规划 约定 graph
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 已有规划(种类: str, 模块: str = "") -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import planning as PL
    try:
        return PL.existing(X.ctx(), 种类, 模块)
    except ValueError as e:
        X.fail(e)
