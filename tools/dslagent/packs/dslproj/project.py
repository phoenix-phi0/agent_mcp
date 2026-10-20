"""dslproj 的项目约定：目录布局、任务里的模块名、范围、约定读取与比对。

布局（项目根下）：contracts/<模块>.md 约定（冻结，不在范围内，模型改不了）、entities/<模块>.entity、services/<模块>.zs、
routes/<模块>*.zs（文件名以模块名开头）、queries/<模块>_*.sql、tests/<模块>_*。
任务文本的写法：含一行「模块 <名>」（其余文字是补充说明）；模块名是 contracts/ 里的文件名（英文 snake）。
"""
import re
from pathlib import Path

from . import contract as C

MODULE_RE = re.compile(r"^\s*模块[ \t:：]+([A-Za-z][A-Za-z0-9_]*)\s*$", re.M)


class ProjError(Exception):
    pass


def module_of(task):
    """任务文本里的「模块 <名>」→ 模块名；没有返回 None。"""
    m = MODULE_RE.search(task or "")
    return m.group(1) if m else None


def require_module(task):
    m = module_of(task)
    if not m:
        raise ProjError("任务里要有一行「模块 <名>」（模块名 = contracts/<名>.md）")
    return m


def scope_globs(module):
    """该模块允许写 / 删的路径（scope.py 的 glob）。"""
    return [f"entities/{module}.entity", f"services/{module}.zs", f"routes/{module}*.zs", f"queries/{module}_*.sql", f"tests/{module}_*"]


def contract_path(project, module):
    return Path(project) / "contracts" / f"{module}.md"


def all_modules(project):
    d = Path(project) / "contracts"
    return sorted(f.stem for f in d.glob("*.md")) if d.is_dir() else []


def load_contract(project, module):
    """→ (contract, 约定原文)；读不到 / 解析或检查不过抛 ProjError（带问题清单）。"""
    f = contract_path(project, module)
    if not f.is_file():
        raise ProjError(f"没有约定文件 contracts/{module}.md")
    text = f.read_text(encoding="utf-8")
    c, probs = C.parse(text)
    mods = all_modules(project)
    ups = {}
    for d in c["依赖"]:
        g = contract_path(project, d)
        if g.is_file():
            uc, p2 = C.parse(g.read_text(encoding="utf-8"))
            if p2:
                probs.append(f"上游 contracts/{d}.md 解析不通过：{p2[0]}")
            else:
                ups[d] = uc
    probs += C.check(c, module, ups, mods)
    if probs:
        raise ProjError(f"contracts/{module}.md 有问题：" + "；".join(probs[:8]))
    return c, text


def closure(project, module):
    """模块及其全部上游（依赖的依赖…），上游在前（建表顺序）。"""
    order, seen = [], set()

    def visit(m):
        if m in seen:
            return
        seen.add(m)
        f = contract_path(project, m)
        if f.is_file():
            c, _ = C.parse(f.read_text(encoding="utf-8"))
            for d in c["依赖"]:
                visit(d)
        order.append(m)
    visit(module)
    return order


def route_files(project, module, modules):
    """routes/ 下属于该模块的接口文件：文件名（不含 .zs）以「最长的模块名」归属。"""
    out = []
    rd = Path(project) / "routes"
    for f in sorted(rd.glob("*.zs")) if rd.is_dir() else []:
        own = max((m for m in modules if f.stem.startswith(m)), key=len, default=None)
        if own == module:
            out.append(f)
    return out


CALL_IN_ROUTE = re.compile(r"调用\s+(?:([A-Za-z0-9_一-鿿]+)\.)?([A-Za-z0-9_一-鿿]+)")


