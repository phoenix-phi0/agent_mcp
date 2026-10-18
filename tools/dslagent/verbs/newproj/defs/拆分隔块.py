"""把「=== 路径 ===」分隔的多文件文本拆成 {files:[{file, content}], n}，可直接喂 写文件。
去代码围栏；只留以前缀开头的路径；路径含 .. / 绝对路径 / 反斜杠的丢掉（记在 rejected 里）。
例如 设 blocks = 拆分隔块 {sqlTxt} queries/
返回 ok：解析到 ≥1 个文件，或回复仅为「无」标记（无 / （无）/ (无)，明确无需定制，n=0 且 none=是）才是 是；
其余 0 文件（空回复、没有分隔块的散文）ok=否，msg=「没有解析到 === 路径 === 分隔块，按格式重写」。
第 3 个参数「不覆盖」（写 是）：解析出的文件在项目里已经存在就不过（ok=否，msg 点名文件），用来防止覆盖 gen 或别的功能写好的文件。
前缀可以是完整路径（如 routes/book_stats.zs）：只收这一个文件。
没有分隔块而整个回复是 JSON edits（{edits:[{file, new/old}…]}、{file, content}、或它们的列表）时转成 files
（new 为空 old 时视为新建内容），返回里 from_json=是、note=由 JSON 转换。
"""
import json
import re
import sys
from pathlib import Path

WORKSPACE = None
PACK_DIR = None
HEAD = re.compile(r"^=== (\S+) ===[ \t]*$", re.M)
FENCE = re.compile(r"^```[^\n]*\n(.*?)\n?```[ \t]*$", re.S)
NONE_MARKS = {"无", "（无）", "(无)", "无。", "（无）。"}
MSG_EMPTY = "没有解析到 === 路径 === 分隔块，按格式重写"


def _json_items(text):
    """整个回复（可带围栏）是 JSON edits / file+content 对象或列表 → [{file, content}]；不是就返回 None。"""
    t = text.strip()
    m = FENCE.match(t)
    if m:
        t = m.group(1).strip()
    if not t or t[0] not in "[{":
        return None
    try:
        v = json.loads(t)
    except ValueError:
        return None
    if isinstance(v, dict):
        v = v["edits"] if isinstance(v.get("edits"), list) else v["files"] if isinstance(v.get("files"), list) else [v]
    if not isinstance(v, list):
        return None
    items = []
    for e in v:
        if not isinstance(e, dict) or not isinstance(e.get("file"), str):
            return None
        c = e.get("content")
        if c is None:
            c = e.get("new") if e.get("new") not in (None, "") else e.get("old")
        if isinstance(c, str) and c.strip():
            items.append({"file": e["file"], "content": c})
    return items


def 拆分隔块(文本: str = "", 前缀: str = "", 不覆盖: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _gen as G
    if G.is_dry():       # 空跑：模型回复是占位，放行让模板走完全部步骤
        return {"ok": "是", "files": [], "n": 0, "rejected": [], "msg": "（空跑）未真的拆分"}
    text = str(文本 or "").replace("\r\n", "\n")
    prefix = str(前缀 or "").strip()
    out, rejected = [], []
    if not prefix:
        return {"ok": "否", "files": [], "n": 0, "rejected": [], "msg": "没给路径前缀"}
    parts = HEAD.split(text)
    blocks = [(parts[i], parts[i + 1].strip()) for i in range(1, len(parts) - 1, 2)]
    from_json = False
    if not blocks:
        items = _json_items(text)
        if items:
            from_json = True
            blocks = [(e["file"], e["content"].strip()) for e in items]
    for name, body in blocks:
        m = FENCE.match(body)
        if m:
            body = m.group(1).strip()
        if ".." in name.split("/") or name.startswith("/") or "\\" in name or ".." in name:
            rejected.append(name)
            continue
        if not name.startswith(prefix):
            rejected.append(name)
            continue
        out.append({"file": name, "content": body + "\n"})
    res = {"files": out, "n": len(out), "rejected": rejected}
    if from_json:
        res.update(from_json="是", note="由 JSON 转换")
    if out and str(不覆盖 or "").strip() in ("是", "true", "True", "1"):
        root = Path(WORKSPACE).resolve()
        dup = [o["file"] for o in out if (root / o["file"]).exists()]
        if dup:
            return dict(res, ok="否", msg="这些文件已存在（gen 或别的功能已生成），不能覆盖：" + "、".join(dup) + "；换个文件名（sql）或只写本功能自己的文件")
    if out:
        return dict(res, ok="是")
    if text.strip() in NONE_MARKS:
        return dict(res, ok="是", none="是")
    why = f"（{len(rejected)} 个路径不在 {prefix} 下被丢掉：{'、'.join(rejected[:3])}）" if rejected else ""
    return dict(res, ok="否", msg=MSG_EMPTY + why)
