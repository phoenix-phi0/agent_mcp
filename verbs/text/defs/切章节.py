"""把一大段文本按章节（课）切成块，返回 [{seq, title, text, chars}]。例如 设 chunks = 切章节 {doc.text} 6000

认哪些行是「一块的开头」，按这个顺序挑第一种出现过的：

  1. 课、章的标题行：「第3课 …」「第十二課」「第2章」「Lesson 5」「Unit 3」
     「Chapter 1」（行首，前面可以有 # 号）
  2. Markdown 标题：出现过的最浅那一级（只有一个「# 书名」时往下取「##」）

都没有就整段一块。第一个标题之前的那段（书名、前言）短于 200 字就丢掉，长的
单独成一块，标题「（开头）」。

一块超过上限（字数，默认 6000）就在段落边界（空行）再切，标题后面加
「（续2）」「（续3）」——交给模型的一块不能太长。

为什么是通用动词：上传的教材要切成一课一块交给模型抽取，这一步纯是文本处理，
跟 kg 无关；写成 .zs 的话要逐行判正则、拼列表，DSL 写不顺。
"""

import re

LESSON_RE = re.compile(
    r"^\s*#*\s*(第\s*[0-9０-９一二三四五六七八九十百零〇]+\s*[课課章节節回讲講单元]"
    r"|(lesson|unit|chapter)\s*[0-9]+)", re.I)
MD_RE = re.compile(r"^(#{1,6})\s+\S")


def _split_long(title, body, limit):
    if len(body) <= limit:
        return [(title, body)]
    parts, cur = [], ""
    for para in re.split(r"\n\s*\n", body):
        if cur and len(cur) + len(para) + 2 > limit:
            parts.append(cur)
            cur = para
        else:
            cur = (cur + "\n\n" + para) if cur else para
        # 一段本身就超长（没有空行的大段）：硬切
        while len(cur) > limit:
            parts.append(cur[:limit])
            cur = cur[limit:]
    if cur.strip():
        parts.append(cur)
    return [(title if i == 0 else f"{title}（续{i + 1}）", p) for i, p in enumerate(parts)]


def 切章节(文本: str = "", 上限: str = "6000") -> list:
    text = str(文本 or "").replace("\r\n", "\n").replace("\r", "\n")
    try:
        limit = max(int(上限 or 6000), 200)
    except ValueError:
        raise ValueError(f"切章节：上限要是数字（字数），给的是 {上限}")
    lines = text.split("\n")

    heads = [i for i, ln in enumerate(lines) if LESSON_RE.match(ln)]
    if not heads:
        levels = [len(MD_RE.match(ln).group(1)) for ln in lines if MD_RE.match(ln)]
        for lvl in sorted(set(levels)):
            # 只有一个的这一级（书名）跳过，往下一级找
            if levels.count(lvl) >= 2 or lvl == max(levels):
                heads = [i for i, ln in enumerate(lines)
                         if MD_RE.match(ln) and len(MD_RE.match(ln).group(1)) == lvl]
                break

    blocks = []
    if not heads:
        if text.strip():
            blocks.append(("（全文）", text.strip()))
    else:
        pre = "\n".join(lines[:heads[0]]).strip()
        if len(pre) >= 200:
            blocks.append(("（开头）", pre))
        for k, start in enumerate(heads):
            end = heads[k + 1] if k + 1 < len(heads) else len(lines)
            title = re.sub(r"^\s*#+\s*", "", lines[start]).strip()
            body = "\n".join(lines[start:end]).strip()
            if body:
                blocks.append((title, body))

    out = []
    for title, body in blocks:
        for t, b in _split_long(title, body, limit):
            out.append({"seq": len(out) + 1, "title": t[:200], "text": b, "chars": len(b)})
    return out
