"""plan5 核对范围 / 补读范围 共用（下划线开头，不注册成动词）。

- ids_from(text)：从 note/reason/运行输出里用正则抽关键标识（商品编号、日期、带引号的字面量、≥4 位数字常量、
  带下划线的函数/变量名、点号调用名、文件名），按「在源码里的命中数少 + 类型辨识度高」排序取前 3 个。
- 命中只算测试文件以外的 .py（测试不能改，补读它没用）。
- segs 解析成 {文件: [(起, 止)]}，补读的「行号 ±25」并入后同文件区间合并，每段 ≤200 行。
- covered_range：一个区间是否被已读的段整段覆盖（合并后看，不只看两端）。
每次调用写一行到状态目录的 verb_log.jsonl（verb=核对范围/补读范围）。
"""

import json
import re
from pathlib import Path

from _sandbox import is_test_rel, py_files, state_dir

PAD = 25
SEG_MAX = 200
WHOLE_MAX = 500
BIG_HEAD = 120
TOP = 3
MAX_HITS = 4          # 一个标识在源码里命中超过这么多条就不算「有辨识度」

_RANGE_ONLY = re.compile(r"^:?\s*(\d+)(?:\s*[-~–—到至]\s*(\d+))?$")

# (类型, 正则, 优先级：越小越有辨识度)
PATTERNS = [
    ("编号", re.compile(r"\b[A-Z]{1,6}-\d{2,}[A-Z0-9]*\b"), 0),
    ("日期", re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), 0),
    ("字面量", re.compile(r"[\"'“「『]([^\"'”」』\n]{2,40})[\"'”」』]"), 1),
    ("数字", re.compile(r"(?<![\w.])\d{4,}(?![\w.])"), 1),
    ("文件", re.compile(r"\b(?:[\w.-]+/)*(\w+)\.py\b"), 3),
    ("标识符", re.compile(r"\b[A-Za-z_][A-Za-z0-9]*_[A-Za-z0-9_]+\b"), 2),
    ("调用", re.compile(r"\b([A-Za-z_]\w{2,})\s*\("), 2),
]
STOP = {"self", "print", "import", "return", "range", "len", "str", "int", "dict", "list", "sum"}


def log(root, rec):
    try:
        with open(state_dir(root) / "verb_log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def src_files(root):
    """测试文件以外的源码（测试不能改，补读它没用）。"""
    return [f for f in py_files(root) if not is_test_rel(f)]


def file_lines(root, rel):
    try:
        return (Path(root).resolve() / rel).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def find(root, needle):
    """字面量精确搜索（不当正则），只搜测试文件以外的源码。返回 [(文件, 行号)]。"""
    out = []
    for rel in src_files(root):
        for i, l in enumerate(file_lines(root, rel), 1):
            if needle in l:
                out.append((rel, i))
    return out


def parse_segs(root, segs):
    """「文件:起-止,…」→ {文件: [(起, 止)]}；只写文件名=整文件（>500 行只算前 120 行）。"""
    res, prev = {}, ""
    for s in re.split(r"[,;，；、\n]", str(segs or "")):
        s = s.strip()
        if not s:
            continue
        m0 = _RANGE_ONLY.match(s)
        if m0 and prev:
            s = f"{prev}:{m0.group(1)}" + (f"-{m0.group(2)}" if m0.group(2) else "")
        m = re.match(r"^(\S+?)(?::|\s+)(\d+)(?:\s*[-~–—到至]\s*|\s+)(\d+)$", s) \
            or re.match(r"^(\S+?)(?::|\s+)(\d+)$", s) or re.match(r"^(\S+)$", s)
        if not m:
            continue
        f = m.group(1).strip("'\"")
        n = len(file_lines(root, f))
        if not n:
            continue
        prev = f
        if m.lastindex < 2:
            a, b = 1, (n if n <= WHOLE_MAX else BIG_HEAD)
        else:
            a = int(m.group(2))
            b = int(m.group(3)) if m.lastindex >= 3 else a
            b = min(b, a + SEG_MAX - 1, n)
        res.setdefault(f, []).append((a, b))
    return res


def merge(iv):
    iv = sorted(iv)
    out = []
    for a, b in iv:
        if out and a <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def fmt_segs(root, m):
    parts = []
    for f, iv in m.items():
        n = len(file_lines(root, f))
        for a, b in merge(iv):
            if a == 1 and b >= n and n <= WHOLE_MAX:
                parts.append(f)
                continue
            while a <= b:
                e = min(b, a + SEG_MAX - 1)
                parts.append(f"{f}:{a}-{e}")
                a = e + 1
    return ",".join(parts)


def covered(m, rel, line):
    return any(a <= line <= b for a, b in m.get(rel, []))


def covered_range(m, rel, a, b):
    """[a, b] 整段都在已读的段里（几段拼起来连续覆盖也算）。只看两端会漏掉中间没读的空洞。"""
    return any(x <= a and b <= y for x, y in merge(m.get(rel, [])))


def ids_from(root, text, limit=TOP):
    """抽候选标识 → 去掉在源码里 0 命中或命中太多的 → 按 (优先级, 命中数, 出现顺序) 取前 limit 个。
    返回 [(标识, 类型, 命中列表)]。「文件」类返回的是文件名，命中列表是 [(文件, 0)]。"""
    text = str(text or "")
    seen, cands = set(), []
    files = set(src_files(root))
    for kind, rx, pri in PATTERNS:
        for m in rx.finditer(text):
            tok = (m.group(1) if m.groups() else m.group(0)).strip()
            if not tok or tok in seen or tok in STOP or len(tok) < 3:
                continue
            seen.add(tok)
            if kind == "文件":
                rel = next((f for f in sorted(files, key=len) if f == f"{tok}.py" or f.endswith(f"/{tok}.py")), "")
                if rel:
                    cands.append((tok, kind, pri, [(rel, 0)], m.start()))
                continue
            hits = find(root, tok)
            if hits and len(hits) <= MAX_HITS:
                cands.append((tok, kind, pri, hits, m.start()))
    cands.sort(key=lambda x: (x[2], len(x[3]), x[4]))
    return [(c[0], c[1], c[3]) for c in cands[:limit]]


def add_around(root, m, rel, line):
    n = len(file_lines(root, rel))
    if line <= 0:          # 整文件
        if n <= WHOLE_MAX:
            m.setdefault(rel, []).append((1, n))
            return f"{rel}"
        return ""
    a, b = max(1, line - PAD), min(n, line + PAD)
    m.setdefault(rel, []).append((a, b))
    return f"{rel}:{a}-{b}"
