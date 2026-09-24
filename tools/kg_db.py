# -*- coding: utf-8 -*-
"""知识图谱的 SQLite 存储：节点、关系、学习者掌握状态。

    py -m tools.kg_db --init            从 kg.py 建库（会覆盖 node/edge）
    py -m tools.kg_db --status φ-0      看某人的进度
    py -m tools.kg_db --unlock φ-0      看现在可学什么
    py -m tools.kg_db --chain te-form   看某节点的全部前置和下游

直接跑也行：cd data\\tools && py kg_db.py --init

为什么用 SQLite 而不是继续存 JSON：

    节点和关系是静态的，JSON 够用；但「谁掌握了哪些节点、各答对多少题」
    是每个学习者一份、每答一题都要改的。JSON 的做法是整个读进来改完写
    回去——两个人同时练就会互相覆盖，而且要算「现在可学什么」得在 Python
    里遍历一遍图。

    SQL 里这是一句话：自己没掌握、且不存在未掌握的前置。递归查询还能直接
    算出整条依赖链，不用自己写图遍历。

三张表：

    node     节点本身。从 kg.py 的 RAW 生成，是派生数据——改节点表要改
             kg.py 然后重新 --init，不要直接改库。
    edge     关系。前置有方向（src 是前置，dst 是后继），对照无方向，
             只存一条（小 id 在前），查的时候两边都要看。
    mastery  学习者状态。这张才是真正的数据，--init 不会动它。

node 和 edge 可以随时重建，mastery 不能——所以 --init 只 DROP 前两张。
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
  名称      TEXT NOT NULL,
  层        INTEGER NOT NULL,
  类型      TEXT NOT NULL,
  考点      TEXT NOT NULL,
  正确率    INTEGER NOT NULL DEFAULT 80,
  最少题数  INTEGER NOT NULL DEFAULT 8
);

CREATE TABLE IF NOT EXISTS edge(
  src   TEXT NOT NULL REFERENCES node(id),
  dst   TEXT NOT NULL REFERENCES node(id),
  kind  TEXT NOT NULL CHECK(kind IN ('前置','对照')),
  PRIMARY KEY(src, dst, kind)
);
-- 查「某节点的前置有没有都掌握」是最高频的操作，按 dst 建索引
CREATE INDEX IF NOT EXISTS idx_edge_dst ON edge(dst, kind);
CREATE INDEX IF NOT EXISTS idx_edge_src ON edge(src, kind);

CREATE TABLE IF NOT EXISTS mastery(
  learner  TEXT NOT NULL,
  node     TEXT NOT NULL REFERENCES node(id),
  对       INTEGER NOT NULL DEFAULT 0,
  总       INTEGER NOT NULL DEFAULT 0,
  掌握     INTEGER NOT NULL DEFAULT 0,
  更新     TEXT,
  PRIMARY KEY(learner, node)
);

-- 每次作答的流水，用来事后分析「哪个考点反复错」。
-- 不参与解锁判断——那个只看 mastery 的汇总。
CREATE TABLE IF NOT EXISTS attempt(
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  learner  TEXT NOT NULL,
  node     TEXT NOT NULL REFERENCES node(id),
  题号     TEXT,
  对错     INTEGER NOT NULL,
  时间     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempt ON attempt(learner, node);
"""

# 可学 = 自己没掌握、且不存在「未掌握的前置」。
# 用两层 NOT EXISTS 而不是 JOIN + GROUP BY：前者在缺少 mastery 行时
# 也正确（没记录就是没掌握），后者要处理 NULL，容易写错。
Q_UNLOCKED = """
SELECT n.id, n.名称, n.层, n.类型, n.考点 FROM node n
WHERE NOT EXISTS(
        SELECT 1 FROM mastery m
        WHERE m.learner = :who AND m.node = n.id AND m.掌握 = 1)
  AND NOT EXISTS(
        SELECT 1 FROM edge e
        WHERE e.dst = n.id AND e.kind = '前置'
          AND NOT EXISTS(
                SELECT 1 FROM mastery m2
                WHERE m2.learner = :who AND m2.node = e.src AND m2.掌握 = 1))
ORDER BY n.层, n.id
"""

