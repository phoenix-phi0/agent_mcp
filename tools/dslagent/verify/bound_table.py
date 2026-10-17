"""边界复核的「期望表」路径（verify/code.py 的 boundary 用）：规划时让模型写一张期望表（性质断言为主），改完后程序按表调用函数核对，
不再让模型写 unittest。依据 /workspace/dslagent_exp/bound_code4/REPORT.md（断言表 + 失败时判表错：误报 0/28、检出 38/40、正确代码 ~3.5s、0.39 次调用）。

规划阶段（零模型调用）：
  split_table(raw)            规划回复里 `#期望表` 之后的块切出来 → (去掉表的回复, 表行|None, 说明)
  planned_units(checklist)    计划 #清单 里要改 / 新建的函数
  table_check(task, rows, units, notes)  规则覆盖率（≥70%）+ 每个改动函数 ≥2 条 → 达标与否；不达标由 v2 补表 1 次（fill_user / parse_rows）
  fixture_notes(text)         按提到的模块从 fixtures/modules.json 取专用夹具说明（追加到规划 / 补表的 user，不写死在 system）

改完后：
  changed_callables(base, cur) / validate(rows, ...)   按改后代码的真实签名校验表项（函数名、参数名、必填参数、断言词表），不对的丢弃并计数
  run_cases(...)              子进程（fixtures/child.py）在临时工作区里调用，HOME / CBATCH_HOME / GBATCH_HOME 指向临时目录，单次 5 秒，
                              结果上限 200000 字符；含「同改前」的条目在 base 快照还原出的改前副本上再跑一次
  judge_all(...)              期望 / 断言判定（断言见 asserts.py）
  judge_user / parse_judge    失败条目交给 bound_judge 判「代码错 / 期望写错」
  fail_list                   给 bfix 的失败清单 {规则原文, 函数, 输入, 断言/期望, 实际}
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import asserts as A

FIXDIR = Path(__file__).resolve().parent / "fixtures"
CHILD = FIXDIR / "child.py"
THRESH_COV = 0.70            # 规则覆盖率
THRESH_PER_FN = 2            # 每个改动函数至少几条
RESULT_CAP = 200000
CALL_SEC = 5
EXPK = ("期望", "期望包含", "期望异常")
VERDICT_WRONG = "期望写错"
VERDICT_CODE = "代码错"
PLACEHOLDER = object()


# ------------------------------------------------------------------ 规划阶段：切表

_HEAD = re.compile(r"^[ \t]*#[ \t]*期望表.*$", re.M)


def parse_rows(text):
    """从一段文本里取 JSON 数组（可带围栏）。返回 list 或 None。"""
    a = (text or "").find("[")
    if a < 0:
        return None
    try:
        v, _ = json.JSONDecoder().raw_decode(text[a:])
    except ValueError:
        b = text.rfind("]")
        if b < a:
            return None
        try:
            v = json.loads(text[a:b + 1])
        except ValueError:
            return None
    return v if isinstance(v, list) else None


def split_table(raw):
    """规划回复 → (去掉表的回复, 表行|None, 说明)。表从 `#期望表` 标题行起到末尾；之前的部分原样交给 .zs 处理。
    说明：无表 / 表解析失败 / 表不是数组 / 表为空 / ""（有表）。"""
    m = _HEAD.search(raw or "")
    if not m:
        return raw, None, "无表"
    body = raw[m.end():]
    rest = raw[:m.start()].rstrip("\n")
    rest = rest + "\n" if rest.strip() else rest
    a, o = body.find("["), body.find("{")
    if a < 0 and o < 0:
        return rest, None, "表解析失败"
    if o >= 0 and (a < 0 or o < a):                 # 先出现的是对象：表应该是数组
        try:
            json.JSONDecoder().raw_decode(body[o:])
            return rest, None, "表不是数组"
        except ValueError:
            return rest, None, "表解析失败"
    rows = parse_rows(body)
    if rows is None:
        return rest, None, "表解析失败"
    if not rows:
        return rest, None, "表为空"
    return rest, rows, ""


# ------------------------------------------------------------------ 规则候选与覆盖（搬自 bound_code2/common2.py）

SPLIT = r"[。；;\n]"
KEEP = re.compile(r"[0-9０-９\"「」“”'‘]|不|只|按|缺省|默认|必须|时|如果|若|才|一律|照旧|恰好|完全|忽略|返回|抛|上限|新增")
DROP_BG = re.compile(r"各自|各写各的|于是|有的|彼此不一致|可能是模型写的|所以|测试文件|现有测试")
MINLEN = 8


def candidates(prompt):
    segs = [re.sub(r"^[\s\-\d.、)]+", "", x).strip() for x in re.split(SPLIT, prompt or "")]
    return [x for x in segs if len(x) >= MINLEN and KEEP.search(x) and not DROP_BG.search(x)]


def _n(s):
    return re.sub(r"[\s，,：:「」“”\"'（）()、]", "", s)


def covered(c, rules, k=6):
    cc = _n(c)
    for r in rules:
        rr = _n(r)
        for i in range(0, max(1, len(cc) - k + 1)):
            if cc[i:i + k] in rr:
                return True
    return False


def coverage(prompt, rows):
    cs = candidates(prompt)
    rules = [str(r.get("规则", "")) for r in rows if isinstance(r, dict)]
    un = [c for c in cs if not covered(c, rules)]
    ratio = (len(cs) - len(un)) / len(cs) if cs else 1.0       # 任务里切不出规则候选就不卡覆盖率
    return {"n": len(cs), "covered": len(cs) - len(un), "ratio": ratio, "uncovered": un}


def _strip_name(fn):
    return re.sub(r"\(.*\)\s*$", "", re.sub(r"^动词\s+", "", fn.strip())).strip()


def row_shape_problem(r):
    """表项的结构问题（不看代码）；None = 结构合格。"""
    if not isinstance(r, dict):
        return "不是对象"
    if not isinstance(r.get("函数"), str) or not r["函数"].strip():
        return "没有函数名"
    if not isinstance(r.get("参数", {}), dict):
        return "参数不是对象"
    exp = [k for k in EXPK if k in r]
    if len(exp) > 1:
        return "期望字段不是至多一个"
    if "断言" in r:
        a = r["断言"]
        if not isinstance(a, list) or not a or not all(isinstance(x, dict) and x for x in a):
            return "断言不是非空对象列表"
        bad = [k for x in a for k in x if k not in A.VOCAB]
        if bad:
            return f"断言词表里没有 {bad[0]}"
    elif not exp:
        return "没有断言 / 期望"
    if "文件" in r and not isinstance(r["文件"], dict):
        return "文件不是对象"
    return None


def planned_units(checklist):
    """计划 #清单 里要改 / 新建的 .py 函数 → [{label, path, func}]。改 + 函数名；新建只有路径（func=None）；行号范围 / 类方法 / 没写位置的跳过。"""
    out = []
    for op, path, loc in (checklist or {}).get("items") or []:
        if not str(path).endswith(".py") or _is_test(path):
            continue
        if op == "新建":
            out.append({"label": path, "path": path, "func": None})
        elif op == "改" and loc and re.fullmatch(r"[A-Za-z_]\w*|[^\W\d]\w*", loc):
            out.append({"label": f"{path}:{loc}", "path": path, "func": loc})
    return out


