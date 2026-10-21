"""删除模块 <名>：把这一行从 plan/top.zs 去掉（保留别的行与注释），过 top 检查；复用「清理删掉的模块」删它的
contracts/entities/services/routes/queries/tests 文件与 state.json 记录。
例如 删除模块 old_mod
"""
import importlib.util
import re
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")

MOD_RE = re.compile(r"^模块\s+(\S+)")


def _code_part(line):
    i = line.find("#")
    while i >= 0:
        if i == 0 or line[i - 1] in " \t":
            return line[:i]
        i = line.find("#", i + 1)
    return line


def _clean_removed_modules():
    p = Path(__file__).parent / "清理删掉的模块.py"
    spec = importlib.util.spec_from_file_location("_v3_del_clean", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.清理删掉的模块()


def 删除模块(名: str) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import top as VT
    c = X.ctx()
    name = (名 or "").strip()
    if not name:
        X.fail("删除模块要写模块名")
    if not c.top_path().is_file():
        X.fail("还没有 plan/top.zs，不能删除模块")
    old_text = c.top_path().read_text(encoding="utf-8")
    lines = VT.clean(old_text).splitlines()
    kept = []
    found = False
    for l in lines:
        mo = MOD_RE.match(_code_part(l).strip())
        if mo and mo.group(1) == name:
            found = True
            continue
        kept.append(l)
    if not found:
        X.fail(f"删除模块「{name}」不在 plan/top.zs 里")
    new_text = "\n".join(kept) + "\n"
    new_probs = VT.check(new_text)
    if new_probs:
        X.fail(f"删除模块「{name}」后 plan/top.zs 没通过检查：" + "；".join(new_probs[:3]))
    c.top_path().write_text(new_text, encoding="utf-8", newline="\n")
    c.pending_contracts.pop(name, None)
    _clean_removed_modules()
    c.log("修改计划", 事件="删除模块", 模块=name)
    return {"name": name}
