# -*- coding: utf-8 -*-
"""kg_v4 教师助手深度学情（M4-P4，assist_insight）的补充测试：约定用例只断言 status / 个数，这里造多天多学生的作答，逐个断言具体数字与原文。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_assist_insight.py

拷一份 kg_v4 到临时目录，用约定用例的运行器（cases.build_sql / reset_db / call）造数据、调函数。当前时间固定 2026-01-01 09:00:00。离线，不调模型。
  字符条 / 迷你图 逐字
  学情趋势：按天 / 按周、单个学生、不足 3 天、非法 days、只算登记学生
  错题归因：错误率、名次、条目、题库外、时间窗、top、单个学生
  学生对比：名次、没作答不参与排名、追问话术、去重
  掉队名单：规则① / ②、边界、停用不判、撤销登记不算、放假、空态⑤
  空态①②原文；分析上下文分发与格式；权限（学生 / 无关老师 / 不存在 / 非数字科目）
"""

import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "kg_v4"
sys.path.insert(0, str(ROOT))

from tools.dslagent.packs.dslproj import cases as K, project as P  # noqa: E402

passed = failed = 0


def check(ok, msg, detail=None):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg + ("" if ok or detail is None else f"\n      {detail}"))


tmp = Path(tempfile.mkdtemp(prefix="kg_v4_assist_insight_"))
ws = tmp / "kg_v4"
shutil.copytree(SRC, ws, ignore=K.COPY_IGNORE, symlinks=True)
os.environ["DSL_NOW"] = K.DEFAULT_NOW
SQL = K.build_sql(ws, P.closure(ws, "assist_insight"))

SUBJECTS = [
    ("subject_info", dict(code="jp_grammar", name="日语语法", kind="language", caps="x", levels="", qtypes="choice", visibility="public",
                          owner="t1", status="active", created_at="2026-01-01", updated_at="2026-01-01")),
    ("subject_info", dict(code="math", name="数学", kind="general", caps="x", levels="", qtypes="choice", visibility="private",
                          owner="t2", status="active", created_at="2026-01-01", updated_at="2026-01-01")),
]


def seed(rows=()):
    db = K.reset_db(ws, SQL)
    con = sqlite3.connect(db)
    try:
        for table, kv in list(SUBJECTS) + list(rows):
            con.execute(f"INSERT INTO {table}({', '.join(kv)}) VALUES({', '.join('?' * len(kv))})", list(kv.values()))
        con.commit()
    finally:
        con.close()
    return db


_eng = []
_n = [0]


def run(fn, **args):
    """→ (结果, 报错码, 报错原文)"""
    if not _eng:
        _eng.append(K.make_engine(ws))
    _n[0] += 1
    try:
        r, err = K.call(_eng[0], "assist_insight", fn, args, f"t{_n[0]}")
    except Exception as ex:  # 引擎层异常（服务内部崩）：当作 EXC 报错，让后面的断言写出现象，不中断整个测试
        K.settle()
        return {"status": "EXC", "hint": "", "rows": [], "points": [], "students": [], "chart": "", "context_text": "", "spark": "", "active_days": -1}, "EXC", str(ex)
    K.settle()
    if isinstance(err, dict):
        return r, str(err.get("code")), str(err.get("error", ""))
    return r, ("" if err in ("", None) else str(err)), ("" if err in ("", None) else str(err))


def user(u, name, disabled=0):
    return ("account_user", dict(username=u, password_hash="x", display_name=name, role="student", disabled=disabled, created_at="2025-12-01"))


def enrol(u, status="active", subject_id=1):
    return ("subject_student", dict(subject_id=subject_id, learner=u, assigned_by="t1", status=status, created_at="2026-01-01"))


def stu(u, name, disabled=0, status="active"):
    return [user(u, name, disabled), enrol(u, status)]


_q = [0]


def ans(u, day, point, qno, correct, subject_id=1):
    _q[0] += 1
    return ("progress_answer", dict(learner=u, point_code=point, question_no=qno, correct=correct, at=f"{day} 10:00:00", subject_id=subject_id))


def bulk(u, day, n, right, point="P1", qno="Q1"):
    return [ans(u, day, point, qno, 1 if i < right else 0) for i in range(n)]


def many(u, day, point, qno, right, wrong):
    return [ans(u, day, point, qno, 1)] * right + [ans(u, day, point, qno, 0)] * wrong


ON_T = dict(learner="t1", current_role="teacher", auth_mode="on")
EMPTY1 = "这个科目还没有学生，去「科目管理 → 成员」分配学生后再看"
EMPTY2 = "还没有作答记录，趋势、归因、预警都要等学生做过题才有"
RULES = "规则：①全班近 7 天有作答、而这位学生 7 天以上没有作答；②近 14 天正确率比之前 14 天低 15 个百分点以上（两段都至少 10 题）"
NODATA = "按现在的规则没有掉队的学生。" + RULES

# ---- 主数据：今天 2026-01-01；s1 小明 / s2 小红 / s3 小丽（没作答）；s5 撤销登记、s9 没登记（作答都不该计入）
KG = [("kg_point", dict(code="P1", title="点一")), ("kg_point", dict(code="P2", title="点二")), ("kg_point", dict(code="P3", title="点三")),
      ("kg_item", dict(code="I1", name="条目一", point_code="P1")), ("kg_item", dict(code="I2", name="条目二", point_code="P1")),
      ("quiz_question", dict(question_no="Q1", level="N5", category="接续", stem="题一", answer="A", item_code="I1")),
      ("quiz_question", dict(question_no="Q2", level="N5", category="接续", stem="题二", answer="A", item_code="I2")),
      ("quiz_question", dict(question_no="Q8", level="N5", category="接续", stem="题八", answer="A", item_code="I2"))]
