"""加载检查：服务启动后「接口出错」那一类（条件看不懂、变量名非法、遍历写法不对……）在生成时就挡掉。

服务端的接口表只切块（dsl_http.scan_routes / split_endpoints），脚本要到请求时才由 DSLEngine 解析，
解析错误以 DSLError 抛出，路由器打印「[接口出错] 文件: 原话」并回 500。这里复用同一套：

- 切接口块：dsl_http.split_endpoints（与启动同一个函数；块不配对、端口反了同样报）。
- 脚本解析：DSLEngine 自己的 _take_sections / _check_loops / _scan_block / parse_cond_expr / _parse_each /
  _split_assign（check_name），逐行走一遍和 _exec_block 一样的解析点，但不执行任何动词（不碰库、不调模型）。

没有另写解析器：引擎改了写法规则，这里自动跟着变。只查「解析点」，运行期才知道的值（变量内容、sql 结果）不查。
"""
from pathlib import Path

import re

from tools.dsl import DSLEngine
from tools.dsl_core import (
    CALL_PARAM_RE, DSLError, PACK_SEP_RE, RESERVED, normalize, single_eq_hint, parse_cond_expr,
    split_head, split_raw_cmp,
)
from tools.verbs import VerbRegistry
from tools.dsl_http import scan_routes, split_endpoints
from tools.dsl_service import Services, parse_call_text, split_target


class _ParseOnly(DSLEngine):
    """只解析：把运行时才有值的部分（遍历的列表）换成空。"""

    def _resolve_items(self, raw):
        return []


def parse_cond(cond, lineno):
    """条件：结构（parse_cond_expr）+ 每个比较能不能拆出 左 运算符 右（求值时 eval_cond_expr 才拆，拆不出报「看不懂的条件」，这里提前拆一遍）。"""
    def leaves(t):
        if t[0] in ("and", "or"):
            for x in t[1]:
                yield from leaves(x)
        elif t[0] == "not":
            yield from leaves(t[1])
        else:
            yield t[1]
    for raw in leaves(parse_cond_expr(cond, lineno)):
        if split_raw_cmp(raw) is None:
            raise DSLError(
                f"第 {lineno + 1} 行：看不懂的条件「{raw}」。可用："
                f"包含 / 不包含 / 等于 / 不等于 / 为空 / 不为空 / "
                f"大于 / 小于 / 不小于 / 不大于 / 开头是 / 结尾是（符号 > < >= <= == != 也可以），组合用 且 / 或 / 非 / 括号"
                + single_eq_hint(raw))


def parse_script(script):
    """走一遍引擎的解析点。通过返回 None，否则返回报错原话（DSLError 的文字）。"""
    eng = _ParseOnly(client=None, workdir=Path("."), verbose=False)
    try:
        script = eng._take_sections(script)
        lines = [normalize(ln).rstrip() for ln in script.splitlines()]
        eng._check_loops(lines)
        for i, raw in enumerate(lines):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            head, rest = split_head(line)
            if head == "if":
                if not rest:
                    raise DSLError(f"第 {i + 1} 行：「如果」后面要跟条件")
                marks, _end = eng._scan_block(lines, i, len(lines))
                parse_cond(rest, i)
                for kind, at, cond in marks:
                    if kind == "elif":
                        parse_cond(cond, at)
            elif head in ("each", "foreach"):
                eng._parse_each(rest, i)
                else_at, _end = eng._find_block(lines, i, len(lines))
                if else_at is not None:
                    raise DSLError(f"第 {else_at + 1} 行：循环里不能直接写「否则」")
            elif head == "while":
                cond, _ = eng._parse_while(rest, i)
                parse_cond(cond, i)
            elif head == "set":
                eng._split_assign(rest, "设")
            elif head in ("else", "elif", "end") and not _opened(lines, i):
                raise DSLError(f"第 {i + 1} 行：多余的「{head_word(head)}」")
    except DSLError as e:
        return str(e)
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"
    return None


def head_word(head):
    return {"else": "否则", "elif": "否则如果", "end": "结束"}[head]


def _opened(lines, at):
    """第 at 行之前是否有还没关的块（游离的 否则 / 结束 引擎运行到才报，这里提前报）。"""
    from tools.dsl_core import BLOCK_OPENERS
    depth = 0
    for j in range(at):
        h, _ = split_head(lines[j].strip())
        if h in BLOCK_OPENERS:
            depth += 1
        elif h == "end":
            depth -= 1
    return depth > 0


