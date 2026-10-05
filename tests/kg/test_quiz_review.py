# -*- coding: utf-8 -*-
"""做题页的「复习薄弱点」模式：#做题?mode=review、queries/question_pick_review.sql。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_quiz_review.py

临时工作区（照 kg 搭，导入知识点、课文、题目），不碰 kg/app.db。总结用离线的
假模型（MockClient(offline=True)）。

  一、对照：没有作答记录时载入 mode=review 不报错，phase=noreview（界面一句
      「先按等级做几道」和「开始」），顶栏等级填 N5，库里不记复习模式
  二、构造作答历史：低分点 A（错三道）、低分点 B（一对一错，分比 A 高）、
      已掌握但 30 天没做的 M、已掌握最近刚做的 G
  三、一轮 10 道（M 的答对，其余答错）：第一道出自得分最低的 A；题只来自 A、B、M；
      G（掌握了、刚做过）不出；同一道题至少隔 3 题再出、而且错题确实会再出；
      同一个点不连出超过 2 道；M 少量混入（1–2 道）；中途刷新（state、再载入）
      模式和这一轮都还在；顶栏 scope「复习薄弱点：A、B…」
  四、出够 10 道：phase=end，卡上的提示；round_total 10；顶栏「结束并请老师总结」
      的条件不成立（round_mode=review）；请老师总结：提示词里是「复习薄弱点」
      这 10 道，写进对话记录，这一轮不清；再来一轮：新的一轮从 0 开始，还是复习
  五、打分和学习记录照常：attempt 多了 10 条、answer 都记了，A 的得分有新行
  六、点「开始」退出复习模式（地址里的 mode=review 并进了提交也不管），之后
      「下一题」按等级考点出
  七、别的学习者不串；老库补 quiz_state.mode 列，不重建
"""

import re
import sqlite3
from itertools import groupby
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import choice_key, client, import_graph, make_ws   # noqa: E402
from kg.__main__ import BANK, ensure_new_columns, read_bank              # noqa: E402
from tools.mock import MockClient                                        # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


SUMMARY = "老师对这一轮复习的总结。"


def brain(prompt, system):
    if "意图分类器" in (system or ""):
        return '{"intent":"讲解","keywords":[],"level":"","kind":"","grade":"否"}'
    return SUMMARY


