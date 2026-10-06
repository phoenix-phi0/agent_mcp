# -*- coding: utf-8 -*-
"""AI 老师设定的第四种「传达」：teacher_relay / relay_state / relay_use 表、
/teacher_relay/* 接口、问老师拼提示词、后台判定。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_teacher_relay.py

临时工作区（照 kg 搭），不碰 kg/app.db。模型是离线的假客户端：意图判定一律讲解
（「给我出点题」是出题）；老师回答回 REPLY；判定（系统提示词里有「传达检查员」，
走「问JSON」）按 JUDGE[学习者] 回：yes / no / wrong / raise（抛错）/ garbage（不是
JSON）/ nokey（JSON 里没有 delivered）。每次调用都记在 mock.calls 里。判定在后台线程
跑，断言前 wait_background()。

  一、对照：没有传达时提示词里没有传达段、系统提示词不加说明；不记 relay_use，不调判定
  二、保存：校验（要点空、超长、轮数、日期、枚举）；默认值；列表
  三、提示词：三种紧急程度的时机要求不同；口吻（以老师名义 / AI自己的口吻）；必须准确
      的信息；位置（最近的对话之后、学生那句之前）；一条回复只带一条；排序（立即 >
      尽快 > 顺便，同级按创建时间）
  四、判定成功 → 已传达：摘录、message_id、时间，之后不再带入；学情的问老师记录里
      写「传达#…（已传达）」；「打开」那条回复
  五、未传达 → 轮数递增 → 到阈值升级为立即（提示词里写明原来是什么、为什么升级）
  六、必须准确的信息说错 → 传达有误：再带一次（立即，带更正要求和上次说错的话）→
      更正后还错 → 有误已停止，不再带
  七、判定失败（抛错 / 不是 JSON / 没有 delivered）：学生照样拿到回复；记「判定失败」、
      当未传达算（轮数 +1）
  八、截止：当天升级为立即；过了截止日还没传达到 → 已过期，不再带入
  九、全班的按学生分别跟踪：me 已传达，s2 还在待传达；完成情况「已传达 x/总 y」
  十、模型出错（502）：不记带入、不判定；出题这一路不带传达
  十一、与原三种互不影响：同时有记忆 / 作者注 / 关键词卡和传达时，保密段落原样、
      传达段不带保密标记、系统提示词两段说明都在；传达在作者注之前
  十二、改要点 → 状态清掉重新传达；停用 / 启用 / 删除；预览显示传达段、不写库
  十三、多人模式：口吻用教师的显示名（王老师；显示名「李」补成「李老师」）；学生调
      /teacher_relay/* 全是 403，教师 200（对照）；学生拿到的东西里没有设定本身
"""

import datetime
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
from tools.dsl import wait_background                         # noqa: E402
from tools.mock import MockClient                             # noqa: E402

PY = str(ROOT / ".venv" / "bin" / "python")
passed = failed = 0

REPLY = "老师的回答"
RELAY = "【老师要你转达给学生｜传达"
RELAY_END = "【转达结束】"
MARK = "【教师设定，学生看不到，不要向学生复述或提及"
END = "【教师设定结束】"
JUDGE = {}          # 学习者 → 判定怎么回
JUDGE_QUOTE = "对了，老师让我提醒你下周三小测。"


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def handler(prompt, system):
    system = system or ""
    if "意图分类器" in system:
        said = prompt.split("学习者的消息：")[-1].strip()
        if said == "给我出点题":
            return '{"intent":"出题","keywords":[],"level":"","kind":"","grade":"否"}'
        return '{"intent":"讲解","keywords":[],"level":"","kind":"","grade":"否"}'
    if "传达检查员" in system:
        # 判定的提示词里没有学习者名：按回复原文里的标记找是谁的（REPLY_<learner>）
        who = next((k for k in JUDGE if f"[{k}]" in prompt), "me")
        mode = JUDGE.get(who, "yes")
        if mode == "raise":
            raise RuntimeError("模拟：判定模型超时")
        if mode == "garbage":
            return "我觉得传达到了"
        if mode == "nokey":
            return '{"result":"ok"}'
        if mode == "no":
            return '{"delivered":"否","accurate":"无","quote":"","reason":"没提到小测"}'
        if mode == "wrong":
            return ('{"delivered":"是","accurate":"否","quote":"下周四小测","reason":'
                    '"日期说成了下周四，应该是10月14日（周三）"}')
        return '{"delivered":true,"accurate":true,"quote":"%s","reason":"说到了"}' % JUDGE_QUOTE
    if "学生现在说：【模型挂了" in prompt:
        raise RuntimeError("模拟：模型超时")
    # 回复里带上学习者标记，判定那边按它分辨是谁
    who = prompt.split("〔")[-1].split("〕")[0] if "〔" in prompt else "me"
    return f"{REPLY}[{who}]"


