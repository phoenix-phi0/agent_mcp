# -*- coding: utf-8 -*-
"""问老师：chat_message 表、/teacher/state、/teacher/send。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_teacher_chat.py

临时工作区（照 kg 搭，导入知识点、课文、题目），不碰 kg/app.db。模型是
离线的假客户端（MockClient(offline=True)），由 router.client_factory 交给
每个请求，所以看得到每次发了什么提示词、用的哪一档：

  意图判定的系统提示词里有「意图分类器」，按「学习者的消息：」后面那段
  （学习者原话）查 INTENTS 回预设的 JSON；别的调用（老师回答）回 REPLY。

模型档位怎么断言：calls 里记的 model 是解析过的名字（现在的 models.json 里
快 = cli:claude/haiku、平衡 = cli:claude/sonnet），tier 是从哪个档位查到的。
两样都比：tier 等于「快」/「平衡」，model 等于 config.resolve_model(档位)——
换了 models.json 也不用改测试。

  一、对照：讲解问答回老师的话，两条对话记录进库（学习者、老师），意图是讲解，
      附了参考课文的做题链接
  二、出题意图：回复里是 #做题?lesson=… 链接（跟 quiz_link 同一写法），只调了
      一次模型（判意图），没有在对话里出题、判分；链接拿去打做题页的载入
      接口，出的正是那一课的题
  三、找不到课文：退到按等级考点（#做题?level=N4&kind=接续），载入接口接得住；
      等级考点都没有就是不带参数的做题页
  四、贴答案求判：也走出题这一路，说明判对错去做题页，学习记录不动
  五、意图 JSON 坏了 / intent 不认识 / 空回复：按讲解兜底，不 500
  六、多轮：第二轮的提示词里带着第一轮的问和答
  七、讲解时提示词里带着检索到的课文正文
  八、档位：判意图用「快」，回答用「平衡」
  九、不同学习者的对话互不串
  十、进页面只回 state 不推消息；空消息 400 不记；已有库补建表不碰学习记录
  十一、进度进上下文：讲解的提示词里有进度摘要——没答过题是「还没有作答记录」；
      用做题接口答三题（一对两错）后是对的数字和答错的点；别的学习者不串
  十二、「进度」意图：平衡档，提示词以进度为主，回复带读课文、做题链接
  十二之二、掌握得分：进度摘要里有在学点的得分（低的在前）；「进度」推荐先推
      得分低的点答错过的那课（不是最近答错的那课）；没有得分退回原来的顺序
  十三、「教材」意图：提示词里有课文目录（问 N4 只列 N4，不问等级列全部），
      问「有没有讲〜的课」附那一课的读课文
  十四、讲解附「读课文」（指向 lesson_find 命中的课）和「练一练」两个链接；
      links 存进库，/teacher/state 拉回来还在；老库补 links 列，旧链接照样还原
"""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import choice_key, client, import_graph, make_ws    # noqa: E402
from kg.__main__ import (BANK, ensure_new_columns, ensure_new_tables,  # noqa: E402
                          quiz_link, read_bank)
from tools import config                                       # noqa: E402
from tools.mock import MockClient                              # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


REPLY = "老师的回答"
# 学习者原话 → 意图判定回什么。不在表里的回一个讲解
INTENTS = {
    "てから怎么用": '{"intent":"讲解","keywords":["てから"],"level":"N5","kind":"","grade":"否"}',
    "给我出几道てから的题": '好的：\n```json\n{"intent":"出题","keywords":["てから"],"level":"","kind":"","grade":"否"}\n```',
    "考考我N4的ために接续": '{"intent":"出题","keywords":["ために"],"level":"N4","kind":"接续","grade":"否"}',
    "随便出点题": '{"intent":"出题","keywords":[],"level":"","kind":"","grade":"否"}',
    "这题我选B对吗：彼は来る（　）だ A.よう B.そう": '{"intent":"出题","keywords":["ようだ"],"level":"","kind":"","grade":"是"}',
    "坏的 JSON 来一个": "这不是 JSON，判定坏了",
    "intent 乱写": '{"intent":"聊天吧","keywords":[]}',
    "空回复": "",
    "我学得怎么样": '{"intent":"进度","keywords":[],"level":"","kind":"","grade":"否"}',
    "N4还差什么": '{"intent":"进度","keywords":[],"level":"N4","kind":"","grade":"否"}',
    "N4有哪些课": '{"intent":"教材","keywords":[],"level":"N4","kind":"","grade":"否"}',
    "教材里有什么": '{"intent":"教材","keywords":[],"level":"","kind":"","grade":"否"}',
    "有没有讲てから的课": '{"intent":"教材","keywords":["てから"],"level":"","kind":"","grade":"否"}',
}
DEFAULT_INTENT = '{"intent":"讲解","keywords":[],"level":"","kind":"","grade":"否"}'


