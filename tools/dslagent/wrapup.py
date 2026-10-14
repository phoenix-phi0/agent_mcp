"""grok 规划「读超限」后的收尾：按本次已记录的读取调用（read_file / grep / list_dir），在待改项目里用程序重新取出内容，
去重、按调用顺序拼成「已读内容」（总长不超过 CAP，超出时去掉最早的），交给不带工具的收尾调用（v2.plan_read_call）。
grok 自带工具的参数名：read_file {target_file, offset?, limit?}，grep {pattern, path?, glob?, head_limit?, -A/-B/-C?}，list_dir {target_directory}；
也认 path / file / start / end 这几种别名。路径必须落在项目里，落在外面的当作取不到。
"""
import fnmatch
import json
import re
from pathlib import Path

CAP = 120000          # 已读内容总长上限（字）
SEG_CAP = 40000       # 单段上限
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".mypy_cache", ".pytest_cache"}
GREP_LIMIT = 250
MAX_FILE = 2_000_000


def _inside(project, p):
    """p（绝对或相对项目）→ 项目内的绝对 Path；越界 / 不是路径返回 None。"""
    if not isinstance(p, str) or not p.strip():
        return None
    q = Path(p)
    q = (q if q.is_absolute() else project / q).resolve()
    try:
        q.relative_to(project)
    except ValueError:
        return None
    return q


def _int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _lines(path):
    try:
        if path.stat().st_size > MAX_FILE:
            return None
        return path.read_bytes().decode("utf-8").split("\n")
    except (OSError, UnicodeDecodeError):
        return None


def _read_file(project, a):
    p = _inside(project, a.get("target_file") or a.get("path") or a.get("file"))
    if p is None or not p.is_file():
        return None
    lines = _lines(p)
    if lines is None:
        return None
    start = max(1, _int(a.get("offset"), _int(a.get("start"), 1)) or 1)
    n = _int(a.get("limit"))
    end = _int(a.get("end"), start + n - 1 if n else len(lines))
    end = min(max(end, start), len(lines))
    rel = p.relative_to(project)
    body = "\n".join(f"{i}|{lines[i - 1]}" for i in range(start, end + 1))
    return f"### read_file {rel} L{start}-{end}\n{body}"


def _expand_braces(g):
    m = re.search(r"\{([^{}]*)\}", g)
    if not m:
        return [g]
    return [x for alt in m.group(1).split(",") for x in _expand_braces(g[:m.start()] + alt + g[m.end():])]


def _glob_ok(rel, pats):
    if not pats:
        return True
    for g in pats:
        g = g[3:] if g.startswith("**/") else g
        if fnmatch.fnmatch(rel.name, g) or fnmatch.fnmatch(str(rel), g) or fnmatch.fnmatch(str(rel), "*/" + g):
            return True
    return False


def _files(project, base, pats):
    if base.is_file():
        yield base
        return
    for f in sorted(base.rglob("*")):
        rel = f.relative_to(project)
        if f.is_file() and not (set(rel.parts) & SKIP_DIRS) and _glob_ok(rel, pats):
            yield f


def _grep(project, a):
    pat = a.get("pattern")
    if not isinstance(pat, str) or not pat:
        return None
    try:
        rx = re.compile(pat)
    except re.error:
        rx = re.compile(re.escape(pat))
    base = _inside(project, a["path"]) if a.get("path") else project
    if base is None or not base.exists():
        return None
    g = a.get("glob")
    pats = _expand_braces(g) if isinstance(g, str) and g else []
    limit = _int(a.get("head_limit"), GREP_LIMIT) or GREP_LIMIT
    after, before = _int(a.get("-A"), 0) or 0, _int(a.get("-B"), 0) or 0
    c = _int(a.get("-C"), 0) or 0
    after, before = max(after, c), max(before, c)
    out = []
    for f in _files(project, base, pats):
        lines = _lines(f)
        if lines is None:
            continue
        rel = f.relative_to(project)
        for i, ln in enumerate(lines):
            if rx.search(ln):
                for j in range(max(0, i - before), min(len(lines), i + after + 1)):
                    out.append(f"{rel}:{j + 1}:{lines[j]}")
                if len(out) >= limit:
                    break
        if len(out) >= limit:
            break
    return f"### grep {pat} @{base.relative_to(project) if base != project else '.'}\n" + "\n".join(out[:limit])


def _list_dir(project, a):
    p = _inside(project, a.get("target_directory") or a.get("path"))
    if p is None or not p.is_dir():
        return None
    names = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
    return f"### list_dir {p.relative_to(project) if p != project else '.'}\n" + "\n".join(names)


_FN = {"read_file": _read_file, "grep": _grep, "list_dir": _list_dir}


def reread(project, calls, cap=CAP):
    """calls = [{工具, 参数, ...}]（call_grok 记的读取调用）→ (已读内容文本, 重取段数, 字数)。
    去重（工具 + 参数相同只取一次）；按调用顺序拼；单段超 SEG_CAP 截尾；总长超 cap 时去掉最早的段，只剩一段还超就保留它靠后的部分。"""
    project = Path(project).resolve()
    segs, seen = [], set()
    for c in calls or []:
        fn, a = _FN.get(c.get("工具")), c.get("参数")
        if not fn or not isinstance(a, dict):
            continue
        key = (c["工具"], json.dumps(a, sort_keys=True, ensure_ascii=False))
        if key in seen:
            continue
        seen.add(key)
        s = fn(project, a)
        if s:
            segs.append(s[:SEG_CAP])
    n = len(segs)
    while len(segs) > 1 and sum(len(s) + 2 for s in segs) - 2 > cap:
        segs.pop(0)
    text = "\n\n".join(segs)
    if len(text) > cap:
        text = text[-cap:]
    return text, n, len(text)
