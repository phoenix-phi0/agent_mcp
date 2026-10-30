# -*- coding: utf-8 -*-
"""kg_v4 教师助手教学材料（M4-P3 assist_material）的补充测试：约定用例的「得 / 库」写不了可控的假模型输出和多步流程，这里补上。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_assist_material.py

拷一份 kg_v4 到临时目录，用约定用例的运行器（cases.build_sql / reset_db / call）造数据、调函数。离线，不调真模型（假模型按脚本出）。
  生成（四种类型、标题后端拼、纯文本兜底、档位、20000 字截断、追问不调模型）→保存→改→导出→删
  课堂练习转出题草稿（草稿待确认、不写题库）
  权限（别人的 404、只读老师 / 学生 403）、跨科目 404
  内容 20000 字规则、按消息列材料、挂回材料消息
"""

import json
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


tmp = Path(tempfile.mkdtemp(prefix="kg_v4_assist_material_"))
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
S1 = [("account_user", dict(username="s1", password_hash="x", display_name="小明", role="student", disabled=0, created_at="2026-01-01")),
      ("subject_student", dict(subject_id=1, learner="s1", assigned_by="t1", status="active", created_at="2026-01-01"))]
BASE = [("kg_point", dict(code="P1", title="点一")), ("kg_item", dict(code="I1", name="条目一", point_code="P1"))]
QUIZ_JSON = json.dumps({"title": "出 2 道题", "questions": [
    {"stem": "题一", "options": ["甲", "乙"], "answer": "A", "accepted": [], "explain": "", "item_code": "I1", "level": "N5", "category": "助手出题"},
    {"stem": "题二", "options": ["甲", "乙"], "answer": "B", "accepted": [], "explain": "", "item_code": "I1", "level": "N5", "category": "助手出题"}]},
    ensure_ascii=False)


def mat(**kw):
    row = dict(teacher="t1", subject_id=1, kind="handout", title="讲义", content="正文", status="draft", source_msg_id=None, file_id=None,
               created_at="2025-12-31 10:00:00", updated_at="2025-12-31 10:00:00")
    row.update(kw)
    return ("teacher_assist_material", row)


def seed(rows=()):
    db = K.reset_db(ws, SQL)
    con = sqlite3.connect(db)
    try:
        for table, kv in list(SUBJECTS) + list(rows):
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


def engine(script=None, calls=None):
    """假模型：材料提示词按 script（字符串或依次的列表）回；assist_draft 的 JSON 提示词回合法的出题 JSON。calls 记录所有提示词。"""
    from tools import packs
    from tools.dsl import DSLEngine
    from tools.dsl_http import DEFAULT_PACKS
    from tools.dsl_service import get_services
    from tools.mock import MockClient
    outs = [script] if isinstance(script, str) else list(script or ["【题目】\n1. 默认"])
    mat_calls = []

    def handler(prompt, system=None):
        if calls is not None:
            calls.append(prompt)
        if "输出格式：只输出一个 JSON 对象" in prompt:
            return QUIZ_JSON
        mat_calls.append(prompt)
        return outs[min(len(mat_calls) - 1, len(outs) - 1)]

    eng = DSLEngine(MockClient(offline=True, handler=handler), workdir=Path(ws), verbose=False,
                    verbs=packs.registry(DEFAULT_PACKS, Path(ws)), verbs_root=packs.verbs_root())
    svc = get_services(Path(ws) / "services")
    svc.refresh()
    eng.services = svc
    eng.svc_module = None
    return eng


_n = [0]


def run(fn, eng=None, **args):
    """→ (结果, 报错码或空)"""
    _n[0] += 1
    r, err = K.call(eng or engine(), "assist_material", fn, args, f"c{_n[0]}")
    K.settle()
    return r, (str(err.get("code")) if isinstance(err, dict) else ("" if err in ("", None) else str(err)))


