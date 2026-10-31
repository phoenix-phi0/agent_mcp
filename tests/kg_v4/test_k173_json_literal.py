# -*- coding: utf-8 -*-
"""选项 / 解析 / 人设拼进 JSON 字面量（K173 A1、A2）：值含英文双引号、反斜杠、换行、花括号时不坏。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_k173_json_literal.py

backlog A1：quiz.组题面 `{"letter": "{letter}", "text": "{tx}"}`、拼题卡 `{"key": "{o.letter}", "text": "{o.text}"}`、
判答案页面 `{"key": …, "text": "{op.text}", "state": …}`、提交答案 `"explain": "{ex}"`；
A2：subject.科目老师设定 / 科目助手设定 `"custom": "{custom}"` 等。
引擎对 JSON 字符串引号内的 {变量} 做 JSON 转义（tests/dsl/test_json_literal.py），这里在 kg_v4 真函数上逐个核对。
拷一份 kg_v4 到临时目录，用约定用例的运行器离线调函数，假模型。
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


tmp = Path(tempfile.mkdtemp(prefix="kg_v4_k173_"))
ws = tmp / "kg_v4"
shutil.copytree(SRC, ws, ignore=K.COPY_IGNORE, symlinks=True)
os.environ["DSL_NOW"] = K.DEFAULT_NOW
MODS = ("quiz", "subject")
SQL = K.build_sql(ws, sorted(set().union(*(set(P.closure(ws, m)) for m in MODS))))

# 选项：英文双引号、反斜杠（含 \n 这种两字符）、真换行、花括号（Python f 串）
OPTS = ['print("hi")', 'C:\\new\\table', '第一行\n第二行', 'f"{x}" 和 {y}']
EXPLAIN = '选 A：print("hi") 输出 hi；路径写成 "C:\\\\new" 才对\n第二行 {x}'
PERSONA = '你是一位"严格"的老师\\不废话\n先讲规则'
ASSIST = '你是"教研"助手 \\ 只说要点\n{别展开}'

BASE = [
    ("subject_info", dict(code="jp_grammar", name="日语语法", kind="language", caps="x", levels="N5,N4,N3,N2,N1",
                          qtypes="choice", visibility="public", owner="t1", status="active",
                          created_at="2026-01-01", updated_at="2026-01-01")),
    ("subject_info", dict(code="python", name="Python 编程", kind="general", caps="x", levels="入门,基础,进阶",
                          qtypes="choice", visibility="public", owner="t1", status="active",
                          created_at="2026-01-01", updated_at="2026-01-01")),
    ("kg_point", dict(code="python.str", title="字符串", subject_id=2)),
    ("kg_item", dict(code="python.str.i1", name="字符串字面量", point_code="python.str", subject_id=2)),
    ("quiz_question", dict(question_no="python.q1", level="入门", category="选择", stem='下面哪个输出 hi？', options="^".join(OPTS),
                           answer="A", item_code="python.str.i1", explain=EXPLAIN, subject_id=2)),
    ("subject_ai", dict(subject_id=2, persona=PERSONA, assist_prompt=ASSIST, updated_by="t1")),
]


def seed():
    db = K.reset_db(ws, SQL)
    con = sqlite3.connect(db)
    try:
        for table, kv in BASE:
            con.execute(f"INSERT INTO {table}({', '.join(kv)}) VALUES({', '.join('?' * len(kv))})", list(kv.values()))
        con.commit()
    finally:
        con.close()


_n = [0]


def run(mod, fn, **args):
    """→ (结果, 报错码或报错文字或空)"""
    _n[0] += 1
    try:
        r, err = K.call(K.make_engine(ws), mod, fn, args, f"c{_n[0]}")
    except Exception as e:  # noqa: BLE001  脚本报错也算失败，原样带出
        return None, f"{type(e).__name__}: {str(e)[:300]}"
    K.settle()
    return r, (str(err.get("code")) if isinstance(err, dict) else ("" if err in ("", None) else str(err)))


def texts(opts, key="text"):
    return sorted(o.get(key) for o in (opts or []) if isinstance(o, dict))


print("== quiz：选项、解析含双引号 / 反斜杠 / 换行 / 花括号")
seed()
r, e = run("quiz", "开始", learner="me", level="入门", category="选择", subject="2")
qn = (r or {}).get("question") or {}
check(e == "" and isinstance(qn, dict) and qn.get("is_choice") == 1, "开始 不报错、题面是对象且是选择题", e or r)
check(texts(qn.get("options")) == sorted(OPTS), "组题面 options 的 text 与库里逐字一致（4 个）", qn.get("options"))
check(sorted(o.get("letter") for o in qn.get("options") or []) == ["A", "B", "C", "D"], "组题面 letter 为 A–D",
      qn.get("options"))

seed()
r, e = run("quiz", "开始页面", learner="me", pick_level="入门", pick_kind="选择", subject="2")
card = (r or {}).get("card") or {}
check(e == "" and texts(card.get("options")) == sorted(OPTS), "开始页面（拼题卡）options 的 text 逐字一致", e or r)

shown = next((o["key"] for o in card.get("options") or [] if o.get("text") == OPTS[0]), "")
r, e = run("quiz", "判答案页面", learner="me", choice=shown, subject="2")
card = (r or {}).get("card") or {}
opts = card.get("options") or []
check(e == "" and texts(opts) == sorted(OPTS), "判答案页面 回显 options 的 text 逐字一致", e or r)
check(sorted(o.get("state") for o in opts) == ["dim", "dim", "dim", "right"], "判答案页面 state：选对的那项 right、其余 dim",
      opts)
check(str(card.get("explain") or "").startswith(EXPLAIN), "判答案页面 explain 以库里解析原文开头", card.get("explain"))

seed()
run("quiz", "开始", learner="me", level="入门", category="选择", subject="2")
r, e = run("quiz", "提交答案", learner="me", answer="B", subject="2")
check(e == "" and (r or {}).get("explain") == EXPLAIN and str((r or {}).get("correct")) == "0",
      "提交答案 explain 与库里逐字一致、判错", e or r)
r, e = run("quiz", "提交答案", learner="me", answer="B", subject="2")
check(e == "" and (r or {}).get("explain") == EXPLAIN and str((r or {}).get("repeated")) == "1",
      "重复提交 explain 与库里逐字一致", e or r)

print("== subject：custom 人设 / 助手提示词含双引号 / 反斜杠 / 换行 / 花括号")
seed()
r, e = run("subject", "科目老师设定", subject_id="2")
check(e == "" and isinstance(r, dict) and r.get("custom") == PERSONA, "科目老师设定 custom 与库里逐字一致", e or r)
check(isinstance(r, dict) and r.get("persona") == PERSONA, "科目老师设定 persona = custom（去尾标点空白）", r)
r, e = run("subject", "科目助手设定", subject_id="2")
check(e == "" and isinstance(r, dict) and r.get("custom") == ASSIST, "科目助手设定 custom 与库里逐字一致", e or r)
check(isinstance(r, dict) and r.get("intro") == ASSIST, "科目助手设定 intro = custom（去尾标点空白）", r)

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