def _auth_diffs(project, module, contract, modules):
    """约定头部「认证 …」与本模块 routes 文件顶层实际写的认证声明是否一致（dsl_http.auth_config 的同一套解析）。
    没声明认证的模块两边都该是空的；两边都没写就不比，省得给不相关的模块报一堆「约定是（无）」。"""
    from tools.dsl_http import auth_config
    want = contract["认证"]
    if not (want["必须"] or want["可选"] or want["角色"]):
        return []                 # 这个模块的约定没打算要登录 / 角色，不比对实际文件（可能项目里别的模块开了登录）
    files = route_files(Path(project), module, modules)
    if not files:
        return [f"约定写了「认证 …」，但 routes/{module}*.zs 还没有文件"]
    import tempfile
    diffs = []
    # auth_config 按整个目录扫 .zs：只把属于本模块的几个文件拷到一个干净的临时目录里扫，不跟别的模块的声明混
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        for f in files:
            (tdp / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        got = auth_config(tdp)
    if bool(got["mandatory"]) != bool(want["必须"]):
        diffs.append(f"约定「认证 必须」是 {bool(want['必须'])}，routes/{module}*.zs 实际是 {bool(got['mandatory'])}")
    if bool(got["optional"]) != bool(want["可选"]):
        diffs.append(f"约定「认证 可选」是 {bool(want['可选'])}，routes/{module}*.zs 实际是 {bool(got['optional'])}")
    want_check = tuple(want["核对"]) if want["核对"] else None
    if got["check"] != want_check:
        diffs.append(f"约定「认证 核对」是 {want_check or '（无）'}，routes/{module}*.zs 实际是 {got['check'] or '（无）'}")
    want_identity = tuple(want["身份"]) if want["身份"] else None
    if got["identity"] != want_identity:
        diffs.append(f"约定「认证 身份」是 {want_identity or '（无）'}，routes/{module}*.zs 实际是 {got['identity'] or '（无）'}")
    if got["roles"] != want["角色"]:
        diffs.append(f"约定「认证 角色」是 {want['角色'] or '（无）'}，routes/{module}*.zs 实际是 {got['roles'] or '（无）'}")
    return diffs


def compare(project, module, contract, modules):
    """实际文件与约定是否一致：业务文件（模块名 / 依赖 / 每个函数的名字、公开与否、入参顺序与可选）、接口（方法 + 路径存在、只调约定里那个函数）、
    约定里的表在 entities/<模块>.entity 里都有。返回 {"一致": bool, "差异": [文字]}。"""
    from tools.dsl_http import split_endpoints
    from tools.dsl_service import ServiceProblem, parse_module
    project = Path(project)
    diffs = []
    sf = project / "services" / f"{module}.zs"
    if not sf.is_file():
        diffs.append(f"缺 services/{module}.zs")
    else:
        try:
            mod = parse_module(sf.read_text(encoding="utf-8"), sf, f"services/{module}.zs")
        except ServiceProblem as e:
            mod = None
            diffs.append(f"services/{module}.zs 解析失败：{e}")
        if mod is not None:
            if mod.name != module:
                diffs.append(f"services/{module}.zs 第一行「业务 {mod.name}」应是「业务 {module}」")
            have = sorted(d for d, _ in mod.deps)
            if have != sorted(contract["依赖"]):
                diffs.append(f"业务文件的「依赖」是 {have or '无'}，约定是 {sorted(contract['依赖']) or '无'}")
            want = {f["名"]: f for f in contract["函数"]}
            for n, f in want.items():
                a = mod.funcs.get(n)
                if a is None:
                    diffs.append(f"缺函数「{n}」")
                    continue
                if a.public != f["公开"]:
                    diffs.append(f"函数「{n}」约定是{'公开' if f['公开'] else '私有'}，实际是{'公开' if a.public else '私有'}")
                wp = [(p.rstrip("?"), p.endswith("?")) for p in f["入参"]]
                if list(a.params) != wp:
                    fmt = lambda ps: " ".join(n_ + ("?" if o else "") for n_, o in ps) or "（无）"  # noqa: E731
                    diffs.append(f"函数「{n}」入参约定是 {fmt(wp)}，实际是 {fmt(a.params)}")
            for n, a in mod.funcs.items():
                if a.public and n not in want:
                    diffs.append(f"多了约定里没有的公开函数「{n}」")
    eps = []
    for rf in route_files(project, module, modules):
        try:
            got, _ = split_endpoints(rf.read_text(encoding="utf-8"), rf)
        except Exception as e:  # noqa: BLE001
            diffs.append(f"{rf.name} 接口切块失败：{e}")
            continue
        eps += got
    by = {(e.method, e.path): e for e in eps}
    for i in contract["接口"]:
        e = by.pop((i["方法"], i["路径"]), None)
        if e is None:
            diffs.append(f"缺接口 {i['方法']} {i['路径']}（routes/{module}*.zs）")
            continue
        called = {f"{m or module}.{fn}" for m, fn in CALL_IN_ROUTE.findall(e.script)}
        if called != {f"{module}.{i['函数']}"}:
            diffs.append(f"接口 {i['方法']} {i['路径']} 应只调 {module}.{i['函数']}，实际调了 {sorted(called) or '没有调用'}")
        if bool(e.public) != bool(i["公开"]):
            diffs.append(f"接口 {i['方法']} {i['路径']} 约定「公开」是 {i['公开']}，实际是 {bool(e.public)}")
        if (e.role or "") != (i["角色"] or ""):
            diffs.append(f"接口 {i['方法']} {i['路径']} 约定「角色」是 {i['角色'] or '（无）'}，实际是 {e.role or '（无）'}")
        if i["上传"]:
            up = i["上传"]
            field = up["字段"]
            if not re.search(rf"存文件\s+{re.escape(field)}(\s|$)", e.script):
                diffs.append(f"接口 {i['方法']} {i['路径']} 声明了「上传 {field}」，但 routes 脚本里没有「存文件 {field}」")
            if up["类型"] and f"类型={up['类型']}" not in e.script:
                diffs.append(f"接口 {i['方法']} {i['路径']} 约定「类型 {up['类型']}」，routes 脚本里没有「存文件 … 类型={up['类型']}」")
            if up["上限"] and f"上限={up['上限']}" not in e.script:
                diffs.append(f"接口 {i['方法']} {i['路径']} 约定「上限 {up['上限']}」，routes 脚本里没有「存文件 … 上限={up['上限']}」")
    for (m, p) in by:
        diffs.append(f"多了约定里没有的接口 {m} {p}")
    diffs += _auth_diffs(project, module, contract, modules)
    ef = project / "entities" / f"{module}.entity"
    ents = set(re.findall(r"^\s*实体\s+(\S+)", ef.read_text(encoding="utf-8"), re.M)) if ef.is_file() else set()
    for t in contract["表"]:
        if t["名"] not in ents:
            diffs.append(f"约定里的表「{t['名']}」在 entities/{module}.entity 里没有对应的「实体 {t['名']}」")
    if any(t.get("学习记录") for t in contract["表"]):
        from tools.migrate import switch_on
        if not switch_on(project / "routes"):
            diffs.append("模块有「学习记录」标注的表，但 routes/ 下没有「迁移 只加」声明（应由生成骨架写出 routes/_project.zs）")
    return {"一致": not diffs, "差异": diffs}


def load_problems(project, module, modules):
    """加载检查（loadcheck.check_project）里属于该模块文件的问题。"""
    from tools.dslagent import loadcheck
    keys = [f"services/{module}.zs"] + [f"routes/{f.name}" for f in route_files(project, module, modules)]
    return [p for p in loadcheck.check_project(project) if any(k in p for k in keys)]
