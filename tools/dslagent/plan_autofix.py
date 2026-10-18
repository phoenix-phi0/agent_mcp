"""计划检查不过时，由程序先自动修复三类机械错误，再决定要不要 plan_fix（v2.run 在 check 不过时调用）。

只处理主脚本和 #子脚本 的语句行；#改法 / #清单 段不碰（#期望表 / #范围 在进 check 前已切走）。由报错驱动：只修报错指到的那一行，
修一处就重新 check 一次，最多修 MAX_FIXES 处；每处修改都记 {类型, 行号, 原文, 新文}（行号是整份计划文本里的行号，从 1 起）。
三类：
  说明句行  行首不是关键字 / 动词，首词汉字开头的一句说明（「修改 …」「将 …」）→ 改成注释行 # 原文
  赋值右边  设 x = 词 其余…，词不是动词也不是 {变量} → 设 x = 词：其余…（成为文本值）；
            词是 import / from 等 Python 语句、且该变量随后作为 运行代码 的参数 → 设 x = _=0;词 其余…
  参数过多  设 r = 派任务 a b c d e：末尾是「格式」（字段:类型，或前面已定义为字段:类型 的 {变量}）时，
            前两个保持为 任务、入参，中间多出来的连成一段文本放进新增的「设 _logic<N> = 逻辑：…」，原位置换成 {_logic<N>}
            （只处理 派任务；并行派任务 的参数是 列表 并发，没有可唯一判定的写法，留给 plan_fix）
其它报错一概不动。DSLAGENT_AUTOFIX=0 关闭。
"""
import os
import re

from tools.dsl_core import KEYWORDS, VERB_LIKE_RE, normalize, split_head
from tools.dsl_sections import EDIT_HEAD, LIST_HEAD

MAX_FIXES = 40
ENV = "DSLAGENT_AUTOFIX"
PY_HEADS = ("import", "from", "def", "class", "return", "raise", "assert", "global", "del", "with", "try", "for", "while", "lambda")
SUB_HEAD = re.compile(r"^\s*#\s*子脚本\s+(\S+?)(?:\.zs)?\s*$")
SET_RE = re.compile(r"^(\s*)(设置|设|变量)\s+(\S+?)\s*[=＝]\s*(.*)$")
NO_VERB = re.compile(r"第 (\d+) 行：没有名为「(.*?)」的动词")
UNKNOWN_STMT = re.compile(r"(?:主脚本|子脚本 (\S+?))第 (\d+) 行：认不出的语句「")
TOO_MANY = re.compile(r"第 (\d+) 行：「派任务」最多接受 4 个参数")
FORMAT_PAT = r"[^\s:：{}]+[:：]\S+"
CJK = re.compile(r"[一-鿿]")


def enabled():
    return (os.environ.get(ENV) or "").strip() != "0"


def _segments(script):
    """整份计划的行下标 → 报错行号的口径（同 plan.split_subs）：返回 (主脚本行下标列表 + 段落行下标, 主脚本语句行数, {子脚本名: 行下标列表}, 段内行下标集合)。
    #改法 / #清单 起，到下一个 #子脚本 之前的行都是段内行（split_subs 把它们挪到主脚本末尾）。"""
    main, subs, secs = [], {}, []
    cur, in_sec = None, False
    for i, l in enumerate(script.splitlines()):
        m = SUB_HEAD.match(l)
        if m:
            cur, in_sec = m.group(1) + ".zs", False
            subs.setdefault(cur, [])
            continue
        if EDIT_HEAD.match(l) or LIST_HEAD.match(l):
            in_sec = True
        if in_sec:
            secs.append(i)
        elif cur:
            subs[cur].append(i)
        else:
            main.append(i)
    return main + secs, len(main), subs, set(secs)


def _locate(script, line_no, pred, sub_name=None):
    """报错行号 → 整份里的行下标：先看主脚本第 line_no 行，再看各子脚本第 line_no 行，取第一个满足 pred(原文) 的；段内行不要。"""
    lines = script.splitlines()
    mainl, nmain, subs, sec = _segments(script)
    cands = []
    if sub_name:
        s = subs.get(sub_name if sub_name.endswith(".zs") else sub_name + ".zs") or []
        if 0 < line_no <= len(s):
            cands.append(s[line_no - 1])
    else:
        if 0 < line_no <= nmain:
            cands.append(mainl[line_no - 1])
        for s in subs.values():
            if 0 < line_no <= len(s):
                cands.append(s[line_no - 1])
    for i in cands:
        if i not in sec and pred(lines[i]):
            return i
    return None


def _first_word(rhs):
    rhs = rhs.strip()
    return re.split(r"\s", rhs, maxsplit=1)[0] if rhs else ""


def _is_known_head(word, allowed):
    from .plan import ALL_VERBS
    return word in KEYWORDS or word in set(KEYWORDS.values()) or word in ALL_VERBS or word in allowed


