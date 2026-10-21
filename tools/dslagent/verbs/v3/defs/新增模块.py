"""新增模块 <名> 依赖=<逗号隔开，没有写 无> 说明=<一句话>：改 plan/top.zs（保留别的行与注释，追加一行），过 top
检查；并登记到 ctx.pending_contracts[名]=""（空串 = 还没约定过，落实修改 时走 规划一份 的正常写约定全流程）。
例如 新增模块 quiz_knowledge 依赖=quiz 说明=按知识点练习
"""
import re
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 新增模块(名: str, 依赖: str = "", 说明: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import top as VT
    c = X.ctx()
    name = (名 or "").strip()
    if not name:
        X.fail("新增模块要写模块名")
    if not c.top_path().is_file():
        X.fail("还没有 plan/top.zs，不能新增模块")
    old_text = c.top_path().read_text(encoding="utf-8")
    top, probs = VT.parse(old_text)
    if probs:
        X.fail("plan/top.zs 解析不过，不能新增模块：" + "；".join(probs[:3]))
    if any(m["名"] == name for m in top["模块"]):
        X.fail(f"模块「{name}」已经存在，不能重名新增")
    deps = [d for d in re.split(r"[,，]", 依赖 or "") if d and d != "无"]
    dep_part = (" 依赖 " + " ".join(deps)) if deps else ""
    comment = f"  # {说明}" if (说明 or "").strip() else ""
    new_text = VT.clean(old_text).rstrip("\n") + f"\n模块 {name}{dep_part}{comment}\n"
    new_probs = VT.check(new_text)
    if new_probs:
        X.fail(f"新增模块「{name}」后 plan/top.zs 没通过检查：" + "；".join(new_probs[:3]))
    c.top_path().write_text(new_text, encoding="utf-8", newline="\n")
    c.pending_contracts[name] = ""
    c.log("修改计划", 事件="新增模块", 模块=name, 依赖=deps)
    return {"名": name}
