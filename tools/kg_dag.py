# -*- coding: utf-8 -*-
"""把知识图谱导入库：有向无环图，加边时拒绝成环。

    from tools.kg_dag import import_file, format_report
    report = import_file("kg/app.db", "kg/queries", "kg/content/kg.jsonl")
    print(format_report(report))

也可以在 .zs 里用：`用包 kg` 之后 `导入图谱 app.db content/kg.jsonl`。

## 文件格式

JSONL，一行一个知识点，三个键：

    {"id": "katakana", "label": "片假名", "prereq": ["hiragana"]}

图就是节点和边，所以只有这三个。早先文件里还有「解锁」「层」「考点」
「掌握判据」：解锁是前置的反向，存两份迟早不一致（改成查库里的边表）；
层是人工分组，而依赖深度算得出来（kg_levels.sql）；掌握判据是教学策略，
不是语言结构；考点是出题的事，该由题目指向知识点。

对照（易混词对）在另一个文件 contrast.jsonl，一行一对：

    {"a": "i-adj", "b": "na-adj"}

它是无向的，不是图的边，也**不参与环检查**——平假名→片假名 是前置，
片假名↔平假名 是对照，两种关系并存很正常。

## 规则

**先全部节点，再全部边。** 文件里可以先引用、后定义。

**节点是 upsert。** 同一个文件导两次，名称更新成最新的，不会重复。

**边走带环检查的插入**（queries/kg_edge_add.sql）。被拒的不中断导入，逐条
报出来：行号、哪条边、原因（成环、自环、前置不存在、已存在）。成环的还
报出库里那条闭合的路径。「已存在」不算被拒——重复导入时每条边都已存在。

**整个导入是一个事务。** 中途出意外（文件坏了、库锁了）全部回滚，不会导
一半。被拒的边不算意外，照常提交。

**只增不减。** 文件里删掉一行，库里那个节点还在——要清掉得重建库。
"""

import json
import sqlite3
from pathlib import Path

