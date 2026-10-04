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
    text = (msgs(body) or [{}])[0].get("text", "")
    item_label = one("SELECT label FROM item WHERE code = ?", q["item"]).get("label", "")
    check(q["stem"] in text and "N4" in text, "消息里有题干和等级")
    check(q["answer"] not in text.replace(q["stem"], ""), "答案没露出来")
    check(item_label not in text.replace(q["stem"], ""), f"条目名（{item_label}）没露出来")
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
    m = msgs(body)
    check(st == 200 and m and m[0]["kind"] == "no" and q["answer"] in m[0]["text"],
          f"答错：给正确答案 {m[:1]}")
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
    st, body = post("/quiz/answer", given=fancy)
    m = msgs(body)
    check(st == 200 and m and m[0]["kind"] == "ok", f"空格、句号不计，判对：{fancy} → {m[:1]}")
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
        check(st == 200 and msgs(body)[0]["kind"] == "ok", f"可接受的写法判对：{x['可接受'][0]}")
    else:
        check(False, "题库里没有带「可接受」的接续题，测不了")

    print("五、选择题")
    st, body = post("/quiz/start", pick_level="全部", pick_kind="挖空")
    q = key(current()["current"])
    check(state(body).get("qtype") == "选择", f"挖空是选择题：{state(body).get('qtype')}")
    before = n("attempt")
    st, body = post("/quiz/answer", choice="", given="")
    check(st == 400 and "还没作答" in (body.get("error") or ""), f"没作答：{st}")
    check(n("attempt") == before and current()["answered"] == 0, "没作答不记、这道还能答")
    st, body = post("/quiz/answer", choice=q["answer"])
    m = msgs(body)
    check(st == 200 and m[0]["kind"] == "ok", f"选对：{q['answer']}")
    lab = one("SELECT label FROM item WHERE code = ?", q["item"])["label"]
    check("考的是：" + lab in m[0]["text"], f"批改里说了考的条目：{lab}")
    if q.get("lesson"):
        title = one("SELECT title FROM lesson WHERE code = ?", q["lesson"]).get("title", "")
        check(title and f"《{title}》" in m[0]["text"], f"批改里有课文：{title}")
    check(current()["choice"] == q["answer"], "选的选项记在进度里")
    post("/quiz/next", pick_level="全部", pick_kind="挖空")
    q = key(current()["current"])
    wrong = next(x for x in "ABCD" if x != q["answer"])
    st, body = post("/quiz/answer", choice=wrong, given="写了也不看")
    check(st == 200 and msgs(body)[0]["kind"] == "no", "选错；选择题不看输入框")

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