def gen(script, **kw):
    calls = []
    r, e = run("生成材料", eng=engine(script, calls), current_user="t1", **kw)
    return r, e, calls


try:
    print("一、生成材料（四种类型 / 标题后端拼 / 兜底清洗 / 档位）")
    db = seed(BASE)
    r, e, calls = gen("# 【教学目标】\n## ・**掌握**たばかり\n正文", kind="lesson_plan", message="写一份たばかり的教案", point="点一")
    check(e == "" and r["status"] == "ok" and r["kind"] == "lesson_plan" and r["tier"] == "平衡" and r["mat_id"] == 1, "教案：ok、平衡档、mat_id=1", (r, e))
    check(r["title"] == "教案：点一", "教案标题后端拼 = 教案：点一", r["title"])
    row = q(db, "SELECT teacher, subject_id, kind, title, content, status, source_msg_id, file_id FROM teacher_assist_material")
    check(len(row) == 1 and row[0][:4] == ("t1", 1, "lesson_plan", "教案：点一") and row[0][5] == "draft", "落库：draft、teacher=t1、subject_id=1", row)
    check(row[0][4] == "【教学目标】\n・掌握たばかり\n正文", "纯文本兜底：去掉行首 # 和 **", row[0][4])
    check(row[0][6] is None and row[0][7] is None, "source_msg_id、file_id 为空")
    check(len(calls) == 1 and "【数据】" in calls[0] and "知识点：点一（P1）" in calls[0] and "写一份たばかり的教案" in calls[0] and "教学目标" in calls[0],
          "模型只调 1 次，提示词带【数据】知识点与老师原话", calls[:1])
    check(r["preview"] == row[0][4], "preview = 全文（不足 300 字无省略号）", r["preview"])

    for msg, kind, tier in [("写一份完整的一节课教案", "教案", "强"), ("写一份详细讲义", "handout", "强"), ("写一份长篇讲义", "讲义", "强"),
                            ("按一整课写教案", "lesson_plan", "强"), ("出一份详细的课堂练习", "exercise", "平衡"),
                            ("写一份完整的学情报告", "report", "平衡"), ("随便写份讲义", "handout", "平衡")]:
        if kind == "report":
            seed(BASE + S1)
        else:
            seed(BASE)
        r, e, _ = gen("x", kind=kind, message=msg)
        check(e == "" and r["status"] == "ok" and r["tier"] == tier, f"档位：{kind}「{msg}」→ {tier}", (r, e))
    seed(BASE)
    r, e, calls = gen("x", kind="handout", message="写讲义", ref_text="字" * 3001)
    check(r["tier"] == "强" and "【资料】" in calls[0], "ref_text 超过 3000 字 → 强，提示词带【资料】", (r.get("tier"), e))
    r, e, calls = gen("x", kind="handout", message="写讲义", ref_text="字" * 3000)
    check(r["tier"] == "平衡", "ref_text 恰好 3000 字 → 平衡", r.get("tier"))
    r, e, calls = gen("x", kind="exercise", message="出题", ref_text="甲" * 7000)
    check(calls[0].count("甲") == 6000, "ref_text 超 6000 字只取前 6000", calls[0].count("甲"))

    db = seed(BASE)
    r, e, _ = gen("【题目】\n1. 题", kind="课堂练习", message="  出一份课堂练习  ", file_id=3, ref_text="は和が")
    check(e == "" and r["kind"] == "exercise" and r["tier"] == "平衡", "中文类型名「课堂练习」→ exercise、平衡", (r, e))
    check(r["title"] == "课堂练习：出一份课堂练习", "无知识点无学生：标题取老师的话前 20 字", r["title"])
    check(q(db, "SELECT file_id FROM teacher_assist_material")[0][0] == 3, "file_id=3 落库")
    r, e, _ = gen("x", kind="handout", message="一二三四五六七八九十一二三四五六七八九十甲乙丙")
    check(r["title"] == "讲义：一二三四五六七八九十一二三四五六七八九十", "标题尾部截 20 字", r["title"])

    db = seed(BASE + S1)
    r, e, calls = gen("【总体】\n全班", kind="report", message="写一份全班学情报告")
    check(e == "" and r["status"] == "ok" and r["title"] == "学情报告：全班" and r["tier"] == "平衡", "学情报告标题 = 学情报告：全班", (r, e))
    check("全班1人" in calls[0], "【数据】带全班人数", calls[0][:300])

    db = seed(BASE + S1)
    r, e, calls = gen("【总体】\n小明", kind="report", message="给小明写学情报告", student="小明")
    check(e == "" and r["status"] == "ok" and r["title"] == "学情报告：小明" and "学生：小明（s1）" in calls[0], "按学生：标题 = 学情报告：小明、【数据】带学生行", (r, e))
    db = seed(BASE + S1)
    r, e, calls = gen("x", kind="lesson_plan", message="写教案", point="点一", student="小明")
    check(r["title"] == "教案：点一", "知识点优先于学生作标题", r.get("title"))

    print("二、长文本截断 / 清洗 / 模型出错")
    db = seed(BASE)
    r, e, _ = gen("字" * 20050, kind="handout", message="写讲义")
    c = q(db, "SELECT content FROM teacher_assist_material")[0][0]
    check(e == "" and c == "字" * 20000 + "\n（已截断）", "超 20000 字截到 20000 并加「（已截断）」", (e, len(c), c[-8:]))
    check(r["preview"] == "字" * 300 + "…", "preview 超 300 字末尾加…", len(r["preview"]))
    db = seed(BASE)
    r, e, _ = gen("字" * 20000, kind="handout", message="写讲义")
    check(q(db, "SELECT length(content) FROM teacher_assist_material")[0][0] == 20000, "恰好 20000 字不截断")
    db = seed(BASE)
    r, e, _ = gen("  \n ", kind="handout", message="写讲义")
    check(e == "400" and q(db, "SELECT count(*) FROM teacher_assist_material")[0][0] == 0, "模型回空 → 400 助手暂时无法回答、不写库", (r, e))
    r, e, _ = gen("###\n**", kind="handout", message="写讲义")
    check(e == "400", "清洗后为空 → 400", (r, e))

    print("三、追问 / 入参错误不调模型不写库")
    db = seed(BASE)
    for name, kw, err, st in [("知识点没找到", dict(kind="handout", message="写讲义", point="被动态"), "", "ask"),
                              ("学生没找到", dict(kind="handout", message="写讲义", student="路人甲"), "", "ask"),
                              ("学情报告没有学生", dict(kind="report", message="全班学情报告"), "", "ask"),
                              ("类型不对", dict(kind="poem", message="写首诗"), "400", None),
                              ("消息为空", dict(kind="handout", message="   "), "400", None),
                              ("file_id 不合法", dict(kind="handout", message="写讲义", file_id="abc"), "400", None)]:
        r, e, calls = gen("x", **kw)
        ok = e == err and (st is None or (r["status"] == "ask" and r["mat_id"] in ("", None) and r["tier"] == "" and r["hint"] != ""))
        check(ok and calls == [], f"{name}：{'ask' if st else '400'}、模型 0 次", (r, e, len(calls)))
    check(q(db, "SELECT count(*) FROM teacher_assist_material")[0][0] == 0, "以上都没写库")
    r, e, _ = gen("x", kind="handout", message="写讲义", point="被动态")
    check("被动态" in r["hint"] and "没有找到" in r["hint"], "知识点没找到的 hint 点名", r["hint"])
    r, e, _ = gen("x", kind="report", message="全班学情报告")
    check("还没有学生" in r["hint"], "没有学生的 hint", r["hint"])

    print("四、生成 → 保存 → 改 → 导出 → 删")
    db = seed(BASE)
    r, e, _ = gen("【要点】\n旧正文", kind="handout", message="写一份讲义", point="点一")
    mid = r["mat_id"]
    r, e = run("列材料", current_user="t1")
    check(e == "" and r["total"] == 1 and r["drafts"] == 1 and r["materials"][0]["mat_state"] == "未保存" and r["materials"][0]["mat_kind"] == "讲义",
          "列材料：total=1 drafts=1 状态=未保存", (r, e))
    r, e = run("材料页面", current_user="t1")
    check(r["mat_note"] == "共1份，未保存1份（7天后自动清掉）", "材料页抬头", r)
    r, e = run("导出材料页面", current_user="t1", mat_id=mid)
    check(e == "" and r["mat_export_text"] == "讲义：点一\n\n【要点】\n旧正文" and r["mat_export_head"].startswith("讲义 · 未保存 · 8 字 · 更新于 2026-01-01"),
          "导出：title+空行+content；未保存也能导出", r)
    check(q(db, "SELECT status FROM teacher_assist_material")[0][0] == "draft", "导出不改状态")
    r, e = run("保存材料", current_user="t1", mat_id=mid)
    check(e == "" and r["saved"] == 1 and r["status"] == "saved" and q(db, "SELECT status FROM teacher_assist_material")[0][0] == "saved", "保存：saved=1、状态 saved", (r, e))
    r, e = run("保存材料", current_user="t1", mat_id=mid)
    check(e == "" and r["saved"] == 0, "重复保存不报错 saved=0", (r, e))
    r, e = run("列材料", current_user="t1", status="saved")
    check(r["total"] == 1 and r["drafts"] == 0, "列材料 status=saved：total=1 drafts=0", r)
    r, e = run("列材料", current_user="t1", status="draft")
    check(r["total"] == 0, "列材料 status=draft：0 份", r)
    r, e = run("列材料", current_user="t1", status="bad")
    check(e == "400", "status 不合法 400", (r, e))
    # 改：只传 mat_content，标题与类型保留
    r, e = run("改材料", current_user="t1", mat_id=mid, mat_content="  新正文  ")
    row = q(db, "SELECT title, kind, content, status FROM teacher_assist_material")[0]
    check(e == "" and r["status"] == "saved" and row == ("讲义：点一", "handout", "新正文", "saved"), "只传 mat_content：标题、类型保留，正文去首尾空白", (r, e, row))
    r, e = run("改材料", current_user="t1", mat_id=mid, mat_title="", mat_content="再改")
    check(e == "" and q(db, "SELECT title FROM teacher_assist_material")[0][0] == "讲义：点一", "mat_title 空串视为没传，保留原标题", (r, e))
    r, e = run("改材料", current_user="t1", mat_id=mid, mat_title="新标题", mat_kind="学情报告")
    row = q(db, "SELECT title, kind, content FROM teacher_assist_material")[0]
    check(e == "" and row == ("新标题", "report", "再改"), "改标题与类型（中文名），正文不变", (r, e, row))
    r, e = run("改材料", current_user="t1", mat_id=mid, mat_title="题" * 60)
    check(e == "" and q(db, "SELECT title FROM teacher_assist_material")[0][0] == "题" * 60, "标题恰好 60 字可以")
    r, e = run("改材料", current_user="t1", mat_id=mid, mat_title="题" * 61)
    check(e == "400" and q(db, "SELECT title FROM teacher_assist_material")[0][0] == "题" * 60, "mat_title 61 字 → 400，标题不变", (r, e))
    r, e = run("改材料", current_user="t1", mat_id=mid, mat_kind="poem")
    check(e == "400", "类型不对 400", (r, e))
    r, e = run("改材料", current_user="t1", mat_id=mid, mat_content="   ")
    check(e == "400" and q(db, 'SELECT content FROM teacher_assist_material')[0][0] == "再改", "mat_content 全空白 → 400 内容不能为空，正文不变", (r, e))
    # 改会把 draft 置 saved
    db = seed([mat()])
    r, e = run("改材料页面", current_user="t1", mat_id=1, mat_title="新讲义", mat_kind="课堂练习", mat_content="新内容")
    row = q(db, "SELECT title, kind, content, status, updated_at FROM teacher_assist_material")[0]
    check(e == "" and row[:4] == ("新讲义", "exercise", "新内容", "saved") and row[4] != "2025-12-31 10:00:00" and r["mat_note"] == "共1份",
          "改材料页面：同时置 saved、updated_at 更新、抬头无未保存", (r, e, row))
    r, e = run("载入材料页面", current_user="t1", mat_id=1)
    check(r == {"mat_id": 1, "mat_title": "新讲义", "mat_kind": "课堂练习", "mat_content": "新内容"}, "载入材料页面回填中文类型", r)
    r, e = run("取材料", current_user="t1", mat_id=1)
    check(e == "" and r["kind_label"] == "课堂练习" and r["state"] == "已保存" and r["content"] == "新内容" and r["source_msg_id"] in ("", None) and r["file_id"] in ("", None),
          "取材料：全文、kind_label、state、空 source_msg_id/file_id", r)
    r, e = run("导出材料页面", current_user="t1", mat_id=1)
    check(r["mat_export_text"] == "新讲义\n\n新内容" and r["mat_export_head"].startswith("课堂练习 · 已保存 · 3 字"), "导出材料页面", r)
    r, e = run("删材料", current_user="t1", mat_id=1)
    check(e == "" and r["mat_id"] == 1 and q(db, "SELECT count(*) FROM teacher_assist_material")[0][0] == 0, "删材料：行没了", (r, e))
    r, e = run("取材料", current_user="t1", mat_id=1)
    check(e == "404", "删后取材料 404", (r, e))
    r, e = run("删材料", current_user="t1", mat_id=1)
    check(e == "404", "再删 404", (r, e))
    r, e = run("取材料", current_user="t1", mat_id="abc")
    check(e == "400", "mat_id 非法 400", (r, e))
    r, e = run("取材料", current_user="t1", mat_id=0)
    check(e == "400", "mat_id=0 → 400", (r, e))

    print("五、内容 20000 字规则（改材料不截断、原样拒）")
    db = seed([mat()])
    r, e = run("改材料", current_user="t1", mat_id=1, mat_content="字" * 20000)
    check(e == "" and q(db, "SELECT length(content) FROM teacher_assist_material")[0][0] == 20000, "20000 字可以存")
    r, e = run("改材料", current_user="t1", mat_id=1, mat_content="新" * 20001)
    check(e == "400" and q(db, "SELECT substr(content,1,1) FROM teacher_assist_material")[0][0] == "字", "20001 字 → 400，内容不变", (r, e))
    r, e = run("改材料", current_user="t1", mat_id=1, mat_content=" " * 5 + "字" * 20000 + " " * 5)
    check(e == "" , "去首尾空白后 20000 字可以", (r, e))

    print("六、课堂练习转出题草稿")
    db = seed(BASE + [mat(kind="exercise", title="课堂练习：点一", content="【题目】\n1. 题一\n2、题二\n3．题三\n【答案与解析】\n答案 1. 略", status="saved")])
    calls = []
    r, e = run("练习转出题草稿", eng=engine(None, calls), current_user="t1", mat_id=1)
    nd = q(db, "SELECT count(*) FROM teacher_assist_draft")[0][0]
    check(e == "" and r["ok"] == 1 and r["status"] == "ok" and r["mat_id"] == 1 and str(r["draft_id"]) == "1" and nd == 1, "转草稿：ok、draft_id=1、assist_draft 行数 0→1", (r, e, nd))
    d = q(db, "SELECT teacher, subject_id, kind, status FROM teacher_assist_draft")[0]
    check(d == ("t1", 1, "quiz_add", "pending"), "草稿 quiz_add、pending（待确认）", d)
    check(q(db, "SELECT count(*) FROM quiz_question")[0][0] == 0, "转草稿不写题库")
    check(any("课堂练习：点一" in c and "题二" in c for c in calls), "ref_text 带标题和练习全文交给草稿", [c[:80] for c in calls])
    check(q(db, "SELECT status, content FROM teacher_assist_material")[0][0] == "saved", "材料本身不变")
    r, e = run("练习转出题草稿", eng=engine(), current_user="t1", mat_id=1)
    check(e == "" and str(r["draft_id"]) == "2" and q(db, "SELECT count(*) FROM teacher_assist_draft")[0][0] == 2, "可再转一次，各出一份草稿（行数 2）", (r, e))
    r, e = run("练习转草稿页面", eng=engine(), current_user="t1", mat_id=1)
    check(e == "" and r["note"].startswith("已生成出题草稿 #3：") and q(db, "SELECT count(*) FROM teacher_assist_draft")[0][0] == 3
          and r["mat_note"] == "共1份", "练习转草稿页面：note 与行数 3", (r, e))
    db = seed(BASE + [mat(kind="handout", content="1.题一")])
    r, e = run("练习转出题草稿", current_user="t1", mat_id=1)
    check(e == "400" and q(db, "SELECT count(*) FROM teacher_assist_draft")[0][0] == 0, "非课堂练习 → 400、无草稿", (r, e))
    r, e = run("练习转草稿页面", current_user="t1", mat_id=1)
    check(e == "400", "练习转草稿页面 非练习 400", (r, e))

    print("七、权限（别人的 404 / 只读老师 403 / 学生 403）")
    multi = [("kg_point", dict(code="math.a", title="代数", subject_id=2)),
             ("subject_student", dict(subject_id=2, learner="s1", assigned_by="t1", status="active", created_at="2026-01-01"))]
    db = seed(BASE + [mat(teacher="t2", title="别人的", status="draft")])
    for fn, kw in [("取材料", {}), ("保存材料", {}), ("删材料", {}), ("改材料", dict(mat_content="x")), ("练习转出题草稿", {}),
                   ("载入材料页面", {}), ("导出材料页面", {}), ("挂回材料消息", dict(msg_id=5))]:
        r, e = run(fn, current_user="t1", mat_id=1, **kw)
        check(e == "404", f"别人的材料 {fn} → 404", (r, e))
    check(q(db, "SELECT title, status, content, source_msg_id FROM teacher_assist_material")[0] == ("别人的", "draft", "正文", None), "别人的材料原样未动")
    r, e = run("列材料", current_user="t1")
    check(r["total"] == 0 and r["materials"] == [], "列材料看不到别人的", r)
    r, e = run("取材料", current_user="t2", mat_id=1)
    check(e == "" and r["title"] == "别人的", "本人能取", (r, e))

    db = seed(BASE + multi + [mat(teacher="t2", subject_id=2, title="t2数学", status="draft")])
    ro = [("t2", "teacher", "只读老师"), ("s1", "student", "学生")]
    for who, role, name in ro:
        for fn, kw in [("生成材料", dict(kind="handout", message="写讲义")), ("保存材料", dict(mat_id=1)), ("改材料", dict(mat_id=1, mat_content="x")),
                       ("删材料", dict(mat_id=1)), ("练习转出题草稿", dict(mat_id=1)), ("保存材料页面", dict(mat_id=1)),
                       ("改材料页面", dict(mat_id=1, mat_content="x")), ("删材料页面", dict(mat_id=1)), ("练习转草稿页面", dict(mat_id=1))]:
            r, e = run(fn, current_user=who, current_role=role, auth_mode="on", subject=2, **kw)
            check(e == "403", f"{name}{fn} → 403", (r, e))
    check(q(db, "SELECT count(*), min(status), min(title) FROM teacher_assist_material")[0] == (1, "draft", "t2数学"), "被拒后材料原样未动")
    check(q(db, "SELECT count(*) FROM teacher_assist_draft")[0][0] == 0, "被拒后无草稿")
    r, e = run("列材料", current_user="t2", current_role="teacher", auth_mode="on", subject=2)
    check(e == "" and r["total"] == 1, "只读老师读：能列自己的材料", (r, e))
    # 协作教师可写
    db = seed(BASE + multi + [("subject_teacher", dict(subject_id=2, teacher="t2", role="editor", created_at="2026-01-01")),
                              mat(teacher="t2", subject_id=2, title="t2数学", status="draft")])
    r, e = run("保存材料", current_user="t2", mat_id=1, current_role="teacher", auth_mode="on", subject=2)
    check(e == "" and r["saved"] == 1, "协作教师能保存自己的材料", (r, e))

    print("八、跨科目")
    db = seed(BASE + multi + [mat(subject_id=2, title="数学材料", status="draft"), mat(subject_id=1, title="语法材料", status="draft")])
    for fn, kw in [("取材料", {}), ("保存材料", {}), ("删材料", {}), ("改材料", dict(mat_content="x")), ("练习转出题草稿", {}), ("挂回材料消息", dict(msg_id=3))]:
        r, e = run(fn, current_user="t1", mat_id=1 if True else 0, **kw)
        # id=1 是科目 2 的材料，默认科目 1 视角看不到
        check(e == "404", f"科目 1 视角 {fn} 科目 2 的材料 → 404", (r, e))
    check(q(db, "SELECT count(*) FROM teacher_assist_material")[0][0] == 2 and q(db, "SELECT status FROM teacher_assist_material WHERE id=1")[0][0] == "draft",
          "跨科目写操作没改动")
    r, e = run("列材料", current_user="t1")
    check(r["total"] == 1 and r["materials"][0]["mat_title"] == "语法材料", "列材料只列本科目", r)
    r, e = run("列材料", current_user="t1", current_role="teacher", auth_mode="off", subject=2)
    check(e == "" and r["total"] == 1 and r["materials"][0]["mat_title"] == "数学材料", "切到科目 2 只看到数学材料", (r, e))
    r, e = run("取材料", current_user="t1", mat_id=1, subject=2)
    check(e == "" and r["title"] == "数学材料", "科目 2 视角能取", (r, e))
    r, e = run("生成材料", eng=engine("x"), current_user="t1", kind="handout", message="写讲义", subject=2)
    check(e == "" and q(db, "SELECT subject_id FROM teacher_assist_material WHERE id=3")[0][0] == 2, "在科目 2 生成的材料 subject_id=2", (r, e))
    r, e = run("列材料", current_user="t1", current_role="teacher", auth_mode="on", subject=99)
    check(e in ("404", "400"), "不存在的科目报错", (r, e))

    print("九、按消息列材料 / 挂回材料消息")
    db = seed(BASE + multi + [mat(kind="exercise", title="练习", source_msg_id=2, status="draft"),
                              mat(kind="handout", title="讲义2", source_msg_id=3, status="saved"),
                              mat(teacher="t2", kind="exercise", title="别人的", source_msg_id=2),
                              mat(subject_id=2, kind="exercise", title="别科目", source_msg_id=2),
                              mat(kind="lesson_plan", title="无来源")])
    r, e = run("按消息列材料", current_user="t1", msg_ids="1,2,3,abc,-4")
    check(e == "" and r["total"] == 2 and [i["mat_id"] for i in r["items"]] == [1, 2] and [i["source_msg_id"] for i in r["items"]] == [2, 3],
          "按消息列材料：只本人本科目、id 升序", (r, e))
    a1 = [(b["label"], b["action"], b["carry"], b["kind"]) for b in r["items"][0]["actions"]]
    check(a1 == [("保存", "assist_material_save", {"mat_id": 1}, "primary"), ("导出", "assist_material_export", {"mat_id": 1}, ""),
                 ("做成出题草稿", "assist_material_to_draft", {"mat_id": 1}, "")], "draft 课堂练习按钮：保存 / 导出 / 做成出题草稿", a1)
    a2 = [b["label"] for b in r["items"][1]["actions"]]
    check(a2 == ["导出"], "saved 讲义按钮只有导出", a2)
    check(r["items"][0]["links"] == [{"href": "#教学材料?浮层=编辑材料&mat_id=1", "text": "打开材料 #1"}], "links 指向编辑浮层", r["items"][0]["links"])
    r, e = run("按消息列材料", current_user="t1", msg_ids="abc,")
    check(e == "" and r["total"] == 0 and r["items"] == [], "无有效 id → 空", (r, e))
    r, e = run("按消息列材料", current_user="t1", msg_ids=[2, 3])
    check(e == "" and r["total"] == 2, "msg_ids 也收列表", (r, e))
    r, e = run("挂回材料消息", current_user="t1", mat_id=5, msg_id=9)
    check(e == "" and r == {"ok": 1, "mat_id": 5, "source_msg_id": 9}, "挂回：返回 source_msg_id=9", (r, e))
    check(q(db, "SELECT source_msg_id, title, status FROM teacher_assist_material WHERE id=5")[0] == (9, "无来源", "draft"), "只改 source_msg_id")
    r, e = run("按消息列材料", current_user="t1", msg_ids="9")
    check(r["total"] == 1 and r["items"][0]["mat_id"] == 5, "挂回后能按消息列出", r)
    for bad in ("0", "abc", "-1"):
        r, e = run("挂回材料消息", current_user="t1", mat_id=5, msg_id=bad)
        check(e == "400", f"msg_id={bad} → 400", (r, e))
    r, e = run("挂回材料消息", current_user="t1", mat_id=77, msg_id=9)
    check(e == "404", "材料不存在 404", (r, e))
    r, e = run("按消息列材料", current_user="", msg_ids="2")
    check(e == "400", "current_user 为空 400", (r, e))
    # 生成后挂回，删后按消息列不出现
    db = seed(BASE)
    r, e, _ = gen("x", kind="handout", message="写讲义")
    run("挂回材料消息", current_user="t1", mat_id=r["mat_id"], msg_id=4)
    run("删材料", current_user="t1", mat_id=r["mat_id"])
    r, e = run("按消息列材料", current_user="t1", msg_ids="4")
    check(r["total"] == 0, "材料删后那条消息没有按钮", r)

    print("十、页面函数")
    db = seed([mat(kind="handout", title="甲", status="draft"), mat(kind="lesson_plan", title="乙", status="saved")])
    r, e = run("材料页面", current_user="t1", mat_filter="教案")
    check(e == "" and r["mat_note"] == "共1份" and len(r["materials"]) == 1 and r["materials"][0]["mat_title"] == "乙", "筛选教案：共1份", r)
    r, e = run("材料页面", current_user="t1", mat_filter="全部")
    check(r["mat_note"] == "共2份，未保存1份（7天后自动清掉）", "筛选全部", r)
    r, e = run("材料页面", current_user="t1", mat_filter="诗")
    check(e == "400", "筛选类型不对 400", (r, e))
    r, e = run("保存材料页面", current_user="t1", mat_id=1)
    check(r["mat_note"] == "共2份" and q(db, "SELECT status FROM teacher_assist_material WHERE id=1")[0][0] == "saved", "保存材料页面：抬头无未保存", (r, e))
    r, e = run("删材料页面", current_user="t1", mat_id=1)
    check(r["mat_note"] == "共1份" and q(db, "SELECT count(*) FROM teacher_assist_material")[0][0] == 1, "删材料页面", (r, e))
    r, e = run("材料页面", current_user="t3")
    check(r["mat_note"] == "" and r["materials"] == [], "无材料抬头为空", r)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n通过 {passed} / {passed + failed}")
sys.exit(1 if failed else 0)
