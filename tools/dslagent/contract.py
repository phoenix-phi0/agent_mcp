"""modular 的「接口约定」：每个模块先把 sql / 流程 / 接口 / 界面的对外形状约定下来，程序校验后冻结；
之后每个文件只按约定实现，不再照着别的文件的真实内容对接。

约定的源头是模型写的**骨架文件**（真实路径上的 queries/*.sql、scripts/*.zs、routes/*.zs、ui/*.ui，只有头部声明，格式见 skeleton.py），
skeleton.extract 把骨架解析成下面这个 dict（一个模块一份），validate_contract 校验；contracts.json / CONTRACTS.md 只是从骨架生成的只读产物：
  sql   [{名, 参数:[{名, 要求:必填|可选}], 返回:[列…]|"写入", 作用, 表:[实体…], 用列:["表.列"|"列"…], 规则:[R#…]}]
  流程  [{名, 入参:[{名, 要求}], 出参:[键…], 写哪些表:[…], 调:[{名, 给:[键…]}], 用动词:[…], 业务错误:[{情形, 返回}], 作用, 规则}]
  接口  [{文件, 路径, 动作, 角色, 请求字段:[{名, 要求}], 调用:[{名, 给:[键…]}], 响应:{state:[键], lists:[键], messages:是|否}, 业务错误:[{码, 情形}], 作用, 规则}]
  界面  [{页, 用接口:[路径…], 字段:[…]}]
程序不调模型：validate_contract 校验引用、参数、层次、动词、规则；
check_* 比对实现与约定；derive_* 把约定项转成单文件计划的形状（实现步骤直接用，不再另外规划）。
"""
import json
import re
import sqlite3

SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
IDENT = re.compile(r"^[A-Za-z_]\w*$")
REQ_OK = ("必填", "是", True, "true", "True", 1)
REQ_OPT = ("可选", "否", False, "false", "False", 0)
GEN_SUFFIX = ("list", "one", "insert", "update", "delete")


def _list(v):
    return v if isinstance(v, list) else []


def _names(v, what, errs):
    out = []
    if v in (None, ""):
        return out
    if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
        errs.append(f"{what} 要是字符串列表")
        return out
    return [x.strip() for x in v]


def _params(v, what, errs):
    """[{名, 要求}] → [{"名","要求"}]；也收纯名字（= 必填）。"""
    out, seen = [], set()
    if v in (None, ""):
        return out
    if not isinstance(v, list):
        errs.append(f"{what} 要是列表 [{{名, 要求:必填|可选}}]")
        return out
    for p in v:
        if isinstance(p, str):
            n, r = p, "必填"
        elif isinstance(p, dict):
            n = p.get("名")
            raw = p.get("要求", p.get("必填", "必填"))
            if raw in REQ_OK:
                r = "必填"
            elif raw in REQ_OPT:
                r = "可选"
            else:
                errs.append(f"{what} 里「{n}」的要求「{raw}」只能是 必填 或 可选")
                continue
        else:
            errs.append(f"{what} 的项要是 {{名, 要求}}")
            continue
        if not isinstance(n, str) or not IDENT.match(n):
            errs.append(f"{what} 里的名字「{n}」不是合法标识符")
            continue
        if n in seen:
            errs.append(f"{what} 里「{n}」重复")
            continue
        seen.add(n)
        out.append({"名": n, "要求": r})
    return out


def req_opt(ps):
    return [p["名"] for p in ps if p["要求"] == "必填"], [p["名"] for p in ps if p["要求"] == "可选"]


def _calls(v, what, errs):
    """[{名, 给}]；只写名字不行——要写给了哪些键，才能核对参数。"""
    out = []
    if v in (None, ""):
        return out
    if not isinstance(v, list):
        errs.append(f"{what} 要是列表 [{{名, 给:[键…]}}]")
        return out
    for c in v:
        if not isinstance(c, dict) or not isinstance(c.get("名"), str):
            errs.append(f"{what} 的项要是 {{名, 给:[键…]}}（只写名字没法核对参数）")
            continue
        if not isinstance(c.get("给"), list):
            errs.append(f"{what} 里调用「{c['名']}」要写 给:[键…]（没有参数就写 []）")
            continue
        out.append({"名": c["名"], "给": [str(k) for k in c["给"]]})
    return out


def _rules(v, what, nums, errs):
    rs = _names(v, what, errs)
    for h in rs:
        if h not in nums:
            errs.append(f"{what} 的规则「{h}」不是分给本模块的规则 {sorted(nums)}")
    return rs


