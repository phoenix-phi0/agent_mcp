"""替换条目的套用规则，改文件 / 核对计划 / verify.code.apply_edits 共用一份（下划线开头，scan_verbs 不注册它）。

条目是 {file, old, new, line?}：
- old 为空 = 新建 file（目标已存在报错）；
- 同一文件多条按顺序在内存里叠加套用（后一条对着前一条改完的文本找 old）；
- old 在当前文本里恰好 1 处就用它；多处时有 line 就选「起点行离 line 最近」的那一处
  （前面条目造成的行号偏移由「最近」吸收；最近的有并列报错），没给 line 报错；0 处报错并给近似行提示；
- 任何一条出错整体不写（apply 只在内存里算，返回结果由调用方决定写不写）。
"""

from pathlib import Path

import _sandbox as SB

CAP = 8            # 报错里最多列几处行号


def read_text(p):
    """按原样读（不转换换行）：CRLF 文件写回时还是 CRLF。"""
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def finds(text, old):
    """old 在 text 里各处（不重叠）的起点偏移。"""
    out, pos = [], text.find(old)
    while pos >= 0:
        out.append(pos)
        pos = text.find(old, pos + len(old))
    return out


def locate(text, old, new):
    """(各处起点偏移, old, new)；text 是 CRLF 而 old 只用 LF、LF 对不上时换成 CRLF 再找。"""
    hits = finds(text, old)
    if not hits and "\r\n" in text and "\n" in old and "\r\n" not in old:
        crlf = old.replace("\n", "\r\n")
        k = finds(text, crlf)
        if k:
            return k, crlf, new.replace("\r\n", "\n").replace("\n", "\r\n")
    return hits, old, new


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def spots(text, hits, cap=CAP):
    """各处起点行号 + 前后各 1 行摘要，文本：「第 3 行「…」；第 9 行「…」」。"""
    lines, out = text.split("\n"), []
    for pos in hits[:cap]:
        a = line_of(text, pos) - 1
        near = " ⏎ ".join(x.strip()[:60] for x in lines[max(0, a - 1):a + 2])
        out.append(f"第 {a + 1} 行「{near}」")
    return "；".join(out) + (f"（只列前 {cap} 处）" if len(hits) > cap else "")


def hint_zero(text, old):
    """old 找不到时的近似行提示：old 第一行（去缩进）在文本里出现的行号。"""
    first = next((x.strip() for x in old.split("\n") if x.strip()), "")
    if not first:
        return ""
    near = [i for i, ln in enumerate(text.split("\n"), 1) if first in ln]
    if not near:
        return f"。old 开头「{first[:60]}」在文件里没有任何行含有"
    return f"。old 开头「{first[:60]}」出现在第 {'、'.join(map(str, near[:CAP]))} 行附近，核对其后几行是否一字不差"


def pick(text, hits, line):
    """多处时按 line 选最近的一处。返回 (偏移, 错误)。"""
    if line is None:
        return None, f"出现 {len(hits)} 次且没给 line（各处：{spots(text, hits)}）；写 line 指定起点行，或在 old 前后多带几行上下文让它唯一"
    ls = [line_of(text, p) for p in hits]
    best = min(abs(x - line) for x in ls)
    near = [p for p, x in zip(hits, ls) if abs(x - line) == best]
    if len(near) > 1:
        return None, (f"出现 {len(hits)} 次，line={line} 离起点行 "
                      f"{'、'.join(str(line_of(text, p)) for p in near)} 一样近，选不出来（各处：{spots(text, hits)}）；"
                      "换更准的 line，或多带几行上下文")
    return near[0], ""


def _line_arg(v):
    """line 取整数（>=1）；没给返回 None；给了但不合法返回 False。"""
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return False
    if isinstance(v, str) and v.strip().isdigit():
        v = int(v.strip())
    return v if isinstance(v, int) and v >= 1 else False


