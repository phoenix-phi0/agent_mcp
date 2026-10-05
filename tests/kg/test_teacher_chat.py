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
from kg.__main__ import BANK, ensure_new_tables, quiz_link, read_bank  # noqa: E402
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

    print("十、进页面、空消息、补建表")
    r = c.post("/teacher/state", json={"form": {}}).get_json() or {}
    talk = (r.get("state") or {}).get("talk") or []
    check("messages" not in r, "进页面只回 state，不推消息")
    check((r.get("state") or {}).get("mode") == "mock", "测试用的是模拟模式，state.mode == mock（页面据此显示提示）")
    check(talk and talk[0] == {"who": "你", "text": "てから怎么用", "kind": "user", "link": "", "link_text": ""},
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

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
