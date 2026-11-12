# -*- coding: utf-8 -*-
"""探针用的检索（纯标准库）：按函数 / 接口 / 标题切块，BM25 + 中文二元分词，增量索引。

两类来源：
- 代码：工作目录下的源码和文档（git 仓库按 git ls-files，含未跟踪但没被忽略的文件），
  按 mtime+大小增量更新，索引缓存在 ~/.cache/gsb_search/。
- 经验：gsbatch / cbatch 历次任务的「任务书 + 最终回复」，以及 probe / review / verify
  的「指令 + 结论」。让探针先查到「上次查过 / 这里踩过坑」。

只返回 path:行范围 + 几行预览，内容以 read_files 读到的最新文件为准（索引只是线索）。
疑似密钥的行在预览里打码；凭证文件和 config.json 不进索引。
"""
from __future__ import annotations

import fnmatch
import glob
import hashlib
import json
import math
import os
import re
import subprocess
import threading
import time
from collections import Counter

VERSION = 2                             # 切块 / 分词 / 标题规则变了就加一，旧缓存作废重建
CACHE_DIR = os.environ.get("GSB_SEARCH_CACHE") or os.path.expanduser("~/.cache/gsb_search")
MAX_FILE = 400_000                      # 超过的文件不进索引
MAX_CHUNK = 120                         # 块超过这么多行按窗口再切
WIN, OVERLAP = 80, 20
MIN_BLOCK = 8                           # 顶格切出来的小块并到下一块
EXTS = {".py", ".zs", ".ui", ".entity", ".wf", ".md", ".js", ".ts", ".html", ".css", ".sh",
        ".json", ".toml", ".yaml", ".yml", ".txt", ".sql", ".ini", ".cfg"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
             "runs", ".edit_backup"}
SKIP_PREFIXES = ("data/tmp/",)            # 临时脚本、日志：常常原样抄着查询词，会挤掉真代码
SKIP_NAMES = {"config.json", "package-lock.json", "auth.json", ".env", ".netrc", ".git-credentials"}
EXP_DIRS = [d for d in (os.environ.get("GSB_SEARCH_EXP_DIRS") or
                        "~/.goose-batch/jobs:~/.claude-batch/jobs:/tmp/gsb_tools").split(":") if d]

_CJK = re.compile(r"[぀-ヿ㐀-鿿豈-﫿]+")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CAMEL = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")
_SECRET = re.compile(r"(?i)((?:api_?key|secret|token|passw(?:or)?d|authorization|bearer)[\"'\s:=]+)"
                     r"([A-Za-z0-9._\-+/]{12,})")
_LONG = re.compile(r"\b[A-Za-z0-9]{32,}\.[A-Za-z0-9]{8,}\b|\bsk-[A-Za-z0-9\-_]{16,}")


def tokens(text):
    out = []
    for m in _IDENT.finditer(text):
        w = m.group(0)
        lw = w.lower()
        if len(lw) >= 2:
            out.append(lw)
        parts = [p.lower() for seg in w.split("_") for p in _CAMEL.findall(seg)]
        if len(parts) > 1:
            out.extend(p for p in parts if len(p) >= 2 and p != lw)
    for m in _CJK.finditer(text):
        s = m.group(0)
        if len(s) == 1:
            out.append(s)
            continue
        out.extend(s[i:i + 2] for i in range(len(s) - 1))
    return out


def redact(line):
    line = _SECRET.sub(lambda m: m.group(1) + "***", line)
    return _LONG.sub("***", line)


# ---------- 切块 ----------

_PY = re.compile(r"^(\s{0,4})(async\s+def|def|class)\s")
_JS = re.compile(r"^\s{0,4}(function\s|(?:var|const|let)\s+\w+\s*=\s*(?:async\s*)?(?:function|\()|"
                 r"<script|<style|class\s)")
_MD = re.compile(r"^#{1,4}\s")


