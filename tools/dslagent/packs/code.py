"""资料包 code（改代码任务）：规划路径 v2 的确定性数据包（不调模型），由 plan35/proto 的 pack.py + proto2 的补查 / 测试断言
改成对任意项目目录用。实现 packs/__init__.py 里写的资料包接口（plan_outline / files / TASK_DESC / PACK_DESC /
PLAN_RULES / PLAN_RULES_END / plan_problems），配套验收是 verify/code.py。旧路径 tools.dslagent.v2pack 转发到这里。

- build(project, task)：从任务原文抽名字 → 按区分度给非测试 .py 打分选种子模块 → 沿 import 走一跳 → 小文件全文、
  大文件只给文件头和命中的函数；登记处行（同列名字共现、ALLOWED_/注册/白名单 一类）；被点名字的引用行；
  import 了候选模块的测试文件的断言行；候选文件大纲。总长超过 PACK_CHARS 时从最后的候选块砍起。
- test_asserts(project, files, skip)：import 了（或按路径 / 模块名引用了）这些模块的测试文件的断言行。
文件遍历跳过隐藏目录、__pycache__、node_modules、venv 等（同 verbs/code/defs/_sandbox.py 的 SKIP_DIRS）。
"""
import ast
import math
import os
import re
from pathlib import Path

from .. import promptfile as PF

NAME = "code"
PACK_CHARS = 40000       # 数据包总字符上限（含测试断言）
FULL_MAX = 150           # ≤ 这么多行的候选文件给全文
TOP_HITS, MAX_FUNCS = 5, 10   # 大文件：顶层命中最多几处、相关函数最多几个
SEC_CAP = 7000           # 登记处 / 引用行 / 非 .py 命中：每节最多字符
Q_LINES = 40
T_CAP_FILE, T_CAP = 2500, 9000
SKIP_DIRS = {"__pycache__", "node_modules", "venv", "env", "site-packages", "build", "dist"}
TEXT_SUF = {".py", ".zs", ".md", ".txt", ".json", ".ui", ".entity", ".toml", ".ini", ".cfg", ".yaml", ".yml", ".sql",
            ".html", ".csv"}
STOP = set("的和里有是等但没要也在时就给看把还不这个那就会对该其被让为或并及与之后前中上下就都能用可")
REG_RE = re.compile(r"ALLOWED_|OPTIONS|COMMANDS|__all__|WHITELIST|白名单|REGISTRY|注册|速查|能力清单|VERBS\b|@reg\.verb")


# ------------------------------------------------------------ 文件


def is_test(rel):
    parts = Path(rel).parts
    return any(p in ("tests", "test") for p in parts[:-1]) or Path(rel).name.startswith("test_") \
        or Path(rel).name == "conftest.py"


def text_files(project, max_size=400_000):
    """(相对路径, 绝对路径)：项目里的文本文件，跳过隐藏目录和 SKIP_DIRS。"""
    root = Path(project)
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith("."))
        for name in sorted(files):
            f = Path(d) / name
            if f.suffix not in TEXT_SUF or name.startswith("."):
                continue
            try:
                if not f.is_file() or f.stat().st_size > max_size:
                    continue
            except OSError:
                continue
            yield str(f.relative_to(root)), f


def read(project, rel):
    p = Path(project) / rel
    try:
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
    except OSError:
        return None


def snippet(project, rel, a=None, b=None, text=None):
    t = read(project, rel) if text is None else text
    if t is None:
        return None
    ls = t.splitlines()
    a, b = max(1, a or 1), min(len(ls), b or len(ls))
    return f"### {rel} L{a}-{b}（共 {len(ls)} 行）\n```\n" + "\n".join(
        f"{i:4d}| {ls[i - 1]}" for i in range(a, b + 1)) + "\n```"


