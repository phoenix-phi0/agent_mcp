"""全局程序检查：全部约定都通过各自的检查之后跑一次，不调模型。查两类跨模块重复：
同一「方法 + 路径」在两个模块的「## 接口」里都定义、同一张表名在两个模块的「## 表」里都定义
（约定检查已经要求表名以「模块名_」开头，正常不该撞，这里兜底防拼错 / 抄错）；
以及「认证 核对」「认证 身份」各模块写得不一样（路由层整个项目只认一种，不一致加载就报错，冒烟起不来）。

check(project, top) -> {"条数": n, "按模块": {模块: [问题…]}, "摘要": 摘要文本}；没问题 条数=0。

deps_mismatch(project, top) -> 依赖与 plan/top.zs 不一致的问题（约定检查只要求依赖是 top 里的模块且不成环，不要求
逐字一致；「规划到通过 约定」跑完后本该用「同步顶层依赖」把 top.zs 改成与约定一致——这个检查给 核查.zs 用，
查的是没跑同步、或同步之后又有约定改了依赖但没再同步的情形；不并入 check()，因为 check() 在旧流程「规划到通过 约定」
里跑在「同步顶层依赖」之前，这时候约定和 top.zs 本来就还没同步，不能算问题）。

「多余依赖」（声明的依赖没被调用）和「调用了上游不存在 / 非公开的函数」已经在单模块检查里做了
（tools/dslagent/packs/dslproj/contract.check，逐个约定过检查时就会查出来），核查.zs 不重复查，程序检查结果里
由 全局检查 + deps_mismatch 一起给。
"""
from collections import defaultdict

from ..packs.dslproj import contract as C
from . import contracts as VC


AUTH_RIGHT = "正确写法：`认证 核对 app.db account_by_name`——第一个参数是库文件名（以 .db 结尾），第二个是 queries/<名>.sql 的查询名（参数 :username，返回行含 role 列）"


def _auth_check_problems(project, top):
    """「认证 核对 <库> <查询名>」真路由（tools/dsl_http.py check_user）的要求：库参数是 .db 文件名；
    查询名对应 queries/<名>.sql，不存在每个带登录态的请求都会 500。
    代码阶段（queries/ 下已有 .sql）：文件必须存在。约定阶段（queries/ 还没写）：约定里除认证行外要提到这个查询名，
    且不能直接用表名当查询名（`account account_user` 就是把表名当成了查询）。→ [(模块, 问题)]"""
    import re
    from pathlib import Path
    qdir = Path(project) / "queries"
    code_phase = qdir.is_dir() and any(qdir.glob("*.sql"))
    out = []
    for m in top["模块"]:
        name = m["名"]
        f = VC.path_of(project, name)
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8")
        c, probs = C.parse(text)
        if probs or len(c["认证"]["核对"] or []) != 2:
            continue
        db, q = c["认证"]["核对"]
        if not db.endswith(".db"):
            out.append((name, f"「认证 核对 {db} {q}」的库参数不对：第一个参数要是库文件名（以 .db 结尾），不是 {db}；{AUTH_RIGHT}"))
        if code_phase or (qdir / f"{q}.sql").is_file():
            if not (qdir / f"{q}.sql").is_file():
                out.append((name, f"「认证 核对 {db} {q}」指的查询 queries/{q}.sql 不存在，真实路由每个带登录态的请求都会 500；"
                                  f"要么新增这个查询文件，要么把第二个参数改成 queries/ 里已有的查询名。{AUTH_RIGHT}"))
            continue
        body = "\n".join(l for l in text.splitlines() if not l.strip().startswith("认证 核对"))
        tables = {t["名"] for mc in top["模块"] for t in _tables_of(project, mc["名"])}
        if q in tables or not re.search(rf"(?<![\w]){re.escape(q)}(?![\w])", body):
            out.append((name, f"「认证 核对 {db} {q}」的第二个参数 {q} 不是一个声明过的查询（它是表名，或约定里没有任何地方说明这条查询）；"
                              f"第二个参数是 queries/<名>.sql 的查询名，要在约定里（函数伪代码）写明"
                              f"「查询 {q}：按 username 查 <账号表>，返回含 role 列」。{AUTH_RIGHT}"))
    return out


