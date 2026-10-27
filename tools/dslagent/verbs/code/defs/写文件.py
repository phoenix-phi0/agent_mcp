"""新建或整份覆盖非测试文件（任何类型：.py / .json / .md …）。改文件 只能对已有文件做精确替换、不能新建，
「拆配置到新 JSON」「生成报告文件」这类任务用它。
收 {file, content} 或 {files:[{file, content}, …]}（脚本里传 问JSON 的结果 {r}）。返回 {ok: 是/否, msg, n}。
路径在项目根下（不许越界、不许写测试文件），父目录不存在就建；写之前逐个过安全约束（reason.check），任何一处不合法或被拦整体不写。
覆盖已有文件按原文件的换行写回（原文件 CRLF 就把内容换成 CRLF）；新文件照内容原样（LF）。
#改法 段里只写 {file, content} 的条目解析成 {files:[…]}，直接 写文件 {e2}；「设 w.files = {e2}」再 写文件 {w} 也认。
例如 设 res = 写文件 {r}
"""

import json
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
MAX_CHARS = 200000


def 写文件(内容: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    from _sandbox import is_test_path, resolve
    try:
        e = 内容 if isinstance(内容, dict) else json.loads(内容)
    except (TypeError, json.JSONDecodeError) as ex:
        return {"ok": "否", "msg": f"参数不是 JSON 对象：{ex}", "n": 0}
    if isinstance(e, dict) and isinstance(e.get("files"), dict) and isinstance(e["files"].get("files"), list):
        e = e["files"]          # 设 w.files = {e2}：e2 本身是 {files:[…]}
    if isinstance(e, dict) and isinstance(e.get("edits"), list) and not e.get("files"):
        return {"ok": "否", "n": 0, "msg": "写文件 只收 {file, content}；这份改法是 old / new 条目（改局部用 改文件，"
                                           "整份重写在 #改法 段里只写 {file, content}）"}
    items = e.get("files") if isinstance(e, dict) and isinstance(e.get("files"), list) else [e]
    root = Path(WORKSPACE).resolve()
    plan = []
    for k, it in enumerate(items, 1):
        if not isinstance(it, dict):
            return {"ok": "否", "msg": f"第 {k} 项要是 {{file, content}} 对象", "n": 0}
        f = str(it.get("file") or it.get("path") or "")
        c = it.get("content")
        if not isinstance(c, str):
            c = json.dumps(c, ensure_ascii=False, indent=2) + "\n" if c is not None else None
        if not f or c is None:
            return {"ok": "否", "msg": f"第 {k} 项缺 file 或 content（给的键：{'、'.join(map(str, it))}）", "n": 0}
        if len(c) > MAX_CHARS:
            return {"ok": "否", "msg": f"{f}：内容超过 {MAX_CHARS} 字", "n": 0}
        p, err = resolve(root, f)
        if err:
            return {"ok": "否", "msg": err, "n": 0}
        if p.exists() and not p.is_file():
            return {"ok": "否", "msg": f"{f} 是目录", "n": 0}
        if is_test_path(root, p):
            return {"ok": "否", "msg": f"不许写测试文件：{f}", "n": 0}
        if p.is_file() and b"\r\n" in p.read_bytes():
            c = c.replace("\r\n", "\n").replace("\n", "\r\n")
        plan.append((p, c))
    import 推理 as T
    for p, c in plan:
        why = T._R().check("写入", root, str(p.relative_to(root)), c)
        if why:
            return {"ok": "否", "msg": why + "（整体没写）", "n": 0, "blocked": "是"}
    msgs = []
    for p, c in plan:
        existed = p.exists()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(c)
        msgs.append(f"{p.relative_to(root)}（{'覆盖' if existed else '新建'}，{len(c.splitlines())} 行）")
    return {"ok": "是", "n": len(plan), "msg": "已写 " + "、".join(msgs)}