def _is_test(rel):
    parts = Path(rel).parts
    return any(p in ("tests", "test") for p in parts[:-1]) or Path(rel).name.startswith("test_") or Path(rel).name == "conftest.py"


def unit_matches(unit, fn):
    name = _strip_name(fn)
    bare = name.split("::")[-1]
    stem = Path(unit["path"]).stem
    if unit["func"] is None:
        return name.startswith(unit["path"] + "::") or (_is_def(unit["path"]) and name == stem)
    if bare != unit["func"]:
        return False
    return "::" not in name or name.split("::")[0] == unit["path"]


def table_check(task, rows, units):
    """表级检查（零模型调用）：规则覆盖率 ≥ THRESH_COV，且每个改动函数 ≥ THRESH_PER_FN 条结构合格的表项。"""
    rows = rows or []
    cov = coverage(task, rows)
    good = [r for r in rows if row_shape_problem(r) is None]
    per = {u["label"]: sum(1 for r in good if unit_matches(u, r["函数"])) for u in units}
    short = [k for k, v in per.items() if v < THRESH_PER_FN]
    ok = cov["ratio"] >= THRESH_COV and not short and len(good) >= THRESH_PER_FN
    why = []
    if cov["ratio"] < THRESH_COV:
        why.append(f"规则覆盖率 {cov['ratio']:.0%} < {THRESH_COV:.0%}")
    if short:
        why.append("条数不够的函数：" + "、".join(short))
    if len(good) < THRESH_PER_FN:
        why.append(f"结构合格的表项只有 {len(good)} 条")
    return {"达标": ok, "覆盖率": round(cov["ratio"], 3), "候选规则数": cov["n"], "未覆盖": cov["uncovered"],
            "表条数": len(rows), "合格条数": len(good), "各函数条数": per, "原因": "；".join(why)}


