"""全局检查：全部约定都通过各自检查之后调（不调模型）：同一「方法+路径」或同一张表在两个模块都定义 → 按模块分组的问题。
返回 {"count": n, "by_module": {模块: "问题（分号隔开）"}, "summary": 摘要文本, "items": [{issue, modules, basis}]}；
没问题 count=0、by_module={}、items=[]。items 同 issues.program_items（含「依赖与顶层不一致」，basis=程序检查），给 核查.zs 的 存问题清单 用；
count / by_module / summary 只是「方法+路径 / 表重复」（规划到通过 的全局重写按它们判断）。没有 plan/top.zs 时 count=0（核查要能在顶层规划之前跑）。
例如 设 g = 全局检查
约定=是（K174，audit2.zs 开头的约定闸）：改成逐模块跑 v3/contracts.check（写规划时的那套约定检查，含约定里的豁免标注），
不跑上面的全局检查；返回同样的形状 {count, by_module, summary, items}，items 的 basis 写「约定检查 contracts/<模块>.md」。
例如 设 g = 全局检查 约定=是
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 全局检查(约定: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import globalcheck as G, issues as IS, planning as PL
    if 约定 not in ("", "是"):
        X.fail(f"全局检查：约定 只认「是」，不认「{约定}」")
    c = X.ctx()
    if not c.top_path().is_file():
        return {"count": 0, "by_module": {}, "summary": "还没有 plan/top.zs，跳过", "items": []}
    if 约定:
        from tools.dslagent.v3 import contracts as VC
        top = X.top_or_none(c)
        items = VC.check_project(c.project, top)
        按模块 = {}
        for it in items:
            按模块[it["modules"]] = (按模块[it["modules"]] + "；" if it["modules"] in 按模块 else "") + it["issue"]
        c.log("规划", 种类="约定", 模块="", 事件="约定检查", 条数=len(items), 按模块={m: v[:300] for m, v in 按模块.items()})
        return {"count": len(items), "by_module": 按模块, "summary": "；".join(f"{it['modules']}：{it['issue']}" for it in items[:3]),
                "items": items}
    top = PL.current_top(c)
    g = G.check(c.project, top)
    按模块 = {m: "；".join(v) for m, v in g["按模块"].items()}
    c.log("规划", 种类="约定", 模块="", 事件="全局检查", 条数=g["条数"], 按模块=按模块)
    return {"count": g["条数"], "by_module": 按模块, "summary": g["摘要"], "items": IS.program_items(c.project, top)}