def _cols_ok(cols, tables, ents, what, errs):
    pool = set()
    for t in tables or ents:
        pool |= ents.get(t, set())
    for c in cols:
        if "." in c:
            t, _, col = c.partition(".")
            if t not in ents:
                errs.append(f"{what} 的用列「{c}」：表「{t}」不是本模块或依赖模块的实体 / gen 生成的表（可用：{sorted(ents)}）")
            elif col not in ents[t]:
                errs.append(f"{what} 的用列「{c}」：表「{t}」没有列「{col}」（列：{sorted(ents[t])}）")
        elif c not in pool:
            errs.append(f"{what} 的用列「{c}」不在{'表 ' + '、'.join(tables) if tables else '可见实体'}的列里（列：{sorted(pool)[:40]}）")


def validate_contract(obj, ctx):
    """校验一个模块的约定（obj：已解析的 JSON 对象）。返回 {ok, errors, contract}。ctx 见 modbuild.ModRun.contract_ctx。"""
    if not isinstance(obj, dict):
        return {"ok": False, "errors": ["约定要是 JSON 对象 {sql, 流程, 接口, 界面}"], "contract": None}
    m, v = ctx["mod"], ctx["v"]
    ents, nums = ctx["ents"], set(v["规则号"])
    errs = []
    own_tables = set(ctx.get("own_tables") or ())
    # ---- sql
    sqls, seen_sql = [], {}
    for s in _list(obj.get("sql")):
        if not isinstance(s, dict):
            errs.append("sql 项要是对象")
            continue
        n = s.get("名")
        if not isinstance(n, str) or not SNAKE.match(n):
            errs.append(f"sql 名「{n}」要是英文小写 snake")
            continue
        if not n.startswith(m + "_"):
            errs.append(f"sql 名「{n}」要以「{m}_」开头")
        if n in ctx["gen_sqls"]:
            errs.append(f"sql 名「{n}」与 gen 自动生成的重名（<实体>_list/one/insert/update/delete 不用写）")
        elif n in ctx["taken_sqls"] or n in seen_sql:
            errs.append(f"sql 名「{n}」项目里已经有了 / 重复")
        ps = _params(s.get("参数"), f"sql「{n}」的参数", errs)
        ret = s.get("返回")
        if ret != "写入":
            ret = _names(ret, f"sql「{n}」的返回", errs)
            if not ret:
                errs.append(f"sql「{n}」的返回要是列名列表（查询）或 \"写入\"")
        tabs = _names(s.get("表"), f"sql「{n}」的表", errs)
        for t in tabs:
            if t not in ents:
                errs.append(f"sql「{n}」的表「{t}」不是本模块或依赖模块的实体 / gen 生成的表（可用：{sorted(ents)}）")
        cols = _names(s.get("用列"), f"sql「{n}」的用列", errs)
        _cols_ok(cols, [t for t in tabs if t in ents], ents, f"sql「{n}」", errs)
        item = {"名": n, "参数": ps, "返回": ret, "作用": str(s.get("作用") or ""), "表": tabs, "用列": cols,
                "规则": _rules(s.get("规则"), f"sql「{n}」", nums, errs)}
        seen_sql[n] = item
        sqls.append(item)
    # ---- 流程
    declared = {f["名"]: f for f in v["流程"]}
    flows, seen_f = [], {}
    for f in _list(obj.get("流程")):
        if not isinstance(f, dict):
            errs.append("流程项要是对象")
            continue
        n = f.get("名")
        if n not in declared:
            errs.append(f"流程「{n}」不在层次×模块给本模块定的流程里（{sorted(declared)}），不许多出流程")
            continue
        if n in seen_f:
            errs.append(f"流程「{n}」重复")
            continue
        ins = _params(f.get("入参"), f"流程「{n}」的入参", errs)
        outs = _names(f.get("出参"), f"流程「{n}」的出参", errs)
        if not outs:
            errs.append(f"流程「{n}」的出参不能空：流程要返回点什么，接口才能用 {{result.键}}")
        tabs = _names(f.get("写哪些表"), f"流程「{n}」的写哪些表", errs)
        for t in tabs:
            if t not in ents:
                errs.append(f"流程「{n}」写的表「{t}」不是可见实体（可用：{sorted(ents)}）")
        verbs = _names(f.get("用动词"), f"流程「{n}」的用动词", errs)
        for vb in verbs:
            if vb not in ctx["verbs"]:
                errs.append(f"流程「{n}」的用动词「{vb}」不在能力清单里（不许编造）")
        errors = _biz(f.get("业务错误"), ("情形", "返回"), f"流程「{n}」的业务错误", errs)
        item = {"名": n, "入参": ins, "出参": outs, "写哪些表": tabs, "调": _calls(f.get("调"), f"流程「{n}」的调", errs), "用动词": verbs,
                "业务错误": errors, "作用": str(f.get("作用") or declared[n].get("作用") or ""), "规则": _rules(f.get("规则"), f"流程「{n}」", nums, errs)}
        seen_f[n] = item
        flows.append(item)
    for n in declared:
        if n not in seen_f:
            errs.append(f"层次×模块里的流程「{n}」没有约定（不许少）")
    # ---- 接口
    files = {f["文件"] for f in v["接口"]}
    ifaces, paths, acts = [], set(), set()
    for a in _list(obj.get("接口")):
        if not isinstance(a, dict):
            errs.append("接口项要是对象")
            continue
        p, an, fl = a.get("路径"), a.get("动作"), a.get("文件")
        if fl not in files:
            errs.append(f"接口「{p}」的文件「{fl}」不在层次×模块给本模块定的接口文件里（{sorted(files)}）")
        if not isinstance(p, str) or not p.startswith("/"):
            errs.append(f"接口路径「{p}」要以 / 开头")
            continue
        if p in ctx["taken_paths"] or p in paths:
            errs.append(f"接口路径「{p}」已被占用 / 重复")
        paths.add(p)
        if not isinstance(an, str) or not SNAKE.match(an):
            errs.append(f"接口「{p}」的动作名「{an}」要是英文小写 snake")
        elif an in ctx["taken_acts"] or an in acts:
            errs.append(f"动作名「{an}」已被占用 / 重复")
        acts.add(an)
        role = a.get("角色") or ""
        if role and role not in ctx["roles"]:
            errs.append(f"接口「{p}」的角色「{role}」不在项目角色 {ctx['roles'] or '（没有角色）'} 里")
        resp = a.get("响应")
        if not isinstance(resp, dict):
            errs.append(f"接口「{p}」要有「响应」：{{state:[键], lists:[键], messages:是|否}}")
            resp = {}
        msg = str(resp.get("messages") or "否")
        if msg not in ("是", "否"):
            errs.append(f"接口「{p}」响应.messages 只能是 是 或 否")
        item = {"文件": fl, "路径": p, "动作": an, "角色": role, "请求字段": _params(a.get("请求字段"), f"接口「{p}」的请求字段", errs),
                "调用": _calls(a.get("调用"), f"接口「{p}」的调用", errs),
                "响应": {"state": _names(resp.get("state"), f"接口「{p}」响应.state", errs), "lists": _names(resp.get("lists"), f"接口「{p}」响应.lists", errs), "messages": msg},
                "业务错误": _biz(a.get("业务错误"), ("码", "情形"), f"接口「{p}」的业务错误", errs), "作用": str(a.get("作用") or ""),
                "规则": _rules(a.get("规则"), f"接口「{p}」", nums, errs)}
        for e in item["业务错误"]:
            if not str(e["码"]).isdigit() or not 400 <= int(e["码"]) < 500:
                errs.append(f"接口「{p}」的业务错误码「{e['码']}」要是 4xx")
        ifaces.append(item)
    for fl in files:
        if not any(i["文件"] == fl for i in ifaces):
            errs.append(f"接口文件「{fl}」里一个接口也没约定")
    # ---- 界面
    pages = {u["名"] for u in v["界面"]}
    uis, seen_u = [], set()
    avail = set(ctx["ui_paths"]) | paths
    for u in _list(obj.get("界面")):
        if not isinstance(u, dict) or u.get("页") not in pages:
            errs.append(f"界面项的页「{u.get('页') if isinstance(u, dict) else u}」不在层次×模块给本模块定的界面里（{sorted(pages)}）")
            continue
        if u["页"] in seen_u:
            errs.append(f"界面「{u['页']}」重复")
        seen_u.add(u["页"])
        used = _names(u.get("用接口"), f"界面「{u['页']}」的用接口", errs)
        for p in used:
            if p not in avail:
                errs.append(f"界面「{u['页']}」用的接口「{p}」不存在（可用：{sorted(avail)[:40]}）")
        uis.append({"页": u["页"], "用接口": used, "字段": _names(u.get("字段"), f"界面「{u['页']}」的字段", errs)})
    for pg in pages - seen_u:
        errs.append(f"层次×模块里的界面「{pg}」没有约定（不许少）")
    # ---- 引用 / 参数 / 层次 / 规则
    sigs = {**{k: s for k, s in ctx["sql_known"].items()}, **{s["名"]: s for s in sqls}}
    fsigs = {**ctx["flows_ext"], **{f["名"]: f for f in flows}}
    ipaths = {i["路径"] for i in ifaces} | set(ctx["ui_paths"])
    other_flows = set(ctx.get("other_flows") or ()) - set(fsigs)

    def callee(owner, c, may_flow, may_sql):
        n = c["名"]
        if n in sigs and may_sql:
            r, o = req_opt(sigs[n]["参数"])
            kind = "sql"
        elif n in fsigs and may_flow:
            r, o = req_opt(fsigs[n]["入参"])
            kind = "流程"
        elif n in ipaths or n.startswith("/"):
            errs.append(f"{owner} 调了接口「{n}」：越层（只能 界面→接口→流程→sql，不能往上调）")
            return
        elif n in sigs or n in fsigs:
            errs.append(f"{owner} 不能调「{n}」（这一层只能调 {'流程 / ' if may_flow else ''}{'sql' if may_sql else ''}）")
            return
        elif n in other_flows:
            errs.append(f"{owner} 调了别的模块的流程「{n}」：跨模块只能调顶层「共用流程」规定给本模块用的（可调：{sorted(ctx['flows_ext'])}）")
            return
        else:
            errs.append(f"{owner} 调的「{n}」不存在（sql：{sorted(sigs)[:30]}；流程：{sorted(fsigs)}）")
            return
        miss = sorted(set(r) - set(c["给"]))
        extra = sorted(set(c["给"]) - set(r) - set(o))
        if miss:
            errs.append(f"{owner} 调{kind}「{n}」缺必填参数 {miss}（它的参数 必填 {r}，可选 {o}）")
        if extra:
            errs.append(f"{owner} 调{kind}「{n}」多给了它没约定的键 {extra}（必填 {r}，可选 {o}）")
        return kind

    for f in flows:
        used_flows = []
        for c in f["调"]:
            k = callee(f"流程「{f['名']}」", c, True, True)
            if k == "流程":
                used_flows.append(c["名"])
        for d in declared[f["名"]]["调流程"]:
            if d not in used_flows:
                errs.append(f"层次×模块里流程「{f['名']}」要调流程「{d}」，「调」里要写上")
        for t in f["写哪些表"]:
            if t not in own_tables | set(ents):
                errs.append(f"流程「{f['名']}」写的表「{t}」不是可见实体")
    for a in ifaces:
        for c in a["调用"]:
            callee(f"接口「{a['路径']}」", c, True, True)
    cyc = _cycle({f["名"]: [c["名"] for c in f["调"] if c["名"] in seen_f] for f in flows})
    if cyc:
        errs.append("流程互调成环：" + " → ".join(cyc))
    for fl in files:
        need = ctx.get("must_by_file", {}).get(fl, [])
        called = {c["名"] for i in ifaces if i["文件"] == fl for c in i["调用"]}
        for n in need:
            if n not in called:
                errs.append(f"层次×模块规定流程「{n}」给接口文件「{fl}」用，但这个文件的接口调用里没有它")
    covered = {h for grp in (sqls, flows, ifaces) for it in grp for h in it["规则"]}
    for h in v["规则号"]:
        if h not in covered:
            errs.append(f"本模块的规则 {h} 没有落在任何约定项上（sql / 流程 / 接口的「规则」里要写它）")
    if errs:
        return {"ok": False, "errors": errs, "contract": None}
    for grp in (flows, ifaces):
        for it in grp:
            for c in it.get("调", it.get("调用", [])):
                c["类"] = "sql" if c["名"] in sigs else "流程"
    return {"ok": True, "errors": [], "contract": {"模块": m, "sql": sqls, "流程": flows, "接口": ifaces, "界面": uis}}


