"""v7：条目套用规则统一到 _edits.apply（核对计划、verify.code.apply_edits 同用）。
收 [{file, old, new, line?}, …] 列表，或 {file, old, new} / {edits: [{file, old, new, line?}, …]}（脚本里传 {e1}，引擎转成 JSON 文本）。

脚本末尾「#改法 名」段（tools/dsl_sections）：块里直接写 JSON 列表，解析成 {edits:[…]}，改文件 {e1} 一次套全部条目。
老的 @@ 标记写法（其它包在用）解析出的 files:[{file, content}] 仍收，当作 old 为空的新建条目排在前面（JSON 段里只写 {file, content} 的条目也进 files，
整份覆盖已有文件要用 写文件 {名}）。

返回 {ok: 是/否, msg, n}。同一文件的多条按顺序在内存里叠加：old 在当时的文本里恰好 1 处就用它；多处时有 line 就选起点离 line 最近的
（并列报错），没 line 报错；0 处报错并给近似行提示。任何一条失败就整体不改（全有或全无），msg 逐条写第几条、文件、原因。
old 为空 = 新建（父目录自动建），文件已存在报错。测试文件（tests/ 下、test_*.py 等）不许改。写之前每个文件过安全约束（reason.check）。
CRLF 的文件按原换行写回：old/new 只用 LF 对不上原文时换成 CRLF 再找，没动到的行一字不变。
成功后把笔记【代码】区里这些文件的片段刷新成改后的内容。
例如 设 res = 改文件 {r}
"""

import json
import re
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


ALIASES = ("path", "filepath", "file_path", "filename", "fname", "文件", "文件名", "路径")
DEL_RE = re.compile(r"(?:^|=)\s*删文件\s+(\S+)")
USE_RE = re.compile(r"(?:^|=)\s*(改文件|写文件)\s+\{([^{}\s.]+)\}")
ALIAS_RE = re.compile(r"^设\s+([^\s=.]+)(?:\.[^\s=]+)?\s*=\s*\{([^{}\s.]+)\}$")


def _norm(ed, notes):
    """plan2 兜底：path/filename/文件 等常见别名归一成 file，记下说明。"""
    if isinstance(ed, dict) and not ed.get("file"):
        for a in ALIASES:
            if ed.get(a):
                ed = dict(ed, file=ed[a])
                notes.add(f"已把 {a} 当作 file")
                break
    return ed


def _items(e, notes):
    """改法对象 → 条目列表。老的 files:[{file, content}]（@@ 新建 写法）转成 old 为空的新建条目，排在 edits 前面。"""
    news = [{"file": it.get("file"), "old": "", "new": it.get("content")} if isinstance(it, dict) else it
            for it in (e.get("files") if isinstance(e.get("files"), list) else [])]
    if isinstance(e.get("edits"), list) and e["edits"]:
        return news + [_norm(x, notes) for x in e["edits"]]
    if e.get("old") is None:
        return news
    e = _norm(e, notes)
    return news + [{k: e[k] for k in ("file", "old", "new", "line") if k in e}]