def make(ws, login=False):
    from gen.project import make_app
    app, router = make_app(ws, real=False, login=login) if login else make_app(ws, real=False)
    mock = MockClient(handler=handler, offline=True)
    router.client_factory = lambda: mock
    return app, mock


def main():
    ws = make_ws(Path(tempfile.mkdtemp(prefix="teacher_relay_")))
    import_graph(ws)
    client(ws).post("/lesson/import", json={"form": {}})
    db = ws / "app.db"
    app, mock = make(ws)
    c = app.test_client()
    today = datetime.date.today()

    def rows(sql, *args):
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        try:
            return [dict(x) for x in con.execute(sql, args)]
        finally:
            con.close()

    def one(sql, *args):
        got = rows(sql, *args)
        return got[0] if got else {}

    def post(path, cl=None, **form):
        r = (cl or c).post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    def save(point, student="", urgency="尽快", voice="以老师名义", facts="", keywords="",
             rounds="3", due="", relay_id="", cl=None):
        form = {"relay_point": point, "relay_urgency": urgency, "relay_voice": voice,
                "relay_facts": facts, "relay_keywords": keywords, "relay_rounds": rounds,
                "relay_due": due}
        if student:
            form["student"] = student
        if relay_id:
            form["relay_id"] = str(relay_id)
        return post("/teacher_relay/save", cl=cl, **form)

    def last_id():
        return one("SELECT max(id) m FROM teacher_relay")["m"]

    def judge_calls(m=None):
        return [x for x in (m or mock).calls if x["type"] == "chat_json"]

    def answer_call(m=None):
        got = [x for x in (m or mock).calls
               if x["type"] == "chat" and "意图分类器" not in (x.get("system") or "")]
        return got[-1] if got else {}

    def send(text, learner="me", cl=None, m=None):
        """问一句，等后台判定跑完。回 (状态码, 响应, 系统提示词, 提示词)。学习者
        标记「〔learner〕」放在原话末尾，假模型回复里带上它，判定按它分辨是谁"""
        (m or mock).calls.clear()
        form = {"content": f"{text}〔{learner}〕"}
        if cl is None:
            form["learner"] = learner
        r = (cl or c).post("/teacher/send", json={"form": form})
        wait_background(20)
        call = answer_call(m)
        return r.status_code, (r.get_json(silent=True) or {}), call.get("system") or "", call.get("prompt") or ""

    def relay_block(prompt):
        if RELAY not in prompt:
            return ""
        i = prompt.index(RELAY)
        return prompt[i:prompt.index(RELAY_END, i) + len(RELAY_END)]

    def state(rid, learner="me"):
        return one("SELECT * FROM relay_state WHERE relay_id = ? AND learner = ?", rid, learner)

    def clear_relays():
        for x in rows("SELECT id FROM teacher_relay"):
            post("/teacher_relay/delete", relay_id=str(x["id"]))
            post("/teacher_relay/delete", relay_id=str(x["id"]), student="me")
            post("/teacher_relay/delete", relay_id=str(x["id"]), student="s2")

    # ------------------------------------------------------------------
    print("一、对照：没有传达")
    st, body, system, prompt = send("は和が有什么区别")
    check(st == 200 and (body.get("messages") or [{}])[-1].get("text") == f"{REPLY}[me]", f"回了老师的话：{st}")
    check("转达" not in prompt and "转达" not in system, "提示词、系统提示词里都没有传达")
    check(system.endswith("你不要自己写网址。"), "系统提示词跟原来一样结尾")
    check(not judge_calls() and not rows("SELECT * FROM relay_use"), "没调判定模型、没记 relay_use")
    # s2 也问一句：全班名单里有两个学习者
    send("你好", learner="s2")

    # ------------------------------------------------------------------
    print("二、保存和校验")
    st, b = post("/teacher_note/home")
    check(st == 200 and b.get("lists", {}).get("class_relays") == [] and b["lists"].get("class_relay_states") == [],
          f"设定页进来：传达列表空 {st}")
    bad = [
        (dict(point=""), "要点不能为空"),
        (dict(point="长" * 301), "300 字"),
        (dict(point="x", facts="长" * 201), "200 字"),
        (dict(point="x", rounds="21"), "轮数阈值"),
        (dict(point="x", rounds="abc"), "轮数阈值"),
        (dict(point="x", due="2026/10/20"), "截止日期"),
        (dict(point="x", due="2026-02-30"), "截止日期"),
        (dict(point="x", urgency="马上"), "紧急程度"),
        (dict(point="x", voice="随便"), "口吻"),
    ]
    for kw, want in bad:
        st, b = save(**kw)
        check(st == 400 and want in b.get("error", ""), f"{kw}：400「{b.get('error')}」")
    check(not rows("SELECT * FROM teacher_relay"), "被拒的都没存进去")
    st, b = post("/teacher_relay/save", relay_point="只填了要点", relay_rounds=0, relay_voice="", relay_urgency="")
    r = one("SELECT * FROM teacher_relay")
    check(st == 200 and r.get("relay_urgency") == "尽快" and r.get("relay_voice") == "以老师名义"
          and r.get("relay_rounds") == 3 and r.get("relay_student") == "" and r.get("relay_enabled") == 1
          and r.get("relay_by") == "老师",
          f"默认（「新增传达」的空表单：轮数 0、下拉空）：尽快、以老师名义、3 轮、全班、启用、写的人是老师 {r}")
    st, b = post("/teacher_relay/open")
    f = b.get("form") or {}
    check(st == 200 and f.get("relay_urgency") == "尽快" and f.get("relay_voice") == "以老师名义"
          and str(f.get("relay_rounds")) == "3", f"「新增传达」的空表单带默认值：{f}")
    st, b = post("/teacher_relay/open", relay_id=str(r["id"]))
    check(st == 200 and (b.get("form") or {}).get("relay_point") == "只填了要点", "载入一条")
    st, b = post("/teacher_relay/open", relay_id=str(r["id"]), student="me")
    check(st == 404, f"学生页载入不了全班的：{st}")
    st, b = save("给不存在的学生", student="nobody")
    check(st == 400 and "没有这个学生" in b.get("error", ""), f"不是学生：400 {b.get('error')}")
    clear_relays()

    # ------------------------------------------------------------------
    print("三、提示词")
    JUDGE["me"] = "no"
    texts = {}
    for urg in ("顺便", "尽快", "立即"):
        save(f"{urg}的要点：下周三小测", urgency=urg, keywords="小测,テスト" if urg == "顺便" else "")
        rid = last_id()
        st, body, system, prompt = send(f"看{urg}")
        blk = relay_block(prompt)
        texts[urg] = blk
        check(st == 200 and f"{urg}的要点" in blk, f"{urg}：带上了")
        post("/teacher_relay/delete", relay_id=str(rid))
    check("只在学生现在聊的话题跟这件事沾边时" in texts["顺便"] and "小测,テスト" in texts["顺便"]
          and "不沾边这次就先不说" in texts["顺便"], "顺便：话题沾边才说、给了关键词提示、不沾边不说")
    check("这一两轮回复之内" in texts["尽快"] and "自然的过渡" in texts["尽快"], "尽快：一两轮内找过渡")
    check("这一条回复就要说到" in texts["立即"] and "末尾" in texts["立即"] and "「对了，" in texts["立即"],
          "立即：这一条就说、放末尾用「对了」过渡")
    check(len({t.split("时机：")[1].split("\n")[0] for t in texts.values()}) == 3, "三种的时机要求各不相同")
    common = texts["尽快"]
    check("不是台词" in common and "结合学生现在聊的话题" in common and "适合这个学生水平" in common
          and "不要像念公告一样生硬" in common and "不要把这件事放在回复开头" in common
          and "只转达这一件事" in common, "共同要求：意图不是台词、结合话题、学生水平、不生硬、不放开头、只说一件")
    check("口吻：以老师的名义转达" in common and "「老师让我提醒你" in common, "单人模式：以「老师」的名义")
    save("用AI自己的口吻的要点", voice="AI自己的口吻")
    rid = last_id()
    st, body, system, prompt = send("口吻")
    blk = relay_block(prompt)
    check("用你自己的口吻说" in blk and "让我提醒你" not in blk, "AI自己的口吻：不提老师让说")
    post("/teacher_relay/delete", relay_id=str(rid))
    save("带必须准确信息的要点", facts="10月14日；第1到5课")
    rid = last_id()
    st, body, system, prompt = send("准确")
    blk = relay_block(prompt)
    check("必须准确的信息（原样说对" in blk and "10月14日；第1到5课" in blk, "必须准确的信息写进去")
    check(prompt.index("最近的对话") < prompt.index(RELAY) and
          prompt[prompt.index(RELAY_END) + len(RELAY_END):].startswith("\n学生现在说："),
          "位置：最近的对话之后、学生那句之前")
    check("【老师要你转达的话】" in system and "教师设定」照样不能" in system,
          "系统提示词末尾说明转达和教师设定的区别")
    post("/teacher_relay/delete", relay_id=str(rid))
    # 排序：立即 > 尽快 > 顺便；同级按创建时间
    save("A顺便", urgency="顺便")
    a = last_id()
    save("B尽快早", urgency="尽快")
    b_early = last_id()
    save("C尽快晚", urgency="尽快")
    save("D立即", urgency="立即")
    d = last_id()
    st, body, system, prompt = send("排序")
    check(prompt.count(RELAY) == 1 and "D立即" in prompt and "B尽快" not in prompt and "A顺便" not in prompt,
          "一条回复只带一条：立即的排第一")
    check(one("SELECT count(*) n FROM relay_use WHERE message_id = (SELECT max(id) FROM chat_message)")["n"] == 1,
          "relay_use 只记一条")
    post("/teacher_relay/delete", relay_id=str(d))
    st, body, system, prompt = send("排序2")
    check("B尽快早" in prompt and "C尽快晚" not in prompt, "同是尽快：先建的在前")
    st, b = post("/teacher_note/preview", preview_student="me", preview_message="x")
    pv = (b.get("state") or {}).get("preview") or {}
    check(f"传达#{b_early}" in pv.get("relay_pick", "") and "排着2条" in pv.get("relay_pick", ""),
          f"预览：这次带哪条、后面排着几条：{pv.get('relay_pick')}")
    check("B尽快早" in pv.get("relay", "") and RELAY in pv.get("layout", "")
          and pv["layout"].index("最近的对话") < pv["layout"].index(RELAY) < pv["layout"].index("学生现在说：【x】"),
          "预览：传达段原文和位置")
    check(state(a).get("carried_n") is None, "顺便那条一直排在后面，没带过")
    clear_relays()

    # ------------------------------------------------------------------
    print("四、判定成功 → 已传达")
    JUDGE["me"] = "yes"
    save("下周三小测", facts="10月14日")
    rid = last_id()
    st, body, system, prompt = send("讲讲て形")
    msg = one("SELECT max(id) m FROM chat_message WHERE learner = 'me' AND role = 'teacher'")["m"]
    js = judge_calls()
    check(st == 200 and len(js) == 1 and js[0].get("tier") == "快", f"判了一次，用的快档：{[x.get('tier') for x in js]}")
    check("下周三小测" in js[0]["prompt"] and "10月14日" in js[0]["prompt"] and f"{REPLY}[me]" in js[0]["prompt"],
          "判定的材料：要点、必须准确的信息、回复原文")
    s = state(rid)
    check(s.get("status") == "已传达" and s.get("message_id") == msg and s.get("excerpt") == JUDGE_QUOTE
          and s.get("delivered_at") and s.get("carried_n") == 1,
          f"已传达：那条回复、摘录、时间：{s}")
    u = one("SELECT * FROM relay_use WHERE relay_id = ?", rid)
    check(u.get("verdict") == "已传达" and u.get("message_id") == msg and u.get("urgency") == "尽快", f"relay_use：{u}")
    st, body, system, prompt = send("再问一句")
    check(RELAY not in prompt and "转达" not in system and not judge_calls(), "已传达：不再带，也不再调判定")
    st, b = post("/report/one", student="me")
    rel = {x["relay_id"]: x for x in (b.get("lists") or {}).get("student_relays", [])}
    check(rel.get(rid, {}).get("relay_state_text", "").startswith("已传达（") and rel[rid]["relay_excerpt"] == JUDGE_QUOTE
          and rel[rid]["message_id"] == msg and rel[rid]["relay_msg_reply"] == f"{REPLY}[me]"
          and rel[rid]["relay_msg_ask"] == "讲讲て形〔me〕",
          f"学生页：已传达（时间）、摘录、那条回复：{rel.get(rid, {}).get('relay_state_text')}")
    chat = (b.get("lists") or {}).get("student_chat") or []
    check(any(f"传达#{rid}（已传达）" in x["chat_notes"] for x in chat), "问老师记录：老师那条写着「传达#…（已传达）」")
    st, b = post("/teacher_relay/message", message_id=str(msg))
    check(st == 200 and (b.get("form") or {}).get("relay_msg_reply") == f"{REPLY}[me]"
          and b["form"].get("relay_excerpt") == JUDGE_QUOTE, "「打开」那条问老师记录")
    st, b = post("/teacher_relay/message", message_id="999999")
    check(st == 404, f"没有的记录 404：{st}")
    clear_relays()

    # ------------------------------------------------------------------
    print("五、未传达 → 轮数递增 → 升级为立即")
    JUDGE["me"] = "no"
    save("顺便提一下周末的读书会", urgency="顺便", rounds="2")
    rid = last_id()
    st, body, system, prompt = send("第一句")
    check(state(rid).get("miss_n") == 1 and state(rid).get("status") == "待传达" and "不急，顺便说" in prompt,
          f"第一次没传达到：miss 1 {state(rid)}")
    st, body, system, prompt = send("第二句")
    check(state(rid).get("miss_n") == 2 and "不急，顺便说" in prompt, "第二次：miss 2，这次还是顺便")
    st, b = post("/report/one", student="me")
    rel = {x["relay_id"]: x for x in (b.get("lists") or {}).get("student_relays", [])}
    check(rel[rid]["relay_state_text"] == "待传达（已带入 2 轮）·已升级为立即", f"学生页：{rel[rid]['relay_state_text']}")
    st, body, system, prompt = send("第三句")
    blk = relay_block(prompt)
    check("时机：立即" in blk and "原来是「顺便」" in blk and "已经带了 2 轮还没说到" in blk,
          f"到阈值：升级为立即，写明原来是什么、为什么：{blk[blk.find('时机'):][:120]!r}")
    check(one("SELECT urgency FROM relay_use ORDER BY id DESC LIMIT 1")["urgency"] == "立即", "relay_use 记的是立即")
    JUDGE["me"] = "yes"
    st, body, system, prompt = send("第四句")
    check(state(rid).get("status") == "已传达" and state(rid).get("carried_n") == 4, f"这次传达到了：{state(rid)}")
    clear_relays()

    # ------------------------------------------------------------------
    print("六、必须准确的信息说错 → 传达有误")
    JUDGE["me"] = "wrong"
    save("下周三小测，范围第1到5课", facts="10月14日（周三）", urgency="顺便")
    rid = last_id()
    st, body, system, prompt = send("说错一次")
    s = state(rid)
    check(s.get("status") == "传达有误" and s.get("wrong_n") == 1 and s.get("excerpt") == "下周四小测"
          and s.get("miss_n") == 0, f"第一次说错：传达有误，记下说错的那句 {s}")
    st, b = post("/report/one", student="me")
    rel = {x["relay_id"]: x for x in (b.get("lists") or {}).get("student_relays", [])}
    check(rel[rid]["relay_state_text"] == "传达有误（下一条要求更正）", f"学生页提示老师：{rel[rid]['relay_state_text']}")
    st, b = post("/teacher_note/home")
    done = {x["relay_id"]: x["relay_done"] for x in b["lists"]["class_relays"]}
    check("传达有误 1" in done[rid], f"设定页汇总里也标出：{done[rid]}")
    st, body, system, prompt = send("再带一次")
    blk = relay_block(prompt)
    check("时机：立即" in blk and "更正：上一次转达时把必须准确的信息说错了" in blk and "下周四小测" in blk
          and "日期说成了下周四" in blk and "10月14日（周三）" in blk and "之前那句说错了" in blk,
          f"再带一次：立即、带更正要求、上次说错的话和正确的信息：{blk[blk.find('更正'):][:160]!r}")
    s = state(rid)
    check(s.get("status") == "有误已停止" and s.get("wrong_n") == 2, f"更正后还错：有误已停止 {s}")
    st, body, system, prompt = send("之后")
    check(RELAY not in prompt and not judge_calls(), "停止后不再带、不再判")
    st, b = post("/report/one", student="me")
    rel = {x["relay_id"]: x for x in (b.get("lists") or {}).get("student_relays", [])}
    check(rel[rid]["relay_state_text"].startswith("传达有误·已停止"), f"学生页：{rel[rid]['relay_state_text']}")
    # 对照：说错一次、更正那次说对了 → 已传达
    clear_relays()
    JUDGE["me"] = "wrong"
    save("另一个小测", facts="10月21日")
    rid = last_id()
    send("错一次")
    JUDGE["me"] = "yes"
    send("更正")
    check(state(rid).get("status") == "已传达" and state(rid).get("wrong_n") == 1, f"对照：更正对了就是已传达 {state(rid)}")
    clear_relays()

    # ------------------------------------------------------------------
    print("七、判定失败不影响回复")
    for mode, why in (("raise", "判定模型超时"), ("garbage", "合法 JSON"), ("nokey", "没有delivered")):
        JUDGE["me"] = mode
        save(f"判定失败的要点{mode}")
        rid = last_id()
        st, body, system, prompt = send(f"判定{mode}")
        u = one("SELECT * FROM relay_use WHERE relay_id = ?", rid)
        check(st == 200 and (body.get("messages") or [{}])[-1].get("text") == f"{REPLY}[me]",
              f"{mode}：学生照样拿到回复")
        check(u.get("verdict") == "判定失败" and why in (u.get("judge_note") or "")
              and state(rid).get("miss_n") == 1 and state(rid).get("status") == "待传达",
              f"{mode}：记成判定失败、当没传达到（miss 1）：{u.get('judge_note')}")
        post("/teacher_relay/delete", relay_id=str(rid))

    # ------------------------------------------------------------------
    print("八、截止日期")
    JUDGE["me"] = "no"
    save("今天截止的要点", urgency="顺便", due=today.isoformat())
    due_today = last_id()
    st, body, system, prompt = send("截止当天")
    blk = relay_block(prompt)
    check("时机：立即" in blk and "今天是截止日" in blk, "截止日当天：升级为立即")
    post("/teacher_relay/delete", relay_id=str(due_today))
    save("昨天截止的要点", due=(today - datetime.timedelta(days=1)).isoformat())
    past = last_id()
    st, body, system, prompt = send("过期了")
    check(RELAY not in prompt and not judge_calls(), "过了截止日：不再带入、不判定")
    st, b = post("/report/one", student="me")
    rel = {x["relay_id"]: x for x in (b.get("lists") or {}).get("student_relays", [])}
    check(rel[past]["relay_state_text"].startswith("已过期（截止"), f"学生页：{rel[past]['relay_state_text']}")
    st, b = post("/teacher_note/home")
    done = {x["relay_id"]: x["relay_done"] for x in b["lists"]["class_relays"]}
    check("已过期 2" in done[past], f"设定页汇总：{done[past]}")
    clear_relays()

    # ------------------------------------------------------------------
    print("九、全班的按学生分别跟踪")
    JUDGE["me"], JUDGE["s2"] = "yes", "no"
    save("全班：下周三小测")
    rid = last_id()
    send("me 问", learner="me")
    st, body, system, prompt = send("s2 问", learner="s2")
    check(RELAY in prompt, "s2 也带上了")
    check(state(rid, "me").get("status") == "已传达" and state(rid, "s2").get("status") == "待传达"
          and state(rid, "s2").get("miss_n") == 1, "me 已传达，s2 还在待传达")
    st, body, system, prompt = send("me 再问", learner="me")
    st2, body2, system2, prompt2 = send("s2 再问", learner="s2")
    check(RELAY not in prompt and RELAY in prompt2, "me 不再带，s2 还带")
    st, b = post("/teacher_note/home")
    done = {x["relay_id"]: x["relay_done"] for x in b["lists"]["class_relays"]}
    states = [x for x in b["lists"]["class_relay_states"] if x["relay_id"] == rid]
    check(done[rid] == "已传达 1/总 2", f"全班页汇总：{done[rid]}")
    check(sorted((x["relay_student_label"], x["relay_state_text"][:3]) for x in states)
          == [("me", "已传达"), ("s2", "待传达")], f"各学生的状态：{[(x['relay_student_label'], x['relay_state_text']) for x in states]}")
    check([x for x in states if x["relay_student_label"] == "me"][0]["message_id"] is not None
          and [x for x in states if x["relay_student_label"] == "s2"][0]["message_id"] is None,
          "传达到的那行有 message_id（「看那条回复」），没传达到的没有")
    # 个人的只对那个学生
    save("只给s2的要点", student="s2", urgency="立即")
    st, body, system, prompt = send("me 问个人", learner="me")
    st2, body2, system2, prompt2 = send("s2 问个人", learner="s2")
    check("只给s2的要点" not in prompt and "只给s2的要点" in prompt2, "个人的只进 s2 的提示词")
    st, b = post("/report/one", student="me")
    check(not any("只给s2" in x["relay_brief"] for x in b["lists"]["student_relays"]), "me 的学生页没有 s2 个人的")
    st, b = post("/report/one", student="s2")
    sr = b["lists"]["student_relays"]
    check([(x["relay_scope"], x["mine"]) for x in sr] == [("全班", 0), ("个人", 1)], f"s2 的学生页：全班的只读在前、个人的在后 {[(x['relay_scope'], x['mine']) for x in sr]}")
    st, b = save("学生页改全班的", student="s2", relay_id=rid)
    check(st == 404, f"学生页改不了全班的：{st}")
    clear_relays()

    # ------------------------------------------------------------------
    print("十、模型出错、出题这一路")
    JUDGE["me"] = "yes"
    save("模型出错时的要点")
    rid = last_id()
    n_use = len(rows("SELECT * FROM relay_use"))
    st, body, system, prompt = send("模型挂了")
    check(st == 502 and len(rows("SELECT * FROM relay_use")) == n_use and not state(rid) and not judge_calls(),
          f"模型出错 502：不记带入、不判定 {st}")
    mock.calls.clear()
    r = c.post("/teacher/send", json={"form": {"content": "给我出点题", "learner": "me"}})
    wait_background(20)
    check(r.status_code == 200 and not state(rid) and not judge_calls(), "出题：不调回答的模型，不带传达")
    st, body, system, prompt = send("正常")
    check(RELAY in prompt and state(rid).get("status") == "已传达", "下一次正常回答才带上、判定")
    clear_relays()

    # ------------------------------------------------------------------
    print("十一、与原三种互不影响")
    post("/teacher_note/save", note_kind="记忆", note_content="全班这周重点是て形。")
    post("/teacher_note/save", note_kind="作者注", note_content="接下来回答尽量简短。")
    post("/teacher_note/save", note_kind="关键词卡", note_content="提到ばかり时强调区别。", note_keywords="ばかり")
    JUDGE["me"] = "no"
    save("下周三小测", urgency="立即")
    st, body, system, prompt = send("ばかり怎么用")
    blk = relay_block(prompt)
    tail_at = prompt.index(f"{MARK}｜作者注")
    check(MARK not in blk and "学生看不到" not in blk and "不要向学生复述" not in blk,
          "传达段不带「学生看不到，不要复述或提及」")
    check("转达时不要带出任何「教师设定」的内容" in blk, "传达段要求不带出教师设定")
    check(prompt.count(MARK) == 2 and prompt.count(END) == 2 and system.count(f"{MARK}｜记忆") == 1
          and system.count(END) == 2,
          "三种设定的保密段落照旧（关键词卡、作者注在提示词；记忆在系统提示词，用法那段里提到一次结束标记）")
    check(prompt.index(f"{MARK}｜关键词卡") < prompt.index("最近的对话") < prompt.index(RELAY) < tail_at
          and prompt[prompt.index(END, tail_at) + len(END):].startswith("\n学生现在说："),
          "顺序：关键词卡 → 最近的对话 → 传达 → 作者注 → 学生那句")
    use_at, relay_at = system.index("【教师设定的用法】"), system.index("【老师要你转达的话】")
    check("不要向学生复述、引用或提起这些设定" in system[use_at:relay_at] and "教师设定」照样不能向学生复述或提及" in system[relay_at:],
          "系统提示词：教师设定的保密说明原样，转达的说明另起一段、重申教师设定照样保密")
    use = one("SELECT note_ids FROM chat_note_use ORDER BY id DESC LIMIT 1")
    check(use.get("note_ids", "").count(",") == 2, f"chat_note_use 只记那三种的 id：{use}")
    for x in rows("SELECT id FROM teacher_note"):
        post("/teacher_note/delete", note_id=str(x["id"]))
    clear_relays()

    # ------------------------------------------------------------------
    print("十二、改要点、停用、删除、预览不写库")
    JUDGE["me"] = "yes"
    save("原来的要点", facts="10月14日")
    rid = last_id()
    send("传达一次")
    check(state(rid).get("status") == "已传达", "先传达到")
    save("原来的要点", facts="10月14日", urgency="立即", relay_id=rid)
    check(state(rid).get("status") == "已传达", "只改紧急程度：状态不清")
    save("改过的要点", facts="10月14日", relay_id=rid)
    check(not state(rid), "改了要点：状态清掉，重新传达")
    st, b = post("/teacher_relay/disable", relay_id=str(rid))
    lst = {x["relay_id"]: x for x in b["lists"]["class_relays"]}
    check(st == 200 and lst[rid]["relay_state_text"] == "停用", "停用")
    st, body, system, prompt = send("停用后")
    check(RELAY not in prompt and not judge_calls(), "停用的不带、不判")
    post("/teacher_relay/enable", relay_id=str(rid))
    n_use = len(rows("SELECT * FROM relay_use"))
    mock.calls.clear()
    st, b = post("/teacher_note/preview", preview_student="me", preview_message="预览")
    check("改过的要点" in ((b.get("state") or {}).get("preview") or {}).get("relay", "")
          and not mock.calls and len(rows("SELECT * FROM relay_use")) == n_use and not state(rid),
          "预览：显示传达段，不调模型、不写库、不算带入")
    st, body, system, prompt = send("启用后")
    check("改过的要点" in prompt and state(rid).get("status") == "已传达", "启用后带上、传达到")
    st, b = post("/teacher_relay/delete", relay_id=str(rid))
    check(st == 200 and not rows("SELECT * FROM teacher_relay") and not state(rid), "删除：传达和状态都没了")
    st, b = post("/report/one", student="me")
    check(any(f"已删传达#{rid}" in x["chat_notes"] for x in b["lists"]["student_chat"]), "问老师记录里写「已删传达#…」")
    st, b = post("/teacher_relay/delete", relay_id=str(rid))
    check(st == 404, f"再删 404：{st}")

    # ------------------------------------------------------------------
    print("十三、多人模式")
    mapp, mmock = make(ws, login=True)
    LIMITER.reset()
    env = dict(os.environ, KG_TEST_PW="teach-pass-1")
    for user, label in (("t1", "王老师"), ("t2", "李")):
        r = subprocess.run([PY, "-m", "kg", "建教师", user, "--显示名", label, "--库", str(db),
                            "--密码环境变量", "KG_TEST_PW"], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=60)
        check(r.returncode == 0, f"命令行建教师 {user}（{label}）")
    t1, t2 = mapp.test_client(), mapp.test_client()
    t1.post("/auth/login", json={"form": {"username": "t1", "password": "teach-pass-1"}})
    t2.post("/auth/login", json={"form": {"username": "t2", "password": "teach-pass-1"}})
    t1.post("/student/create", json={"form": {"username": "s1", "display_name": "s1", "password": "s1-pass"}})
    s1 = mapp.test_client()
    s1.post("/auth/login", json={"form": {"username": "s1", "password": "s1-pass"}})
    JUDGE["s1"] = "no"
    st, b = save("给s1的要点：下周三小测", student="s1", cl=t1)
    check(st == 200, f"对照：教师能存 {st} {b.get('error')}")
    s1_relay = last_id()
    check(one("SELECT relay_by FROM teacher_relay WHERE id = ?", s1_relay)["relay_by"] == "t1", "写的人记 t1")
    st, body, system, prompt = send("老师好", learner="s1", cl=s1, m=mmock)
    blk = relay_block(prompt)
    check(st == 200 and "以王老师的名义转达" in blk and "「王老师让我提醒你" in blk, f"口吻：用 t1 的显示名「王老师」{blk[blk.find('口吻'):][:40]!r}")
    save("给s1的要点：下周三小测", student="s1", relay_id=s1_relay, cl=t2)
    st, body, system, prompt = send("老师好2", learner="s1", cl=s1, m=mmock)
    check("以李老师的名义转达" in relay_block(prompt), "t2（显示名「李」）改过之后：补成「李老师」")
    eps = ["/teacher_relay/open", "/teacher_relay/save", "/teacher_relay/disable", "/teacher_relay/enable",
           "/teacher_relay/delete", "/teacher_relay/message", "/teacher_note/home", "/teacher_note/preview"]
    bad = []
    n_before = len(rows("SELECT * FROM teacher_relay"))
    for path in eps:
        st, b = post(path, cl=s1, relay_id=str(s1_relay), student="s1", relay_point="学生写的",
                     relay_urgency="立即", relay_voice="以老师名义", message_id="1",
                     preview_student="s1", preview_message="x")
        if st != 403 or b.get("error") != "需要教师权限" or "给s1的要点" in str(b):
            bad.append((path, st, b.get("error")))
    check(not bad, f"学生调 /teacher_relay/* 全是 403「需要教师权限」、拿不到内容（不对的 {bad}）")
    check(len(rows("SELECT * FROM teacher_relay")) == n_before, "学生什么也没改成")
    st, b = post("/teacher_relay/open", cl=t1, relay_id=str(s1_relay), student="s1")
    check(st == 200 and (b.get("form") or {}).get("relay_point") == "给s1的要点：下周三小测", "对照：教师 200")
    st, b = post("/teacher/state", cl=s1)
    check("给s1的要点" not in str(b) and "转达" not in str(b) and "relay" not in str(b),
          "学生的对话记录里没有设定本身（只有 AI 的回复）")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