def _biz(v, keys, what, errs):
    out = []
    if v in (None, ""):
        return out
    if not isinstance(v, list):
        errs.append(f"{what} 要是 [{{{keys[0]}, {keys[1]}}}] 列表")
        return out
    for e in v:
        if not isinstance(e, dict) or any(k not in e for k in keys):
            errs.append(f"{what} 的项要有 {keys[0]} 和 {keys[1]}")
            continue
        out.append({keys[0]: e[keys[0]], keys[1]: str(e[keys[1]])})
    return out


def _cycle(g):
    state = {}

    def visit(n, path):
        state[n] = 1
        for d in g.get(n, ()):
            if state.get(d) == 1:
                return path + [n, d]
            if d not in state:
                c = visit(d, path + [n])
                if c:
                    return c
        state[n] = 2
        return None
    for n in g:
        if n not in state:
            c = visit(n, [])
            if c:
                return c
    return None


# ================================================================== 约定 → 单文件计划（实现步骤用）

def derive_sql(c, mod_sqls=None):
    """本模块的 sql 约定 → f_query 的单文件计划形状。"""
    out = []
    for s in c["sql"]:
        r, o = req_opt(s["参数"])
        out.append({"名": s["名"], "参数": [*r, *o], "可选参数": o, "说明": s["作用"], "规则": list(s["规则"])})
    return {"sql": out}


