# -*- coding: utf-8 -*-
"""kg_v4 科目内容日语替换（K182 日语版第 3 期）：ja 用 subject_content_translation 译文、缺译文回退中文；zh 逐字不变；判题不受影响。

    cd /workspace/k182_wt && /workspace/agent_mcp/.venv/bin/python tests/kg_v4/test_i18n_content_ja.py

口径（契约 contracts/{subject,quiz,progress,report}.md 的 K182 伪代码）：
  - 只翻展示路径：组题面 stem/options、提交答案 explain、判答案页面条目名、复习薄弱点文案、
    progress 三个页面函数的 label、report 学情页标签与取题干、subject 列我的科目科目名；
  - 不翻：编辑/管理路径（kg 取/列等共享读）、判题比对与写库、提示词输入（取进度摘要/取学生学情等）；
  - lang 来源：subject.取界面语言（内部守卫 account_user 表存在才查 subject_user_lang，查不到视为 zh）；report 用 account.取语言；缺译文回退中文。
译文数据用内嵌小集（真 442 行译文由 content/python_v1/ja/*.tsv 经导入脚本进库，在第八节验证）。
"""

import os
import shutil
import sqlite3
import subprocess
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


def acct(user, role, lang=None):
    kv = dict(username=user, password_hash="x", display_name=user, role=role, disabled=0, created_at="2026-01-01")
    if lang:
        kv["lang"] = lang
    return ("account_user", kv)


def tr(tbl, rk, fd, text):
    return ("subject_content_translation", dict(tbl=tbl, row_key=rk, field=fd, lang="ja", text=text, updated_at="2026-01-01"))


def subj(code, name, kind, levels):
    return ("subject_info", dict(code=code, name=name, kind=kind, caps="x", levels=levels, qtypes="choice", visibility="public",
                                 owner="t1", status="active", created_at="2026-01-01", updated_at="2026-01-01"))


SUBJECTS = [subj("jp_grammar", "日语语法", "language", "N5,N4,N3,N2,N1"), subj("python", "Python 编程", "general", "入门,基础,进阶")]
BASE = [
    ("kg_point", dict(code="python.list", title="列表", subject_id=2)),
    ("kg_point", dict(code="python.tuple", title="元组", subject_id=2)),
    ("kg_point", dict(code="P1", title="は和が", subject_id=1)),
    ("kg_item", dict(code="python.list_append", name="append() 追加一个", point_code="python.list", subject_id=2)),
    ("quiz_question", dict(question_no="python.Q1", course="", level="入门", category="选择", stem="下面代码输出什么？\nprint(1 + 1)",
                           options="2^1 1^11^报错", answer="A", explain="1 加 1 等于 2。", item_code="python.list_append", subject_id=2)),
    ("quiz_progress", dict(learner="u1", level="入门", category="选择", current_no="python.Q1", answered=0, right_count=0,
                           asked_nos="python.Q1", asked_count=1, mode="free", lesson_code="", round_start_id=0, seq=1,
                           last_correct=0, subject_id=2)),
    ("subject_student", dict(subject_id=2, learner="u1", assigned_by="", status="active", created_at="2026-01-01")),
    ("subject_student", dict(subject_id=1, learner="u1", assigned_by="", status="active", created_at="2026-01-01")),
]
TR = [
    tr("kg_point", "python.list", "title", "リスト"),
    tr("kg_item", "python.list_append", "name", "append() で 1 つ追加"),
    tr("quiz_question", "python.Q1", "stem", "次のコードの出力は？\nprint(1 + 1)"),
    tr("quiz_question", "python.Q1", "options", "2^1 1^11^エラー"),
    tr("quiz_question", "python.Q1", "explain", "1 + 1 は 2 です。"),
    tr("subject_info", "python", "name", "Python プログラミング"),
]

SQL = {}
_n = [0]


def make_ws():
    tmp = Path(tempfile.mkdtemp(prefix="kg_v4_k182_"))
    ws = tmp / "kg_v4"
    shutil.copytree(SRC, ws, ignore=K.COPY_IGNORE, symlinks=True)
    os.environ["DSL_NOW"] = K.DEFAULT_NOW
    return tmp, ws, K.build_sql(ws, P.closure(ws, "tutor"))


def seed(ws, sql, rows):
    db = K.reset_db(ws, sql)
    con = sqlite3.connect(db)
    try:
        for table, kv in list(SUBJECTS) + list(rows):
            cols = ", ".join(kv)
            qs = ", ".join("?" * len(kv))
            con.execute(f"INSERT INTO {table}({cols}) VALUES({qs})", list(kv.values()))
        con.commit()
    finally:
        con.close()
    return db


