# -*- coding: utf-8 -*-
"""知识图谱（有向无环图）的测试。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_kg.py

图只有节点和边：kg.jsonl 一行一个知识点（id / label / prereq），对照在
contrast.jsonl 一行一对（a / b）。

  一、真数据：导入 128 个节点，数量对、无拒绝；再导一遍不多出行；
      图查询的结果对得上（根、分层是合法的拓扑序、可达有方向……）
  二、故意带问题的文件：自环、两点环、隔两层才闭合的环、前置不存在、
      重复的边、先引用后定义、缺 label
  三、事务：文件中途坏掉时一行都不写
  四、导出：往返不丢东西，节点和对照各写各的文件
"""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.entity import render_sql                                    # noqa: E402
from tools.kg_dag import (KgError, export_file, export_items,          # noqa: E402
                          format_export, format_report, import_file, load_items)

KG = ROOT / "kg"
QDIR = KG / "queries"
SOURCE = KG / "content" / "kg.jsonl"
CONTRAST = KG / "content" / "contrast.jsonl"

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def fresh_db(tmp: Path, name: str) -> Path:
    db = tmp / name
    text = "\n\n".join(f.read_text(encoding="utf-8")
                       for f in sorted((KG / "entities").glob("*.entity")))
    con = sqlite3.connect(db)
    con.executescript(render_sql(text))
    con.close()
    return db


def q(db, name, **params):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        sql = (QDIR / f"{name}.sql").read_text(encoding="utf-8")
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def count(db, table):
    con = sqlite3.connect(db)
    try:
        return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    finally:
        con.close()


def edges(db):
    con = sqlite3.connect(db)
    try:
        return sorted(con.execute("SELECT src, dst FROM prereq").fetchall())
    finally:
        con.close()


