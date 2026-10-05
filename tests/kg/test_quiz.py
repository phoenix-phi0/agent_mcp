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
  七、一轮的计数：开始清零、下一题接着算；没出题就作答 400
  八、重导题目不碰学习记录
"""

import json
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
    st, body = post("/quiz/answer", choice=q["answer"])
    cd = card(body)
    check(st == 200 and cd.get("ok") == "1", f"选对：{q['answer']}")
    marks = {o["key"]: o["state"] for o in cd.get("options") or []}
    check(marks.get(q["answer"]) == "right" and all(v == "dim" for k, v in marks.items() if k != q["answer"]),
          f"选对：答案那项标 right，其余淡出：{marks}")
    lab = one("SELECT label FROM item WHERE code = ?", q["item"])["label"]
    check("考的是：" + lab in cd.get("verdict", ""), f"批改里说了考的条目：{lab}")
    if q.get("lesson"):
        title = one("SELECT title FROM lesson WHERE code = ?", q["lesson"]).get("title", "")
        check(title and f"《{title}》" in cd.get("verdict", ""), f"批改里有课文：{title}")
    check(current()["choice"] == q["answer"], "选的选项记在进度里")
    post("/quiz/next", pick_level="全部", pick_kind="挖空")
    q = key(current()["current"])
    wrong = next(x for x in "ABCD" if x != q["answer"])
    st, body = post("/quiz/answer", choice=wrong, given="写了也不看")
    cd = card(body)
    marks = {o["key"]: o["state"] for o in cd.get("options") or []}
    check(st == 200 and cd.get("ok") == "0", "选错；选择题不看输入框")
    check(marks.get(wrong) == "wrong" and marks.get(q["answer"]) == "right",
          f"选错：选的那项标 wrong、答案标 right：{marks}")

    print("六、学习记录")
    tot = rows("SELECT sum(total) t, sum(right) r FROM mastery WHERE learner = 'me'")[0]
    att = rows("SELECT count(*) t, sum(correct) r FROM attempt WHERE learner = 'me'")[0]
    check(tot["t"] == att["t"] and tot["r"] == att["r"],
          f"mastery 汇总跟流水对得上：{tot} / {att}")
    bad_pt = n("attempt a", "a.learner = 'me' AND a.point NOT IN (SELECT i.point FROM question q"
                            " JOIN item i ON i.code = q.item WHERE q.code = a.item)")
    check(bad_pt == 0, "每条流水的 point 都是那道题的条目所属的点")

    # 刚达标：先给 t3 在某个点上铺 7/7，再答对一道那个点下的题
    q = one("SELECT q.code, q.qtype, q.answer, i.point FROM question q JOIN item i ON i.code = q.item"
            " WHERE q.qtype = '选择' LIMIT 1")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO mastery(learner, point, right, total, mastered) VALUES ('t3', ?, 7, 7, 0)",
                (q["point"],))
    con.execute("INSERT INTO quiz_state(learner, pick_level, pick_kind, current, answered, right, total)"
                " VALUES ('t3', '全部', '全部', ?, 0, 0, 0)", (q["code"],))
    con.commit()
    con.close()
    st, body = post("/quiz/answer", learner="t3", choice=q["answer"])
    texts = " ".join(x["text"] for x in msgs(body))
    label = one("SELECT label FROM node WHERE code = ?", q["point"])["label"]
    check(st == 200 and f"「{label}」达标了" in texts, f"刚达标说一声：{texts[-40:]}")
    mm = one("SELECT * FROM mastery WHERE learner = 't3' AND point = ?", q["point"])
    check(mm["right"] == 8 and mm["total"] == 8 and mm["mastered"] == 1, f"标记写上：{mm}")
    st, body = post("/learn/next", learner="t3")
    nxt = [r["code"] for r in (body.get("lists") or {}).get("next") or []]
    check(q["point"] not in nxt, "掌握了的点不再出现在「能学什么」里")

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
    per = {}
    for x in bank:
        per.setdefault(x["课文"], []).append(x)
    lesson, qs = max(per.items(), key=lambda kv: len(kv[1]))
    lv = qs[0]["课程"][-2:].upper()
    other = "N5" if lv != "N5" else "N4"
    title = one("SELECT title FROM lesson WHERE code = ?", lesson)["title"]
    # 顶栏停在别的等级：按课文进来时不该按它筛，不然一道都没有
    post("/quiz/start", pick_level=other, pick_kind="全部")
    st, body = post("/quiz/lesson", lesson=lesson)
    q = key(current()["current"])
    check(st == 200 and q.get("lesson") == lesson,
          f"载入：直接出这一课的题（顶栏停在 {other} 也不影响）：{q.get('code')}")
    check(title in (state(body).get("scope") or ""), f"顶栏说明只练哪一课：{state(body).get('scope')}")
    check(current()["total"] == 0, "按课文进来：这一轮清零")
    check("lesson" not in (body.get("form") or {}),
          f"lesson 不填回表单（离开那一课后不该还只出它）：{body.get('form')}")
    seen = {q["code"]}
    ok_all = True
    for _ in range(min(6, len(qs) + 2)):
        st, body = post("/quiz/next", pick_level=other, pick_kind="挖空", lesson=lesson)
        q = key(current()["current"])
        seen.add(q["code"])
        ok_all = ok_all and st == 200 and q["lesson"] == lesson
    check(ok_all, f"下一题带着 lesson：一直在这一课里（出过 {len(seen)} 道，这课共 {len(qs)} 道）")
    check(len(seen) > 1 or len(qs) == 1, "不是一直出同一道")
    st, body = post("/quiz/next", pick_level=other, pick_kind="全部")
    q = key(current()["current"])
    check(st == 200 and q["level"] == other and not state(body).get("scope"),
          f"不带 lesson 就回到按等级出、说明清空：{q['code']}")
    st, body = post("/quiz/lesson", lesson="hb-no-such")
    check(st == 404 and "没有这一课" in (body.get("error") or ""), f"没有这一课：{st} {body.get('error')}")
    st, body = post("/quiz/lesson")
    check(st == 400, f"不给 lesson：{st}")
    empty = rows("SELECT code FROM lesson WHERE code NOT IN (SELECT lesson FROM question"
                 " WHERE lesson IS NOT NULL) LIMIT 1")
    if empty:
        st, body = post("/quiz/start", lesson=empty[0]["code"])
        check(st == 404 and "还没有题" in (body.get("error") or ""),
              f"没有题的课（{empty[0]['code']}）：{st} {body.get('error')}")

    print("八、重导题目不碰学习记录")
    keep = {t: rows(f"SELECT * FROM {t} ORDER BY id") for t in ("attempt", "mastery")}
    imp(bank)
    imp(bank)
    check({t: rows(f"SELECT * FROM {t} ORDER BY id") for t in keep} == keep,
          "重导两次，attempt / mastery 原样")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
