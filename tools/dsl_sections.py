"""脚本末尾的多行段：「#改法 名」（多行字面量的替换 / 新建）和「#清单」。

DSL 一行一句，没有换行字面量；要改的代码原文却是多行的、带缩进的。所以原文
不写进语句，写进脚本末尾的段里，段内按字面，不转义：

    #改法 e1
    @@ 改 pkg/calc.py
    <<<<<<< 原文
    …原文（一字不差，含缩进，不带行号前缀）…
    =======
    …新文…
    >>>>>>> 新文
    @@ 新建 pkg/util.py
    <<<<<<< 内容
    …完整文件内容…
    >>>>>>> 新文

    #清单
    改 pkg/calc.py:add
    新建 pkg/util.py
    提示 先改 add 再补 util

同一个「@@ 改」下可以连写多对 <<<<<<< / ======= / >>>>>>>。段从标题行到下一个
「#改法 / #清单 / #子脚本」标题或文末。脚本里 {e1} 就是 {edits:[{file,old,new}…],
files:[{file,content}…]}（空的键不给），交给 改文件 {e1} 一次套全部条目。

split_sections 把段从脚本里拿出来，原位置换成空行（行号不变），引擎和 dslagent
的检查共用这一份解析。
"""
import json
import re

EDIT_HEAD = re.compile(r"^\s*#\s*改法\s+([^\W\d]\w*)\s*$")
LIST_HEAD = re.compile(r"^\s*#\s*清单\s*$")
SECTION_HEAD = re.compile(r"^\s*#\s*(?:(?:子脚本|改法)\s+\S+|清单\s*$)")
BLOCK_HEAD = re.compile(r"^@@\s*(改|新建)\s+(\S+)\s*$")
LIST_ITEM = re.compile(r"^\s*(?:[-*]\s*)?(改|修改|新建|删|删除)\s+[`「'\"]?([\w./\-]+\.\w+)"
                       r"(?::([A-Za-z_][\w.]*|\d+\s*[-~]\s*\d+))?")
LIST_HINT = re.compile(r"^\s*(?:[-*]\s*)?提示[:：\s]\s*(.+)$")


def is_section_head(line: str) -> bool:
    return bool(SECTION_HEAD.match(line))


def split_sections(text: str):
    """拿出「#改法 名」和「#清单」段。返回 (其余文本, {名: 改法}, 清单或 None, 问题列表)。

    其余文本里段所在的行换成空行，行号跟原文一致；「#子脚本」标题只结束前一段，
    它和后面的行留在其余文本里。同名的 #改法 段合并。问题是「第 N 行：…」的文本。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    rest, edits, probs = list(lines), {}, []
    checklist = None
    i = 0
    while i < len(lines):
        m, is_list = EDIT_HEAD.match(lines[i]), LIST_HEAD.match(lines[i])
        if not (m or is_list):
            i += 1
            continue
        start = i
        i += 1
        while i < len(lines) and not SECTION_HEAD.match(lines[i]):
            i += 1
        body = lines[start + 1:i]
        for k in range(start, i):
            rest[k] = ""
        if is_list:
            got = parse_checklist(body)
            if checklist is None:
                checklist = got
            else:
                checklist["items"] += [x for x in got["items"] if x not in checklist["items"]]
                checklist["hint"] = checklist["hint"] or got["hint"]
            continue
        name = m.group(1)
        obj, p = parse_edit_json(body) if is_json_body(body) else parse_edit_body(body, start + 2)
        probs += [f"#改法 {name}：{x}" for x in p]
        if name in edits:
            edits[name]["edits"] += obj["edits"]
            edits[name]["files"] += obj["files"]
        else:
            edits[name] = obj
    return "\n".join(rest), {k: compact(v) for k, v in edits.items()}, checklist, probs


def is_json_body(body: list) -> bool:
    """段内第一个非空、非 # 注释的行以 [ 或 { 开头 = JSON 写法（否则按 @@ 标记写法）。"""
    for line in body:
        s = line.strip()
        if s and not s.startswith("#"):
            return s[0] in "[{"
    return False


def parse_edit_json(body: list):
    """「#改法」段里直接写 JSON → ({edits, files}, 问题列表)。内容原样 json.loads（可多行；不展开 {变量}，
    {p} 之类就是字面文本），每条 {file, old, new, line?}，也接受 {"edits": […]} 或单条 {file, old, new}。
    只有 {file, content}、没有 old / new 的条目是整份内容，归入 files（写文件 {名} 拿它整份新建 / 覆盖），不进 edits。
    每条的细节（file 缺不缺、old 唯一不唯一）不在这里查，交给 改文件 / 核对计划 逐条报。"""
    text = "\n".join(x for x in body if not x.strip().startswith(("#", "```")))
    try:
        v = json.loads(text)
    except json.JSONDecodeError as e:
        return {"edits": [], "files": []}, [f"JSON 解析失败（段内第 {e.lineno} 行第 {e.colno} 列）：{e.msg}"]
    if isinstance(v, dict) and isinstance(v.get("edits"), list):
        v = v["edits"]
    elif isinstance(v, dict) and "file" in v:
        v = [v]
    if not isinstance(v, list):
        return {"edits": [], "files": []}, ["JSON 要是 [{file, old, new, line?}, …] 列表（或 {\"edits\": […]}）"]
    if not v:
        return {"edits": [], "files": []}, ["JSON 列表是空的，至少要有一条改动"]
    files = [x for x in v if is_file_item(x)]
    return {"edits": [x for x in v if not is_file_item(x)], "files": files}, []


