"""存问题清单：把 核查 的结果（{count, items}）存成 plan/issues/<序号>.md，序号接着上一份往后编。返回存盘的相对路径（字符串）。
例如 设 path = 存问题清单 {g}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 存问题清单(g: dict) -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import issues as IS
    c = X.ctx()
    items = g.get("items") if isinstance(g, dict) else []
    rel = IS.save(c.project, items or [])
    c.log("核查", 事件="存问题清单", 路径=rel, 条数=len(items or []))
    return rel
