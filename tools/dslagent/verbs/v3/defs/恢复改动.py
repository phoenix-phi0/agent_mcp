"""恢复改动：把这份修改计划里 改文件 已经改过、还没验收通过的文件恢复成改之前的原文（修改.zs 在执行计划失败时调用）。
返回 {restored: 恢复的文件数}。没有改过任何文件就是 0。
例如 设 x = 恢复改动
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 恢复改动() -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import change_plan as CP
    c = X.ctx()
    n = CP.restore_edits(c)
    if n:
        c.log("修改计划", 事件="恢复改动", 文件数=n)
    return {"restored": n}