def is_file_item(x) -> bool:
    """{file, content} 整份内容条目（没有 old / new 键）。"""
    return isinstance(x, dict) and "content" in x and "old" not in x and "new" not in x


def parse_edit_body(body: list, first_lineno: int = 1):
    """「#改法」段内的行 → ({edits, files}, 问题列表)。first_lineno 是 body[0] 在原文里的行号。

    段内只能有 @@ 标题、<<<<<<< … >>>>>>> 块、空行、# 注释和代码围栏；别的行报错——
    段一直延到下一个标题或文末，写在 #改法 段后面的语句会被吞进来，不报就静悄悄不执行了。"""
    edits, files, probs = [], [], []
    cur = None
    i = 0
    while i < len(body):
        line = body[i]
        at = first_lineno + i
        m = BLOCK_HEAD.match(line.strip())
        if m:
            if cur and not cur[2]:
                probs.append(f"第 {cur[3]} 行：@@ {cur[0]} {cur[1]} 下面没有 <<<<<<< 块")
            cur = [m.group(1), m.group(2), 0, at]
            i += 1
            continue
        if line.startswith("<<<<<<<"):
            if cur is None:
                probs.append(f"第 {at} 行：<<<<<<< 前面缺「@@ 改 文件」或「@@ 新建 文件」")
                cur = ["改", "", 0, at]
            cur[2] += 1
            a, b, mode = [], [], "a"
            i += 1
            while i < len(body) and not body[i].startswith(">>>>>>>"):
                if body[i].startswith("=======") and mode == "a" and cur[0] == "改":
                    mode = "b"
                else:
                    (a if mode == "a" else b).append(body[i])
                i += 1
            if i >= len(body):
                probs.append(f"第 {at} 行起的块：{cur[1]} 缺结尾的 >>>>>>>")
            i += 1
            if cur[0] == "新建":
                files.append({"file": cur[1], "content": "\n".join(a) + ("\n" if a else "")})
            elif mode != "b":
                probs.append(f"第 {at} 行起的块：{cur[1]} 的 <<<<<<< 和 >>>>>>> 之间缺 =======")
            elif not "\n".join(a).strip():
                probs.append(f"第 {at} 行起的块：{cur[1]} 的原文是空的（@@ 改 要写原文；新文件用 @@ 新建）")
            else:
                edits.append({"file": cur[1], "old": "\n".join(a), "new": "\n".join(b)})
            continue
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("```"):
            probs.append(f"第 {at} 行：#改法 段里认不出这一行「{s[:40]}」（段内只能写 @@ 改/新建 和 "
                         f"<<<<<<< … >>>>>>> 块；#改法 段要写在脚本末尾）")
        i += 1
    if cur and not cur[2]:
        probs.append(f"第 {cur[3]} 行：@@ {cur[0]} {cur[1]} 下面没有 <<<<<<< 块")
    return {"edits": edits, "files": files}, probs


def parse_checklist(body: list) -> dict:
    """「#清单」段 → {"items": [[改|新建|删, 路径, 位置]], "hint": 文本}。

    每行「改 路径:位置」（位置＝函数/类/模块级变量名，或行号「起-止」；可省）、「新建 路径」「删 路径」
    （可带「- 」前缀），一行「提示 …」；别的行忽略。"""
    items, hint = [], ""
    for raw in body:
        line = raw.strip().strip("`")
        m = LIST_ITEM.match(line)
        if m:
            op = {"修改": "改", "删除": "删"}.get(m.group(1), m.group(1))
            path = m.group(2).strip("'\"「」")
            loc = re.sub(r"\s+", "", m.group(3) or "").replace("~", "-") if op == "改" else ""
            if [op, path, loc] not in items:
                items.append([op, path, loc])
            continue
        h = LIST_HINT.match(line)
        if h and not hint:
            hint = h.group(1).strip()[:120]
    return {"items": items, "hint": hint}


def compact(o: dict) -> dict:
    r = {}
    if o.get("edits"):
        r["edits"] = o["edits"]
    if o.get("files"):
        r["files"] = o["files"]
    return r


def edits_text(name: str, obj: dict) -> str:
    """改法 → 段的原样写法（给重写提示、存档看）。只有 edits 没有 files（JSON 写法）时写成 JSON 列表。"""
    if (obj or {}).get("edits") and not (obj or {}).get("files") and all(isinstance(e, dict) for e in obj["edits"]):
        return f"#改法 {name}\n" + json.dumps(obj["edits"], ensure_ascii=False, indent=1)
    out = [f"#改法 {name}"]
    for f in (obj or {}).get("files") or []:
        out += [f"@@ 新建 {f.get('file')}", "<<<<<<< 内容", str(f.get("content", "")).rstrip("\n"), ">>>>>>> 新文"]
    for e in (obj or {}).get("edits") or []:
        out += [f"@@ 改 {e.get('file')}", "<<<<<<< 原文", str(e.get("old", "")), "=======", str(e.get("new", "")),
                ">>>>>>> 新文"]
    return "\n".join(out)
