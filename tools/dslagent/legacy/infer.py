"""推理候选：ast 事实抽取（只读）+ 小 Datalog（半朴素自底向上）+ 打分排序 → 第一次定位的候选根因段落。

由 plan14 实验的 dl.py 搬来（plan15 冻结版 sha256 79be439b…），规则、权重、打分、段长逐项不变；
tests/tools/test_dslagent_infer.py 在 N1–N10、B1–B8 场景上对照冻结版逐段一致。

    from tools.dslagent import infer as I
    job = I.start(repo)                          # 开局跑测试之前起：抽事实（只读源码）和跑测试重叠
    p = I.augment(job, p, desc, test, repo)      # 模板抽参之后：推理候选前 K 段并进 p["pre"]（总 ≤ CAP 行）

并入方式：模板预读 ∪ 推理候选前 K=8 段（同文件被已有段包住的跳过；按名次加，加上会超 CAP=675 行的跳过）。
不替代模板、不做硬过滤，只是多给模型几段原文。抽取/推理出错、超过 TIMEOUT 秒（DSLAGENT_INFER_TIMEOUT）、
.py 文件超过 MAX_FILES 个 → 回退为模板原样预读，原因记在 p["infer"]["fallback"]。
开关：DSLAGENT_INFER=0 关（runner.run(infer=False) 同效）。

动态调用（getattr、字典分派、对象方法 obj.m()）抽不准：方法调用按「同名方法」尽力连边（call_weak），只参与排序，
推不出来的函数仍可能靠名字/traceback 命中进候选，也永远只是给模型的预读提示。
"""
import ast
import json
import os
import re
import threading
import time
from collections import defaultdict
from pathlib import Path

from ..datalog import Datalog, Timeout, _check, _is_var, _parse_atom, parse_rules  # noqa: F401  求值器共用，旧名仍可从这里取

K, CAP = 8, 675                 # 并入前 K 段；合并后总行数上限（模板上限 450 的 1.5 倍）
TIMEOUT = 3.0                   # 抽取 + 推理的墙钟上限（秒）；开局测试期间已在后台抽事实，这里只算等它的时间
MAX_FILES = 400                 # .py 文件太多（多半把虚拟环境扫进来了）→ 不做，回退


def enabled(flag=None):
    """flag 显式给了就用它；否则看 DSLAGENT_INFER（0/false/no/off 关），默认开。"""
    if flag is not None:
        return bool(flag)
    return os.environ.get("DSLAGENT_INFER", "1").strip().lower() not in ("0", "false", "no", "off", "")


# ============================================================ 推理规则（求值器在 ../datalog.py）

RULES = r"""
% ---- 调用闭包：测试函数出发，强边（直接解析出的调用）+ 弱边（同名方法尽力连）
edge(F,G) :- call(F,G).
edge(F,G) :- call_weak(F,G).
edge(F,M) :- uses_global(F,C), const_in(C,M).
reaches(T,F) :- test(T,_), edge(T,F).
reaches(T,F) :- reaches(T,G), edge(G,F).
reaches_const(T,C) :- reaches(T,F), uses_global(F,C).
reaches_const(T,C) :- test(T,_), uses_global(T,C).
% ---- 断言/测试里的标识符、字面量 = 相关名字；traceback 报错信息、任务描述里的词也算（弱）
relevant_name(T,N) :- asserts(T,N).
relevant_name(T,N) :- test_lit(T,N).
relevant_name(T,N) :- test(T,_), err_tok(N).
relevant_name(T,N) :- test(T,_), desc_tok(N).
% ---- 函数「定义/赋值/读」相关名字
touches(F,N) :- defines(F,N).
touches(F,N) :- assigns(F,N).
touches(F,N) :- uses_name(F,N).
touches(F,N) :- literal(F,N).
touches(F,N) :- reads_key(F,N).
name_hit(T,F,N) :- reaches(T,F), relevant_name(T,N), touches(F,M), sim(N,M).
def_hit(T,F,N) :- reaches(T,F), relevant_name(T,N), defines(F,M), sim(N,M).
tb_hit(T,F) :- reaches(T,F), tb(F).
tb_hit(T,F) :- test(T,_), tb(F), src_def(F).
data_hit(T,F) :- reaches(T,F), reads_data(F,_,_).
% ---- 候选
candidate(T,F) :- tb_hit(T,F).
candidate(T,F) :- name_hit(T,F,_).
candidate(T,F) :- data_hit(T,F).
candidate(T,F) :- reaches(T,F), src_def(F).
data_candidate(T,C,L) :- reaches_const(T,C), data_lit(C,V,L), relevant_name(T,N), sim(N,V).
data_candidate(T,D,K) :- reaches(T,F), reads_data(F,D,K), data_key(D,K,V), relevant_name(T,N), sim(N,V).
const_candidate(T,C) :- reaches_const(T,C).
missing_def(M,N) :- import_missing(M,N).
round_hit(T,F) :- reaches(T,F), small_diff(_), rounding(F,_).
data_candidate(T,C,L) :- reaches_const(T,C), data_lit(C,V,L), desc_num(N), num_eq(N,V).
"""


