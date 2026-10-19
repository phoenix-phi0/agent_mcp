"""已完成：模块在 plan/state.json 里记了通过，且 contracts/<模块>.md 的 hash 没变 → 是，否则 否（约定变了视为未完成）。
例如 设 完成 = 已完成 graph
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 已完成(模块: str) -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    return "是" if X.ctx().is_done(模块.strip()) else "否"