BAD_BIZ_CODE_RE = re.compile(r"^报错\s+(\d{3})(?:\s|$)")
BIZ_CODE_HEAD_RE = re.compile(r"^4\d\d(?:\s|$)")


def call_sites(lines, funcs=None):
    """脚本行里的调用语句：[(下标, 目标, 参数原文)]，只收业务调用（模块.函数；funcs 里有的只写函数名），
    「执行 x.zs」这类脚本调用不收。"""
    out = []
    for i, raw in enumerate(lines):
        line = normalize(raw).strip()
        if not line or line.startswith("#"):
            continue
        head, rest = split_head(line)
        if head == "set":
            _, sep, value = rest.partition("=")
            if not sep:
                continue
            head, rest = split_head(value.strip())
        if head != "call":
            continue
        target, tail, _on_err = parse_call_text(rest)
        hit = split_target(target, funcs)
        if hit:
            out.append((i, hit, tail))
    return out


def exec_sites(lines):
    """脚本行里 `执行` / `后台执行` 一个 scripts/… 脚本的语句：[(下标, 后台?, 目标, {键: 值原文})]。
    目标里有 {变量} 的不收（运行时才知道）；业务调用（模块.函数）、同目录脚本名不收。"""
    out = []
    for i, raw in enumerate(lines):
        line = normalize(raw).strip()
        if not line or line.startswith("#"):
            continue
        head, rest = split_head(line)
        if head == "set":
            _, sep, value = rest.partition("=")
            if not sep:
                continue
            head, rest = split_head(value.strip())
        if head not in ("call", "call_bg"):
            continue
        target, tail, _on_err = parse_call_text(rest)
        if not target.startswith("scripts/") or "{" in target:
            continue
        out.append((i, head == "call_bg", target, {m.group(1).strip(): m.group(2).strip() for m in CALL_PARAM_RE.finditer(tail)}))
    return out


def script_module(target, modules):
    """scripts/<名>.zs 按文件名前缀归哪个模块（「<模块>_」开头，取最长）；没有返回 None。"""
    stem = Path(target).stem
    return max((m for m in modules if stem.startswith(m + "_")), key=len, default=None)


def check_script_calls(lines, root, caller, modules, label, base=0):
    """`执行` / `后台执行` 的目标是 scripts/… 时：脚本存在；`后台执行` 的 on_error 脚本存在；目标脚本归调用方所在模块
    （文件名以「<调用方模块>_」开头；跨模块不许执行别人的脚本，只能调对方的公开函数）。调用方不属于任何模块（caller 为 None）时只查存在。
    只在加载检查 / 核查阶段用，不在生成阶段拦（8c7dba1）。"""
    probs = []
    for i, bg, target, params in exec_sites(lines):
        where = f"[接口出错] {label}: 第 {base + i + 1} 行："
        targets = [(target, "脚本")]
        if bg and params.get("on_error", "").strip():
            targets.append((params["on_error"].strip(), "on_error 脚本"))
        for t, what in targets:
            if "{" in t:
                continue
            if not (Path(root) / t).is_file():
                probs.append(f"{where}找不到{what} {t}")
                continue
            if caller is None:
                continue
            own = script_module(t, modules)
            if own != caller:
                probs.append(f"{where}{what} {t} 不属于本模块 {caller}（脚本文件名要以「{caller}_」开头）"
                             + (f"，它归 {own}：跨模块不能执行别人的脚本，只能调它的公开函数" if own else ""))
    return probs


def check_calls(lines, svc, caller, in_func, label, funcs=None, base=0):
    """业务调用的静态检查，规则和运行时同一套（Services.lookup / check_args）。
    返回报错原话列表；label 是「文件 函数 / 接口」这段定位，base 是 lines[0] 在文件里的行号偏移。"""
    probs = []
    for i, (mod, fn_name), tail in call_sites(lines, funcs):
        mod = mod or caller
        try:
            fn = svc.lookup(caller, mod, fn_name, in_func)
        except DSLError as e:
            probs.append(f"[接口出错] {label}: 第 {base + i + 1} 行：{e}")
            continue
        given = {m.group(1).strip(): 1 for m in CALL_PARAM_RE.finditer(tail)}
        problem = svc.check_args(mod, fn, given)
        if problem:
            probs.append(f"[接口出错] {label}: 第 {base + i + 1} 行：{problem}")
    return probs


