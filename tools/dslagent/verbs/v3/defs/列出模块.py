"""列出模块：plan/top.zs 里的模块名，逗号隔开的一个字符串（没有 top.zs 返回空串）。
有代码=是：只列已经有代码文件（entities / services / routes / queries）的模块。
例如 设 mods = 列出模块 有代码=是
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 列出模块(有代码: str = "否") -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import planning as PL, regress as RG
    c = X.ctx()
    try:
        names = [m["名"] for m in PL.current_top(c)["模块"]]
    except ValueError:
        return ""
    if 有代码 == "是":
        names = [m for m in names if RG.code_files(c.project, m, names)]
    return ",".join(names)