def main():
    ws = make_ws(Path(tempfile.mkdtemp(prefix="quiz_review_")))
    import_graph(ws)
    c0 = client(ws)
    c0.post("/lesson/import", json={"form": {}})
    r = c0.post("/quiz/import", json={"form": {"rows": read_bank(BANK)}})
    assert r.status_code == 200, r.get_json()
    db = ws / "app.db"

    from gen.project import make_app
    app, router = make_app(ws, real=False)
    mock = MockClient(handler=brain, offline=True)
    router.client_factory = lambda: mock
    c = app.test_client()

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    def rows(sql, *args):
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        try:
            return [dict(x) for x in con.execute(sql, args)]
        finally:
            con.close()

    def one(sql, *args):
        r = rows(sql, *args)
        return r[0] if r else {}

    def exec_sql(sql, *args):
        con = sqlite3.connect(db)
        con.execute(sql, args)
        con.commit()
        con.close()

    def state(body):
        return body.get("state") or {}

    def point_of(code):
        return one("SELECT i.point FROM question q JOIN item i ON i.code = q.item WHERE q.code = ?",
                   code)["point"]

    def answer(body, right, learner="me"):
        cd = state(body).get("card") or {}
        q = one("SELECT * FROM question WHERE code = ?", cd["code"])
        if q["qtype"] == "选择":
            st, b = post("/quiz/answer", learner=learner,
                         choice=choice_key(cd, q["stem"], q["answer"], right))
        else:
            st, b = post("/quiz/answer", learner=learner,
                         given=q["answer"] if right else "わざと間違える")
        assert st == 200, b
        return b

    def learn(q, ok, learner="me"):
        r = c.post("/learn/answer", json={"form": {"learner": learner, "point": q["point"],
                                                  "item": q["code"], "correct": str(ok)}})
        assert r.status_code == 200, r.get_json()

    print("一、对照：没有作答记录")
    st, body = post("/quiz/lesson", mode="review")
    s = state(body)
    check(st == 200 and s.get("phase") == "noreview" and not body.get("error"),
          f"200、phase=noreview、不报错：{st} {s.get('phase')} {body.get('error')}")
    check(not s.get("card") and s.get("round_mode") == "review", "没出题卡")
    check((body.get("form") or {}).get("pick_level") == "N5", f"顶栏等级填 N5：{body.get('form')}")
    qs0 = rows("SELECT pick_level, current, mode FROM quiz_state WHERE learner = 'me'")
    check(qs0 == [{"pick_level": "N5", "current": None, "mode": None}],
          f"库里只记了等级 N5（没出题、不记复习模式）：{qs0}")
    st, b2 = post("/quiz/state")
    check((b2.get("form") or {}).get("pick_level") == "N5", "之后「进入时」的 /quiz/state 顶栏还是 N5")
    check(not body.get("messages"), "不往 messages 推")
    st, body = post("/quiz/start", pick_level="N5", pick_kind="全部", mode="review")
    check(st == 200 and state(body).get("phase") == "ask" and state(body).get("round_mode") == "",
          f"卡上的「开始」：按等级出题，不是复习：{st} {state(body).get('phase')}")
    exec_sql("DELETE FROM quiz_state")

    print("二、构造作答历史")
    # 每个点至少 6 道题、互不相同的四个点
    pts = [x["point"] for x in rows(
        "SELECT i.point FROM question q JOIN item i ON i.code = q.item"
        " GROUP BY i.point HAVING count(*) >= 6 ORDER BY i.point")]
    A, B, M, G = pts[:4]
    qs = {p: rows("SELECT q.code, i.point FROM question q JOIN item i ON i.code = q.item"
                  " WHERE i.point = ? ORDER BY q.code", p) for p in (A, B, M, G)}
    label = {p: one("SELECT label FROM node WHERE code = ?", p)["label"] for p in (A, B, M, G)}
    for q in qs[A][:3]:
        learn(q, 0)
    learn(qs[B][0], 1)
    learn(qs[B][1], 0)
    for p in (M, G):
        for q in qs[p][:2]:
            learn(q, 1)
    # M、G 当成已掌握（得分 90）；M 的作答挪到 30 天前，G 是刚做的
    for p in (M, G):
        exec_sql("INSERT INTO score(learner, point, value) VALUES ('me', ?, 90)", p)
        exec_sql("UPDATE mastery SET mastered = 1 WHERE learner = 'me' AND point = ?", p)
    exec_sql("UPDATE attempt SET at = datetime('now', 'localtime', '-30 days')"
             " WHERE learner = 'me' AND point = ?", M)
    cur = {x["point"]: x["value"] for x in rows(
        "SELECT s.point, s.value FROM score s WHERE s.learner = 'me'"
        " AND s.id = (SELECT max(id) FROM score m WHERE m.learner = 'me' AND m.point = s.point)")}
    check(cur[A] < cur[B] < 80 <= cur[M], f"A {cur[A]} < B {cur[B]} < 80 <= M {cur[M]}、G {cur[G]}")
    n_att = one("SELECT count(*) n FROM attempt WHERE learner = 'me'")["n"]
    n_score_a = one("SELECT count(*) n FROM score WHERE learner = 'me' AND point = ?", A)["n"]

    print("三、一轮 10 道")
    st, body = post("/quiz/lesson", mode="review")
    s = state(body)
    check(st == 200 and s.get("phase") == "ask" and s.get("round_mode") == "review",
          f"载入 mode=review：出题、round_mode=review：{st} {s.get('phase')} {body.get('error')}")
    scope = s.get("scope") or ""
    check(scope.startswith("复习薄弱点：") and label[A] in scope and label[B] in scope
          and scope.index(label[A]) < scope.index(label[B]),
          f"顶栏 scope 列出低分点（低的在前）：{scope}")
    check((body.get("form") or {}).get("pick_level") == "全部", f"有记录时顶栏不改成 N5：{body.get('form')}")
    check(one("SELECT mode FROM quiz_state WHERE learner = 'me'")["mode"] == "review", "库里记 mode=review")
    seq = []
    refreshed = None
    for i in range(10):
        code = state(body)["card"]["code"]
        seq.append(code)
        # M 的题答对（答错的话它就成了错题、低分点，会正常地再出），其余答错
        answer(body, point_of(code) == M)
        if i == 3:
            # 中途刷新：进页面（state）再「载入」mode=review
            st, b2 = post("/quiz/state")
            st, body = post("/quiz/lesson", mode="review")
            refreshed = (state(b2).get("round_mode"), state(body).get("round_mode"),
                         state(body).get("round_total"), state(body).get("scope"))
        else:
            st, body = post("/quiz/next", mode="review")
    check(refreshed == ("review", "review", 4, scope),
          f"刷新后模式和这一轮都在（round_total 4、scope 一样）：{refreshed}")
    ps = [point_of(x) for x in seq]
    names = [label.get(p, p) for p in ps]
    print("    本轮：" + "、".join(f"{x}({n})" for x, n in zip(seq, names)))
    check(ps[0] == A, f"第一道出自得分最低的 A：{names[0]}")
    check(set(ps) <= {A, B, M}, f"题只来自 A、B、M：{sorted(set(names))}")
    check(G not in ps, "G（掌握了、刚做过）不出")
    gaps = [j - i for i in range(len(seq)) for j in range(i + 1, len(seq)) if seq[i] == seq[j]]
    check(gaps and min(gaps) >= 4, f"错题会再出、同一道至少隔 3 题：间距 {gaps}")
    runs = max(len(list(g)) for _, g in groupby(ps))
    check(runs <= 2, f"同一个点不连出超过 2 道：最长连出 {runs}")
    check(1 <= ps.count(M) <= 2 and M not in ps[:4] and ps[4] == M,
          f"已掌握久没做的 M 少量混入（第 5 道起，{ps.count(M)} 道）")
    check(ps.count(A) + ps.count(B) >= 6, f"大部分是低分点：A {ps.count(A)}、B {ps.count(B)}")

    print("四、一轮做完")
    s = state(body)
    check(s.get("phase") == "end" and "这一轮复习做完了" in ((s.get("round") or {}).get("text") or ""),
          f"出够 10 道：phase=end，卡上提示：{s.get('phase')} {(s.get('round') or {}).get('text')}")
    check(s.get("round_total") == 10 and s.get("round_mode") == "review" and s.get("round_lesson") == "",
          f"round_total 10、round_mode review：{s.get('round_total')} {s.get('round_mode')}")
    check(not (s.get("round") or {}).get("more") and not (s.get("round") or {}).get("back"),
          "「换一课」「回教材」地址空（界面不画）")
    st, b = post("/quiz/next", mode="review")
    check(state(b).get("phase") == "end", "再点下一题还是这张卡")
    mock.calls.clear()
    st, body = post("/quiz/summary", mode="review")
    p = mock.calls[0]["prompt"] if mock.calls else ""
    check(st == 200 and "复习薄弱点" in p and "共 10 道" in p,
          f"请老师总结：提示词里是「复习薄弱点」这 10 道：{st} {body.get('error')}")
    check(len(re.findall(r"^\d+\. 【", p, re.M)) == 10, "每道题一段")
    ch = rows("SELECT * FROM chat_message WHERE learner = 'me' ORDER BY id")
    n_ok = ps.count(M)
    check(len(ch) == 2 and ch[0]["content"] == f"（做完一轮：复习薄弱点，{n_ok}/10）请老师总结",
          f"写进对话记录：{[x['content'][:30] for x in ch]}")
    check((state(body).get("summary") or {}).get("text") == SUMMARY and state(body).get("phase") is None,
          "做题页有总结卡片；这一轮不清（跟按课练一样）")
    st, body = post("/quiz/again", mode="review")
    s = state(body)
    check(st == 200 and s.get("phase") == "ask" and s.get("round_total") == 0 and s.get("round_mode") == "review"
          and s.get("summary") == "",
          f"再来一轮：新的一轮从 0 开始，还是复习：{st} {s.get('phase')} {s.get('round_total')} {body.get('error')}")

    print("五、打分和学习记录照常")
    check(one("SELECT count(*) n FROM attempt WHERE learner = 'me'")["n"] == n_att + 10,
          "attempt 多了 10 条")
    check(all(x["answer"] for x in rows("SELECT answer FROM attempt WHERE learner = 'me' ORDER BY id DESC LIMIT 10")),
          "每条都记了作答")
    check(one("SELECT count(*) n FROM score WHERE learner = 'me' AND point = ?", A)["n"] > n_score_a,
          "A 的得分记了新行（答题时重算）")

    print("六、点开始退出复习模式")
    st, body = post("/quiz/start", pick_level="N4", pick_kind="挖空", mode="review")
    s = state(body)
    check(st == 200 and s.get("round_mode") == "" and body.get("go") == "做题",
          f"开始：round_mode 空、回到不带参数的 #做题：{s.get('round_mode')!r} {body.get('go')}")
    check(one("SELECT mode FROM quiz_state WHERE learner = 'me'")["mode"] is None, "库里的 mode 清掉了")
    st, body = post("/quiz/next", pick_level="N4", pick_kind="挖空")
    q = one("SELECT level, kind FROM question WHERE code = ?", state(body)["card"]["code"])
    check(q == {"level": "N4", "kind": "挖空"} and state(body).get("round_mode") == "",
          f"下一题按等级考点：{q}")
    st, b = post("/quiz/again")
    check(st == 400, "不在复习也不在按课：再来一轮 400")

    print("七、别的学习者、老库补列")
    st, body = post("/quiz/lesson", learner="other", mode="review")
    check(st == 200 and state(body).get("phase") == "noreview", "other 没有作答记录：noreview（me 的不算）")
    old = Path(tempfile.mkdtemp(prefix="quiz_review_old_")) / "app.db"
    con = sqlite3.connect(old)
    con.execute("CREATE TABLE quiz_state (learner VARCHAR(255) NOT NULL PRIMARY KEY,"
                " pick_level VARCHAR(32) NOT NULL DEFAULT '全部', pick_kind VARCHAR(32) NOT NULL DEFAULT '全部',"
                " current VARCHAR(255), answered INTEGER NOT NULL DEFAULT 0, right INTEGER NOT NULL DEFAULT 0,"
                " total INTEGER NOT NULL DEFAULT 0, choice VARCHAR(32), given VARCHAR(255), lesson VARCHAR(255),"
                " round_seen VARCHAR(255), round_n INTEGER NOT NULL DEFAULT 0, seq INTEGER NOT NULL DEFAULT 0,"
                " round_from INTEGER NOT NULL DEFAULT 0)")
    con.execute("INSERT INTO quiz_state(learner, right, total) VALUES('me', 3, 4)")
    con.commit()
    con.close()
    added = ensure_new_columns(old, ws / "entities")
    check(added == ["quiz_state.mode"], f"补了 quiz_state.mode：{added}")
    con = sqlite3.connect(old)
    kept = con.execute("SELECT right, total, mode FROM quiz_state").fetchone()
    con.close()
    check(kept == (3, 4, None), f"原有的行还在（没重建）：{kept}")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