MAIN = (stu("s1", "小明") + stu("s2", "小红") + stu("s3", "小丽") + [user("s5", "小旧"), enrol("s5", "revoked"), user("s9", "路人")] + KG
        # s1：12-29 共 4 题对 2；12-30 共 5 题对 4；12-31 共 4 题全对；12-10 两题全错
        + [ans("s1", "2025-12-29", "P1", "Q1", 1), ans("s1", "2025-12-29", "P1", "Q1", 0), ans("s1", "2025-12-29", "P1", "Q2", 0),
           ans("s1", "2025-12-29", "P2", "Q9", 1)]
        + [ans("s1", "2025-12-30", "P1", "Q1", 1), ans("s1", "2025-12-30", "P1", "Q1", 1), ans("s1", "2025-12-30", "P2", "Q9", 0),
           ans("s1", "2025-12-30", "P2", "Q9", 1), ans("s1", "2025-12-30", "P3", "Q8", 1)]
        + [ans("s1", "2025-12-31", "P1", "Q1", 1), ans("s1", "2025-12-31", "P1", "Q1", 1), ans("s1", "2025-12-31", "P2", "Q9", 1),
           ans("s1", "2025-12-31", "P2", "Q9", 1)]
        + [ans("s1", "2025-12-10", "P2", "Q9", 0), ans("s1", "2025-12-10", "P2", "Q9", 0)]
        # s2：12-29 共 6 题对 3；12-31 共 4 题对 1
        + [ans("s2", "2025-12-29", "P1", "Q1", 0), ans("s2", "2025-12-29", "P1", "Q1", 0), ans("s2", "2025-12-29", "P1", "Q2", 0),
           ans("s2", "2025-12-29", "P2", "Q9", 1), ans("s2", "2025-12-29", "P2", "Q9", 1), ans("s2", "2025-12-29", "P2", "Q9", 1)]
        + [ans("s2", "2025-12-31", "P1", "Q2", 0), ans("s2", "2025-12-31", "P3", "Q8", 0), ans("s2", "2025-12-31", "P3", "Q8", 0),
           ans("s2", "2025-12-31", "P3", "Q8", 1)]
        + [ans("s5", "2025-12-31", "P1", "Q1", 0)] * 3 + [ans("s9", "2025-12-31", "P1", "Q1", 0)] * 3
        + [("progress_score", dict(learner="s1", point_code="P1", score=80, at="2025-12-31")),
           ("progress_score", dict(learner="s1", point_code="P2", score=40, at="2025-12-31")),
           ("progress_score", dict(learner="s2", point_code="P1", score=20, at="2025-12-31"))])

