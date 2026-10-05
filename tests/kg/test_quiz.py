# -*- coding: utf-8 -*-
"""做题：question / quiz_state 两张表，/quiz/import、state、start、next、answer。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_quiz.py

  一、导入：题数跟题库文件一致、没有对不上的条目；每道题的条目都有结构点
      （判完要记到那个点上）；可接受原样进库；等级从课程名取对
  二、导入坏数据：题号重复整批回滚；条目拼错的那道不进、报告说得出题号
  三、出题：按等级、考点筛；题干给了、答案和条目名没给；没有题时 404 且
      进度不动；进页面时把上次选的等级考点填回去
  四、接续题：答错、答对（全角、空格、句号都不计）、可接受的写法；同一道
      交两次只算一次；作答里带空格不出错
  五、选择题：答对答错；没作答 400 且不记录；批改里有条目和课文
  六、学习记录：attempt 的 point 是条目所属的结构点、item 是题号；mastery
      跟着累加；刚达标时说一声、标记写上
  六之二、掌握得分：批改后同一个事务里给这道题的点重算得分，state.score_change
      是「知识点 得分 a → b」（第一次打分、没变各有说法），不走 messages；
      同一道再交不重算
  七、一轮的计数：开始清零、下一题接着算；没出题就作答 400
  七之二、按课练：下一题不带 lesson 也留在这一课；一轮 = 本课 1 道（第一道）
      + 别的条目各 1 道（易混对比先出，其余同级同考点），共 5 道、条目不重复；
      一轮做完给提示、不换课；再来一轮本课换题、对比题也换；本课的题一轮轮
      下来全轮到时提示「这一课的 N 道题都出过了」；点开始退出按课练、地址回到
      #做题；没出过题时「再来一轮」400
  八、重导题目不碰学习记录
  九、选项打乱：判题时的顺序跟出题时一样；正确答案的位置分散；选对的内容
      判对、选错判错，批改标在界面上的位置（自由练一轮 10 道，做完再来一轮）
  十、一轮里每个条目只出一题：自由练几种范围 × 几个人 × 三轮，条目都不重复、
      一轮 10 道、做完出结果卡、再来一轮换没出过的条目；做满 10 道的那一下；
      候选条目不够时一轮缩短；按课练多课 × 两轮，本课恰好 1 道、条目不重复
"""