def engine(ws):
    from tools import packs
    from tools.dsl import DSLEngine
    from tools.dsl_http import DEFAULT_PACKS
    from tools.dsl_service import get_services
    from tools.mock import MockClient

    eng = DSLEngine(MockClient(offline=True, handler=lambda p, s=None: "好的。"), workdir=Path(ws), verbose=False,
                    verbs=packs.registry(DEFAULT_PACKS, Path(ws)), verbs_root=packs.verbs_root())
    svc = get_services(Path(ws) / "services")
    svc.refresh()
    eng.services = svc
    eng.svc_module = None
    return eng


def run(ws, mod, fn, **args):
    _n[0] += 1
    try:
        r, err = K.call(engine(ws), mod, fn, args, f"c{_n[0]}")
    except Exception as ex:
        return "", ("ERR: " + str(ex))[:100]
    K.settle()
    return r, (str(err.get("code")) if isinstance(err, dict) else ("" if err in ("", None) else str(err)))


print("一、subject.译文：zh 不查表、ja 取到、缺失回空")
tmp, ws, SQL[ws] = make_ws()
try:
    seed(ws, SQL[ws], BASE + TR + [acct("u1", "student", "ja")])
    r, e = run(ws, "subject", "译文", tbl="kg_point", row_key="python.list", field="title", lang="zh")
    check(e == "" and r.get("text") == "", "zh：不查表返回空串", (r, e))
    r, e = run(ws, "subject", "译文", tbl="kg_point", row_key="python.list", field="title", lang="ja")
    check(e == "" and r.get("text") == "リスト", "ja：取到译文", (r, e))
    r, e = run(ws, "subject", "译文", tbl="kg_point", row_key="python.var", field="title", lang="ja")
    check(e == "" and r.get("text") == "", "ja：无译文返回空串（回退中文由调用方处理）", (r, e))

    print("二、取做题状态（经组题面）：zh 逐字不变、ja 换译文且字母映射不变")
    seed(ws, SQL[ws], BASE + TR)
    rz, ez = run(ws, "quiz", "取做题状态", learner="u1", subject="2")
    qz = rz.get("question") if isinstance(rz, dict) else ""
    check(ez == "" and qz and qz.get("stem") == "下面代码输出什么？\nprint(1 + 1)", "zh：题干逐字不变", (qz, ez))
    map_z = {o["letter"]: o["text"] for o in (qz or {}).get("options", [])}
    check(not map_z or sorted(map_z.values()) == ["1 1", "11", "2", "报错"], "zh：四个选项原文", map_z)
    seed(ws, SQL[ws], BASE + TR + [acct("u1", "student", "ja")])
    rj, ej = run(ws, "quiz", "取做题状态", learner="u1", subject="2")
    qj = rj.get("question") if isinstance(rj, dict) else ""
    check(ej == "" and qj and qj.get("stem") == "次のコードの出力は？\nprint(1 + 1)", "ja：题干换译文（真实换行）", (qj, ej))
    map_j = {o["letter"]: o["text"] for o in (qj or {}).get("options", [])}
    check(not map_j or sorted(map_j.values()) == ["1 1", "11", "2", "エラー"], "ja：四选项译文且个数不变", map_j)
    check(bool(map_z) and len(map_z) == len(map_j) and
          all((map_z[k] == "报错") == (map_j[k] == "エラー") and (map_z[k] == "2") == (map_j[k] == "2") for k in map_z),
          "ja：字母与原文选项的映射不变（报错↔エラー、2↔2 同字母）", (map_z, map_j))
    ans_letter = [k for k, v in map_z.items() if v == "2"][0]

    print("三、提交答案：ja 判题照常、explain 日文；zh explain 逐字不变")
    seed(ws, SQL[ws], BASE + TR + [acct("u1", "student", "ja")])
    r, e = run(ws, "quiz", "提交答案", learner="u1", answer=ans_letter, subject="2")
    check(e == "" and r.get("correct") == 1, "ja：按字母判对（判题不受译文影响）", (r, e))
    check(r.get("explain") == "1 + 1 は 2 です。", "ja：explain 日文", r.get("explain"))
    check(r.get("correct_answer") == ans_letter, "ja：correct_answer 字母不变", r.get("correct_answer"))
    seed(ws, SQL[ws], BASE + TR)
    r, e = run(ws, "quiz", "提交答案", learner="u1", answer=ans_letter, subject="2")
    check(e == "" and r.get("correct") == 1 and r.get("explain") == "1 加 1 等于 2。", "zh：explain 逐字不变（对照）", (r, e))

    print("四、列我的科目：ja 换 Python 科目名、日语科目不换；zh 不变")
    seed(ws, SQL[ws], BASE + TR + [acct("u1", "student", "ja")])
    r, e = run(ws, "subject", "列我的科目", learner="u1", current_role="student")
    names = {s["code"]: s["name"] for s in r.get("subjects", [])}
    check(names.get("python") == "Python プログラミング", "ja：Python 科目名日文", names)
    check(names.get("jp_grammar") == "日语语法", "ja：日语科目名保持中文（无译文回退）", names)
    seed(ws, SQL[ws], BASE + TR)
    r, e = run(ws, "subject", "列我的科目", learner="u1", current_role="student")
    names = {s["code"]: s["name"] for s in r.get("subjects", [])}
    check(names.get("python") == "Python 编程", "zh：科目名逐字不变（对照）", names)

    print("五、progress 图谱页面/知识点页面：ja 换 label、缺译文回退")
    seed(ws, SQL[ws], BASE + TR + [acct("u1", "student", "ja")])
    r, e = run(ws, "progress", "图谱页面", learner="u1", subject="2")
    labels = {n["code"]: n["label"] for n in r.get("graph", {}).get("nodes", [])}
    check(labels.get("python.list") == "リスト" and labels.get("python.tuple") == "元组", "ja：有译文日文、无译文回退中文", labels)
    r, e = run(ws, "progress", "知识点页面", learner="u1", code="python.list", subject="2")
    ilabels = [i.get("label") for i in r.get("items", [])]
    check(ilabels == ["append() で 1 つ追加"], "ja：条目名日文", ilabels)
    seed(ws, SQL[ws], BASE + [acct("u1", "student", "ja")])
    r, e = run(ws, "progress", "图谱页面", learner="u1", subject="2")
    labels = {n["code"]: n["label"] for n in r.get("graph", {}).get("nodes", [])}
    check(labels.get("python.list") == "列表", "ja：完全无译文时全部回退中文", labels)
    seed(ws, SQL[ws], BASE + TR)
    r, e = run(ws, "progress", "图谱页面", learner="u1", subject="2")
    labels = {n["code"]: n["label"] for n in r.get("graph", {}).get("nodes", [])}
    check(labels.get("python.list") == "列表", "zh：图谱 label 逐字不变（对照）", labels)

    print("六、编辑/共享读路径不翻（ja 账号也不翻）")
    seed(ws, SQL[ws], BASE + TR + [acct("u1", "student", "ja"), acct("t1", "teacher", "ja")])
    r, e = run(ws, "kg", "列知识点", subject="2")
    titles = [p.get("title") for p in r.get("points", [])]
    check("列表" in titles and "リスト" not in titles, "kg.列知识点（管理/共享读）保持中文", titles)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("七、导入脚本：预检、写入、幂等（对正式库拷贝）")
