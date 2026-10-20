"""读问题清单：按路径或「最新」读一份问题清单，解析成结构化列表。返回 {"items": [...], "path": 相对路径, "count": n}。
找不到时 终止 失败。
例如 设 issues = 读问题清单 最新
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 读问题清单(问题: str = "最新") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import issues as IS
    c = X.ctx()
    try:
        items, rel = IS.load(c.project, 问题)
    except ValueError as e:
        X.fail(e)
    return {"items": items, "path": rel, "count": len(items)}