def main():
    tmp = Path(tempfile.mkdtemp(prefix="kgtest_"))
    src = [x for _, x in load_items(SOURCE)]
    pairs = [x for _, x in load_items(CONTRAST)]
    n_nodes = len(src)
    n_edges = sum(len(x.get("prereq", [])) for x in src)
    n_pairs = len(pairs)

    print("一、真数据")
    db = fresh_db(tmp, "real.db")
    r = import_file(db, QDIR, SOURCE)
    print("    " + format_report(r).replace("\n", "\n    "))
    check(r["nodes_new"] == n_nodes, f"新增节点 {r['nodes_new']}/{n_nodes}")
    check(r["edges_added"] == n_edges, f"新增前置边 {r['edges_added']}/{n_edges}")
    check(not r["rejected"], f"没有被拒的边（{len(r['rejected'])}）")
    check(r["contrast_added"] == n_pairs, f"对照 {r['contrast_added']} 对/{n_pairs}")
    check((count(db, "node"), count(db, "prereq"), count(db, "contrast"))
          == (n_nodes, n_edges, n_pairs), "库里的行数跟文件一致")

    print("  再导一遍")
    r2 = import_file(db, QDIR, SOURCE)
    check((r2["nodes_new"], r2["nodes_updated"]) == (0, n_nodes),
          f"节点全部是更新：新增 {r2['nodes_new']}，更新 {r2['nodes_updated']}")
    check((r2["edges_added"], r2["edges_existing"], len(r2["rejected"])) == (0, n_edges, 0),
          f"边全部已存在：新增 {r2['edges_added']}，已存在 {r2['edges_existing']}")
    check((r2["contrast_added"], r2["contrast_existing"]) == (0, n_pairs),
          f"对照也是：新增 {r2['contrast_added']}，已存在 {r2['contrast_existing']}")
    check(count(db, "prereq") == n_edges, "行数没变")

    print("  图查询")
    roots = [x["code"] for x in q(db, "kg_roots")]
    check(roots == ["hiragana"], f"根：{roots}")
    levels = {x["code"]: x["depth"] for x in q(db, "kg_levels")}
    check(len(levels) == n_nodes, f"分层覆盖全部节点：{len(levels)}")
    bad = [(s, d) for s, d in edges(db) if not levels[s] < levels[d]]
    check(not bad, f"按分层排序是合法的学习顺序（违反的边 {bad[:3]}）")
    anc = {x["code"]: x["dist"] for x in q(db, "kg_ancestors", code="noun")}
    check("hiragana" in anc and anc.get("kanji-basic") == 1,
          f"名词的前置：直接 kanji-basic，隔几层有 hiragana（共 {len(anc)} 个）")
    desc = {x["code"] for x in q(db, "kg_descendants", code="hiragana")}
    check(len(desc) == n_nodes - 1, f"平假名是一切的前置：后代 {len(desc)}/{n_nodes - 1}")
    reach = lambda a, b: q(db, "kg_reachable", **{"from": a, "to": b})[0]["reachable"]
    check(reach("hiragana", "masu-form") == 1 and reach("masu-form", "hiragana") == 0,
          "可达性有方向：平假名→ます形 是 1，反过来是 0")
    con_iadj = [x["code"] for x in q(db, "kg_contrasts", code="i-adj")]
    check(con_iadj == ["na-adj"], f"い形容词的对照：{con_iadj}（两个方向都查得到）")
    check("label" in q(db, "kg_levels")[0], "查询返回的是 label，不是 name")

    print("\n二、故意带问题的文件")
    bad_file = tmp / "bad.jsonl"
    lines = [
        {"id": "a", "label": "A"},                              # 1
        {"id": "b", "label": "B", "prereq": ["a"]},              # 2
        {"id": "c", "label": "C", "prereq": ["b", "late"]},      # 3 late 在后面才定义
        {"id": "d", "label": "D", "prereq": ["c"]},              # 4
        {"id": "late", "label": "后定义的"},                      # 5
        {"id": "x", "label": "X", "prereq": ["x"]},              # 6 自环
        {"id": "y", "label": "Y", "prereq": ["ghost"]},          # 7 前置不存在
        {"id": "b", "label": "B 改名", "prereq": ["a"]},         # 8 重复，边已存在
        {"id": "a", "label": "A", "prereq": ["c"]},              # 9 隔两层闭合的环
        {"id": "b", "label": "B", "prereq": ["c"]},              # 10 两点环
        {"id": "noname"},                                        # 11 缺 label
    ]
    bad_file.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines),
                        encoding="utf-8")
    db2 = fresh_db(tmp, "bad.db")
    r = import_file(db2, QDIR, bad_file, contrast_path=False or None)
    print("    " + format_report(r).replace("\n", "\n    "))
    got = {(e["src"], e["dst"]): e for e in r["rejected"]}
    check(got.get(("x", "x"), {}).get("reason") == "自环", "x → x 被拒：自环")
    check(got.get(("ghost", "y"), {}).get("reason") == "前置不存在", "ghost → y 被拒：前置不存在")
    e = got.get(("c", "a"), {})
    check(e.get("reason") == "会成环" and e.get("path") == "a → b → c",
          f"c → a 被拒：会成环，闭合路径 {e.get('path')}")
    check(got.get(("c", "b"), {}).get("path") == "b → c", "c → b 被拒，路径 b → c")
    check(len(r["rejected"]) == 4, f"一共拒了 4 条（{len(r['rejected'])}）")
    check(got.get(("c", "a"), {}).get("line") == 9, "报的行号对（c → a 在第 9 行）")
    check(r["edges_existing"] == 1, f"重复的 a → b 算已存在不算拒绝（{r['edges_existing']}）")
    check(edges(db2) == sorted([("a", "b"), ("b", "c"), ("late", "c"), ("c", "d")]),
          f"库里只有该有的边：{edges(db2)}")
    check(r["nodes_skipped"] == [(11, "缺 id 或 label")], f"缺 label 的跳过：{r['nodes_skipped']}")
    labels = {x["code"]: x["label"] for x in q(db2, "kg_levels")}
    check(labels.get("b") == "B", "同一个节点出现多次，以最后一次为准")
    lv = {x["code"]: x["depth"] for x in q(db2, "kg_levels")}
    check((lv.get("a"), lv.get("c"), lv.get("d")) == (0, 2, 3),
          f"分层按最长路径：a0 c2 d3 → {lv}")

    print("\n三、事务：文件中途坏掉，一行都不写")
    broken = tmp / "broken.jsonl"
    broken.write_text('{"id": "p", "label": "P"}\n{"id": "q", "label": \n',
                      encoding="utf-8")
    db3 = fresh_db(tmp, "broken.db")
    try:
        import_file(db3, QDIR, broken)
        check(False, "坏文件应该报错")
    except KgError as ex:
        check("第 2 行" in str(ex), f"报错指出行号：{ex}")
    check(count(db3, "node") == 0, "库里一个节点都没有")

    print("\n四、导出：往返不丢东西")
    out = tmp / "out" / "kg.jsonl"
    r = export_file(db, QDIR, out)
    print("    " + format_export(r))
    exported = [x for _, x in load_items(out)]
    norm = lambda rows: {x["id"]: (x["label"], tuple(sorted(x.get("prereq", []))))
                         for x in rows}
    check(norm(exported) == norm(src), "导出的跟源文件逐字段一致")
    seen, late_refs = set(), []
    for x in exported:
        late_refs += [(p, x["id"]) for p in x["prereq"] if p not in seen]
        seen.add(x["id"])
    check(not late_refs, f"导出顺序是学习顺序（违反 {late_refs[:3]}）")
    cout = out.parent / "contrast.jsonl"
    check(cout.is_file() and len([x for _, x in load_items(cout)]) == n_pairs,
          f"对照导到了单独的文件：{cout.name}")
    check(not list(out.parent.glob("*.tmp")), "没留下临时文件")

    db4 = fresh_db(tmp, "roundtrip.db")
    r4 = import_file(db4, QDIR, out)
    check(not r4["rejected"] and not r4["nodes_skipped"], "导出的文件再导入：零拒绝零跳过")
    check((count(db4, "node"), count(db4, "prereq"), count(db4, "contrast"))
          == (n_nodes, n_edges, n_pairs), "再导入的新库跟原库行数相同")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
