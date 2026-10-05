# -*- coding: utf-8 -*-
"""做完题请老师总结：/quiz/summary、queries/round_attempts.sql。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_quiz_summary.py

临时工作区（照 kg 搭，导入知识点、课文、题目），不碰 kg/app.db。模型是离线的
假客户端（MockClient(offline=True)），由 router.client_factory 交给每个请求，
看得到每次发了什么提示词、用的哪一档；handler 可以换成抛错、回空。

  一、对照：没出过题、这一轮 0 道时 400 一句话，不调模型
  二、按课练一轮：做完到 phase=end（state 里 round_lesson 是这一课）；总结的
      提示词里是这一轮的每道题（作答、正确答案、对错、解析），选择题写的是
      选项内容不是字母；有进度摘要；平衡档；系统提示词是老师人设、不出题
      不判分
  三、写进对话记录：学习者、老师两条，intent=总结，老师那条的 links 是读课文、
      再练这一课（错得最多的课）、去问老师；/teacher/state 拉得回来；做题页
      state.summary 有正文和链接（错得最多的就是在练的课时不给「再练」）；
      之后在问老师页问「刚才那轮怎么样」，提示词里带着这条总结
  四、本轮范围：再来一轮重置；换一课重置；自由练从「开始」算起、下一题接着
      算；按等级考点进来（level/kind）也算开始；别的学习者不串
  五、自由练：答满 5 道 round_total>=5（按钮条件）、round_lesson 空；总结完
      这一轮结束（计数清零、题卡收起、再请总结是 0 道）
  六、模型出错：502 和一句人话（不是 500、不是 Traceback）；对话记录不写、
      这一轮不清；模型回空也是一句话
  七、attempt.answer 记下作答；老库补 attempt.answer、quiz_state.round_from
      两列，不重建、原有的行还在
"""

import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import client, import_graph, make_ws   # noqa: E402
from kg.__main__ import BANK, ensure_new_columns, read_bank  # noqa: E402
from tools import config                                     # noqa: E402
from tools.mock import MockClient                            # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


SUMMARY = "本轮 x/y。老师的总结正文：ようだ 和 そうだ 要分清。"
INTENT_PROGRESS = '{"intent":"进度","keywords":[],"level":"","kind":"","grade":"否"}'


class Brain:
    """假模型：意图判定回「进度」，别的回 SUMMARY；mode 可切成抛错、回空。"""
    mode = "ok"

    def __call__(self, prompt, system):
        if "意图分类器" in (system or ""):
            return INTENT_PROGRESS
        if self.mode == "boom":
            raise RuntimeError("claude 超过 180 秒没有返回\n第二行细节")
        if self.mode == "empty":
            return ""
        return SUMMARY