Q_ANCESTORS = """
WITH RECURSIVE anc(id) AS (
  SELECT src FROM edge WHERE dst = :node AND kind = '前置'
  UNION
  SELECT e.src FROM edge e JOIN anc ON e.dst = anc.id AND e.kind = '前置')
SELECT n.id, n.名称, n.层 FROM anc JOIN node n ON n.id = anc.id
ORDER BY n.层, n.id
"""

Q_DESCENDANTS = """
WITH RECURSIVE d(id) AS (
  SELECT dst FROM edge WHERE src = :node AND kind = '前置'
  UNION
  SELECT e.dst FROM edge e JOIN d ON e.src = d.id AND e.kind = '前置')
SELECT n.id, n.名称, n.层 FROM d JOIN node n ON n.id = d.id
ORDER BY n.层, n.id
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
    """重建 node 和 edge。mastery 与 attempt 保持不动——那是真数据。"""
    con.executescript(SCHEMA)
    con.executescript("DROP TABLE IF EXISTS edge; DROP TABLE IF EXISTS node;")
    con.executescript(SCHEMA)

    con.executemany(
        "INSERT INTO node(id,名称,层,类型,考点,正确率,最少题数) VALUES(?,?,?,?,?,?,?)",
        [(n["id"], n["名称"], n["层"], n["类型"], n["掌握判据"]["考点"],
          n["掌握判据"]["正确率"], n["掌握判据"]["最少题数"]) for n in nodes])

    edges = []
    for n in nodes:
        for p in n["前置"]:
            edges.append((p, n["id"], "前置"))
        for c in n["对照"]:
            # 对照是无方向的，只存一条，小 id 在前。存两条的话查询要去重，
            # 而且很容易出现只更新了一边的不一致。
            if n["id"] < c:
                edges.append((n["id"], c, "对照"))
    con.executemany("INSERT INTO edge(src,dst,kind) VALUES(?,?,?)", edges)
    con.commit()


def record(con: sqlite3.Connection, learner: str, node: str,
           correct: bool, 题号: str = "") -> dict:
    """记一次作答，更新汇总，返回该节点的最新状态（含是否刚刚达标）。"""
    con.execute(
        "INSERT INTO attempt(learner,node,题号,对错,时间) "
        "VALUES(?,?,?,?,datetime('now'))",
        (learner, node, 题号, int(correct)))
    con.execute(
        "INSERT INTO mastery(learner,node,对,总,更新) "
        "VALUES(:w,:n,:c,1,datetime('now')) "
        "ON CONFLICT(learner,node) DO UPDATE SET "
        "对 = 对 + :c, 总 = 总 + 1, 更新 = datetime('now')",
        {"w": learner, "n": node, "c": int(correct)})

    row = con.execute(
        "SELECT m.对, m.总, m.掌握, n.正确率, n.最少题数 "
        "FROM mastery m JOIN node n ON n.id = m.node "
        "WHERE m.learner=? AND m.node=?", (learner, node)).fetchone()

    ratio = round(row["对"] / row["总"] * 100) if row["总"] else 0
    达标 = row["总"] >= row["最少题数"] and ratio >= row["正确率"]
    刚达标 = 达标 and not row["掌握"]
    if 达标 != bool(row["掌握"]):
        con.execute("UPDATE mastery SET 掌握=? WHERE learner=? AND node=?",
                    (int(达标), learner, node))
    con.commit()
    return {"对": row["对"], "总": row["总"], "正确率": ratio,
            "掌握": 达标, "刚达标": 刚达标}


def unlocked(con: sqlite3.Connection, learner: str) -> list[sqlite3.Row]:
    return con.execute(Q_UNLOCKED, {"who": learner}).fetchall()


def mastered(con: sqlite3.Connection, learner: str) -> set[str]:
    return {r["node"] for r in con.execute(
        "SELECT node FROM mastery WHERE learner=? AND 掌握=1", (learner,))}


def status(con: sqlite3.Connection, learner: str) -> str:
    total = con.execute("SELECT count(*) c FROM node").fetchone()["c"]
    done = con.execute(
        "SELECT count(*) c FROM mastery WHERE learner=? AND 掌握=1",
        (learner,)).fetchone()["c"]
    can = unlocked(con, learner)

    lines = [f"{learner}：已掌握 {done}/{total}，现在可学 {len(can)} 个"]
    if can:
        lines.append("  " + "、".join(r["名称"] for r in can[:12])
                     + ("…" if len(can) > 12 else ""))

    # 在学但还没达标的，附上差距——比只说「没掌握」有用
    doing = con.execute(
        "SELECT n.名称, m.对, m.总, n.正确率, n.最少题数 "
        "FROM mastery m JOIN node n ON n.id=m.node "
        "WHERE m.learner=? AND m.掌握=0 AND m.总>0 ORDER BY m.更新 DESC LIMIT 8",
        (learner,)).fetchall()
    if doing:
        lines.append("在学：")
        for r in doing:
            pct = round(r["对"] / r["总"] * 100)
            gap = ("题数不够" if r["总"] < r["最少题数"]
                   else f"正确率差 {r['正确率'] - pct} 个点")
            lines.append(f"  {r['名称']}　{r['对']}/{r['总']}（{pct}%）　{gap}")
    return "\n".join(lines)


def chain(con: sqlite3.Connection, node: str) -> str:
    n = con.execute("SELECT * FROM node WHERE id=?", (node,)).fetchone()
    if not n:
        return f"没有这个节点：{node}"
    anc = con.execute(Q_ANCESTORS, {"node": node}).fetchall()
    desc = con.execute(Q_DESCENDANTS, {"node": node}).fetchall()
    con_ = con.execute(
        "SELECT n.名称 FROM edge e JOIN node n "
        "ON n.id = CASE WHEN e.src=:x THEN e.dst ELSE e.src END "
        "WHERE e.kind='对照' AND (e.src=:x OR e.dst=:x)", {"x": node}).fetchall()

    return "\n".join([
        f"{n['名称']}（{n['类型']}，层 {n['层']}，考点「{n['考点']}」）",
        f"  达标线：{n['最少题数']} 题以上且正确率 {n['正确率']}%",
        f"  前置 {len(anc)} 个：" + "、".join(r["名称"] for r in anc),
        f"  下游 {len(desc)} 个：" + "、".join(r["名称"] for r in desc[:15])
        + ("…" if len(desc) > 15 else ""),
        f"  对照：" + ("、".join(r["名称"] for r in con_) or "无"),
    ])


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
        ne = con.execute("SELECT count(*) c FROM edge").fetchone()["c"]
        nm = con.execute("SELECT count(*) c FROM mastery").fetchone()["c"]
        print(f"已建库 {path}")
        print(f"  节点 {nn}，关系 {ne}，保留的掌握记录 {nm} 条")
        return 0

    if not path.is_file():
        print(f"库还不存在，先跑：py -m tools.kg_db --init")
        return 1
    con = connect(path)

    if "--status" in args:
        i = args.index("--status")
        print(status(con, args[i + 1] if i + 1 < len(args) else "φ-0"))
        return 0

    if "--unlock" in args:
        i = args.index("--unlock")
        who = args[i + 1] if i + 1 < len(args) else "φ-0"
        for r in unlocked(con, who):
            print(f"  层{r['层']}　{r['名称']:16}　考点「{r['考点']}」")
        return 0

    if "--chain" in args:
        i = args.index("--chain")
        print(chain(con, args[i + 1] if i + 1 < len(args) else "te-form"))
        return 0

    print(__doc__.split("\n\n")[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
