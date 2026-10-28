# -*- coding: utf-8 -*-
"""kg_v4 report 学生页面 的 student_notes 是数组、含该学生的设定行（K91）。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_report_notes.py

report.ui 用 lists.student_notes.length 判断「还没有设定」，所以 teacher_rules.设定列表 必须返回数组，
不能是 {items,total}。拷一份 kg_v4 到临时目录，用约定用例运行器造数据、调 学生页面，核对返回。离线，不调模型。
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "kg_v4"
sys.path.insert(0, str(ROOT))

from tools.dslagent.packs.dslproj import cases as K, contract as C, project as P  # noqa: E402

passed = failed = 0


def check(ok, msg, detail=None):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg + ("" if ok or detail is None else f"\n      {detail}"))


CASE = """用例 学生页面设定表
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 teacher_rules_setting kind=memory content=全班设定 enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_setting kind=memory content=只给小一 student=s1 enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_setting kind=memory content=只给小二 student=s2 enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 学生页面 student=s1
  得 有返回
"""

tmp = Path(tempfile.mkdtemp(prefix="kg_v4_report_notes_"))
ws = tmp / "kg_v4"
shutil.copytree(SRC, ws, ignore=K.COPY_IGNORE, symlinks=True)
os.environ.setdefault("DSL_NOW", K.DEFAULT_NOW)
try:
    base = (ws / "contracts" / "report.md").read_text(encoding="utf-8")
    text = base.split("\n## 用例", 1)[0] + "\n## 用例\n" + CASE
    c, probs = C.parse(text)
    check(not probs, "用例能按约定语法解析", probs[:3])
    sql = K.build_sql(ws, P.closure(ws, "report"))
    u = c["用例"][0]
    why = K.seed_case(ws, sql, "report", u)
    check(not why, "造数据", why)
    eng = K.make_engine(ws)
    r, err = K.call(eng, "report", u["调用"]["目标"], u["调用"]["参数"], "c")
    K.settle()
    check(err in ("", None) and isinstance(r, dict), "学生页面 有返回", f"报错 {err}：{r!r}"[:300])
    notes = r.get("student_notes") if isinstance(r, dict) else None
    check(isinstance(notes, list), "student_notes 是数组（不是 {items,total}）", repr(notes)[:300])
    contents = sorted(x.get("note_content") for x in notes) if isinstance(notes, list) else None
    check(contents == sorted(["只给小一", "全班设定"]), "含该学生的设定行和全班设定，不含别的学生的", contents)
    check(all("note_subject_label" in x and "can_edit" in x for x in (notes or [])) and bool(notes),
          "每行带科目列 note_subject_label 和 can_edit")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