# ============================================================ 事实抽取（ast，只读）

def _is_test(rel):
    return rel.startswith("tests/") or "/tests/" in rel or Path(rel).name.startswith("test_")


def _mod(rel):
    return rel[:-3].replace("/", ".").removesuffix(".__init__")


def _toks(s):
    """标识符拆词：make_invoice → make_invoice, make, invoice；去复数 s。"""
    s = str(s)
    out = {s.lower()}
    for w in re.split(r"[^0-9A-Za-z一-鿿-]+|_", s):
        if len(w) >= 3:
            out.add(w.lower())
            if w.lower().endswith("s") and len(w) > 3:
                out.add(w.lower()[:-1])
    return out


# 停用词照搬实验版（含 shopkit：调参集的包名；别的包名不在这里，冻结版就是这样）
STOP = {"self", "test", "tests", "assertequal", "asserttrue", "assertfalse", "assertin", "date", "unittest", "none",
        "true", "false", "the", "and", "for", "len", "sum", "int", "str", "shopkit", "order", "lines", "return",
        "value", "code", "kind", "make", "build", "get", "add", "new", "from", "data", "item", "items", "name"}


def sim(a, b):
    a, b = str(a).lower(), str(b).lower()
    if a in STOP or b in STOP or len(a) < 3 or len(b) < 3:
        return False
    if a == b:
        return True
    ta, tb = _toks(a) - STOP, _toks(b) - STOP
    return bool(ta & tb)


def py_files(repo):
    """项目里的 .py（跳过 __pycache__ 和隐藏目录）。实验版按绝对路径判隐藏，项目放在 ~/.cache 之类下面就一个都抽不到；
    这里按相对路径判，实验场景的结果不变。"""
    repo = Path(repo)
    out = []
    for p in repo.rglob("*.py"):
        parts = p.relative_to(repo).parts
        if "__pycache__" not in parts and not any(x.startswith(".") for x in parts):
            out.append(str(p.relative_to(repo)))
    return sorted(out)


