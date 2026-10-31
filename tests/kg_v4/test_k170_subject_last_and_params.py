# -*- coding: utf-8 -*-
"""kg_v4「最近学习」按科目取 + 剩余按位置传参改对象传参（K170）：约定用例只能比顶层键，这里离线调函数核对。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_k170_subject_last_and_params.py

拷一份 kg_v4 到临时目录，用约定用例的运行器（cases.build_sql / reset_db / call）造数据、调函数。离线，假模型。
  最近学习按科目：s1 只在科目 2 作答、s2 只在科目 1 作答 → account.列学生 / 列学生页面、report 学情、assist_common.学生范围、
    教师助手全班上下文在科目 2 下 s1 有最近学习、科目 1 下为空；不传科目（日语）与改前一样
  vocab：带首尾空白的搜索词、汉字/假名/意思、导入行「猫 | ねこ | 猫」不报错，存去空白后的值
  progress：作答原文带首尾空白不报错、原样存
  quiz：题目解析以换行结尾，判答案页面不报错
  teacher_rules：显示名首尾有空白、科目名首尾有空白时设定页不报错
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
    print(("  ✓ " if ok else "  ✗ ") + msg + ("" if ok or detail is None else f"\n      {str(detail)[:400]}"))


tmp = Path(tempfile.mkdtemp(prefix="kg_v4_k170_"))
ws = tmp / "kg_v4"
shutil.copytree(SRC, ws, ignore=K.COPY_IGNORE, symlinks=True)
os.environ["DSL_NOW"] = K.DEFAULT_NOW
MODS = ("account", "report", "assist_common", "teacher_assist", "teacher_rules", "vocab", "progress", "quiz")
SQL = K.build_sql(ws, sorted(set().union(*(set(P.closure(ws, m)) for m in MODS))))


def subj(code, name, kind, levels):
    return ("subject_info", dict(code=code, name=name, kind=kind, caps="x", levels=levels, qtypes="choice", visibility="public",
                                 owner="t1", status="active", created_at="2026-01-01", updated_at="2026-01-01"))


BASE = [
    subj("jp_grammar", "日语语法", "language", "N5,N4,N3,N2,N1"), subj("python", "Python 编程", "general", "入门,基础,进阶"),
    ("account_user", dict(username="t1", password_hash="x", display_name="王老师", role="teacher", disabled=0, created_at="2025-12-01")),
    ("account_user", dict(username="s1", password_hash="x", display_name="小明", role="student", disabled=0, created_at="2025-12-01")),
    ("account_user", dict(username="s2", password_hash="x", display_name="小红", role="student", disabled=0, created_at="2025-12-01")),
    ("subject_teacher", dict(subject_id=1, teacher="t1", role="owner", created_at="2026-01-01")),
    ("subject_teacher", dict(subject_id=2, teacher="t1", role="owner", created_at="2026-01-01")),
    ("subject_student", dict(subject_id=1, learner="s1", assigned_by="t1", status="active", created_at="2026-01-01")),
    ("subject_student", dict(subject_id=2, learner="s1", assigned_by="t1", status="active", created_at="2026-01-01")),
    ("subject_student", dict(subject_id=1, learner="s2", assigned_by="t1", status="active", created_at="2026-01-01")),
    ("subject_student", dict(subject_id=2, learner="s2", assigned_by="t1", status="active", created_at="2026-01-01")),
    ("kg_point", dict(code="P1", title="は和が", subject_id=1)),
    ("kg_item", dict(code="I1", name="は的用法", point_code="P1", subject_id=1)),
    ("kg_point", dict(code="python.list", title="列表", subject_id=2)),
    # s1 只在 Python 科目作答，s2 只在日语科目作答
    ("progress_answer", dict(learner="s1", point_code="python.list", question_no="py.q1", correct=1, answer="A",
                             at="2026-01-02 10:00:00", subject_id=2)),
    ("progress_score", dict(learner="s1", point_code="python.list", score=100, at="2026-01-02 10:00:00", subject_id=2)),
    ("progress_answer", dict(learner="s2", point_code="P1", question_no="Q1", correct=1, answer="A",
                             at="2026-01-03 11:00:00", subject_id=1)),
    ("progress_score", dict(learner="s2", point_code="P1", score=100, at="2026-01-03 11:00:00", subject_id=1)),
]
S1_AT, S2_AT = "2026-01-02 10:00:00", "2026-01-03 11:00:00"


def seed(extra=(), sql=()):
    db = K.reset_db(ws, SQL)
    con = sqlite3.connect(db)
    try:
        for table, kv in list(BASE) + list(extra):
            con.execute(f"INSERT INTO {table}({', '.join(kv)}) VALUES({', '.join('?' * len(kv))})", list(kv.values()))
        for s in sql:
            con.execute(s)
        con.commit()
    finally:
        con.close()
    return db


def q(sql, *args):
    con = sqlite3.connect(ws / "app.db")
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


_n = [0]


def run(mod, fn, **args):
    """→ (结果, 报错码或报错文字或空)"""
    _n[0] += 1
    try:
        r, err = K.call(K.make_engine(ws), mod, fn, args, f"c{_n[0]}")
    except Exception as e:  # noqa: BLE001  脚本报错（引擎拒绝传参）也算失败，原样带出
        return None, f"{type(e).__name__}: {str(e)[:300]}"
    K.settle()
    return r, (str(err.get("code")) if isinstance(err, dict) else ("" if err in ("", None) else str(err)))


def by_user(rows, key="username"):
    return {x.get(key): x for x in (rows or []) if isinstance(x, dict)}


print("== 最近学习按科目：account.列学生 / 列学生页面")
seed()
r, e = run("account", "列学生", subject="2")
st = by_user((r or {}).get("students"))
check(e == "" and st.get("s1", {}).get("last_at") == S1_AT and str(st.get("s1", {}).get("answer_count")) == "1",
      "列学生 科目 2：s1 有最近学习、作答 1", e or st)
check(e == "" and st.get("s2", {}).get("last_at") == "" and str(st.get("s2", {}).get("answer_count")) == "0",
      "列学生 科目 2：s2（只在日语作答）最近学习为空", e or st)
r, e = run("account", "列学生", subject="1")
st = by_user((r or {}).get("students"))
check(e == "" and st.get("s1", {}).get("last_at") == "" and st.get("s2", {}).get("last_at") == S2_AT,
      "列学生 科目 1：s1 为空、s2 有值", e or st)
r, e = run("account", "列学生")
st = by_user((r or {}).get("students"))
check(e == "" and str((r or {}).get("total")) == "2","列学生 不传科目：学生范围仍是全部学生账号", e or r)
check(e == "" and st.get("s1", {}).get("last_at") == "" and st.get("s2", {}).get("last_at") == S2_AT,
      "列学生 不传科目：同日语科目（与改前一样）", e or st)
r, e = run("account", "列学生页面", subject="2")
st = by_user(r)
check(e == "" and st.get("s1", {}).get("last_active") == S1_AT and str(st.get("s1", {}).get("attempt_n")) == "1",
      "列学生页面 科目 2：s1 最近学习有值", e or r)
r, e = run("account", "列学生页面")
st = by_user(r)
check(e == "" and st.get("s1", {}).get("last_active") == "" and st.get("s2", {}).get("last_active") == S2_AT,
      "列学生页面 不传科目：同日语科目", e or r)
seed(extra=[("subject_pref", dict(learner="t1", subject_id=2))])
r, e = run("account", "列学生页面", learner="t1", current_role="teacher", auth_mode="on")
st = by_user(r)
check(e == "" and st.get("s1", {}).get("last_active") == S1_AT,
      "列学生页面 登录模式、老师当前科目是 Python：s1 最近学习有值", e or r)
r, e = run("account", "设置学生停用", username="s2", disabled="1", learner="t1", current_role="teacher", auth_mode="on")
st = by_user(r)
check(e == "" and st.get("s1", {}).get("last_active") == S1_AT and st.get("s2", {}).get("account_state") == "已停用",
      "设置学生停用 刷新的列表也按当前科目取", e or r)

print("== 最近学习按科目：学情 / 学生范围 / 教师助手")
seed()
r, e = run("report", "取全班学情", subject="2")
st = by_user((r or {}).get("students"))
check(e == "" and st.get("s1", {}).get("last_at") == S1_AT, "取全班学情 科目 2：s1 最近学习有值", e or st)
r, e = run("report", "取全班学情", subject="1")
st = by_user((r or {}).get("students"))
check(e == "" and st.get("s1", {}).get("last_at") == "" and st.get("s2", {}).get("last_at") == S2_AT,
      "取全班学情 科目 1：s1 为空、s2 有值（日语照常）", e or st)
r, e = run("report", "学情首页页面", subject="2")
rows = r if isinstance(r, list) else None
if rows is None and isinstance(r, dict):
    rows = next((v for v in r.values() if isinstance(v, list) and v and isinstance(v[0], dict) and "last_active" in v[0]), [])
st = by_user(rows)
check(e == "" and st.get("s1", {}).get("last_active") == S1_AT, "学情首页页面 科目 2：s1 最近学习有值", e or r)
r, e = run("assist_common", "学生范围", subject="2")
st = by_user((r or {}).get("students"))
check(e == "" and st.get("s1", {}).get("last_at") == S1_AT and st.get("s2", {}).get("last_at") == "",
      "assist_common.学生范围 科目 2：按科目取", e or st)
r, e = run("teacher_assist", "取助手上下文", intent="class_overview", subject="2")
ctx = (r or {}).get("context_text", "")
check(e == "" and "最近学习 2026-01-02" in ctx, "教师助手全班概况（Python）学生行带最近学习日期", e or ctx[:300])

print("== vocab：首尾空白")
seed()
r, e = run("vocab", "新建单词", kanji="猫 ", kana=" ねこ", meaning="猫\n", subject="1")
check(e == "" and str((r or {}).get("ok")) == "1", "新建单词 汉字/假名/意思带首尾空白不报错", e or r)
check(q("SELECT kanji, kana, meaning FROM vocab_word") == [("猫", "ねこ", "猫")], "新建单词 存去空白后的值",
      q("SELECT kanji, kana, meaning FROM vocab_word"))
r, e = run("vocab", "新建单词", kanji="猫", kana="ねこ ", subject="1")
check(e == "400", "新建单词 去空白后与已有词相同 → 400 单词已存在", e or r)
r, e = run("vocab", "列单词", keyword=" 猫 ", subject="1")
check(e == "" and str((r or {}).get("total")) == "1", "列单词 搜索词带首尾空白能搜到", e or r)
r, e = run("vocab", "取单词", kanji="猫 ", kana=" ねこ", subject="1")
check(e == "" and (r or {}).get("kana") == "ねこ", "取单词 汉字/假名带首尾空白能取到", e or r)
r, e = run("vocab", "修改单词", word_id="1", kanji=" 猫", kana="ねこ", meaning=" 猫咪 ", point_code="", subject="1")
check(e == "" and q("SELECT meaning FROM vocab_word WHERE id=1") == [("猫咪",)], "修改单词 带首尾空白不报错、存去空白后的值",
      e or q("SELECT kanji, kana, meaning FROM vocab_word"))
(ws / "uploads").mkdir(exist_ok=True)
(ws / "uploads" / "k170_words.txt").write_text("猫 | ねこ | 小猫 | P1\n犬 | いぬ | 狗\n", encoding="utf-8")
r, e = run("vocab", "导入单词", file_path="uploads/k170_words.txt", subject="1")
check(e == "" and str((r or {}).get("created")) == "1" and str((r or {}).get("updated")) == "1",
      "导入单词 「猫 | ねこ | 小猫 | P1」不报错：1 更新 1 新增", e or r)
check(q("SELECT kanji, kana, meaning, point_code FROM vocab_word ORDER BY id") == [("猫", "ねこ", "小猫", "P1"), ("犬", "いぬ", "狗", "")],
      "导入单词 各项去首尾空白后存", q("SELECT kanji, kana, meaning, point_code FROM vocab_word ORDER BY id"))

print("== progress：作答原文首尾空白")
seed()
r, e = run("progress", "记作答", learner="s1", point_code="P1", question_no="Q9", correct="0", answer=" ねこ \n", subject="1")
check(e == "" and str((r or {}).get("ok")) == "1", "记作答 answer 首尾有空白不报错", e or r)
check(q("SELECT answer FROM progress_answer WHERE question_no='Q9'") == [(" ねこ \n",)], "记作答 answer 原样存",
      q("SELECT answer FROM progress_answer WHERE question_no='Q9'"))
odd = ' 引号"和\\反斜杠\n第二行 '
r, e = run("progress", "记作答", learner="s1", point_code="P1", question_no="Q10", correct="1", answer=odd, subject="1")
check(e == "" and q("SELECT answer, correct FROM progress_answer WHERE question_no='Q10'") == [(odd, 1)],
      "记作答 answer 带双引号、反斜杠、换行：原样存", e or q("SELECT answer, correct FROM progress_answer WHERE question_no='Q10'"))

print("== quiz：解析以换行结尾")
seed(extra=[("quiz_question", dict(question_no="Q1", level="N5", category="接续", stem="题干", answer="です", item_code="I1",
                                   explain="解析一\n"))])
r, e = run("quiz", "开始", learner="me", level="N5", category="接续", subject="1")
check(e == "", "开始 不报错", e)
r, e = run("quiz", "判答案页面", learner="me", given="です", subject="1")
ex = (((r or {}).get("card") or {}).get("explain")) or ""
check(e == "" and ex.startswith("解析一\n") and "考的是：は的用法" in ex, "判答案页面 解析以换行结尾不报错、拼上「考的是」", e or r)

print("== teacher_rules：显示名 / 科目名首尾有空白")
seed(extra=[("teacher_rules_relay", dict(urgency="normal", must_info="下周三小测", rounds=2, enabled=1, author="t1",
                                         updated_at="2026-01-01 09:00:00"))],
     sql=["UPDATE account_user SET display_name=' 小明' WHERE username='s1'",
          "UPDATE subject_info SET name='Python 编程 ' WHERE code='python'"])
for sid in ("1", "2"):
    r, e = run("teacher_rules", "设定首页页面", subject=sid)
    opts = by_user((r or {}).get("note_students"), "value")
    check(e == "" and opts.get("s1", {}).get("label") == " 小明（s1）", f"设定首页页面 科目 {sid}：显示名首尾有空白不报错、原样保留", e or r)
r, e = run("teacher_rules", "传达状态列表", subject="1")
check(e == "" and any(x.get("relay_student_label") == " 小明（s1）" for x in (r or [])), "传达状态列表 显示名首尾有空白不报错、原样保留", e or r)
r, e = run("teacher_rules", "设定列表", subject="2")
check(e == "", "设定列表 科目名首尾有空白不报错", e)
r, e = run("teacher_rules", "传达列表", subject="2")
check(e == "", "传达列表 科目名首尾有空白不报错", e)

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
