# -*- coding: utf-8 -*-
"""教材页、学习进度页的接口，和知识图谱浮层里的「答对/答题」。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_pages.py

  一、教材列表：全部 / 按等级 / 关键字（标题、一句话、条目名；带空格、日语、
      首尾空白、%）；题数、链接地址；进页面不推消息
  二、读一课：抬头、接续、讲解；例句从 JSON 拆成一句一行；挂着的条目带
      知识点名；题数和「练这一课」的地址；没题的课不给地址、给说明；
      不存在的课给 missing 说明；不给 lesson 400
  三、学习进度（空库）：概览是 0、说「还没有作答」；在学、最近作答、得分
      是空的；按等级五行；现在能学有根节点
  四、学习进度（答了题之后）：经 /quiz 答一对一错，概览、在学、最近作答、
      按等级跟着变；刷到达标（得分过 80）后已掌握数和按等级的已掌握数加一；答题自动打分：
      掌握得分有这个点（当前分、变化、打分时间），概览有平均得分；手工再记
      一次分，变化跟着变；按分从低到高排
  五、知识图谱浮层：答对/答题，没做过说「还没做过」，别的学习者看不到；
      打过分的点后面有「得分」，没打过的没有

每条「不该有」的断言前面都有一条「该有」的对照：接口整个坏掉、什么都不回
的时候，「不该有」那几条照样会过。
"""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import choice_key, client, import_graph, make_ws   # noqa: E402
from kg.__main__ import BANK, read_bank                      # noqa: E402

passed = failed = 0