def fill_user(task, rows, chk, units, notes=""):
    un = "\n".join(f"- {u}" for u in chk["未覆盖"]) or "（无；覆盖率已够，只是条数不够）"
    fns = "、".join(u["label"] for u in units) or "（清单里没有可调用的函数）"
    short = "、".join(k for k, v in chk["各函数条数"].items() if v < THRESH_PER_FN) or "（无）"
    return (f"【任务原文】\n{task}\n\n【你之前的期望表】\n{json.dumps(rows or [], ensure_ascii=False)}\n\n"
            f"【还没被引到的任务原文规则】\n{un}\n\n【要改的函数】{fns}\n条数不够（每个至少 {THRESH_PER_FN} 条）的函数：{short}；"
            f"当前结构合格的表项 {chk['合格条数']} 条。{notes}\n请输出补充的 JSON 数组。")


# ------------------------------------------------------------------ 夹具登记（fixtures/modules.json：模块路径 → 夹具构造）

def registry():
    return json.loads((FIXDIR / "modules.json").read_text(encoding="utf-8"))


def fixture_notes(text):
    """text 里出现了登记过的模块路径 → 对应的专用夹具说明（追加到规划 / 补表的 user，空串 = 没有）。"""
    parts = [v["说明"] for k, v in registry().items() if k in (text or "")]
    return ("\n\n【专用夹具说明】\n" + "\n".join(parts)) if parts else ""


# ------------------------------------------------------------------ AST：函数表（搬自 bound_code2/layer1.py，只留表校验要的）

EXT_NAMES = {"subprocess", "socket", "urllib", "requests", "http", "sqlite3", "psycopg2", "pymysql", "httpx", "aiohttp",
             "call_claude", "Popen", "urlopen", "smtplib", "ftplib"}
STATE_PARAMS = {"self", "cls", "conn", "db", "cur", "cursor", "session", "reg", "registry", "engine", "app", "req", "request",
                "ctx", "m", "model", "client", "fn", "func", "callback", "state", "store", "logger", "log", "out", "env",
                "writer", "reader", "stream", "proc", "thread", "lock"}
MISSING = "<MISSING>"


class Fn:
    def __init__(self, node, qual, parent, in_class):
        self.node, self.qual, self.parent, self.in_class, self.name = node, qual, parent, in_class, node.name


def collect(src):
    tree = ast.parse(src)
    out = {}

    def walk(body, qual, parent, in_class):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = f"{qual}.{n.name}" if qual else n.name
                f = Fn(n, q, parent, in_class)
                out[q] = f
                walk(n.body, q + ".<locals>", f, False)
            elif isinstance(n, ast.ClassDef):
                walk(n.body, f"{qual}.{n.name}" if qual else n.name, parent, True)
            else:
                for fld in ("body", "orelse", "finalbody", "handlers"):
                    sub = getattr(n, fld, None)
                    if isinstance(sub, list):
                        walk([x for x in sub if isinstance(x, ast.stmt)] +
                             [y for x in sub if isinstance(x, ast.ExceptHandler) for y in x.body], qual, parent, in_class)
    walk(tree.body, "", None, False)
    return tree, out


