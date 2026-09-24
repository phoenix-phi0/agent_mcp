# -*- coding: utf-8 -*-
"""知识图谱存储：SQLite + 邻接表。

    py -m tools.kg_store --init         从 kg.py 建库
    py -m tools.kg_store --status φ-0
    py -m tools.kg_store --unlock φ-0
    py -m tools.kg_store --node te-form

直接跑也行：cd data\\tools && py kg_store.py --init

## 为什么是邻接表而不是边表

关系存在节点行里（prereq 和 contrast 两个 JSON 数组），不单开一张 edge 表。

边表的优势在三处：边本身要带属性、反向查询频繁、关系类型很多。这三条在
当前规模下都不成立——69 个节点全表扫几微秒，关系只有两种，边上没有属性。
而邻接表跟 kg.py 的数据结构一模一样，存取不用转换。

真要换边表的信号：边开始需要属性（「这条依赖有多强」），或者关系类型涨到
五六种。那时候邻接表就得在节点上挂一堆 JSON 列。

SQLite 的 json_each() 让邻接表也能写出正经的查询，包括递归——不是只能
全读进内存自己遍历。

## 字段划分

图本身的字段和领域的字段分开：

    id / name / kind / layer / prereq / contrast     图本身
    meta                                            领域配置，JSON

meta 里现在装的是日语教学的掌握判据（考点、正确率、最少题数）。换个领域
只改 meta 的内容，schema 不动。

unlocks（下游）不存——它是 prereq 的反向，存了就有两份真相，容易只更新
一边。要用的时候反查：WHERE json_each(prereq).value = ?

layer 存下来而不是算出来：拓扑深度和教学阶段不是一回事。「は と が」在
拓扑上很浅，教学上却属于第四阶段。

## 两类数据

    node      派生数据，从 kg.py 生成，--init 会重建
    mastery   真数据，每个学习者的作答汇总，--init 不碰
    attempt   作答流水，用来事后分析，同样不碰

mastered 那一列是从 correct/total 算出来的冗余，存下来是为了「查可学节点」
的 SQL 不必每次重算比例。代价是达标线改了要跑一次 recheck()。
"""

import json
import sqlite3
import sys
from pathlib import Path

try:
    from .kg import build, check, out_dir
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from kg import build, check, out_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS node(
  id        TEXT PRIMARY KEY,
  name      TEXT NOT NULL,
  kind      TEXT NOT NULL,
  layer     INTEGER NOT NULL,
  prereq    TEXT NOT NULL DEFAULT '[]',   -- JSON 数组，前置节点 id
  contrast  TEXT NOT NULL DEFAULT '[]',   -- JSON 数组，对照节点 id（双向）
  meta      TEXT NOT NULL DEFAULT '{}',   -- 领域配置，换领域只改这里
  enabled   INTEGER NOT NULL DEFAULT 1    -- 暂时停用某节点而不删
);
CREATE INDEX IF NOT EXISTS idx_node_layer ON node(layer);

CREATE TABLE IF NOT EXISTS mastery(
  learner   TEXT NOT NULL,
  node      TEXT NOT NULL REFERENCES node(id),
  correct   INTEGER NOT NULL DEFAULT 0,
  total     INTEGER NOT NULL DEFAULT 0,
  mastered  INTEGER NOT NULL DEFAULT 0,   -- 冗余，省得查询时重算比例
  updated   TEXT,
  PRIMARY KEY(learner, node)
);