def derive_flow(f):
    r, o = req_opt(f["入参"])
    sqls = [c["名"] for c in f["调"] if c.get("类") == "sql"]
    return {"入参": r, "可选入参": o, "出参": list(f["出参"]), "用sql": sqls, "用流程": [c["名"] for c in f["调"] if c.get("类") == "流程"],
            "用动词": list(f["用动词"]), "规则": list(f["规则"]), "步骤": [f["作用"] or f["名"]]}


def derive_iface(items):
    out = []
    for a in items:
        r, o = req_opt(a["请求字段"])
        out.append({"路径": a["路径"], "动作": a["动作"], "角色": a["角色"], "入参": [*r, *o], "可选入参": o,
                    "用sql": [c["名"] for c in a["调用"] if c.get("类") == "sql"],
                    "用流程": [c["名"] for c in a["调用"] if c.get("类") == "流程"],
                    "调用": {c["名"]: list(c["给"]) for c in a["调用"] if c.get("类") == "流程"},
                    "规则": list(a["规则"]), "说明": a["作用"], "响应": a["响应"], "业务错误": a["业务错误"]})
    return {"接口": out}


def derive_ui(u):
    return {"页面": [{"名": u["页"], "说明": "", "用接口": list(u["用接口"]), "字段": list(u["字段"])}]}