import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import client, import_graph, make_ws   # noqa: E402
from kg.__main__ import BANK, read_bank                      # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def main():
    bank = read_bank(BANK)
    check(len(bank) > 400, f"题库读得到：{len(bank)} 道")

    ws = make_ws(Path(tempfile.mkdtemp(prefix="quiz_")))
    import_graph(ws)
    c = client(ws)
    db = ws / "app.db"
    c.post("/lesson/import", json={"form": {}})

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    def rows(sql, *args):
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, args)]
        finally:
            con.close()

    def one(sql, *args):
        r = rows(sql, *args)
        return r[0] if r else {}

    def n(table, where="1", *args):
        return rows(f"SELECT count(*) n FROM {table} WHERE {where}", *args)[0]["n"]

    def imp(data):
        r = c.post("/quiz/import", json={"form": {"rows": data}})
        return r.status_code, (r.get_json(silent=True) or {})

    def msgs(body):
        return body.get("messages") or []

    def state(body):
        return body.get("state") or {}

    def card(body):
        """题卡：{code, head, stem, options:[{key,text,state}], verdict, mine, ok}"""
        return state(body).get("card") or {}

    def card_text(c):
        return "\n".join([c.get("head", ""), c.get("stem", "")]
                         + [o["key"] + " " + o["text"] for o in c.get("options") or []])

    def current(who="me"):
        return one("SELECT * FROM quiz_state WHERE learner = ?", who)

    def key(code):
        return one("SELECT * FROM question WHERE code = ?", code)

    def orig_options(code):
        """题库里的原选项：{原字母: 内容}"""
        out = {}
        for line in key(code)["stem"].splitlines():
            m = re.match(r"^\s*([A-D])\s*[.．、:：]\s*(.*)$", line)
            if m:
                out[m.group(1)] = m.group(2).strip()
        return out

    def right_key(cd):
        """正确答案在界面上（打乱后）的字母：按内容找"""
        want = orig_options(cd["code"])[key(cd["code"])["answer"]]
        return next(o["key"] for o in cd["options"] if o["text"] == want)

    print("一、导入")
    st, body = imp(bank)
    check(st == 200, f"导入：{st} {body.get('error', '')}")
    check(body.get("questions") == str(len(bank)) and n("question") == len(bank),
          f"题数一致：报告 {body.get('questions')}，库里 {n('question')}，文件 {len(bank)}")
    check(body.get("skipped") == "0", f"没有对不上条目的题：{body.get('skipped')} {body.get('note', '')[:80]}")
    joined = n("question q JOIN item i ON i.code = q.item JOIN node nd ON nd.code = i.point")
    check(joined == len(bank), f"每道题的条目都有结构点（判完记在那上面）：{joined}/{len(bank)}")
    lv = {r["level"]: r["n"] for r in rows("SELECT level, count(*) n FROM question GROUP BY level")}
    want = {}
    for q in bank:
        k = q["课程"][-2:].upper()
        want[k] = want.get(k, 0) + 1
    check(lv == want, f"等级从课程名取：{lv}")
    acc = [q for q in bank if q.get("可接受")]
    if acc:
        got = json.loads(key(acc[0]["id"])["accept"])
        check(got == acc[0]["可接受"], f"可接受原样进库：{got}")
    check(key(bank[0]["id"])["stem"] == bank[0]["题干"], "题干原样进库（换行、全角符号）")

    print("二、导入坏数据")
    st, body = imp(bank + [bank[0]])
    check(st >= 400, f"题号重复：导入失败 {st}")
    check(n("question") == len(bank), f"整批回滚，库里的题一道不少：{n('question')}")
    bad = dict(bank[1], id="bunpou_n5-999-挖空-1", 条目="no-such-item")
    st, body = imp(bank + [bad])
    check(st == 200 and body.get("skipped") == "1"
          and "bunpou_n5-999-挖空-1" in (body.get("note") or "")
          and "no-such-item" in (body.get("note") or ""),
          f"条目拼错的那道不进、报告说得出题号：{body.get('skipped')} {body.get('note', '')[:80]}")
    check(n("question") == len(bank), "别的照常进库")

    print("三、出题")
    st, body = post("/quiz/state")
    check(st == 200 and body.get("form") == {"pick_level": "全部", "pick_kind": "全部"},
          f"没做过题：等级考点都是「全部」：{body.get('form')}")
    st, body = post("/quiz/start", pick_level="N4", pick_kind="接续")
    cur = current()
    q = key(cur.get("current", ""))
    check(st == 200 and q.get("level") == "N4" and q.get("kind") == "接续",
          f"按等级、考点出题：{cur.get('current')}")
    cd = card(body)
    text = card_text(cd)
    item_label = one("SELECT label FROM item WHERE code = ?", q["item"]).get("label", "")
    check(cd.get("code") == q["code"] and (cd.get("stem") or "").strip() == q["stem"].strip()
          and "N4" in cd.get("head", ""),
          f"题卡：题号、题干、等级：{cd.get('head')}")
    check(cd.get("options") == [], "接续题没有选项按钮")
    check(q["answer"] not in text and "answer" not in cd, "答案没露出来")
    check(item_label not in text.replace(q["stem"], ""), f"条目名（{item_label}）没露出来")
    check(cd.get("verdict") == "" and not msgs(body), "还没判：没有批改，也不推消息")
    check(state(body).get("phase") == "ask" and state(body).get("qtype") == "接续",
          f"state：{state(body)}")
    st, body = post("/quiz/state")
    check(body.get("form") == {"pick_level": "N4", "pick_kind": "接续"},
          f"再进页面，等级考点填回上次的：{body.get('form')}")
    before = current()
    st, body = post("/quiz/start", pick_level="N9", pick_kind="接续")
    check(st == 404 and "没有题" in (body.get("error") or ""), f"没有题：{st} {body.get('error')}")
    check(current() == before, "没题时进度不动")

    print("四、接续题")
    code = cur["current"]
    st, body = post("/quiz/answer", given="ぜんぜんちがう")
    cd = card(body)
    check(st == 200 and cd.get("ok") == "0" and q["answer"] in cd.get("verdict", ""),
          f"答错：题卡上给正确答案 {cd.get('verdict', '')[:40]!r}")
    check(cd.get("code") == code and cd.get("mine") == "ぜんぜんちがう",
          "题卡原地更新（题号不变、不翻页），记着你写的")
    check(state(body).get("phase") == "done", "判完 phase=done，作答区收起")
    a = rows("SELECT * FROM attempt WHERE learner = 'me'")
    point = one("SELECT point FROM item WHERE code = ?", q["item"])["point"]
    check(len(a) == 1 and a[0]["point"] == point and a[0]["item"] == code and a[0]["correct"] == 0,
          f"attempt 记在结构点 {point} 上，item 是题号：{a}")
    st, body = post("/quiz/answer", given=q["answer"])
    check(st == 400 and "答过" in (body.get("error") or ""), f"同一道再交：{st} {body.get('error')}")
    check(n("attempt") == 1, "第二次不记")
    check(current()["right"] == 0 and current()["total"] == 1, "这一轮 0/1")

    # 换一道接续题，用全角、空格、句号的写法答对
    st, body = post("/quiz/next", pick_level="N4", pick_kind="接续")
    code2 = current()["current"]
    check(code2 != code, f"下一题不是刚才那道：{code2}")
    ans = key(code2)["answer"]
    fancy = " ".join(ans) + "。"          # 字间插空格、末尾加句号
    check(card(body).get("code") == code2, "下一题：题卡换成新的一张（题号变了，界面据此翻页）")
    st, body = post("/quiz/answer", given=fancy)
    check(st == 200 and card(body).get("ok") == "1",
          f"空格、句号不计，判对：{fancy} → {card(body).get('verdict', '')[:20]!r}")
    check(current()["right"] == 1 and current()["total"] == 2, f"这一轮 1/2：{state(body).get('stat')}")
    check(state(body).get("stat") == "这一轮 1/2", f"顶栏的成绩：{state(body).get('stat')}")

    # 可接受的写法
    accq = [x for x in bank if x.get("可接受") and x["题型"] == "接续"]
    if accq:
        x = accq[0]
        con = sqlite3.connect(db)
        con.execute("UPDATE quiz_state SET current = ?, answered = 0 WHERE learner = 'me'", (x["id"],))
        con.commit()
        con.close()
        st, body = post("/quiz/answer", given=x["可接受"][0])
        check(st == 200 and card(body).get("ok") == "1", f"可接受的写法判对：{x['可接受'][0]}")
    else:
        check(False, "题库里没有带「可接受」的接续题，测不了")

    print("五、选择题")
    st, body = post("/quiz/start", pick_level="全部", pick_kind="挖空")
    q = key(current()["current"])
    check(state(body).get("qtype") == "选择", f"挖空是选择题：{state(body).get('qtype')}")
    cd = card(body)
    opts = cd.get("options") or []
    check([o["key"] for o in opts] == ["A", "B", "C", "D"] and all(o["text"] for o in opts),
          f"选项拆成 A–D 四个带内容的按钮：{[o['key'] + ' ' + o['text'] for o in opts]}")
    check(all(o["state"] == "" for o in opts), "还没答：选项都没标对错（按钮能点）")
    check("A." not in cd.get("stem", "") and opts[0]["text"] in q["stem"],
          "选项从题面里拆出去了，题面不再重复列一遍")
    before = n("attempt")
    st, body = post("/quiz/answer", choice="", given="")
    check(st == 400 and "还没作答" in (body.get("error") or ""), f"没作答：{st}")
    check(n("attempt") == before and current()["answered"] == 0, "没作答不记、这道还能答")
    rk = right_key(cd)
    st, body = post("/quiz/answer", choice=rk)
    cd = card(body)
    check(st == 200 and cd.get("ok") == "1", f"选对（界面上的 {rk}，原字母 {q['answer']}）")
    marks = {o["key"]: o["state"] for o in cd.get("options") or []}
    check(marks.get(rk) == "right" and all(v == "dim" for k, v in marks.items() if k != rk),
          f"选对：答案那项标 right，其余淡出：{marks}")
    lab = one("SELECT label FROM item WHERE code = ?", q["item"])["label"]
    check("考的是：" + lab in cd.get("verdict", ""), f"批改里说了考的条目：{lab}")
    if q.get("lesson"):
        title = one("SELECT title FROM lesson WHERE code = ?", q["lesson"]).get("title", "")
        check(title and f"《{title}》" in cd.get("verdict", ""), f"批改里有课文：{title}")
    check(current()["choice"] == q["answer"], "选的选项记在进度里（记题库里的原字母）")
    st, body = post("/quiz/next", pick_level="全部", pick_kind="挖空")
    q = key(current()["current"])
    rk = right_key(card(body))
    wrong = next(x for x in "ABCD" if x != rk)
    st, body = post("/quiz/answer", choice=wrong, given="写了也不看")
    cd = card(body)
    marks = {o["key"]: o["state"] for o in cd.get("options") or []}
    check(st == 200 and cd.get("ok") == "0", "选错；选择题不看输入框")
    check(marks.get(wrong) == "wrong" and marks.get(rk) == "right",
          f"选错：选的那项标 wrong、答案标 right：{marks}")
    check(f"正确答案是 {rk}" in cd.get("verdict", ""),
          f"批改说的正确答案是界面上的字母 {rk}：{cd.get('verdict', '')[:20]!r}")

    print("六、学习记录")
    tot = rows("SELECT sum(total) t, sum(right) r FROM mastery WHERE learner = 'me'")[0]
    att = rows("SELECT count(*) t, sum(correct) r FROM attempt WHERE learner = 'me'")[0]
    check(tot["t"] == att["t"] and tot["r"] == att["r"],
          f"mastery 汇总跟流水对得上：{tot} / {att}")
    bad_pt = n("attempt a", "a.learner = 'me' AND a.point NOT IN (SELECT i.point FROM question q"
                            " JOIN item i ON i.code = q.item WHERE q.code = a.item)")
    check(bad_pt == 0, "每条流水的 point 都是那道题的条目所属的点")

    # 刚达标：t3 出一道选择题，在那道题的点上铺 7/7，再答对它
    st, body = post("/quiz/start", learner="t3", pick_level="全部", pick_kind="挖空")
    cd = card(body)
    q = one("SELECT q.code, q.answer, i.point FROM question q JOIN item i ON i.code = q.item"
            " WHERE q.code = ?", cd["code"])
    con = sqlite3.connect(db)
    con.execute("INSERT INTO mastery(learner, point, right, total, mastered) VALUES ('t3', ?, 7, 7, 0)",
                (q["point"],))
    con.commit()
    con.close()
    st, body = post("/quiz/answer", learner="t3", choice=right_key(cd))
    label = one("SELECT label FROM node WHERE code = ?", q["point"])["label"]
    cheer = state(body).get("cheer") or ""
    check(st == 200 and f"「{label}」达标了" in cheer, f"刚达标说一声（state.cheer，题卡上显示）：{cheer[-40:]}")
    # 对照在上面「还没判：不推消息」；这里是喜报不走 messages——做题页没有
    # 消息流，走 messages 的话早先被前端塞进了问老师的对话
    check(msgs(body) == [], f"喜报不走 messages（不会进问老师的消息流）：{msgs(body)}")
    st, body = post("/quiz/next", learner="t3", pick_level="全部", pick_kind="挖空")
    check(state(body).get("cheer") == "", "下一道出题时喜报清掉")
    mm = one("SELECT * FROM mastery WHERE learner = 't3' AND point = ?", q["point"])
    check(mm["right"] == 8 and mm["total"] == 8 and mm["mastered"] == 1, f"标记写上：{mm}")
    st, body = post("/learn/next", learner="t3")
    nxt = [r["code"] for r in (body.get("lists") or {}).get("next") or []]
    check(q["point"] not in nxt, "掌握了的点不再出现在「能学什么」里")

    print("六之二、掌握得分")
    # 同一个点上两道接续题（进阶），用 given 交，不受选项打乱影响
    pair = rows("SELECT q.code, q.answer, i.point FROM question q JOIN item i ON i.code = q.item"
                " WHERE q.qtype = '接续' AND i.point IN (SELECT i2.point FROM question q2"
                " JOIN item i2 ON i2.code = q2.item WHERE q2.qtype = '接续'"
                " GROUP BY i2.point HAVING count(*) >= 2) ORDER BY i.point, q.code LIMIT 2")
    plabel = one("SELECT label FROM node WHERE code = ?", pair[0]["point"])["label"]
    post("/quiz/start", learner="sc1", pick_level="全部", pick_kind="接续")

    def put_q(code):
        con = sqlite3.connect(db)
        con.execute("UPDATE quiz_state SET current = ?, answered = 0 WHERE learner = 'sc1'", (code,))
        con.commit()
        con.close()

    def sc_hist():
        return [r["value"] for r in rows("SELECT value FROM score WHERE learner = 'sc1' AND point = ?"
                                         " ORDER BY id", pair[0]["point"])]

    put_q(pair[0]["code"])
    st, body = post("/quiz/answer", learner="sc1", given=pair[0]["answer"])
    sc = state(body).get("score_change")
    # 进阶题答对一道：(1.3 + 0.25) / (1.3 + 0.25 + 1.25) → 55
    check(st == 200 and card(body).get("ok") == "1" and sc_hist() == [55],
          f"答对一道进阶题：自动记了一行得分 {sc_hist()}")
    check(sc == f"{plabel} 得分 55（第一次打分）", f"state 里有得分变化：{sc!r}")
    check(msgs(body) == [], f"得分变化不走 messages：{msgs(body)}")
    st, body = post("/quiz/answer", learner="sc1", given=pair[0]["answer"])
    check(st == 400 and sc_hist() == [55], "同一道再交：400，不重算、不加行")
    put_q(pair[1]["code"])
    st, body = post("/quiz/answer", learner="sc1", given="ぜんぜんちがう")
    sc = state(body).get("score_change")
    check(card(body).get("ok") == "0" and len(sc_hist()) == 2 and sc_hist()[1] < 55,
          f"答错一道：分降了 {sc_hist()}")
    check(sc == f"{plabel} 得分 55 → {sc_hist()[-1]}", f"批改后显示「得分 a → b」：{sc!r}")
    st, body = post("/quiz/next", learner="sc1", pick_level="全部", pick_kind="接续")
    check(state(body).get("phase") == "ask", "下一题：phase=ask（得分那行只在判完时显示）")
    check(not rows("SELECT 1 FROM score WHERE learner = 'me' AND point NOT IN"
                   " (SELECT point FROM attempt WHERE learner = 'me')"),
          "me 的得分都落在答过的点上")
    check(rows("SELECT count(DISTINCT point) n FROM score WHERE learner = 'me'")[0]["n"]
          == rows("SELECT count(DISTINCT point) n FROM attempt WHERE learner = 'me'")[0]["n"],
          "对照：me 答过的每个点都有得分")

    print("七、一轮的计数")
    st, body = post("/quiz/answer", learner="nobody")
    check(st == 400 and "先点" in (body.get("error") or ""), f"没出题就作答：{st} {body.get('error')}")
    check(n("attempt", "learner = 'nobody'") == 0, "也不记")
    post("/quiz/start", pick_level="N5", pick_kind="全部")
    check(current()["right"] == 0 and current()["total"] == 0, "开始：这一轮清零")
    q = key(current()["current"])
    ans = q["answer"] if q["qtype"] == "选择" else ""
    post("/quiz/answer", choice=ans or "A", given=q["answer"])
    post("/quiz/next", pick_level="N5", pick_kind="全部")
    check(current()["total"] == 1, "下一题：接着算")

    print("七之二、按课文练（老师讲完课给的链接）")
    # 挑一课：有易混对比（contrast 里跟本课条目成对）、题最多的那课
    L = one("""SELECT q.lesson, count(*) n FROM question q
               WHERE q.item IN (SELECT a FROM contrast UNION SELECT b FROM contrast)
               GROUP BY q.lesson ORDER BY n DESC, q.lesson LIMIT 1""")
    lesson, nL = L["lesson"], L["n"]
    mine_items = {r["item"] for r in rows("SELECT DISTINCT item FROM question WHERE lesson = ?", lesson)}
    pair = {r["x"] for r in rows("SELECT b x FROM contrast WHERE a IN (SELECT item FROM question WHERE lesson = ?)"
                                 " UNION SELECT a FROM contrast WHERE b IN (SELECT item FROM question WHERE lesson = ?)",
                                 lesson, lesson)}
    lv = one("SELECT level FROM lesson WHERE code = ?", lesson)["level"]
    other = "N5" if lv != "N5" else "N4"
    title = one("SELECT title FROM lesson WHERE code = ?", lesson)["title"]
    # 顶栏停在别的等级：按课文进来时不该按它筛，不然一道都没有
    post("/quiz/start", pick_level=other, pick_kind="全部")
    st, body = post("/quiz/lesson", lesson=lesson)
    q = key(current()["current"])
    check(st == 200 and q.get("lesson") == lesson,
          f"载入：直接出这一课的题（顶栏停在 {other} 也不影响）：{q.get('code')}")
    scope = state(body).get("scope") or ""
    check(scope == f"本课《{title}》+ 易混对比", f"顶栏说明练哪一课、混了易混对比：{scope}")
    check(current()["total"] == 0 and current()["lesson"] == lesson, "按课文进来：这一轮清零，库里记下这一课")
    check("lesson" not in (body.get("form") or {}),
          f"lesson 不填回表单（离开那一课后不该还只出它）：{body.get('form')}")
    # 连做下去：「下一题」不带 lesson（地址参数没并进来、直接调接口都一样），
    # 也带着别的等级考点——都不该把人带出这一课
    lesson_qs = {r["code"] for r in rows("SELECT code FROM question WHERE lesson = ?", lesson)}
    # 这一课能混进来的别的条目（易混对比的、同级同考点的选择题）
    kinds = {r["kind"] for r in rows("SELECT DISTINCT kind FROM question WHERE lesson = ? AND qtype = '选择'", lesson)}
    pair_avail = {r["item"] for r in rows("SELECT DISTINCT item FROM question WHERE qtype = '选择'")} & (pair - mine_items)
    lv_avail = {r["item"] for r in rows("SELECT DISTINCT item, kind FROM question WHERE qtype = '选择' AND level = ?", lv)
                if r["kind"] in kinds} - mine_items
    want_n = 1 + min(4, len(pair_avail | lv_avail))

    def lesson_round(who="me"):
        """接着当前那道做完一轮（每道都交、点下一题），回 (题号列表, phase=end 的响应)"""
        picked = [current(who)["current"]]
        for _ in range(20):
            post("/quiz/answer", learner=who, choice="A", given="x")
            st, body = post("/quiz/next", learner=who, pick_level=other, pick_kind="挖空")
            if state(body).get("phase") == "end":
                return picked, body
            picked.append(current(who)["current"])
        return picked, None

    picked, end_body = lesson_round()
    qs = [key(c) for c in picked]
    own = [x for x in qs if x["item"] in mine_items]
    oth = [x for x in qs if x["item"] not in mine_items]
    check(len(qs) == want_n, f"一轮 {want_n} 道（本课 1 + 别的条目 {want_n - 1}）：出了 {len(qs)} 道")
    check(len(own) == 1 and qs[0]["code"] in lesson_qs,
          f"每轮恰好 1 道本课的题，在第一道：{[x['code'] for x in own]}")
    check(len({x["item"] for x in qs}) == len(qs), f"一轮里条目各不相同：{[x['item'] for x in qs]}")
    check(all(x["qtype"] == "选择" for x in oth), "混进来的都是选择题，考的不是本课的条目")
    npair = min(len(pair_avail), want_n - 1)
    check(all(x["item"] in pair for x in oth[:npair])
          and all(x["item"] in pair or (x["level"] == lv and x["kind"] in kinds) for x in oth),
          f"易混对比的条目先出、其余是同级同考点：{[x['item'] for x in oth]}，对比条目 {sorted(pair)}")
    check(end_body is not None, "一轮出够了：下一题不再出题")
    rd = state(end_body or {}).get("round") or {}
    check("这一轮做完了" in (rd.get("text") or "") and "再来一轮" in rd.get("text", "")
          and "都出过了" not in rd.get("text", ""),
          f"一轮做完的提示（本课的题还没轮完，不说都出过了）：{rd.get('text')}")
    check(rd.get("back", "").endswith("lesson=" + lesson) and rd.get("more", "").startswith("#"),
          f"提示里给回教材、换一课的地址：{rd}")
    check(state(end_body or {}).get("round_lesson") == lesson, "round_lesson 还是这一课")
    st, body = post("/quiz/next", pick_level=other, pick_kind="挖空")
    check(state(body).get("phase") == "end" and key(current()["current"])["code"] == picked[-1],
          "再点下一题还是那句提示，不悄悄换课")
    st, body = post("/quiz/again", pick_level=other, pick_kind="挖空")
    check(st == 200 and state(body).get("phase") == "ask" and key(current()["current"])["lesson"] == lesson
          and current()["total"] == 0 and current()["round_n"] == 1,
          f"再来一轮：从这一课重新出、计数清零：{current()['current']}")
    check(current()["current"] != picked[0] and current()["current"] in lesson_qs,
          f"再来一轮：本课换了一道没出过的题：{picked[0]} → {current()['current']}")
    picked2, _ = lesson_round()
    check({x for x in picked2[1:]} != {x for x in picked[1:]},
          f"再来一轮：对比的题也换了：{picked[1:]} → {picked2[1:]}")

    # 本课的题一轮轮下来：每轮第一道都是没出过的本课题，最后一轮的卡上说「都出过了」
    who = "L1"
    post("/quiz/lesson", learner=who, lesson=lesson)
    leads, notes = [], []
    for r in range(len(lesson_qs) + 1):
        leads.append(current(who)["current"])
        pk, eb = lesson_round(who)
        notes.append("都出过了" in ((state(eb or {}).get("round") or {}).get("text") or ""))
        last_text = (state(eb or {}).get("round") or {}).get("text") or ""
        if r == len(lesson_qs) - 1:
            full_text = last_text
        post("/quiz/again", learner=who)
    nq = len(lesson_qs)
    check(set(leads[:nq]) == lesson_qs, f"前 {nq} 轮的本课题各不相同，本课 {nq} 道都轮到：{leads[:nq]}")
    check(notes[:nq] == [False] * (nq - 1) + [True],
          f"本课题全轮到的那一轮才提示：{notes[:nq]}")
    check(f"这一课的{nq}道题都出过了" in full_text, f"提示原文：{full_text}")
    check(leads[nq] in lesson_qs and not notes[nq], f"再来一轮从头轮：{leads[nq]}，第 {nq + 1} 轮不再提示")

    # 点开始退出按课练：地址里的 lesson 前端照样会并进来，后端不管它
    st, body = post("/quiz/start", pick_level=other, pick_kind="全部", lesson=lesson)
    q = key(current()["current"])
    check(st == 200 and q["level"] == other and not state(body).get("scope")
          and not current()["lesson"] and current()["round_seen"] == "," + q["code"] + ","
          and current()["round_n"] == 1,
          f"点开始：退出按课练，按等级出、说明清空、新的一轮：{q['code']} {state(body).get('scope')!r} {current()['lesson']!r}")
    check(body.get("go") == "做题", f"点开始：让前端回到不带 lesson 的 #做题：{body.get('go')}")
    st, body = post("/quiz/next", pick_level=other, pick_kind="全部")
    check(key(current()["current"])["level"] == other, "之后的下一题也按等级出")
    st, body = post("/quiz/again", learner="never")
    check(st == 400, f"没出过题时没有「再来一轮」：{st} {body.get('error')}")
    st, body = post("/quiz/lesson", lesson="hb-no-such")
    check(st == 404 and "没有这一课" in (body.get("error") or ""), f"没有这一课：{st} {body.get('error')}")
    st, body = post("/quiz/lesson")
    check(st == 400, f"不给 lesson：{st}")
    empty = rows("SELECT code FROM lesson WHERE code NOT IN (SELECT lesson FROM question"
                 " WHERE lesson IS NOT NULL) LIMIT 1")
    if empty:
        st, body = post("/quiz/lesson", lesson=empty[0]["code"])
        check(st == 404 and "还没有题" in (body.get("error") or ""),
              f"没有题的课（{empty[0]['code']}）：{st} {body.get('error')}")

    print("八、重导题目不碰学习记录")
    keep = {t: rows(f"SELECT * FROM {t} ORDER BY id") for t in ("attempt", "mastery")}
    imp(bank)
    imp(bank)
    check({t: rows(f"SELECT * FROM {t} ORDER BY id") for t in keep} == keep,
          "重导两次，attempt / mastery 原样")

    print("九、选项打乱")
    # 对照：不打乱时正确答案就在题库写的那个字母上
    shown_pos, same_order, judged = [], True, True
    moved = 0
    st, body = post("/quiz/start", learner="t9", pick_level="全部", pick_kind="挖空")
    for i in range(60):
        cd = card(body)
        orig = orig_options(cd["code"])
        texts = [o["text"] for o in cd["options"]]
        check_set = sorted(texts) == sorted(orig.values())
        rk = right_key(cd)
        shown_pos.append(rk)
        moved += [o["text"] for o in cd["options"]] != [orig[k] for k in "ABCD"]
        # 一半选对、一半选错
        pick = rk if i % 2 == 0 else next(k for k in "ABCD" if k != rk)
        st, body = post("/quiz/answer", learner="t9", choice=pick)
        ad = card(body)
        # 判题时重拆的顺序跟出题时一模一样（同一个种子）
        same_order = same_order and check_set and [o["text"] for o in ad["options"]] == texts
        marks = {o["key"]: o["state"] for o in ad["options"]}
        judged = judged and ad["ok"] == ("1" if pick == rk else "0") and marks[rk] == "right" \
            and (pick == rk or marks[pick] == "wrong")
        st, body = post("/quiz/next", learner="t9", pick_level="全部", pick_kind="挖空")
        if state(body).get("phase") == "end":
            # 自由练一轮 10 道，做完再来一轮
            st, body = post("/quiz/again", learner="t9")
    check(same_order, "判题时选项顺序跟出题时一样（刷新、重拆都是同一个顺序）")
    check(judged, "选正确内容判对、选错判错；批改的 right / wrong 标在界面上的位置")
    dist = {k: shown_pos.count(k) for k in "ABCD"}
    check(len([v for v in dist.values() if v]) == 4 and max(dist.values()) <= 30,
          f"正确答案在界面上的位置分散（60 道）：{dist}")
    check(moved >= 30, f"大多数题的选项顺序跟题库不一样：{moved}/60")
    t9 = rows("SELECT correct FROM attempt WHERE learner = 't9'")
    check(len(t9) == 60 and sum(r["correct"] for r in t9) == 30, f"学习记录 60 道、对 30 道：{len(t9)}")

    print("十、一轮里每个知识点（条目）只出一题")

    def items_of(codes):
        return [key(x)["item"] for x in codes]

    def free_round(who, lvl, kd, first=None):
        """自由练做一轮：从当前那道接着做到 phase=end，回 (题号列表, end 的响应)"""
        codes = [first or current(who)["current"]]
        for _ in range(30):
            post("/quiz/answer", learner=who, choice="A", given="x")
            st, body = post("/quiz/next", learner=who, pick_level=lvl, pick_kind=kd)
            if state(body).get("phase") == "end":
                return codes, body
            codes.append(current(who)["current"])
        return codes, None

    # 自由练：几种范围、几个学习者、每人三轮
    dup_rounds, bad_len, ends_ok, total_rounds = [], [], True, 0
    for who, lvl, kd in (("f1", "全部", "全部"), ("f2", "N5", "挖空"), ("f3", "N4", "全部"), ("f4", "N3", "挖空")):
        n_items = n("(SELECT DISTINCT item FROM question WHERE (? = '全部' OR level = ?) AND (? = '全部' OR kind = ?))",
                    "1", lvl, lvl, kd, kd)
        post("/quiz/start", learner=who, pick_level=lvl, pick_kind=kd)
        hist = []
        for r in range(3):
            codes, eb = free_round(who, lvl, kd)
            total_rounds += 1
            its = items_of(codes)
            if len(set(its)) != len(its):
                dup_rounds.append((who, r, its))
            if len(codes) != min(10, n_items):
                bad_len.append((who, r, len(codes), n_items))
            s_ = state(eb or {})
            ends_ok = ends_ok and s_.get("phase") == "end" and s_.get("round_total") == len(codes) \
                and "这一轮做完了" in ((s_.get("round") or {}).get("text") or "") \
                and s_.get("round_lesson") == "" and s_.get("round_mode") == "" \
                and not (s_.get("round") or {}).get("back")
            hist.append(set(its))
            st, body = post("/quiz/again", learner=who)
            if r < 2:
                ends_ok = ends_ok and st == 200 and state(body).get("phase") == "ask" \
                    and current(who)["total"] == 0 and current(who)["round_n"] == 1
        if who == "f2":
            # N5 挖空有 30 多个条目：再来一轮换没出过的条目，三轮互不重叠
            check(not (hist[0] & hist[1]) and not (hist[2] & (hist[0] | hist[1])),
                  f"自由练再来一轮：优先换没出过的条目（{n_items} 个条目，三轮互不重叠）")
    check(not dup_rounds, f"自由练 {total_rounds} 轮，每轮条目都不重复：{dup_rounds[:2]}")
    check(not bad_len, f"自由练一轮 10 道（候选条目够时）：{bad_len[:3]}")
    check(ends_ok, "一轮做完出结果卡：phase=end、round_total、「这一轮做完了」、没有回教材；再来一轮清零")
    # 一轮 10 道：第 10 道判完时还没结束，下一题才出结果卡
    post("/quiz/start", learner="f5", pick_level="N5", pick_kind="全部")
    for i in range(9):
        post("/quiz/answer", learner="f5", choice="A", given="x")
        post("/quiz/next", learner="f5", pick_level="N5", pick_kind="全部")
    st, body = post("/quiz/answer", learner="f5", choice="A", given="x")
    check(state(body).get("phase") == "done" and state(body).get("round_total") == 10, "第 10 道判完：phase=done")
    st, body = post("/quiz/next", learner="f5", pick_level="N5", pick_kind="全部")
    rd = (state(body).get("round") or {}).get("text") or ""
    check(state(body).get("phase") == "end" and "10道题各考一个不同的知识点" in rd,
          f"自由练做满 10 道出结果卡：{rd}")
    # 候选条目不够：N1 意思只有两三个条目，一轮就是那么几道
    n1 = n("(SELECT DISTINCT item FROM question WHERE level = 'N1' AND kind = '意思')")
    post("/quiz/start", learner="f6", pick_level="N1", pick_kind="意思")
    codes, eb = free_round("f6", "N1", "意思")
    check(len(codes) == n1 < 10 and state(eb or {}).get("phase") == "end"
          and f"{n1}道题" in ((state(eb or {}).get("round") or {}).get("text") or ""),
          f"候选条目只有 {n1} 个：一轮 {len(codes)} 道就结束")
    # 按课练：多课、每课两轮
    les = [r["lesson"] for r in rows("SELECT lesson FROM question WHERE lesson IS NOT NULL GROUP BY lesson"
                                     " HAVING count(*) >= 3 ORDER BY lesson LIMIT 12")]
    lesson_bad, lesson_rounds = [], 0
    for i, ls in enumerate(les):
        who = f"lr{i}"
        mine = {r["item"] for r in rows("SELECT DISTINCT item FROM question WHERE lesson = ?", ls)}
        post("/quiz/lesson", learner=who, lesson=ls)
        for r in range(2):
            codes = [current(who)["current"]]
            for _ in range(10):
                post("/quiz/answer", learner=who, choice="A", given="x")
                st, body = post("/quiz/next", learner=who)
                if state(body).get("phase") == "end":
                    break
                codes.append(current(who)["current"])
            lesson_rounds += 1
            its = items_of(codes)
            own = [x for x in codes if key(x)["lesson"] == ls and key(x)["item"] in mine]
            if len(set(its)) != len(its) or len(own) != 1 or codes[0] not in own or len(codes) > 5:
                lesson_bad.append((ls, r, its))
            post("/quiz/again", learner=who)
    check(not lesson_bad, f"按课练 {len(les)} 课 × 2 轮：每轮本课恰好 1 道、条目不重复、不超过 5 道：{lesson_bad[:2]}")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