def _starts(lines, ext):
    st = [0]
    if ext == ".py":
        for i, ln in enumerate(lines):
            if _PY.match(ln):
                j = i
                while j > 0 and lines[j - 1].lstrip().startswith("@"):
                    j -= 1
                st.append(j)
    elif ext in (".js", ".ts", ".html"):
        st += [i for i, ln in enumerate(lines) if _JS.match(ln)]
    elif ext == ".md":
        st += [i for i, ln in enumerate(lines) if _MD.match(ln)]
    elif ext in (".zs", ".wf", ".ui", ".entity"):
        # 顶格的非空行开新块；紧挨着的顶格注释归到下一块
        for i, ln in enumerate(lines):
            if ln and not ln[0].isspace() and (i == 0 or lines[i - 1].strip() == ""
                                                or not lines[i - 1].lstrip().startswith("#")):
                st.append(i)
    return sorted(set(st))


def chunk_lines(lines, ext):
    st = _starts(lines, ext) + [len(lines)]
    blocks = [(a, b) for a, b in zip(st, st[1:]) if b > a]
    merged = []
    for a, b in blocks:                 # 小块往后并
        if merged and merged[-1][1] - merged[-1][0] < MIN_BLOCK and b - merged[-1][0] <= 60:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    out = []
    for a, b in merged:
        if b - a <= MAX_CHUNK:
            out.append((a, b))
            continue
        i = a
        while i < b:
            out.append((i, min(b, i + WIN)))
            if i + WIN >= b:
                break
            i += WIN - OVERLAP
    return [(a, b) for a, b in out if any(lines[k].strip() for k in range(a, b))]


def _title(lines, a, b, ext=""):
    # 块里有函数 / 类 / 标题就用它（小块并过来时开头常是 import 或注释）
    pat = {".py": _PY, ".js": _JS, ".ts": _JS, ".html": _JS, ".md": _MD}.get(ext)
    if pat:
        for k in range(a, b):
            if pat.match(lines[k]):
                return lines[k].strip()[:100]
    for k in range(a, b):
        s = lines[k].strip()
        if s and not s.startswith(("#", "//", "\"\"\"", "'''")) or (s.startswith("#") and _MD.match(s)):
            return s[:100]
    return lines[a].strip()[:100]


def _doc(path, start, lines_or_text, title, kind, extra=None):
    text = lines_or_text if isinstance(lines_or_text, str) else "\n".join(lines_or_text)
    tf = Counter(tokens(text))
    for t in tokens(title + " " + path):   # 标题和路径的词加权
        tf[t] += 2
    d = {"path": path, "start": start, "title": title, "kind": kind, "tf": dict(tf),
         "len": sum(tf.values())}
    if extra:
        d.update(extra)
    return d


def index_file(rel, abspath):
    ext = os.path.splitext(rel)[1].lower()
    try:
        with open(abspath, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    if "\x00" in text[:2000]:
        return []
    lines = text.split("\n")
    out = []
    for a, b in chunk_lines(lines, ext):
        d = _doc(rel, a + 1, lines[a:b], _title(lines, a, b, ext), "code")
        d["end"] = b
        out.append(d)
    return out


# ---------- 经验 ----------

def _exp_jobs(root):
    """{job.json 路径: mtime}"""
    out = {}
    for jf in glob.glob(os.path.join(root, "*", "job.json")):
        try:
            out[jf] = os.path.getmtime(jf)
        except OSError:
            continue
    return out


def _load_job(jf):
    """每个任务一条：任务书 + 回复。"""
    try:
        with open(jf, encoding="utf-8") as f:
            j = json.load(f)
    except (OSError, ValueError):
        return []
    docs = []
    jid = os.path.basename(os.path.dirname(jf))
    src = "cbatch" if ".claude-batch" in jf else "gsbatch"
    for i, t in enumerate(j.get("tasks") or []):
        out = (t.get("output") or "").strip()
        if not out or t.get("status") not in ("done", "failed", "error"):
            continue
        prompt = (t.get("prompt") or "").strip()
        title = re.sub(r"\s+", " ", prompt)[:100]
        text = prompt[:2000] + "\n---\n" + out[:8000]
        docs.append(_doc(f"{src}:{jid}#{i + 1}", 0, text, title, "exp",
                         {"file": jf, "when": j.get("finished") or j.get("created") or "",
                          "status": t.get("status"), "text": out[:8000]}))
    return docs


def _exp_probes(root):
    out = {}
    for p in glob.glob(os.path.join(root, "*.reply.txt")):
        try:
            if os.path.getsize(p) > 0:
                out[p] = os.path.getmtime(p)
        except OSError:
            continue
    return out


def _load_probe(rp):
    base = rp[:-len(".reply.txt")]
    kind = os.path.basename(base).split("_", 1)[0]
    try:
        with open(rp, encoding="utf-8", errors="replace") as f:
            reply = f.read().strip()
        prompt = ""
        if os.path.exists(base + ".prompt.txt"):
            with open(base + ".prompt.txt", encoding="utf-8", errors="replace") as f:
                prompt = f.read()
        when = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(os.path.getmtime(rp)))
    except OSError:
        return []
    if "任务：\n" in prompt:            # 去掉探针前言
        prompt = prompt.split("任务：\n", 1)[1]
    prompt = prompt.strip()
    title = re.sub(r"\s+", " ", prompt)[:100] or os.path.basename(base)
    return [_doc(f"{kind}:{os.path.basename(base)}", 0, prompt[:2000] + "\n---\n" + reply[:8000],
                 title, "exp", {"file": rp, "when": when, "text": reply[:8000]})]