def contracts_md(top, contracts):
    L = ["# 接口约定（CONTRACTS）", "", "由骨架文件生成的只读产物（源头是 queries/*.sql、scripts/*.zs、routes/*.zs、ui/*.ui 头部的声明）；每个模块先约定、再按约定实现，约定通过程序校验后冻结。参数后带 `?` = 可选。", ""]

    def ps(xs):
        return "、".join(p["名"] + ("?" if p["要求"] == "可选" else "") for p in xs) or "—"
    for m in top["构建顺序"]:
        c = contracts.get(m)
        L += [f"## {m}", ""]
        if not c:
            L += ["（约定没写成）", ""]
            continue
        if c["sql"]:
            L += ["### sql", "", "| 名 | 参数 | 返回 | 作用 | 规则 |", "|---|---|---|---|---|"]
            L += [f"| {s['名']} | {ps(s['参数'])} | {'写入' if s['返回'] == '写入' else '、'.join(s['返回'])} | {s['作用']} | {'、'.join(s['规则']) or '—'} |" for s in c["sql"]]
            L.append("")
        if c["流程"]:
            L += ["### 流程", ""]
            for f in c["流程"]:
                L += [f"- **{f['名']}**：{f['作用']}；入参 {ps(f['入参'])}；出参 {'、'.join(f['出参'])}；写表 {'、'.join(f['写哪些表']) or '—'}；"
                      f"调 {'、'.join(x['名'] + '(' + ','.join(x['给']) + ')' for x in f['调']) or '—'}；动词 {'、'.join(f['用动词']) or '—'}；"
                      f"业务错误 {'；'.join(str(e['情形']) + '→' + e['返回'] for e in f['业务错误']) or '—'}；规则 {'、'.join(f['规则']) or '—'}"]
            L.append("")
        if c["接口"]:
            L += ["### 接口", ""]
            for a in c["接口"]:
                r = a["响应"]
                L += [f"- **POST {a['路径']}**（{a['文件']}.zs，动作 {a['动作']}，角色 {a['角色'] or '不限'}）：{a['作用']}；请求 {ps(a['请求字段'])}；"
                      f"调用 {'、'.join(x['名'] + '(' + ','.join(x['给']) + ')' for x in a['调用']) or '—'}；响应 state {r['state']} lists {r['lists']} messages {r['messages']}；"
                      f"业务错误 {'；'.join(str(e['码']) + ' ' + str(e['情形']) for e in a['业务错误']) or '—'}；规则 {'、'.join(a['规则']) or '—'}"]
            L.append("")
        if c["界面"]:
            L += ["### 界面", ""]
            L += [f"- **{u['页']}**：用接口 {'、'.join(u['用接口']) or '—'}；字段 {'、'.join(u['字段']) or '—'}" for u in c["界面"]]
            L.append("")
    return "\n".join(L)


