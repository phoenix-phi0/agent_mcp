# -*- coding: utf-8 -*-
"""学习记录：作答流水、掌握汇总、现在能学什么。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_learn.py

  一、答题累加：流水一条条进，汇总按人按知识点合并
  二、达标看掌握得分（≥ 80），不看累计正确率；「刚达标」只在跨过线那一次为真
  三、解锁：掌握了前置才能学后续；没有 mastery 行等于没掌握
  四、达标线可调：同一批作答，线严了就不算掌握
  四之二、早错后对也能掌握（累计正确率够不着线）；掌握后有回落线，
      错一两道不收回，一直错才收回
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

from tests.kg.helpers import client, import_graph, make_ws   # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def main():
    ws = make_ws(Path(tempfile.mkdtemp(prefix="learn_")))
    import_graph(ws)
    c = client(ws)

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

    print("二、达标（看掌握得分）")
    check(m[0]["mastered"] == 0 and int(body.get("score") or 0) < 80,
          f"3/4，得分不到 80，还没掌握：{body}")
    # 接着全对，直到得分过 80。记下每次的 just
    trail = []
    for _ in range(20):
        st, body = answer("hiragana", True)
        trail.append((body.get("score"), body.get("mastered"), body.get("just")))
        if body.get("mastered") == "1":
            break
    check(body.get("mastered") == "1" and int(body["score"]) >= 80,
          f"得分过 80 就掌握了：{trail[-3:]}")
    check([t[2] for t in trail].count("是") == 1 and trail[-1][2] == "是",
          f"「刚达标」只在跨线那一次为真：{trail}")
    m = rows("SELECT * FROM mastery WHERE learner='u1'")[0]
    check(m["mastered"] == 1, "库里的标记也写上了")

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
    # 基础题全对的得分封顶在 84 上下（score_calc.sql），线提到 95 一定够不着；
    # 回落线也提到 95，不然「掌握过、得分 ≥ keep」会让它继续算掌握
    st, body = post("/learn/status", learner="u1", line="95", keep="95")
    doing = (body.get("lists") or {}).get("doing", [])
    prog = (body.get("state") or {}).get("progress") or {}
    check(prog.get("done") == 1, f"按默认线已掌握 1 个：{prog}")
    check(any(r["code"] == "hiragana" for r in doing),
          f"线提到 95 后，hiragana 变成「在学」：{[r['code'] for r in doing]}")
    gap = next((r["gap"] for r in doing if r["code"] == "hiragana"), "")
    check("得分" in gap and "差" in gap, f"差距说得具体：{gap}")
    st, body = post("/learn/status", learner="u1")
    doing = (body.get("lists") or {}).get("doing", [])
    check(not any(r["code"] == "hiragana" for r in doing), "默认线下它不在「在学」里")

    print("五之二、早错后对；回落线")
    for _ in range(10):
        answer("katakana", False, who="u2")
    st, body = None, {}
    for _ in range(20):
        st, body = answer("katakana", True, who="u2")
    mm = rows("SELECT * FROM mastery WHERE learner='u2'")[0]
    check(mm["right"] * 100 // mm["total"] < 80 and body.get("mastered") == "1",
          f"累计 {mm['right']}/{mm['total']} 不到 80%，但最近全对，得分 {body.get('score')}，掌握了")
    st, body = answer("katakana", False, who="u2")
    check(body.get("mastered") == "1" and int(body["score"]) < 80,
          f"掌握后错一道，得分掉到 {body.get('score')}（< 80）也不收回")
    for _ in range(10):
        st, body = answer("katakana", False, who="u2")
        if body.get("mastered") == "0":
            break
    check(body.get("mastered") == "0" and int(body["score"]) < 60,
          f"一直错，得分掉到 60 以下（{body.get('score')}）才收回")
    # u2 没学过 hiragana（katakana 的前置），所以看不到可学列表，看「在学」
    st, body = post("/learn/status", learner="u2")
    prog = (body.get("state") or {}).get("progress") or {}
    doing = [r["code"] for r in (body.get("lists") or {}).get("doing", [])]
    check(prog.get("done") == 0 and "katakana" in doing,
          f"收回之后算回「在学」：done={prog.get('done')}，在学 {doing}")

    print("六、重导知识点不清空学习记录")
    before = rows("SELECT * FROM mastery")
    n_attempt = rows("SELECT count(*) n FROM attempt")[0]["n"]
    n_score = rows("SELECT count(*) n FROM score")[0]["n"]
    import_graph(ws)
    after = rows("SELECT * FROM mastery")
    check(before == after, "重导之后 mastery 一行没变")
    check(rows("SELECT count(*) n FROM attempt")[0]["n"] == n_attempt and n_attempt > 0,
          "流水也还在")
    check(rows("SELECT count(*) n FROM score")[0]["n"] == n_score and n_score > 0,
          "得分也还在")

    print("七、时间一律是本地时间")
    # 实体里「默认 现在」渲染成 datetime('now','localtime')。SQL 自己填时间的
    # 地方也得是本地时间——早先作答和掌握写的是 datetime('now')，那是 UTC，
    # 同一个库里两种时间差 9 小时，排序、按天统计全会错，而且不报错。
    local = rows("SELECT datetime('now','localtime') t")[0]["t"]
    a = rows("SELECT at FROM attempt ORDER BY id DESC LIMIT 1")[0]["at"]
    u = rows("SELECT updated FROM mastery WHERE learner='u1'")[0]["updated"]
    check(a[:13] == local[:13], f"作答时间是本地时间：{a}（现在 {local}）")
    check(u[:13] == local[:13], f"掌握的更新时间是本地时间：{u}")

    # 防再犯：代码里不许再出现写 UTC 的 datetime('now')。注释里提到它不算
    import re
    bare = re.compile(r"datetime\('now'\)")
    hits = []
    for pattern, mark in (("kg/queries/*.sql", "--"), ("kg/routes/*.zs", "#"),
                          ("tools/*.py", "#")):
        for f in sorted(ROOT.glob(pattern)):
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if bare.search(line.split(mark, 1)[0]):
                    hits.append(f"{f.relative_to(ROOT)}:{i}")
    check(not hits, f"代码里没有写 UTC 的 datetime('now')：{hits or '无'}")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
