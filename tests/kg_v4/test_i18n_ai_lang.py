# -*- coding: utf-8 -*-
"""kg_v4 AI 回答语言跟随界面（K181 日语版第 2 期）：假模型截提示词，ja 与 zh 逐字对照。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_i18n_ai_lang.py

GOLDEN_JA 口径：zh（含没填 lang、查无账号）提示词一字不改（zh GOLDEN 由 test_tutor_persona /
test_assist_persona 钉住，本文件不重复钉）；lang=ja 时只在约定位置多出同一句语言指示，其余与
zh 逐字一致。追加句（契约唯一措辞，前置一个空格）：
  「请用日语回答，专业术语第一次出现时用括号标注中文；与其他提示里的语言要求冲突时，以本句为准。」
注入点与 lang 来源（契约 contracts/{tutor,teacher_assist,report,account}.md）：
  tutor.答一轮（learner）      → 系统提示最末尾（传达事项段之后、【以下是学生相关内容】之前）
  tutor.总结本轮（learner）    → 整个提示词最末尾
  teacher_assist.答一轮（current_user）→ sysp 最末尾（回答规则之后、【数据】段之前）
  report.写学情总结（current_user）    → 提示词最末尾
覆盖：教师写了明确语言要求（AI老师设定 / 科目助手设定 的 custom 非空且含语言关键词）→ 不追加。
判意图等结构化调用不追加；日语科目在 ja 界面照常追加（跟随界面，不按科目特判）。
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


# 追加句（含前置空格）：ja 与 zh 唯一的差异
SP = " 请用日语回答，专业术语第一次出现时用括号标注中文；与其他提示里的语言要求冲突时，以本句为准。"
LANG_WORDS = ("中文", "汉语", "日文", "日语", "日本語", "中国語", "英文", "英语", "English", "Chinese", "Japanese")


def acct(user, role, lang=None):
    kv = dict(username=user, password_hash="x", display_name=user, role=role, disabled=0, created_at="2026-01-01")
    if lang:
        kv["lang"] = lang
    return ("account_user", kv)


def subj(code, name, kind, levels):
    return ("subject_info", dict(code=code, name=name, kind=kind, caps="x", levels=levels, qtypes="choice", visibility="public",
                                 owner="t1", status="active", created_at="2026-01-01", updated_at="2026-01-01"))


SUBJECTS = [subj("jp_grammar", "日语语法", "language", "N5,N4,N3,N2,N1"), subj("python", "Python 编程", "general", "入门,基础,进阶")]
ROUND = [
    ("kg_point", dict(code="P1", title="は和が", subject_id=1)),
    ("quiz_progress", dict(learner="u1", level="N5", category="选择", current_no="Q1", answered=1, right_count=1, asked_nos="Q1",
                           asked_count=1, mode="free", lesson_code="", round_start_id=0, seq=1, last_correct=1, subject_id=1)),
    ("progress_answer", dict(learner="u1", point_code="P1", question_no="Q1", correct=1, answer="A", at="2026-01-01", subject_id=1)),
    ("kg_point", dict(code="python.list", title="列表", subject_id=2)),
    ("quiz_progress", dict(learner="u1", level="入门", category="选择", current_no="python.Q1", answered=1, right_count=0, asked_nos="python.Q1",
                           asked_count=1, mode="free", lesson_code="", round_start_id=0, seq=1, last_correct=0, subject_id=2)),
    ("progress_answer", dict(learner="u1", point_code="python.list", question_no="python.Q1", correct=0, answer="B", at="2026-01-01", subject_id=2)),
]


def make_ws(mod):
    tmp = Path(tempfile.mkdtemp(prefix=f"kg_v4_i18n_{mod}_"))
    ws = tmp / "kg_v4"
    shutil.copytree(SRC, ws, ignore=K.COPY_IGNORE, symlinks=True)
    os.environ["DSL_NOW"] = K.DEFAULT_NOW
    return tmp, ws, K.build_sql(ws, P.closure(ws, mod))


def seed(ws, rows=()):
    db = K.reset_db(ws, SQL[ws])
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


def engine(ws, calls, extra_intent=None):
    from tools import packs
    from tools.dsl import DSLEngine
    from tools.dsl_http import DEFAULT_PACKS
    from tools.dsl_service import get_services
    from tools.mock import MockClient

    def handler(prompt, system=None):
        calls.append(prompt)
        if "判断学生这句话的意图" in prompt or "教师端助手的意图分类器" in prompt:
            return '{"intent": "explain", "keyword": "", "level": ""}' if "判断学生这句话的意图" in prompt else '{"intent": "chitchat", "student": "", "point": ""}'
        if "delivered" in prompt:
            return '{"delivered": 0}'
        return "好的，我们来看看。"

    eng = DSLEngine(MockClient(offline=True, handler=handler), workdir=Path(ws), verbose=False,
                    verbs=packs.registry(DEFAULT_PACKS, Path(ws)), verbs_root=packs.verbs_root())
    svc = get_services(Path(ws) / "services")
    svc.refresh()
    eng.services = svc
    eng.svc_module = None
    return eng


_n = [0]


def run(ws, mod, fn, **args):
    calls = []
    _n[0] += 1
    r, err = K.call(engine(ws, calls), mod, fn, args, f"c{_n[0]}")
    K.settle()
    return r, (str(err.get("code")) if isinstance(err, dict) else ("" if err in ("", None) else str(err))), calls


def first(calls, key, exclude=()):
    xs = [c for c in calls if key in c and not any(x in c for x in exclude)]
    return xs[0] if xs else ""


SQL = {}

print("一、tutor：问老师 / 总结本轮")
tmp, ws, SQL[ws] = make_ws("tutor")
try:
    seed(ws, ROUND)
    r, e, calls = run(ws, "tutor", "问老师", learner="u1", message="你好", subject="1")
    check(e == "" and str(r.get("ok")) == "1", "zh：问老师 ok=1（对照）", (r, e))
    it_zh = first(calls, "判断学生这句话的意图")
    ans_zh = first(calls, "【以下是学生相关内容】")
    check(it_zh and ans_zh, "zh：截到判意图与答一轮提示词", len(calls))

    seed(ws, ROUND + [acct("u1", "student", "ja")])
    r, e, calls = run(ws, "tutor", "问老师", learner="u1", message="你好", subject="1")
    it_ja = first(calls, "判断学生这句话的意图")
    ans_ja = first(calls, "【以下是学生相关内容】")
    check(it_ja == it_zh, "ja：判意图提示词与 zh 逐字一致（结构化调用不追加）", it_ja[:120])
    expect = ans_zh.replace(" 【以下是学生相关内容】", SP + " 【以下是学生相关内容】", 1)
    check(ans_ja == expect, "ja：答一轮只在系统提示末尾多出语言指示句，其余逐字一致",
          None if ans_ja == expect else (ans_zh[-60:], ans_ja[-60:]))
    check(SP in ans_ja and ans_ja.count(SP) == 1, "ja：语言指示句恰好出现一次", ans_ja.count(SP))

    seed(ws, ROUND + [acct("u1", "student", "zh")])
    r, e, calls = run(ws, "tutor", "问老师", learner="u1", message="你好", subject="1")
    ans_zh2 = first(calls, "【以下是学生相关内容】")
    check(ans_zh2 == ans_zh, "zh：lang=zh 与没填 lang 逐字一致", None)

    seed(ws, ROUND + [acct("u1", "student", "ja"),
                      ("subject_ai", dict(subject_id=1, persona="  全部用中文回答学生，语气亲切。 "))])
    r, e, calls = run(ws, "tutor", "问老师", learner="u1", message="你好", subject="1")
    ans_ov = first(calls, "【以下是学生相关内容】")
    check(SP not in ans_ov, "覆盖：教师设定写了明确语言要求（中文）→ 不追加", ans_ov[:120])

    seed(ws, ROUND + [acct("u1", "student", "ja"),
                      ("subject_ai", dict(subject_id=1, persona="  你是严格的老师，先讲要点再举例子。 "))])
    r, e, calls = run(ws, "tutor", "问老师", learner="u1", message="你好", subject="1")
    ans_ov2 = first(calls, "【以下是学生相关内容】")
    check(SP in ans_ov2, "覆盖：教师设定没有语言要求 → 照常追加", ans_ov2[:120])

    seed(ws, ROUND + [acct("u1", "student", "ja"),
                      ("subject_ai", dict(subject_id=1, persona="你是日语老师，耐心讲解语法。"))])
    r, e, calls = run(ws, "tutor", "问老师", learner="u1", message="你好", subject="1")
    ans_id = first(calls, "【以下是学生相关内容】")
    check(SP in ans_id, "覆盖：只提语言名的身份描述（日语老师）不算指示 → 照常追加", ans_id[:120])

    seed(ws, ROUND + [acct("u1", "student", "ja"),
                      ("subject_ai", dict(subject_id=1, persona="你是中文老师，教中文学习者日语语法。"))])
    r, e, calls = run(ws, "tutor", "问老师", learner="u1", message="你好", subject="1")
    ans_id2 = first(calls, "【以下是学生相关内容】")
    check(SP in ans_id2, "覆盖：照抄默认人设当自定义（身份描述）不算指示 → 照常追加", ans_id2[:120])

    seed(ws, ROUND + [acct("u1", "student", "ja")])
    r, e, calls = run(ws, "tutor", "问老师", learner="u1", message="你好", subject="2")
    ans_py = first(calls, "【以下是学生相关内容】")
    check(SP in ans_py and "Python 编程老师" in ans_py, "ja：Python 科目也跟随界面语言追加（不按科目特判）", ans_py[:120])

    seed(ws, ROUND)
    r, e, calls = run(ws, "tutor", "总结本轮", learner="u1", subject="1")
    check(e == "" and str(r.get("ok")) == "1", "zh：总结本轮 ok=1（对照）", (r, e))
    s_zh = calls[0]
    seed(ws, ROUND + [acct("u1", "student", "ja")])
    r, e, calls = run(ws, "tutor", "总结本轮", learner="u1", subject="1")
    check(e == "" and str(r.get("ok")) == "1", "ja：总结本轮 ok=1", (r, e))
    s_ja = calls[0]
    check(s_ja == s_zh + SP, "ja：总结本轮只在末尾多出语言指示句，其余逐字一致",
          None if s_ja == s_zh + SP else (s_zh[-50:], s_ja[-50:]))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("二、teacher_assist：问助手")
tmp, ws, SQL[ws] = make_ws("teacher_assist")
try:
    ASSIST_DATA = [
        ("kg_point", dict(code="P1", title="は和が", subject_id=1)),
        ("kg_item", dict(code="I1", name="は的用法", point_code="P1", subject_id=1)),
        ("kg_point", dict(code="python.list", title="列表", subject_id=2)),
        ("kg_item", dict(code="python.list1", name="列表切片", point_code="python.list", subject_id=2)),
    ]
    seed(ws, ASSIST_DATA)
    r, e, calls = run(ws, "teacher_assist", "问助手", current_user="t1", message="你好", subject="1")
    check(e == "" and str(r.get("ok")) == "1", "zh：问助手 ok=1（对照）", (r, e))
    a_zh = first(calls, "像同事一样和老师说话")
    check(a_zh, "zh：截到答一轮提示词", len(calls))

    seed(ws, ASSIST_DATA + [acct("t1", "teacher", "ja")])
    r, e, calls = run(ws, "teacher_assist", "问助手", current_user="t1", message="你好", subject="1")
    a_ja = first(calls, "像同事一样和老师说话")
    expect = a_zh.replace("\n\n【数据】", SP + "\n\n【数据】", 1)
    check(a_ja == expect, "ja：答一轮只在 sysp 末尾（【数据】之前）多出语言指示句，其余逐字一致",
          None if a_ja == expect else (a_zh[:80], a_ja[:80]))

    seed(ws, ASSIST_DATA + [acct("t1", "teacher", "ja"),
                            ("subject_ai", dict(subject_id=1, assist_prompt="  回答一律用中文，简洁。 "))])
    r, e, calls = run(ws, "teacher_assist", "问助手", current_user="t1", message="你好", subject="1")
    a_ov = first(calls, "像同事一样和老师说话")
    check(SP not in a_ov, "覆盖：科目助手设定写了明确语言要求（中文）→ 不追加", a_ov[:100])

    seed(ws, ASSIST_DATA + [acct("t1", "teacher", "ja")])
    r, e, calls = run(ws, "teacher_assist", "问助手", current_user="t1", message="你好", subject="2")
    a_py = first(calls, "像同事一样和老师说话")
    check(SP in a_py, "ja：Python 科目助手也跟随教师界面语言", a_py[:100])

    seed(ws, ASSIST_DATA + [acct("t1", "teacher", "ja"),
                            ("subject_ai", dict(subject_id=1, assist_prompt="你是日语学习系统里的助手。"))])
    r, e, calls = run(ws, "teacher_assist", "问助手", current_user="t1", message="你好", subject="1")
    a_id = first(calls, "像同事一样和老师说话")
    check(SP in a_id, "覆盖：助手设定只提语言名（日语学习系统）不算指示 → 照常追加", a_id[:100])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("三、report：写学情总结（给教师看，跟随教师 lang）")
tmp, ws, SQL[ws] = make_ws("report")
try:
    REP = [
        acct("s1", "student"),
        ("subject_student", dict(subject_id=1, learner="s1", assigned_by="t1", status="active", created_at="2026-01-01")),
        ("kg_point", dict(code="P1", title="一次函数")),
        ("progress_answer", dict(learner="s1", point_code="P1", question_no="q1", correct=0, at="2026-01-01")),
        ("progress_score", dict(learner="s1", point_code="P1", score=0, at="2026-01-01")),
    ]
    seed(ws, REP + [acct("t1", "teacher")])
    r, e, calls = run(ws, "report", "写学情总结", student="s1", current_user="t1")
    check(e == "" and str(r.get("ok")) == "1", "zh：写学情总结 ok=1（对照）", (r, e))
    p_zh = calls[0]
    check("中文，不超过300字" in p_zh and SP not in p_zh, "zh：总结提示词与旧版逐字一致", p_zh[:80])

    seed(ws, REP + [acct("t1", "teacher", "ja")])
    r, e, calls = run(ws, "report", "写学情总结", student="s1", current_user="t1")
    p_ja = calls[0]
    check(p_ja == p_zh + SP, "ja：只在末尾多出语言指示句，其余逐字一致（学生 lang 不影响，跟教师走）",
          None if p_ja == p_zh + SP else (p_zh[-50:], p_ja[-50:]))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