def declared_packs(text):
    """脚本 / 接口文件里「用包 a b」点名的包。"""
    out = []
    for raw in text.splitlines():
        head, rest = split_head(normalize(raw).strip())
        if head == "use":
            out += [x for x in PACK_SEP_RE.split(rest) if x]
    return out


def load_verbs(root, packs, _cache=None):
    """按「用包」点名的包建一个动词表（先看项目下的 verbs/，再看全局动词包目录）。
    包不存在就跳过：这里只做参数检查，缺包的报错留给运行期。"""
    from tools import packs as _packs
    reg = VerbRegistry(reserved=RESERVED)
    for name in packs:
        for base in (Path(root) / "verbs", _packs.verbs_root()):
            if (base / name).is_dir():
                reg.load_pack(base / name, workspace=Path(root))
                break
    return reg


def check_verb_calls(lines, reg, label, base=0):
    """动词调用的静态检查：缺必填、同一参数给两次、位置参数过多（规则和运行期 bind 同一套）。
    只看词的个数和键，不求值。返回报错原话列表。"""
    probs = []
    for i, raw in enumerate(lines):
        line = normalize(raw).strip()
        if not line or line.startswith("#"):
            continue
        head, rest = split_head(line)
        if head == "set":
            _, sep, value = rest.partition("=")
            if not sep:
                continue
            head, rest = split_head(value.strip())
        if head in RESERVED or not reg.has(head):
            continue
        if head == "报错" and BIZ_CODE_HEAD_RE.match(rest.strip()):
            continue   # 「报错 4xx 文字」是业务错误（引擎先认它），不是 common 的报错动词
        problem = reg.check_call(head, rest.split())
        if problem:
            probs.append(f"[接口出错] {label}: 第 {base + i + 1} 行：{problem}")
    return probs


# 这两个包随处能用，不用「用包」点名：routes 的 DEFAULT_PACKS 就是它俩（见 dsl_http.py），
# 这里把 services / scripts 也按同一惯例放行，省得模型照顾一个处处都要写的「用包 common http」
RESIDENT_PACKS = {"common", "http"}
_FULL_REG_CACHE = {}


def full_registry(root):
    """全部可用动词包（项目自己的 verbs/ 优先，缺的用全局）的动词表，用来查一个动词在哪个包里。按 root 路径缓存。"""
    from tools import packs as _packs
    key = str(Path(root).resolve())
    reg = _FULL_REG_CACHE.get(key)
    if reg is not None:
        return reg
    names = set(_packs.available())
    proj_verbs = Path(root) / "verbs"
    if proj_verbs.is_dir():
        names |= {p.name for p in proj_verbs.iterdir() if p.is_dir()
                  and (any(p.glob("*.zs")) or (p / "_verbs.py").is_file())}
    reg = load_verbs(root, sorted(names))
    _FULL_REG_CACHE[key] = reg
    return reg


def check_table_external_verbs(lines, reg, full, declared, label, base=0):
    """用到了没点名的包里的动词：报「用到表外动词「X」，它在「Y」包里，开头要加 用包 Y」。
    常驻包 common、http 不用点名。reg 是已点名的包建的表，full 是全部包建的表。"""
    probs = []
    allowed = set(declared) | RESIDENT_PACKS
    for i, raw in enumerate(lines):
        line = normalize(raw).strip()
        if not line or line.startswith("#"):
            continue
        head, rest = split_head(line)
        if head == "set":
            _, sep, value = rest.partition("=")
            if not sep:
                continue
            head, rest = split_head(value.strip())
        if head in RESERVED or reg.has(head) or not full.has(head):
            continue
        pack = full.pack_of(head)
        if pack in allowed:
            continue
        probs.append(f"[接口出错] {label}: 第 {base + i + 1} 行：用到表外动词「{head}」，它在「{pack}」包里，开头要加 用包 {pack}")
    return probs


