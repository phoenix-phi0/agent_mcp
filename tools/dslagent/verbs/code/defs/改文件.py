"""v6：刷新的片段同时刷新步号和函数清单。
精确替换，v4 支持一次多处：收 {file, old, new} 或 {edits: [{file, old, new}, …]}
（脚本里传 {r}，引擎转成 JSON 文本）。

返回 {ok: 是/否, msg, n}。逐处在内存里依次应用（同一文件的多处按顺序叠加），
每处 old 必须在当时的文本里恰好出现 1 次；任何一处失败就整体不改（原子），
msg 说明是第几处、为什么。测试文件（tests/ 下、test_*.py 等）不许改。
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
    e = _norm(e, notes)
    return [{"file": e.get("file"), "old": e.get("old"), "new": e.get("new")}]


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
    if not (isinstance(e.get("edits"), list) and e["edits"]) and e.get("old") is None:
        return {"ok": "否", "msg": "没有给 edits（缺失或空列表），这一轮没改任何文件", "n": 0}
    edits = _list(e, notes)
    root = Path(WORKSPACE).resolve()
    texts, orig = {}, {}
    many = len(edits) > 1
    for k, ed in enumerate(edits, 1):
        where = f"第 {k} 处（共 {len(edits)} 处）" if many else ""
        fail = lambda m: {"ok": "否", "n": len(edits),  # noqa: E731
                          "msg": (f"{where}：{m}；整体没有改动，所有文件保持原样" if many else m)}
        if not isinstance(ed, dict):
            return fail("每处要是 {file, old, new} 对象")
        f, old, new = str(ed.get("file") or ""), ed.get("old"), ed.get("new")
        if not f:
            return fail(f"缺 file 键（这处给的键：{'、'.join(map(str, ed)) or '无'}；"
                        f"old 开头「{str(old)[:24]}」）——每处要写成 {{file, old, new}}，file 是相对路径")
        if not isinstance(old, str) or not isinstance(new, str) or not old:
            return fail(f"{f or '?'}：old / new 要是文本，old 不能为空")
        p, err = resolve(root, f)
        if err:
            return fail(err)
        if not p.is_file():
            return fail(f"没有这个文件：{f}")
        if is_test_path(root, p):
            return fail(f"不许改测试文件：{f}")
        rel = str(p.relative_to(root))
        if rel not in texts:
            texts[rel] = orig[rel] = p.read_text(encoding="utf-8")
        n = texts[rel].count(old)
        if n != 1:
            why = "没找到（注意别带行号前缀「  12| 」、缩进要一致" + \
                  ("；同一文件前面几处改过之后的文本才是这里的对照" if many else "") + "）" \
                if n == 0 else f"出现了 {n} 次，要多带几行上下文让它唯一"
            return fail(f"old 在 {rel} 里{why}")
        if old == new:
            return fail(f"{rel}：old 和 new 一样，没有改动")
        texts[rel] = texts[rel].replace(old, new)
    import 推理 as T
    for rel, t in texts.items():
        why = T._R().check("改写", root, rel, t)
        if why:
            return fail(why)
    for rel, t in texts.items():
        (root / rel).write_text(t, encoding="utf-8")
    st = _notes.load(WORKSPACE)
    st["stats"]["edits"].append(len(edits))
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
        parts.append(f"{rel}（{len(a)} 行 → {len(b)} 行）")
    return {"ok": "是", "n": len(edits),
            "msg": f"已改 {len(edits)} 处：" + "、".join(parts) + "；【代码】区已刷新为改后内容"}