def main():
    ws = make_ws(Path(tempfile.mkdtemp(prefix="quiz_summary_")))
    import_graph(ws)
    c0 = client(ws)
    c0.post("/lesson/import", json={"form": {}})
    r = c0.post("/quiz/import", json={"form": {"rows": read_bank(BANK)}})
    assert r.status_code == 200, r.get_json()
    db = ws / "app.db"

    from gen.project import make_app
    app, router = make_app(ws, real=False)
    brain = Brain()
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

    def state(body):
        return body.get("state") or {}

    def key(code):
        return one("SELECT * FROM question WHERE code = ?", code)

    def orig_options(code):
        out = {}
        for line in key(code)["stem"].splitlines():
            m = re.match(r"^\s*([A-D])\s*[.．、:：]\s*(.*)$", line)
            if m:
                out[m.group(1)] = m.group(2).strip()
        return out

    def answer(body, right, learner="me"):
        """按题卡交一个对的或错的答案。返回 (状态码, 响应, 交的内容)"""
        cd = state(body).get("card") or {}
        q = key(cd["code"])
        if q["qtype"] == "选择":
            want = orig_options(q["code"])[q["answer"]]
            rk = next(o["key"] for o in cd["options"] if o["text"] == want)
            pick = rk if right else next(o["key"] for o in cd["options"] if o["key"] != rk)
            text = next(o["text"] for o in cd["options"] if o["key"] == pick)
            st, b = post("/quiz/answer", learner=learner, choice=pick)
            return st, b, text
        given = q["answer"] if right else "ぜんぜんちがう"
        st, b = post("/quiz/answer", learner=learner, given=given)
        return st, b, given

    def summary_calls():
        return [x for x in mock.calls if "意图分类器" not in (x.get("system") or "")]

    def chats(learner="me"):
        return rows("SELECT * FROM chat_message WHERE learner = ? ORDER BY id", learner)

    def summarize(learner="me"):
        mock.calls.clear()
        return post("/quiz/summary", learner=learner)

    print("一、对照：这一轮 0 道")
    st, body = summarize()
    check(st == 400 and "还没有做题" in (body.get("error") or "") and not mock.calls,
          f"没出过题：400 一句话、没调模型：{st} {body.get('error')}")
    check(not chats(), "对话记录没写")

    print("二、按课练一轮")
    # 挑一课：有选择题也有接续题、题不太多
    L = one("SELECT lesson, count(*) n FROM question WHERE lesson IS NOT NULL GROUP BY lesson"
            " HAVING sum(qtype = '选择') > 0 AND sum(qtype <> '选择') > 0 AND count(*) BETWEEN 4 AND 8"
            " ORDER BY lesson LIMIT 1")
    lesson = L["lesson"]
    title = one("SELECT title FROM lesson WHERE code = ?", lesson)["title"]
    st, body = post("/quiz/lesson", lesson=lesson)
    check(st == 200 and state(body).get("round_lesson") == lesson,
          f"按课进来：state.round_lesson = {state(body).get('round_lesson')}")
    st, b0 = summarize()
    check(st == 400 and not mock.calls, "刚进来、还没答：0 道，不调模型")
    done = []        # [(题号, 对错, 交的内容)]
    for i in range(40):
        if state(body).get("phase") == "end":
            break
        code = state(body)["card"]["code"]
        right = i % 3 == 0          # 第 1、4、7… 道答对，其余答错
        st, b, text = answer(body, right)
        done.append((code, right, text))
        st, body = post("/quiz/next")
    check(state(body).get("phase") == "end" and state(body).get("round_lesson") == lesson,
          f"一轮做完：phase=end（按钮「请老师总结这一轮」在这张卡上），做了 {len(done)} 道")
    n_right = sum(1 for _, ok, _ in done if ok)
    st, body = summarize()
    sc = summary_calls()
    check(st == 200 and len(sc) == 1, f"总结：200，调了一次模型：{st} {body.get('error')}")
    p = sc[0]["prompt"] if sc else ""
    sysp = sc[0].get("system") or "" if sc else ""
    check(sc and sc[0].get("tier") == "平衡" and sc[0].get("model") == config.resolve_model("平衡"),
          f"用的是平衡档：{sc and sc[0].get('tier')} {sc and sc[0].get('model')}")
    check(f"答对 {n_right} 道，共 {len(done)} 道" in p and f"本轮 {n_right}/{len(done)}" in p,
          f"提示词里有本轮 {n_right}/{len(done)}")
    check(f"按课练《{title}》" in p, "提示词里说了范围（按课练《标题》）")
    blocks = re.findall(r"^\d+\. 【", p, re.M)
    check(len(blocks) == len(done), f"每道题一段：{len(blocks)} 段 / 做了 {len(done)} 道")
    ok_all = True
    for code, right, text in done:
        q = key(code)
        if q["qtype"] == "选择":
            want = orig_options(code)[q["answer"]]
            ok_all = ok_all and f"正确答案：{want}；学习者选的：{text}" in p
        else:
            ok_all = ok_all and f"正确答案：{q['answer']}；学习者写的：{text}" in p
        ok_all = ok_all and (q["explain"] or "")[:20] in p
    check(ok_all, "每道题的正确答案、学习者的作答（选择题是选项内容）、解析都在")
    check(p.count("○ 答对") == n_right and p.count("✗ 答错") == len(done) - n_right,
          f"对错标得对：○ {p.count('○ 答对')}、✗ {p.count('✗ 答错')}")
    check(not re.search(r"学习者选的：[A-D]\b", p), "选择题没拿字母说事（界面上打乱过）")
    check("已掌握" in p and f"累计答题 {len(done)}" in p, "提示词里有进度摘要（progress_brief）")
    check("日语老师" in sysp and "不出新题" in sysp and "不重新判分" in sysp and "不要编造" in sysp,
          "系统提示词：老师人设，不出新题、不重新判分、不编造")

    print("三、写进对话记录、做题页上的总结")
    ch = chats()
    check(len(ch) == 2 and [x["role"] for x in ch] == ["learner", "teacher"]
          and all(x["intent"] == "总结" for x in ch),
          f"两条：学习者、老师，intent=总结：{[(x['role'], x['intent']) for x in ch]}")
    check(ch and ch[0]["content"] == f"（做完一轮：按课练《{title}》，{n_right}/{len(done)}）请老师总结",
          f"学习者那条：{ch and ch[0]['content']}")
    check(len(ch) == 2 and ch[1]["content"] == SUMMARY, "老师那条是总结全文")
    links = json.loads(ch[1]["links"]) if len(ch) == 2 else []
    check([unquote(x["href"]) for x in links]
          == [f"#教材?lesson={lesson}", f"#做题?lesson={lesson}", "#问老师"]
          and [x["text"] for x in links]
          == [f"读课文：《{title}》", f"再练这一课：《{title}》", "去问老师接着聊"],
          f"links：读课文、再练这一课、去问老师：{links}")
    check(len(ch) == 2 and ch[1]["lesson"] == lesson, "记着是哪一课")
    sm = state(body).get("summary") or {}
    check(sm.get("text") == SUMMARY and unquote(sm.get("read", "")) == f"#教材?lesson={lesson}"
          and unquote(sm.get("chat", "")) == "#问老师",
          f"做题页 state.summary：正文、读课文、去问老师：{sm}")
    check(sm.get("practice") == "", "错得最多的就是在练的课：做题页不给「再练这一课」（卡上有再来一轮）")
    check(not body.get("messages"), "做题页没有消息流，不往 messages 里推")
    check(state(body).get("phase") is None, "按课练总结完 phase 不动（还是那张一轮做完的卡）")
    r = c.post("/teacher/state", json={"form": {}}).get_json() or {}
    talk = (r.get("state") or {}).get("talk") or []
    check(len(talk) == 2 and talk[-1]["text"] == SUMMARY and talk[-1]["who"] == "老师"
          and [unquote(x["href"]) for x in talk[-1]["links"]][-1] == "#问老师",
          "/teacher/state 拉得回这条总结（带链接）")
    mock.calls.clear()
    r = c.post("/teacher/send", json={"form": {"content": "刚才那轮怎么样"}})
    tp = [x["prompt"] for x in summary_calls()]
    check(r.status_code == 200 and tp and SUMMARY in tp[0] and "请老师总结" in tp[0],
          "问老师「刚才那轮怎么样」：提示词的最近对话里有这条总结")
    st, body = summarize()
    check(st == 200 and len(summary_calls()) == 1, "按课练总结完这一轮不清，可以再请一次")

    print("四、本轮范围")
    st, body = post("/quiz/again")
    check(st == 200 and state(body).get("summary") == "", "再来一轮：总结卡片收起（summary 清空）")
    st, b0 = summarize()
    check(st == 400 and not mock.calls, "再来一轮后还没答：0 道")
    st, b, text = answer(body, False)
    st, b0 = summarize()
    p = (summary_calls() or [{}])[0].get("prompt", "")
    check(st == 200 and "共 1 道" in p and len(re.findall(r"^\d+\. 【", p, re.M)) == 1,
          "再来一轮后答 1 道：本轮就是这 1 道")
    other = one("SELECT lesson FROM question WHERE lesson IS NOT NULL AND lesson <> ? "
                "GROUP BY lesson ORDER BY lesson LIMIT 1", lesson)["lesson"]
    st, body = post("/quiz/lesson", lesson=other)
    st, b0 = summarize()
    check(st == 400 and not mock.calls, "换一课：重新算，0 道")
    st, b, text = answer(body, True)
    st, body = post("/quiz/next")
    st, b, text = answer(body, False)
    # 自由练：「开始」之前做的不算
    st, body = post("/quiz/start", pick_level="N5", pick_kind="全部")
    check(state(body).get("round_lesson") == "" and state(body).get("round_total") == 0,
          f"开始：自由练，round_total 0：{state(body).get('round_lesson')!r} {state(body).get('round_total')}")
    st, b0 = summarize()
    check(st == 400 and not mock.calls, "开始之后还没答：0 道（按课练做的不算）")
    for i in range(2):
        st, b, text = answer(body, i == 0)
        st, body = post("/quiz/next", pick_level="N5", pick_kind="全部")
    st, b0 = summarize()
    p = (summary_calls() or [{}])[0].get("prompt", "")
    check(st == 200 and "自由练（等级 N5，考点 全部）" in p and "答对 1 道，共 2 道" in p,
          f"自由练：从开始算起、下一题接着算，共 2 道：{st} {b0.get('error')}")
    # 按等级考点进来（问老师给的 #做题?level=N4&kind=接续）也是开一轮
    st, body = post("/quiz/lesson", level="N4", kind="接续")
    st, b0 = summarize()
    check(st == 400, "按等级考点进来：重新算")
    # 别的学习者不串
    st, bo = post("/quiz/start", learner="other", pick_level="N5", pick_kind="全部")
    answer(bo, True, learner="other")
    st, b0 = summarize()
    check(st == 400, "别的学习者答的不算到 me 头上")
    st, b0 = summarize(learner="other")
    p = (summary_calls() or [{}])[0].get("prompt", "")
    check(st == 200 and "共 1 道" in p, "other 自己的一轮是 1 道")

    print("五、自由练：答满 5 道出按钮，总结完这一轮结束")
    st, body = post("/quiz/start", pick_level="N4", pick_kind="挖空")
    totals = []
    for i in range(5):
        st, b, text = answer(body, i % 2 == 0)
        totals.append(state(b).get("round_total"))
        if i < 4:
            st, body = post("/quiz/next", pick_level="N4", pick_kind="挖空")
    check(state(body).get("round_total") == 4, f"出题时也带着 round_total：{state(body).get('round_total')}")
    check(totals == [1, 2, 3, 4, 5] and state(b).get("round_lesson") == "",
          f"判完带回 round_total（界面 >=5 才出「结束并请老师总结」）：{totals}")
    st, b2 = post("/quiz/state")
    check(state(b2).get("round_total") == 5 and state(b2).get("round_lesson") == "",
          "进页面（刷新）也带回 round_total、round_lesson")
    n_chat = len(chats())
    st, body = summarize()
    check(st == 200 and len(summary_calls()) == 1, "总结：调了一次模型")
    s = state(body)
    check(s.get("phase") == "" and s.get("stat") == "这一轮 0/0" and s.get("round_total") == 0,
          f"自由练总结完这一轮结束：题卡收起、计数清零：{s.get('phase')!r} {s.get('stat')} {s.get('round_total')}")
    check((s.get("summary") or {}).get("text") == SUMMARY and (s.get("summary") or {}).get("practice"),
          "做题页有总结；不是在练的课，「再练这一课」给了")
    check(len(chats()) == n_chat + 2, "对话记录多两条")
    st, b0 = summarize()
    check(st == 400 and not mock.calls, "再请总结：新的一轮 0 道，不重复总结")

    print("六、模型出错")
    st, body = post("/quiz/start", pick_level="N5", pick_kind="全部")
    st, b, text = answer(body, False)
    n_chat = len(chats())
    brain.mode = "boom"
    st, body = summarize()
    err = body.get("error") or ""
    check(st == 502 and "模型这次没有回应" in err and "过一会儿再试" in err and "Traceback" not in err
          and "第二行" not in err, f"502 一句人话：{st} {err}")
    check(not body.get("messages"), "不是「脚本出错」那种 messages")
    check(len(chats()) == n_chat, "对话记录没写半截")
    brain.mode = "empty"
    st, body = summarize()
    check(st == 502 and "没有给出总结" in (body.get("error") or "") and len(chats()) == n_chat,
          f"模型回空：{st} {body.get('error')}")
    brain.mode = "ok"
    st, body = summarize()
    check(st == 200 and "共 1 道" in (summary_calls() or [{}])[0].get("prompt", ""),
          "出错后这一轮没被清掉，再点一次照常总结")

    print("七、attempt.answer、老库补列")
    a = rows("SELECT a.answer, q.qtype, q.answer AS key FROM attempt a JOIN question q ON q.code = a.item")
    check(a and all(x["answer"] for x in a), f"每条作答都记了 answer（{len(a)} 条）")
    check(all(x["answer"] in "ABCD" for x in a if x["qtype"] == "选择"), "选择题记的是题库里的原字母")
    r = c.post("/learn/answer", json={"form": {"point": one("SELECT code FROM node LIMIT 1")["code"],
                                               "correct": "1"}})
    check(r.status_code == 200 and rows("SELECT answer FROM attempt ORDER BY id DESC LIMIT 1")[0]["answer"] is None,
          f"/learn/answer 照常能记（answer 空）：{r.status_code}")
    old = Path(tempfile.mkdtemp(prefix="quiz_summary_old_")) / "app.db"
    con = sqlite3.connect(old)
    con.execute("CREATE TABLE attempt (id INTEGER PRIMARY KEY AUTOINCREMENT, learner VARCHAR(255) NOT NULL,"
                " point VARCHAR(255) NOT NULL, item VARCHAR(255), correct INTEGER NOT NULL,"
                " at VARCHAR(255) NOT NULL DEFAULT (datetime('now','localtime')))")
    con.execute("CREATE TABLE quiz_state (learner VARCHAR(255) NOT NULL PRIMARY KEY,"
                " pick_level VARCHAR(32) NOT NULL DEFAULT '全部', pick_kind VARCHAR(32) NOT NULL DEFAULT '全部',"
                " current VARCHAR(255), answered INTEGER NOT NULL DEFAULT 0, right INTEGER NOT NULL DEFAULT 0,"
                " total INTEGER NOT NULL DEFAULT 0, choice VARCHAR(32), given VARCHAR(255), lesson VARCHAR(255),"
                " round_seen VARCHAR(255), round_n INTEGER NOT NULL DEFAULT 0, seq INTEGER NOT NULL DEFAULT 0)")
    con.execute("INSERT INTO attempt(learner, point, item, correct) VALUES('me', 'p', 'q', 1)")
    con.execute("INSERT INTO quiz_state(learner, right, total) VALUES('me', 3, 4)")
    con.commit()
    con.close()
    added = ensure_new_columns(old, ws / "entities")
    check(sorted(added) == ["attempt.answer", "quiz_state.round_from"], f"补了两列：{added}")
    con = sqlite3.connect(old)
    kept = (con.execute("SELECT count(*) FROM attempt").fetchone()[0],
            con.execute("SELECT right, total, round_from FROM quiz_state").fetchone())
    con.close()
    check(kept == (1, (3, 4, 0)), f"原有的行还在（没重建）：{kept}")
    check(ensure_new_columns(old, ws / "entities") == [], "再跑一次什么都不补")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
