"""读片段 / 钉住 共用（下划线开头，不注册成动词）：解析「文件:起-止」并读出带行号的原文。

plan3：
- 只写文件名（不带行号）= 整文件读取：≤ WHOLE_MAX 行整份返回；更长的返回前 BIG_HEAD 行
  + 「文件共 N 行，太长请指定区间」+ 该文件的 def/class 行号清单。
- 多段写法里没写文件名的段（「40-60」「:40-60」「40」）沿用前一段的文件。
- 每段字数上限放宽到 MAX_CHARS（装得下 500 行）；写了区间的段仍是每段 ≤ MAX_LINES 行。
- 每次读写一行到状态目录的 verb_log.jsonl（统计整文件读取用）。
"""

import json
import re
from pathlib import Path

from _sandbox import state_dir

MAX_LINES = 200        # 写了区间的段
WHOLE_MAX = 500        # 只写文件名：≤ 这么多行整份返回
BIG_HEAD = 120         # 只写文件名、文件更长：返回前这么多行 + 函数/类清单
MAX_CHARS = 25000
MAX_TOTAL = 800


def split_segs(arg):
    return [s.strip() for s in re.split(r"[,;，；、\n]", str(arg or "")) if s.strip()]


_RANGE_ONLY = re.compile(r"^:?\s*(\d+)(?:\s*[-~–—到至]\s*(\d+))?$")


def outline(lines):
    out = []
    for i, l in enumerate(lines, 1):
        m = re.match(r"(\s*)(?:async\s+)?(def|class)\s+(\w+)", l)
        if m:
            out.append(f"{i:5d}: {m.group(1)}{m.group(2)} {m.group(3)}")
    return out


def one(root, seg, resolve, prev_file=""):
    m0 = _RANGE_ONLY.match(seg)
    if m0:
        if not prev_file:
            return None, f"看不懂：{seg}（第一段要写文件名，写成 文件:起-止）"
        seg = f"{prev_file}:{m0.group(1)}" + (f"-{m0.group(2)}" if m0.group(2) else "")
    m = re.match(r"^(\S+?)(?::|\s+)(\d+)(?:\s*[-~–—到至]\s*|\s+)(\d+)$", seg) \
        or re.match(r"^(\S+?)(?::|\s+)(\d+)$", seg) or re.match(r"^(\S+)$", seg)
    if not m:
        return None, f"看不懂：{seg}（写成 文件:起-止，或只写文件名读整个文件）"
    f = m.group(1)
    whole = m.lastindex < 2
    a = int(m.group(2)) if not whole else 1
    b = int(m.group(3)) if m.lastindex >= 3 else 10 ** 9
    p, err = resolve(root, f)
    if err:
        return None, err
    if not p.is_file():
        return None, f"没有这个文件：{f}"
    f = str(p.relative_to(Path(root).resolve()))
    lines = p.read_text(encoding="utf-8").splitlines()
    n = len(lines)
    a = max(a, 1)
    if a > n:
        return None, f"{f} 只有 {n} 行"
    big = whole and n > WHOLE_MAX
    if whole:
        line_cap = BIG_HEAD if big else WHOLE_MAX
    else:
        line_cap = MAX_LINES
    want = min(b, n)
    out, chars, end = [], 0, a - 1
    for i in range(a, want + 1):
        row = f"{i:4d}| {lines[i - 1]}"
        if i - a + 1 > line_cap or chars + len(row) + 1 > MAX_CHARS:
            break
        out.append(row)
        chars += len(row) + 1
        end = i
    note = ""
    if big:
        ol = outline(lines)
        note = (f"\n（文件共 {n} 行，太长请指定区间（写成 {f}:起-止，每段≤{MAX_LINES} 行）。这里只给了前 {end} 行。"
                f"函数/类及所在行号：\n" + ("\n".join(ol) if ol else "（没有 def/class 行）") + "）")
    elif end < want:
        note = f"\n（第 {end} 行后省略，需要再读 {f}:{end + 1}-{want}）"
    return {"file": f, "a": a, "b": end, "body": "\n".join(out), "trunc": note,
            "total": n, "whole": whole, "big": big}, ""


def _log(root, rec):
    try:
        with open(state_dir(root) / "verb_log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_into(st, root, arg, tag="读片段"):
    """读 arg 里的各段进笔记状态，返回 (输出文本列表, 读到的键列表)。钉住 也用它。"""
    from _sandbox import resolve
    import _notes
    out, got, total = [], [], 0
    step = int(st.get("step", 0)) + 1
    prev = ""
    for s in split_segs(arg):
        if total >= MAX_TOTAL:
            out.append(f"[{tag}] 合计超过 {MAX_TOTAL} 行，后面的没读：{s}")
            continue
        snip, err = one(root, s, resolve, prev)
        if err:
            out.append(f"[{tag}] {err}")
            _log(root, {"verb": tag, "seg": s, "err": err})
            continue
        prev = snip["file"]
        _log(root, {"verb": tag, "seg": s, "file": snip["file"], "a": snip["a"], "b": snip["b"],
                    "total": snip["total"], "whole": snip["whole"], "big": snip["big"],
                    "inherit": bool(_RANGE_ONLY.match(s)), "chars": len(snip["body"])})
        if any(x["file"] == snip["file"] and x["a"] <= snip["a"] and snip["b"] <= x["b"]
               for x in st["snips"]):
            st["stats"]["reread"] += 1
        if _notes.ref_overlaps(st, snip["file"], snip["a"], snip["b"]):
            _notes.note_reread_ref(st)
        if snip["trunc"]:
            st["stats"]["trunc"] += 1
        got.append(_notes.add_snip(st, snip["file"], snip["a"], snip["b"], snip["body"], step,
                                   snip["trunc"], _notes.funcs_of(root, snip["file"], snip["a"], snip["b"])))
        total += snip["b"] - snip["a"] + 1
        head = "（整个文件）" if snip["whole"] and not snip["big"] and snip["b"] == snip["total"] else ""
        out.append(f'{snip["file"]} {snip["a"]}-{snip["b"]}（共 {snip["total"]} 行）{head}：\n'
                   f'{snip["body"]}{snip["trunc"]}')
    return out, got
