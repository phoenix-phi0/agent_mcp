# -*- coding: utf-8 -*-
"""请老师讲一课：/teacher/send 的讲一课这一路，lesson_ref.sql、lesson_explain.sql、
lesson_find.sql 的找课。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_teacher_lesson.py

用户反馈「课文没法让老师讲解」：教材页没有请老师讲这一课的入口；问老师页
说「讲解第1课」「讲一下 N5 的 ～ています」「这课讲的是什么」都找不到或找
错课（标题「动词 て います」中间有空格，「ています」对不上，落到了讲解正文
里提过一句的《动词 たいです》）。

临时工作区照 kg 搭（同 test_teacher_chat.py），模型是离线假客户端：意图判定
（系统提示词里有「意图分类器」）按学习者原话查 INTENTS，别的回 REPLY。

  一、对照：lesson 参数、content 空——不判意图（只有一次平衡档），问话由接口
      拼好和回复一起回来（两条消息），提示词里是这一课的正文、例句、答题情况，
      链接「做这课的题」在前、「读课文」在后，两条记录记着这一课
  二、lesson 参数加一句话（「这课讲的是什么」）：照样讲这一课，问话用原话，
      不回显
  三、答题情况：按课做几道（有错的）之后，提示词里有答过几次、对几次、答错
      的条目；别的学习者不串
  四、没有题的课：只给「读课文」
  五、lesson 是不存在的编号：不调模型，友好回复加「打开教材」，200
  六、原话指名：课号（hb-n5-046）、「N5 第46课」、只有一个等级有的课号
      （第1课）；几个等级都有的课号没说等级：列出来问是哪一级，不调模型；
      没有这个号（第999课）：找不到，不调模型
  七、按标题、按语法项找课（讲解路的 lesson_find）：标题原文带空格、
      ～ています（回归：以前找成《动词 たいです》）
  八、「这课」：接着最近对话里的那一课；之前没聊过课时找不到；判成「教材」
      的「这课讲的是什么」也改成讲这一课
  九、出题意图里指名一课：出那一课的题；课号几个等级都有时说一声
  十、教材页 lesson_one 的抬头有课号、给「请老师讲解」的地址
"""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import client, import_graph, make_ws    # noqa: E402
from kg.__main__ import BANK, read_bank                       # noqa: E402
from tools.mock import MockClient                             # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


REPLY = "老师的讲解"


def intent(kind="讲解", keywords=(), level=""):
    return json.dumps({"intent": kind, "keywords": list(keywords), "level": level,
                       "kind": "", "grade": "否"}, ensure_ascii=False)


INTENTS = {
    "讲一下 hb-n5-046": intent(),
    "讲讲 N5 第46课": intent(level="N5"),
    "讲解第1课": intent(),
    "讲讲第46课": intent(),
    "讲解第999课": intent(),
    "讲一下 N5 的 ～ています": intent(keywords=["～ています"], level="N5"),
    "讲解《动词 て ください》": intent(keywords=["动词 て ください"]),
    "这一课的接续再说一遍": intent(),
    "这课讲的是什么": intent("教材"),
    "给我出N5第47课的题": intent("出题", level="N5"),
    "给我出第47课的题": intent("出题"),
}


def handler(prompt, system):
    if "意图分类器" in (system or ""):
        said = prompt.split("学习者的消息：")[-1].strip()
        return INTENTS.get(said, intent())
    return REPLY