def _tables_of(project, name):
    f = VC.path_of(project, name)
    if not f.is_file():
        return []
    c, probs = C.parse(f.read_text(encoding="utf-8"))
    return [] if probs else c["表"]


def check(project, top):
    by_route, by_table = defaultdict(set), defaultdict(set)
    by_auth = {"核对": defaultdict(set), "身份": defaultdict(set)}
    for m in top["模块"]:
        name = m["名"]
        f = VC.path_of(project, name)
        if not f.is_file():
            continue
        c, probs = C.parse(f.read_text(encoding="utf-8"))
        if probs:
            continue
        for i in c["接口"]:
            by_route[(i["方法"], i["路径"])].add(name)
        for t in c["表"]:
            by_table[t["名"]].add(name)
        for kind, groups in by_auth.items():
            if c["认证"][kind]:
                groups[tuple(c["认证"][kind])].add(name)
    per_module = defaultdict(list)
    for kind, groups in by_auth.items():
        if len(groups) > 1:
            # 多数派为准（并列取写法靠前的）；其余模块照它改
            keep = max(sorted(groups), key=lambda k: len(groups[k]))
            for k, mods in sorted(groups.items()):
                if k != keep:
                    for m in sorted(mods):
                        per_module[m].append(f"「认证 {kind}」与其他模块不一致：本模块写「认证 {kind} {' '.join(k)}」，"
                                             f"{'、'.join(sorted(groups[keep]))} 写「认证 {kind} {' '.join(keep)}」；整个项目只能有一种写法，照后者改")
    for m, msg in _auth_check_problems(project, top):
        per_module[m].append(msg)
    for (method, path), mods in sorted(by_route.items()):
        if len(mods) > 1:
            msg = f"接口「{method} {path}」在模块 {'、'.join(sorted(mods))} 里都定义了，一个方法+路径只能属于一个模块"
            for m in mods:
                per_module[m].append(msg)
    for table, mods in sorted(by_table.items()):
        if len(mods) > 1:
            msg = f"表「{table}」在模块 {'、'.join(sorted(mods))} 里都定义了，一张表只能属于一个模块"
            for m in mods:
                per_module[m].append(msg)
    total = sum(len(v) for v in per_module.values())
    brief = "；".join(f"{m}：{'; '.join(v)}" for m, v in sorted(per_module.items()))
    return {"条数": total, "按模块": dict(per_module), "摘要": brief}


def deps_mismatch(project, top):
    """→ {模块: [问题…]}（只有不一致的模块才有键）。"""
    per_module = defaultdict(list)
    top_deps = {m["名"]: set(m["依赖"]) for m in top["模块"]}
    for m in top["模块"]:
        name = m["名"]
        f = VC.path_of(project, name)
        if not f.is_file():
            continue
        c, probs = C.parse(f.read_text(encoding="utf-8"))
        if probs:
            continue
        if set(c["依赖"]) != top_deps.get(name, set()):
            per_module[name].append(
                f"依赖与 plan/top.zs 不一致：约定写的依赖是 {sorted(c['依赖']) or '无'}，"
                f"top.zs 写的是 {sorted(top_deps.get(name, set())) or '无'}（跑「同步顶层依赖」或手动对齐）")
    return dict(per_module)


def full_check(project, top):
    """核查.zs 用的程序检查汇总：check() + deps_mismatch()。→ {"条数", "按模块", "摘要"}。"""
    g = check(project, top)
    per_module = defaultdict(list, {m: list(v) for m, v in g["按模块"].items()})
    for m, probs in deps_mismatch(project, top).items():
        per_module[m].extend(probs)
    total = sum(len(v) for v in per_module.values())
    brief = "；".join(f"{m}：{'; '.join(v)}" for m, v in sorted(per_module.items()))
    return {"条数": total, "按模块": dict(per_module), "摘要": brief}
