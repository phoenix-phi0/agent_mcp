"""模块改名/移动（确定性，不调模型）。把 旧路径（如 pkg/a.py）挪到 新路径（如 pkg/b.py），
范围内所有非测试 .py 里按词边界把旧模块名（a，以及点路径 pkg.a）换成新模块名；兼容=是 时在旧路径留一个兼容模块，
只从新模块重新导出 导出名（逗号分隔；空=新模块里全部公开的模块级函数/类/常量），自己不定义任何函数。
返回 {ok: 是/否, msg, left（改完后范围内仍出现旧模块名的行，兼容模块除外）}。
例如 设 m = 改模块名 studykit/textutil.py studykit/textnorm.py 是 strip_punct,normalize
"""
import ast
import re
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def _dotted(rel):
    return rel[:-3].replace("/", ".")


def 改模块名(旧路径: str = "", 新路径: str = "", 兼容: str = "否", 导出名: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    from _sandbox import is_test_rel, py_files, resolve
    root = Path(WORKSPACE).resolve()
    po, e1 = resolve(root, 旧路径)
    pn, e2 = resolve(root, 新路径)
    if e1 or e2:
        return {"ok": "否", "msg": e1 or e2, "left": ""}
    ro, rn = str(po.relative_to(root)), str(pn.relative_to(root))
    if not (ro.endswith(".py") and rn.endswith(".py")) or is_test_rel(ro) or is_test_rel(rn):
        return {"ok": "否", "msg": f"只能改非测试 .py 模块：{ro} → {rn}", "left": ""}
    if not po.is_file():
        return {"ok": "否", "msg": f"旧模块不存在：{ro}", "left": ""}
    if pn.exists():
        return {"ok": "否", "msg": f"新路径已存在：{rn}", "left": ""}
    so, sn = Path(ro).stem, Path(rn).stem
    src = po.read_text(encoding="utf-8")
    scope = po.parent
    rx_dot = re.compile(rf"\b{re.escape(_dotted(ro))}\b")
    rx = re.compile(rf"\b{re.escape(so)}\b")
    # 先在内存里算好所有改动，逐个过安全约束（新模块按 写入、引用方按 改写），有一处被拦就整体不动
    writes, n, files = {rn: src}, 0, []
    for rel in py_files(root):
        if is_test_rel(rel) or rel == ro:
            continue
        p = root / rel
        s = p.read_text(encoding="utf-8")
        s2, k1 = rx_dot.subn(_dotted(rn), s)
        k2 = 0
        if scope in p.parents:
            s2, k2 = rx.subn(sn, s2)
        if k1 + k2:
            writes[rel] = s2
            n += k1 + k2
            files.append(f"{rel}({k1 + k2})")
    s2, k1 = rx_dot.subn(_dotted(rn), src)
    s2, k2 = rx.subn(sn, s2)
    if k1 + k2:
        writes[rn] = s2
        n += k1 + k2
        files.append(f"{rn}({k1 + k2})")
    import 推理 as T
    for rel, text in writes.items():
        why = T._R().check("写入" if rel == rn else "改写", root, rel, text)
        if why:
            return {"ok": "否", "msg": why + "（整体没改）", "left": "", "blocked": "是"}
    pn.parent.mkdir(parents=True, exist_ok=True)
    for rel, text in writes.items():
        (root / rel).write_text(text, encoding="utf-8")
    po.unlink()
    compat = str(兼容 or "").strip() in ("是", "yes", "true", "True", "1")
    if compat:
        tree = ast.parse(pn.read_text(encoding="utf-8"))
        pub = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                pub.append(node.name)
            elif isinstance(node, ast.Assign):
                pub += [t.id for t in node.targets if isinstance(t, ast.Name)]
        pub = [x for x in pub if not x.startswith("_")]
        want = [x.strip() for x in re.split(r"[,，、\s]+", 导出名 or "") if x.strip()]
        bad = [x for x in want if x not in pub]
        names = [x for x in want if x in pub] or pub
        rel_mod = "." + sn if pn.parent == po.parent else _dotted(rn)
        po.write_text(f'"""兼容模块：已改名为 {_dotted(rn)}，这里只重新导出旧名字。"""\n'
                      f"from {rel_mod} import {', '.join(names)}  # noqa: F401\n\n__all__ = {names!r}\n", encoding="utf-8")
    left = []
    for rel in py_files(root):
        p = root / rel
        if is_test_rel(rel) or (compat and p == po) or not (scope in p.parents):
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if rx.search(line):
                left.append(f"{rel}:{i}: {line.strip()}")
    msg = f"{ro} → {rn}；替换 {n} 处：{'、'.join(files) or '无'}；剩余 {len(left)} 行"
    if compat:
        msg += f"；兼容模块 {ro} 重新导出 {', '.join(names)}" + (f"（这些名字新模块里没有，未导出：{','.join(bad)}）" if bad else "")
    return {"ok": "是" if not left else "否", "msg": msg, "left": "；".join(left[:20]) or "无"}
