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


def scope_globs(module, project=None):
    """该模块允许写 / 删的路径（scope.py 的 glob）。给了 project 时 routes 按「最长模块名归属」（同 route_files）收窄：
    别的模块名以本模块名开头（quiz 与 quiz_knowledge）时，routes/quiz*.zs 会吞掉对方的文件，改成 routes/<模块>.zs + 已有的、归本模块的文件。"""
    routes = [f"routes/{module}*.zs"]
    if project is not None:
        mods = sorted(set(all_modules(project)) | {module})
        if any(m != module and m.startswith(module) for m in mods):
            routes = [f"routes/{module}.zs"] + [f"routes/{f.name}" for f in route_files(project, module, mods) if f.stem != module]
    return [f"entities/{module}.entity", f"services/{module}.zs", *routes, f"queries/{module}_*.sql", f"tests/{module}_*"]


def scope_files(root, module):
    """root 下现有的、属于该模块范围的文件（相对路径，排序）；routes 按最长模块名归属。"""
    root = Path(root)
    return sorted({str(f.relative_to(root)) for g in scope_globs(module, root) for f in root.glob(g) if f.is_file()})


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


def _all_contracts(project, module, contract, modules):
    """{模块: 约定}：modules 里读得到、解析得过的 contracts/<m>.md，本模块用传进来的这份。"""
    out = {}
    for m in modules:
        f = Path(project) / "contracts" / f"{m}.md"
        if f.is_file():
            c, probs = C.parse(f.read_text(encoding="utf-8"))
            if not probs:
                out[m] = c
    out[module] = contract
    return out


def _auth_parsed(root):
    """auth_config 的解析结果里和认证声明有关的几项（比对用）。"""
    from tools.dsl_http import auth_config
    g = auth_config(root)
    return {"必须": bool(g["mandatory"]), "可选": bool(g["optional"]), "核对": g["check"], "核对函数": g["check_fn"],
            "身份": g["identity"], "角色": g["roles"], "拒绝": g["deny"]}


def _auth_diffs(project, module, contract, modules):
    """本模块 routes 文件顶层实际写的认证声明 与 程序生成的那份是否一致：账号模块（有公开函数「核对身份」的模块）应等于
    contract.auth_block 生成的认证块，其他模块一条认证行都不该有。"""
    from tools.dsl import DSLError
    owner, lines = C.auth_block(_all_contracts(project, module, contract, modules))
    want_lines = lines if owner == module else []
    files = route_files(Path(project), module, modules)
    if not files:
        return [f"账号模块 {module} 的 routes/{module}*.zs 还没有文件，应有认证块：{' / '.join(want_lines)}"] if want_lines else []
    import tempfile
    # auth_config 按整个目录扫 .zs：只把属于本模块的几个文件拷到一个干净的临时目录里扫，不跟别的模块的声明混
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        for f in files:
            (tdp / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            got = _auth_parsed(tdp)
        except DSLError as e:
            return [f"routes/{module}*.zs 的认证声明写得不一致：{e}"]
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "w.zs").write_text("\n".join(want_lines) + "\n", encoding="utf-8")
        want = _auth_parsed(Path(td))
    if got == want:
        return []
    if not want_lines:
        return [f"routes/{module}*.zs 里不该有认证行（认证只在账号模块 routes 里由程序生成一份），实际有：{_auth_summary(got)}"]
    return [f"routes/{module}*.zs 的认证块和程序生成的不一致：应是 {' / '.join(want_lines)}；实际是 {_auth_summary(got) or '（没有）'}"]


def _auth_summary(g):
    parts = []
    if g["必须"]:
        parts.append("认证 必须")
    if g["可选"]:
        parts.append("认证 可选")
    if g["核对"]:
        parts.append("认证 核对 " + " ".join(g["核对"]))
    if g["核对函数"]:
        parts.append("认证 核对 " + ".".join(g["核对函数"]))
    if g["身份"]:
        parts.append("认证 身份 " + " 默认 ".join(g["身份"]))
    for code, label in g["角色"].items():
        parts.append(f"认证 角色 {code} {label}" + (f" 拒绝 {g['拒绝'][code]}" if code in g["拒绝"] else ""))
    return " / ".join(parts)


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
