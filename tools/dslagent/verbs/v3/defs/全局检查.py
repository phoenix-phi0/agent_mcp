"""全局检查：全部约定都通过各自检查之后调（不调模型）：同一「方法+路径」或同一张表在两个模块都定义 → 按模块分组的问题。
返回 {"count": n, "by_module": {模块: "问题（分号隔开）"}, "summary": 摘要文本, "items": [{issue, modules, basis, type}]}；
没问题 count=0、by_module={}、items=[]。items 同 issues.program_items（含「依赖与顶层不一致」，basis=程序检查，type=contract），给 核查.zs 的 存问题清单 用；
count / by_module / summary 只是「方法+路径 / 表重复」（规划到通过 的全局重写按它们判断）。没有 plan/top.zs 时 count=0（核查要能在顶层规划之前跑）。
例如 设 g = 全局检查
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 全局检查() -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import globalcheck as G, issues as IS, planning as PL
    c = X.ctx()
    if not c.top_path().is_file():
        return {"count": 0, "by_module": {}, "summary": "还没有 plan/top.zs，跳过", "items": []}
    top = PL.current_top(c)
    g = G.check(c.project, top)
    按模块 = {m: "；".join(v) for m, v in g["按模块"].items()}
    c.log("规划", 种类="约定", 模块="", 事件="全局检查", 条数=g["条数"], 按模块=按模块)
    return {"count": g["条数"], "by_module": 按模块, "summary": g["摘要"], "items": IS.program_items(c.project, top)}
