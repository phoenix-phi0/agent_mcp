"""v7：点名函数整段替换 / 函数内锚点 / 缩进容错（见下）。v6：刷新的片段同时刷新步号和函数清单。
精确替换，v4 支持一次多处：收 {file, old, new} 或 {edits: [{file, old, new}, …]}
（脚本里传 {r}，引擎转成 JSON 文本）。

脚本末尾「#改法 名」段（tools/dsl_sections）解析出的 {edits:[…], files:[{file, content}]} 也直接收：
改文件 {e1} 一次套全部条目——files 是「@@ 新建」的新文件（目标已存在不覆盖），edits 是替换。

返回 {ok: 是/否, msg, n}。逐处在内存里依次应用（同一文件的多处按顺序叠加），
每处 old 必须在当时的文本里恰好出现 1 次（否则 ok=否，msg 报出现了几次）；任何一处失败就整体不改（原子），
msg 说明是第几处、为什么。测试文件（tests/ 下、test_*.py 等）不许改。写之前每个文件过安全约束（reason.check）。
edits 里某项 old 为空（或缺省）且目标文件不存在 = 新建（内容 = new，父目录自动建）；文件已存在而 old 为空仍报错。
CRLF 的文件按原换行写回：old/new 只用 LF 对不上原文时换成 CRLF 再找，没动到的行一字不变。
定位（v7，改文件 和 核对计划 共用 _resolve）：
- 点名函数：edit 带 func（别名 函数 / function / fn；#改法 段写「@@ 改 路径 函数 名」），old 为空 = 整个函数换成 new
  （.zs 从「[公开 ]函数 名」到同缩进的 结束，.py 从 def/class 头到缩进回落；Class.method 可点名方法）；
  函数名必须在文件里唯一，没有 / 多个时报候选或行号。新函数首行缩进和原函数不同就整体挪齐。
- 锚点：func 和 old 都给 = 只在这个函数的范围里找 old（在函数里唯一即可）。
- 缩进容错：old 精确出现 0 次时逐行比、忽略行首行尾空白；恰好一处且各行缩进差一致才套用，new 按同样的差挪缩进，msg 里注明。
- 成功的返回里 modes 列出用到的非精确定位（函数 / 锚点 / 缩进容错 / 锚点+缩进容错）。
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


def _norm(ed, notes):
    """plan2 兜底：path/filename/文件 等常见别名归一成 file，记下说明。"""
    if isinstance(ed, dict) and not ed.get("file"):
        for a in ALIASES:
            if ed.get(a):
                ed = dict(ed, file=ed[a])
                notes.add(f"已把 {a} 当作 file")
                break
    return ed


def _list(e, notes):
    if isinstance(e.get("edits"), list) and e["edits"]:
        return [_norm(x, notes) for x in e["edits"]]
    if e.get("old") is None and not _func_of(e):
        return []
    e = _norm(e, notes)
    one = {"file": e.get("file"), "old": e.get("old"), "new": e.get("new")}
    if _func_of(e):
        one["func"] = _func_of(e)
    return [one]


def _read(p):
    """按原样读（不转换换行）：CRLF 文件写回时还是 CRLF。"""
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def _locate(text, old, new):
    """old 在 text 里的出现次数；text 是 CRLF 而 old 只用 LF 时换成 CRLF 再数。返回 (次数, old, new)。"""
    n = text.count(old)
    if n == 0 and "\r\n" in text and "\n" in old and "\r\n" not in old:
        crlf = old.replace("\n", "\r\n")
        k = text.count(crlf)
        if k:
            return k, crlf, new.replace("\r\n", "\n").replace("\n", "\r\n")
    return n, old, new


FUNC_KEYS = ("func", "函数", "function", "fn")
ZS_HEAD = re.compile(r"^([ \t]*)(?:(?:公开|私有|内部)\s+)?函数\s+([^\s(（]+)")
PY_HEAD = re.compile(r"^([ \t]*)(?:async\s+)?(?:def|class)\s+(\w+)")


def _func_of(ed):
    """edit 里点名的函数（func / 函数 / function / fn）；「公开 函数 名 参数」「def 名(」这类整行写法只取名字。"""
    for k in FUNC_KEYS:
        v = ed.get(k) if isinstance(ed, dict) else None
        if isinstance(v, str) and v.strip():
            s = re.sub(r"^\s*(?:(?:公开|私有|内部)\s+)?(?:函数|async\s+def|def|class)\s+", "", v.strip())
            return re.split(r"[\s(（:：]", s, 1)[0]
    return ""


def _ind(line):
    return len(line) - len(line.lstrip(" \t"))


def _func_spans(text, name):
    """text 里名叫 name 的函数的范围 [(起点偏移, 终点偏移, 首行行号, 头部缩进串)]，终点含最后一行的换行。
    .zs：「[公开 ]函数 名 …」到同缩进的「结束」；.py：def / class 头到缩进回落前最后一个非空行（Class.method 先找类再在类里找）。
    缩进比头部深的行、空行都算函数体；碰到缩进不深于头部的非空行就停（.zs 同缩进的 结束 算进来）。"""
    lines = text.splitlines(keepends=True)
    offs = [0]
    for ln in lines:
        offs.append(offs[-1] + len(ln))
    parts = name.split(".") if "." in name else [name]

    def scan(lo, hi, nm):
        out = []
        for i in range(lo, hi):
            body = lines[i].rstrip("\r\n")
            m = ZS_HEAD.match(body) or PY_HEAD.match(body)
            if not m or m.group(2) != nm:
                continue
            h = _ind(body)
            last, j = i, i + 1
            while j < hi:
                s = lines[j].strip()
                if not s:
                    j += 1
                    continue
                d = _ind(lines[j].rstrip("\r\n"))
                if d > h:
                    last = j
                    j += 1
                    continue
                if d == h and s == "结束" and ZS_HEAD.match(body):
                    last = j
                break
            out.append((i, last + 1, body[:h]))
        return out
    found = [(0, len(lines), "")]
    for nm in parts:
        nxt = []
        for a, b, _ in found:
            nxt += scan(a if a == 0 and b == len(lines) else a + 1, b, nm)
        found = nxt
    return [(offs[a], offs[b], a + 1, ind) for a, b, ind in found]


def _func_list(text, cap=8):
    """文件里能认出的函数名（报「没有这个函数」时列候选）。"""
    names = []
    for ln in text.splitlines():
        m = ZS_HEAD.match(ln) or PY_HEAD.match(ln)
        if m and m.group(2) not in names:
            names.append(m.group(2))
    return names[:cap] + (["…"] if len(names) > cap else [])


def _eol(text):
    return "\r\n" if "\r\n" in text else "\n"


def _shift(block, delta, ch=" "):
    """非空行整体移 delta 格（负数＝去掉行首最多 -delta 个空白）。"""
    out = []
    for ln in block.split("\n"):
        if not ln.strip():
            out.append(ln)
        elif delta > 0:
            out.append(ch * delta + ln)
        else:
            k = min(-delta, _ind(ln))
            out.append(ln[k:])
    return "\n".join(out)


def _fuzzy(text, old):
    """缩进容错：逐行比较、忽略行首行尾空白。返回 [(起点, 终点, 缩进差, 首行行号)]（只收各行缩进差一致的匹配），
    以及只因各行缩进差不一致被丢掉的个数。终点不含最后一行的换行。"""
    o = old[:-1] if old.endswith("\n") else old
    ol = o.replace("\r\n", "\n").split("\n")
    if not any(x.strip() for x in ol):
        return [], 0
    keys = [x.strip() for x in ol]
    lines = text.splitlines(keepends=True)
    offs = [0]
    for ln in lines:
        offs.append(offs[-1] + len(ln))
    tl = [ln.rstrip("\r\n") for ln in lines]
    tk = [x.strip() for x in tl]
    m, hits, bad = len(ol), [], 0
    for i in range(0, len(tl) - m + 1):
        if tk[i:i + m] != keys:
            continue
        ds = {_ind(tl[i + k]) - _ind(ol[k]) for k in range(m) if keys[k]}
        if len(ds) != 1:
            bad += 1
            continue
        hits.append((offs[i], offs[i + m - 1] + len(tl[i + m - 1]), ds.pop(), i + 1))
    return hits, bad


def _resolve(text, old, new, func=""):
    """一处改法在 text 里定位并替换（改文件 和 核对计划 共用，保证检查和实际套用一致）。
    返回 dict：ok=True 时 text=替换后全文、mode=精确|函数|锚点|缩进容错、note=说明；
    ok=False 时 kind=missing|many|nofunc|manyfunc|same|badindent，n=出现次数，msg=原因，old=实际比对的原文（CRLF 换算后）。"""
    old = old or ""
    if func:
        spans = _func_spans(text, func)
        if not spans and "." in func:
            spans = _func_spans(text, func.rsplit(".", 1)[1])
        if not spans:
            cand = "、".join(_func_list(text)) or "无"
            return dict(ok=False, kind="nofunc", n=0, old=old,
                        msg=f"没有叫「{func}」的函数（文件里的函数：{cand}）")
        if len(spans) > 1:
            return dict(ok=False, kind="manyfunc", n=len(spans), old=old,
                        msg=f"叫「{func}」的函数有 {len(spans)} 个（第 {'、'.join(str(s[2]) for s in spans)} 行），"
                            "改用 old 原文定位，或写 类名.方法名")
        s, e, line, ind = spans[0]
        if not old.strip():
            cur = text[s:e]
            nl = _eol(text)
            body = new.replace("\r\n", "\n")
            first = next((x for x in body.split("\n") if x.strip()), "")
            note = f"按函数 {func} 整段替换（第 {line} 行起）"
            if first and _ind(first) != len(ind):
                body = _shift(body, len(ind) - _ind(first), (ind[:1] or " "))
                note += f"，新函数缩进按原函数挪了 {len(ind) - _ind(first):+d} 格"
            body = body.rstrip("\n") + "\n" if cur.endswith(("\n", "\r")) else body.rstrip("\n")
            if nl == "\r\n":
                body = body.replace("\n", "\r\n")
            if body == cur:
                return dict(ok=False, kind="same", n=1, old=cur, msg="新函数和原函数一样，没有改动")
            return dict(ok=True, text=text[:s] + body + text[e:], mode="函数", note=note)
        sub = text[s:e]
        r = _resolve(sub, old, new)
        if not r["ok"]:
            if r["kind"] in ("missing", "many"):
                r["msg"] = f"在函数 {func}（第 {line} 行起）里" + r["msg"]
            return r
        note = f"在函数 {func} 里定位" + ("（缩进容错）" if r["mode"] == "缩进容错" else "")
        return dict(ok=True, text=text[:s] + r["text"] + text[e:], mode="锚点",
                    note=note + ("；" + r["note"] if r.get("note") and r["mode"] == "缩进容错" else ""),
                    fuzzy=r["mode"] == "缩进容错")
    n, o2, n2 = _locate(text, old, new)
    if n == 1:
        if o2 == n2:
            return dict(ok=False, kind="same", n=1, old=o2, msg="old 和 new 一样，没有改动")
        return dict(ok=True, text=text.replace(o2, n2), mode="精确", note="")
    if n > 1:
        return dict(ok=False, kind="many", n=n, old=o2, msg=f"出现了 {n} 次，要多带几行上下文让它唯一")
    hits, bad = _fuzzy(text, old)
    if len(hits) == 1:
        s, e, d, line = hits[0]
        ch = next((c for c in text[s:s + 1] if c in " \t"), " ")
        body = new.replace("\r\n", "\n")
        body = body[:-1] if old.endswith("\n") and body.endswith("\n") else body
        body = _shift(body, d, ch) if d else body
        if _eol(text) == "\r\n":
            body = body.replace("\n", "\r\n")
        if body == text[s:e]:
            return dict(ok=False, kind="same", n=1, old=old, msg="old 和 new 一样，没有改动")
        return dict(ok=True, text=text[:s] + body + text[e:], mode="缩进容错",
                    note=f"第 {line} 行起按缩进容错匹配（缩进差 {d:+d}，新文同样挪了 {d:+d} 格）" if d else
                         f"第 {line} 行起按缩进容错匹配（只差行尾空白）")
    extra = ""
    if len(hits) > 1:
        extra = f"；忽略缩进后出现 {len(hits)} 次（第 {'、'.join(str(h[3]) for h in hits[:5])} 行），也不唯一"
    elif bad:
        extra = "；忽略缩进后能对上，但各行缩进差不一致，没套用"
    return dict(ok=False, kind="missing", n=0, old=o2, msg="出现 0 次" + extra, extra=extra)


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
    _log({"ok": r["ok"], "msg": r["msg"][:300], "aliased": sorted(notes), "modes": r.get("modes", [])})
    return r


def _do(改法, notes) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    from _sandbox import is_test_path, resolve
    import _notes
    try:
        e = 改法 if isinstance(改法, dict) else json.loads(改法)
    except (TypeError, json.JSONDecodeError) as ex:
        return {"ok": "否", "msg": f"改法不是 JSON 对象：{ex}", "n": 0}
    if not isinstance(e, dict):
        return {"ok": "否", "msg": "改法要是 {file, old, new} 或 {edits:[…]} 对象", "n": 0}
    news = e.get("files") if isinstance(e.get("files"), list) else []
    if not (isinstance(e.get("edits"), list) and e["edits"]) and e.get("old") is None and not news \
            and not _func_of(e):
        return {"ok": "否", "msg": "没有给 edits（缺失或空列表），这一轮没改任何文件", "n": 0}
    edits = _list(e, notes)
    total = len(edits) + len(news)
    modes = []
    root = Path(WORKSPACE).resolve()
    texts, orig, created = {}, {}, []
    many = total > 1
    where = ""

    def fail(m):
        return {"ok": "否", "n": total,
                "msg": (f"{where + '：' if where else ''}{m}；整体没有改动，所有文件保持原样" if many else m)}
    for k, it in enumerate(news, 1):
        where = f"新建第 {k} 个（共 {total} 处）" if many else ""
        if not isinstance(it, dict):
            return fail("新建的每项要是 {file, content} 对象")
        f, c = str(it.get("file") or ""), it.get("content")
        if not f or not isinstance(c, str):
            return fail(f"新建项缺 file 或 content（给的键：{'、'.join(map(str, it)) or '无'}）")
        p, err = resolve(root, f)
        if err:
            return fail(err)
        if is_test_path(root, p):
            return fail(f"不许写测试文件：{f}")
        rel = str(p.relative_to(root))
        if p.exists() or rel in texts:
            return fail(f"{rel} 已存在，@@ 新建 只建新文件（改已有文件用 @@ 改）")
        texts[rel], orig[rel] = c, ""
        created.append(rel)
    for k, ed in enumerate(edits, 1):
        where = f"第 {k} 处（共 {total} 处）" if many else ""
        if not isinstance(ed, dict):
            return fail("每处要是 {file, old, new} 对象")
        f, old, new = str(ed.get("file") or ""), ed.get("old"), ed.get("new")
        func = _func_of(ed)
        if not f:
            return fail(f"缺 file 键（这处给的键：{'、'.join(map(str, ed)) or '无'}；"
                        f"old 开头「{str(old)[:24]}」）——每处要写成 {{file, old, new}}，file 是相对路径")
        if old is None:
            old = ""
        if not isinstance(old, str) or not isinstance(new, str):
            return fail(f"{f or '?'}：old / new 要是文本")
        p, err = resolve(root, f)
        if err:
            return fail(err)
        rel = str(p.relative_to(root))
        if not old and not func:
            if is_test_path(root, p):
                return fail(f"不许写测试文件：{f}")
            if rel in texts or p.exists():
                return fail(f"{rel} 已存在，old 不能为空；要整份重写用 写文件")
            texts[rel], orig[rel] = new, ""
            created.append(rel)
            continue
        if rel not in texts and not p.is_file():
            return fail(f"没有这个文件：{f}")
        if is_test_path(root, p):
            return fail(f"不许改测试文件：{f}")
        if rel not in texts:
            texts[rel] = orig[rel] = _read(p)
        r = _resolve(texts[rel], old, new, func)
        if not r["ok"]:
            if r["kind"] == "same":
                return fail(f"{rel}：{'函数 ' + func + ' 的' if func and not old.strip() else ''}old 和 new 一样，没有改动")
            if r["kind"] in ("nofunc", "manyfunc"):
                return fail(f"{rel} 里{r['msg']}")
            n = r["n"]
            why = "没找到（注意别带行号前缀「  12| 」、缩进要一致" + \
                  ("；同一文件前面几处改过之后的文本才是这里的对照" if many else "") + "）" \
                if n == 0 else f"出现了 {n} 次，要多带几行上下文让它唯一" + \
                ("" if func else "，或在 @@ 改 行后写「函数 名」只在那个函数里找")
            why = f"出现 0 次，{why}{r.get('extra', '')}" if n == 0 else why
            return fail(f"old 在 {rel} 里" + (f"（函数 {func} 内）" if func else "") + why)
        if r["mode"] != "精确":
            notes.add((f"第 {k} 处：" if many else "") + r["note"])
            modes.append(r["mode"] if not r.get("fuzzy") else "锚点+缩进容错")
        texts[rel] = r["text"]
    import 推理 as T
    where = ""
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
    head = f"已改 {len(edits) - sum(1 for e in edits if not e.get('old') and not _func_of(e))} 处" + (f"、新建 {len(created)} 个文件" if created else "")
    out = {"ok": "是", "n": total,
           "msg": f"{head}：" + "、".join(parts) + "；【代码】区已刷新为改后内容"}
    if modes:
        out["modes"] = modes
    return out


def _spots(text, old, cap=5):
    """old 在 text 里各处的起点行号（最多 cap 处），每处带前后各 1 行：[(行号, 摘要)]。"""
    lines, out, pos = text.split("\n"), [], text.find(old)
    while pos >= 0 and len(out) < cap:
        a = text.count("\n", 0, pos)
        near = " ⏎ ".join(x.strip()[:60] for x in lines[max(0, a - 1):a + 2])
        out.append((a + 1, near))
        pos = text.find(old, pos + len(old))
    return out


def 核对计划(root, sections, info=None) -> list:
    """计划检查用（只读，不改文件）：sections 是 split_sections 给的 {段名: {edits, files}}。
    每段按 改文件 的实际行为在内存里顺序套用，返回问题文本列表：文件不存在 / old 出现 0 次或多次（报次数和行号）/
    @@ 新建 的文件已存在 / 路径越界、测试文件 / 点名的函数没有或不唯一。
    定位规则和 改文件 共用 _resolve（精确 → 缩进容错；点名函数时整段替换或只在函数里找）。
    info 给一个列表时，每处用到的非精确定位追加一条 {section, k, file, mode, note}。"""
    sys.path.insert(0, str(Path(__file__).parent))
    from _sandbox import is_test_path, resolve
    root, probs = Path(root).resolve(), []
    for name, e in sections.items():
        notes = set()
        news = e.get("files") if isinstance(e.get("files"), list) else []
        edits = _list(e, notes)
        pre = f"#改法 {name}"
        texts, seen = {}, set()
        for k, it in enumerate(news, 1):
            p, err = resolve(root, str(it.get("file") or ""))
            if err:
                probs.append(f"{pre} 新建第 {k} 个：{err}")
                continue
            rel = str(p.relative_to(root))
            if is_test_path(root, p):
                probs.append(f"{pre} 新建第 {k} 个：不许写测试文件 {rel}")
            elif p.exists() or rel in seen:
                probs.append(f"{pre} 新建第 {k} 个：{rel} 已存在，@@ 新建 只建新文件（要改已有文件用 @@ 改，old 写原文）")
            seen.add(rel)
            texts[rel] = ""
        for k, ed in enumerate(edits, 1):
            f, old, new = str(ed.get("file") or ""), ed.get("old"), ed.get("new")
            func = _func_of(ed)
            where = f"{pre} 第 {k} 处改（共 {len(edits)} 处改）"
            p, err = resolve(root, f)
            if err:
                probs.append(f"{where}：{err}")
                continue
            rel = str(p.relative_to(root))
            if is_test_path(root, p):
                probs.append(f"{where}：不许改测试文件 {rel}")
                continue
            if rel not in texts:
                if not p.is_file():
                    probs.append(f"{where}：文件 {rel} 不存在")
                    continue
                texts[rel] = _read(p)
            if not isinstance(new, str) or (old is not None and not isinstance(old, str)) or (not old and not func):
                continue
            r = _resolve(texts[rel], old or "", new, func)
            if r["ok"]:
                if r["mode"] != "精确" and info is not None:
                    info.append({"section": name, "k": k, "file": rel, "func": func,
                                 "mode": r["mode"] if not r.get("fuzzy") else "锚点+缩进容错", "note": r["note"]})
                texts[rel] = r["text"]
                continue
            fin = f"（函数 {func} 内）" if func else ""
            if r["kind"] in ("nofunc", "manyfunc"):
                probs.append(f"{where}：{rel} 里{r['msg']}")
            elif r["kind"] == "missing":
                o = r["old"]
                probs.append(f"{where}：{rel}{fin or ' '}里找不到 old（出现 0 次；原文要一字不差、缩进一致"
                             + ("；前面几处改过之后的文本才是这里的对照" if k > 1 else "") + "）" + r.get("extra", "")
                             + "。开头：" + o.split("\n")[0].strip()[:60])
            elif r["kind"] == "many":
                n = r["n"]
                base = texts[rel]
                if func:
                    s0, e0 = _func_spans(base, func)[0][:2] if _func_spans(base, func) else (0, len(base))
                    off = base.count("\n", 0, s0)
                    sp = [(a + off, b) for a, b in _spots(base[s0:e0], r["old"])]
                else:
                    sp = _spots(base, r["old"])
                more = f"（只列前 {len(sp)} 处）" if n > len(sp) else ""
                probs.append(f"{where}：old 在 {rel}{fin or ' '}里出现 {n} 次，必须唯一{more}："
                             + "；".join(f"第 {a} 行「{b}」" for a, b in sp)
                             + "。建议在 old 前后多带几行上下文让它唯一"
                             + ("" if func else "，或在 @@ 改 行后写「函数 名」只在那个函数里找；整个函数重写就只写新函数"))
            else:
                probs.append(f"{where}：{rel} 里" + (f"函数 {func} 的新文和原文一样" if func and not (old or "").strip() else " old 和 new 一样") + "，没有改动")
    return probs