def fix_assign(script, idx, word, allowed=()):
    """第 idx 行（0 起）是 设 x = 词 其余…：返回 (新行, 类型) 或 None。"""
    lines = script.splitlines()
    m = SET_RE.match(normalize(lines[idx]))
    if not m:
        return None
    ind, kw, name, rhs = m.groups()
    w = _first_word(rhs)
    if not w or w != word or w.startswith("{") or not VERB_LIKE_RE.match(w) or _is_known_head(w, allowed):
        return None
    rest = rhs[len(w):].strip()
    if not rest:
        return None
    if w in PY_HEADS and re.search(r"运行代码\s+\{" + re.escape(name) + r"(?:[.}\s])", "\n".join(lines)):
        return f"{ind}{kw} {name} = _=0;{w} {rest}", "赋值右边:Python代码"
    return f"{ind}{kw} {name} = {w}：{rest}", "赋值右边:文本"


def fix_prose(script, idx, word, allowed=()):
    """第 idx 行是说明句（首词汉字开头，不是关键字 / 动词 / 白名单动词，也不是 设 赋值）：改成注释行。"""
    raw = script.splitlines()[idx]
    s = normalize(raw).strip()
    if not s or s.startswith("#") or SET_RE.match(s):
        return None
    head, _ = split_head(s)
    if head != word or _is_known_head(head, allowed) or not CJK.match(head[:1]) or "=" in head:
        return None
    ind = raw[:len(raw) - len(raw.lstrip())]
    return f"{ind}# {raw.strip()}", "说明句行"


def fix_dispatch(script, idx):
    """第 idx 行是 [设 r =] 派任务 a b c d e…（>4 个参数）。返回 ([新行…], 类型) 或 None；新行里第一行是新增的 设 _logic<N>。"""
    lines = script.splitlines()
    m = re.match(r"^(\s*)((?:设置|设|变量)\s+\S+?\s*[=＝]\s*)?派任务\s+(.+?)\s*$", normalize(lines[idx]))
    if not m:
        return None
    ind, pre, argstr = m.group(1), m.group(2) or "", m.group(3)
    toks = argstr.split()
    if len(toks) <= 4:
        return None
    last = toks[-1]
    ok = bool(re.fullmatch(FORMAT_PAT, last))
    if not ok and re.fullmatch(r"\{[^{}.\s]+\}", last):       # {变量}：前面有 设 变量 = 字段:类型 才认
        decl = re.compile(r"^\s*(?:设置|设|变量)\s+" + re.escape(last[1:-1]) + r"\s*[=＝]\s*" + FORMAT_PAT + r"\s*$")
        ok = any(decl.match(normalize(l)) for l in lines[:idx])
    if not ok:
        return None
    n = 1
    while f"_logic{n}" in "\n".join(lines):
        n += 1
    new = [f"{ind}设 _logic{n} = 逻辑：{' '.join(toks[2:-1])}", f"{ind}{pre}派任务 {toks[0]} {toks[1]} {{_logic{n}}} {last}"]
    return new, "派任务参数过多"


def _apply_one(script, problem, allowed):
    """按报错修一处：返回 (新脚本, {类型, 行号, 原文, 新文}) 或 None。"""
    lines = script.splitlines()
    tail = "\n" if script.endswith("\n") else ""
    m = NO_VERB.search(problem)
    if m:
        n, word = int(m.group(1)), m.group(2)
        idx = _locate(script, n, lambda l: not normalize(l).strip().startswith("#") and word in normalize(l))
        got = idx is not None and (fix_assign(script, idx, word, allowed) or fix_prose(script, idx, word, allowed))
        new = [got[0]] if got else None
    elif UNKNOWN_STMT.search(problem):
        m = UNKNOWN_STMT.search(problem)
        idx = _locate(script, int(m.group(2)), lambda l: bool(normalize(l).strip()) and not normalize(l).strip().startswith("#"), m.group(1))
        got = idx is not None and fix_prose(script, idx, split_head(normalize(lines[idx]).strip())[0], allowed)
        new = [got[0]] if got else None
    elif TOO_MANY.search(problem):
        idx = _locate(script, int(TOO_MANY.search(problem).group(1)), lambda l: "派任务" in l and "并行派任务" not in l)
        got = idx is not None and fix_dispatch(script, idx)
        new = got[0] if got else None
    else:
        return None
    if not got:
        return None
    old = lines[idx]
    lines[idx:idx + 1] = new
    return "\n".join(lines) + tail, {"类型": got[1], "行号": idx + 1, "原文": old, "新文": "\n".join(new)}


def autofix(script, problem, recheck, allowed=()):
    """problem：recheck 对 script 给出的问题文本。recheck(script) → (问题文本, main, subs, 记录)，每修一处调一次。
    返回 (新计划, 修改记录列表, 最终问题文本, main, subs, 最后一次 recheck 的记录)；一处也没修时后三项是 (原问题, None, None, None)。"""
    fixes, main, subs, crec = [], None, None, None
    seen = set()
    for _ in range(MAX_FIXES):
        got = _apply_one(script, problem, allowed)
        if not got or got[0] == script:
            break
        key = (got[1]["类型"], got[1]["行号"], got[1]["新文"])
        if key in seen:
            break
        seen.add(key)
        script = got[0]
        fixes.append(got[1])
        problem, main, subs, crec = recheck(script)
        if not problem:
            break
    return script, fixes, problem, main, subs, crec