# ================================================================== 实现 vs 约定

def sql_result_cols(sql_text, entities_sql):
    """在内存库里（按实体建好表）把 sql 跑一遍（参数全给 NULL）看返回哪些列。写操作 / 跑不通 → None。"""
    text = re.sub(r"/\*.*?\*/", " ", sql_text, flags=re.S)
    text = "\n".join(l.split("--", 1)[0] for l in text.splitlines()).strip().rstrip(";")
    if not re.match(r"(?is)^\s*(select|with)\b", text):
        return "写入"
    con = sqlite3.connect(":memory:")
    try:
        con.executescript(entities_sql)
        params = {p: None for p in set(re.findall(r"(?<!:):([A-Za-z_]\w*)", re.sub(r"'(?:[^']|'')*'", "''", text)))}
        cur = con.execute(text, params)
        return [d[0] for d in cur.description or []]
    except sqlite3.Error:
        return None
    finally:
        con.close()


def check_sql_returns(name, item, actual):
    """sql 实现与约定的返回列一致。actual：sql_result_cols 的结果（None = 判不了，放过）。"""
    want = item["返回"]
    if actual is None:
        return []
    if want == "写入":
        return [] if actual == "写入" else [f"sql「{name}」约定是「写入」，实现却是查询（返回 {actual}）"]
    if actual == "写入":
        return [f"sql「{name}」约定返回列 {want}，实现却是写操作（不是 SELECT）"]
    if set(actual) != set(want):
        return [f"sql「{name}」返回的列与约定不符：约定 {sorted(want)}，实际 {sorted(actual)}"]
    return []


def check_calls_match(owner, text, want_sql, want_flows, sql_names_fn, flow_names_fn):
    """实现里调用的 sql / 流程要和约定的一致（不多不少）。"""
    got_sql, got_flows = set(sql_names_fn(text)), set(flow_names_fn(text))
    errs = []
    for n in sorted(set(want_sql) - got_sql):
        errs.append(f"{owner} 约定要用 sql「{n}」，实现里没有调它")
    for n in sorted(got_sql - set(want_sql)):
        errs.append(f"{owner} 实现里用了约定之外的 sql「{n}」（约定的：{sorted(want_sql)}）")
    for n in sorted(set(want_flows) - got_flows):
        errs.append(f"{owner} 约定要调流程「{n}」，实现里没有调它")
    for n in sorted(got_flows - set(want_flows)):
        errs.append(f"{owner} 实现里调了约定之外的流程「{n}」（约定的：{sorted(want_flows)}）")
    return errs


def check_response(path, resp, body):
    """接口块里要出现约定的响应键：state / lists 的每个键、messages=是 时要有消息输出。宽松的文本核对。"""
    errs = []
    for k in resp.get("state", []):
        if not re.search(rf"(?<![\w.]){re.escape(k)}(?!\w)", body):
            errs.append(f"接口「{path}」约定 state 里有「{k}」，实现里没出现它")
    for k in resp.get("lists", []):
        if not re.search(rf"(?<![\w.]){re.escape(k)}(?!\w)", body):
            errs.append(f"接口「{path}」约定 lists 里有「{k}」，实现里没出现它")
    if resp.get("messages") == "是" and not re.search(r"(^|\s)(消息|响应\s+messages)\b|\"messages\"", body, re.M):
        errs.append(f"接口「{path}」约定 messages=是，实现里没有「消息 …」或「响应 messages …」")
    return errs


def check_ui_actions(page, text, want_actions):
    """界面里用到的远程动作要正好是约定「用接口」对应的动作。want_actions：{动作名}。"""
    got = set(re.findall(r"动作\s+(\S+)\s+远程", text))
    errs = []
    for a in sorted(want_actions - got):
        errs.append(f"界面「{page}」约定用的接口动作「{a}」，界面里没有 `动作 {a} 远程 …`")
    for a in sorted(got - want_actions):
        errs.append(f"界面「{page}」用了约定之外的接口动作「{a}」（约定的：{sorted(want_actions)}）")
    return errs