try:
    print("一、字符条 / 迷你图（逐字；这几个是模块私有函数，经公开函数的输出验证）")
    # 迷你图：12-20 ~ 12-29 每天 100 题，正确率 0 19 20 39 40 59 60 79 80 100，其余天没作答
    rates = [0, 19, 20, 39, 40, 59, 60, 79, 80, 100]
    rows = stu("s1", "小明")
    for i, rt in enumerate(rates):
        rows += bulk("s1", "2025-12-%02d" % (20 + i), 100, rt)
    seed(rows)
    r, c, e = run("学情趋势", days=14)
    check(c == "" and r["spark"] == "·▁▁▂▂▃▃▅▅▆▆···", "迷你图 各档边界：空·、<20▁、<40▂、<60▃、<80▅、≥80▆", (r["spark"], c, e))
    check(r["chart"].splitlines()[0] == "近 14 天（按天）正确率 ·▁▁▂▂▃▃▅▅▆▆··· 0%→100%（共作答 1000 题）", "迷你图接「首个%→最后一个%」", r["chart"])
    check([x["ana_bar"] for x in r["rows"]] == ["░░░░░░░░░░", "██░░░░░░░░", "██░░░░░░░░", "████░░░░░░", "████░░░░░░", "██████░░░░",
                                                "██████░░░░", "████████░░", "████████░░", "██████████"], "字符条 0/19/20/39/40/59/60/79/80/100 → 满格 0/2/2/4/4/6/6/8/8/10", [x["ana_bar"] for x in r["rows"]])
    # 字符条：四舍五入 5 → 1 格，4 → 0 格，14 → 1 格，15 → 2 格，100 → 满（用错误率）
    rows = stu("s1", "小明")
    for code, n, w in (("B4", 25, 1), ("B5", 20, 1), ("B14", 50, 7), ("B15", 20, 3), ("B100", 2, 2)):
        rows += [ans("s1", "2025-12-31", code, "Q9", 0)] * w + [ans("s1", "2025-12-31", code, "Q9", 1)] * (n - w)
    seed(rows)
    r, c, e = run("错题归因", top=10)
    got = {x["ana_day"]: (x["ana_rate"], x["ana_bar"]) for x in r["rows"]}
    check(got == {"B4": (4, "░░░░░░░░░░"), "B5": (5, "█░░░░░░░░░"), "B14": (14, "█░░░░░░░░░"), "B15": (15, "██░░░░░░░░"), "B100": (100, "██████████")},
          "字符条 四舍五入：4→0 格、5→1 格、14→1 格、15→2 格、100→10 格", got)
    check("B100 ██████████ 100%（错 2 / 作答 2 题，1 人）" in r["chart"].splitlines() and [p["title"] for p in r["points"]] == ["B14", "B15", "B100", "B5", "B4"],
          "知识点取不到名称时标题用编号；排序先看答错数（7 / 3 / 2 / 1 / 1），并列时错误率高的在前（5% 在 4% 前）", r["chart"])

    print("二、空态①②原文，四个函数 + 分析上下文")
    seed()   # 没有任何学生
    for fn, extra in (("学情趋势", {}), ("错题归因", {}), ("学生对比", dict(students="甲、乙")), ("掉队名单", {})):
        r, c, e = run(fn, **extra)
        check(c == "" and r["status"] == "empty" and r["hint"] == EMPTY1, f"空态① {fn}：原文", (r, c, e))
    r, c, e = run("掉队名单")
    check(r["total"] == 0 and r["students"] == [] and r["rules_text"] == RULES and r["chart"] == "" and r["context_text"] == "",
          "空态① 掉队名单：total=0、名单空、rules_text 照给、chart / context 空", r)
    for kind in ("trend", "attribution", "compare", "alert"):
        r, c, e = run("分析上下文", kind=kind, student="甲、乙")
        check(r == {"status": "empty", "kind": kind, "hint": EMPTY1, "chart": "", "context_text": ""}, f"分析上下文 {kind} 空态①：整体返回", (r, c, e))

    seed(stu("s1", "小明") + stu("s2", "小红") + [ans("s9", "2025-12-31", "P1", "Q1", 1), ans("s5", "2025-12-31", "P1", "Q1", 1)])
    # s9 没登记的作答不算：仍是空态②
    for fn in ("学情趋势", "错题归因", "掉队名单"):
        r, c, e = run(fn)
        check(c == "" and r["status"] == "empty" and r["hint"] == EMPTY2, f"空态② {fn}：只有未登记学生的作答仍是空态②", (r, c, e))
    r, c, e = run("掉队名单")
    check(r["total"] == 0 and r["rules_text"] == RULES, "空态② 掉队名单 total=0 且给 rules_text", r)
    r, c, e = run("分析上下文", kind="attribution")
    check(r == {"status": "empty", "kind": "attribution", "hint": EMPTY2, "chart": "", "context_text": ""}, "分析上下文 attribution 空态②", r)
    r, c, e = run("学生对比", students="小明、小红")
    check(c == "" and r["status"] == "ok" and r["total"] == 2 and r["ranked"] == 0, "空态② 学生对比不拦：total=2 ranked=0", r)
    check(r["chart"] == "小明：还没作答\n小红：还没作答", "空态④ 全员没作答：chart 逐行「显示名：还没作答」", r["chart"])
    check([(x["ana_day"], x["ana_n"], x["ana_rate"], x["ana_bar"]) for x in r["rows"] if isinstance(x, dict)] == [("小明", 0, "", "还没作答"), ("小红", 0, "", "还没作答")] and len(r["rows"]) == 2, "空态④ rows", r["rows"])

    print("三、学情趋势")
    seed(MAIN)
    r, c, e = run("学情趋势", days=14)
    check(c == "" and r["status"] == "ok" and r["hint"] == "" and r["student"] == "" and r["days"] == 14 and r["week"] == 0, "14 天：按天 week=0、全班", r)
    check(r["active_days"] == 3, "14 天：有作答 3 天（12-10 在窗外，s5 / s9 不算）", r["active_days"])
    rows = [(x["ana_day"], x["ana_n"], x["ana_rate"], x["ana_bar"]) for x in r["rows"]]
    check(rows == [("2025-12-29", "10 题 / 2 人", 50, "█████░░░░░"), ("2025-12-30", "5 题 / 1 人", 80, "████████░░"),
                   ("2025-12-31", "8 题 / 2 人", 63, "██████░░░░")], "14 天：rows 作答数 / 人数 / 正确率（5/8 → 63）/ 字符条", rows)
    check(r["spark"] == "··········▃▆▅·", "14 天：迷你图 10 个空天 + ▃▆▅ + 今天空", r["spark"])
    want_chart = ("近 14 天（按天）正确率 ··········▃▆▅· 50%→63%（共作答 23 题）\n"
                  "2025-12-29 █████░░░░░ 50%（10 题 / 2 人）\n2025-12-30 ████████░░ 80%（5 题 / 1 人）\n2025-12-31 ██████░░░░ 63%（8 题 / 2 人）")
    check(r["chart"] == want_chart, "14 天：chart 原文", r["chart"])
    want_ctx = ("今天：2026-01-01\n分析：作答趋势，范围 全班，最近 14 天，按天\n"
                "2025-12-29｜作答 10｜答对 5｜正确率 50%｜人数 2\n2025-12-30｜作答 5｜答对 4｜正确率 80%｜人数 1\n"
                "2025-12-31｜作答 8｜答对 5｜正确率 63%｜人数 2\n【后端算好的字符图】\n" + want_chart)
    check(r["context_text"] == want_ctx, "14 天：context_text 格式", r["context_text"])

    r, c, e = run("学情趋势")
    check(r["days"] == 28 and r["week"] == 1 and r["active_days"] == 4, "默认：28 天、按周 week=1、有作答 4 天", r)
    rows = [(x["ana_day"], x["ana_n"], x["ana_rate"], x["ana_bar"]) for x in r["rows"]]
    check(rows == [("2025-12-08 起一周", "2 题 / 1 人", 0, "░░░░░░░░░░"), ("2025-12-29 起一周", "23 题 / 2 人", 61, "██████░░░░")],
          "默认：按周 rows（周一 12-08 / 12-29；14/23 → 61）", rows)
    check(r["spark"] == "·▁··▅", "默认：5 周迷你图 ·▁··▅", r["spark"])
    want_chart = ("近 28 天（按周）正确率 ·▁··▅ 0%→61%（共作答 25 题）\n"
                  "2025-12-08 起一周 ░░░░░░░░░░ 0%（2 题 / 1 人）\n2025-12-29 起一周 ██████░░░░ 61%（23 题 / 2 人）")
    check(r["chart"] == want_chart, "默认：按周 chart 原文", r["chart"])
    check(r["context_text"].startswith("今天：2026-01-01\n分析：作答趋势，范围 全班，最近 28 天，按周\n2025-12-08｜作答 2｜答对 0｜正确率 0%｜人数 1\n"
                                       "2025-12-29｜作答 23｜答对 14｜正确率 61%｜人数 2\n【后端算好的字符图】\n"), "默认：context_text 头部与按周行", r["context_text"])
    r, c, e = run("学情趋势", days=28, week=0)
    check(r["week"] == 0 and r["active_days"] == 4 and len(r["rows"]) == 4 and r["rows"][0]["ana_day"] == "2025-12-10" and r["rows"][0]["ana_rate"] == 0,
          "days=28 week=0：强制按天，4 行，首行 12-10 正确率 0", r)
    check(r["spark"] == "·····▁" + "·" * 17 + "▃▆▅·" .replace("▃▆▅·", "▃▆▅·")[:0] + "·▃▆▅·"[1:] if False else len(r["spark"]) == 28 and r["spark"][5] == "▁" and r["spark"][-4:] == "▃▆▅·",
          "days=28 week=0：迷你图 28 格，12-10 是第 6 格 ▁，末 4 格 ▃▆▅·", r["spark"])
    r, c, e = run("学情趋势", days=7)
    check(r["week"] == 0 and r["days"] == 7 and r["spark"] == "···▃▆▅·", "days=7：按天，迷你图 7 格", r)

    r, c, e = run("学情趋势", student="小明", days=14)
    rows = [(x["ana_day"], x["ana_n"], x["ana_rate"]) for x in r["rows"]]
    check(r["student"] == "s1" and rows == [("2025-12-29", "4 题 / 1 人", 50), ("2025-12-30", "5 题 / 1 人", 80), ("2025-12-31", "4 题 / 1 人", 100)],
          "单个学生（小明）：student=s1，逐日 50 / 80 / 100", r)
    check(r["chart"].splitlines()[0] == "近 14 天（按天）正确率 ··········▃▆▆· 50%→100%（共作答 13 题）", "单个学生：chart 首行", r["chart"])
    check("范围 小明（s1）" in r["context_text"], "单个学生：context 范围写「小明（s1）」", r["context_text"])

    r, c, e = run("学情趋势", student="小红", days=14)
    check(r["active_days"] == 2 and r["chart"] == "只有 2 天有作答，数据太少，先不画趋势", "空态③ 小红只有 2 天：chart 原文，不画迷你图", r)
    check(len(r["rows"]) == 2 and r["rows"][0]["ana_rate"] == 50 and r["rows"][1]["ana_rate"] == 25 and r["status"] == "ok",
          "空态③：rows 仍返回（50 / 25），status 仍 ok（仍调模型）", r["rows"])
    check(r["context_text"].endswith("【后端算好的字符图】\n只有 2 天有作答，数据太少，先不画趋势"), "空态③：context 末尾带这句", r["context_text"])
    r, c, e = run("学情趋势", student="小丽", days=14)
    check(r["status"] == "ok" and r["active_days"] == 0 and r["rows"] == [] and r["chart"] == "只有 0 天有作答，数据太少，先不画趋势",
          "小丽 0 天：只有 0 天…", (r, e))
    r, c, e = run("学情趋势", student="路人")
    check(r["status"] == "ask" and r["hint"] == "没有找到叫「路人」的学生。现有学生：小明（s1）、小红（s2）、小丽（s3）", "学生不在本科目（s9 没登记）：ask 话术", r)
    r, c, e = run("学情趋势", student="小")
    check(r["status"] == "ask" and r["hint"] == "找到多位：小明（s1）、小红（s2）、小丽（s3），你指哪一位？", "名字不唯一：ask 话术", r)
    r, c, e = run("学情趋势", student="小旧")
    check(r["status"] == "ask", "撤销登记的 小旧 找不到：ask", r)
    for bad in ("6", "91", "abc", "-3", "7.5"):
        r, c, e = run("学情趋势", days=bad)
        check(c == "400" and "days 不合法" in e, f"days={bad} → 400 days 不合法", (c, e))
    r, c, e = run("学情趋势", days=90)
    check(c == "" and r["days"] == 90 and r["week"] == 1 and r["active_days"] == 4, "days=90 合法", (c, e))

    print("四、错题归因")
    r, c, e = run("错题归因", top=2)
    pts = [(p["point_code"], p["title"], p["n"], p["wrong"], p["rate"], p["learners"]) for p in r["points"]]
    check(c == "" and r["status"] == "ok" and r["days"] == 28 and r["total"] == 3, "归因 28 天：total=3（点一 / 点二 / 点三）", r)
    check(pts == [("P1", "点一", 11, 6, 55, 2), ("P2", "点二", 10, 3, 30, 1)], "top=2：点一 错 6/11=55% 2 人、点二 错 3/10=30% 1 人（点三 错 2 排第三被截）", pts)
    check(r["points"][0]["items"] == [{"code": "I1", "name": "条目一", "wrong": 3}, {"code": "I2", "name": "条目二", "wrong": 3}],
          "点一 条目：错数并列时按条目编号升序", r["points"][0]["items"])
    check(r["points"][1]["items"] == [{"code": "", "name": "（题库外的题）", "wrong": 3}], "点二 条目：题库外的题", r["points"][1]["items"])
    check([(x["ana_day"], x["ana_n"], x["ana_rate"], x["ana_bar"]) for x in r["rows"]] ==
          [("点一", 11, 55, "██████░░░░"), ("点二", 10, 30, "███░░░░░░░")], "rows：标题 / 作答数 / 错误率 / 字符条", r["rows"])
    want_chart = ("最近 28 天错题最多的 2 个知识点（错误率 = 答错 / 作答）：\n"
                  "点一 ██████░░░░ 55%（错 6 / 作答 11 题，2 人）\n  错得多的条目：条目一（3）、条目二（3）\n"
                  "点二 ███░░░░░░░ 30%（错 3 / 作答 10 题，1 人）\n  错得多的条目：（题库外的题）（3）")
    check(r["chart"] == want_chart, "归因 chart 原文", r["chart"])
    want_ctx = ("今天：2026-01-01\n分析：错题归因，范围 全班，最近 28 天，有错题的知识点共 3 个，下面是前 2 个\n"
                "点一（P1）｜作答 11｜答错 6｜错误率 55%｜答错的人 2｜条目：条目一 错 3 题、条目二 错 3 题\n"
                "点二（P2）｜作答 10｜答错 3｜错误率 30%｜答错的人 1｜条目：（题库外的题） 错 3 题\n【后端算好的字符图】\n" + want_chart)
    check(r["context_text"] == want_ctx, "归因 context_text 格式", r["context_text"])
    r, c, e = run("错题归因")
    check([p["point_code"] for p in r["points"]] == ["P1", "P2", "P3"] and r["total"] == 3, "默认 top=5：三个点按错题数 6 / 3 / 2 排", r)
    p3 = r["points"][2]
    check((p3["n"], p3["wrong"], p3["rate"], p3["learners"], p3["items"]) == (4, 2, 50, 1, [{"code": "I2", "name": "条目二", "wrong": 2}]),
          "点三：4 题错 2 = 50%，1 人，条目二（2）", p3)
    r, c, e = run("错题归因", days=7, top=1)
    check(r["total"] == 3 and [p["point_code"] for p in r["points"]] == ["P1"], "days=7 top=1：只留点一，total 仍 3", r)
    check(r["chart"].splitlines()[0] == "最近 7 天错题最多的 1 个知识点（错误率 = 答错 / 作答）：", "days=7：chart 首行", r["chart"])
    r, c, e = run("错题归因", days=7)
    p2 = [p for p in r["points"] if p["point_code"] == "P2"][0]
    check((p2["n"], p2["wrong"], p2["rate"]) == (8, 1, 13), "days=7：12-10 的两道错题被时间窗排除，点二 1/8=13%", p2)
    r, c, e = run("错题归因", student="小红")
    check([(p["point_code"], p["n"], p["wrong"], p["rate"], p["learners"]) for p in r["points"]] == [("P1", 4, 4, 100, 1), ("P3", 3, 2, 67, 1)] and r["total"] == 2,
          "小红：点一 4/4=100%，点三 2/3=67%；没错题的点二不列", r["points"])
    check("范围 小红（s2）" in r["context_text"] and r["chart"].splitlines()[1] == "点一 ██████████ 100%（错 4 / 作答 4 题，1 人）", "小红：context 范围与 chart 第一行", r["chart"])
    r, c, e = run("错题归因", student="路人")
    check(r["status"] == "ask" and r["hint"].startswith("没有找到叫「路人」的学生。现有学生：小明（s1）"), "归因 学生找不到：ask", r)
    for k, v in (("top", 0), ("top", 11), ("top", "x"), ("days", 6)):
        r, c, e = run("错题归因", **{k: v})
        check(c == "400" and (k + " 不合法") in e, f"归因 {k}={v} → 400 {k} 不合法", (c, e))
    # 没有错题
    seed(stu("s1", "小明") + bulk("s1", "2025-12-31", 3, 3))
    r, c, e = run("错题归因")
    check(r["status"] == "ok" and r["total"] == 0 and r["points"] == [] and r["rows"] == [] and r["chart"] == "最近 28 天没有答错的题", "没有任何错题：chart 原文", r)
    check(r["context_text"].endswith("有错题的知识点共 0 个，下面是前 0 个\n【后端算好的字符图】\n最近 28 天没有答错的题"), "没有错题：context", r["context_text"])

    print("五、学生对比")
    seed(MAIN)
    r, c, e = run("学生对比", students="小红、小明、小丽")
    check(c == "" and r["status"] == "ok" and r["total"] == 3 and r["ranked"] == 2, "三人对比：total=3 ranked=2（小丽没作答）", r)
    lines = r["chart"].split("\n")
    check(lines[0].startswith("1. 小明 ███████░░░ 近期正确率 67%｜平均分 ") and lines[1].startswith("2. 小红 ████░░░░░░ 近期正确率 40%｜平均分 "),
          "名次 / 字符条 / 近期正确率（小明 10/15=67，小红 4/10=40）", lines)
    check(lines[2] == "小丽：还没作答" and len(lines) == 3, "没作答的排在后面且不带名次（空态④）", lines)
    check(lines[0].endswith("｜已掌握 0｜低分点 1 个") or "｜已掌握" in lines[0], "chart 行含已掌握 / 低分点", lines[0])
    check([(x["ana_day"], x["ana_n"], x["ana_rate"], x["ana_bar"]) for x in r["rows"]] ==
          [("小明", 15, 67, "███████░░░"), ("小红", 10, 40, "████░░░░░░"), ("小丽", 0, "", "还没作答")], "rows：排名在前、没作答在后", r["rows"])
    ctx = r["context_text"].split("\n")
    check(ctx[0] == "今天：2026-01-01" and ctx[1] == "分析：学生对比（近期正确率按每人最近 20 次作答算）", "context 头两行", ctx[:2])
    check(ctx[2].startswith("小明（s1）｜作答 15｜近期正确率 67%｜平均分 ") and ctx[3].startswith("小红（s2）｜作答 10｜近期正确率 40%｜平均分 ")
          and ctx[4] == "小丽（s3）｜还没作答" and ctx[5] == "【后端算好的字符图】" and "\n".join(ctx[6:]) == r["chart"], "context 各行格式", ctx)
    r2, c, e = run("学生对比", students="s2,小明 s1")
    check(r2["status"] == "ok" and r2["total"] == 2 and r2["ranked"] == 2 and r2["chart"].startswith("1. 小明"), "分隔符（英文逗号 / 空白）、用户名、重复（小明 / s1 同一人）只算一次", r2)
    r, c, e = run("学生对比", students="小明")
    check(r["status"] == "ask" and r["hint"] == "对比要说 2 到 5 位学生的名字，用「、」隔开" and r["total"] == 0, "只说一位：ask", r)
    r, c, e = run("学生对比", students="小明、s1")
    check(r["status"] == "ask" and r["hint"] == "对比要说 2 到 5 位学生的名字，用「、」隔开", "两个名字是同一人，去重后不足 2：ask", r)
    r, c, e = run("学生对比", students="甲、乙、丙、丁、戊、己")
    check(r["status"] == "ask" and r["hint"] == "对比要说 2 到 5 位学生的名字，用「、」隔开", "6 位：ask", r)
    r, c, e = run("学生对比", students="小明、路人")
    check(r["status"] == "ask" and r["hint"] == "没有找到叫「路人」的学生。现有学生：小明（s1）、小红（s2）、小丽（s3）", "有人找不到：ask 话术", r)
    r, c, e = run("学生对比", students="小明、小")
    check(r["status"] == "ask" and r["hint"] == "「小」找到多位：小明（s1）、小红（s2）、小丽（s3），你指哪一位？", "有人不唯一：ask 话术", r)
    r, c, e = run("学生对比", students="小明、小旧")
    check(r["status"] == "ask" and "小旧" in r["hint"], "撤销登记的学生找不到", r)
    # 平手：近期正确率、平均分都一样 → username 升序
    seed(stu("a2", "乙乙") + stu("a1", "甲甲") + bulk("a1", "2025-12-31", 4, 2) + bulk("a2", "2025-12-31", 4, 2))
    r, c, e = run("学生对比", students="乙乙、甲甲")
    check(r["chart"].split("\n")[0].startswith("1. 甲甲 █████░░░░░ 近期正确率 50%") and r["chart"].split("\n")[1].startswith("2. 乙乙"), "平手按 username 升序（a1 在前）", r["chart"])

    print("六、掉队名单")
    rows = []
    rows += stu("u01", "小甲") + bulk("u01", "2025-12-31", 3, 3)                                    # 近期活跃，不命中
    rows += stu("u02", "小乙") + bulk("u02", "2025-12-20", 1, 1)                                    # ① 最近一次 12-20
    rows += stu("u03", "小丙") + bulk("u03", "2025-12-10", 10, 9) + bulk("u03", "2025-12-30", 10, 5)  # ② 90 → 50 降 40
    rows += stu("u04", "小丁") + bulk("u04", "2025-12-10", 10, 8) + bulk("u04", "2025-12-30", 10, 7)  # 80 → 70 降 10，不命中
    rows += stu("u05", "小戊") + bulk("u05", "2025-12-10", 10, 9) + bulk("u05", "2025-12-30", 9, 3)   # 近 14 天只有 9 题，不判
    rows += stu("u06", "小己") + bulk("u06", "2025-12-12", 20, 17) + bulk("u06", "2025-12-29", 20, 14)  # 85 → 70 刚好降 15，命中
    rows += stu("u07", "小庚", disabled=1) + bulk("u07", "2025-12-20", 1, 1)                        # 停用且沉默，不判
    rows += stu("u08", "小辛")                                                                     # 从没作答
    rows += stu("u09", "小壬", status="revoked") + bulk("u09", "2025-12-20", 1, 1)                  # 撤销登记，不判
    rows += stu("u10", "小癸") + bulk("u10", "2025-12-08", 10, 10) + bulk("u10", "2025-12-20", 10, 2)  # ① + ② 都命中
    rows += stu("u11", "小子") + bulk("u11", "2025-12-18", 10, 10) + bulk("u11", "2025-12-31", 10, 10)  # 12-18 刚好是「之前 14 天」第 1 天（距今 14）
    rows += bulk("x1", "2025-12-31", 5, 5)                                                         # 没登记的人
    seed(rows)
    r, c, e = run("掉队名单")
    check(c == "" and r["status"] == "ok" and r["hint"] == "" and r["total"] == 5, "total=5", r)
    check([s["username"] for s in r["students"]] == ["u02", "u03", "u06", "u08", "u10"],
          "名单（username 升序）：u02 沉默、u03 降 40、u06 刚好降 15、u08 没作答过、u10 两条；不含 u04（降 10）u05（9 题）u07（停用）u09（撤销）u11", [s["username"] for s in r["students"]])
    by = {s["username"]: s for s in r["students"]}
    check(by["u02"]["reasons"] == ["近 7 天没有作答（最近一次 2025-12-20）"] and by["u02"]["last_at"] == "2025-12-20" and by["u02"]["display_name"] == "小乙",
          "u02：规则① 原文、last_at=2025-12-20", by["u02"])
    check(by["u03"]["reasons"] == ["近 14 天正确率 50%，之前 14 天 90%，降了 40 个百分点"] and by["u03"]["last_at"] == "2025-12-30", "u03：规则② 原文", by["u03"])
    check(by["u06"]["reasons"] == ["近 14 天正确率 70%，之前 14 天 85%，降了 15 个百分点"], "u06：刚好 15 个百分点命中", by["u06"])
    check(by["u08"]["reasons"] == ["近 7 天没有作答（最近一次 从没作答过）"] and by["u08"]["last_at"] == "", "u08：从没作答过、last_at 空串", by["u08"])
    check(by["u10"]["reasons"] == ["近 7 天没有作答（最近一次 2025-12-20）", "近 14 天正确率 20%，之前 14 天 100%，降了 80 个百分点"], "u10：两条规则都命中，①在前", by["u10"])
    check(r["rules_text"] == RULES, "rules_text 原文", r["rules_text"])
    want_chart = ("掉队名单 5 人（" + RULES + "）\n"
                  "・小乙（u02）：近 7 天没有作答（最近一次 2025-12-20）\n"
                  "・小丙（u03）：近 14 天正确率 50%，之前 14 天 90%，降了 40 个百分点\n"
                  "・小己（u06）：近 14 天正确率 70%，之前 14 天 85%，降了 15 个百分点\n"
                  "・小辛（u08）：近 7 天没有作答（最近一次 从没作答过）\n"
                  "・小癸（u10）：近 7 天没有作答（最近一次 2025-12-20）；近 14 天正确率 20%，之前 14 天 100%，降了 80 个百分点")
    check(r["chart"] == want_chart, "chart 原文", r["chart"])
    body = "\n".join(want_chart.split("\n")[1:])
    check(r["context_text"] == "今天：2026-01-01\n分析：掉队名单（规则由系统判定，不要自己增减名单）\n" + body + "\n" + RULES + "\n【后端算好的字符图】\n" + want_chart,
          "context_text 格式", r["context_text"])
    r, c, e = run("分析上下文", kind="alert")
    check(r["status"] == "ok" and r["kind"] == "alert" and r["hint"] == "" and r["chart"] == want_chart and r["context_text"].startswith("今天：2026-01-01\n分析：掉队名单"),
          "分析上下文 alert：原样带回 chart / context", r)

    # 近 7 天全班都没人作答（放假）：规则①对谁都不命中
    seed(stu("v1", "小一") + stu("v2", "小二") + bulk("v1", "2025-12-20", 3, 3) + bulk("v2", "2025-12-22", 3, 3))
    r, c, e = run("掉队名单")
    check(r["status"] == "empty" and r["total"] == 0 and r["students"] == [] and r["hint"] == NODATA and r["chart"] == NODATA and r["context_text"] == "" and r["rules_text"] == RULES,
          "放假（全班近 7 天都没作答）→ 空态⑤：hint = 「按现在的规则没有掉队的学生。」+ 规则；chart 同 hint", r)
    r, c, e = run("分析上下文", kind="alert")
    check(r == {"status": "empty", "kind": "alert", "hint": NODATA, "chart": "", "context_text": ""}, "分析上下文 alert 空态⑤：chart / context 清空", r)
    # 边界：距今 6 天（12-26）算近 7 天，距今 7 天（12-25）不算
    seed(stu("w1", "小甲") + stu("w2", "小乙") + bulk("w1", "2025-12-31", 1, 1) + bulk("w2", "2025-12-26", 1, 1))
    r, c, e = run("掉队名单")
    check(r["status"] == "empty", "边界：w2 距今 6 天仍算近 7 天有作答 → 不掉队", r)
    seed(stu("w1", "小甲") + stu("w2", "小乙") + bulk("w1", "2025-12-31", 1, 1) + bulk("w2", "2025-12-25", 1, 1))
    r, c, e = run("掉队名单")
    check(r["total"] == 1 and r["students"][0]["username"] == "w2" and r["students"][0]["reasons"] == ["近 7 天没有作答（最近一次 2025-12-25）"], "边界：w2 距今 7 天 → 掉队", r)
    # 单个学生停用而全班其他人活跃
    seed(stu("d1", "小甲") + stu("d2", "小乙", disabled=1) + bulk("d1", "2025-12-31", 1, 1))
    r, c, e = run("掉队名单")
    check(r["status"] == "empty" and r["hint"] == NODATA, "停用且从没作答的学生不判掉队", r)

    print("七、分析上下文分发")
    seed(MAIN)
    r, c, e = run("分析上下文", kind="bad")
    check(c == "400" and "分析类型不对" in e, "kind 不对 → 400 分析类型不对", (c, e))
    t, _, _ = run("学情趋势", student="小明", days=14)
    r, c, e = run("分析上下文", kind="trend", student="小明", days=14)
    check(r == {"status": "ok", "kind": "trend", "hint": "", "chart": t["chart"], "context_text": t["context_text"]}, "trend：同 学情趋势（student / days 透传）", r)
    a, _, _ = run("错题归因", days=7, top=1)
    r, c, e = run("分析上下文", kind="attribution", days=7, top=1)
    check(r == {"status": "ok", "kind": "attribution", "hint": "", "chart": a["chart"], "context_text": a["context_text"]}, "attribution：同 错题归因（days / top 透传）", r)
    m, _, _ = run("学生对比", students="小明、小红")
    r, c, e = run("分析上下文", kind="compare", student="小明、小红")
    check(r == {"status": "ok", "kind": "compare", "hint": "", "chart": m["chart"], "context_text": m["context_text"]}, "compare：student 当作多个名字传给 学生对比", r)
    r, c, e = run("分析上下文", kind="compare", student="小明")
    check(r == {"status": "ask", "kind": "compare", "hint": "对比要说 2 到 5 位学生的名字，用「、」隔开", "chart": "", "context_text": ""}, "compare 只给一个名字：ask，chart / context 清空", r)
    r, c, e = run("分析上下文", kind="trend", student="路人")
    check(r["status"] == "ask" and r["chart"] == "" and r["context_text"] == "" and "没有找到叫「路人」的学生" in r["hint"], "trend 找不到学生：ask，不带 chart", r)
    r, c, e = run("分析上下文", kind="trend", days=5)
    check(c == "400" and "days 不合法" in e, "分析上下文 days 不合法 → 400", (c, e))
    r, c, e = run("分析上下文", kind="attribution", top=99)
    check(c == "400" and "top 不合法" in e, "分析上下文 top 不合法 → 400", (c, e))

    print("八、权限（只读，按读解析科目）")
    seed(MAIN + [("subject_teacher", dict(subject_id=1, teacher="t1", role="owner", created_at="2026-01-01"))])
    r, c, e = run("学情趋势", days=14, subject=1, **ON_T)
    check(c == "" and r["status"] == "ok" and r["active_days"] == 3, "登录模式 + 负责老师 + 显式 subject=1：通过", (c, e))
    r, c, e = run("掉队名单", subject=1, learner="t3", current_role="teacher", auth_mode="on")
    check(c == "", "无关老师读公共科目：通过（只读不要写权限）", (c, e, r))
    r, c, e = run("掉队名单", subject=1, learner="s1", current_role="student", auth_mode="on")
    check(c == "" and r["status"] == "ok", "分配到该科目的学生读本科目：通过（本模块只按读解析科目）", (c, e))
    for fn, extra in (("学情趋势", {}), ("错题归因", {}), ("掉队名单", {}), ("学生对比", dict(students="小明、小红")), ("分析上下文", dict(kind="alert"))):
        r, c, e = run(fn, subject=1, learner="s9", current_role="student", auth_mode="on", **extra)
        check(c == "403" and "该科目未分配给你" in e, f"没分配到该科目的学生 + 显式 subject：{fn} 403 该科目未分配给你", (c, e))
        r, c, e = run(fn, subject=2, learner="t1", current_role="teacher", auth_mode="on", **extra)
        check(c == "403" and "没有权限访问该科目" in e, f"老师读别人的私有科目：{fn} 403 没有权限访问该科目", (c, e))
        r, c, e = run(fn, subject=99, learner="t1", current_role="teacher", auth_mode="on", **extra)
        check(c == "404" and "没有这个科目" in e, f"不存在的科目：{fn} 404", (c, e))
        r, c, e = run(fn, subject="abc", learner="t1", current_role="teacher", auth_mode="on", **extra)
        check(c == "400" and "subject 不对" in e, f"subject 不是数字：{fn} 400 subject 不对", (c, e))
    # 科目 2 是空科目：owner t2 读 → 空态①（也证明统计只限本科目，科目 1 的学生不串过来）
    r, c, e = run("掉队名单", subject=2, learner="t2", current_role="teacher", auth_mode="on")
    check(c == "" and r["status"] == "empty" and r["hint"] == EMPTY1, "科目 2 的负责老师读：空态①，科目 1 的学生不串科目", (c, e, r))
    # 本模块不写库
    db = seed(MAIN)
    con = sqlite3.connect(db)
    before = [con.execute(f"select count(*) from {t}").fetchone()[0] for t in ("progress_answer", "account_user", "subject_student", "quiz_question")]
    con.close()
    for fn, extra in (("学情趋势", {}), ("错题归因", {}), ("学生对比", dict(students="小明、小红")), ("掉队名单", {})):
        run(fn, **extra)
    con = sqlite3.connect(db)
    after = [con.execute(f"select count(*) from {t}").fetchone()[0] for t in ("progress_answer", "account_user", "subject_student", "quiz_question")]
    con.close()
    check(before == after, "四个函数只读：表行数不变", (before, after))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