def _own_dump(node):
    import copy
    n2 = copy.deepcopy(node)

    class Strip(ast.NodeTransformer):
        def visit_FunctionDef(self, n):
            return ast.Pass()
        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, n):
            return ast.Pass()
    n2.body = [Strip().visit(x) for x in n2.body]
    return ast.dump(n2, include_attributes=False)


def _state_globals(tree):
    names = set()
    for n in tree.body:
        if isinstance(n, ast.Assign):
            txt = ast.unparse(n.value)
            if any(k in txt for k in ("environ", "Path.home", "__file__", "expanduser", "getenv")):
                names.update(t.id for t in n.targets if isinstance(t, ast.Name))
    return names


def _refs(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


def _params(node):
    a = node.args
    pos = a.posonlyargs + a.args
    defs = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
    res = [(x.arg, d is None) for x, d in zip(pos, defs)]
    res += [(x.arg, d is None) for x, d in zip(a.kwonlyargs, a.kw_defaults)]
    return res                      # [(名, 必填)]


def _is_def(rel):
    return "/defs/" in rel and not Path(rel).name.startswith("_")


def describe(rel, f, tree, root):
    """顶层函数 f 能不能被表调用 → {key, kind(verb|module), params, covered, reason, ...}；kind 为 verb 时带 pack_dir / name，module 时带 module / func。"""
    reg = registry()
    t = {"file": rel, "name": f.name, "covered": False, "reason": ""}
    if f.in_class:
        return dict(t, kind="method", reason="类方法（需要实例）")
    if f.parent is not None:
        return dict(t, kind="nested", reason="嵌套函数")
    if _is_def(rel) and f.name == Path(rel).stem:
        t.update(kind="verb", key=f.name, pack_dir=str(Path(rel).parent.parent), verb=f.name)
    else:
        t.update(kind="module", key=f"{rel}::{f.name}", module=".".join(Path(rel).with_suffix("").parts), func=f.name)
    t["params"] = _params(f.node)
    refs = _refs(f.node)
    ext = refs & EXT_NAMES
    if ext:
        t["reason"] = "外部状态（" + "、".join(sorted(ext)) + "）"
        return t
    bad = [p for p, _ in t["params"] if p.lower() in STATE_PARAMS]
    if bad:
        t["reason"] = "参数需要外部对象（" + "、".join(bad) + "）"
        return t
    sg = refs & _state_globals(tree)
    if sg and t["kind"] == "module":
        fx = reg.get(rel)
        if fx and f.name in fx.get("函数", []):
            t["fixture"] = fx["构造"]
        else:
            t["reason"] = "依赖模块级路径 / 环境状态（" + "、".join(sorted(sg)) + "）"
            return t
    t["covered"] = True
    return t


def _parse(path):
    try:
        return collect(Path(path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return None, {}


def changed_callables(root, base, cur):
    """base / cur 是快照 {相对路径: 文本}：改过或新增的 .py（非测试）里能被表调用的顶层函数。"""
    out = []
    for rel in sorted(cur):
        if not rel.endswith(".py") or _is_test(rel) or base.get(rel) == cur[rel]:
            continue
        try:
            atree, afn = collect(cur[rel])
            _, bfn = collect(base[rel]) if base.get(rel) is not None else (None, {})
        except (SyntaxError, ValueError):
            continue
        for q, f in afn.items():
            if q in bfn and _own_dump(bfn[q].node) == _own_dump(f.node):
                continue
            t = describe(rel, f, atree, root)
            if t["covered"]:
                out.append(t)
    return out


def resolve(root, name):
    """表里的函数名 → describe 结果（改后代码里真实存在、能被调用）；动词写名字、模块函数写 文件::函数；找不到 / 不可调返回 None。"""
    root = Path(root)
    name = _strip_name(name)
    if "::" in name:
        rel, f = name.rsplit("::", 1)
        paths = [root / rel] if (root / rel).is_file() and not _is_test(rel) else []
    else:
        f = name
        paths = [p for p in root.rglob(f"{f}.py") if p.parent.name == "defs" and "tests" not in p.parts] if f.isidentifier() else []
    if len(paths) != 1:
        return None
    tree, fns = _parse(paths[0])
    node = fns.get(f)
    if node is None:
        return None
    t = describe(str(paths[0].relative_to(root)), node, tree, root)
    return t if t["covered"] else None


def validate(rows, root, changed):
    """按改后代码的真实签名校验表项。返回 (kept, dropped)。
    kept 项：{idx, rule, key, t, args, files, exp_kind, exp, asserts, row}；dropped 项：{row, why}。"""
    bykey = {t["key"]: t for t in changed}
    bare = {}
    for t in changed:
        bare.setdefault(t["key"].split("::")[-1], []).append(t)
    cache, kept, dropped = {}, [], []
    for idx, r in enumerate(rows):
        p = row_shape_problem(r)
        if p:
            dropped.append({"row": r, "why": p})
            continue
        fn = _strip_name(r["函数"])
        t = bykey.get(fn)
        if t is None and "::" not in fn and len(bare.get(fn, [])) == 1:
            t = bare[fn][0]
        elif t is None and "::" in fn and len(bare.get(fn.split("::")[-1], [])) == 1:
            t = bare[fn.split("::")[-1]][0]
        if t is None:
            if fn not in cache:
                cache[fn] = resolve(root, fn)
            t = cache[fn]
        if t is None:
            dropped.append({"row": r, "why": f"函数名不在改后的代码里（或不能被调用）：{fn}"})
            continue
        args = r.get("参数", {})
        names = [p for p, _ in t["params"]]
        bad = [k for k in args if k not in names]
        miss = [p for p, req in t["params"] if req and p not in args]
        if bad or miss:
            dropped.append({"row": r, "why": f"参数不对：多 {bad} 缺 {miss}"})
            continue
        if t["kind"] == "verb":
            args = {k: (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)) for k, v in args.items()}
        files = {k: str(v) for k, v in (r.get("文件") or {}).items() if isinstance(k, str)}
        exp = [k for k in EXPK if k in r]
        kept.append({"idx": idx, "rule": str(r.get("规则", "")), "key": t["key"], "t": t, "args": args, "files": files,
                     "exp_kind": exp[0] if exp else None, "exp": r[exp[0]] if exp else None, "asserts": r.get("断言"), "row": r})
    return kept, dropped


# ------------------------------------------------------------------ 执行

def spec_of(t):
    if t["kind"] == "verb":
        return {"kind": "verb", "pack_dir": t["pack_dir"], "name": t["verb"], "fixture": t.get("fixture")}
    return {"kind": "module", "module": t["module"], "func": t["func"], "fixture": t.get("fixture")}


def _child_env(tmp):
    env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT") if k in os.environ}
    env.update(PYTHONDONTWRITEBYTECODE="1", BP_TMP=str(tmp), LC_ALL=env.get("LC_ALL", "C.UTF-8"), HOME=str(tmp))
    return env


def run_child(py, root, spec, inputs, ws_files, tmp):
    """起一次子进程跑一组输入。返回 {res: {i: {...}}, fatal, done, timeout, stderr, sec}。"""
    req = dict(spec, root=str(Path(root).resolve()), inputs=inputs, ws_files=ws_files, twice=False)
    t0 = time.time()
    try:
        p = subprocess.run([py, "-B", str(CHILD)], input=json.dumps(req, ensure_ascii=False), capture_output=True, text=True,
                           timeout=len(inputs) * (CALL_SEC + 2) + 25, env=_child_env(tmp), cwd=str(tmp), stdin=None)
        out, err, to = p.stdout, p.stderr, False
    except subprocess.TimeoutExpired as e:
        out = (e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else e.stdout) or ""
        err, to = "", True
    except OSError as e:
        return {"res": {}, "fatal": f"子进程起不来：{e}", "done": False, "timeout": False, "stderr": "", "sec": 0.0}
    res, fatal, done = {}, None, False
    for ln in out.splitlines():
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if "fatal" in d:
            fatal = d["fatal"]
        elif "done" in d:
            done = True
        elif "i" in d:
            res[d["i"]] = d
    return {"res": res, "fatal": fatal, "done": done, "timeout": to, "stderr": err[-400:], "sec": round(time.time() - t0, 2)}


def run_cases(kept, root, py, tmp):
    """每条一个结果 {exc, rep, rtype} 或 None（没跑到）。按 (函数, 夹具文件) 分组，每组一个子进程。
    返回 (results: {idx: res}, fatals: [说明], sec)。"""
    tmp = Path(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    groups = {}
    for i, k in enumerate(kept):
        groups.setdefault((k["key"], json.dumps(k["files"], sort_keys=True)), []).append(i)
    results, fatals, secs = {}, [], 0.0
    for n, ((key, _), idxs) in enumerate(groups.items()):
        t = kept[idxs[0]]["t"]
        r = run_child(py, root, spec_of(t), [kept[i]["args"] for i in idxs], kept[idxs[0]]["files"], _fresh(tmp, f"g{n}"))
        secs += r["sec"]
        if r["fatal"]:
            fatals.append(f"{key}: {r['fatal']}")
            continue
        if r["timeout"] or not r["done"]:
            fatals.append(f"{key}: 子进程没跑完（{'超时' if r['timeout'] else '提前退出'}）{r['stderr'][-150:]}")
        for j, i in enumerate(idxs):
            results[i] = r["res"].get(j)
    return results, fatals, round(secs, 2)


def _fresh(tmp, name):
    d = Path(tmp) / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def materialize(base, dest):
    """把 base 快照还原成一份改前副本。"""
    dest = Path(dest)
    for rel, text in base.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return dest


def needs_before(k):
    return k["asserts"] is not None and any("同改前" in a for a in k["asserts"] if isinstance(a, dict))


def run_before(kept, base, py, tmp):
    """含「同改前」的条目在改前副本上再跑一次。返回 ({idx: res}, fatals, sec)。"""
    idx = [i for i, k in enumerate(kept) if needs_before(k)]
    if not idx:
        return {}, [], 0.0
    bdir = materialize(base, Path(tmp) / "before_tree")
    sub = [kept[i] for i in idx]
    res, fatals, sec = run_cases(sub, bdir, py, Path(tmp) / "before_run")
    return {idx[j]: r for j, r in res.items()}, fatals, sec


# ------------------------------------------------------------------ 判定（期望搬自 bound_code2/layer2.py，断言见 asserts.py）

def _sub(e):
    if isinstance(e, str):
        return e.replace("$OUT", "$TMP/outside.txt")
    if isinstance(e, list):
        return [_sub(x) for x in e]
    if isinstance(e, dict):
        return {k: _sub(v) for k, v in e.items()}
    return e


def _val(res):
    try:
        return json.loads(res.get("rep"))
    except (TypeError, ValueError):
        return res.get("rep")


def _judge_expect(k, res):
    kind, e = k["exp_kind"], _sub(k["exp"])
    exc, rep = res.get("exc"), res.get("rep")
    if kind == "期望异常":
        return (bool(exc) and str(e) in exc), (exc if exc else f"没抛异常，返回 {rep}")
    if exc:
        return False, f"抛了 {exc}"
    actual = _val(res)
    if kind == "期望":
        return actual == e, rep
    text = actual if isinstance(actual, str) else json.dumps(actual, ensure_ascii=False)
    return all(str(n) in text for n in (e if isinstance(e, list) else [e])), rep


def judge_one(k, res, res_before=None):
    """→ (ok, 实际, [没过的原因])。期望部分和断言部分全部满足才过。"""
    if res is None:
        return False, "没有结果（子进程失败 / 超时）", ["没有结果"]
    why, ok, actual_s = [], True, None
    if k["exp_kind"]:
        ok1, actual_s = _judge_expect(k, res)
        if not ok1:
            ok = False
            why.append("期望不符")
    if k["asserts"] is not None:
        before = A._MISSING
        if res_before is not None:
            before = ("EXC:" + res_before["exc"]) if res_before.get("exc") else _val(res_before)
        exc = res.get("exc")
        ok2, w = A.check(k["asserts"], ("EXC:" + exc) if exc else _val(res), before=before, exc=exc)
        if actual_s is None:
            actual_s = res.get("rep") if not exc else f"抛了 {exc}"
        if not ok2:
            ok = False
            why.extend(w)
    return ok, actual_s, why


def judge_all(kept, results, before):
    """→ 每条 {ok, actual, why}（与 kept 同序）。同改前条目在改前副本没结果（函数改前不存在 / 改前跑不起来）时按「无改前结果」判失败。"""
    out = []
    for i, k in enumerate(kept):
        rb = before.get(i)
        if needs_before(k) and rb is None:
            out.append({"ok": False, "actual": "（改前副本没有这个函数的结果）", "why": ["同改前: 无改前结果"]})
            continue
        ok, actual, why = judge_one(k, results.get(i), rb)
        out.append({"ok": ok, "actual": actual, "why": why})
    return out


# ------------------------------------------------------------------ 失败清单 / 判表错

def _item(i, k, j, cap):
    t = f"[{i}] 规则原文：{k['rule']}\n    函数：{k['key']}\n    输入：{json.dumps(k['args'], ensure_ascii=False)}\n"
    if k["exp_kind"]:
        t += f"    期望：{json.dumps({k['exp_kind']: k['exp']}, ensure_ascii=False)}\n"
    if k["asserts"] is not None:
        t += f"    性质断言：{json.dumps(k['asserts'], ensure_ascii=False)}\n    没通过的断言：{'；'.join(j['why'])[:500]}\n"
    return t + f"    实际：{str(j['actual'])[:cap]}"


def fail_list(items, cap=600):
    """items = [(kept 项, 判定)] → 给 bound_judge / bfix 的失败清单文本，序号从 1 起。"""
    return "\n".join(_item(n, k, j, cap) for n, (k, j) in enumerate(items, 1))


def fn_source(root, t, cap=5000):
    p = Path(root) / t["file"]
    try:
        src = p.read_text(encoding="utf-8")
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == t["name"]:
                return f"# {t['file']}\n" + (ast.get_source_segment(src, n) or "")[:cap]
        return f"# {t['file']}\n" + src[:cap]
    except (OSError, SyntaxError, ValueError):
        return f"（找不到 {t['key']} 的源码）"


def judge_user(task, root, items):
    seen, code = set(), []
    for k, _ in items:
        if k["key"] not in seen:
            seen.add(k["key"])
            code.append(fn_source(root, k["t"]))
    return (f"【任务原文】\n{task}\n\n【改动函数当前代码】\n" + "\n\n".join(code) + f"\n\n【失败条目】\n{fail_list(items)}\n\n"
            "请逐条判定，只输出 JSON 数组。")


def parse_judge(text):
    """bound_judge 的回复 → {"value": {序号: (判定, 依据)}, "problems": [问题]}（同 dsl_task.parse_check 的出参风格）。"""
    t = re.sub(r"^```[a-z]*\n|\n```$", "", (text or "").strip())
    rows = parse_rows(t)
    if rows is None:
        return {"value": None, "problems": ["回复不是 JSON 数组"]}
    val, probs = {}, []
    for r in rows:
        if not isinstance(r, dict) or not isinstance(r.get("条目序号"), int) or r.get("判定") not in (VERDICT_CODE, VERDICT_WRONG):
            probs.append(f"项格式不对：{str(r)[:80]}（需要 条目序号 + 判定「{VERDICT_CODE}」或「{VERDICT_WRONG}」+ 依据）")
            continue
        val[r["条目序号"]] = (r["判定"], str(r.get("依据") or ""))
    if not val and not probs:
        probs.append("数组是空的")
    return {"value": val, "problems": probs}