# ---------- 索引 ----------

class Index:
    def __init__(self, root):
        self.root = os.path.realpath(root)
        key = hashlib.sha1(self.root.encode()).hexdigest()[:16]
        self.cache = os.path.join(CACHE_DIR, f"code_{key}.json")
        self.files = {}                 # rel -> [mtime, size, docs]
        self.exp = {}                   # 源文件 -> [mtime, docs]
        self.lock = threading.Lock()
        self._load()

    def _load(self):
        for path, attr in ((self.cache, "files"), (os.path.join(CACHE_DIR, "exp.json"), "exp")):
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                if d.get("v") == VERSION:
                    setattr(self, attr, d["data"])
            except (OSError, ValueError, KeyError):
                pass

    def _save(self, path, data):
        try:                            # 写不了（比如验证员的只读沙箱）就只留在内存
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = f"{path}.{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"v": VERSION, "data": data}, f, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError:
            pass

    def _list(self, deny):
        try:
            r = subprocess.run(["git", "-C", self.root, "ls-files", "-z", "--cached", "--others",
                                "--exclude-standard"], capture_output=True, timeout=30)
            rels = r.stdout.decode("utf-8", "replace").split("\0") if r.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            rels = None
        if rels is None:
            rels = []
            for dp, dns, fns in os.walk(self.root):
                dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
                for fn in fns:
                    rels.append(os.path.relpath(os.path.join(dp, fn), self.root))
        out = []
        for rel in rels:
            if not rel:
                continue
            parts = rel.replace("\\", "/").split("/")
            if any(p in SKIP_DIRS for p in parts[:-1]) or parts[-1] in SKIP_NAMES:
                continue
            if "/".join(parts).startswith(SKIP_PREFIXES):
                continue
            if os.path.splitext(rel)[1].lower() not in EXTS:
                continue
            ab = os.path.join(self.root, rel)
            if deny and deny(ab):
                continue
            out.append(rel)
        return out

    def refresh_code(self, deny=None):
        changed = 0
        seen = set()
        for rel in self._list(deny):
            ab = os.path.join(self.root, rel)
            try:
                st = os.stat(ab)
            except OSError:
                continue
            if st.st_size > MAX_FILE:
                continue
            seen.add(rel)
            old = self.files.get(rel)
            if old and old[0] == st.st_mtime and old[1] == st.st_size:
                continue
            self.files[rel] = [st.st_mtime, st.st_size, index_file(rel, ab)]
            changed += 1
        gone = [r for r in self.files if r not in seen]
        for r in gone:
            del self.files[r]
        if changed or gone:
            self._save(self.cache, self.files)
        return changed + len(gone)

    def refresh_exp(self):
        changed = 0
        seen = set()
        for d in EXP_DIRS:
            d = os.path.expanduser(d)
            if not os.path.isdir(d):
                continue
            srcs = list(_exp_jobs(d).items()) + list(_exp_probes(d).items())
            for src, mt in srcs:
                seen.add(src)
                old = self.exp.get(src)
                if old and old[0] == mt:
                    continue
                self.exp[src] = [mt, _load_job(src) if src.endswith("job.json") else _load_probe(src)]
                changed += 1
        gone = [s for s in self.exp if s not in seen]
        for s in gone:
            del self.exp[s]
        if changed or gone:
            self._save(os.path.join(CACHE_DIR, "exp.json"), self.exp)
        return changed + len(gone)

    def docs(self, scope):
        if scope in ("all", "code"):
            for v in self.files.values():
                yield from v[2]
        if scope in ("all", "exp"):
            for v in self.exp.values():
                yield from v[1]