CREATE TABLE IF NOT EXISTS attempt(
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  learner   TEXT NOT NULL,
  node      TEXT NOT NULL REFERENCES node(id),
  ref       TEXT,                          -- 题号之类的外部引用
  correct   INTEGER NOT NULL,
  at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempt ON attempt(learner, node);
"""

# 可学 = 启用 且 自己没掌握 且 不存在「未掌握的前置」。
#
# 两层 NOT EXISTS 而不是 JOIN + GROUP BY：前者在缺少 mastery 行时天然
# 正确（没记录就是没掌握），后者要处理 NULL，容易写错。
# json_each 把 prereq 数组展开成行，于是数组也能参与关系查询。
Q_UNLOCKED = """
SELECT n.* FROM node n
WHERE n.enabled = 1
  AND NOT EXISTS(
        SELECT 1 FROM mastery m
        WHERE m.learner = :who AND m.node = n.id AND m.mastered = 1)
  AND NOT EXISTS(
        SELECT 1 FROM json_each(n.prereq) j
        WHERE NOT EXISTS(
              SELECT 1 FROM mastery m2
              WHERE m2.learner = :who AND m2.node = j.value AND m2.mastered = 1))
ORDER BY n.layer, n.id
"""

# 直接下游：谁把我列为前置
Q_CHILDREN = """
SELECT n.* FROM node n, json_each(n.prereq) j
WHERE j.value = :node ORDER BY n.layer, n.id
"""

# 全部下游，递归。锚点是直接下游，然后顺着 prereq 一路展开
Q_DESCENDANTS = """
WITH RECURSIVE d(id) AS (
  SELECT n.id FROM node n, json_each(n.prereq) j WHERE j.value = :node
  UNION
  SELECT n.id FROM node n, json_each(n.prereq) j JOIN d ON j.value = d.id)
SELECT n.* FROM d JOIN node n ON n.id = d.id ORDER BY n.layer, n.id
"""

# 全部前置，递归
Q_ANCESTORS = """
WITH RECURSIVE a(id) AS (
  SELECT j.value FROM node n, json_each(n.prereq) j WHERE n.id = :node
  UNION
  SELECT j.value FROM node n, json_each(n.prereq) j JOIN a ON n.id = a.id)
SELECT n.* FROM a JOIN node n ON n.id = a.id ORDER BY n.layer, n.id
"""


def db_path() -> Path:
    return out_dir() / "kg.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init(con: sqlite3.Connection, nodes: list[dict]) -> None:
    """重建 node。mastery 和 attempt 保持不动——那是真数据。"""
    con.executescript(SCHEMA)
    con.execute("DROP TABLE IF EXISTS node")
    con.executescript(SCHEMA)
    con.executemany(
        "INSERT INTO node(id,name,kind,layer,prereq,contrast,meta) "
        "VALUES(?,?,?,?,?,?,?)",
        [(n["id"], n["名称"], n["类型"], n["层"],
          json.dumps(n["前置"], ensure_ascii=False),
          json.dumps(n["对照"], ensure_ascii=False),
          json.dumps(n["掌握判据"], ensure_ascii=False)) for n in nodes])
    con.commit()


def criteria(row: sqlite3.Row) -> dict:
    try:
        return json.loads(row["meta"])
    except (json.JSONDecodeError, TypeError):
        return {}


def record(con: sqlite3.Connection, learner: str, node: str,
           correct: bool, ref: str = "") -> dict:
    """记一次作答，更新汇总。返回最新状态，含「是否刚刚达标」。

    刚达标这个标志是给界面用的——可以据此弹一句「解锁了 XX」。
    """
    con.execute(
        "INSERT INTO attempt(learner,node,ref,correct,at) "
        "VALUES(?,?,?,?,datetime('now'))", (learner, node, ref, int(correct)))
    con.execute(
        "INSERT INTO mastery(learner,node,correct,total,updated) "
        "VALUES(:w,:n,:c,1,datetime('now')) "
        "ON CONFLICT(learner,node) DO UPDATE SET "
        "correct = correct + :c, total = total + 1, updated = datetime('now')",
        {"w": learner, "n": node, "c": int(correct)})

    row = con.execute(
        "SELECT m.correct, m.total, m.mastered, n.meta FROM mastery m "
        "JOIN node n ON n.id = m.node WHERE m.learner=? AND m.node=?",
        (learner, node)).fetchone()

    rule = criteria(row)
    need_n = rule.get("最少题数", 8)
    need_p = rule.get("正确率", 80)
    ratio = round(row["correct"] / row["total"] * 100) if row["total"] else 0
    ok = row["total"] >= need_n and ratio >= need_p

    if ok != bool(row["mastered"]):
        con.execute("UPDATE mastery SET mastered=? WHERE learner=? AND node=?",
                    (int(ok), learner, node))
    con.commit()
    return {"correct": row["correct"], "total": row["total"], "ratio": ratio,
            "mastered": ok, "just_unlocked": ok and not row["mastered"]}


def recheck(con: sqlite3.Connection, learner: str | None = None) -> int:
    """按当前达标线重算 mastered。改了 meta 里的阈值之后要跑一次。"""
    sql = ("SELECT m.learner, m.node, m.correct, m.total, m.mastered, n.meta "
           "FROM mastery m JOIN node n ON n.id = m.node")
    rows = (con.execute(sql + " WHERE m.learner=?", (learner,)).fetchall()
            if learner else con.execute(sql).fetchall())
    changed = 0
    for r in rows:
        rule = criteria(r)
        ratio = round(r["correct"] / r["total"] * 100) if r["total"] else 0
        ok = (r["total"] >= rule.get("最少题数", 8)
              and ratio >= rule.get("正确率", 80))
        if ok != bool(r["mastered"]):
            con.execute("UPDATE mastery SET mastered=? WHERE learner=? AND node=?",
                        (int(ok), r["learner"], r["node"]))
            changed += 1
    con.commit()
    return changed


def unlocked(con: sqlite3.Connection, learner: str) -> list[sqlite3.Row]:
    return con.execute(Q_UNLOCKED, {"who": learner}).fetchall()


def mastered_set(con: sqlite3.Connection, learner: str) -> set[str]:
    return {r["node"] for r in con.execute(
        "SELECT node FROM mastery WHERE learner=? AND mastered=1", (learner,))}


def node_detail(con: sqlite3.Connection, nid: str) -> str:
    n = con.execute("SELECT * FROM node WHERE id=?", (nid,)).fetchone()
    if not n:
        return f"没有这个节点：{nid}"
    anc = con.execute(Q_ANCESTORS, {"node": nid}).fetchall()
    desc = con.execute(Q_DESCENDANTS, {"node": nid}).fetchall()
    kids = con.execute(Q_CHILDREN, {"node": nid}).fetchall()
    rule = criteria(n)
    names = lambda rows, cap=None: "、".join(
        r["name"] for r in (rows[:cap] if cap else rows)) or "无"

    return "\n".join([
        f"{n['name']}（{n['kind']}，层 {n['layer']}）",
        f"  掌握判据：{json.dumps(rule, ensure_ascii=False)}",
        f"  直接前置：{names([{'name': x} for x in json.loads(n['prereq'])]) if False else '、'.join(json.loads(n['prereq'])) or '无'}",
        f"  全部前置 {len(anc)} 个：{names(anc)}",
        f"  直接下游 {len(kids)} 个：{names(kids)}",
        f"  全部下游 {len(desc)} 个：{names(desc, 15)}"
        + ("…" if len(desc) > 15 else ""),
        f"  对照：{'、'.join(json.loads(n['contrast'])) or '无'}",
    ])


def status(con: sqlite3.Connection, learner: str) -> str:
    total = con.execute("SELECT count(*) c FROM node WHERE enabled=1").fetchone()["c"]
    done = con.execute(
        "SELECT count(*) c FROM mastery WHERE learner=? AND mastered=1",
        (learner,)).fetchone()["c"]
    can = unlocked(con, learner)

    lines = [f"{learner}：已掌握 {done}/{total}，现在可学 {len(can)} 个"]
    if can:
        lines.append("  " + "、".join(r["name"] for r in can[:12])
                     + ("…" if len(can) > 12 else ""))

    doing = con.execute(
        "SELECT n.name, m.correct, m.total, n.meta FROM mastery m "
        "JOIN node n ON n.id = m.node "
        "WHERE m.learner=? AND m.mastered=0 AND m.total>0 "
        "ORDER BY m.updated DESC LIMIT 8", (learner,)).fetchall()
    if doing:
        lines.append("在学：")
        for r in doing:
            rule = criteria(r)
            pct = round(r["correct"] / r["total"] * 100)
            gap = ("题数不够" if r["total"] < rule.get("最少题数", 8)
                   else f"正确率差 {rule.get('正确率', 80) - pct} 个点")
            lines.append(f"  {r['name']}　{r['correct']}/{r['total']}（{pct}%）　{gap}")
    return "\n".join(lines)


def main() -> int:
    args = sys.argv[1:]
    path = db_path()

    if "--init" in args:
        nodes = build()
        errs = check(nodes)
        if errs:
            print(f"节点表有 {len(errs)} 个问题，先修好：")
            for e in errs[:10]:
                print("  ", e)
            return 1
        con = connect(path)
        init(con, nodes)
        nn = con.execute("SELECT count(*) c FROM node").fetchone()["c"]
        nm = con.execute("SELECT count(*) c FROM mastery").fetchone()["c"]
        moved = recheck(con)
        print(f"已建库 {path}")
        print(f"  节点 {nn}，保留的掌握记录 {nm} 条"
              + (f"，按新达标线调整了 {moved} 条" if moved else ""))
        return 0

    if not path.is_file():
        print("库还不存在，先跑：py -m tools.kg_store --init")
        return 1
    con = connect(path)

    def arg_after(flag, default):
        i = args.index(flag)
        return args[i + 1] if i + 1 < len(args) else default

    if "--status" in args:
        print(status(con, arg_after("--status", "φ-0")))
    elif "--unlock" in args:
        for r in unlocked(con, arg_after("--unlock", "φ-0")):
            rule = criteria(r)
            print(f"  层{r['layer']}　{r['name']:16}　"
                  f"考点「{rule.get('考点', '')}」")
    elif "--node" in args:
        print(node_detail(con, arg_after("--node", "te-form")))
    elif "--recheck" in args:
        print(f"调整了 {recheck(con)} 条掌握记录")
    else:
        print(__doc__.split("\n\n")[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