def handler(prompt, system):
    if "意图分类器" in (system or ""):
        said = prompt.split("学习者的消息：")[-1].strip()
        return INTENTS.get(said, DEFAULT_INTENT)
    return REPLY


def main():
    ws = make_ws(Path(tempfile.mkdtemp(prefix="teacher_chat_")))
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

    def send(text, learner=None):
        form = {"content": text}
        if learner:
            form["learner"] = learner
        mock.calls.clear()
        r = c.post("/teacher/send", json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    def rows(sql, *args):
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        try:
            return [dict(x) for x in con.execute(sql, args)]
        finally:
            con.close()

    def chats(learner="me"):
        return rows("SELECT * FROM chat_message WHERE learner = ? ORDER BY id", learner)

    def reply(body):
        m = body.get("messages") or []
        return m[-1] if m else {}

    def calls(tier):
        return [x for x in mock.calls if x.get("tier") == tier]

    def link_of(code):
        # quiz_link 给的是整个地址（http://…/#做题?lesson=…），站内链接是 # 往后那段
        full = quiz_link(code, "http://x")
        return full[full.index("#"):]

    teru = rows("SELECT code, title, explanation FROM lesson WHERE title LIKE '%てから%'")[0]
    teru_n = rows("SELECT count(*) n FROM question WHERE lesson = ?", teru["code"])[0]["n"]

    print("一、对照：讲解")
    st, body = send("てから怎么用")
    m = reply(body)
    check(st == 200 and m.get("text") == REPLY and m.get("who") == "老师",
          f"回了老师的话：{st} {m}")
    got = chats()
    check([(x["role"], x["content"]) for x in got] == [("learner", "てから怎么用"), ("teacher", REPLY)],
          f"两条对话记录进库：{[(x['role'], x['content'][:20]) for x in got]}")
    check(all(x["intent"] == "讲解" for x in got), "意图记成讲解")
    check(teru_n > 0 and m.get("link") == link_of(teru["code"]) and "练一练" in m.get("link_text", ""),
          f"参考的课文有题，回答下面附了做题链接：{m.get('link')} {m.get('link_text')}")
    check(got[1]["link"] == m.get("link") and got[1]["lesson"] == teru["code"],
          "老师那条记着链接和课文编号")
    check(len(calls("快")) == 1 and len(calls("平衡")) == 1, "调了两次模型：判意图一次、回答一次")

    print("二、出题意图：给链接，不出题不判分")
    n_attempt = rows("SELECT count(*) n FROM attempt")[0]["n"]
    st, body = send("给我出几道てから的题")
    m = reply(body)
    check(st == 200, f"200：{st} {body.get('error')}")
    check(m.get("link") == link_of(teru["code"]),
          f"链接是 #做题?lesson={teru['code']}，跟 quiz_link 一个写法：{m.get('link')}")
    check(unquote(m["link"]) == f"#做题?lesson={teru['code']}", f"解码后：{unquote(m['link'])}")
    check(teru["title"] in m.get("text", "") and "做题页" in m.get("text", ""),
          f"说了是哪一课、去做题页：{m.get('text')}")
    check(len(mock.calls) == 1 and calls("快"),
          "只调了一次模型（判意图）——没让模型在对话里出题")
    stems = rows("SELECT stem FROM question WHERE lesson = ?", teru["code"])
    check(not any(s["stem"].split("\n")[0] in m.get("text", "") for s in stems),
          "回复里没有这一课的题干")
    check(rows("SELECT count(*) n FROM attempt")[0]["n"] == n_attempt
          and not rows("SELECT * FROM quiz_state"), "学习记录、做题进度都没动（没判分）")
    check(chats()[-1]["intent"] == "出题", "意图记成出题")
    lesson = unquote(m["link"]).split("lesson=")[1]
    r = c.post("/quiz/lesson", json={"form": {"lesson": lesson}})
    cur = rows("SELECT q.lesson FROM quiz_state s JOIN question q ON q.code = s.current"
               " WHERE s.learner = 'me'")
    check(r.status_code == 200 and cur and cur[0]["lesson"] == teru["code"],
          f"链接拿去打做题页的载入接口：出的是这一课的题 {r.status_code} {cur}")

    print("三、找不到课文：退到等级考点，再退到做题页")
    st, body = send("考考我N4的ために接续")
    m = reply(body)
    check(st == 200 and unquote(m.get("link", "")) == "#做题?level=N4&kind=接续",
          f"没有 ために 的课：按 N4・接续 {unquote(m.get('link', ''))}")
    check("没找到" in m.get("text", "") and "N4・接续" in m.get("text", ""),
          f"说明了找不到课文、按什么出：{m.get('text')}")
    r = c.post("/quiz/lesson", json={"form": {"level": "N4", "kind": "接续"}})
    q = rows("SELECT q.level, q.kind, s.pick_level, s.pick_kind FROM quiz_state s"
             " JOIN question q ON q.code = s.current WHERE s.learner = 'me'")
    check(r.status_code == 200 and q and q[0]["level"] == "N4" and q[0]["kind"] == "接续",
          f"做题页的载入接口接得住 level/kind：{r.status_code} {q}")
    check((r.get_json() or {}).get("form") == {"pick_level": "N4", "pick_kind": "接续"},
          f"顶栏填成 N4・接续：{(r.get_json() or {}).get('form')}")
    st, body = send("随便出点题")
    m = reply(body)
    check(st == 200 and unquote(m.get("link", "")) == "#做题" and "打开做题页" == m.get("link_text"),
          f"等级考点都没有：不带参数的做题页 {unquote(m.get('link', ''))}")
    check("没找到对应的课文" in m.get("text", ""), "并说明了找不到")

    print("四、贴答案求判：引导去做题页")
    n_attempt = rows("SELECT count(*) n FROM attempt")[0]["n"]
    st, body = send("这题我选B对吗：彼は来る（　）だ A.よう B.そう")
    m = reply(body)
    check(st == 200 and "判对错" in m.get("text", "") and "做题页" in m.get("text", ""),
          f"说了判对错去做题页：{m.get('text')}")
    check(m.get("link", "").startswith("#%E5%81%9A%E9%A2%98"), f"给了做题页链接：{m.get('link')}")
    check(len(mock.calls) == 1, "只判了意图，没调回答模型")
    check(not any(w in m.get("text", "") for w in ("答对", "答错", "选对", "选错", "B是对", "B 是对", "不对")),
          "回复里没有替学习者判对错")
    check(rows("SELECT count(*) n FROM attempt")[0]["n"] == n_attempt, "学习记录没动")

    print("五、意图判定坏了：按讲解兜底")
    for said in ("坏的 JSON 来一个", "intent 乱写", "空回复"):
        st, body = send(said)
        m = reply(body)
        check(st == 200 and m.get("text") == REPLY and chats()[-1]["intent"] == "讲解"
              and len(calls("平衡")) == 1,
              f"「{said}」：200，按讲解回答 {st} {body.get('error') or ''}")

    print("六、多轮")
    st, _ = send("第一轮：てから和たあとで", learner="multi")
    first_reply = chats("multi")[-1]["content"]
    st, _ = send("那第二轮呢", learner="multi")
    p = calls("平衡")[0]["prompt"]
    check("第一轮：てから和たあとで" in p and first_reply in p and "那第二轮呢" in p,
          "第二轮的提示词里有第一轮的问和答、也有这一句")
    check(p.index("第一轮：てから和たあとで") < p.index("那第二轮呢"), "旧的在前")

    print("七、讲解带课文正文")
    send("てから怎么用", learner="ref")
    p = calls("平衡")[0]["prompt"]
    check(teru["explanation"] in p and teru["title"] in p,
          f"提示词里有《{teru['title']}》的讲解正文")
    send("今天天气不错", learner="ref")
    p = calls("平衡")[0]["prompt"]
    check("没找到相关课文" in p, "找不到课文时提示词里说明了")

    print("八、模型档位")
    send("てから怎么用", learner="tier")
    fast, mid = calls("快"), calls("平衡")
    want_fast, want_mid = str(config.resolve_model("快")), str(config.resolve_model("平衡"))
    check(len(fast) == 1 and fast[0]["model"] == want_fast and "意图分类器" in (fast[0]["system"] or ""),
          f"判意图用「快」档：{fast[0]['model'] if fast else None}（期望 {want_fast}）")
    check(len(mid) == 1 and mid[0]["model"] == want_mid and "日语老师" in (mid[0]["system"] or ""),
          f"回答用「平衡」档：{mid[0]['model'] if mid else None}（期望 {want_mid}）")
    check(len(mock.calls) == 2, "没有别的模型调用")

    print("九、不同学习者互不串")
    send("我是甲：ように怎么用", learner="甲")
    send("我是乙：のに怎么用", learner="乙")
    send("乙的第二句", learner="乙")
    p = calls("平衡")[0]["prompt"]
    check("我是乙" in p and "我是甲" not in p, "乙的第二轮提示词里只有乙自己的对话")
    a = [x["content"] for x in chats("甲")]
    b = [x["content"] for x in chats("乙")]
    check(len(a) == 2 and len(b) == 4 and not any("乙" in x for x in a),
          f"库里各记各的：甲 {len(a)} 条、乙 {len(b)} 条")
    r = c.post("/teacher/state", json={"form": {"learner": "甲"}}).get_json() or {}
    talk = (r.get("state") or {}).get("talk") or []
    check([x["text"] for x in talk] == a and all("乙" not in x["text"] for x in talk),
          "甲进页面只看到自己的")

    READ = "#%E6%95%99%E6%9D%90?lesson="     # 教材页读一课（界面名编过码）
    QUIZ = "#%E5%81%9A%E9%A2%98"               # 做题页

    shown = {}      # 最近一次出题的题卡：选项打乱过，按它找界面上的字母

    def answer(learner, right):
        """用做题页的接口答当前这道：right=True 交答案，否则交一个错的。答完点下一题。"""
        cur = rows("SELECT q.code, q.qtype, q.answer, q.stem FROM quiz_state s"
                   " JOIN question q ON q.code = s.current WHERE s.learner = ?", learner)[0]
        if cur["qtype"] == "选择":
            val = choice_key(shown[learner], cur["stem"], cur["answer"], right)
        else:
            val = cur["answer"] if right else "わざと間違える"
        key = "choice" if cur["qtype"] == "选择" else "given"
        r = c.post("/quiz/answer", json={"form": {"learner": learner, key: val}})
        assert r.status_code == 200, r.get_json()
        r = c.post("/quiz/next", json={"form": {"learner": learner}})
        shown[learner] = ((r.get_json() or {}).get("state") or {}).get("card") or {}

    print("十一、进度进上下文")
    total = rows("SELECT count(*) n FROM node")[0]["n"]
    send("てから怎么用", learner="p1")
    p = calls("平衡")[0]["prompt"]
    check("还没有作答记录" in p and f"已掌握 0 / 总知识点 {total}" in p,
          "没答过题：讲解提示词里有「还没有作答记录」和已掌握 0 / 总数")
    check("累计答题" not in p and "最近答错" not in p, "没答过题时不列答题数、答错（免得模型从「无」里编）")
    check("现在能学" in p, "列了现在能学的点")
    r = c.post("/quiz/lesson", json={"form": {"learner": "p1", "lesson": teru["code"]}})
    check(r.status_code == 200, f"做题页按《{teru['title']}》出题：{r.status_code}")
    shown["p1"] = ((r.get_json() or {}).get("state") or {}).get("card") or {}
    answer("p1", True)
    answer("p1", False)
    answer("p1", False)
    att = rows("SELECT correct FROM attempt WHERE learner = 'p1' ORDER BY id")
    check([x["correct"] for x in att] == [1, 0, 0], f"学习记录是一对两错：{att}")
    wrong = rows("SELECT DISTINCT coalesce(n.label, a.point) AS pl, coalesce(i.label, '') AS il"
                 " FROM attempt a LEFT JOIN node n ON n.code = a.point"
                 " LEFT JOIN question q ON q.code = a.item LEFT JOIN item i ON i.code = q.item"
                 " WHERE a.learner = 'p1' AND a.correct = 0")
    doing = rows("SELECT n.label, m.right, m.total FROM mastery m JOIN node n ON n.code = m.point"
                 " WHERE m.learner = 'p1'")
    send("てから怎么用", learner="p1")
    p = calls("平衡")[0]["prompt"]
    check("累计答题 3，答对 1，正确率 33%" in p, "提示词里是累计答题 3、答对 1、正确率 33%")
    check("还没有作答记录" not in p, "有记录了就不再说「还没有作答记录」")
    check(all(f"{w['pl']}·{w['il']}" in p if w["il"] else w["pl"] in p for w in wrong),
          f"最近答错的点（知识点·条目）在提示词里：{[(w['pl'], w['il']) for w in wrong]}")
    check(all(f"{d['label']} {d['right']}/{d['total']}" in p for d in doing),
          f"在学的点和答对/答题：{[(d['label'], d['right'], d['total']) for d in doing]}")
    block = p.split("学习进度")[1].split("】")[0]
    check(len(block) <= 820, f"进度摘要控制在 800 字以内：{len(block)} 字")
    send("てから怎么用", learner="p2")
    p = calls("平衡")[0]["prompt"]
    check("还没有作答记录" in p and "累计答题 3" not in p, "别的学习者（p2）的提示词里没有 p1 的进度")
    send("坏的 JSON 来一个", learner="p1")
    p = calls("平衡")[0]["prompt"]
    check(chats("p1")[-1]["intent"] == "讲解" and "累计答题 3" in p, "意图 JSON 坏了按讲解兜底，进度照样带上")

    print("十二、「进度」意图")
    st, body = send("我学得怎么样", learner="p1")
    m = reply(body)
    check(st == 200 and m.get("text") == REPLY and (body.get("state") or {}).get("intent") == "进度",
          f"判成进度，回了老师的话：{st} {(body.get('state') or {}).get('intent')}")
    check(chats("p1")[-1]["intent"] == "进度", "库里意图记成进度")
    mid = calls("平衡")
    check(len(calls("快")) == 1 and len(mid) == 1 and mid[0]["model"] == str(config.resolve_model("平衡")),
          f"判意图快档一次，回答平衡档一次：{[x.get('tier') for x in mock.calls]}")
    p = mid[0]["prompt"]
    check(p.startswith("下面是这个学生在网站上的学习进度") and "以学习进度为主" in p,
          "提示词以进度为主（开头就是进度，要求以进度为主回答）")
    check("累计答题 3，答对 1，正确率 33%" in p and "按进度推荐的下一课" in p, "提示词里有进度数字和推荐的课")
    check("例句：" not in p and teru["explanation"] not in p, "不塞课文正文")
    check("不要编造进度里没有的数据" in (mid[0]["system"] or ""), "系统提示词说了不编造进度里没有的数据")
    links = m.get("links") or []
    hrefs = [x.get("href", "") for x in links]
    check(len(links) == 2 and hrefs[0].startswith(READ) and hrefs[1].startswith(QUIZ),
          f"回复带两个链接：读课文、做题 {[(x.get('text'), unquote(x.get('href', ''))) for x in links]}")
    pick = hrefs[0][len(READ):] if hrefs and hrefs[0].startswith(READ) else ""
    wrong_lessons = {x["lesson"] for x in rows(
        "SELECT q.lesson FROM attempt a JOIN question q ON q.code = a.item"
        " WHERE a.learner = 'p1' AND a.correct = 0")}
    check(pick in wrong_lessons and pick in p, f"推荐的是答错过的那一课（复习），提示词里写了它：{pick}")
    check(hrefs[1:] and hrefs[1] == f"{QUIZ}?lesson={pick}" and "练这一课" in links[1].get("text", ""),
          f"「练这一课」指向同一课：{hrefs[1:]}")
    check(m.get("link") == hrefs[1] if len(hrefs) > 1 else False, "旧的 link 字段给的是做题链接（兼容）")
    st, body = send("我学得怎么样", learner="p3")
    m = reply(body)
    p = calls("平衡")[0]["prompt"]
    hrefs = [x.get("href", "") for x in m.get("links") or []]
    first = rows("SELECT l.code FROM lesson l WHERE l.level = 'N5' AND EXISTS"
                 " (SELECT 1 FROM question q WHERE q.lesson = l.code) ORDER BY l.code")[0]["code"]
    check("还没有作答记录" in p and hrefs[:1] == [READ + first],
          f"没答过题的学习者：进度说还没有记录，推荐 N5 有题的第一课 {first}：{hrefs}")
    st, body = send("N4还差什么", learner="p1")
    m = reply(body)
    p = calls("平衡")[0]["prompt"]
    check("N4 还没掌握的知识点" in p, "问 N4 还差什么：进度摘要里多一行 N4 还没掌握的知识点")
    lv = rows("SELECT level FROM lesson WHERE code = ?",
              (m.get("links") or [{}])[0].get("href", "")[len(READ):])
    check(lv and lv[0]["level"] == "N4", f"推荐的课在 N4 里：{lv}")

    print("十二之二、掌握得分优先低分点")
    qs = rows("SELECT i.point, q.code, q.lesson FROM question q JOIN item i ON i.code = q.item"
              " WHERE q.lesson IS NOT NULL AND q.difficulty = '基础' ORDER BY i.point, q.code")
    lessons = {}
    for x in qs:
        lessons.setdefault(x["point"], set()).add(x["lesson"])
    pts = list(lessons)
    pb = pts[0]
    pc = next(x for x in pts[1:] if not (lessons[x] & lessons[pb]))
    qb = next(x for x in qs if x["point"] == pb)
    qc = next(x for x in qs if x["point"] == pc)
    lb, lc = (rows("SELECT label FROM node WHERE code = ?", x)[0]["label"] for x in (pb, pc))

    def learn(who, q, ok):
        r = c.post("/learn/answer", json={"form": {"learner": who, "point": q["point"],
                                                  "item": q["code"], "correct": str(ok)}})
        assert r.status_code == 200, r.get_json()

    # B 错一道（最早），C 对四道再错一道（最近答错的是 C）
    learn("lowp", qb, 0)
    for _ in range(4):
        learn("lowp", qc, 1)
    learn("lowp", qc, 0)
    sb, sc_ = (rows("SELECT value FROM score WHERE learner = 'lowp' AND point = ? ORDER BY id DESC LIMIT 1",
                    x)[0]["value"] for x in (pb, pc))
    check(sb < sc_ < 80, f"B 得分 {sb} < C 得分 {sc_} < 80")
    st, body = send("我学得怎么样", learner="lowp")
    m = reply(body)
    p = calls("平衡")[0]["prompt"]
    check(f"在学知识点的掌握得分（0–100，按做题情况算，低的在前）：{lb} {sb}；{lc} {sc_}" in p,
          f"进度摘要里有在学点的得分，低的在前：{p[p.find('掌握得分'):][:80]!r}")
    pick = ((m.get("links") or [{}])[0].get("href") or "")[len(READ):]
    check(pick == qb["lesson"] and f"「{lb}」掌握得分 {sb}" in p,
          f"推荐得分最低的点（B）答错过的那课 {qb['lesson']}，不是最近答错的 C：{pick}")
    # 对照：直接写进流水、没有得分的人，还是按最近答错的推（原来的顺序）
    con = sqlite3.connect(db)
    for q in (qb, qc):
        con.execute("INSERT INTO attempt(learner, point, item, correct) VALUES ('nos', ?, ?, 0)",
                    (q["point"], q["code"]))
    con.commit()
    con.close()
    st, body = send("我学得怎么样", learner="nos")
    m = reply(body)
    p = calls("平衡")[0]["prompt"]
    pick = ((m.get("links") or [{}])[0].get("href") or "")[len(READ):]
    check(pick == qc["lesson"] and "在学知识点的掌握得分" not in p,
          f"没有得分：退回最近答错的那课 {qc['lesson']}，摘要里不写得分：{pick}")

    print("十三、「教材」意图")
    st, body = send("N4有哪些课", learner="t1")
    m = reply(body)
    check(st == 200 and chats("t1")[-1]["intent"] == "教材", f"判成教材：{st}")
    mid = calls("平衡")
    p = mid[0]["prompt"] if mid else ""
    n4 = rows("SELECT title FROM lesson WHERE level = 'N4' ORDER BY code")
    check(len(mid) == 1 and f"N4（{len(n4)} 课）：" in p and all(x["title"] in p for x in n4),
          f"平衡档；提示词里有 N4 的课文目录（{len(n4)} 课，标题都在）")
    check("N5（" not in p and "N3（" not in p, "只列了 N4 这一级")
    check("课文目录" in p and "目录里没有的课不要编" in p, "让老师按目录回答、不编课")
    check(any(x.get("href") == "#%E6%95%99%E6%9D%90" for x in m.get("links") or []),
          f"附了「打开教材」：{[x.get('text') for x in m.get('links') or []]}")
    send("教材里有什么", learner="t1")
    p = calls("平衡")[0]["prompt"]
    cat = p.split("课文目录（按等级分组，只有标题）：【")[1].split("】")[0]
    check(all(f"{lv}（" in cat for lv in ("N5", "N4", "N3", "N2", "N1")) and len(cat) <= 1502,
          f"不问等级：按等级分组列全部，控制长度（{len(cat)} 字）")
    check(cat.index("N5（") < cat.index("N4（") < cat.index("N1（"), "N5 在前")
    st, body = send("有没有讲てから的课", learner="t1")
    m = reply(body)
    p = calls("平衡")[0]["prompt"]
    hrefs = [x.get("href") for x in m.get("links") or []]
    check(hrefs and hrefs[0] == READ + teru["code"] and f"课文 {teru['code']}" in p,
          f"问有没有讲 てから 的课：提示词里有那一课，第一个链接读它 {[unquote(h) for h in hrefs]}")

    print("十四、讲解的多个链接、存库、拉回来")
    st, body = send("てから怎么用", learner="lk")
    m = reply(body)
    links = m.get("links") or []
    check(len(links) == 2 and links[0].get("href") == READ + teru["code"]
          and links[0].get("text") == f"读课文：《{teru['title']}》",
          f"第一个链接是读课文，指向 lesson_find 命中的《{teru['title']}》：{links[:1]}")
    check(links[1:] and links[1].get("href") == link_of(teru["code"]) and "练一练" in links[1].get("text", ""),
          f"第二个是练一练：{links[1:]}")
    check(m.get("link") == link_of(teru["code"]), "旧的 link 字段照旧（做题链接）")
    saved = chats("lk")[-1]
    check(json.loads(saved["links"] or "[]") == links, f"links 原样存进 chat_message.links：{saved['links']}")
    check(chats("lk")[0]["links"] is None, "学习者那条不记 links")
    r = c.post("/teacher/state", json={"form": {"learner": "lk"}}).get_json() or {}
    talk = (r.get("state") or {}).get("talk") or []
    check(talk and talk[-1].get("links") == links and talk[0].get("links") == [],
          f"/teacher/state 拉回来链接还是列表、内容一样：{talk[-1].get('links') if talk else None}")
    st, body = send("给我出几道てから的题", learner="lk")
    m = reply(body)
    hrefs = [x.get("href") for x in m.get("links") or []]
    check(hrefs == [link_of(teru["code"]), READ + teru["code"]],
          f"出题：去做题 + 读课文两个链接 {[unquote(h) for h in hrefs]}")

    print("十、进页面、空消息、补建表")
    r = c.post("/teacher/state", json={"form": {}}).get_json() or {}
    talk = (r.get("state") or {}).get("talk") or []
    check("messages" not in r, "进页面只回 state，不推消息")
    check((r.get("state") or {}).get("mode") == "mock", "测试用的是模拟模式，state.mode == mock（页面据此显示提示）")
    check(talk and talk[0] == {"who": "你", "text": "てから怎么用", "kind": "user", "link": "", "link_text": "",
                               "links": []},
          f"学习者那条跟前端回显一样（你 / user）：{talk[:1]}")
    check(talk[1]["who"] == "老师" and talk[1]["link"] == link_of(teru["code"]),
          "老师那条带着链接，重新进页面还能点")
    before = len(chats())
    st, body = send("")
    check(st == 400 and len(chats()) == before and not mock.calls, f"空消息 400、不记、不调模型：{st}")
    st, body = send("   ")
    check(st == 400 and len(chats()) == before, f"只有空格也算空：{st}")

    # 已有的库（没有 chat_message）：补建这张表，学习记录原样。先答一道
    # 题，库里有一条真学习记录
    c.post("/quiz/answer", json={"form": {"choice": "A", "given": "x"}})
    con = sqlite3.connect(db)
    con.execute("DROP TABLE chat_message")
    n_att = con.execute("SELECT count(*) FROM attempt").fetchone()[0]
    con.commit()
    con.close()
    made = ensure_new_tables(db, ws / "entities")
    check(made == ["chat_message"], f"补建了 chat_message：{made}")
    check(rows("SELECT count(*) n FROM attempt")[0]["n"] == n_att and n_att > 0,
          f"学习记录没动（attempt {n_att} 条）")
    check(ensure_new_tables(db, ws / "entities") == [], "再跑一次什么都不建")

    # 老库的 chat_message 没有 links 列：补列（ALTER TABLE ADD COLUMN），不重建，
    # 原有的行还在；只有 link 的旧记录拉回来也是 links 列表
    con = sqlite3.connect(db)
    con.execute("DROP TABLE chat_message")
    con.execute("CREATE TABLE chat_message (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " learner VARCHAR(255) NOT NULL, role VARCHAR(255) NOT NULL,"
                " content VARCHAR(255) NOT NULL, intent VARCHAR(255), lesson VARCHAR(255),"
                " link VARCHAR(255), link_text VARCHAR(255),"
                " created VARCHAR(255) NOT NULL DEFAULT (datetime('now','localtime')))")
    con.execute("INSERT INTO chat_message(learner, role, content, intent, link, link_text)"
                " VALUES('old', 'teacher', '旧的一条', '出题', '#x', '旧链接')")
    con.commit()
    con.close()
    check(ensure_new_tables(db, ws / "entities") == [], "老库：表在，不补建")
    added = ensure_new_columns(db, ws / "entities")
    check(added == ["chat_message.links"], f"补了 links 列：{added}")
    check(rows("SELECT content FROM chat_message WHERE learner = 'old'") == [{"content": "旧的一条"}],
          "原有的行还在（没重建）")
    check(ensure_new_columns(db, ws / "entities") == [], "再跑一次什么都不补")
    r = c.post("/teacher/state", json={"form": {"learner": "old"}}).get_json() or {}
    talk = (r.get("state") or {}).get("talk") or []
    check(talk and talk[0].get("links") == [{"href": "#x", "text": "旧链接"}] and talk[0].get("link") == "#x",
          f"旧记录的 link 还原成 links 列表：{talk[:1]}")
    st, body = send("てから怎么用", learner="old")
    check(st == 200 and json.loads(chats("old")[-1]["links"] or "[]") == (reply(body).get("links") or [None]),
          "补列后新对话的 links 照常存")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