tmp2 = Path(tempfile.mkdtemp(prefix="kg_v4_k182_import_"))
try:
    tmpdb = tmp2 / "import_test.db"
    shutil.copy("/workspace/dslagent_exp/kg_v4_data/app.db", tmpdb)
    M = ROOT / "kg_v4" / "scripts"
    subprocess.run([sys.executable, str(M / "migrate_subject_content_translation.py"), "--db", str(tmpdb)], check=True, capture_output=True)
    JA = "/workspace/dslagent_exp/content/python_v1/ja"
    imp = str(M / "import_content_ja.py")
    r1 = subprocess.run([sys.executable, imp, "--db", str(tmpdb), "--dir", JA], capture_output=True, text=True)
    check("预检通过：442 行" in r1.stdout, "预检通过 442 行", r1.stdout[-300:] + r1.stderr[-200:])
    check("未写库" in r1.stdout, "预检模式未写库", r1.stdout[-120:])
    r2 = subprocess.run([sys.executable, imp, "--db", str(tmpdb), "--dir", JA, "--apply"], capture_output=True, text=True)
    con = sqlite3.connect(tmpdb)
    n1 = con.execute("SELECT COUNT(*) FROM subject_content_translation WHERE lang='ja'").fetchone()[0]
    r3 = subprocess.run([sys.executable, imp, "--db", str(tmpdb), "--dir", JA, "--apply"], capture_output=True, text=True)
    n2 = con.execute("SELECT COUNT(*) FROM subject_content_translation WHERE lang='ja'").fetchone()[0]
    con.close()
    check(n1 == 442, "写入 442 行", n1)
    check(n2 == 442 and "现 442 行" in r3.stdout, "重复导入幂等（仍 442 行）", (n2, r3.stdout[-120:]))
finally:
    shutil.rmtree(tmp2, ignore_errors=True)

print(f"\n通过 {passed} / 失败 {failed}")
sys.exit(1 if failed else 0)
