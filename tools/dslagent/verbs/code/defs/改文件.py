"""v6：刷新的片段同时刷新步号和函数清单。
精确替换，v4 支持一次多处：收 {file, old, new} 或 {edits: [{file, old, new}, …]}
（脚本里传 {r}，引擎转成 JSON 文本）。

脚本末尾「#改法 名」段（tools/dsl_sections）解析出的 {edits:[…], files:[{file, content}]} 也直接收：
改文件 {e1} 一次套全部条目——files 是「@@ 新建」的新文件（目标已存在不覆盖），edits 是替换。

返回 {ok: 是/否, msg, n}。逐处在内存里依次应用（同一文件的多处按顺序叠加），
每处 old 必须在当时的文本里恰好出现 1 次（否则 ok=否，msg 报出现了几次）；任何一处失败就整体不改（原子），
msg 说明是第几处、为什么。测试文件（tests/ 下、test_*.py 等）不许改。写之前每个文件过安全约束（reason.check）。
edits 里某项 old 为空（或缺省）且目标文件不存在 = 新建（内容 = new，父目录自动建）；文件已存在而 old 为空仍报错。
CRLF 的文件按原换行写回：old/new 只用 LF 对不上原文时换成 CRLF 再找，没动到的行一字不变。
成功后把笔记【代码】区里这些文件的片段刷新成改后的内容。
例如 设 res = 改文件 {r}
"""

import json
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
    if e.get("old") is None:
        return []
    e = _norm(e, notes)
    return [{"file": e.get("file"), "old": e.get("old"), "new": e.get("new")}]


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
    from _sandbox import is_test_path, resolve
    import _notes
    try:
        e = 改法 if isinstance(改法, dict) else json.loads(改法)
    except (TypeError, json.JSONDecodeError) as ex:
        return {"ok": "否", "msg": f"改法不是 JSON 对象：{ex}", "n": 0}
    if not isinstance(e, dict):
        return {"ok": "否", "msg": "改法要是 {file, old, new} 或 {edits:[…]} 对象", "n": 0}
    news = e.get("files") if isinstance(e.get("files"), list) else []
    if not (isinstance(e.get("edits"), list) and e["edits"]) and e.get("old") is None and not news:
        return {"ok": "否", "msg": "没有给 edits（缺失或空列表），这一轮没改任何文件", "n": 0}
    edits = _list(e, notes)
    total = len(edits) + len(news)
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
        if not old:
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
        n, old, new = _locate(texts[rel], old, new)
        if n != 1:
            why = "没找到（注意别带行号前缀「  12| 」、缩进要一致" + \
                  ("；同一文件前面几处改过之后的文本才是这里的对照" if many else "") + "）" \
                if n == 0 else f"出现了 {n} 次，要多带几行上下文让它唯一"
            why = f"出现 0 次，{why}" if n == 0 else why
            return fail(f"old 在 {rel} 里{why}")
        if old == new:
            return fail(f"{rel}：old 和 new 一样，没有改动")
        texts[rel] = texts[rel].replace(old, new)
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
    head = f"已改 {len(edits) - sum(1 for e in edits if not e.get('old'))} 处" + (f"、新建 {len(created)} 个文件" if created else "")
    return {"ok": "是", "n": total,
            "msg": f"{head}：" + "、".join(parts) + "；【代码】区已刷新为改后内容"}


def _spots(text, old, cap=5):
    """old 在 text 里各处的起点行号（最多 cap 处），每处带前后各 1 行：[(行号, 摘要)]。"""
    lines, out, pos = text.split("\n"), [], text.find(old)
    while pos >= 0 and len(out) < cap:
        a = text.count("\n", 0, pos)
        near = " ⏎ ".join(x.strip()[:60] for x in lines[max(0, a - 1):a + 2])
        out.append((a + 1, near))
        pos = text.find(old, pos + len(old))
    return out


def 核对计划(root, sections) -> list:
    """计划检查用（只读，不改文件）：sections 是 split_sections 给的 {段名: {edits, files}}。
    每段按 改文件 的实际行为在内存里顺序套用，返回问题文本列表：文件不存在 / old 出现 0 次或多次（报次数和行号）/
    @@ 新建 的文件已存在 / 路径越界、测试文件。"""
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
            if not isinstance(old, str) or not old or not isinstance(new, str):
                continue
            n, old, new = _locate(texts[rel], old, new)
            if n == 0:
                probs.append(f"{where}：{rel} 里找不到 old（出现 0 次；原文要一字不差、缩进一致"
                             + ("；前面几处改过之后的文本才是这里的对照" if k > 1 else "") + "）。开头：" + old.split("\n")[0].strip()[:60])
                continue
            if n > 1:
                sp = _spots(texts[rel], old)
                more = f"（只列前 {len(sp)} 处）" if n > len(sp) else ""
                probs.append(f"{where}：old 在 {rel} 里出现 {n} 次，必须唯一{more}："
                             + "；".join(f"第 {a} 行「{b}」" for a, b in sp)
                             + "。建议在 old 前后多带几行上下文让它唯一")
                continue
            if new == old:
                probs.append(f"{where}：{rel} 里 old 和 new 一样，没有改动")
                continue
            texts[rel] = texts[rel].replace(old, new)
    return probs
