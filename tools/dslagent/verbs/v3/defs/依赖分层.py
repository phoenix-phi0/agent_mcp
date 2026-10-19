"""依赖分层：按 plan/top.zs 把模块分层（第 0 层没有依赖，之后每层的依赖都在更低层）。返回列表，每项是一层，模块名逗号连起来，如 ["graph", "vocab,progress", "tutor"]。
例如 遍历 组 于 {层} … 结束
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 依赖分层() -> list:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import planning as PL, top as VT
    try:
        return [",".join(layer) for layer in VT.layers(PL.current_top(X.ctx()))]
    except ValueError as e:
        X.fail(e)
