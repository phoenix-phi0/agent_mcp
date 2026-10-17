"""DSL 验收检查（verify.code.check 里用）：本次改动里有 .entity / .sql / .zs / .ui 时，对受影响的 gen 项目在临时副本里跑
实体解析校验 → build → 建库 → make_app（含重复接口、sql 引用）→ 改动的 .ui 的 ui 检查（_gencore.dsl_verify，解释器缺 jinja2 / flask
时走 .venv 子进程，同 newproj）。失败的步骤变成验收缺口（带报错文本、文件、行号）。改动里没有 DSL 文件完全跳过。

project_roots(project, files) -> 受影响的 gen 项目根（相对 project 的路径，"." 是 project 自己）
check(project, files) -> {"跑了": bool, "项目": [{项目, ok, msg, errors}], "缺口": [{说明, 文件?, 行?}]}
"""
import importlib.util
import re
from pathlib import Path

DSL_SUF = (".entity", ".sql", ".zs", ".ui")
GEN = Path(__file__).resolve().parent.parent / "verbs" / "newproj" / "defs" / "_gen.py"
LOC = re.compile(r"([\w./-]+\.(?:zs|ui|entity|sql)):(\d+)")
LINE = re.compile(r"第\s*(\d+)\s*行")
ERR_CAP = 10


def dsl_files(files):
    return sorted(f for f in files if f.endswith(DSL_SUF))


def is_gen_project(d):
    d = Path(d)
    return (any((d / "entities").glob("*.entity")) and any((d / "ui").glob("*.ui"))
            and ((d / "routes").is_dir() or (d / "queries").is_dir()))


def project_roots(project, files):
    """每个 DSL 改动文件向上找（含自己所在目录、直到 project 根）第一个像 gen 项目的目录；去重排序。找不到的文件不归任何项目。"""
    project = Path(project).resolve()
    roots = set()
    for rel in dsl_files(files):
        d = (project / rel).parent
        while True:
            if d.is_dir() and is_gen_project(d):
                roots.add(str(d.relative_to(project)) or ".")
                break
            if d == project or project not in d.parents:
                break
            d = d.parent
    return sorted(roots)


def _gen():
    spec = importlib.util.spec_from_file_location("_dsl_gen", GEN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def entity_loc(base, line):
    """实体报错的行号是所有 .entity 用空行拼起来（gen.project.entities_text）后的行号，还原成 (entities/<文件>, 文件内行号)。"""
    start = 1
    for f in sorted((Path(base) / "entities").glob("*.entity")):
        n = f.read_text(encoding="utf-8").count("\n")
        if line <= start + n:
            return f"entities/{f.name}", line - start + 1
        start += n + 2
    return None, line


def _gap(root, e, base):
    """一条 dsl_verify 错误 → 缺口。文件、行号尽量从报错文本里抠出来（相对 project）。"""
    msg = e.get("msg") or ""
    pre = "" if root == "." else root + "/"
    g = {"说明": f"DSL 检查（{root}）{e['步']}失败：{msg[:600]}"}
    f, ln = e.get("文件"), None
    m = LOC.search(msg)
    if m:
        f, ln = (f or m.group(1)), int(m.group(2))
    elif e["步"] in ("ui", "实体"):
        m = LINE.search(msg)
        ln = int(m.group(1)) if m else None
    if e["步"] == "实体" and not f and ln:
        f, ln = entity_loc(base, ln)
    if f and "/" not in f and e["步"] == "路由加载":
        f = None
    if f:
        sub = {".zs": "routes/", ".ui": "ui/", ".entity": "entities/", ".sql": "queries/"}
        if "/" not in f and not f.startswith(pre):
            f = sub.get(Path(f).suffix, "") + f
        g["文件"] = f if f.startswith(pre) or root == "." else pre + f
        if ln:
            g["行"] = ln
    return g


def check(project, files):
    """对 files（本次改动文件，相对 project）里涉及的 gen 项目跑 DSL 检查。没有 DSL 文件 / 找不到项目 → {"跑了": False}。"""
    project = Path(project).resolve()
    roots = project_roots(project, files)
    if not roots:
        return {"跑了": False, "项目": [], "缺口": []}
    G = _gen()
    out, gaps = [], []
    for root in roots:
        base = project if root == "." else project / root
        prefix = "" if root == "." else root + "/"
        uis = [f[len(prefix):] for f in dsl_files(files) if f.endswith(".ui") and f.startswith(prefix)]
        r = G.run_op("dsl_verify", {"root": str(base), "ui_files": uis})
        errs = r.get("errors") or ([] if r.get("ok") == "是" else [{"步": "检查", "msg": r.get("msg") or "失败"}])
        out.append({"项目": root, "ok": r.get("ok") == "是", "msg": (r.get("msg") or "")[:600], "errors": errs[:ERR_CAP]})
        gaps += [_gap(root, e, base) for e in errs[:ERR_CAP]]
    return {"跑了": True, "项目": out, "缺口": gaps}