# 边和对照的唯一性。.entity 表达不了多列唯一，所以导入器每次确保一下。
# 插入 SQL 里已经查过重，这是第二道：手工往库里写也挡得住。
EXTRA_SCHEMA = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_prereq_pair ON prereq(src, dst);
CREATE UNIQUE INDEX IF NOT EXISTS ux_contrast_pair ON contrast(a, b);
"""


class KgError(Exception):
    """文件读不了、格式不对。"""


def load_items(path) -> list:
    """读 JSONL，返回 [(行号, 对象), ...]。JSON 数组也认（旧格式）。"""
    p = Path(path)
    if not p.is_file():
        raise KgError(f"文件不存在：{p}")
    text = p.read_text(encoding="utf-8")

    if text.lstrip().startswith("["):
        try:
            return [(i, x) for i, x in enumerate(json.loads(text), 1)]
        except json.JSONDecodeError as e:
            raise KgError(f"{p.name} 不是合法的 JSON：{e}") from e

    items = []
    for no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            items.append((no, json.loads(line)))
        except json.JSONDecodeError as e:
            raise KgError(f"{p.name} 第 {no} 行不是合法的 JSON：{e}") from e
    return items


def _sql(qdir: Path, name: str) -> str:
    f = Path(qdir) / f"{name}.sql"
    if not f.is_file():
        raise KgError(f"缺查询文件：{f}")
    return f.read_text(encoding="utf-8")


def _changed(con, sql: str, args: dict) -> int:
    """执行一条增删改，返回影响的行数。

    不用 cursor.rowcount：Python 的 sqlite3 只在语句以 INSERT/UPDATE/DELETE
    开头时才填它，而带环检查的那条插入以 WITH 开头——rowcount 是 -1。那样
    每条边其实插进去了，却判成没插，再查原因得到「已存在」，报告全错。
    """
    before = con.total_changes
    con.execute(sql, args)
    return con.total_changes - before


def _list(v) -> list:
    """prereq：缺了当空列表；写成单个字符串也认。"""
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v.strip() else []
    return [str(x) for x in v if str(x).strip()]


def import_file(db, qdir, path, contrast_path=None) -> dict:
    """导入知识图谱。contrast_path 不给就找同目录的 contrast.jsonl。"""
    items = load_items(path)
    qdir = Path(qdir)
    sql_node = _sql(qdir, "kg_node_upsert")
    sql_edge = _sql(qdir, "kg_edge_add")
    sql_why = _sql(qdir, "kg_edge_why")
    sql_path = _sql(qdir, "kg_path")
    sql_contrast = _sql(qdir, "kg_contrast_add")

    if contrast_path is None:
        guess = Path(path).parent / "contrast.jsonl"
        contrast_path = guess if guess.is_file() else None
    pairs = load_items(contrast_path) if contrast_path else []

    report = {
        "file": str(path), "items": len(items),
        "nodes_new": 0, "nodes_updated": 0, "nodes_skipped": [],
        "edges_added": 0, "edges_existing": 0, "rejected": [],
        "contrast_added": 0, "contrast_existing": 0, "contrast_rejected": [],
    }

    con = sqlite3.connect(db)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(EXTRA_SCHEMA)
        con.execute("BEGIN")

        # ---- 第一遍：节点 ----
        good = []
        for no, obj in items:
            if not isinstance(obj, dict):
                report["nodes_skipped"].append((no, "不是对象"))
                continue
            code = str(obj.get("id") or "").strip()
            label = str(obj.get("label") or "").strip()
            if not code or not label:
                report["nodes_skipped"].append((no, "缺 id 或 label"))
                continue
            existed = con.execute("SELECT 1 FROM node WHERE code = ?",
                                  (code,)).fetchone()
            con.execute(sql_node, {"code": code, "label": label})
            report["nodes_updated" if existed else "nodes_new"] += 1
            good.append((no, obj))

        # ---- 第二遍：前置边。节点都在了，先引用后定义也没关系 ----
        for no, obj in good:
            dst = str(obj["id"]).strip()
            for src in _list(obj.get("prereq")):
                args = {"src": src, "dst": dst}
                if _changed(con, sql_edge, args) == 1:
                    report["edges_added"] += 1
                    continue
                reason = con.execute(sql_why, args).fetchone()[0]
                if reason == "已存在":
                    report["edges_existing"] += 1
                    continue
                entry = {"line": no, "src": src, "dst": dst, "reason": reason}
                if reason == "会成环":
                    row = con.execute(sql_path, {"from": dst, "to": src}).fetchone()
                    if row:
                        entry["path"] = row[0]
                report["rejected"].append(entry)

        # ---- 对照，单独的文件 ----
        for no, obj in pairs:
            a = str((obj or {}).get("a") or "").strip()
            b = str((obj or {}).get("b") or "").strip()
            if not a or not b:
                report["contrast_rejected"].append((no, a, b, "缺 a 或 b"))
                continue
            if _changed(con, sql_contrast, {"x": a, "y": b}) == 1:
                report["contrast_added"] += 1
            elif a == b:
                report["contrast_rejected"].append((no, a, b, "自己对照自己"))
            elif not con.execute("SELECT 1 FROM node WHERE code IN (?, ?)"
                                 " GROUP BY 1 HAVING count(*) = 2",
                                 (a, b)).fetchone():
                report["contrast_rejected"].append((no, a, b, "有一方不存在"))
            else:
                report["contrast_existing"] += 1

        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return report


# ----------------------------------------------------------------------
# 导出
# ----------------------------------------------------------------------


def export_items(db, qdir) -> list:
    """把库里的图读成跟导入同格式的对象列表，按学习顺序排。

    前置从边表来，所以导出的文件跟库永远一致——不像早先还要维护一个
    「解锁」字段。
    """
    qdir = Path(qdir)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        nodes = con.execute(_sql(qdir, "kg_export_nodes")).fetchall()
        edges = con.execute(_sql(qdir, "kg_export_edges")).fetchall()
    finally:
        con.close()

    pre = {}
    for e in edges:
        pre.setdefault(e["dst"], []).append(e["src"])
    return [{"id": n["code"], "label": n["label"],
             "prereq": sorted(pre.get(n["code"], []))} for n in nodes]


def export_contrasts(db, qdir) -> list:
    qdir = Path(qdir)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return [{"a": r["a"], "b": r["b"]}
                for r in con.execute(_sql(qdir, "kg_export_contrasts"))]
    finally:
        con.close()


def export_file(db, qdir, path, contrast_path=None) -> dict:
    """导出到文件。对照一并导到同目录的 contrast.jsonl（或指定的路径）。

    先写临时文件再改名：导出中途出错不会把已有的文件写坏一半——尤其导出
    的目标常常就是那份手写的 kg.jsonl。
    """
    p = Path(path)
    items = export_items(db, qdir)
    pairs = export_contrasts(db, qdir)

    def dump(target: Path, rows: list) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(target)

    dump(p, items)
    cpath = Path(contrast_path) if contrast_path else p.parent / "contrast.jsonl"
    dump(cpath, pairs)
    return {"file": str(p), "contrast_file": str(cpath), "nodes": len(items),
            "edges": sum(len(x["prereq"]) for x in items),
            "contrast_pairs": len(pairs)}


def format_export(r: dict) -> str:
    return (f"导出到 {Path(r['file']).name}：{r['nodes']} 个节点，"
            f"{r['edges']} 条前置边；"
            f"{Path(r['contrast_file']).name}：{r['contrast_pairs']} 对对照")


def format_report(r: dict) -> str:
    lines = [
        f"导入 {Path(r['file']).name}：{r['items']} 条",
        f"  节点：新增 {r['nodes_new']}，更新 {r['nodes_updated']}"
        + (f"，跳过 {len(r['nodes_skipped'])}" if r["nodes_skipped"] else ""),
        f"  前置边：新增 {r['edges_added']}，已存在 {r['edges_existing']}"
        + (f"，拒绝 {len(r['rejected'])}" if r["rejected"] else ""),
        f"  对照：新增 {r['contrast_added']}，已存在 {r['contrast_existing']}"
        + (f"，拒绝 {len(r['contrast_rejected'])}" if r["contrast_rejected"] else ""),
    ]
    for no, why in r["nodes_skipped"]:
        lines.append(f"  [跳过] 第 {no} 行：{why}")
    for e in r["rejected"]:
        tail = f"（库里已有 {e['path']}）" if e.get("path") else ""
        lines.append(f"  [拒绝] 第 {e['line']} 行：{e['src']} → {e['dst']}  "
                     f"{e['reason']}{tail}")
    for no, a, b, why in r["contrast_rejected"]:
        lines.append(f"  [拒绝] 对照第 {no} 行：{a} ↔ {b}  {why}")
    return "\n".join(lines)
