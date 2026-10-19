"""标记完成：在 plan/state.json 记模块通过 + 当前约定 hash。返回 是。
例如 标记完成 graph
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 标记完成(模块: str) -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    c = X.ctx()
    try:
        c.mark_done(模块.strip())
    except ValueError as e:
        X.fail(e)
    c.log("验收", 模块=模块.strip(), 通过=True, 说明="标记完成")
    return "是"
