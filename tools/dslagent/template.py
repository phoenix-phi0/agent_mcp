"""第 1 版计划：固定模板，不调模型规划。参数从任务描述 / 开局测试摘要（含 traceback）里按规则抽。

骨架：跑测试拿线索 → 定位.zs（kw=抽出的标识，pre=预读段落，可直接给改法）→ 找到就 读改测.zs（first=定位直接给的改法）
      → 按 outcome 分支：修好 / 缺原文（回退：按 need 再 定位 一次 → 读改测）/ 无需改 / 没修好；没找到 → 需要更多信息。

抽 kw 的规则（只留在测试文件以外的源码里命中 1–30 行的标识，按优先级取前 6 个）：
  1 traceback 里源码帧的函数名；2 测试行里被调用的函数（去掉 assert*/date/self 等）、ImportError 的 cannot import name；
  3 报错信息开头的中文字面量（如「包裹超重」）、unexpected keyword argument 的参数名；
  4 任务描述里的编号 [A-Z]+-\\d+、日期（2024-05-03 也搜 2024, 5, 3 写法）、代码标识（带下划线 / 点号 / 全大写 ≥4）；
  5 测试名拆出的词（test_eta_skips_may_holidays → eta、holidays…）。
预读 pre：traceback 帧所在的源码文件、test_X.py 对应的 X.py、ImportError 里的模块——≤300 行整份，
  更长的只读帧所在行 ±30（没有帧就不读，交给搜索）；再加失败测试所在行附近（-15～+3）。总量 ≤ 450 行。

plan6/plan7 实测 N1–N10 共 28 次，模板第 1 版修好 28/28。
"""
import re
import sys
from pathlib import Path

SKIP_CALLS = {"self", "assertEqual", "assertTrue", "assertFalse", "assertRaises", "assertIn", "assertIsNone", "assertAlmostEqual",
              "assertNotEqual", "assertIsNotNone", "date", "datetime", "len", "str", "int", "float", "list", "dict", "set",
              "tuple", "Decimal", "print", "range", "sorted", "sum", "min", "max", "isinstance", "super", "type", "repr"}
WHOLE, AROUND, CAP = 300, 30, 450
_DEFS = Path(__file__).resolve().parent / "verbs" / "code" / "defs"


def _sandbox():
    if str(_DEFS) not in sys.path:
        sys.path.insert(0, str(_DEFS))
    import _sandbox
    return _sandbox


def _src_files(repo):
    sb = _sandbox()
    return [f for f in sb.py_files(repo) if not sb.is_test_rel(f)]


def _lines(repo, rel):
    try:
        return (Path(repo) / rel).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []


def _count(repo, rx, files):
    try:
        r = re.compile(rx)
    except re.error:
        return 0
    return sum(1 for f in files for l in _lines(repo, f) if r.search(l))


def _module_file(files, mod):
    """模块名 → 源码文件（a.b.c → a/b/c.py；只给末段就按文件名找，取路径最短的）。"""
    want = mod.replace(".", "/") + ".py"
    for f in files:
        if f == want or f.endswith("/" + want):
            return f
    tail = "/" + mod.split(".")[-1] + ".py"
    hits = sorted((f for f in files if f.endswith(tail) or f == tail[1:]), key=len)
    return hits[0] if hits else ""