READ = "#%E6%95%99%E6%9D%90?lesson="       # #教材?lesson=
QUIZ = "#%E5%81%9A%E9%A2%98?lesson="       # #做题?lesson=


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def main():
    lessons = [json.loads(l) for l in
               (ROOT / "kg" / "content" / "lessons.jsonl").read_text(encoding="utf-8").splitlines()
               if l.strip()]
    by_code = {d["code"]: d for d in lessons}
    bank = read_bank(BANK)
    # 留一课没有题：从题库里拿掉这一课的题再导入
    NOQ = "hb-n5-007"
    LESSON = "hb-n4-118"            # ～ようだ
    check(NOQ in by_code and LESSON in by_code, "对照：两课都在课文文件里")
    bank_used = [q for q in bank if q.get("课文") != NOQ]
    check(len(bank_used) < len(bank), f"对照：{NOQ} 在题库里本来有题，拿掉之后少了 {len(bank) - len(bank_used)} 道")

    ws = make_ws(Path(tempfile.mkdtemp(prefix="pages_")))
    import_graph(ws)
    c = client(ws)
    db = ws / "app.db"
    r = c.post("/lesson/import", json={"form": {}}).get_json()
    check(r.get("lessons") == str(len(lessons)), f"课文导入：{r.get('lessons')}")
    r = c.post("/quiz/import", json={"form": {"rows": bank_used}}).get_json()
    check(r.get("questions") == str(len(bank_used)), f"题目导入：{r.get('questions')}")

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

    def lst(body, key):
        return (body.get("lists") or {}).get(key)

    def codes(body):
        return [r["code"] for r in lst(body, "lessons") or []]

    # ------------------------------------------------------------------
    print("一、教材列表")
    st, body = post("/lesson/list")
    allc = codes(body)
    check(st == 200 and len(allc) == len(lessons), f"不给条件：全部 {len(allc)} 课")
    check((body.get("state") or {}).get("lesson_count") == f"共{len(lessons)}课",
          f"顶栏的课数：{(body.get('state') or {}).get('lesson_count')}")
    check(not body.get("messages"), "进页面调的接口不推消息")
    check(body.get("form") == {"lesson_level": "全部", "keyword": ""},
          f"用的条件填回表单（等级下拉不是空的）：{body.get('form')}")
    rowmap = {r["code"]: r for r in lst(body, "lessons")}
    check(set(rowmap[LESSON]) >= {"level", "title", "summary", "qcount", "href"},
          f"每行有等级、标题、一句话、题数、地址：{sorted(rowmap[LESSON])}")
    want_n = sum(1 for q in bank_used if q.get("课文") == LESSON)
    check(want_n > 0 and rowmap[LESSON]["qcount"] == want_n,
          f"题数跟题库一致：{rowmap[LESSON]['qcount']} / {want_n}")
    check(rowmap[NOQ]["qcount"] == 0, f"没题的课题数 0：{rowmap[NOQ]['qcount']}")
    check(rowmap[LESSON]["href"] == READ + LESSON, f"点标题去 #教材?lesson=…：{rowmap[LESSON]['href']}")
    lv = [r["level"] for r in lst(body, "lessons")]
    check(lv == sorted(lv, reverse=True), "N5 在前，N1 在后")

    st, body = post("/lesson/list", lesson_level="全部", keyword="")
    check(codes(body) == allc, "等级「全部」、关键字空：跟不给一样")
    n4 = [d["code"] for d in lessons if d["level"] == "N4"]
    st, body = post("/lesson/list", lesson_level="N4")
    got = codes(body)
    check(len(got) == len(n4) and set(got) == set(n4), f"N4：{len(got)} 课（文件里 {len(n4)}）")
    check(all(r["level"] == "N4" for r in lst(body, "lessons")), "N4：每行都是 N4")

    st, body = post("/lesson/list", keyword="ようだ")
    check(LESSON in codes(body), f"日语关键字「ようだ」找到 {LESSON}：{codes(body)}")
    st, body = post("/lesson/list", keyword="  ようだ　 ".strip(" ") + "  ")
    check(LESSON in codes(body), "首尾有空白也一样找得到")
    st, body = post("/lesson/list", keyword="推测、比喻")
    check(LESSON in codes(body), f"按一句话找：{codes(body)}")
    spaced = next(d for d in lessons if " " in d["title"])
    kw = " ".join(spaced["title"].split(" ")[:2])
    st, body = post("/lesson/list", keyword=kw)
    check(spaced["code"] in codes(body), f"带空格的关键字「{kw}」找到 {spaced['code']}：{codes(body)[:5]}")
    # 条目名：找一个只在条目名里出现、标题和一句话里都没有的
    lbl = one("SELECT il.lesson, i.label FROM item_lesson il JOIN item i ON i.code = il.item"
              " JOIN lesson l ON l.code = il.lesson"
              " WHERE instr(l.title, i.label) = 0 AND instr(l.summary, i.label) = 0"
              " AND length(i.label) >= 2 LIMIT 1")
    if lbl:
        st, body = post("/lesson/list", keyword=lbl["label"])
        check(lbl["lesson"] in codes(body),
              f"按条目名「{lbl['label']}」找到 {lbl['lesson']}（标题、一句话里都没有这个词）")
    st, body = post("/lesson/list", lesson_level="N5", keyword="ようだ")
    check(st == 200 and LESSON not in codes(body), "等级和关键字一起筛：N5 里没有 N4 那课")
    check((body.get("form") or {}).get("lesson_level") == "N5", "填回表单的是这次用的等级")
    st, body = post("/lesson/list", keyword="没有这种课zzz")
    check(st == 200 and lst(body, "lessons") == [], "搜不到：空表，不报错")
    check((body.get("state") or {}).get("lesson_count") == "共0课", "搜不到时课数是 0")
    st, body = post("/lesson/list", keyword="%")
    n_pct = sum(1 for d in lessons if "%" in d["title"] or "%" in d["summary"])
    check(len(codes(body)) == n_pct and n_pct < len(lessons),
          f"「%」按字面找，不是通配：{len(codes(body))} 课")
    st, body = post("/lesson/list", keyword="_")
    check(len(codes(body)) < len(lessons), "「_」也按字面找")

    # ------------------------------------------------------------------
    print("二、读一课")
    st, body = post("/lesson/one", lesson=LESSON)
    rd = (body.get("state") or {}).get("reading") or {}
    src = by_code[LESSON]
    check(st == 200 and rd.get("code") == LESSON, f"拉回来的是这一课：{rd.get('code')}")
    check(rd.get("head") == f"《{src['title']}》　{src['level']}", f"抬头：{rd.get('head')}")
    check(rd.get("summary") == src["summary"] and rd.get("explanation") == src["explanation"],
          "一句话、讲解原样")
    check(rd.get("formation") == (src.get("formation") or ""), f"接续：{rd.get('formation')}")
    check(rd.get("missing") == "", "找到了：missing 是空的")
    exs = json.loads(src["examples"])
    got = lst(body, "examples") or []
    check(len(exs) > 1 and len(got) == len(exs), f"例句拆成 {len(got)} 行（JSON 里 {len(exs)} 句）")
    check(got == [{"jp": e["jp"], "zh": e.get("zh", "")} for e in exs], "例句的 jp / zh 按原顺序")
    items = lst(body, "lesson_items") or []
    want = rows("SELECT i.code, i.label, n.label AS point_label FROM item_lesson il"
                " JOIN item i ON i.code = il.item JOIN node n ON n.code = i.point"
                " WHERE il.lesson = ?", LESSON)
    check(len(want) > 0 and sorted(items, key=lambda x: x["code"]) == sorted(want, key=lambda x: x["code"]),
          f"挂着的条目带知识点名：{items}")
    check(rd.get("qcount") == want_n and rd.get("practice") == QUIZ + LESSON,
          f"有题：{rd.get('qcount')} 道，「练这一课」去 {rd.get('practice')}")
    check(rd.get("ask", "").startswith("#") and "问" not in rd.get("ask", ""),
          f"「问老师」的地址编过码：{rd.get('ask')}")
    check(len(lst(body, "lessons") or []) == len(lessons), "顺带把课文表换回全部（表单被清回默认了）")
    check(not body.get("messages"), "读课不推消息")
    check(body.get("form") == {"lesson_level": "全部", "keyword": ""}, "读课：表单填回默认，跟换回全部的课文表一致")

    st, body = post("/lesson/one", lesson=NOQ)
    rd = (body.get("state") or {}).get("reading") or {}
    check(st == 200 and rd.get("code") == NOQ, "没题的课照样能读")
    check(len(lst(body, "examples") or []) > 0, "对照：没题的课也有例句")
    check(rd.get("qcount") == 0 and rd.get("practice") == "", f"没题：不给「练这一课」的地址（{rd.get('practice')!r}）")
    check("还没有题" in (rd.get("quiz_note") or ""), f"没题时的说明：{rd.get('quiz_note')}")

    st, body = post("/lesson/one", lesson="hb-no such")
    rd = (body.get("state") or {}).get("reading") or {}
    check(st == 200 and rd.get("code") == "hb-no such", "不存在的课：code 原样带回（页面靠它对上地址）")
    check("没有这一课" in (rd.get("missing") or "") and "hb-no such" in rd.get("missing", ""),
          f"不存在的课：说清楚是哪一课没有：{rd.get('missing')}")
    check(not lst(body, "examples") and not rd.get("head"), "不存在的课：没有例句、没有抬头")
    check(not body.get("messages"), "不存在的课：不推消息（这页没有消息流，会落到别的界面）")
    check(rd.get("back") == "#%E6%95%99%E6%9D%90", "不存在的课：照样给「回课文表」的地址")
    st, body = post("/lesson/one")
    check(st == 400 and "lesson" in (body.get("error") or ""), f"不给 lesson：{st} {body.get('error')}")

    # ------------------------------------------------------------------
    print("三、学习进度（还没答过）")
    nodes = rows("SELECT count(*) n FROM node")[0]["n"]
    st, body = post("/progress/page")
    pg = (body.get("state") or {}).get("prog") or {}
    check(st == 200 and pg.get("total") == nodes, f"总知识点 {pg.get('total')}（库里 {nodes}）")
    check(pg.get("empty") == 1 and pg.get("answers") == 0, "没答过：empty=1、答题 0")
    check(pg.get("head") == f"已掌握 0 / 总知识点 {nodes}", f"概览：{pg.get('head')}")
    check(pg.get("rate_text") == "正确率 —", f"没答过不算正确率：{pg.get('rate_text')}")
    check(pg.get("score_text") == "平均得分 —", f"没打过分不算平均得分：{pg.get('score_text')}")
    check(pg.get("quiz_link") == "#%E5%81%9A%E9%A2%98", "去做题页的地址")
    nxt = lst(body, "next") or []
    check(len(nxt) > 0 and all(r["depth"] == 0 for r in nxt), f"对照：现在能学有根节点：{[r['label'] for r in nxt]}")
    check(lst(body, "doing") == [] and lst(body, "recent") == [] and lst(body, "scores") == [],
          "在学、最近作答、得分都是空的")
    lvs = lst(body, "levels") or []
    check([r["level"] for r in lvs] == ["N5", "N4", "N3", "N2", "N1"], "按等级五行 N5..N1")
    check(all(r["tally"].startswith("0/") and r["answers"] == 0 for r in lvs), f"都是 0：{lvs}")
    want_pts = rows("SELECT count(DISTINCT i.point) n FROM question q JOIN item i ON i.code = q.item"
                    " WHERE q.level = 'N4'")[0]["n"]
    n4row = next(r for r in lvs if r["level"] == "N4")
    check(n4row["tally"] == f"0/{want_pts}", f"N4 要学的知识点数：{n4row['tally']}（库里算出 {want_pts}）")
    check(not body.get("messages"), "进页面不推消息")

    # ------------------------------------------------------------------
    print("四、学习进度（经做题页答一对一错之后）")

    def quiz_state():
        return one("SELECT * FROM quiz_state WHERE learner = 'me'")

    def answer(right, shown):
        """shown 是出题接口的响应：选项打乱过，按题卡找界面上的字母"""
        q = one("SELECT * FROM question WHERE code = ?", quiz_state()["current"])
        if q["qtype"] == "选择":
            cd = (shown.get("state") or {}).get("card") or {}
            return q, post("/quiz/answer", choice=choice_key(cd, q["stem"], q["answer"], right))
        return q, post("/quiz/answer", given=q["answer"] if right else "ぜんぜんちがう")

    st, shown = post("/quiz/lesson", lesson=LESSON)
    check(st == 200 and quiz_state().get("current"), "按课文出了第一道")
    q1, (st1, b1) = answer(True, shown)
    check(st1 == 200 and (b1.get("state") or {}).get("card", {}).get("ok") in (1, "1", True, "是", "对"),
          f"第一道答对：{(b1.get('state') or {}).get('card', {}).get('ok')}")
    # 第二道也要是这一课的：按课练一轮里本课只出 1 道（其余是别的条目的
    # 对比题），所以用「再来一轮」——新的一轮第一道是本课另一道题
    st, shown = post("/quiz/again")
    q2, (st2, b2) = answer(False, shown)
    check(st2 == 200 and rows("SELECT count(*) n FROM attempt")[0]["n"] == 2, "第二道答错，流水两行")

    point = one("SELECT point FROM item WHERE code = ?", q1["item"])["point"]
    plabel = one("SELECT label FROM node WHERE code = ?", point)["label"]
    st, body = post("/progress/page")
    pg = (body.get("state") or {}).get("prog") or {}
    check(pg.get("empty") == 0 and pg.get("answers") == 2 and pg.get("right") == 1,
          f"概览：答 {pg.get('answers')} 对 {pg.get('right')}")
    check(pg.get("answers_text") == "累计答题 2" and pg.get("rate_text") == "正确率 50%",
          f"概览文字：{pg.get('answers_text')}，{pg.get('rate_text')}")
    check(pg.get("head") == f"已掌握 0 / 总知识点 {nodes}", "还没达标：已掌握 0")
    doing = lst(body, "doing") or []
    check(len(doing) == 1 and doing[0]["label"] == plabel and doing[0]["tally"] == "1/2",
          f"在学：{doing}")
    check(doing and doing[0]["verdict"].startswith("得分 ") and "差" in doing[0]["verdict"],
          f"还没达标，说得分差几分：{doing and doing[0]['verdict']}")
    rec = lst(body, "recent") or []
    check([r["result"] for r in rec] == ["错", "对"], f"最近作答新的在前：{[r['result'] for r in rec]}")
    check(all(r["label"] == plabel for r in rec), f"最近作答关联到知识点名：{[r['label'] for r in rec]}")
    ilabel = one("SELECT label FROM item WHERE code = ?", q2["item"])["label"]
    check(rec and rec[0]["item_label"] == ilabel and rec[0]["at"], f"带条目名和时间：{rec[:1]}")
    n4row = next(r for r in lst(body, "levels") if r["level"] == "N4")
    n5row = next(r for r in lst(body, "levels") if r["level"] == "N5")
    check(n4row["answers"] == 2 and n5row["answers"] == 0, f"按等级：N4 答过 2，N5 答过 0")

    # 刷到达标：接着记对的，直到掌握（经 /learn/answer，跟做题页同一套汇总；
    # 掌握看得分，过 80 为止，几道才到由得分算法定）
    extra = 0
    for _ in range(20):
        _, r = post("/learn/answer", point=point, correct=1)
        extra += 1
        if r.get("mastered") == "1":
            break
    right_n, total_n = 1 + extra, 2 + extra
    st, body = post("/progress/page")
    pg = (body.get("state") or {}).get("prog") or {}
    doing = lst(body, "doing") or []
    check(pg.get("head") == f"已掌握 1 / 总知识点 {nodes}", f"达标后：{pg.get('head')}（又答对 {extra} 道）")
    check(doing and doing[0]["tally"] == f"{right_n}/{total_n}" and doing[0]["verdict"].startswith("达标"),
          f"在学里标达标：{doing}")
    in_n4 = rows("SELECT 1 FROM question q JOIN item i ON i.code = q.item"
                 " WHERE q.level = 'N4' AND i.point = ?", point)
    n4row = next(r for r in lst(body, "levels") if r["level"] == "N4")
    check(bool(in_n4) and n4row["tally"] == f"1/{want_pts}", f"按等级：N4 已掌握 {n4row['tally']}")
    check(pg.get("answers") == total_n and pg.get("rate_text") == f"正确率 {right_n * 100 // total_n}%",
          f"{total_n} 题 {right_n} 对：{pg.get('rate_text')}")
    st, body = post("/progress/page", line="95", keep="95")
    doing = lst(body, "doing") or []
    check(doing and "差" in doing[0]["verdict"], f"达标线从请求来：{doing and doing[0]['verdict']}")

    # 答题时自动打分：每次作答都重算，分变了才记，当前分是最新那行
    sc = lst(body, "scores") or []
    auto = rows("SELECT value FROM score WHERE learner = 'me' AND point = ? ORDER BY id", point)
    check(len(sc) == 1 and sc[0]["label"] == plabel and sc[0]["value"] == auto[-1]["value"] and sc[0]["at"],
          f"答过题就有得分（自动打的）：{sc}，历史 {[a['value'] for a in auto]}")
    want = (f"+{auto[-1]['value'] - auto[-2]['value']}" if auto[-1]["value"] > auto[-2]["value"]
            else f"−{auto[-2]['value'] - auto[-1]['value']}")
    check(len(auto) >= 2 and sc and sc[0]["delta"] == want, f"变化跟上一次比：{sc and sc[0]['delta']}（要 {want}）")
    pg = (body.get("state") or {}).get("prog") or {}
    check(pg.get("score_text") == f"平均得分 {auto[-1]['value']}", f"概览有平均得分：{pg.get('score_text')}")
    post("/score/add", point=point, value="70")
    st, body = post("/progress/page")
    sc = lst(body, "scores") or []
    check(len(sc) == 1 and sc[0]["value"] == 70 and sc[0]["label"] == plabel, f"再记一次分，当前分是它：{sc}")
    d = 70 - auto[-1]["value"]
    check(sc and sc[0]["delta"] == (f"+{d}" if d > 0 else f"−{-d}" if d < 0 else "±0"),
          f"变化：{sc and sc[0]['delta']}")
    # 排序：分低的在前。另一个人答两个点，一个全对、一个全错
    pts = [r["code"] for r in rows("SELECT code FROM node ORDER BY code LIMIT 3")]
    for _ in range(3):
        post("/learn/answer", learner="sorter", point=pts[0], correct=1)
    post("/learn/answer", learner="sorter", point=pts[1], correct=0)
    post("/learn/answer", learner="sorter", point=pts[2], correct=1)
    st, body = post("/progress/page", learner="sorter")
    sc = lst(body, "scores") or []
    vals = [r["value"] for r in sc]
    check([r["code"] for r in sc] == [pts[1], pts[2], pts[0]] and vals == sorted(vals),
          f"按分从低到高：{[(r['code'], r['value']) for r in sc]}")
    check(all(r["delta"] == "首次" for r in sc[1:2]), f"只打过一次分的写「首次」：{[r['delta'] for r in sc]}")
    pg = (body.get("state") or {}).get("prog") or {}
    check(pg.get("score_text") == f"平均得分 {round(sum(vals) / len(vals))}", f"平均得分：{pg.get('score_text')} {vals}")
    st, body = post("/progress/page", learner="someone")
    pg = (body.get("state") or {}).get("prog") or {}
    check(pg.get("empty") == 1 and lst(body, "scores") == [], "别的学习者：空的（学习者默认是 me）")

    # ------------------------------------------------------------------
    print("五、知识图谱浮层：答对/答题")
    st, body = post("/node/one", code=point)
    check(st == 200 and (body.get("state") or {}).get("node_tally") == f"答对 {right_n} / 答题 {total_n}（已掌握）",
          f"做过的点：{(body.get('state') or {}).get('node_tally')}")
    check((body.get("form") or {}).get("code") == point and (body.get("lists") or {}).get("items"),
          "对照：原来的详情照旧（表单、条目）")
    other = one("SELECT code FROM node WHERE code <> ? LIMIT 1", point)["code"]
    st, body = post("/node/one", code=other)
    check((body.get("state") or {}).get("node_tally") == "还没做过", f"没做过的点：{(body.get('state') or {}).get('node_tally')}")
    st, body = post("/node/one", code=point, learner="someone")
    check((body.get("state") or {}).get("node_tally") == "还没做过", "别的学习者看不到 me 的成绩")
    post("/learn/answer", point=other, correct=0)
    st, body = post("/node/one", code=other)
    check((body.get("state") or {}).get("node_tally") == "答对 0 / 答题 1", f"只答错过：{(body.get('state') or {}).get('node_tally')}")
    check((body.get("state") or {}).get("node_score") not in (None, ""), f"答过就有得分：{(body.get('state') or {}).get('node_score')!r}")
    st, body = post("/node/one", code=point)
    check((body.get("state") or {}).get("node_score") == "70", f"浮层的得分是当前分：{(body.get('state') or {}).get('node_score')!r}")
    third = one("SELECT code FROM node WHERE code NOT IN (?, ?) LIMIT 1", point, other)["code"]
    st, body = post("/node/one", code=third)
    check((body.get("state") or {}).get("node_score") == "", "没打过分的点：得分是空的（浮层不显示）")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
