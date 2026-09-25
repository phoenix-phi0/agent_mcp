# -*- coding: utf-8 -*-
"""学习记录：作答流水、掌握汇总、现在能学什么。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_learn.py

  一、答题累加：流水一条条进，汇总按人按知识点合并
  二、达标：够题数且够正确率才算掌握，「刚达标」只在跨过线那一次为真
  三、解锁：掌握了前置才能学后续；没有 mastery 行等于没掌握
  四、达标线可调：同一批作答，线严了就不算掌握
  五、**重导知识点不清空学习记录**——图可以随时从 kg.jsonl 重建，
      「谁学会了什么」不能
"""

import sqlite3
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gen.project import make_app                     # noqa: E402
from tools.entity import render_sql                  # noqa: E402
from tools.kg_dag import import_file                 # noqa: E402

KG = ROOT / "kg"
passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def main():
    ws = Path(tempfile.mkdtemp(prefix="learn_"))
    for d in ("entities", "queries", "routes", "content"):
        shutil.copytree(KG / d, ws / d)

    text = "\n\n".join(f.read_text(encoding="utf-8")
                       for f in sorted((ws / "entities").glob("*.entity")))
    con = sqlite3.connect(ws / "app.db")
    con.executescript(render_sql(text, strict=True))
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_mastery"
                " ON mastery(learner, point)")
    con.commit()
    con.close()
    import_file(ws / "app.db", ws / "queries", ws / "content" / "kg.jsonl")

    app, _ = make_app(ws, real=False)
    c = app.test_client()

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    def answer(point, correct, who="u1", **extra):
        st, body = post("/learn/answer", learner=who, point=point,
                        item="q1", correct="1" if correct else "0", **extra)
        return st, body

    def rows(sql, *args):
        con = sqlite3.connect(ws / "app.db")
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, args)]
        finally:
            con.close()

    print("一、答题累加")
    st, body = answer("hiragana", True)
    check(st == 200 and body.get("right") == "1" and body.get("total") == "1",
          f"第一题：{body}")
    for ok in (True, True, False):
        answer("hiragana", ok)
    check(rows("SELECT count(*) n FROM attempt")[0]["n"] == 4, "流水 4 条")
    m = rows("SELECT * FROM mastery WHERE learner='u1'")
    check(len(m) == 1 and m[0]["right"] == 3 and m[0]["total"] == 4,
          f"汇总合并成一行：{m}")

    print("二、达标")
    check(m[0]["mastered"] == 0, "3/4 = 75%，题数也不够 8，还没掌握")
    for _ in range(5):
        answer("hiragana", True)
    m = rows("SELECT * FROM mastery WHERE learner='u1'")[0]
    check(m["right"] == 8 and m["total"] == 9, f"累计 8/9：{m['right']}/{m['total']}")
    check(m["mastered"] == 1, "8/9 = 88%，题数够 8，掌握了")

    print("三、刚达标只报一次")
    # 上一次答题就是跨线那次，再答一题不该再报
    st, body = answer("hiragana", True)
    check(body.get("just") == "否", f"已经掌握了，just 应该是否：{body.get('just')}")

    print("四、现在能学什么")
    st, body = post("/learn/next", learner="u1")
    nxt = [r["code"] for r in (body.get("lists") or {}).get("next", [])]
    check("hiragana" not in nxt, "掌握了的不再出现在可学列表里")
    check("katakana" in nxt, f"前置掌握了，后续解锁：{nxt[:4]}")
    check("masu-form" not in nxt, "更深的还没解锁（它的前置还没掌握）")

    st, body = post("/learn/next", learner="新人")
    nxt2 = [r["code"] for r in (body.get("lists") or {}).get("next", [])]
    check(nxt2 == ["hiragana"], f"没有任何记录的人，只能从根开始：{nxt2}")

    print("五、达标线可调")
    st, body = post("/learn/status", learner="u1", rate="95", min_count="20")
    doing = (body.get("lists") or {}).get("doing", [])
    prog = (body.get("state") or {}).get("progress") or {}
    check(prog.get("done") == 1, f"按默认线已掌握 1 个：{prog}")
    check(any(r["code"] == "hiragana" for r in doing),
          f"线提到 95%/20 题后，hiragana 变成「在学」：{[r['code'] for r in doing]}")
    gap = next((r["gap"] for r in doing if r["code"] == "hiragana"), "")
    check("还差" in gap, f"差距说得具体：{gap}")

    print("六、重导知识点不清空学习记录")
    before = rows("SELECT * FROM mastery")
    import_file(ws / "app.db", ws / "queries", ws / "content" / "kg.jsonl")
    after = rows("SELECT * FROM mastery")
    check(before == after, "重导之后 mastery 一行没变")
    check(rows("SELECT count(*) n FROM attempt")[0]["n"] == 10, "流水也还在")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
