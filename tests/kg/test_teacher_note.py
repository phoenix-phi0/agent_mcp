# -*- coding: utf-8 -*-
"""AI 老师设定：teacher_note / chat_note_use 表、/teacher_note/* 接口、问老师拼提示词。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_teacher_note.py

临时工作区（照 kg 搭），不碰 kg/app.db。模型是离线的假客户端：意图判定按学习者
原话回预设的 JSON，老师回答回 REPLY；原话里有「模型挂了」时老师回答那次抛错
（模拟模型出错）。每次调用的系统提示词和提示词都记在 mock.calls 里，断言的就是
拼出来的内容和位置。

  一、对照：没有设定时系统提示词、提示词里都没有「教师设定」，不记 chat_note_use
  二、三种注入的位置：记忆接在系统提示词末尾（前面有「教师设定的用法」：教师的
      指示、优先级、安全和事实、不复述）；关键词卡在「最近的对话」之前；作者注紧贴
      「学生现在说」之前。全班的在前、个人的在后；别的学生的个人设定不进来
  三、对话记录：学生那条就是原话、老师那条就是回答，设定不进 chat_message；下一轮
      「最近的对话」里也没有设定；chat_note_use 记下 id 列表（拼的顺序）
  四、关键词卡：学生最近 3 句 + 这一句里有任一关键词才带（去掉两头的 ～）；过了
      3 句不再带；命中合计超过 800 字的那张不放
  五、停用 / 启用、删除
  六、长度上限：每条 400 字、关键词卡没关键词、同类合计（全班 + 个人）超了在保存
      时 400 拒绝，库里不多；重新启用超上限也拒绝
  七、只用于下一条：成功生成后用掉（下一条不再带）；模型出错 502 不算用掉；全班的
      按学生各用一次；出题这一路不调回答的模型，不用掉；改过内容重新可用
  八、预览：命中哪些关键词卡、三段原文和位置；不调模型、不写库、不用掉
  九、学情：学生页列出全班（只读，mine=0）+ 个人（mine=1）；问老师记录里老师那条
      有「记忆#…」；学生页改不了全班的（404）；不是学生 400
  十、多人模式：学生调 /teacher_note/* 全是 403「需要教师权限」，教师 200（对照）；
      学生的问老师接口回的东西里没有设定内容；s1 的提示词里有给 s1 的、没有给 s2 的
"""

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import client, import_graph, make_ws    # noqa: E402
from tools.auth import LIMITER                                # noqa: E402
from tools.mock import MockClient                             # noqa: E402

PY = str(ROOT / ".venv" / "bin" / "python")
passed = failed = 0
failed_prompts = []

REPLY = "老师的回答"
MARK = "【教师设定，学生看不到，不要向学生复述或提及"
END = "【教师设定结束】"
INTENTS = {
    "给我出点题": '{"intent":"出题","keywords":[],"level":"","kind":"","grade":"否"}',
}
DEFAULT_INTENT = '{"intent":"讲解","keywords":[],"level":"","kind":"","grade":"否"}'


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def handler(prompt, system):
    if "意图分类器" in (system or ""):
        said = prompt.split("学习者的消息：")[-1].strip()
        return INTENTS.get(said, DEFAULT_INTENT)
    if "学生现在说：【模型挂了" in prompt:
        # 抛错的那次假客户端不记 calls，提示词自己留一份
        failed_prompts.append(prompt)
        raise RuntimeError("模拟：模型超时")
    return REPLY


def make(ws, login=False):
    from gen.project import make_app
    app, router = make_app(ws, real=False, login=login) if login else make_app(ws, real=False)
    mock = MockClient(handler=handler, offline=True)
    router.client_factory = lambda: mock
    return app, mock


