# -*- coding: utf-8 -*-
"""kg_v4 教师助手草稿确认框架（M4-P1）的补充测试：约定用例的「得 / 库」写不了并发和可控的假模型输出，这里补上。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_assist_drafts.py

拷一份 kg_v4 到临时目录，用约定用例的运行器（cases.build_sql / reset_db / call）造数据、调函数。离线，不调真模型。
  并发：两个线程（各自的引擎）同时确认 / 撤销同一份草稿，只能成功一次（另一个 409），题只写一遍
  partial：传达里一个学生成功、一个失败 → partial，撤销只撤成功的
  7 天撤销边界（当前时间固定为 2026-01-01 09:00:00）
  已作答的助手题不可删；传达撤销：带到过 = 停用，没带到过 = 删除
  只读老师 / 学生 / 跨科目
  模型输出不合法：重试 1 次后回模板话、不建草稿；第二次合法则建草稿（假模型按脚本出）
  P1b：setting_save 设定被他人改过撤销 409、kg_add 知识点被引用撤销 409、两种 kind 的并发确认只成功一次
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
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


tmp = Path(tempfile.mkdtemp(prefix="kg_v4_assist_drafts_"))
ws = tmp / "kg_v4"
shutil.copytree(SRC, ws, ignore=K.COPY_IGNORE, symlinks=True)
os.environ["DSL_NOW"] = K.DEFAULT_NOW
SQL = K.build_sql(ws, P.closure(ws, "teacher_assist"))

SUBJECTS = [
    ("subject_info", dict(code="jp_grammar", name="日语语法", kind="language", caps="x", levels="", qtypes="choice", visibility="public",
                          owner="t1", status="active", created_at="2026-01-01", updated_at="2026-01-01")),
    ("subject_info", dict(code="math", name="数学", kind="general", caps="x", levels="", qtypes="choice", visibility="public",
                          owner="t1", status="active", created_at="2026-01-01", updated_at="2026-01-01")),
]
BASE = [("kg_point", dict(code="P1", title="点一")), ("kg_item", dict(code="I1", name="条目一", point_code="P1"))]
QUIZ_PAYLOAD = json.dumps({"questions": [
    {"stem": "题一", "options": ["甲", "乙"], "answer": "A", "accepted": [], "explain": "", "item_code": "I1", "level": "N5", "category": "助手出题"},
    {"stem": "题二", "options": ["甲", "乙"], "answer": "B", "accepted": [], "explain": "", "item_code": "I1", "level": "N5", "category": "助手出题"}]},
    ensure_ascii=False)
RELAY_PAYLOAD = json.dumps({"items": [{"student": "s1", "display_name": "小明"}, {"student": "s2", "display_name": "小红"}],
                            "must_info": "周五小测", "facts": "", "urgency": "normal", "deadline": "", "rounds": 3, "keywords": ""},
                           ensure_ascii=False)


def draft(**kw):
    row = dict(teacher="t1", subject_id=1, kind="quiz_add", title="草稿", payload=QUIZ_PAYLOAD, preview="x", snapshot="", result="",
               status="pending", claim="", error="", created_at="2025-12-31", decided_at=None)
    row.update(kw)
    return ("teacher_assist_draft", row)


def seed(rows):
    db = K.reset_db(ws, SQL)
    con = sqlite3.connect(db)
    try:
        for table, kv in rows:
            kv = {k: v for k, v in kv.items() if v is not None}
            con.execute(f"INSERT INTO {table}({', '.join(kv)}) VALUES({', '.join('?' * len(kv))})", list(kv.values()))
        con.commit()
    finally:
        con.close()
    return db


def q(db, sql, *a):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, a).fetchall()
    finally:
        con.close()


def engine(handler=None):
    """同 cases.make_engine，但假模型可换成 handler(prompt, system)（默认照格式示例回）。"""
    from tools import packs
    from tools.dsl import DSLEngine
    from tools.dsl_http import DEFAULT_PACKS
    from tools.dsl_service import get_services
    from tools.mock import MockClient
    eng = DSLEngine(MockClient(offline=True, handler=handler or K._mock_reply), workdir=Path(ws), verbose=False,
                    verbs=packs.registry(DEFAULT_PACKS, Path(ws)), verbs_root=packs.verbs_root())
    svc = get_services(Path(ws) / "services")
    svc.refresh()
    eng.services = svc
    eng.svc_module = None
    return eng


def run(fn, tag="c", eng=None, **args):
    """→ (结果, 报错码或空)"""
    eng = eng or engine()
    r, err = K.call(eng, "assist_draft", fn, args, tag)
    K.settle()
    return r, (str(err.get("code")) if isinstance(err, dict) else ("" if err in ("", None) else str(err)))


def concurrent(fn, n=2, **args):
    """n 个线程各用自己的引擎同时调同一个函数 → [(结果, 报错码)]"""
    engs = [engine() for _ in range(n)]
    bar = threading.Barrier(n)
    out = [None] * n

    def work(i):
        bar.wait()
        out[i] = run(fn, tag=f"t{i}", eng=engs[i], **args)

    ts = [threading.Thread(target=work, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(120)
    return out


ON = "current_role=teacher auth_mode=on"
try:
    print("一、并发")
    for rnd in range(3):
        db = seed(BASE + [draft()])
        res = concurrent("确认草稿", current_user="t1", draft_id=1)
        oks = [r for r, e in res if e == ""]
        errs = [e for r, e in res if e != ""]
        check(len(oks) == 1 and errs == ["409"], f"并发确认 第{rnd + 1}轮：一个成功、一个 409", res)
        check(q(db, "SELECT count(*) FROM quiz_question")[0][0] == 2, f"并发确认 第{rnd + 1}轮：题只写了一遍（2 题）")
        check(q(db, "SELECT status, claim FROM teacher_assist_draft")[0] == ("done", ""), f"并发确认 第{rnd + 1}轮：草稿 done、claim 已清")
    for rnd in range(3):
        db = seed(BASE + [("quiz_question", dict(question_no="ta1-1", level="N5", category="助手出题", stem="题一", answer="A", item_code="I1")),
                          ("quiz_question", dict(question_no="ta1-2", level="N5", category="助手出题", stem="题二", answer="B", item_code="I1")),
                          draft(status="done", result='{"question_nos":"ta1-1,ta1-2"}', decided_at="2025-12-31")])
        res = concurrent("撤销草稿", current_user="t1", draft_id=1)
        oks = [r for r, e in res if e == ""]
        errs = [e for r, e in res if e != ""]
        check(len(oks) == 1 and errs == ["409"], f"并发撤销 第{rnd + 1}轮：一个成功、一个 409", res)
        check(q(db, "SELECT status FROM teacher_assist_draft")[0][0] == "undone"
              and q(db, "SELECT count(*) FROM quiz_question")[0][0] == 0, f"并发撤销 第{rnd + 1}轮：草稿 undone、题删光")
    # 确认 vs 放弃同时来：只有一个生效
    db = seed(BASE + [draft()])
    engs = [engine(), engine()]
    bar = threading.Barrier(2)
    out = {}

    def w(name, fn, e):
        bar.wait()
        out[name] = run(fn, tag=name, eng=e, current_user="t1", draft_id=1)

    ts = [threading.Thread(target=w, args=("c", "确认草稿", engs[0])), threading.Thread(target=w, args=("d", "放弃草稿", engs[1]))]
    [t.start() for t in ts]
    [t.join(120) for t in ts]
    n_ok = sum(1 for r, e in out.values() if e == "")
    st = q(db, "SELECT status FROM teacher_assist_draft")[0][0]
    n_q = q(db, "SELECT count(*) FROM quiz_question")[0][0]
    check(n_ok == 1 and ((st == "done" and n_q == 2) or (st == "discarded" and n_q == 0)), "确认和放弃同时来：只有一个生效", (out, st, n_q))

    print("二、partial（传达有人成功有人失败）")
    # 用触发器让 s2 的传达写库失败（真实的 partial：同一份 payload 有人成功有人失败）
    db = seed([draft(kind="relay_add", payload=RELAY_PAYLOAD)])
    con = sqlite3.connect(db)
    con.execute("CREATE TRIGGER fail_s2 BEFORE INSERT ON teacher_rules_relay WHEN NEW.student='s2' "
                "BEGIN SELECT RAISE(ABORT, '数据库忙'); END")
    con.commit()
    con.close()
    r, e = run("确认草稿", current_user="t1", draft_id=1)
    check(e == "" and isinstance(r, dict) and r.get("status") == "partial" and r.get("done") == 1 and r.get("total") == 2,
          "确认：1 成功 1 失败 → partial（done=1 total=2）", (r, e))
    check(q(db, "SELECT count(*) FROM teacher_rules_relay")[0][0] == 1, "partial：只建了成功的那一条个人传达")
    check(q(db, "SELECT status, claim FROM teacher_assist_draft")[0] == ("partial", ""), "partial：草稿 partial、claim 已清")
    r, e = run("确认草稿", tag="again", current_user="t1", draft_id=1)
    check(e == "409", "partial 不能再确认（409）", (r, e))
    r, e = run("撤销草稿", tag="u", current_user="t1", draft_id=1)
    check(e == "" and r.get("status") == "undone" and r.get("undone") == 1, "partial 撤销：只撤成功的那条 → undone", (r, e))
    check(q(db, "SELECT count(*) FROM teacher_rules_relay")[0][0] == 0, "partial 撤销后传达已删除")

    print("三、7 天撤销边界（当前时间 2026-01-01 09:00:00）")
    for decided, want, name in [("2025-12-25 10:00:00", "", "6 天 23 小时前：能撤"), ("2025-12-25 09:00:00", "", "刚好 7 天：能撤"),
                                ("2025-12-25 08:59:59", "409", "7 天零 1 秒：409"), ("2025-12-20 09:00:00", "409", "12 天前：409")]:
        db = seed(BASE + [("quiz_question", dict(question_no="ta1-1", level="N5", category="助手出题", stem="题一", answer="A", item_code="I1")),
                          draft(status="done", result='{"question_nos":"ta1-1"}', decided_at=decided)])
        r, e = run("撤销草稿", current_user="t1", draft_id=1)
        n = q(db, "SELECT count(*) FROM quiz_question")[0][0]
        check(e == want and n == (0 if want == "" else 1), "撤销 " + name, (r, e, n))

    print("四、已作答的助手题不可删")
    db = seed(BASE + [("quiz_question", dict(question_no="ta1-1", level="N5", category="助手出题", stem="题一", answer="A", item_code="I1")),
                      ("quiz_question", dict(question_no="ta1-2", level="N5", category="助手出题", stem="题二", answer="B", item_code="I1")),
                      ("progress_answer", dict(learner="s1", point_code="P1", question_no="ta1-1", correct=1, at="2026-01-01")),
                      draft(status="done", result='{"question_nos":"ta1-1,ta1-2"}', decided_at="2025-12-31")])
    r, e = run("撤销草稿", current_user="t1", draft_id=1)
    check(e == "409" and q(db, "SELECT count(*) FROM quiz_question")[0][0] == 2, "有人答过其中一题：409，两题都不删", (r, e))
    check(q(db, "SELECT status, claim FROM teacher_assist_draft")[0] == ("done", ""), "撤销失败后草稿回到 done、claim 已清")

    print("五、传达撤销 = 停用 / 删除")
    one = json.dumps({"items": [{"student": "s1", "display_name": "小明"}], "must_info": "周五小测", "facts": "", "urgency": "normal",
                      "deadline": "", "rounds": 3, "keywords": ""}, ensure_ascii=False)
    res1 = '{"items":[{"student":"s1","display_name":"小明","relay_id":1,"ok":1,"error":"","undo":""}]}'
    relay = ("teacher_rules_relay", dict(urgency="normal", must_info="周五小测", rounds=3, student="s1", enabled=1, author="t1",
                                         updated_at="2025-12-31", subject_id=1))
    db = seed([relay, ("teacher_rules_relay_state", dict(relay_id=1, student="s1", rounds_done=1, finished=0, confirmed=0, updated_at="2025-12-31")),
               draft(kind="relay_add", payload=one, result=res1, status="done", decided_at="2025-12-31")])
    r, e = run("撤销草稿", current_user="t1", draft_id=1)
    check(e == "" and q(db, "SELECT count(*), min(enabled) FROM teacher_rules_relay")[0] == (1, 0), "已带到过：传达停用（没删）", (r, e))
    items = json.loads(q(db, "SELECT result FROM teacher_assist_draft")[0][0])["items"]
    check(items[0]["undo"] == "disabled", "result 里记 undo=disabled", items)
    db = seed([relay, draft(kind="relay_add", payload=one, result=res1, status="done", decided_at="2025-12-31")])
    r, e = run("撤销草稿", current_user="t1", draft_id=1)
    items = json.loads(q(db, "SELECT result FROM teacher_assist_draft")[0][0])["items"]
    check(e == "" and q(db, "SELECT count(*) FROM teacher_rules_relay")[0][0] == 0 and items[0]["undo"] == "deleted",
          "没带到过：传达删除，undo=deleted", (r, e, items))

    print("六、只读老师 / 学生 / 跨科目")
    multi = SUBJECTS + [("kg_point", dict(code="math.a", title="代数", subject_id=2)),
                        ("kg_item", dict(code="math.i1", name="条目", point_code="math.a", subject_id=2)),
                        ("subject_student", dict(subject_id=2, learner="s1", assigned_by="t1", status="active", created_at="2026-01-01"))]
    qp = json.dumps({"questions": [{"stem": "一加一", "options": ["1", "2"], "answer": "B", "accepted": [], "explain": "", "item_code": "math.i1",
                                    "level": "初一", "category": "计算"}]}, ensure_ascii=False)
    d2 = lambda **kw: draft(teacher="t2", subject_id=2, payload=qp, **kw)  # noqa: E731
    db = seed(multi + [d2()])
    for who, role, name in [("t2", "teacher", "只读老师"), ("s1", "student", "学生")]:
        for fn in ("确认草稿", "撤销草稿"):
            r, e = run(fn, current_user=who, draft_id=1, current_role=role, auth_mode="on", subject=2)
            check(e == "403", f"{name}{fn} → 403", (r, e))
        r, e = run("生成草稿", current_user=who, kind="quiz_add", message="出两道题", current_role=role, auth_mode="on", subject=2)
        check(e == "403", f"{name}生成草稿 → 403", (r, e))
    check(q(db, "SELECT status FROM teacher_assist_draft")[0][0] == "pending" and q(db, "SELECT count(*) FROM quiz_question")[0][0] == 0,
          "被拒后草稿仍 pending、题库没动")
    r, e = run("放弃草稿", current_user="t2", draft_id=1, current_role="teacher", auth_mode="on", subject=2)
    check(e == "" and q(db, "SELECT status FROM teacher_assist_draft")[0][0] == "discarded", "只读老师仍能放弃自己的草稿")
    db = seed(multi + [("subject_teacher", dict(subject_id=2, teacher="t2", role="editor", created_at="2026-01-01")), d2()])
    r, e = run("确认草稿", current_user="t2", draft_id=1, current_role="teacher", auth_mode="on", subject=2)
    nos = [x[0] for x in q(db, "SELECT question_no FROM quiz_question ORDER BY question_no")]
    check(e == "" and nos == ["math.ta1-1"], "协作教师能确认，题号带科目编码", (r, e, nos))
    # 跨科目：科目 1 视角看不到科目 2 的草稿
    db = seed(multi + [d2()])
    r, e = run("确认草稿", current_user="t2", draft_id=1)
    check(e == "404", "别的科目的草稿：404（不泄露）", (r, e))
    db = seed(multi + [draft(teacher="t1")])
    r, e = run("确认草稿", current_user="t9", draft_id=1)
    check(e == "404", "别人的草稿：404", (r, e))

    print("七、模型输出不合法 → 重试 → 模板话；第二次合法 → 建草稿")
    GOOD = json.dumps({"title": "出 2 道题", "questions": json.loads(QUIZ_PAYLOAD)["questions"]}, ensure_ascii=False)
    BADQ = '{"title":"t","questions":[{"stem":"","options":["甲","乙"],"answer":"A","item_code":"I1"}]}'
    # (名, 模型依次的输出, 期望 status, 期望 tries, 草稿数, 模型调用次数)
    # 问JSON 自己对「不是 JSON」会重试 2 次（一次 tries 内最多 3 次原始调用），内容不合法才算 tries 的第二次
    seqs = [("两次都不是 JSON", ["不是json"], "ask", 2, 0, 6),
            ("两次校验不过（题干为空）", [BADQ], "ask", 2, 0, 2),
            ("第一次内容不合法第二次好", [BADQ, GOOD], "ok", 2, 1, 2),
            ("第一次就好", [GOOD], "ok", 1, 1, 1),
            ("模型写了题号被拒，第二次好", ['{"title":"t","questions":[{"question_no":"Q9","stem":"x","options":["甲","乙"],"answer":"A","item_code":"I1"}]}', GOOD],
             "ok", 2, 1, 2)]
    for name, outs, st, tries, n_drafts, n_calls in seqs:
        db = seed(BASE)
        calls = []

        def handler(prompt, system=None, _o=outs, _c=calls):
            _c.append(prompt)
            return _o[min(len(_c) - 1, len(_o) - 1)]

        r, e = run("生成草稿", eng=engine(handler), current_user="t1", kind="quiz_add", message="出两道题", count=2)
        nd = q(db, "SELECT count(*) FROM teacher_assist_draft")[0][0]
        check(e == "" and r.get("status") == st and r.get("tries") == tries and nd == n_drafts and len(calls) == n_calls,
              f"{name}：status={st} tries={tries} 草稿 {n_drafts} 份（模型调用 {n_calls} 次）", (r, e, nd, len(calls)))
        check(q(db, "SELECT count(*) FROM quiz_question")[0][0] == 0, f"{name}：生成不写题库")
        if st == "ask":
            check(str(r.get("hint", "")).startswith("没生成成功"), f"{name}：回模板话「没生成成功…」", r.get("hint"))
    # 第二次提示词里带了上一次的错误
    db = seed(BASE)
    calls = []

    def h2(prompt, system=None):
        calls.append(prompt)
        return BADQ if len(calls) == 1 else GOOD

    run("生成草稿", eng=engine(h2), current_user="t1", kind="quiz_add", message="出两道题", count=2)
    check(len(calls) == 2 and "上次输出的问题" in calls[1], "重试的提示词带上次的错误句子", calls[1][-200:] if len(calls) > 1 else calls)

    print("八、P1b：setting_save / kg_add（设定被他人改过、知识点被引用撤销 409，并发确认只成功一次）")
    SET_PAYLOAD = json.dumps({"settings": [{"op": "add", "target_id": "", "kind": "memory", "content": "喜欢动漫", "student": "", "student_name": "",
                                            "keywords": "", "once": 0}]}, ensure_ascii=False)
    KG_PAYLOAD = json.dumps({"points": [{"code": "P2", "title": "点二"}],
                             "items": [{"code": "I2", "name": "条目二", "point_code": "P2", "after_form": "", "prev_code": ""}],
                             "edges": [{"pre_code": "P1", "point_code": "P2"}]}, ensure_ascii=False)
    set_row = lambda **kw: ("teacher_rules_setting", dict(dict(kind="memory", student="", keywords="", content="喜欢动漫", enabled=1, once=0, version=1,  # noqa: E731
                                                              author="t1", updated_at="2025-12-31", subject_id=1), **kw))
    SET_RES = json.dumps({"items": [{"op": "add", "setting_id": 1, "label": "x", "ok": 1, "error": "", "undo": "",
                                     "written": {"kind": "memory", "student": "", "keywords": "", "content": "喜欢动漫", "once": 0, "enabled": 1}}]},
                         ensure_ascii=False)
    # 确认：设定写入、草稿 done
    db = seed([draft(kind="setting_save", payload=SET_PAYLOAD)])
    r, e = run("确认草稿", current_user="t1", draft_id=1)
    check(e == "" and r.get("status") == "done" and q(db, "SELECT count(*) FROM teacher_rules_setting")[0][0] == 1
          and q(db, "SELECT status FROM teacher_assist_draft")[0][0] == "done", "setting_save 确认：写入设定、草稿 done", (r, e))
    # 撤销：设定没人动 → 删掉
    db = seed([set_row(), draft(kind="setting_save", payload=SET_PAYLOAD, result=SET_RES, status="done", decided_at="2025-12-31")])
    r, e = run("撤销草稿", current_user="t1", draft_id=1)
    check(e == "" and q(db, "SELECT count(*) FROM teacher_rules_setting")[0][0] == 0
          and q(db, "SELECT status FROM teacher_assist_draft")[0][0] == "undone", "setting_save 撤销：设定没被动过 → 删除、草稿 undone", (r, e))
    # 撤销：设定被他人改过 → 409，设定与草稿都不动
    db = seed([set_row(content="别人又改了", version=3, author="t3"),
               draft(kind="setting_save", payload=SET_PAYLOAD, result=SET_RES, status="done", decided_at="2025-12-31")])
    r, e = run("撤销草稿", current_user="t1", draft_id=1)
    check(e == "409" and q(db, "SELECT content FROM teacher_rules_setting")[0][0] == "别人又改了"
          and q(db, "SELECT status, claim FROM teacher_assist_draft")[0] == ("done", ""), "setting_save 撤销：设定被他人改过 → 409，设定不动、草稿回到 done", (r, e))
    # 撤销：设定已被删 → 新建的算撤掉
    db = seed([draft(kind="setting_save", payload=SET_PAYLOAD, result=SET_RES, status="done", decided_at="2025-12-31")])
    r, e = run("撤销草稿", current_user="t1", draft_id=1)
    check(e == "" and q(db, "SELECT status FROM teacher_assist_draft")[0][0] == "undone", "setting_save 撤销：新建的设定已被老师删掉 → 算撤掉", (r, e))
    # 并发确认
    for rnd in range(3):
        db = seed([draft(kind="setting_save", payload=SET_PAYLOAD)])
        res = concurrent("确认草稿", current_user="t1", draft_id=1)
        oks = [r for r, e in res if e == ""]
        errs = [e for r, e in res if e != ""]
        check(len(oks) == 1 and errs == ["409"], f"setting_save 并发确认 第{rnd + 1}轮：一个成功、一个 409", res)
        check(q(db, "SELECT count(*) FROM teacher_rules_setting")[0][0] == 1
              and q(db, "SELECT status, claim FROM teacher_assist_draft")[0] == ("done", ""), f"setting_save 并发确认 第{rnd + 1}轮：设定只写一条、草稿 done、claim 已清")

    KG_RES = json.dumps({"items": [
        {"type": "point", "code": "P2", "pre_code": "", "point_code": "", "label": "x", "ok": 1, "error": "", "created": "", "undo": ""},
        {"type": "item", "code": "I2", "pre_code": "", "point_code": "", "label": "x", "ok": 1, "error": "", "created": "", "undo": ""},
        {"type": "edge", "code": "P1>P2", "pre_code": "P1", "point_code": "P2", "label": "x", "ok": 1, "error": "", "created": 1, "undo": ""}]})
    kg_rows = BASE + [("kg_point", dict(code="P2", title="点二")), ("kg_item", dict(code="I2", name="条目二", point_code="P2")),
                      ("kg_edge", dict(pre_code="P1", point_code="P2"))]
    kg_done = lambda: draft(kind="kg_add", payload=KG_PAYLOAD, result=KG_RES, status="done", decided_at="2025-12-31")  # noqa: E731
    db = seed(BASE + [draft(kind="kg_add", payload=KG_PAYLOAD)])
    r, e = run("确认草稿", current_user="t1", draft_id=1)
    check(e == "" and r.get("status") == "done" and q(db, "SELECT count(*) FROM kg_point")[0][0] == 2
          and q(db, "SELECT count(*) FROM kg_item")[0][0] == 2 and q(db, "SELECT count(*) FROM kg_edge")[0][0] == 1,
          "kg_add 确认：知识点、条目、前置边都写入", (r, e))
    db = seed(kg_rows + [kg_done()])
    r, e = run("撤销草稿", current_user="t1", draft_id=1)
    check(e == "" and q(db, "SELECT count(*) FROM kg_point")[0][0] == 1 and q(db, "SELECT count(*) FROM kg_item")[0][0] == 1
          and q(db, "SELECT count(*) FROM kg_edge")[0][0] == 0 and q(db, "SELECT status FROM teacher_assist_draft")[0][0] == "undone",
          "kg_add 撤销：没被引用 → 边、条目、知识点都删", (r, e))
    db = seed(kg_rows + [("quiz_question", dict(question_no="q1", level="N5", category="手工", stem="题", answer="A", item_code="I2")), kg_done()])
    r, e = run("撤销草稿", current_user="t1", draft_id=1)
    check(e == "409" and q(db, "SELECT count(*) FROM kg_point")[0][0] == 2 and q(db, "SELECT count(*) FROM kg_item")[0][0] == 2
          and q(db, "SELECT count(*) FROM kg_edge")[0][0] == 1 and q(db, "SELECT status, claim FROM teacher_assist_draft")[0] == ("done", ""),
          "kg_add 撤销：条目被题目引用 → 409，什么都不删、草稿回到 done", (r, e))
    db = seed(kg_rows + [("kg_point", dict(code="P3", title="别人的点")), ("kg_edge", dict(pre_code="P2", point_code="P3")), kg_done()])
    r, e = run("撤销草稿", current_user="t1", draft_id=1)
    check(e == "409" and q(db, "SELECT count(*) FROM kg_point")[0][0] == 3 and q(db, "SELECT count(*) FROM kg_edge")[0][0] == 2,
          "kg_add 撤销：别人后来加了前置边 → 409，什么都不删", (r, e))
    for rnd in range(3):
        db = seed(BASE + [draft(kind="kg_add", payload=KG_PAYLOAD)])
        res = concurrent("确认草稿", current_user="t1", draft_id=1)
        oks = [r for r, e in res if e == ""]
        errs = [e for r, e in res if e != ""]
        check(len(oks) == 1 and errs == ["409"], f"kg_add 并发确认 第{rnd + 1}轮：一个成功、一个 409", res)
        check(q(db, "SELECT count(*) FROM kg_point")[0][0] == 2 and q(db, "SELECT count(*) FROM kg_item")[0][0] == 2
              and q(db, "SELECT status, claim FROM teacher_assist_draft")[0] == ("done", ""), f"kg_add 并发确认 第{rnd + 1}轮：只建一遍、草稿 done、claim 已清")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