def _log(rec):
    """每次调用记一行到状态目录的 edit_log.jsonl（统计静默错误用）。"""
    from _sandbox import state_dir
    try:
        with open(state_dir(WORKSPACE) / "edit_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def 改文件(改法: str = "") -> dict:
    notes = set()
    r = _do(改法, notes)
    if notes:
        r["msg"] = r["msg"] + "（" + "；".join(sorted(notes)) + "）"
    _log({"ok": r["ok"], "msg": r["msg"][:300], "aliased": sorted(notes)})
    return r


def _do(改法, notes) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _edits as E
    import _notes
    try:
        e = 改法 if isinstance(改法, (dict, list)) else json.loads(改法)
    except (TypeError, json.JSONDecodeError) as ex:
        return {"ok": "否", "msg": f"改法不是 JSON：{ex}", "n": 0}
    if isinstance(e, list):
        e = {"edits": e}
    if not isinstance(e, dict):
        return {"ok": "否", "msg": "改法要是 [{file, old, new, line?}, …] 列表，或 {file, old, new} / {edits:[…]} 对象", "n": 0}
    edits = _items(e, notes)
    if not edits:
        return {"ok": "否", "msg": "没有给 edits（缺失或空列表），这一轮没改任何文件", "n": 0}
    total = len(edits)
    root = Path(WORKSPACE).resolve()
    texts, orig, created, errs = E.apply(root, edits)

    def fail(m):
        return {"ok": "否", "n": total, "msg": m}
    if errs:
        return fail("\n".join(errs) + "\n整体没有改动，所有文件保持原样")
    import 推理 as T
    for rel, t in texts.items():
        why = T._R().check("写入" if rel in created else "改写", root, rel, t)
        if why:
            return fail(why)
    for rel, t in texts.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        with open(root / rel, "w", encoding="utf-8", newline="") as f:
            f.write(t)
    st = _notes.load(WORKSPACE)
    st["stats"]["edits"].append(total)
    for rel, t in texts.items():
        lines = t.splitlines()
        delta = len(lines) - len(orig[rel].splitlines())
        for s in st["snips"]:
            if s["file"] != rel:
                continue
            b = min(len(lines), s["b"] + max(delta, 0))
            a = min(s["a"], b)
            s.update(a=a, b=b, trunc="", step=int(st.get("step", 0)) + 1,
                     funcs=_notes.funcs_of(root, rel, a, b),
                     body="\n".join(f"{i:4d}| {lines[i - 1]}" for i in range(a, b + 1)))
    _notes.save(WORKSPACE, st)
    parts = []
    for rel in texts:
        a, b = orig[rel].splitlines(), texts[rel].splitlines()
        parts.append(f"{rel}（新建，{len(b)} 行）" if rel in created else f"{rel}（{len(a)} 行 → {len(b)} 行）")
    head = f"已改 {len(edits) - sum(1 for e in edits if not e.get('old'))} 处" + (f"、新建 {len(created)} 个文件" if created else "")
    return {"ok": "是", "n": total,
            "msg": f"{head}：" + "、".join(parts) + "；【代码】区已刷新为改后内容"}


def _plan_uses(body):
    """计划主体（段已拿掉）→ (删文件 [(行号, 路径)], {段名: [(行号, 改文件|写文件)]})。
    「设 w = {e2}」「设 w.files = {e2}」记成别名，之后 写文件 {w} 算消费 e2；路径带 {变量} 的 删文件 不计。"""
    dels, uses, alias = [], {}, {}
    for i, raw in enumerate((body or "").splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = ALIAS_RE.match(s)
        if m:
            alias[m.group(1)] = alias.get(m.group(2), m.group(2))
            continue
        m = DEL_RE.search(s)
        if m:
            if "{" not in m.group(1):
                dels.append((i, m.group(1).strip("`'\"「」")))
            continue
        m = USE_RE.search(s)
        if m:
            uses.setdefault(alias.get(m.group(2), m.group(2)), []).append((i, m.group(1)))
    return dels, uses


def _write_problems(root, e, SB):
    """只给 写文件 用的段：files 条目只查路径 / 测试文件 / 目录（覆盖已有文件允许）；带 old / new 的条目 写文件 不收。"""
    files = e.get("files") if isinstance(e.get("files"), list) else []
    edits = e.get("edits") if isinstance(e.get("edits"), list) else []
    total, out = len(files) + len(edits), []
    for k, it in enumerate(files, 1):
        f = str(it.get("file") or "") if isinstance(it, dict) else ""
        if not f or it.get("content") is None:
            out.append(f"第 {k} 条（共 {total} 条）：写文件 的条目要是 {{file, content}}")
            continue
        p, err = SB.resolve(root, f)
        why = err or (SB.is_test_rel(str(p.relative_to(root))) and "不许写测试文件") or (p.is_dir() and "是目录")
        if why:
            out.append(f"第 {k} 条（共 {total} 条）{f}：{why}")
    for k, it in enumerate(edits, len(files) + 1):
        f = it.get("file") if isinstance(it, dict) else ""
        out.append(f"第 {k} 条（共 {total} 条）{f or ''}：写文件 只收 {{file, content}} 整份内容，这条带 old / new"
                   "（改局部用 改文件；整份重写只写 file 和 content）")
    return out


def 核对计划(root, sections, body="") -> list:
    """计划检查用（只读，不改文件）：sections 是 split_sections 给的 {段名: {edits, files}}，body 是拿掉段以后的计划主体。
    每段用 改文件 同一个套用函数（_edits.apply）在内存里顺序套用，返回问题文本列表：
    文件不存在 / old 出现 0 次 / 多处且 line 选不出（报各处行号）/ 新建的文件已存在 / 路径越界、测试文件。
    看 body 里的语句：段第一次被消费之前已 删文件 的路径按「不存在」处理（删在后面不算）；只被 写文件 用的段
    只查 files 条目的路径 / 测试文件（覆盖已有文件允许）。"""
    sys.path.insert(0, str(Path(__file__).parent))
    import _edits as E
    import _sandbox as SB
    root, probs = Path(root).resolve(), []
    dels, uses = _plan_uses(body)
    for name, e in sections.items():
        used = uses.get(name, [])
        if used and {v for _, v in used} == {"写文件"}:
            probs += [f"#改法 {name} {x}" for x in _write_problems(root, e, SB)]
            continue
        items = _items(e, set())
        if not items:
            continue
        first = min((i for i, _ in used), default=0)
        deleted = set()
        for i, f in dels:
            p, err = SB.resolve(root, f)
            if i < first and not err:
                deleted.add(str(p.relative_to(root)))
        probs += [f"#改法 {name} {x}" for x in E.apply(root, items, deleted=deleted)[3]]
    return probs