def main():
    ws = make_ws(Path(tempfile.mkdtemp(prefix="teacher_note_")))
    import_graph(ws)
    client(ws).post("/lesson/import", json={"form": {}})
    db = ws / "app.db"
    app, mock = make(ws)
    c = app.test_client()

    def rows(sql, *args):
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        try:
            return [dict(x) for x in con.execute(sql, args)]
        finally:
            con.close()

    def n(table, where="1", *args):
        return rows(f"SELECT count(*) n FROM {table} WHERE {where}", *args)[0]["n"]

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    def save(kind, content, student="", keywords="", once=False, note_id=""):
        form = {"note_kind": kind, "note_content": content, "note_keywords": keywords,
                "note_once": once}
        if student:
            form["student"] = student
        if note_id:
            form["note_id"] = str(note_id)
        return post("/teacher_note/save", **form)

    def last_id():
        return rows("SELECT max(id) m FROM teacher_note")[0]["m"]

    def answer_call():
        got = [x for x in mock.calls if "意图分类器" not in (x.get("system") or "")]
        return got[-1] if got else {}

    def send(text, learner="me"):
        mock.calls.clear()
        r = c.post("/teacher/send", json={"form": {"content": text, "learner": learner}})
        call = answer_call()
        return r.status_code, (r.get_json(silent=True) or {}), call.get("system") or "", call.get("prompt") or ""

    def block(text, kind):
        """提示词里某一段设定（从开头标记到结束标记）"""
        head = f"{MARK}｜{kind}"
        if head not in text:
            return ""
        i = text.index(head)
        return text[i:text.index(END, i) + len(END)]

    # ------------------------------------------------------------------
    print("一、对照：没有设定")
    st, body, system, prompt = send("は和が有什么区别")
    check(st == 200 and (body.get("messages") or [{}])[-1].get("text") == REPLY, f"回了老师的话：{st}")
    check(system and "教师设定" not in system and "教师设定" not in prompt,
          "系统提示词、提示词里都没有「教师设定」")
    check(system.endswith("你不要自己写网址。"), "系统提示词跟原来一样结尾")
    check(n("chat_note_use") == 0, "没记 chat_note_use")

    # ------------------------------------------------------------------
    print("二、三种注入的位置")
    st, b = post("/teacher_note/home")
    check(st == 200 and (b.get("lists") or {}).get("class_notes") == [], f"设定页进来：空列表 {st}")
    check(any(x.get("value") == "me" for x in (b.get("lists") or {}).get("note_students", [])),
          "预览的学生下拉里有 me（有问老师记录的学习者）")
    save("记忆", "全班这周重点是て形。")
    m_class = last_id()
    save("记忆", "这个学生是工程背景，多用技术例子。", student="me")
    m_me = last_id()
    save("记忆", "这是给别人的记忆。", student="other")
    check(n("teacher_note") == 2, "给不存在的学生（other）存不进去")
    st, b = save("作者注", "接下来回答尽量简短，最后出一道小题。")
    a_class = last_id()
    check(st == 200 and "设定已保存" in str(b.get("messages")), f"作者注存了：{st}")
    save("作者注", "多用敬语。", student="me")
    a_me = last_id()
    save("关键词卡", "提到ばかり时，强调和たばかり的区别。", keywords="～ばかり，たばかり")
    k_class = last_id()
    save("关键词卡", "提到てから时，提醒て形的接续。", student="me", keywords="てから")
    k_me = last_id()
    check(rows("SELECT note_keywords FROM teacher_note WHERE id = ?", k_class)[0]["note_keywords"] == "～ばかり,たばかり",
          "关键词规整成半角逗号分隔")
    # 有人（s2）也有问老师记录，给 s2 的个人设定不该进 me 的提示词
    send("你好", learner="s2")
    save("记忆", "这是s2的记忆。", student="s2")

    st, body, system, prompt = send("～ばかり怎么用")
    check(st == 200, f"200：{st} {body.get('error')}")
    rule_at = system.find("【教师设定的用法】")
    mem = block(system, "记忆")
    check(rule_at > 0 and "教师" in system[rule_at:] and "优先级高于" in system and "安全" in system
          and "事实" in system and "不要向学生复述" in system,
          "系统提示词里说明：教师的指示、优先级高于一般风格、不能违背安全和事实、不复述")
    check(system.index("你不要自己写网址。") < rule_at < system.index(mem) and system.endswith(END),
          "记忆在系统提示词末尾（原来的系统提示词 → 用法 → 记忆）")
    check(mem.index("全班这周重点是て形") < mem.index("工程背景") and "s2的记忆" not in system
          and "给别人的记忆" not in system,
          "记忆：全班的在前、个人的在后，别的学生的不进来")
    cards = block(prompt, "关键词卡")
    tail = block(prompt, "作者注")
    check("ばかり" in cards and "てから" not in cards, f"关键词卡：命中 ばかり 那张，没命中 てから 那张：{cards!r}")
    check(prompt.index(cards) < prompt.index("最近的对话"), "关键词卡在「最近的对话」之前")
    check(tail and prompt.index(tail) > prompt.index("最近的对话")
          and prompt[prompt.index(tail) + len(tail):].startswith("\n学生现在说：【～ばかり怎么用】"),
          f"作者注紧贴「学生现在说」之前：{prompt[prompt.index(tail) + len(tail) - 10:][:40]!r}")
    check(tail.index("尽量简短") < tail.index("多用敬语"), "作者注：全班的在前、个人的在后")
    check(prompt.count(MARK) == 2 and MARK not in prompt[prompt.index("学生现在说"):],
          "提示词里只有关键词卡、作者注两段，学生那句之后没有设定")

    # ------------------------------------------------------------------
    print("三、对话记录")
    got = rows("SELECT role, content FROM chat_message WHERE learner = 'me' ORDER BY id DESC LIMIT 2")
    check(got == [{"role": "teacher", "content": REPLY}, {"role": "learner", "content": "～ばかり怎么用"}],
          f"学生那条是原话、老师那条是回答：{got}")
    check(n("chat_message", "content LIKE '%教师设定%'") == 0, "chat_message 里没有设定内容")
    use = rows("SELECT * FROM chat_note_use WHERE learner = 'me' ORDER BY id")
    teacher_msg = rows("SELECT max(id) m FROM chat_message WHERE learner = 'me' AND role = 'teacher'")[0]["m"]
    want_ids = ",".join(str(x) for x in (m_class, m_me, a_class, a_me, k_class))
    check(len(use) == 1 and use[0]["note_ids"] == want_ids and use[0]["message_id"] == teacher_msg
          and use[0]["learner"] == "me",
          f"chat_note_use 记了老师那条的 id 和设定 id（拼的顺序）：{use} 应为 {want_ids}")
    st, body, system, prompt = send("那第二个呢")
    talk = prompt.split("最近的对话（旧的在前，接着这些往下聊）：【")[1].split("】" + "\n" + MARK)[0]
    check("～ばかり怎么用" in talk and "教师设定" not in talk and "尽量简短" not in talk,
          f"下一轮「最近的对话」里有上一轮的问答、没有设定：{talk[:80]!r}")
    st, b = post("/teacher/state")
    check("教师设定" not in str(b) and "尽量简短" not in str(b) and "工程背景" not in str(b),
          "学生的 /teacher/state 回的东西里没有设定")

    # ------------------------------------------------------------------
    print("四、关键词卡")
    check("ばかり" in block(prompt, "关键词卡"), "这一句没提，但最近几句提过 ばかり：照样带")
    for t in ("问题一", "问题二"):
        send(t)
    st, body, system, prompt = send("问题三")
    check(not block(prompt, "关键词卡") and "关键词卡" not in prompt,
          "过了 3 句（最近 3 句和这一句都没有关键词）：不带了，提示词里没有空的关键词卡段")
    st, body, system, prompt = send("てから和たら有什么区别")
    cards = block(prompt, "关键词卡")
    check("てから" in cards and "ばかり" not in cards, "提到 てから：带个人的那张")
    # 命中合计上限 800：再加三张 300 字的卡都命中「上限测试」
    big = []
    for i in range(3):
        save("关键词卡", f"第{i}张" + "长" * 300, keywords="上限测试")
        big.append(last_id())
    st, body, system, prompt = send("上限测试てから")
    cards = block(prompt, "关键词卡")
    check("第0张" in cards and "第1张" in cards and "第2张" not in cards and "てから" in cards,
          "命中合计超过 800 字：第三张 300 字的不放，后面个人的短卡照放")
    for i in big:
        post("/teacher_note/delete", note_id=str(i))
    check(n("teacher_note", "note_content LIKE '第%张%'") == 0, "删掉了三张长卡")

    # ------------------------------------------------------------------
    print("五、停用 / 启用")
    st, b = post("/teacher_note/disable", note_id=str(m_class))
    lst = {r["note_id"]: r for r in (b.get("lists") or {}).get("class_notes", [])}
    check(st == 200 and lst.get(m_class, {}).get("note_state") == "停用", f"停用：列表里状态是停用 {st}")
    st, body, system, prompt = send("停用以后")
    check("全班这周重点是て形" not in system and "工程背景" in system, "停用的全班记忆不带了，个人的照带")
    st, b = post("/teacher_note/enable", note_id=str(m_class))
    st, body, system, prompt = send("启用以后")
    check(st == 200 and "全班这周重点是て形" in system, "重新启用：又带上了")

    # ------------------------------------------------------------------
    print("六、长度上限")
    before = n("teacher_note")
    st, b = save("记忆", "长" * 401)
    check(st == 400 and "400 字" in b.get("error", ""), f"一条 401 字：400「{b.get('error')}」")
    st, b = save("关键词卡", "没有关键词的卡", keywords=" ，、 ")
    check(st == 400 and "关键词" in b.get("error", ""), f"关键词卡没关键词：400「{b.get('error')}」")
    st, b = save("关键词卡", "关键词太长", keywords="词" * 101)
    check(st == 400 and "100 字" in b.get("error", ""), f"关键词 101 字：400「{b.get('error')}」")
    # 记忆合计 1200：全班已有 10 字、me 个人 17 字、s2 个人 8 字。再加三条全班 395 字
    # → 10+1185+17 > 1200
    save("记忆", "甲" * 395)
    save("记忆", "乙" * 395)
    fill = last_id()
    st, b = save("记忆", "丙" * 395)
    check(st == 400 and "1200" in b.get("error", ""), f"全班 + me 个人的记忆合计超 1200：400「{b.get('error')}」")
    st, b = save("记忆", "丁" * 395, student="s2")
    check(st == 400 and "1200" in b.get("error", ""), f"给 s2 加个人的也超：400「{b.get('error')}」")
    check(n("teacher_note") == before + 2, "被拒的都没存进去")
    st, b = save("记忆", "短一点", note_id=fill)
    check(st == 200 and rows("SELECT note_content FROM teacher_note WHERE id = ?", fill)[0]["note_content"] == "短一点",
          f"改短了能存（修改不算自己两次）：{st}")
    post("/teacher_note/disable", note_id=str(fill))
    st, b = save("记忆", "戊" * 395)
    check(st == 200, f"停用的不算进合计：再加一条 395 字能存 {st} {b.get('error')}")
    st, b = save("记忆", "己" * 390, note_id=fill)
    st, b = post("/teacher_note/enable", note_id=str(fill))
    check(st == 400 and "1200" in b.get("error", "")
          and rows("SELECT note_enabled FROM teacher_note WHERE id = ?", fill)[0]["note_enabled"] == 0,
          f"重新启用会超上限：400，还是停用的「{b.get('error')}」")
    for i in [x["id"] for x in rows("SELECT id FROM teacher_note WHERE note_content GLOB '[甲乙丙丁戊己]*' OR id = ?", fill)]:
        post("/teacher_note/delete", note_id=str(i))

    # ------------------------------------------------------------------
    print("七、只用于下一条")
    save("作者注", "下一条先夸一句。", student="me", once=True)
    once_me = last_id()
    check(rows("SELECT note_once FROM teacher_note WHERE id = ?", once_me)[0]["note_once"] == 1, "存成只用于下一条")
    save("记忆", "记忆勾了也不算", once=True)
    check(rows("SELECT note_once FROM teacher_note WHERE id = ?", last_id())[0]["note_once"] == 0,
          "别的种类勾了「只用于下一条」存成 0")
    post("/teacher_note/delete", note_id=str(last_id()))
    n_chat = n("chat_message")
    st, body, system, prompt = send("模型挂了一次")
    check(st == 502 and failed_prompts and "下一条先夸一句" in block(failed_prompts[-1], "作者注"),
          f"模型出错：502，那次的提示词里带着它 {st}")
    check(n("chat_message") == n_chat and not rows("SELECT * FROM chat_note_use WHERE instr(',' || note_ids || ',', ?)",
                                                   f",{once_me},"),
          "出错这轮不记对话、不记使用")
    st, b = post("/report/one", student="me")
    state = {r["note_id"]: r["note_state"] for r in (b.get("lists") or {}).get("student_notes", [])}
    check(state.get(once_me) == "只用于下一条·还没用", f"学生页上：还没用 {state.get(once_me)}")
    st, body, system, prompt = send("这次正常")
    check(st == 200 and "下一条先夸一句" in prompt, "失败不消耗：下一次成功的回复里还带着")
    st, body, system, prompt = send("再下一次")
    check(st == 200 and "下一条先夸一句" not in prompt and "多用敬语" in prompt, "用过了：不再带，别的作者注照带")
    st, b = post("/report/one", student="me")
    state = {r["note_id"]: r["note_state"] for r in (b.get("lists") or {}).get("student_notes", [])}
    check(state.get(once_me) == "只用于下一条·这个学生已用过", f"学生页上：已用过 {state.get(once_me)}")
    # 出题这一路不调回答的模型：不用掉
    save("作者注", "全班的一次性提醒。", once=True)
    once_class = last_id()
    st, body, system, prompt = send("给我出点题")
    check(st == 200 and not system and n("chat_note_use", "instr(',' || note_ids || ',', ?)", f",{once_class},") == 0,
          "出题：没调回答的模型，一次性的作者注没被用掉")
    st, body, system, prompt = send("讲讲吧")
    check("全班的一次性提醒" in prompt, "me 下一条讲解用上了全班的一次性作者注")
    st, body, system, prompt = send("讲讲吧2")
    check("全班的一次性提醒" not in prompt, "me 再下一条：不带了")
    st, body, system, prompt = send("我是s2", learner="s2")
    check("全班的一次性提醒" in prompt and "多用敬语" not in prompt, "全班的一次性作者注按学生算：s2 还能用一次")
    st, b = post("/teacher_note/home")
    state = {r["note_id"]: r["note_state"] for r in (b.get("lists") or {}).get("class_notes", [])}
    check(state.get(once_class) == "只用于下一条·已有 2 个学生用过", f"设定页：{state.get(once_class)}")
    save("作者注", "下一条先夸一句（改过）。", student="me", once=True, note_id=once_me)
    st, body, system, prompt = send("改过以后")
    check("下一条先夸一句（改过）" in prompt, "改过内容：重新可用一次")
    post("/teacher_note/delete", note_id=str(once_class))

    # ------------------------------------------------------------------
    print("八、预览")
    save("作者注", "预览用的一次性作者注。", student="me", once=True)
    once_prev = last_id()
    n_chat, n_use = n("chat_message"), n("chat_note_use")
    mock.calls.clear()
    st, b = post("/teacher_note/preview", preview_student="me", preview_message="たばかり和ばかり")
    pv = (b.get("state") or {}).get("preview") or {}
    hits = (b.get("lists") or {}).get("preview_hits") or []
    check(st == 200 and [h.get("note_id") for h in hits] == [str(k_class)] or [h.get("note_id") for h in hits] == [k_class],
          f"命中的关键词卡：{hits}")
    check(hits and hits[0].get("hit_keyword") == "ばかり" and hits[0].get("hit_placed") == "放进去了",
          f"命中的关键词、放进去了：{hits[:1]}")
    check("工程背景" in pv.get("system", "") and "ばかり" in pv.get("cards", "") and "预览用的一次性作者注" in pv.get("tail", ""),
          "三段原文：记忆、关键词卡、作者注")
    lay = pv.get("layout", "")
    check(lay.index("【系统提示词】") < lay.index("工程背景") < lay.index("【发给模型的提示词】")
          < lay.index(f"{MARK}｜关键词卡") < lay.index("最近的对话") < lay.index(f"{MARK}｜作者注")
          < lay.index("学生现在说：【たばかり和ばかり】"),
          "拼好的样子：记忆在系统提示词里，关键词卡在最近的对话之前，作者注紧贴学生那句之前")
    check(str(once_prev) in pv.get("ids", ""), f"用到的设定 id：{pv.get('ids')}")
    check(not mock.calls and n("chat_message") == n_chat and n("chat_note_use") == n_use, "不调模型、不写库")
    st, body, system, prompt = send("预览以后")
    check("预览用的一次性作者注" in prompt, "预览没用掉「只用于下一条」")
    st, b = post("/teacher_note/preview", preview_student="me", preview_message="没有关键词的话")
    check(st == 200 and (b.get("lists") or {}).get("preview_hits") == []
          and "没有命中" in ((b.get("state") or {}).get("preview") or {}).get("cards", ""), "没命中：空表、说明没有命中")
    st, b = post("/teacher_note/preview", preview_student="", preview_message="x")
    check(st == 400, f"没选学生 400：{b.get('error')}")

    # ------------------------------------------------------------------
    print("九、学情")
    st, b = post("/report/one", student="me")
    notes = (b.get("lists") or {}).get("student_notes") or []
    kinds = [(r["note_kind"], r["note_scope"]) for r in notes]
    check(("记忆", "全班") in kinds and ("记忆", "个人") in kinds
          and kinds.index(("记忆", "全班")) < kinds.index(("记忆", "个人"))
          and kinds.index(("作者注", "全班")) < kinds.index(("作者注", "个人")), f"全班的在前、个人的在后：{kinds}")
    check(all((r["mine"] == 1) == (r["note_scope"] == "个人") for r in notes), "个人的能改（mine=1），全班的只读")
    check(not any("s2的记忆" in r["note_brief"] for r in notes), "没有别的学生的个人设定")
    chat = (b.get("lists") or {}).get("student_chat") or []
    tagged = [r for r in chat if r["chat_notes"]]
    check(tagged and all(r["chat_who"] == "老师" for r in tagged)
          and any(f"记忆#{m_class}" in r["chat_notes"] and f"作者注#{a_me}" in r["chat_notes"] for r in tagged),
          f"问老师记录：老师那条带着用了的设定：{tagged[-1]['chat_notes'] if tagged else None}")
    st, b = post("/teacher_note/save", student="me", note_id=str(m_class), note_kind="记忆", note_content="学生页改全班")
    check(st == 404 and rows("SELECT note_content FROM teacher_note WHERE id = ?", m_class)[0]["note_content"] == "全班这周重点是て形。",
          f"学生页改不了全班的：{st}")
    st, b = post("/teacher_note/delete", student="me", note_id=str(m_class))
    st2, b2 = post("/teacher_note/open", student="me", note_id=str(m_class))
    check(st == 404 and st2 == 404 and n("teacher_note", "id = ?", m_class) == 1, "学生页删不了、载入不了全班的")
    st, b = post("/teacher_note/open", student="me", note_id=str(a_me))
    check(st == 200 and (b.get("form") or {}).get("note_content") == "多用敬语。", f"学生页载入自己的：{b.get('form')}")
    st, b = post("/teacher_note/save", student="me", note_kind="记忆", note_content="学生页新增")
    lst = (b.get("lists") or {}).get("student_notes") or []
    check(st == 200 and any(r["note_brief"] == "学生页新增" and r["note_scope"] == "个人" for r in lst),
          "学生页新增：存成这个学生个人的，回学生页的列表")
    deleted = last_id()
    post("/teacher_note/delete", student="me", note_id=str(deleted))
    st, b = post("/teacher_note/save", student="nobody", note_kind="记忆", note_content="x")
    check(st == 400, f"不是学生：400 {b.get('error')}")

    # ------------------------------------------------------------------
    print("十、多人模式")
    mapp, mmock = make(ws, login=True)
    LIMITER.reset()
    env = dict(os.environ, KG_TEST_PW="teach-pass-1")
    r = subprocess.run([PY, "-m", "kg", "建教师", "t1", "--显示名", "王老师", "--库", str(db),
                        "--密码环境变量", "KG_TEST_PW"], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=60)
    check(r.returncode == 0, "命令行建教师 t1")
    teacher = mapp.test_client()
    teacher.post("/auth/login", json={"form": {"username": "t1", "password": "teach-pass-1"}})
    for u in ("s1", "s3"):
        teacher.post("/student/create", json={"form": {"username": u, "display_name": u, "password": f"{u}-pass"}})
    s1 = mapp.test_client()
    s1.post("/auth/login", json={"form": {"username": "s1", "password": "s1-pass"}})

    def mpost(cl, path, **form):
        rr = cl.post(path, json={"form": form})
        return rr.status_code, (rr.get_json(silent=True) or {})

    eps = ["/teacher_note/home", "/teacher_note/open", "/teacher_note/save", "/teacher_note/disable",
           "/teacher_note/enable", "/teacher_note/delete", "/teacher_note/preview"]
    st, b = mpost(teacher, "/teacher_note/save", student="s1", note_kind="作者注", note_content="给s1的作者注。")
    check(st == 200, f"对照：教师能存（给 s1）{st} {b.get('error')}")
    s1_note = last_id()
    st, b = mpost(teacher, "/teacher_note/save", student="s3", note_kind="作者注", note_content="给s3的作者注。")
    st, b = mpost(teacher, "/teacher_note/home")
    check(st == 200 and b.get("lists", {}).get("class_notes"), "对照：教师进设定页 200")
    bad = []
    n_before = n("teacher_note")
    for path in eps:
        st, b = mpost(s1, path, note_id=str(s1_note), student="s1", note_kind="记忆", note_content="学生写的",
                      preview_student="s1", preview_message="x")
        if st != 403 or b.get("error") != "需要教师权限" or "给s1的作者注" in str(b):
            bad.append((path, st, b.get("error")))
    check(not bad, f"学生调 /teacher_note/* 全是 403「需要教师权限」、拿不到内容（不对的 {bad}）")
    check(n("teacher_note") == n_before, "学生什么也没改成")
    mmock.calls.clear()
    rr = s1.post("/teacher/send", json={"form": {"content": "老师好"}})
    sb = rr.get_json(silent=True) or {}
    calls = [x for x in mmock.calls if "意图分类器" not in (x.get("system") or "")]
    p = calls[-1]["prompt"] if calls else ""
    check(rr.status_code == 200 and "给s1的作者注" in p and "给s3的作者注" not in p and "多用敬语" not in p,
          "s1 的提示词里有给 s1 的，没有给 s3、me 的")
    st, b = mpost(s1, "/teacher/state")
    check("给s1的作者注" not in str(sb) and "给s1的作者注" not in str(b) and "教师设定" not in str(b),
          "s1 拿到的回复、对话记录里都没有设定内容")
    st, b = mpost(teacher, "/report/one", student="s1")
    chat = (b.get("lists") or {}).get("student_chat") or []
    check(any(f"作者注#{s1_note}" in r["chat_notes"] for r in chat), "教师在学情里看到 s1 那条回复用了哪条设定")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