def apply(root, edits, path_check=None, deleted=()):
    """在内存里按顺序套 edits。返回 (texts, orig, created, errs)：
    texts {相对路径: 改后全文}、orig {相对路径: 原文，新建为 ""}、created [新建的相对路径]、errs [逐条错误文本]。
    errs 非空就不该写任何文件。path_check(rel) 返回错误文本或空（测试文件、范围拦截等调用方自己的约束）。
    deleted：计划里在这之前已 删文件 的相对路径（核对计划用），按「不存在」处理。"""
    root = Path(root).resolve()
    total = len(edits)
    texts, orig, created, touched, errs = {}, {}, [], {}, []

    def bad(k, f, why):
        errs.append(f"第 {k} 条（共 {total} 条）{f + '：' if f else '：'}{why}")

    for k, ed in enumerate(edits, 1):
        if not isinstance(ed, dict):
            bad(k, "", "每条要是 {file, old, new, line?} 对象")
            continue
        f, old, new = str(ed.get("file") or ""), ed.get("old"), ed.get("new")
        if not f:
            bad(k, "", f"缺 file 键（这条给的键：{'、'.join(map(str, ed)) or '无'}；old 开头「{str(old)[:24]}」）"
                       "——每条要写成 {file, old, new}，file 是相对路径")
            continue
        old = "" if old is None else old
        if not isinstance(old, str) or not isinstance(new, str):
            bad(k, f, "old / new 要是文本")
            continue
        line = _line_arg(ed.get("line"))
        if line is False:
            bad(k, f, f"line 要是 >=1 的整数（起点所在行，按带行号的文件），给的是 {ed.get('line')!r}")
            continue
        p, err = SB.resolve(root, f)
        if err:
            bad(k, f, err)
            continue
        rel = str(p.relative_to(root))
        why = SB.is_test_rel(rel) and f"不许{'写' if not old else '改'}测试文件" or (path_check(rel) if path_check else "")
        if why:
            bad(k, rel, why)
            continue
        if not old:
            if rel in texts:
                prev = touched.get(rel, [])
                bad(k, rel, f"已存在，old 不能为空（与第 {prev[0]} 条冲突：前面已经新建 / 改过它）" if prev
                    else "已存在，old 不能为空")
            elif p.exists() and rel not in deleted:
                bad(k, rel, "已存在，old 不能为空；新建只建不存在的文件，改已有文件要把 old 写成原文。整份重写已有文件："
                    "一条 edit，old 取整个原文；或在段里只写 {file, content}（不写 old / new），用 写文件 {段名}")
            else:
                texts[rel], orig[rel] = new, ""
                created.append(rel)
                touched.setdefault(rel, []).append(k)
            continue
        if rel not in texts:
            if rel in deleted:
                bad(k, rel, "没有这个文件（计划前面已 删文件 它；重新建要 old 写成空串）")
                continue
            if not p.is_file():
                bad(k, rel, "没有这个文件" + ("（这是新建文件时 old 写成空串）" if not p.exists() else ""))
                continue
            texts[rel] = orig[rel] = read_text(p)
        cur = texts[rel]
        hits, old, new = locate(cur, old, new)
        if not hits:
            prev = touched.get(rel, [])
            if prev and orig[rel] and locate(orig[rel], old, new)[0]:
                bad(k, rel, f"old 出现 0 次：与第 {prev[-1]} 条冲突（这处文字已被前面第 {'、'.join(map(str, prev))} 条改掉，"
                            "后一条要对着改完的文本写）")
            else:
                bad(k, rel, "old 出现 0 次，没找到（注意别带行号前缀「  12| 」、缩进要一致"
                            + ("；同一文件前面几条改过之后的文本才是这里的对照" if prev else "") + "）" + hint_zero(cur, old))
            continue
        if len(hits) == 1:
            pos = hits[0]
        else:
            pos, err = pick(cur, hits, line)
            if err:
                bad(k, rel, "old " + err)
                continue
        if old == new:
            bad(k, rel, "old 和 new 一样，没有改动")
            continue
        texts[rel] = cur[:pos] + new + cur[pos + len(old):]
        touched.setdefault(rel, []).append(k)
    return texts, orig, created, errs
