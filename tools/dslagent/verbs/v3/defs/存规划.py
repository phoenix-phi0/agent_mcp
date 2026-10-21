"""存规划：把通过检查的规划文本写进项目（顶层 → plan/top.zs，约定 → contracts/<模块>.md）。返回 {path}。
例如 设 w = 存规划 约定 {文本} graph
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 存规划(种类: str, 文本: str, 模块: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import planning as PL
    c = X.ctx()
    try:
        rel = PL.save(c, 种类, 文本, 模块)
    except ValueError as e:
        X.fail(e)
    c.log("规划", 种类=种类, 模块=模块, 次=c.attempts.get((种类, 模块), 0), 事件="存", 路径=rel)
    return {"path": rel}
