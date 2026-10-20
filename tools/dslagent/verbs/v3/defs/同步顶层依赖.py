"""同步顶层依赖：全部约定过了之后调，把 plan/top.zs 每个模块的「依赖」改成与它的约定一致（约定的依赖可能比 top.zs 多或少，
约定检查只要求「是 top.zs 里的模块、不成环」，不要求逐字一致）；保留注释、不改模块名、不碰没有约定的模块。
同步后的 plan/top.zs 要过 top 检查，不过 终止 失败（不应该发生：约定检查时已经保证不成环）。
返回 {改了: [模块名…], 没变: 布尔}。
例如 同步顶层依赖
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 同步顶层依赖() -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import contracts as VC, top as VT
    c = X.ctx()
    old_text = c.top_path().read_text(encoding="utf-8")
    top, probs = VT.parse(old_text)
    if probs:
        X.fail("plan/top.zs 解析不过，不能同步依赖：" + "；".join(probs[:3]))
    want, changed = {}, []
    for m in top["模块"]:
        name = m["名"]
        try:
            cc, _ = VC.load(c.project, name)
        except FileNotFoundError:
            continue
        if sorted(cc["依赖"]) != sorted(m["依赖"]):
            want[name] = cc["依赖"]
            changed.append(name)
    if not changed:
        return {"改了": [], "没变": True}
    new_text = VT.sync_deps(old_text, want)
    new_probs = VT.check(new_text)
    if new_probs:
        X.fail("同步依赖后 plan/top.zs 没通过检查：" + "；".join(new_probs[:3]))
    c.top_path().write_text(new_text, encoding="utf-8", newline="\n")
    c.log("规划", 种类="顶层", 事件="同步依赖", 改了=changed)
    return {"改了": changed, "没变": False}
