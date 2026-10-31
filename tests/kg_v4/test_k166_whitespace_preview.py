# -*- coding: utf-8 -*-
"""kg_v4 首尾空白传参与设定预览按科目（K166）：约定用例只能比顶层键，这里离线调函数核对。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_k166_whitespace_preview.py
    （--record：在改前代码上截下日语科目的设定预览版式写进 GOLDEN 文件，只在建 GOLDEN 时用）

拷一份 kg_v4 到临时目录，用约定用例的运行器（cases.build_sql / reset_db / call）造数据、调函数。离线，假模型按提示词回。
  教师助手：学生只在 Python 科目作答（列学生 的 last_at 取不到，学生行以空格结尾）时问学情 / 教学建议不报错，回答提示词不含「日语」
  assist_common：「小明 同学」「列表 的用法」这类带空格的说法能匹配上
  assist_draft：模型写的解析、必须准确的信息以换行结尾时校验草稿不报错
  AI 老师设定预览：日语科目版式与改前逐字一致（GOLDEN）；Python 科目不出现「日语」、用本科目的老师设定；示例提问首尾有空白不报错
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
GOLDEN = Path(__file__).resolve().parent / "k166_preview_golden.json"
sys.path.insert(0, str(ROOT))

from tools.dslagent.packs.dslproj import cases as K, project as P  # noqa: E402

RECORD = "--record" in sys.argv
passed = failed = 0


def check(ok, msg, detail=None):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg + ("" if ok or detail is None else f"\n      {detail}"))


tmp = Path(tempfile.mkdtemp(prefix="kg_v4_k166_"))
ws = tmp / "kg_v4"
shutil.copytree(SRC, ws, ignore=K.COPY_IGNORE, symlinks=True)
os.environ["DSL_NOW"] = K.DEFAULT_NOW
SQL = K.build_sql(ws, sorted(set(P.closure(ws, "teacher_assist")) | set(P.closure(ws, "teacher_rules"))))


def subj(code, name, kind, levels):
    return ("subject_info", dict(code=code, name=name, kind=kind, caps="x", levels=levels, qtypes="choice", visibility="public",
                                 owner="t1", status="active", created_at="2026-01-01", updated_at="2026-01-01"))


SUBJECTS = [subj("jp_grammar", "日语语法", "language", "N5,N4,N3,N2,N1"), subj("python", "Python 编程", "general", "入门,基础,进阶")]
DATA = [
    ("account_user", dict(username="s1", password_hash="x", display_name="小明", role="student", disabled=0, created_at="2025-12-01")),
    ("subject_student", dict(subject_id=1, learner="s1", assigned_by="t1", status="active", created_at="2026-01-01")),
    ("subject_student", dict(subject_id=2, learner="s1", assigned_by="t1", status="active", created_at="2026-01-01")),
    ("kg_point", dict(code="P1", title="は和が", subject_id=1)),
    ("kg_item", dict(code="I1", name="は的用法", point_code="P1", subject_id=1)),
    ("kg_point", dict(code="python.list", title="列表", subject_id=2)),
    ("kg_item", dict(code="python.list1", name="列表切片", point_code="python.list", subject_id=2)),
    # s1 只在 Python 科目作答：account.列学生 按日语科目取 last_at，取不到 → 班级上下文的学生行以「最近学习 」结尾
    ("progress_answer", dict(learner="s1", point_code="python.list", question_no="py.q1", correct=1, at="2026-01-01", subject_id=2)),
    ("progress_score", dict(learner="s1", point_code="python.list", score=100, at="2026-01-01", subject_id=2)),
    ("teacher_rules_setting", dict(kind="memory", content="学生基础弱", enabled=1, once=0, version=1, author="t1",
                                   updated_at="2026-01-01 09:00:00", subject_id=0)),
]
BANNED = ("日语", "语法", "JLPT")
K_INTENT = "教师端助手的意图分类器"
K_ANSWER = "像同事一样和老师说话，只读。"


def seed():
    db = K.reset_db(ws, SQL)
    con = sqlite3.connect(db)
    try:
        for table, kv in list(SUBJECTS) + list(DATA):
            con.execute(f"INSERT INTO {table}({', '.join(kv)}) VALUES({', '.join('?' * len(kv))})", list(kv.values()))
        con.commit()
    finally:
        con.close()
    return db


def engine(calls, intent):
    from tools import packs
    from tools.dsl import DSLEngine
    from tools.dsl_http import DEFAULT_PACKS
    from tools.dsl_service import get_services
    from tools.mock import MockClient

    def handler(prompt, system=None):
        calls.append(prompt)
        if K_INTENT in prompt:
            return json.dumps({"intent": intent, "student": "", "point": ""})
        return "好的，我们来看看。"

    eng = DSLEngine(MockClient(offline=True, handler=handler), workdir=Path(ws), verbose=False,
                    verbs=packs.registry(DEFAULT_PACKS, Path(ws)), verbs_root=packs.verbs_root())
    svc = get_services(Path(ws) / "services")
    svc.refresh()
    eng.services = svc
    eng.svc_module = None
    return eng


_n = [0]


def run(mod, fn, mock_intent="chitchat", **args):
    """→ (结果, 报错码或报错文字或空, 提示词列表)"""
    calls = []
    _n[0] += 1
    try:
        r, err = K.call(engine(calls, mock_intent), mod, fn, args, f"c{_n[0]}")
    except Exception as e:  # noqa: BLE001  脚本报错（引擎拒绝传参）也算失败，原样带出
        return None, f"{type(e).__name__}: {str(e)[:300]}", calls
    K.settle()
    return r, (str(err.get("code")) if isinstance(err, dict) else ("" if err in ("", None) else str(err))), calls


def layout(subject, message="ばかり是什么"):
    seed()
    r, e, _ = run("teacher_rules", "设定预览页面", preview_student="s1", preview_message=message, subject=subject)
    return ((r or {}).get("preview") or {}).get("layout", ""), e


if RECORD:
    lay, e = layout("1")
    assert not e and lay, (e, lay)
    GOLDEN.write_text(json.dumps({"preview_layout_jp": lay}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"已录 GOLDEN：{GOLDEN}（{len(lay)} 字）")
    shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0)

gold = json.loads(GOLDEN.read_text(encoding="utf-8"))

print("== 教师助手：学生行以空格结尾（只在 Python 科目作答）")
for intent in ("class_overview", "teaching_advice"):
    seed()
    r, e, calls = run("teacher_assist", "问助手", mock_intent=intent, current_user="t1", message="全班最近怎么样，给点教学建议", subject="2")
    check(e == "", f"Python 科目 {intent} 不报错", e)
    ans = next((c for c in calls if K_ANSWER in c), "")
    check(ans != "" and "小明（s1）" in ans, f"{intent} 的数据段里有学生行", ans[:300])
    check(ans != "" and not any(b in ans for b in BANNED), f"{intent} 回答提示词不含 日语/语法/JLPT",
          [b for b in BANNED if b in ans])
seed()
r, e, _ = run("teacher_assist", "取助手上下文", intent="class_overview", subject="2")
ctx = (r or {}).get("context_text", "")
check(e == "" and "最近学习" in ctx, "取助手上下文 Python 科目全班概况有学生行", e or ctx[:200])

print("== assist_common：带空格的说法")
seed()
r, e, _ = run("assist_common", "匹配学生", name="小明 同学", subject="1")
check(e == "" and (r or {}).get("status") == "one" and r.get("username") == "s1", "「小明 同学」匹配到 s1", e or r)
r, e, _ = run("assist_common", "匹配知识点", keyword="列表 的用法", subject="2")
check(e == "" and (r or {}).get("status") == "one" and r.get("code") == "python.list", "「列表 的用法」匹配到 python.list", e or r)

print("== assist_draft：模型输出以换行结尾")
seed()
pj = {"questions": [{"stem": "题一", "options": ["甲", "乙"], "answer": "乙", "explain": "因为是乙\n", "item_code": "I1", "level": "N5"}]}
r, e, _ = run("assist_draft", "校验草稿", kind="quiz_add", payload_json=json.dumps(pj, ensure_ascii=False), subject="1")
check(e == "" and str((r or {}).get("ok")) == "1", "解析以换行结尾的出题草稿校验通过", e or r)
pj = {"students": ["小明"], "must_info": "周五小测", "facts": "周五第三节\n", "rounds": 2}
r, e, _ = run("assist_draft", "校验草稿", kind="relay_add", payload_json=json.dumps(pj, ensure_ascii=False), subject="1")
check(e == "" and str((r or {}).get("ok")) == "1", "必须准确的信息以换行结尾的传达草稿校验通过", e or r)

pj = {"questions": [{"stem": "题\"一\"", "options": ["甲", "乙"], "answer": "乙", "explain": "引号\"和\\反斜杠\n第二行\n", "item_code": "I1", "level": "N5"}]}
r, e, _ = run("assist_draft", "校验草稿", kind="quiz_add", payload_json=json.dumps(pj, ensure_ascii=False), subject="1")
nq = ((r or {}).get("normalized") or {}).get("questions") or [{}]
check(e == "" and str((r or {}).get("ok")) == "1" and nq[0].get("explain") == pj["questions"][0]["explain"],
      "解析带双引号、反斜杠、换行：校验通过且原样保留", e or r)

print("== AI 老师设定预览")
lay, e = layout("1")
check(e == "" and lay == gold["preview_layout_jp"], "日语科目版式与改前逐字一致", e or lay[:200])
lay, e = layout("2", "列表怎么切片")
check(e == "", "Python 科目预览不报错", e)
check(lay.startswith("【系统提示词】你是一位Python 编程老师"), "Python 科目预览用本科目老师设定开头", lay[:80])
check("日语" not in lay and "语法" not in lay, "Python 科目预览不含「日语」「语法」", lay[:200])
check("学生现在说：【列表怎么切片】" in lay, "Python 科目预览带示例提问", lay[-80:])
lay, e = layout("2", " 列表怎么切片 \n")
check(e == "", "示例提问首尾有空白不报错", e)

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
