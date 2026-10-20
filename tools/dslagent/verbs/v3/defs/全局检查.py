"""全局检查：全部约定都通过各自检查之后调（不调模型）：同一「方法+路径」或同一张表在两个模块都定义 → 按模块分组的问题。
返回 {"条数": n, "按模块": {模块: "问题（分号隔开）"}, "摘要": 摘要文本}；没问题 条数=0、按模块={}。
例如 设 g = 全局检查
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 全局检查() -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import globalcheck as G, planning as PL
    c = X.ctx()
    top = PL.current_top(c)
    g = G.check(c.project, top)
    按模块 = {m: "；".join(v) for m, v in g["按模块"].items()}
    c.log("规划", 种类="约定", 模块="", 事件="全局检查", 条数=g["条数"], 按模块=按模块)
    return {"条数": g["条数"], "按模块": 按模块, "摘要": g["摘要"]}
