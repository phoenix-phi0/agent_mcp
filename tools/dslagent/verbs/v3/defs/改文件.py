"""改文件 <文件> <原文> <新文>：修改计划里直接改项目文件（代码和约定不一致时用）。原文在文件里必须恰好出现一次，
新文可省（＝删掉原文）。文件必须属于 plan/top.zs 里某个模块的范围（entities / services / routes / queries，同 dslproj 的
scope_globs；tests/、kg/ 等范围外一律拒绝）。三个参数各是一个词：空格写 \\_、换行写 \\n、制表符写 \\t、反斜杠写 \\\\，
花括号 {x} 写成 {{x}}（DSL 引擎会还原）。CRLF 文件按原换行写回。改之前先登记原文到 ctx.file_edits，
落实修改 验收不过 / 计划中途失败（恢复改动）时据此恢复。出错就 终止 失败，并先把这份计划已经改过的文件恢复。
返回 {file, module}。
例如 改文件 services/graph.zs 返回\\_1 返回\\_2
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 改文件(文件: str, 原文: str, 新文: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import change_plan as CP, top as VT
    c = X.ctx()

    def fail(msg):
        n = _restore(c)
        c.log("修改计划", 事件="改文件失败", 文件=文件, 原因=msg, 已恢复=n)
        X.fail(f"改文件失败：{msg}" + (f"（已恢复这份计划前面改过的 {n} 个文件）" if n else ""))

    top_text = c.top_path().read_text(encoding="utf-8") if c.top_path().is_file() else ""
    mods = {m["名"] for m in VT.parse(top_text)[0]["模块"]} if top_text else set()
    f, old, new = CP.decode_edit_arg(文件, False), CP.decode_edit_arg(原文, False), CP.decode_edit_arg(新文, False)
    path, rel, owner, err = CP.resolve_edit_path(c.project, mods, f)
    if err:
        fail(err)
    if not path.is_file():
        fail(f"文件「{rel}」不存在")
    if not old:
        fail("原文是空的")
    text = CP.read_raw(path)
    n, old2, new2 = CP.locate_edit(text, old, new)
    if n != 1:
        fail(f"原文在「{rel}」里" + ("找不到（出现 0 次）" if n == 0 else f"出现了 {n} 次，必须唯一"))
    if old2 == new2:
        fail(f"「{rel}」里原文和新文一样，没有改动")
    with c.lock:
        c.file_edits.setdefault(owner, {}).setdefault(rel, text)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text.replace(old2, new2))
    c.log("修改计划", 事件="改文件", 文件=rel, 模块=owner)
    return {"file": rel, "module": owner}


def _restore(c):
    sys.path.insert(0, str(Path(__file__).parent))
    from tools.dslagent.v3 import change_plan as CP
    return CP.restore_edits(c)