def main():
    ws = make_ws(Path(tempfile.mkdtemp(prefix="teacher_lesson_")))
    import_graph(ws)
    c0 = client(ws)
    c0.post("/lesson/import", json={"form": {}})
    r = c0.post("/quiz/import", json={"form": {"rows": read_bank(BANK)}})
    assert r.status_code == 200, r.get_json()
    db = ws / "app.db"

    from gen.project import make_app
    app, router = make_app(ws, real=False)
    mock = MockClient(handler=handler, offline=True)
    router.client_factory = lambda: mock
    c = app.test_client()

    def rows(sql, *args):
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        try:
            return [dict(x) for x in con.execute(sql, args)]
        finally:
            con.close()

    def send(text="", learner="me", lesson=None):
        form = {"content": text, "learner": learner}
        if lesson is not None:
            form["lesson"] = lesson
        mock.calls.clear()
        r = c.post("/teacher/send", json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    def last(body):
        m = body.get("messages") or []
        return m[-1] if m else {}

    def hrefs(body):
        return [unquote(x["href"]) for x in last(body).get("links") or []]

    def texts(body):
        return [x["text"] for x in last(body).get("links") or []]

    def tiers():
        return [x.get("tier") for x in mock.calls]

    def answer_prompt():
        p = [x["prompt"] for x in mock.calls if "意图分类器" not in (x.get("system") or "")]
        return p[-1] if p else ""

    def chats(learner):
        return rows("SELECT * FROM chat_message WHERE learner = ? ORDER BY id", learner)

    L = rows("SELECT * FROM lesson WHERE code = 'hb-n5-046'")[0]
    n46 = rows("SELECT count(*) n FROM question WHERE lesson = ?", L["code"])[0]["n"]
    assert n46 > 0, "hb-n5-046 应该有题"

    print("一、lesson 参数、不带话：直接讲这一课")
    st, body = send(lesson=L["code"], learner="a1")
    msgs = body.get("messages") or []
    check(st == 200 and last(body).get("text") == REPLY, f"200，回老师的讲解：{st} {body.get('error') or ''}")
    check(tiers() == ["平衡"], f"不判意图，只调一次平衡档：{tiers()}")
    check(len(msgs) == 2 and msgs[0].get("who") == "你" and msgs[0].get("kind") == "user"
          and L["title"] in msgs[0].get("text", ""),
          f"问话由接口拼好一起回来（消息流里先是「你」）：{msgs[:1]}")
    p = answer_prompt()
    check(L["title"] in p and L["explanation"][:30] in p and L["code"] in p,
          "提示词里是这一课的标题、讲解正文")
    ex = json.loads(L["examples"])[0] if L["examples"] else None
    jp = (ex.get("jp") if isinstance(ex, dict) else None) or ""
    check(not jp or jp in p, f"提示词里有课文的例句：{jp}")
    check("还没做过这一课的题" in p, "没做过题：提示词里说还没做过这一课的题")
    check(hrefs(body) == [f"#做题?lesson={L['code']}", f"#教材?lesson={L['code']}"]
          and texts(body)[0].startswith("做这课的题") and texts(body)[1].startswith("读课文"),
          f"链接：做这课的题、读课文：{list(zip(texts(body), hrefs(body)))}")
    check(unquote(last(body).get("link", "")) == f"#做题?lesson={L['code']}", "老的 link 字段也是做题链接")
    ch = chats("a1")
    check(len(ch) == 2 and all(x["lesson"] == L["code"] and x["intent"] == "讲解" for x in ch)
          and L["title"] in ch[0]["content"],
          f"两条记录：意图讲解、记着这一课，学习者那条是拼好的问话：{[(x['role'], x['content'][:20]) for x in ch]}")

    print("二、lesson 参数加一句话")
    st, body = send("这课讲的是什么", learner="a2", lesson=L["code"])
    msgs = body.get("messages") or []
    check(st == 200 and tiers() == ["平衡"] and len(msgs) == 1, f"不判意图、不回显（前端回显过了）：{tiers()} {len(msgs)}")
    check(L["explanation"][:30] in answer_prompt() and "这课讲的是什么" in answer_prompt(),
          "提示词里是这一课的正文和学习者的原话")
    check(chats("a2")[0]["content"] == "这课讲的是什么", "学习者那条记原话")

    print("三、答题情况进提示词")
    qs = rows("SELECT * FROM question WHERE lesson = ? ORDER BY code", L["code"])
    q = next(x for x in qs if x["qtype"] != "选择") if any(x["qtype"] != "选择" for x in qs) else qs[0]
    item_label = rows("SELECT label FROM item WHERE code = ?", q["item"])[0]["label"]
    con = sqlite3.connect(db)
    point = rows("SELECT point FROM item WHERE code = ?", q["item"])[0]["point"]
    # 直接写作答（做题页判完写的就是这一行）：两错一对
    for ok in (0, 0, 1):
        con.execute("INSERT INTO attempt (learner, point, item, correct, answer) VALUES (?, ?, ?, ?, ?)",
                    ("a3", point, q["code"], ok, "x"))
    con.commit()
    con.close()
    st, body = send(lesson=L["code"], learner="a3")
    p = answer_prompt()
    check("答过 3 次，答对 1 次" in p and f"{item_label}（2 次）" in p,
          f"提示词里有答过 3 次、对 1 次，答错的条目 {item_label} 2 次")
    st, body = send(lesson=L["code"], learner="a4")
    check("还没做过这一课的题" in answer_prompt(), "别的学习者不串：还是没做过")

    print("四、没有题的课")
    # 现在每一课都有题：临时库里删掉一课的题（只动这个临时工作区）
    e = rows("SELECT code, title FROM lesson WHERE code <> ? ORDER BY code", L["code"])[0]
    con = sqlite3.connect(db)
    con.execute("DELETE FROM question WHERE lesson = ?", (e["code"],))
    con.commit()
    con.close()
    st, body = send(lesson=e["code"], learner="a5")
    check(st == 200 and hrefs(body) == [f"#教材?lesson={e['code']}"] and texts(body)[0].startswith("读课文"),
          f"只给读课文：{hrefs(body)}")

    print("五、不存在的课")
    st, body = send(lesson="hb-n9-999", learner="a6")
    msgs = body.get("messages") or []
    check(st == 200 and not mock.calls, f"200，不调模型：{st} {tiers()}")
    check("没有这一课" in last(body).get("text", "") and "hb-n9-999" in last(body).get("text", ""),
          f"友好回复：{last(body).get('text')}")
    check(hrefs(body) == ["#教材"], f"附「打开教材」：{hrefs(body)}")
    check(len(msgs) == 2 and "hb-n9-999" in msgs[0].get("text", ""), "问话也回来了")

    print("六、原话里指名一课")
    st, body = send("讲一下 hb-n5-046", learner="b1")
    check(tiers() == ["快", "平衡"] and L["explanation"][:30] in answer_prompt()
          and hrefs(body)[0] == f"#做题?lesson={L['code']}" and chats("b1")[-1]["lesson"] == L["code"],
          f"课号：讲 hb-n5-046，附做这课的题：{hrefs(body)}")
    st, body = send("讲讲 N5 第46课", learner="b2")
    check(L["explanation"][:30] in answer_prompt() and chats("b2")[-1]["lesson"] == L["code"],
          "「N5 第46课」：讲 hb-n5-046")
    ones = rows("SELECT code, title, explanation FROM lesson WHERE substr(code, -3) = '001'")
    st, body = send("讲解第1课", learner="b3")
    if len(ones) == 1:
        check(ones[0]["explanation"][:30] in answer_prompt() and chats("b3")[-1]["lesson"] == ones[0]["code"],
              f"「第1课」：只有一个等级有 001，讲 {ones[0]['code']}")
    else:
        check(not [t for t in tiers() if t == "平衡"], "「第1课」几个等级都有或没有：不调回答的模型")
    many = rows("SELECT code FROM lesson WHERE substr(code, -3) = '046'")
    st, body = send("讲讲第46课", learner="b4")
    t = last(body).get("text", "")
    check(len(many) > 1 and tiers() == ["快"] and "好几个等级" in t and all(x["code"] in t for x in many),
          f"「第46课」几个等级都有：列出来问是哪一级，不调回答的模型：{t[:80]}")
    st, body = send("讲解第999课", learner="b5")
    t = last(body).get("text", "")
    check(st == 200 and tiers() == ["快"] and "没找到你说的那一课" in t and hrefs(body) == ["#教材"],
          f"「第999课」：找不到，不拿别的课凑数，附打开教材：{t[:40]}")

    print("七、按标题、按语法项找课")
    st, body = send("讲一下 N5 的 ～ています", learner="c1")
    check(chats("c1")[-1]["lesson"] == L["code"] and hrefs(body)[0] == f"#教材?lesson={L['code']}",
          f"～ています：找到《{L['title']}》（标题中间有空格），不是《动词 たいです》：{chats('c1')[-1]['lesson']}")
    check(L["explanation"][:30] in answer_prompt(), "提示词里有这一课的正文")
    k = rows("SELECT * FROM lesson WHERE title = '动词 て ください'")[0]
    st, body = send("讲解《动词 て ください》", learner="c2")
    check(chats("c2")[-1]["lesson"] == k["code"] and k["explanation"][:30] in answer_prompt(),
          f"标题原文：找到 {k['code']}")

    print("八、「这课」")
    send(lesson=L["code"], learner="d1")
    st, body = send("这一课的接续再说一遍", learner="d1")
    check(tiers() == ["快", "平衡"] and L["explanation"][:30] in answer_prompt()
          and chats("d1")[-1]["lesson"] == L["code"],
          "接着最近对话里的那一课讲")
    st, body = send("这课讲的是什么", learner="d1")
    check(chats("d1")[-1]["intent"] == "讲解" and L["explanation"][:30] in answer_prompt(),
          "判成「教材」的「这课讲的是什么」也改成讲这一课")
    st, body = send("这课讲的是什么", learner="d2")
    check(st == 200 and tiers() == ["快"] and "没找到你说的那一课" in last(body).get("text", ""),
          "之前没聊过课：找不到，不调回答的模型")

    print("九、出题意图里指名一课")
    st, body = send("给我出N5第47课的题", learner="e1")
    check(hrefs(body)[:1] == ["#做题?lesson=hb-n5-047"] and tiers() == ["快"],
          f"出 hb-n5-047 的题：{hrefs(body)}")
    st, body = send("给我出第47课的题", learner="e2")
    check("好几个等级" in last(body).get("text", "") and "hb-n5-047" in last(body).get("text", ""),
          f"课号几个等级都有：说一声：{last(body).get('text', '')[:60]}")

    print("十、教材页")
    r = c.post("/lesson/one", json={"form": {"lesson": L["code"]}}).get_json() or {}
    rd = (r.get("state") or {}).get("reading") or {}
    check(unquote(rd.get("explain", "")) == f"#问老师?lesson={L['code']}",
          f"reading.explain 是 #问老师?lesson=…：{rd.get('explain')}")
    check("第46课" in rd.get("head", "") and L["code"] in rd.get("head", ""),
          f"抬头有课号：{rd.get('head')}")

    print()
    print("=" * 50)
    print(f"通过 {passed}，失败 {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