def check_services(root):
    """services/*.zs：解析错误、依赖指向不存在的模块、依赖成环（Services 加载时报）；每个函数体走一遍引擎的
    解析点；函数里的调用（不存在 / 非公开 / 未声明依赖 / 缺必填 / 多出未知键）；「报错」的码要是 4xx。"""
    sdir = Path(root) / "services"
    if not sdir.is_dir() or not any(sdir.glob("*.zs")):
        return []
    svc = Services(sdir)
    probs = list(svc.errors)
    for mod in svc.modules.values():
        probs += _check_module(svc, mod)
    return probs


def _check_module(svc, mod):
    """一个模块的每个函数：函数体解析点、报错的码、函数里的调用。"""
    probs = []
    for fn in mod.funcs.values():
        label = f"{mod.rel} 函数 {fn.name}"
        body = mod.lines[fn.start:fn.end]
        e = parse_script("\n".join([""] * fn.start + body))
        if e:
            probs.append(f"[接口出错] {label}: {e}")
        for i, line in enumerate(body):
            m = BAD_BIZ_CODE_RE.match(line.strip())
            if m and not m.group(1).startswith("4"):
                probs.append(f"[接口出错] {label}: 第 {fn.start + i + 1} 行：业务错误的码要是 400–499，现在是 {m.group(1)}")
        probs += check_calls(body, svc, mod.name, True, label, mod.funcs, base=fn.start)
    return probs


def check_route_calls(text, rel, svc):
    """接口文件里的业务调用。接口属于哪个模块按文件名 routes/<模块>*.zs。"""
    probs = []
    caller = svc.module_for(rel)
    try:
        eps, _ports = split_endpoints(text, Path(rel))
    except DSLError:
        return probs
    for ep in eps:
        probs += check_calls(ep.body, svc, caller, False,
                             f"{rel} 接口 {ep.method} {ep.path}（文件第 {ep.line} 行起）",
                             base=ep.line)
    return probs


def check_text(text, rel, route):
    """一份文本按服务的方式加载。route=True：接口文件（切接口块逐块解析）；False：scripts 下的流程（整个当脚本）。
    返回问题列表，每条形如「[接口出错] 文件: 报错原话」，与服务打印的一致。"""
    if not route:
        e = parse_script(text)
        return [f"[接口出错] {rel}: {e}"] if e else []
    try:
        eps, _ports = split_endpoints(text, Path(rel))
    except DSLError as e:
        return [f"[接口出错] {rel}: {e}"]
    probs = []
    for ep in eps:
        e = parse_script(ep.script)
        if e:
            probs.append(f"[接口出错] {rel} 接口 {ep.method} {ep.path}（文件第 {ep.line} 行起）: {e}")
    return probs


def check_file(path, rel=None):
    """磁盘上的一个 .zs：scripts/ 下整个当脚本，其余（routes/）切接口块。"""
    path = Path(path)
    rel = rel or path.name
    if path.parent.name == "services":
        return _check_service_file(path, rel)
    return check_text(path.read_text(encoding="utf-8"), rel, not (path.parent.name == "scripts" or "/scripts/" in str(rel)))


def check_project(root, scripts=False):
    """全项目加载：scan_routes（接口重复、块不配对）+ 每个接口块 + scripts/*.zs 逐个解析。返回问题列表。
    scripts=True 再查 `执行` / `后台执行` 的 scripts/… 目标（check_project_scripts：脚本存在、on_error 存在、归本模块）——
    只在核查阶段（dslproj 的 加载检查 / project.load_problems）开，生成阶段（骨架、v2 逐步生成）不开：脚本是后写的，
    生成中途拦只会误拦（H1 8c7dba1 的教训）。"""
    root = Path(root)
    probs = []
    routes = root / "routes"
    try:
        scan_routes(routes)
    except DSLError as e:
        probs.append(f"[接口出错] routes: {e}")
    for f in sorted(routes.rglob("*.zs")) if routes.is_dir() else []:
        probs += check_file(f, str(f.relative_to(root)))
    sdir = root / "scripts"
    for f in sorted(sdir.rglob("*.zs")) if sdir.is_dir() else []:
        probs += check_file(f, str(f.relative_to(root)))
    # 动词调用：按每个文件「用包」点名的包查参数（缺必填 / 给两次 / 位置参数过多）+ 用到表外动词（没点名但别的包里有）
    svcdir = root / "services"
    for f in sorted(routes.rglob("*.zs")) if routes.is_dir() else []:
        probs += _check_file_verbs(root, f, True)
    for f in sorted(sdir.rglob("*.zs")) if sdir.is_dir() else []:
        probs += _check_file_verbs(root, f, False)
    for f in sorted(svcdir.rglob("*.zs")) if svcdir.is_dir() else []:
        probs += _check_file_verbs(root, f, False)
    # 业务层：services/*.zs，以及接口 / 脚本里对业务函数的调用
    probs += check_services(root)
    if (root / "services").is_dir() and any((root / "services").glob("*.zs")):
        svc = Services(root / "services")
        for f in sorted(routes.rglob("*.zs")) if routes.is_dir() else []:
            probs += check_route_calls(f.read_text(encoding="utf-8"), str(f.relative_to(root)), svc)
        for f in sorted(sdir.rglob("*.zs")) if sdir.is_dir() else []:
            lines = f.read_text(encoding="utf-8").splitlines()
            probs += check_calls(lines, svc, None, False, str(f.relative_to(root)))
    if scripts:
        probs += check_project_scripts(root)
    return probs