_INDEXES = {}
_ILOCK = threading.Lock()


def _index(root):
    root = os.path.realpath(root)
    with _ILOCK:
        if root not in _INDEXES:
            _INDEXES[root] = Index(root)
        return _INDEXES[root]


def _bm25(q, docs, k1=1.2, b=0.75):
    n = len(docs)
    if not n:
        return []
    avg = sum(d["len"] for d in docs) / n or 1
    df = Counter()
    for d in docs:
        tf = d["tf"]
        for t in q:
            if t in tf:
                df[t] += 1
    scored = []
    for d in docs:
        tf = d["tf"]
        s = 0.0
        hit = 0
        for t in q:
            f = tf.get(t)
            if not f:
                continue
            hit += 1
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * d["len"] / avg))
        if s > 0:
            scored.append((s * (0.5 + 0.5 * hit / len(q)), d))   # 覆盖的查询词越多越好
    scored.sort(key=lambda x: -x[0])
    return scored


def _preview(d, root, q, n):
    qs = set(q)
    if d["kind"] == "exp":
        lines = (d.get("text") or "").split("\n")
        rng = range(len(lines))
        num = False
    else:
        try:
            with open(os.path.join(root, d["path"]), encoding="utf-8", errors="replace") as f:
                lines = f.read().split("\n")
        except OSError:
            return ["（文件读不到了，可能已删除）"]
        rng = range(d["start"] - 1, min(d["end"], len(lines)))
        num = True
    best = sorted(((len(qs & set(tokens(lines[i]))), i) for i in rng if lines[i].strip()),
                  key=lambda x: (-x[0], x[1]))[:n]
    picked = sorted(i for c, i in best if c > 0) or [i for _, i in best[:2]]
    return [(f"{i + 1:>6}| " if num else "      ") + redact(lines[i].rstrip())[:200] for i in picked]


def search(query, cwd=None, scope="all", k=8, path_glob=None, preview_lines=4, deny=None):
    """返回给模型看的文本。"""
    if not query or not str(query).strip():
        raise ValueError("query 不能为空")
    if scope not in ("all", "code", "exp"):
        raise ValueError("scope 只能是 all / code / exp")
    k = max(1, min(int(k or 8), 30))
    root = os.path.realpath(cwd or os.getcwd())
    t0 = time.time()
    ix = _index(root)
    with ix.lock:
        ch = 0
        if scope in ("all", "code"):
            ch += ix.refresh_code(deny)
        if scope in ("all", "exp"):
            ch += ix.refresh_exp()
        docs = list(ix.docs(scope))
    if path_glob:
        docs = [d for d in docs if d["kind"] == "exp" or fnmatch.fnmatch(d["path"], path_glob)]
    q = list(dict.fromkeys(tokens(str(query))))
    if not q:
        raise ValueError("query 里没有可检索的词")
    res = _bm25(q, docs)[:k]
    head = (f"检索「{query}」：{len(docs)} 块里命中 {len(res)} 条（范围 {scope}，"
            f"更新 {ch} 个来源，用时 {time.time() - t0:.1f}s）。索引只是线索，内容以 read_files 读到的为准。")
    out = [head]
    for i, (s, d) in enumerate(res, 1):
        if d["kind"] == "code":
            out.append(f"[{i}] {d['path']}:{d['start']}-{d['end']}  （{s:.1f}）  {redact(d['title'])}")
        else:
            out.append(f"[{i}] 经验 {d['path']}  {d.get('when', '')}  （{s:.1f}）\n"
                       f"      任务：{redact(d['title'])}\n      全文：{d['file']}")
        out += _preview(d, root, q, preview_lines)
    if not res:
        out.append("没有命中。换个说法（同义词、英文标识符、中文动词名），或直接 rg。")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    print(search(" ".join(sys.argv[2:]), cwd=sys.argv[1]))