def extract(desc, test, repo, files=None):
    repo = Path(repo)
    sb = _sandbox()
    files = _src_files(repo) if files is None else files
    cands = []   # (优先级, 正则, 说明)
    rows = re.findall(r"^\s*([\w./-]+\.py):(\d+) (\w+|<module>): (.*)$", test, re.M)
    frames = [(f, ln, fn) for f, ln, fn, _ in rows if not sb.is_test_rel(f)]
    tlines = [(f, ln, fn, code) for f, ln, fn, code in rows if sb.is_test_rel(f)]
    for f, ln, fn in frames:
        if fn != "<module>":
            cands.append((1, re.escape(fn), f"帧函数 {fn}"))
    for _, _, _, code in tlines:
        for fn in re.findall(r"([A-Za-z_]\w*)\s*\(", code):
            if fn not in SKIP_CALLS and not fn.startswith("assert"):
                cands.append((2, re.escape(fn), f"测试调用 {fn}"))
    for nm in re.findall(r"cannot import name '(\w+)'", test):
        cands.append((2, re.escape(nm), f"导入失败 {nm}"))
    for msg in re.findall(r"^\s*\w*(?:Error|Exception): (.+)$", test, re.M):
        m = re.match(r"([一-鿿]{2,})", msg.strip())
        if m:
            cands.append((3, re.escape(m.group(1)), f"报错字面量 {m.group(1)}"))
        m2 = re.search(r"unexpected keyword argument '(\w+)'", msg)
        if m2:
            cands.append((3, re.escape(m2.group(1)), f"报错参数 {m2.group(1)}"))
    for code in re.findall(r"\b[A-Z]{1,5}-\d{2,}\b", desc):
        cands.append((4, re.escape(code), f"编号 {code}"))
    for y, mo, d in re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", desc):
        cands.append((4, f"{y}-{mo}-{d}|{y},\\s*{int(mo)},\\s*{int(d)}", f"日期 {y}-{mo}-{d}"))
    for tok in re.findall(r"[A-Za-z_][\w.]*", desc):
        for part in tok.split("."):
            if ("_" in part.strip("_") and len(part) >= 4) or (part.isupper() and len(part) >= 4):
                cands.append((4, re.escape(part), f"描述标识 {part}"))
    for tn in re.findall(r"\btest_(\w+)", desc + "\n" + test):
        for w in tn.split("_"):
            if len(w) >= 3 and w not in ("test", "the", "and", "for", "may", "with", "only"):
                cands.append((5, re.escape(w), f"测试名词 {w}"))
    seen, kept = set(), []
    for pri, rx, why in sorted(cands, key=lambda x: x[0]):
        if rx in seen:
            continue
        seen.add(rx)
        n = _count(repo, rx, files)
        if 1 <= n <= 30:
            kept.append((pri, rx, why, n))
    kept = kept[:6]
    kw = "|".join(rx for _, rx, _, _ in kept) or "def\\s"
    kw = kw.replace(" ", "\\s")

    # ---- 预读
    want = {}
    for f, ln, _ in frames:
        if (repo / f).is_file():
            want.setdefault(f, []).append(int(ln))
    mods = re.findall(r"(?:^|/)test_(\w+)\.py", test, re.M) + re.findall(r"\btests?\.test_(\w+)\.", desc)
    for mod in mods:
        f = _module_file(files, mod)
        if f:
            want.setdefault(f, [])
    for mod in re.findall(r"from '([\w.]+)'", test) + re.findall(r"from ([\w.]+) import", test):
        f = _module_file(files, mod)
        if f:
            want.setdefault(f, [])
    segs, total = [], 0
    for f, lns in want.items():
        n = len(_lines(repo, f))
        if n <= WHOLE:
            if total + n <= CAP:
                segs.append(f)
                total += n
        elif lns:
            for ln in sorted(set(lns)):
                a, b = max(1, ln - AROUND), min(n, ln + AROUND)
                if total + (b - a + 1) <= CAP:
                    segs.append(f"{f}:{a}-{b}")
                    total += b - a + 1
    tseen = {}
    for tf, ln, fn, _ in tlines:
        tseen.setdefault(tf, []).append(-1 if fn == "<module>" else int(ln))
    for tf, lns in tseen.items():
        n = len(_lines(repo, tf))
        if not n:
            continue
        if -1 in lns:      # 导入就失败（新增接口）：测试文件就是规格，≤90 行整份读
            if n <= 90 and total + n <= CAP:
                segs.append(tf)
                total += n
            continue
        a, b = max(1, min(lns) - 15), min(n, max(lns) + 3)
        if total + (b - a + 1) <= CAP:
            segs.append(f"{tf}:{a}-{b}")
            total += b - a + 1
    return {"kw": kw, "kw_why": [f"{why}（{n} 行）" for _, _, why, n in kept], "pre": ",".join(segs), "pre_lines": total}


def build(desc, test, repo):
    p = extract(desc, test, repo)
    pre = p["pre"] or "无"
    s = f"""用包 common text code
# 第 1 版：固定模板（不调模型规划）。kw 来自：{'；'.join(p['kw_why']) or '无'}；预读 {p['pre_lines']} 行
设 t0 = 跑测试
设 h = 开局失败：{{t0.summary}}
设 p = 执行 定位.zs task={{task}} kw={p['kw']} hint={{h}} pre={pre} rounds=3
打印 定位：{{p.outcome}}｜{{p.segs}}｜{{p.note}}
打印 {{p.log}}
如果 {{p.outcome}} 等于 找到
  设 r = 执行 读改测.zs task={{task}} segs={{p.segs}} hint={{p.note}} first={{p.first}} rounds=3
  打印 {{r.log}}
  如果 {{r.outcome}} 等于 修好
    打印 结论：修好 测试全部通过
  否则如果 {{r.outcome}} 等于 缺原文
    打印 缺原文：{{r.need}}
    设 h2 = 缺的位置：{{r.need}}｜上次判断：{{r.reason}}
    设 p2 = 执行 定位.zs task={{task}} kw={{p.kw}} hint={{h2}} rounds=2
    打印 {{p2.log}}
    如果 {{p2.outcome}} 等于 找到
      设 r2 = 执行 读改测.zs task={{task}} segs={{p2.segs}} hint={{p2.note}} first={{p2.first}} rounds=2
      打印 {{r2.log}}
      如果 {{r2.outcome}} 等于 修好
        打印 结论：修好 补读后修好
      否则
        打印 {{r2.last.msg}}｜{{r2.last.test}}
        打印 结论：没修好 补读后仍没修好：{{r2.outcome}}
      结束
    否则
      打印 结论：需要更多信息 缺原文且没再定位到：{{r.need}}
    结束
  否则如果 {{r.outcome}} 等于 无需改
    打印 {{r.reason}}
    打印 结论：没修好 模型认为无需改，但测试仍失败
  否则
    打印 {{r.last.msg}}｜{{r.last.test}}
    打印 结论：没修好 {{r.outcome}}
  结束
否则
  打印 结论：需要更多信息 没定位到要改的位置
结束"""
    return s, p