def check_project_scripts(root):
    """全项目 `执行` / `后台执行` scripts/… 的静态检查（见 check_script_calls）：接口 / 业务函数 / scripts 三处。
    模块名取 services/*.zs 与 contracts/*.md；调用方模块：接口按文件名 routes/<模块>*.zs、业务函数是所在模块、
    脚本按文件名前缀 scripts/<模块>_*.zs（对不上任何模块的 = 调用方未知，只查存在）。"""
    root = Path(root)
    modules = {f.stem for f in (root / "services").glob("*.zs")} if (root / "services").is_dir() else set()
    modules |= {f.stem for f in (root / "contracts").glob("*.md")} if (root / "contracts").is_dir() else set()
    probs = []
    routes = root / "routes"
    for f in sorted(routes.rglob("*.zs")) if routes.is_dir() else []:
        rel = str(f.relative_to(root))
        caller = max((m for m in modules if f.stem.startswith(m)), key=len, default=None)
        try:
            eps, _ports = split_endpoints(f.read_text(encoding="utf-8"), Path(rel))
        except DSLError:
            continue
        for ep in eps:
            probs += check_script_calls(ep.body, root, caller, modules,
                                        f"{rel} 接口 {ep.method} {ep.path}（文件第 {ep.line} 行起）", base=ep.line)
    sdir = root / "services"
    if sdir.is_dir() and any(sdir.glob("*.zs")):
        svc = Services(sdir)
        for mod in svc.modules.values():
            for fn in mod.funcs.values():
                probs += check_script_calls(mod.lines[fn.start:fn.end], root, mod.name, modules,
                                            f"{mod.rel} 函数 {fn.name}", base=fn.start)
    scdir = root / "scripts"
    for f in sorted(scdir.rglob("*.zs")) if scdir.is_dir() else []:
        probs += check_script_calls(f.read_text(encoding="utf-8").splitlines(), root, script_module(f.name, modules), modules,
                                    str(f.relative_to(root)))
    return probs


def _check_file_verbs(root, f, route):
    text = f.read_text(encoding="utf-8")
    packs = declared_packs(text)
    rel = str(f.relative_to(root))
    reg = load_verbs(root, packs) if packs else VerbRegistry(reserved=RESERVED)
    full = full_registry(root)
    if not route:
        lines = text.splitlines()
        probs = check_verb_calls(lines, reg, rel) if packs else []
        probs += check_table_external_verbs(lines, reg, full, packs, rel)
        return probs
    try:
        eps, _ports = split_endpoints(text, Path(rel))
    except DSLError:
        return []
    probs = []
    for ep in eps:
        label = f"{rel} 接口 {ep.method} {ep.path}（文件第 {ep.line} 行起）"
        if packs:
            probs += check_verb_calls(ep.body, reg, label, base=ep.line)
        probs += check_table_external_verbs(ep.body, reg, full, packs, label, base=ep.line)
    return probs


def _check_service_file(path, rel):
    """单个业务文件：解析 + 函数体 + 函数里的调用。依赖 / 调用别的模块要看同目录的其他业务文件，
    所以整个目录加载一遍，只报属于这个文件的问题（依赖成环的算）。"""
    svc = Services(path.parent)
    probs = [e for e in svc.errors if f"services/{path.name}" in e or "依赖成环" in e]
    mod = svc.modules.get(path.stem)
    return probs + (_check_module(svc, mod) if mod is not None else [])