class Extractor(ast.NodeVisitor):
    def __init__(self, repo, deadline=None, files=None):
        self.repo = Path(repo)
        self.deadline = deadline
        self.F = defaultdict(set)
        self.defs = {}           # qual → (rel, start, end)
        self.consts = {}         # qual → (rel, start, end)
        self.methods = defaultdict(set)   # 方法名 → {qual}
        self.files = py_files(self.repo) if files is None else files
        self.trees = {}
        for rel in self.files:
            _check(deadline)
            try:
                self.trees[rel] = ast.parse((self.repo / rel).read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                pass

    def f(self, pred, *a):
        self.F[pred].add(tuple(str(x) for x in a))

    def run(self):
        self.collect()
        self.bodies()
        self.json_data()
        return self

    # ---- 第一遍：定义、常量、import 别名
    def collect(self):
        self.alias = {}
        for rel, tree in self.trees.items():
            _check(self.deadline)
            mod = _mod(rel)
            self.f("file", rel)
            al = {}
            n = len((self.repo / rel).read_text(encoding="utf-8").splitlines())
            self.defs[f"{mod}.<module>"] = (rel, 1, n)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    base = node.module or ""
                    if node.level:
                        pkg = mod.split(".")[:-node.level] if not rel.endswith("__init__.py") else mod.split(".")[:len(mod.split(".")) - node.level + 1]
                        base = ".".join(pkg + ([node.module] if node.module else []))
                    for a in node.names:
                        al[a.asname or a.name] = f"{base}.{a.name}"
                        self.f("import", rel, a.asname or a.name, f"{base}.{a.name}")
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        al[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
                        self.f("import", rel, a.asname or a.name, a.name)
            self.alias[rel] = al
            for node in tree.body:
                self._collect_def(node, mod, rel, None)
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    tg = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for t in tg:
                        if isinstance(t, ast.Name):
                            q = f"{mod}.{t.id}"
                            self.consts[q] = (rel, node.lineno, node.end_lineno)
                            self.f("const", q, rel, node.lineno, node.end_lineno)
                            self.f("const_in", q, f"{mod}.<module>")
                            self._data_lits(q, node.value, rel)

    def _collect_def(self, node, mod, rel, cls):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            q = f"{mod}.{cls + '.' if cls else ''}{node.name}"
            self.defs[q] = (rel, node.lineno - len(node.decorator_list), node.end_lineno)
            self.f("def", q, rel, node.lineno, node.end_lineno)
            if cls:
                self.methods[node.name].add(q)
            if _is_test(rel) and node.name.startswith("test"):
                self.f("test", q, mod)
            elif not _is_test(rel):
                self.f("src_def", q)
        elif isinstance(node, ast.ClassDef):
            self.f("class", f"{mod}.{node.name}", rel, node.lineno, node.end_lineno)
            for b in node.body:
                self._collect_def(b, mod, rel, node.name)

    def _data_lits(self, q, val, rel):
        """模块级常量里的字面量（含嵌套 dict/list/tuple）→ data_lit(常量, 值, 行)；dict 键 → data_key。"""
        for n in ast.walk(val):
            if isinstance(n, ast.Constant) and isinstance(n.value, (str, int, float)) and not isinstance(n.value, bool):
                self.f("data_lit", q, n.value, n.lineno)
                if isinstance(n.value, str):        # 「键 = 值」文本配置里的键也拆出来
                    for ln_off, line in enumerate(n.value.splitlines()):
                        m = re.match(r"\s*([\w.]+)\s*[=:]\s*(.+?)\s*(#.*)?$", line)
                        if m:
                            self.f("data_lit", q, m.group(1), n.lineno + ln_off)
                            self.f("data_lit", q, m.group(2), n.lineno + ln_off)
            if isinstance(n, ast.Dict):
                for kk, vv in zip(n.keys, n.values):
                    if isinstance(kk, ast.Constant):
                        self.f("data_key", q, kk.value, getattr(vv, "value", ""))

    # ---- 第二遍：函数体 → call/uses/assigns/literal/reads
    def resolve(self, rel, name):
        mod = _mod(rel)
        for cand in (f"{mod}.{name}", self.alias.get(rel, {}).get(name, "")):
            if cand in self.defs or cand in self.consts:
                return cand
            if cand and f"{cand}.__init__" in self.defs:
                return f"{cand}.__init__"
            if cand and any(d.startswith(cand + ".") for d in self.defs) and cand not in self.defs:
                return "MOD:" + cand
        return None

    def bodies(self):
        for rel, tree in self.trees.items():
            _check(self.deadline)
            mod = _mod(rel)
            tops = []
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self._body(f"{mod}.{node.name}", node, rel, None)
                elif isinstance(node, ast.ClassDef):
                    for b in node.body:
                        if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            self._body(f"{mod}.{node.name}.{b.name}", b, rel, f"{mod}.{node.name}")
                else:
                    tops.append(node)
            self._body(f"{mod}.<module>", ast.Module(body=tops, type_ignores=[]), rel, None)

    def _body(self, q, node, rel, cls):
        is_t = _is_test(rel)
        self.f("defines", q, q.split(".")[-1])
        test_consts = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                fn = n.func
                tgt = None
                if isinstance(fn, ast.Name):
                    tgt = self.resolve(rel, fn.id)
                    if is_t and fn.id != "date" and not fn.id.startswith("assert"):
                        self.f("test_lit", q, fn.id)
                elif isinstance(fn, ast.Attribute):
                    v = fn.value
                    if isinstance(v, ast.Name) and v.id == "self" and cls:
                        tgt = f"{cls}.{fn.attr}" if f"{cls}.{fn.attr}" in self.defs else None
                    elif isinstance(v, ast.Name):
                        r = self.resolve(rel, v.id)
                        if r and r.startswith("MOD:"):
                            c = f"{r[4:]}.{fn.attr}"
                            tgt = c if c in self.defs else (f"{c}.__init__" if f"{c}.__init__" in self.defs else None)
                    if tgt is None and not fn.attr.startswith("assert"):
                        for m in self.methods.get(fn.attr, ()):
                            self.f("call_weak", q, m)
                    if fn.attr in ("load", "loads") and isinstance(v, ast.Name) and v.id == "json":
                        self.f("reads_data", q, "<json>", "")
                    if is_t and not fn.attr.startswith("assert"):
                        self.f("test_lit", q, fn.attr)
                if tgt and not tgt.startswith("MOD:"):
                    if tgt in self.consts:
                        self.f("uses_global", q, tgt)
                    else:
                        self.f("call", q, tgt)
                if isinstance(fn, ast.Name) and fn.id == "open" and n.args and isinstance(n.args[0], ast.Constant):
                    self.f("reads_data", q, n.args[0].value, "")
                if is_t and isinstance(fn, ast.Attribute) and fn.attr.startswith("assert"):
                    for a in ast.walk(n):
                        if isinstance(a, ast.Name) and a.id != "self":
                            self.f("asserts", q, a.id)
                        elif isinstance(a, ast.Constant) and a.value is not None:
                            self.f("asserts", q, a.value)
                        elif isinstance(a, ast.Attribute):
                            self.f("asserts", q, a.attr)
            elif isinstance(n, ast.BinOp) and isinstance(n.op, (ast.FloorDiv, ast.Mod)):
                self.f("rounding", q, "//")
            elif isinstance(n, ast.Name):
                if n.id in ("round", "int", "floor", "ceil", "ROUND_HALF_UP", "ROUND_DOWN", "ROUND_FLOOR") \
                        or n.id.startswith("round"):
                    self.f("rounding", q, n.id)
                if isinstance(n.ctx, ast.Store):
                    self.f("assigns", q, n.id)
                else:
                    self.f("uses_name", q, n.id)
                    r = self.resolve(rel, n.id)
                    if r and r in self.consts:
                        self.f("uses_global", q, r)
                        if is_t:
                            test_consts.add(r)
                    elif r and r in self.defs and not isinstance(getattr(n, "_parent", None), ast.Call):
                        self.f("call", q, r)          # 函数当值传（回调、分派表）也算可达
            elif isinstance(n, ast.Attribute):
                self.f("assigns" if isinstance(n.ctx, ast.Store) else "uses_name", q, n.attr)
                if isinstance(n.value, ast.Name):
                    r = self.resolve(rel, n.value.id)
                    if r and r.startswith("MOD:"):
                        c = f"{r[4:]}.{n.attr}"
                        if c in self.consts:
                            self.f("uses_global", q, c)
                        elif c in self.defs:
                            self.f("call", q, c)
            elif isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
                self.f("reads_key", q, n.slice.value)
                if is_t:
                    self.f("test_lit", q, n.slice.value)
            elif isinstance(n, ast.Constant) and n.value is not None and not isinstance(n.value, bool):
                self.f("literal", q, n.value)
                if is_t:
                    self.f("test_lit", q, n.value)
        for c in test_consts:      # 测试模块级常量里的字面量（如 VIP 券）也算测试字面量
            for (_, v, _) in [t for t in self.F["data_lit"] if t[0] == c]:
                self.f("test_lit", q, v)

    def json_data(self):
        for p in self.repo.rglob("*.json"):
            _check(self.deadline)
            if "__pycache__" in p.parts:
                continue
            rel = str(p.relative_to(self.repo))
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue

            def walk(o, path):
                if isinstance(o, dict):
                    for k, v in o.items():
                        walk(v, f"{path}.{k}" if path else str(k))
                elif isinstance(o, list):
                    for i, v in enumerate(o):
                        walk(v, f"{path}[{i}]")
                else:
                    self.f("data_key", rel, path, o)
            walk(obj, "")


def parse_tb(test, desc):
    tb, toks, missing = [], set(), []
    for f, ln, fn in re.findall(r"^\s*([\w./-]+\.py):(\d+) (\w+|<module>): ", test, re.M):
        tb.append((f, int(ln), fn))
    for msg in re.findall(r"^\s*\w*(?:Error|Exception): (.+)$", test, re.M):
        toks |= set(re.findall(r"[一-鿿]{2,}|[A-Za-z_]\w{2,}|[A-Z]+-\d+", msg))
    for nm, mod in re.findall(r"cannot import name '(\w+)' from '([\w.]+)'", test):
        missing.append((mod, nm))
    dt = set(re.findall(r"[A-Za-z_][\w]{3,}|[A-Z]{1,5}-\d{2,}", desc))
    return tb, toks, missing, dt


# ============================================================ 打分排序

W = {"tb": 4.0, "name": 1.2, "name_cap": 4, "data": 2.0, "dist": 2.0, "const": 1.0, "datahit": 2.5, "round": 2.5, "defname": 1.5}
PAD, MAX_SEG, SMALL_FILE = 25, 70, 60    # 单行定位上下各补 PAD 行；函数段超 MAX_SEG 截头；≤SMALL_FILE 行的文件整份给


def extract(repo, deadline=None):
    """只读源码的那部分（和测试结果无关）：可以在开局跑测试时后台先做。"""
    return Extractor(repo, deadline).run()


def rank(ex, repo, test, desc, k=K, pad=PAD, max_seg=MAX_SEG, small_file=SMALL_FILE, deadline=None):
    """在抽好的事实上加测试/描述线索，求值、打分、出段。ex 会被改（加线索事实），只能用一次。"""
    t0 = time.time()
    repo = Path(repo)
    tb, etoks, missing, dtoks = parse_tb(test, desc)
    failing = set(re.findall(r"\((?:[\w.]*\.)?(\w+)\.(\w+)\.(test\w+)\)", test))
    for f, ln, fn in tb:
        for q, (rel, a, b) in ex.defs.items():
            if rel == f and a <= ln <= b and not q.endswith("<module>"):
                ex.f("tb", q)
    for t in etoks:
        ex.f("err_tok", t)
    for t in dtoks:
        ex.f("desc_tok", t)
    for m, n in missing:
        ex.f("import_missing", m, n)
    # 只对失败的测试推理
    keep = {q for (q, _) in ex.F["test"] if any(q.endswith(f".{c}.{m}") for (_, c, m) in failing)}
    if keep:
        ex.F["test"] = {t for t in ex.F["test"] if t[0] in keep}
    # 断言两边数字差很小（≤2）→ small_diff；任务描述里的数字 → desc_num
    for a, b in re.findall(r"AssertionError: .*?([\d, ()]+) != ([\d, ()]+)", test):
        xa, xb = re.findall(r"\d+", a), re.findall(r"\d+", b)
        if len(xa) == len(xb) and any(0 < abs(int(u) - int(v)) <= 2 for u, v in zip(xa, xb)):
            ex.f("small_diff", "1")
    for num in set(re.findall(r"(?<![\w.-])(\d{1,5})(?![\w.-])", desc)):
        if int(num) >= 2:
            ex.f("desc_num", num)
    if not keep:     # 导入就失败等认不出测试名：只留 traceback 里测试文件的测试
        tf = {f for f, _, _ in tb if _is_test(f)}
        tm = {_mod(f) for f in tf}
        ex.F["test"] = {t for t in ex.F["test"] if t[1] in tm} or ex.F["test"]
    dl = Datalog(parse_rules(RULES), {"sim": sim, "num_eq": lambda a, b: str(a) == str(b)}, deadline)
    for p, ts in ex.F.items():
        for t in ts:
            dl.add(p, *t)
    out = dl.run()
    t_inf = time.time()

    # 距离（BFS，最短调用步数）
    edges = defaultdict(set)
    for p in ("call", "call_weak"):
        for a, b in ex.F[p]:
            edges[a].add((b, 1.0 if p == "call" else 1.6))
    for a, c in ex.F["uses_global"]:
        edges[a].add((f"{c.rsplit('.', 1)[0]}.<module>", 1.0))
    dist = {}
    for (t, _) in ex.F["test"]:
        frontier, seen = [(t, 0.0)], {t: 0.0}
        while frontier:
            nxt = []
            for u, d in frontier:
                for v, w in edges[u]:
                    if d + w < seen.get(v, 99):
                        seen[v] = d + w
                        nxt.append((v, d + w))
            frontier = nxt
        for v, d in seen.items():
            dist[v] = min(dist.get(v, 99), d)

    score, why = defaultdict(float), defaultdict(list)
    tbf = {f for (_, f) in out.get("tb_hit", ())}
    for (_, f) in out.get("candidate", ()):
        if f not in ex.defs or _is_test(ex.defs[f][0]):
            continue
        d = dist.get(f, 9)
        score[f] += W["dist"] / (1 + d)
        if f in tbf:
            score[f] += W["tb"]
            why[f].append("tb")
    nh = defaultdict(set)
    for (_, f, n) in out.get("name_hit", ()):
        nh[f].add(n)
    df = defaultdict(set)          # 名字的「文档频率」：命中它的可达函数越多，它越不说明问题（IDF 式加权）
    for f, ns in nh.items():
        for n in ns:
            df[n].add(f)
    for f, ns in nh.items():
        if f in score:
            score[f] += min(sum(W["name"] * min(1.0, 3 / len(df[n])) for n in ns), W["name"] * W["name_cap"])
            why[f].append("名字:" + ",".join(sorted(map(str, ns), key=lambda n: len(df[n]))[:4]))
    for (_, f, n) in out.get("def_hit", ()):
        if f in score and not any(w.startswith("函数名") for w in why[f]):
            score[f] += W["defname"]
            why[f].append(f"函数名~{n}")
    for (_, f) in out.get("round_hit", ()):
        if f in score and "舍入" not in why[f]:
            score[f] += W["round"]
            why[f].append("舍入")
    for (_, f) in out.get("data_hit", ()):
        if f in score:
            score[f] += W["data"]
            why[f].append("读数据")
    # 数据/常量位置：data_candidate → 常量里字面量命中的那一行
    locs = {}
    for f, s in score.items():
        rel, a, b = ex.defs[f]
        if f.endswith("<module>"):
            continue
        locs[f] = (rel, a, b, s)
    dc = defaultdict(list)
    for (_, c, ln) in out.get("data_candidate", ()):
        if c in ex.consts and not _is_test(ex.consts[c][0]):
            dc[c].append(int(ln))
    for c in {c for (_, c) in out.get("const_candidate", ())}:
        if c not in ex.consts or _is_test(ex.consts[c][0]):
            continue
        rel, a, b = ex.consts[c]
        mod_d = min((dist.get(u, 9) for (u, cc) in ex.F["uses_global"] if cc == c), default=9)
        s = W["const"] + W["dist"] / (2 + mod_d)
        if c in dc:
            s += W["datahit"] + 0.3 * min(len(dc[c]), 5)
            why[c].append(f"数据命中{len(dc[c])}行")
            ln = sorted(dc[c])[len(dc[c]) // 2]
            if b - a > max_seg:
                a, b = ln, ln
        locs[c] = (rel, a, b, s)
    for (m, n) in out.get("missing_def", ()):
        rel = m.replace(".", "/") + ".py"
        if (repo / rel).is_file():
            nl = len((repo / rel).read_text(encoding="utf-8").splitlines())
            locs[f"{m}.{n}<缺>"] = (rel, nl, nl, 99.0)
            why[f"{m}.{n}<缺>"].append("缺定义")
    ranked = sorted(locs.items(), key=lambda kv: -kv[1][3])
    segs = []
    for q, (rel, a, b, s) in ranked:
        n = len((repo / rel).read_text(encoding="utf-8").splitlines())
        if n <= small_file:                      # 小文件整份给（便宜，且常量/初始化都在里面）
            lo, hi = 1, n
        elif b - a + 1 <= max_seg:
            lo, hi = max(1, a - pad if a == b else a - 3), min(n, b + pad if a == b else b + 3)
        else:
            lo, hi = max(1, a - 3), min(n, a + max_seg)
        same = [x for x in segs if x["file"] == rel and not (hi < x["a"] - 1 or lo > x["b"] + 1)]
        if same:                                 # 和已选段重叠/相邻：并进去，不占名额
            x = same[0]
            x["a"], x["b"] = min(x["a"], lo), max(x["b"], hi)
            x["also"].append(q.split(".")[-1])
            continue
        segs.append({"q": q, "file": rel, "a": lo, "b": hi, "score": round(s, 2), "why": why.get(q, []), "also": []})
        if len(segs) >= k:
            break
    return {"segs": segs, "seg_str": [f"{s['file']}:{s['a']}-{s['b']}" for s in segs],
            "facts": {p: len(ts) for p, ts in ex.F.items()}, "derived": {p: len(ts) for p, ts in out.items()},
            "ms_infer": round(1000 * (t_inf - t0)), "ms_rank": round(1000 * (time.time() - t0))}


def locate(repo, test, desc, k=K, **kw):
    """抽取 + 推理一步做完（对照、离线评估用）。"""
    t0 = time.time()
    r = rank(extract(repo), repo, test, desc, k=k, **kw)
    r["ms_total"] = round(1000 * (time.time() - t0))
    return r


# ============================================================ 并入模板预读

def parse_segs(pre, repo):
    """模板的 pre 串 → [(文件, 起, 止)]；不带行号的是整份文件。"""
    segs = []
    for x in [p for p in (pre or "").split(",") if p and p != "无"]:
        m = re.match(r"(.+?):(\d+)-(\d+)$", x)
        if m:
            segs.append((m.group(1), int(m.group(2)), int(m.group(3))))
        else:
            segs.append((x, 1, len((Path(repo) / x).read_text(encoding="utf-8").splitlines())))
    return segs


def nlines(segs):
    return sum(b - a + 1 for _, a, b in segs)


def merge(tpl, extra, cap=CAP):
    """模板预读 ∪ 推理候选（被已有同文件段包住的跳过），总行数 ≤ cap（候选按名次加，加上会超的跳过）。"""
    out = list(tpl)
    tot = nlines(out)
    for f, a, b in extra:
        if any(sf == f and sa <= a and b <= sb for sf, sa, sb in out):
            continue
        add = b - a + 1
        if tot + add > cap:
            continue
        out.append((f, a, b))
        tot += add
    return out


def pre_str(segs, repo):
    """[(文件, 起, 止)] → pre 串（整份文件只写文件名）。"""
    out = []
    for f, a, b in segs:
        n = len((Path(repo) / f).read_text(encoding="utf-8").splitlines())
        out.append(f if (a == 1 and b == n) else f"{f}:{a}-{b}")
    return ",".join(out)


class Job:
    """后台抽事实（线程）。抽完或出错都记在自己身上；deadline 到了线程自己停。"""

    def __init__(self, repo, timeout=None):
        self.repo = Path(repo)
        self.timeout = float(os.environ.get("DSLAGENT_INFER_TIMEOUT") or TIMEOUT) if timeout is None else timeout
        self.ex = self.error = None
        self.ms_extract = None
        self.deadline = None
        self.done = threading.Event()
        self.thread = None

    def start(self, max_files=MAX_FILES):
        t0 = time.time()
        try:
            files = py_files(self.repo)
        except Exception as e:
            self.error = f"列文件出错：{type(e).__name__}: {str(e)[:200]}"
            self.done.set()
            return self
        if len(files) > max_files:
            self.error = f".py 文件 {len(files)} 个，超过 {max_files}，不做推理"
            self.done.set()
            return self
        # 开局测试在跑时不计时；单独的硬上限防线程跑飞（测试慢时它也早该抽完了）
        self.deadline = t0 + max(self.timeout, 1.0) * 10

        def work():
            try:
                self.ex = Extractor(self.repo, self.deadline, files).run()
            except Timeout:
                self.error = "抽事实超时"
            except Exception as e:
                self.error = f"抽事实出错：{type(e).__name__}: {str(e)[:200]}"
            self.ms_extract = round(1000 * (time.time() - t0))
            self.done.set()
        self.thread = threading.Thread(target=work, name="dslagent-infer", daemon=True)
        self.thread.start()
        return self


def start(repo, timeout=None):
    return Job(repo, timeout).start()


def augment(job, p, desc, test, repo, k=K, cap=CAP):
    """把推理候选前 k 段并进模板参数 p 的预读。任何异常/超时 → p 原样（只用模板预读），原因记在 info["fallback"]。
    返回新的 p（多一个 infer 字段：耗时、候选段、模板原预读、是否回退）。"""
    t0 = time.time()
    info = {"on": True, "k": k, "cap": cap, "timeout": job.timeout if job else TIMEOUT, "tpl_pre": p.get("pre", ""),
            "tpl_lines": p.get("pre_lines", 0), "cands": [], "fallback": ""}
    res = {}
    try:
        if job is None:
            job = Job(repo)
            info["timeout"] = job.timeout
            job.start()
        deadline = t0 + job.timeout
        if not job.done.wait(max(0.0, deadline - time.time())):
            raise Timeout(f"等抽事实超过 {job.timeout} 秒")
        if job.error:
            raise RuntimeError(job.error)
        info["ms_extract"] = job.ms_extract
        th = threading.Thread(target=lambda: _rank_into(res, job.ex, repo, test, desc, k, deadline), daemon=True)
        th.start()
        th.join(max(0.0, deadline - time.time()))
        if th.is_alive():
            raise Timeout(f"推理超过 {job.timeout} 秒")
        if "error" in res:
            raise res["error"]
        r = res["r"]
        info.update(cands=r["seg_str"], ms_infer=r["ms_infer"], ms_rank=r["ms_rank"],
                    why=[f"{x['q'].split('.')[-1]} {x['score']} {'/'.join(map(str, x['why']))}" for x in r["segs"]])
        m = merge(parse_segs(p.get("pre", ""), repo), [(x["file"], x["a"], x["b"]) for x in r["segs"]], cap)
        new = dict(p, pre=pre_str(m, repo), pre_lines=nlines(m))
        info.update(pre=new["pre"], pre_lines=new["pre_lines"], added=len(m) - len(parse_segs(p.get("pre", ""), repo)))
    except Exception as e:
        info["fallback"] = f"{type(e).__name__}: {str(e)[:300]}"
        new = dict(p)
    info["ms_local"] = round(1000 * (time.time() - t0))
    new["infer"] = info
    return new


def _rank_into(res, ex, repo, test, desc, k, deadline):
    try:
        res["r"] = rank(ex, repo, test, desc, k=k, deadline=deadline)
    except Exception as e:
        res["error"] = e
