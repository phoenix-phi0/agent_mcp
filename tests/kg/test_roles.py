# -*- coding: utf-8 -*-
"""kg 多人模式下教师、学生分端，和教师端的「学情」页。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_roles.py

临时工作区（照 kg 搭，导入知识点、课文、题目、单词），不碰 kg/app.db。同一个
工作区起单人模式和多人模式（login=True）两个应用，模型是离线假客户端。

  一、单人模式不分端：/auth/me 没有角色和标识；学习接口、学情接口都不查角色；
      score/add 照旧能记；教材页照旧记偏好
  二、引擎：「只许 学生」对回 student、「只许 教师」对回 teacher；拒绝的说明来自
      「认证 角色 … 拒绝 …」；没声明的角色名记警告
  三、教师登录：/auth/me 的 role_label=教师、badge=教师端
  四、教师调学生学习类接口（每个「只许 学生」）全是 403「教师账号不参与学习，
      请用学生账号」，学生调同样的接口不是 403（对照）；score/add 多人模式下教师
      也 403；库里没有任何记在教师名下的学习记录
  五、教师读教材：教材列表、读一课、条目挂的课、知识点能看，不写偏好；学生选
      系列照旧记偏好（对照）
  六、学生碰不了教师端：学情三个接口 403「需要教师权限」
  七、学情数据：两个学生的作答（/learn/answer 定好对错）、默写、问老师；教师名下
      塞一条旧作答（不该算进全班）。全班表各列、排序、全班薄弱点、单个学生的各块
      跟库里现算的一致；查不到的学生给 missing；学情接口不改学习数据
  八、AI 学情总结（假模型）：提示词里有这个学生的数据；存进 learner_report、不进
      chat_message；再开这个学生看得到上一份；模型回空 502、不写库；缺 student 400
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import import_graph, import_words, make_ws   # noqa: E402
from kg.__main__ import BANK, read_bank                             # noqa: E402
from tools.auth import LIMITER                                      # noqa: E402
from tools.mock import MockClient                                   # noqa: E402

PY = str(ROOT / ".venv" / "bin" / "python")
passed = failed = 0

SUMMARY = "学情总结：这个学生最近练得不多，薄弱点集中在一个知识点上。"
prompts = []
reply = {"summary": SUMMARY}


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def handler(prompt, system):
    if "意图分类器" in (system or ""):
        return '{"intent":"讲解","keywords":[],"level":"","kind":"","grade":"否"}'
    if "教研" in (system or ""):
        prompts.append(prompt)
        return reply["summary"]
    return "老师的回答"


def make(ws, login):
    from gen.project import make_app
    app, router = make_app(ws, real=False, login=login) if login else make_app(ws, real=False)
    mock = MockClient(handler=handler, offline=True)
    router.client_factory = lambda: mock
    return app, router


LEARNING_TABLES = ("attempt", "mastery", "score", "word_attempt", "chat_message",
                   "quiz_state", "dictation_state", "learner_pref")


def main():
    ws = make_ws(Path(tempfile.mkdtemp(prefix="roles_")))
    db = ws / "app.db"
    import_graph(ws)
    import_words(ws)
    solo_app, solo_router = make(ws, False)
    solo = solo_app.test_client()
    solo.post("/lesson/import", json={"form": {}})
    r = solo.post("/quiz/import", json={"form": {"rows": read_bank(BANK)}})
    check(r.status_code == 200, f"题目导入：{r.status_code}")

    def rows(sql, *args):
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        try:
            return [dict(x) for x in con.execute(sql, args)]
        finally:
            con.close()

    def n(table, where="1", *args):
        return rows(f"SELECT count(*) n FROM {table} WHERE {where}", *args)[0]["n"]

    def exec_sql(sql, *args):
        con = sqlite3.connect(db)
        try:
            con.execute(sql, args)
            con.commit()
        finally:
            con.close()

    def post(c, path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {}), r

    def snapshot():
        return {t: rows(f"SELECT * FROM {t} ORDER BY rowid") for t in LEARNING_TABLES}

    # ------------------------------------------------------------------
    print("一、单人模式不分端")
    st, b, _ = post(solo, "/auth/me")
    check(st == 200 and b.get("user") == "" and b.get("role_label") == "" and b.get("badge") == "",
          f"/auth/me：没人、没有角色和标识：{b}")
    st, b, _ = post(solo, "/quiz/state")
    st2, b2, _ = post(solo, "/report/home")
    check(st == 200 and st2 == 200 and "class_rows" in (b2.get("lists") or {}),
          f"学习接口、学情接口都能调（不查角色）：{st} {st2}")
    point = rows("SELECT code FROM node ORDER BY code LIMIT 1")[0]["code"]
    st, b, _ = post(solo, "/score/add", learner="solo_dbg", point=point, value="70")
    check(st == 200 and n("score", "learner = 'solo_dbg'") == 1, f"score/add 单人模式照旧能记：{st}")
    exec_sql("DELETE FROM score WHERE learner = 'solo_dbg'")
    st, b, _ = post(solo, "/lesson/list", learner="solo_pref", series="hanabira")
    check(st == 200 and n("learner_pref", "learner = 'solo_pref'") == 1, "教材页照旧记偏好")
    exec_sql("DELETE FROM learner_pref WHERE learner = 'solo_pref'")
    st, b, _ = post(solo, "/report/one", student="me")
    check(st == 200 and (b.get("state") or {}).get("student", {}).get("missing"),
          "单人模式 me 没有学习记录时：学情里查不到（missing）")

    # ------------------------------------------------------------------
    print("二、引擎：只许 / 拒绝")
    app, router = make(ws, True)
    student_eps = sorted(p for (m, p), ep in router.table.items() if ep.role == "student")
    teacher_eps = sorted(p for (m, p), ep in router.table.items() if ep.role == "teacher")
    want_student = {
        "/learn/answer", "/learn/next", "/learn/status",
        "/quiz/state", "/quiz/start", "/quiz/next", "/quiz/again", "/quiz/lesson", "/quiz/answer",
        "/quiz/summary",
        "/dictation/state", "/dictation/start", "/dictation/next", "/dictation/again",
        "/dictation/wrong", "/dictation/random", "/dictation/load", "/dictation/hint",
        "/dictation/answer", "/dictation/book",
        "/teacher/state", "/teacher/send", "/progress/page", "/score/now", "/score/history",
        "/node/list", "/node/one"}
    check(set(student_eps) == want_student,
          f"「只许 学生」{len(student_eps)} 个，多 {sorted(set(student_eps) - want_student)}"
          f" 缺 {sorted(want_student - set(student_eps))}")
    check({"/report/home", "/report/one", "/report/summary"} <= set(teacher_eps),
          "学情接口「只许 教师」对回 teacher")
    open_eps = sorted(p for (m, p), ep in router.table.items() if not ep.role)
    want_open = {"/auth/login", "/auth/logout", "/auth/me", "/auth/password", "/kg/roots",
                 "/kg/levels", "/kg/ancestors", "/kg/descendants", "/kg/contrasts",
                 "/item/lessons", "/lesson/list", "/lesson/one", "/word/list", "/word/one",
                 "/point/words", "/word/orphans"}
    check(set(open_eps) == want_open, f"两边都能调的 {len(open_eps)} 个：多 {sorted(set(open_eps) - want_open)}"
          f" 缺 {sorted(want_open - set(open_eps))}")
    check(router.role_deny.get("student") == "教师账号不参与学习，请用学生账号"
          and not router.warnings, f"拒绝说明来自「认证 角色 student 学生 拒绝 …」；没有警告 {router.warnings}")
    # 没声明的中文角色名：记警告
    bad = Path(tempfile.mkdtemp(prefix="roles_bad_"))
    (bad / "a.zs").write_text("认证 可选\n认证 角色 teacher 教师\n\n"
                              "接口 POST /x 动作 x 只许 校长\n  返回 ok\n结束\n", encoding="utf-8")
    from tools.dsl_http import Router
    rb = Router(bad, bad, bad / "sessions", real=False, login=True)
    check(any("校长" in w for w in rb.warnings), f"「只许 校长」没声明：警告 {rb.warnings}")

    # ------------------------------------------------------------------
    print("三、教师登录")
    LIMITER.reset()
    env = dict(os.environ, KG_TEST_PW="teach-pass-1")
    r = subprocess.run([PY, "-m", "kg", "建教师", "t1", "--显示名", "王老师", "--库", str(db),
                        "--密码环境变量", "KG_TEST_PW"], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=60)
    check(r.returncode == 0, "命令行建教师 t1")
    teacher = app.test_client()
    st, *_ = post(teacher, "/auth/login", username="t1", password="teach-pass-1")
    st2, b, _ = post(teacher, "/auth/me")
    check(st == 200 and b.get("role") == "teacher" and b.get("role_label") == "教师"
          and b.get("badge") == "教师端" and b.get("hide") == [], f"/auth/me：{b}")
    for u, label in (("s1", "小一"), ("s2", "小二")):
        post(teacher, "/student/create", username=u, display_name=label, password=f"{u}-pass")
    s1, s2 = app.test_client(), app.test_client()
    post(s1, "/auth/login", username="s1", password="s1-pass")
    post(s2, "/auth/login", username="s2", password="s2-pass")
    st, b, _ = post(s1, "/auth/me")
    check(b.get("role_label") == "学生" and b.get("badge") == "" and b.get("hide") == ["管理"],
          f"学生的 /auth/me：role_label=学生、没有标识：{b}")

    # ------------------------------------------------------------------
    print("四、教师碰不了学习接口")
    before = snapshot()
    bad = []
    for path in student_eps:
        st, b, _ = post(teacher, path, point=point, correct="1", content="你好", code=point,
                        pick_level="全部", pick_kind="全部")
        if st != 403 or b.get("error") != "教师账号不参与学习，请用学生账号":
            bad.append((path, st, b.get("error")))
    check(not bad, f"教师调 {len(student_eps)} 个学习接口全是 403「教师账号不参与学习，请用学生账号」"
                   f"（不对的 {bad[:3]}）")
    ctrl = []
    for path in ("/quiz/state", "/progress/page", "/dictation/state", "/teacher/state",
                 "/node/list", "/score/now", "/learn/next", "/dictation/book"):
        st, b, _ = post(s2, path)
        if st != 200:
            ctrl.append((path, st))
    check(not ctrl, f"对照：学生调同样的接口 200（不对的 {ctrl}）")
    st, b, _ = post(teacher, "/score/add", point=point, value="90")
    check(st == 403 and b.get("error") == "教师账号不参与学习，请用学生账号",
          f"score/add 多人模式下教师也 403：{st} {b.get('error')}")
    st, b, _ = post(s1, "/score/add", point=point, value="90")
    check(st == 403 and b.get("error") == "需要教师权限", "学生调 score/add 仍是「需要教师权限」")
    after = snapshot()
    check(all(after[t] == before[t] for t in LEARNING_TABLES if t not in ("quiz_state", "dictation_state"))
          and all(not [x for x in after[t] if x.get("learner") == "t1"] for t in LEARNING_TABLES),
          "库里没有任何记在 t1 名下的学习记录")

    # ------------------------------------------------------------------
    print("五、教师读教材，不写偏好")
    st, b, _ = post(teacher, "/lesson/list", series="hanabira")
    lessons = (b.get("lists") or {}).get("lessons") or []
    check(st == 200 and lessons and (b.get("state") or {}).get("series_head"),
          f"教材列表：{st}，{len(lessons)} 课")
    check(n("learner_pref", "learner = 't1'") == 0 and n("learner_pref", "learner = ''") == 0,
          "选了系列也不记偏好（t1 没有、空名字也没有）")
    st, b, _ = post(teacher, "/lesson/list", series="no_such_series")
    check(st == 200 and (b.get("form") or {}).get("series") == "hanabira",
          f"选了不存在的系列：回到 hanabira：{(b.get('form') or {}).get('series')}")
    code = lessons[0]["code"] if lessons else ""
    st, b, _ = post(teacher, "/lesson/one", lesson=code)
    check(st == 200 and ((b.get("state") or {}).get("reading") or {}).get("code") == code,
          f"读一课 {code}：{st}")
    item = rows("SELECT item FROM item_lesson LIMIT 1")
    st, *_ = post(teacher, "/item/lessons", item=item[0]["item"] if item else "")
    st2, *_ = post(teacher, "/kg/roots")
    st3, *_ = post(teacher, "/word/list")
    check(st == 200 and st2 == 200 and st3 == 200, f"条目挂的课、知识点、单词表能看：{st} {st2} {st3}")
    check(n("learner_pref", "learner = 't1'") == 0, "读完还是没有 t1 的偏好")
    st, b, _ = post(s2, "/lesson/list", series="hanabira")
    check(st == 200 and n("learner_pref", "learner = 's2'") == 1, "对照：学生选系列记偏好")
    exec_sql("DELETE FROM learner_pref WHERE learner = 's2'")

    # ------------------------------------------------------------------
    print("六、学生碰不了教师端")
    bad = []
    for path in ("/report/home", "/report/one", "/report/summary"):
        st, b, _ = post(s1, path, student="s2")
        if st != 403 or b.get("error") != "需要教师权限":
            bad.append((path, st, b.get("error")))
    check(not bad, f"学生调学情接口：403「需要教师权限」（不对的 {bad}）")

    # ------------------------------------------------------------------
    print("七、学情数据")
    # 两道题，挂在不同的知识点上
    qs = rows("SELECT q.code, q.item, a.point FROM question q JOIN item i ON i.code = q.item "
              "JOIN (SELECT code AS item_code, point FROM item) a ON a.item_code = q.item "
              "WHERE a.point IS NOT NULL ORDER BY q.code")
    q1 = qs[0]
    q2 = next(q for q in qs if q["point"] != q1["point"])
    plan = {"s1": [(q1, 0), (q1, 0), (q1, 0), (q2, 1), (q2, 1)],
            "s2": [(q1, 0), (q1, 1), (q2, 0), (q2, 0)]}
    for who, c in (("s1", s1), ("s2", s2)):
        for q, ok in plan[who]:
            st, b, _ = post(c, "/learn/answer", point=q["point"], item=q["code"], correct=str(ok))
            if st != 200:
                check(False, f"{who} 作答：{st} {b}")
    check(n("attempt", "learner = 's1'") == 5 and n("attempt", "learner = 's2'") == 4,
          "s1 作答 5 道（错 3），s2 作答 4 道（错 3）")
    # s1 默写错一个词；问老师一句
    post(s1, "/dictation/start", dict_direction="看中文写日语", dict_level="全部", dict_source="随机")
    post(s1, "/dictation/answer", dict_answer="ちがう")
    post(s1, "/teacher/send", content="てから怎么用")
    check(n("word_attempt", "learner = 's1' AND correct = 0") == 1 and n("chat_message", "learner = 's1'") == 2,
          "s1 默写错 1 个、问老师 2 条")
    # 教师名下早先留下的作答（分端之前），不该算进全班
    exec_sql("INSERT INTO attempt(learner, point, item, correct, answer, at) "
             "VALUES ('t1', ?, ?, 0, 'x', datetime('now','localtime'))", q2["point"], q2["code"])
    before = snapshot()

    st, b, _ = post(teacher, "/report/home")
    cls = {r["username"]: r for r in (b.get("lists") or {}).get("class_rows", [])}
    check(st == 200 and {"s1", "s2"} <= set(cls) and "t1" not in cls,
          f"全班表有 s1、s2，没有教师：{sorted(cls)}")

    def expect(who):
        cur = rows("SELECT point, value FROM score s WHERE learner = ? AND id = "
                   "(SELECT max(id) FROM score m WHERE m.learner = s.learner AND m.point = s.point)", who)
        # SQLite 的 round 是四舍五入（Python 的 round 是银行家舍入，20.5 → 20）
        avg = int(sum(x["value"] for x in cur) / len(cur) + 0.5) if cur else None
        recent = rows("SELECT correct FROM attempt WHERE learner = ? ORDER BY id DESC LIMIT 20", who)
        weak = sorted([x for x in cur if x["value"] < 80], key=lambda x: x["value"])[:3]
        labels = [rows("SELECT label FROM node WHERE code = ?", x["point"])[0]["label"] for x in weak]
        return {
            "attempt_n": len(recent),
            "recent_rate": f"{sum(x['correct'] for x in recent) * 100 // len(recent)}%" if recent else "—",
            "avg_score": str(avg) if avg is not None else "—",
            "mastered_n": n("mastery", "learner = ? AND mastered = 1", who),
            "weak": set(labels),
        }
    for who, label, book in (("s1", "小一", 1), ("s2", "小二", 0)):
        got, want = cls.get(who, {}), expect(who)
        weak_got = set(filter(None, (got.get("weak_points") or "").split("、"))) - {"—"}
        ok = (got.get("label") == label and got.get("attempt_n") == want["attempt_n"]
              and got.get("recent_rate") == want["recent_rate"] and got.get("avg_score") == want["avg_score"]
              and got.get("mastered_n") == want["mastered_n"] and weak_got == want["weak"]
              and got.get("book_n") == book and got.get("last_active")
              and got.get("href") == f"#%E5%AD%A6%E6%83%85?student={who}")
        check(ok, f"{who} 一行：{ {k: got.get(k) for k in ('label', 'attempt_n', 'recent_rate', 'avg_score', 'mastered_n', 'weak_points', 'book_n')} }"
                  f" 应为 {want}")
    check(cls["s1"]["recent_rate"] == "40%" and cls["s2"]["recent_rate"] == "25%",
          "近期正确率：s1 2/5=40%，s2 1/4=25%")
    # 排序
    st, b, _ = post(teacher, "/report/home", report_sort="平均得分")
    order = [r["username"] for r in (b.get("lists") or {}).get("class_rows", [])]
    avgs = {u: cls[u]["avg_score"] for u in cls}
    key = lambda u: (avgs[u] == "—", int(avgs[u]) if avgs[u] != "—" else 0)
    check(order == sorted(order, key=key) and (b.get("form") or {}).get("report_sort") == "平均得分",
          f"按平均得分排（低的在前，没分的最后）：{[(u, avgs[u]) for u in order]}")
    st, b, _ = post(teacher, "/report/home", report_sort="最近学习")
    order = [r["username"] for r in (b.get("lists") or {}).get("class_rows", [])]
    acts = [cls[u]["last_active"] for u in order]
    check(acts == sorted(acts, reverse=True), f"按最近学习排（新的在前）：{list(zip(order, acts))}")
    # 全班薄弱点
    wp = (b.get("lists") or {}).get("class_weak_points") or []
    wi = (b.get("lists") or {}).get("class_weak_items") or []
    p1 = next((x for x in wp if x["code"] == q1["point"]), {})
    p2 = next((x for x in wp if x["code"] == q2["point"]), {})
    check(wp and wp[0]["code"] == q1["point"] and p1.get("wrong_n") == 4 and p1.get("learner_n") == 2
          and p1.get("answer_n") == 5,
          f"全班薄弱知识点第一是 q1 的点：错 4、作答 5、2 人（{p1}）")
    check(p2.get("wrong_n") == 2 and p2.get("learner_n") == 1 and p2.get("answer_n") == 4,
          f"q2 的点：错 2、作答 4、1 人——教师那条旧作答不算（{p2}）")
    i1 = next((x for x in wi if x["code"] == q1["item"]), {})
    check(wi and len(wi) <= 10 and i1.get("wrong_n") == 4 and i1.get("label"),
          f"全班常错条目：q1 的条目错 4（{i1}）")

    # 单个学生
    st, b, _ = post(teacher, "/report/one", student="s1")
    stu = (b.get("state") or {}).get("student") or {}
    ls = b.get("lists") or {}
    check(st == 200 and stu.get("username") == "s1" and not stu.get("missing")
          and "小一" in stu.get("head", "") and stu.get("series_label")
          and "已掌握" in stu.get("overview", "") and "错词本 1 个" in stu.get("dictation", ""),
          f"抬头、概况、默写：{stu.get('head')} | {stu.get('overview')} | {stu.get('dictation')}")
    pts = {x["code"]: x for x in ls.get("student_points", [])}
    sc = {x["point"]: x["value"] for x in rows(
        "SELECT point, value FROM score s WHERE learner = 's1' AND id = "
        "(SELECT max(id) FROM score m WHERE m.learner = s.learner AND m.point = s.point)")}
    check(set(pts) == {q1["point"], q2["point"]} and pts[q1["point"]]["tally"] == "0/3"
          and pts[q2["point"]]["tally"] == "2/2"
          and all(pts[p]["score_text"] == str(v) for p, v in sc.items()),
          f"各知识点：答对/答题、得分跟库里一致：{[(p, x['tally'], x['score_text'], x['mastered_text']) for p, x in pts.items()]}")
    wr = ls.get("student_wrong") or []
    check(len(wr) == 1 and wr[0]["code"] == q1["item"] and wr[0]["wrong_n"] == 3 and wr[0]["tally"] == "0/3",
          f"常错条目：只有 q1 的条目，错 3（{wr}）")
    rc = ls.get("student_recent") or []
    stem = rows("SELECT stem FROM question WHERE code = ?", q2["code"])[0]["stem"]
    check(len(rc) == 5 and rc[0]["result"] == "对" and rc[0]["stem_brief"] == (stem[:40] + "…" if len(stem) > 40 else stem)
          and [x["result"] for x in rc] == ["对", "对", "错", "错", "错"],
          f"最近作答 5 条，新的在前，带题干摘要：{[(x['result'], x['stem_brief'][:10]) for x in rc]}")
    bk = ls.get("student_book") or []
    check(len(bk) == 1 and bk[0]["direction_label"] == "看中文写日语" and bk[0]["label"],
          f"默写错词本 1 个：{bk}")
    ch = ls.get("student_chat") or []
    check([x["chat_who"] for x in ch] == ["学生", "老师"] and ch[0]["chat_text"] == "てから怎么用",
          f"问老师记录（只读）：{[(x['chat_who'], x['chat_text'][:10]) for x in ch]}")
    st, b, _ = post(teacher, "/report/one", student="s2")
    ls2 = b.get("lists") or {}
    check(st == 200 and not ls2.get("student_book") and not ls2.get("student_chat")
          and len(ls2.get("student_recent") or []) == 4,
          "s2：没有错词、没有问老师、作答 4 条（按 student 过滤）")
    for who in ("t1", "nobody"):
        st, b, _ = post(teacher, "/report/one", student=who)
        stu = (b.get("state") or {}).get("student") or {}
        check(st == 200 and "没有这个学生" in stu.get("missing", "") and not (b.get("lists") or {}).get("student_recent"),
              f"{who}：查不到，给 missing：{stu.get('missing')}")
    st, b, _ = post(teacher, "/report/one")
    check(st == 400, "没给 student：400")
    check(snapshot() == before, "学情接口不改学习数据（8 张学习表前后一样）")

    # ------------------------------------------------------------------
    print("八、AI 学情总结（假模型）")
    chat_before = n("chat_message", "1")
    prompts.clear()
    st, b, _ = post(teacher, "/report/summary", student="s1")
    summ = (b.get("state") or {}).get("student_summary") or {}
    check(st == 200 and summ.get("text") == SUMMARY and summ.get("student") == "s1"
          and "t1" in summ.get("head", ""), f"写好了：{st} {summ.get('head')}")
    item_label = rows("SELECT label FROM item WHERE code = ?", q1["item"])[0]["label"]
    check(len(prompts) == 1 and "小一" in prompts[0] and item_label in prompts[0]
          and "てから怎么用" in prompts[0] and "默写过 1 个词" in prompts[0],
          "提示词里有这个学生的名字、常错条目、问过的问题、默写")
    rep = rows("SELECT learner, summary_text, written_by FROM learner_report")
    check(rep == [{"learner": "s1", "summary_text": SUMMARY, "written_by": "t1"}],
          f"存进 learner_report：{rep}")
    check(n("chat_message", "1") == chat_before, "不进 chat_message（学生的问老师记录没多）")
    st, b, _ = post(teacher, "/report/one", student="s1")
    check(((b.get("state") or {}).get("student_summary") or {}).get("text") == SUMMARY,
          "再打开 s1：看得到上一份总结")
    st, b, _ = post(teacher, "/report/one", student="s2")
    check(not ((b.get("state") or {}).get("student_summary") or {}).get("text"),
          "s2 没写过：总结是空的")
    reply["summary"] = ""
    st, b, _ = post(teacher, "/report/summary", student="s2")
    check(st == 502 and "没有写出总结" in b.get("error", "") and n("learner_report", "1") == 1,
          f"模型回空：502「{b.get('error')}」，不写库")
    reply["summary"] = SUMMARY
    st, b, _ = post(teacher, "/report/summary")
    check(st == 400 and n("learner_report", "1") == 1, "缺 student：400")
    st, b, _ = post(teacher, "/report/summary", student="t1")
    check(st == 404 and n("learner_report", "1") == 1, "给教师写：404，不写库")
    check(all(snapshot()[t] == before[t] for t in LEARNING_TABLES if t != "chat_message")
          and n("chat_message", "1") == chat_before, "写总结也不改学习数据")

    print(f"\n通过 {passed}，失败 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
