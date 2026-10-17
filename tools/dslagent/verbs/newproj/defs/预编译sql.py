"""逐条预编译 sql：在 :memory: 库按实体建表（render_sql）后 EXPLAIN，:参数 一律绑 1。
第 1 个参数：拆分隔块 的结果 {files:[{file,content}]}（或 files 列表），或项目里的目录（读其中 *.sql）；第 2 个：实体文本。
返回 {ok, msg}，msg 列出所有不过的文件和原因。没有 sql 算通过。
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def _items(x, root):
    if isinstance(x, str):
        s = x.strip()
        if s.startswith(("{", "[")):
            try:
                x = json.loads(s)
            except json.JSONDecodeError as e:
                return None, f"第 1 个参数不是 JSON：{e}"
        else:
            import _gen as G
            d, err = G.sandbox_resolve(root, s)
            if err:
                return None, err
            if not d.is_dir():
                return None, f"{s} 不是目录"
            return [{"file": str(f.relative_to(Path(root).resolve())), "content": f.read_text(encoding="utf-8")}
                    for f in sorted(d.rglob("*.sql"))], ""
    if isinstance(x, dict):
        x = x.get("files", [])
    if not isinstance(x, list) or not all(isinstance(i, dict) and "content" in i for i in x):
        return None, "要给 {files:[{file, content}]} 或目录"
    return x, ""


def 预编译sql(文件: str = "", 实体文本: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _gen as G
    if G.is_dry():
        return {"ok": "是", "msg": "（空跑）未真的预编译"}
    items, err = _items(文件, WORKSPACE)
    if err:
        return {"ok": "否", "msg": err}
    if not str(实体文本 or "").strip():
        return {"ok": "否", "msg": "没给实体文本"}
    try:
        from tools.entity import render_sql
        ddl = render_sql(实体文本)
    except Exception as e:  # noqa: BLE001
        return {"ok": "否", "msg": f"实体建表失败：{e}"}
    bad = []
    for it in items:
        name = str(it.get("file") or "?")
        body = "\n".join(l for l in str(it["content"]).splitlines() if not l.strip().startswith("--")).strip().rstrip(";").strip()
        if not body:
            bad.append(f"{name} 预编译失败: 内容为空")
            continue
        con = sqlite3.connect(":memory:")
        try:
            con.executescript(ddl)
            con.execute("EXPLAIN " + body, {m: 1 for m in re.findall(r":(\w+)", body)})
        except Exception as e:  # noqa: BLE001  sqlite 各种错
            bad.append(f"{name} 预编译失败: {e}")
        finally:
            con.close()
    return {"ok": "否" if bad else "是", "msg": "；".join(bad) if bad else f"{len(items)} 条通过"}