def modname(rel):
    parts = list(Path(rel).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


# ------------------------------------------------------------ 抽名字、打分


def terms_of(prompt):
    quoted = re.findall(r"[「`](.+?)[」`]", prompt)
    terms, peers = set(), set()
    for q in quoted:
        for part in re.split(r"<[^>]*>|[，,]", q):
            part = part.strip(" []")
            if len(part) >= 2:
                terms.add(part)
    for lst in re.findall(r"((?:[一-鿿]{2,6}、)+[一-鿿]{2,6})", prompt):
        items = [re.sub(r"(等|或|和).*$", "", x) for x in lst.split("、")]
        items = [re.sub(r"^.*(有|里|的)", "", x) for x in items]
        items = [x for x in items if len(x) >= 2]
        if len(items) >= 2:
            peers |= set(items)
    terms |= set(re.findall(r"[A-Za-z_][A-Za-z_\-]{2,}", prompt))
    terms |= {p for p in re.findall(r"[\w./-]+\.py", prompt)}
    for chunk in re.split(r"[^一-鿿]+", prompt):
        for w in re.split("[" + "".join(STOP) + "]", chunk):
            if 2 <= len(w) <= 6:
                terms.add(w)
    return terms, peers


def blocks(src):
    """顶层函数 / 类及大类里方法的 (起, 止) 行号。"""
    out = []
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return out
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((n.lineno - len(n.decorator_list), n.end_lineno))
        elif isinstance(n, ast.ClassDef):
            meth = [m for m in n.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if n.end_lineno - n.lineno <= 60 or not meth:
                out.append((n.lineno, n.end_lineno))
            else:
                out.append((n.lineno, meth[0].lineno - 1))
                out += [(m.lineno - len(m.decorator_list), m.end_lineno) for m in meth]
    return out


def imports_of(rel, src, all_files):
    mods = set()
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return mods
    pkg = Path(rel).parent
    for n in ast.walk(tree):
        names = []
        if isinstance(n, ast.Import):
            names = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:
                p = pkg
                for _ in range(n.level - 1):
                    p = p.parent
                base = ".".join([*p.parts, *([base] if base else [])])
            names = [base] + [f"{base}.{a.name}" for a in n.names]
        for m in names:
            for cand in (m.replace(".", "/") + ".py", m.replace(".", "/") + "/__init__.py"):
                if cand in all_files:
                    mods.add(cand)
    for m in re.findall(r"^\s*(?:from|import)\s+(\w+)", src, re.M):     # 同目录裸 import（sys.path.insert 后）
        cand = str(pkg / f"{m}.py")
        if cand in all_files:
            mods.add(cand)
    return mods


def outline(project, files, src=None):
    """候选文件的顶层函数 / 类及行区间（规划给子任务写「文件:起-止」入参用）。"""
    out = ["## 文件大纲（候选文件的顶层函数/类，行区间；派任务入参可按「文件:起-止」引用）\n```"]
    for r in files:
        s = (src or {}).get(r) or read(project, r)
        if s is None:
            continue
        items = []
        try:
            body = ast.parse(s).body
        except (SyntaxError, ValueError):
            body = []
        for nd in body:
            if isinstance(nd, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                items.append(f"{nd.name}:{nd.lineno - len(nd.decorator_list)}-{nd.end_lineno}")
            elif isinstance(nd, ast.Assign) and nd.end_lineno - nd.lineno >= 3:
                nm = ",".join(getattr(t, "id", "?") for t in nd.targets)
                items.append(f"{nm}=:{nd.lineno}-{nd.end_lineno}")
        out.append(f"{r}（共 {len(s.splitlines())} 行）: " + " ".join(items))
    out.append("```")
    return "\n".join(out)


# ------------------------------------------------------------ 数据包


def build(project, task, opening="未跑（验收时统一跑一次全量测试）", budget=PACK_CHARS, outline_only=False):
    """返回 (数据包文本, 信息 {chars, cands, seeds, peers, test_files})。
    outline_only：选完候选文件就返回，文本只有「文件大纲」一节（全部候选，不按 budget 砍；规划用）。"""
    project = Path(project)
    terms, peers = terms_of(task)
    src = {}
    for rel, f in text_files(project):
        if rel.endswith(".py"):
            try:
                src[rel] = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
    code = [r for r in src if not is_test(r)]
    # 名字的区分度：命中文件越少越重；命中超过 40% 文件的词丢掉
    hits = {w: [r for r in code if w in src[r]] for w in terms | peers}
    weight = {w: 1.0 / len(h) for w, h in hits.items() if h and len(h) <= max(3, 0.4 * len(code))}
    for p in peers:
        if hits.get(p):
            weight[p] = max(weight.get(p, 0), 1.0)
    for w in terms:                       # 任务里点名的路径
        if w.endswith(".py") and w in src:
            weight[w] = 2.0
    # 命中目录名 / 文件名的词（如「probe 动词包」→ verbs/probe/…）另加分；大文件按行数打折（命中多是因为长）
    # 任务里写成「xxx/」的按路径前缀算（verbs/ 只指顶层 verbs/，不指 tools/dslagent/verbs/）
    prefixes = set(re.findall(r"(?<![\w./-])([\w.-]+(?:/[\w.-]+)*)/", task))
    named = {w for w in terms | peers if (len(w) >= 3 or re.fullmatch(r"[一-鿿]{2,}", w)) and w not in prefixes}
    score = {}
    for r in code:
        parts = set(Path(r).parts[:-1]) | {Path(r).stem}
        s = sum(wt for w, wt in weight.items() if w in src[r] or w == r) + sum(1.0 for w in named if w in parts) \
            + sum(1.0 for x in prefixes if r.startswith(x + "/"))
        score[r] = s / (1 + math.log10(max(len(src[r].splitlines()), 100) / 100))
    seeds = [r for r, s in sorted(score.items(), key=lambda x: (-x[1], x[0])) if s > 0][:8]
    seeds += [r for r in code if Path(r).stem in peers and r not in seeds]
    cands = list(seeds)
    code_set = set(code)
    for r in list(seeds):
        for m in sorted(imports_of(r, src[r], code_set)):
            if m not in cands and score.get(m, 0) > 0:
                cands.append(m)
    if outline_only:
        text = outline(project, cands, src)
        return text, {"chars": len(text), "cands": cands, "seeds": seeds, "peers": sorted(peers), "test_files": [],
                      "n_terms": len(weight)}
    keys = set(weight)

    def cand_block(r):
        ls = src[r].splitlines()
        n = len(ls)

        def add(a, b, title):
            b = min(b, n)
            return f"### {r} L{a}-{b}{title}\n```python\n" + "\n".join(
                f"{i:4d}| {ls[i - 1]}" for i in range(a, b + 1)) + "\n```\n"
        if n <= FULL_MAX:
            return add(1, n, "（全文）")
        got = set()
        # 大文件只按区分度高的名字找命中行；顶层命中、相关函数各按命中名字的总权重取前几个
        strong = {k for k in keys if weight[k] >= 0.1} or keys
        lw = {i + 1: sum(weight[k] for k in strong if k in l) for i, l in enumerate(ls)}
        hit = {i for i, w in lw.items() if w > 0}
        bl = blocks(src[r])
        inside = {i for a, b in bl for i in range(a, b + 1)}
        doc_end = next((i for i, l in enumerate(ls[1:], 2) if l.strip().endswith('"""')), 1)
        rngs = [(1, min(doc_end, 30), "（文件头）")]
        top = sorted(sorted(hit - inside, key=lambda h: -lw[h])[:TOP_HITS])
        rngs += [(max(1, h - 2), min(n, h + 3), "（顶层命中）") for h in top]
        fns = [(sum(lw[h] for h in hit if a <= h <= b), a, b) for a, b in bl if b - a <= 120]
        fns = sorted(sorted((x for x in fns if x[0] > 0), key=lambda x: -x[0])[:MAX_FUNCS], key=lambda x: x[1])
        rngs += [(a, b, "（相关函数）") for _, a, b in fns]
        txt = f"<!-- {r} 共 {n} 行，只给相关部分 -->\n"
        for a, b, title in rngs:
            if set(range(a, b + 1)) <= got:
                continue
            got.update(range(a, b + 1))
            txt += add(a, b, title)
        return txt

    blocks_txt = [cand_block(r) for r in cands]
    reg = []
    for r in code:
        for i, l in enumerate(src[r].splitlines(), 1):
            if sum(p in l for p in peers) >= 2 or (REG_RE.search(l) and any(k in l for k in keys)):
                reg.append(f"{r}:{i}: {l.strip()[:300]}")
    ref = []
    for w in sorted(weight, key=lambda w: (-weight[w], w)):
        if weight[w] < 0.2 and w not in peers:
            continue
        n = 0
        for r in code:
            for i, l in enumerate(src[r].splitlines(), 1):
                if w in l and n < 25:
                    ref.append(f"[{w}] {r}:{i}: {l.strip()[:200]}")
                    n += 1
    ta, tfiles = test_asserts(project, cands)
    head = f"# 数据包\n\n## 开局测试\n{opening}\n"
    tail = ["## 同列名字共现行 / 登记处（全仓非测试文件）\n" + f"同列名字：{sorted(peers)}\n```\n"
            + "\n".join(reg)[:SEC_CAP] + "\n```\n",
            "## 被点名字的全部引用行（非测试，区分度高的名字，每个最多 25 行）\n```\n" + "\n".join(ref)[:SEC_CAP] + "\n```\n"]
    if ta:
        tail.append(ta)
    n_cand = len(cands)

    def compose(k):
        return "\n".join([head, "## 候选模块\n"] + blocks_txt[:k] + tail) + "\n" + outline(project, cands[:k], src)
    text = compose(n_cand)
    while len(text) > budget and n_cand > 1:          # 超长：从最后的候选块砍起
        n_cand -= 1
        text = compose(n_cand)
    if len(text) > budget:
        text = text[:budget] + "\n…（数据包过长，已截断）"
    return text, {"chars": len(text), "cands": cands[:n_cand], "seeds": seeds, "peers": sorted(peers),
                  "test_files": tfiles, "n_terms": len(weight)}


# ------------------------------------------------------------ 测试断言


def _imports(src):
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return set()
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            out.add(n.module)
            out |= {f"{n.module}.{a.name}" for a in n.names}
    return out


def test_asserts(project, files, skip=()):
    """import 了（或按路径 / 模块名引用了）files 里模块的测试文件的断言行。返回 (文本, 用到的测试文件)。"""
    mods = {modname(r): r for r in files if r.endswith(".py") and not is_test(r)}
    if not mods:
        return "", []
    parts, used, total = ["## 相关测试断言（自动收入：import 了被改模块的测试文件）"], [], 0
    for rel, f in text_files(project):
        if not (rel.endswith(".py") and is_test(rel)) or rel in skip:
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        imps = _imports(src)
        hit = sorted(m for m in mods if m in imps or any(i.startswith(m + ".") for i in imps)
                     or mods[m] in src or (m.count(".") >= 1 and f'"{m}"' in src))
        if not hit:
            continue
        ls = src.splitlines()
        keep = [i for i, l in enumerate(ls, 1) if re.search(r"\bassert\b|\bcheck\(|raises|assertEqual|assertIn", l)]
        if not keep:
            continue
        body = "\n".join(f"{i:4d}| {ls[i - 1]}" for i in keep)[:T_CAP_FILE]
        blk = f"### {rel}（引用了 {hit[:6]}）\n```python\n{body}\n```"
        if total + len(blk) > T_CAP:
            break
        total += len(blk)
        parts.append(blk)
        used.append(rel)
    return ("\n\n".join(parts) if used else ""), used


# ------------------------------------------------------------ 补查


def grep(project, rx, limit=Q_LINES, py_only=False, skip_tests=False, dirs=None):
    """逐行搜。返回 (前 limit 条「文件:行: 内容」, 总命中数, [(文件, 行号, 行)] 全部)。dirs：只搜这些目录前缀。"""
    hits, allh = [], []
    for rel, f in text_files(project):
        if py_only and not rel.endswith(".py"):
            continue
        if skip_tests and is_test(rel):
            continue
        if dirs is not None and not any(rel == d or rel.startswith(d.rstrip("/") + "/") for d in dirs):
            continue
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, l in enumerate(lines, 1):
            if rx.search(l):
                allh.append((rel, i, l))
                if len(hits) < limit:
                    hits.append(f"{rel}:{i}: {l.strip()[:200]}")
    return hits, len(allh), allh


# ------------------------------------------------------------ 资料包接口（见 packs/__init__.py）

OLD_RX_LINE = re.compile(r"^\s*#\s*旧写法\s*[:：]\s*(.+?)\s*$", re.M)
TASK_DESC = "改代码任务"
PACK_DESC = "从仓库里确定性抽出的「数据包」（相关代码片段带行号、登记处、引用行、相关测试断言、文件大纲）"

PLAN_RULES = PF.text("packs/code/plan_rules.md")

PLAN_RULES_END = PF.text("packs/code/plan_rules_end.md")


def files(project):
    """快照 / 对比用：项目里的文本文件。"""
    return text_files(project)


def plan_outline(task, project):
    """只产文件大纲（不收代码片段 / 引用行 / 测试断言；规划的 user 用）。出参 {text, refs, 记录}。"""
    text, info = build(project, task, outline_only=True)
    return {"text": text, "refs": list(info["cands"]), "记录": {"候选": list(info["cands"])}}


def plan_problems(main, body, cl, generic):
    """计划静态检查里 code 专属的：#清单 段、旧写法 正则；顺序 = 清单、通用（预算）、旧写法。"""
    probs = []
    if cl is None or not cl.get("items"):
        probs.append("缺 #清单 段（脚本最后写 #清单，逐行 改 路径:函数名 / 新建 路径 / 删 路径）")
    probs += generic
    for rx in OLD_RX_LINE.findall(main):
        try:
            re.compile(rx)
        except re.error as e:
            probs.append(f"# 旧写法 的正则不合法 {rx!r}：{e}")
    return probs
