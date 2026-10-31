# -*- coding: utf-8 -*-
"""kg_v4 教师助手提示词按科目切换（K164）：约定用例用假模型、断言不了提示词，这里截下提示词逐字核对。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_assist_persona.py
    （--record：在改前代码上截下日语科目的提示词写进 GOLDEN 文件，只在建 GOLDEN 时用）

拷一份 kg_v4 到临时目录，用约定用例的运行器（cases.build_sql / reset_db / call）造数据、调函数。离线，假模型按提示词回。
  日语科目（1）：教师助手判意图、答一轮，加知识点草稿，讲义材料四处提示词与改前逐字一致（GOLDEN 是改前代码截下来的全文）
  通用科目（Python 编程）：四处提示词都不出现「日语」「语法」「JLPT」，自称本科目，讲义用【示例】
  subject_ai.assist_prompt：非空时替换答一轮开头的助手自我介绍，空时用默认；不影响别的科目
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
GOLDEN = Path(__file__).resolve().parent / "assist_persona_golden.json"
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


tmp = Path(tempfile.mkdtemp(prefix="kg_v4_assist_persona_"))
ws = tmp / "kg_v4"
shutil.copytree(SRC, ws, ignore=K.COPY_IGNORE, symlinks=True)
os.environ["DSL_NOW"] = K.DEFAULT_NOW
SQL = K.build_sql(ws, P.closure(ws, "teacher_assist"))


def subj(code, name, kind, levels):
    return ("subject_info", dict(code=code, name=name, kind=kind, caps="x", levels=levels, qtypes="choice", visibility="public",
                                 owner="t1", status="active", created_at="2026-01-01", updated_at="2026-01-01"))


SUBJECTS = [subj("jp_grammar", "日语语法", "language", "N5,N4,N3,N2,N1"), subj("python", "Python 编程", "general", "入门,基础,进阶")]
DATA = [
    ("kg_point", dict(code="P1", title="は和が", subject_id=1)),
    ("kg_item", dict(code="I1", name="は的用法", point_code="P1", subject_id=1)),
    ("kg_point", dict(code="python.list", title="列表", subject_id=2)),
    ("kg_item", dict(code="python.list1", name="列表切片", point_code="python.list", subject_id=2)),
]
BANNED = ("日语", "语法", "JLPT")
# 四处提示词的识别标记（改前改后都在）
K_INTENT = "教师端助手的意图分类器"
K_ANSWER = "像同事一样和老师说话，只读。"
K_KG = "任务：往图谱里加知识点、条目、前置边。"
K_MAT = "请按下面的要求写材料。"


def seed(rows=()):
    db = K.reset_db(ws, SQL)
    con = sqlite3.connect(db)
    try:
        for table, kv in list(SUBJECTS) + list(DATA) + list(rows):
            con.execute(f"INSERT INTO {table}({', '.join(kv)}) VALUES({', '.join('?' * len(kv))})", list(kv.values()))
        con.commit()
    finally:
        con.close()
    return db


def engine(calls):
    from tools import packs
    from tools.dsl import DSLEngine
    from tools.dsl_http import DEFAULT_PACKS
    from tools.dsl_service import get_services
    from tools.mock import MockClient

    def handler(prompt, system=None):
        calls.append(prompt)
        if K_INTENT in prompt:
            return '{"intent": "chitchat", "student": "", "point": ""}'
        if K_KG in prompt:
            pre = "python." if "python." in prompt else ""
            return json.dumps({"title": "加一个点", "points": [{"code": pre + "newp", "title": "新知识点"}], "items": [], "edges": []},
                              ensure_ascii=False)
        if K_MAT in prompt:
            return "【要点】一\n【小练习】1. 题"
        return "好的，我们来看看。"

    eng = DSLEngine(MockClient(offline=True, handler=handler), workdir=Path(ws), verbose=False,
                    verbs=packs.registry(DEFAULT_PACKS, Path(ws)), verbs_root=packs.verbs_root())
    svc = get_services(Path(ws) / "services")
    svc.refresh()
    eng.services = svc
    eng.svc_module = None
    return eng


_n = [0]


def run(mod, fn, **args):
    """→ (结果, 报错码或空, 提示词列表)"""
    calls = []
    _n[0] += 1
    r, err = K.call(engine(calls), mod, fn, args, f"c{_n[0]}")
    K.settle()
    return r, (str(err.get("code")) if isinstance(err, dict) else ("" if err in ("", None) else str(err))), calls


def first(calls, key):
    xs = [c for c in calls if key in c]
    return xs[0] if xs else ""


def prompts(subject):
    """一个科目的四处提示词：{intent, answer, kg, handout}，外加各调用的结果"""
    out, res = {}, {}
    r, e, calls = run("teacher_assist", "问助手", current_user="t1", message="你好", subject=subject)
    res["问助手"] = (r, e)
    out["intent"] = first(calls, K_INTENT)
    out["answer"] = first(calls, K_ANSWER)
    r, e, calls = run("assist_draft", "生成草稿", current_user="t1", kind="kg_add", message="加一个新知识点", subject=subject)
    res["生成草稿"] = (r, e)
    out["kg"] = first(calls, K_KG)
    pt = "は和が" if subject == "1" else "列表"
    r, e, calls = run("assist_material", "生成材料", current_user="t1", kind="handout", message="写一份讲义", point=pt, subject=subject)
    res["生成材料"] = (r, e)
    out["handout"] = first(calls, K_MAT)
    return out, res


try:
    seed()
    jp, res = prompts("1")
    if RECORD:
        miss = [k for k, v in jp.items() if not v]
        if miss:
            print("截不到提示词：", miss, res)
            sys.exit(1)
        GOLDEN.write_text(json.dumps(jp, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"已写 GOLDEN：{GOLDEN}（{', '.join(f'{k} {len(v)} 字' for k, v in jp.items())}）")
        sys.exit(0)

    gold = json.loads(GOLDEN.read_text(encoding="utf-8"))
    print("一、日语科目：四处提示词与改前逐字一致（GOLDEN 全文）")
    for name, (r, e) in res.items():
        check(e == "" and str(r.get("ok")) == "1", f"{name} ok=1", (r, e))
    for k, label in (("intent", "教师助手判意图"), ("answer", "教师助手答一轮"), ("kg", "加知识点草稿"), ("handout", "讲义材料")):
        same = jp.get(k) == gold[k]
        diff = None
        if not same:
            a, b = jp.get(k, ""), gold[k]
            i = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b)))
            diff = f"第 {i} 字起：改后「{a[max(0, i - 20):i + 40]}」 / 改前「{b[max(0, i - 20):i + 40]}」"
        check(same, f"{label}提示词与改前逐字一致（{len(gold[k])} 字）", diff)

    print("二、Python 科目：不出现日语/语法/JLPT，自称本科目")
    seed()
    py, res = prompts("2")
    for name, (r, e) in res.items():
        check(e == "" and str(r.get("ok")) == "1", f"{name} ok=1", (r, e))
    for k, label in (("intent", "判意图"), ("answer", "答一轮"), ("kg", "加知识点草稿"), ("handout", "讲义材料")):
        hit = [b for b in BANNED if b in py.get(k, "")]
        check(py.get(k) and not hit, f"{label}提示词没有日语/语法/JLPT", hit or py.get(k, "")[:200])
    check(py["intent"].startswith("你是Python 编程学习系统里教师端助手的意图分类器。"), "判意图：Python 编程学习系统", py["intent"][:60])
    check("问某个知识点或条目全班的掌握情况" in py["intent"] and "说这个知识点、这个点时" in py["intent"], "判意图：知识点或条目 / 这个知识点", py["intent"])
    check(py["answer"].startswith("你是Python 编程学习系统教师端的教学助手，像同事一样和老师说话，只读。"), "答一轮：Python 编程学习系统的教学助手", py["answer"][:60])
    check("编号前缀（本科目的编号必须以它开头）：python." in py["kg"], "加知识点草稿：编号前缀说明不提日语", py["kg"][:300])
    check("【示例】" in py["handout"] and "【例句】" not in py["handout"], "讲义：【示例】代替【例句】", py["handout"][:300])

    print("三、subject_ai.assist_prompt 可选覆盖")
    seed([("subject_ai", dict(subject_id=2, assist_prompt="  你是严谨又耐心的 Python 助教。 "))])
    r, e, calls = run("teacher_assist", "问助手", current_user="t1", message="你好", subject="2")
    a = first(calls, K_ANSWER)
    check(e == "" and a.startswith("你是严谨又耐心的 Python 助教，像同事一样和老师说话，只读。回答规则：①"), "答一轮用自定义开头（去首尾空白和句末句号）", a[:80])
    r, e, calls = run("teacher_assist", "问助手", current_user="t1", message="你好", subject="1")
    check(first(calls, K_ANSWER) == gold["answer"], "Python 的覆盖不影响日语科目", first(calls, K_ANSWER)[:80])
    seed([("subject_ai", dict(subject_id=2, assist_prompt="   "))])
    r, e, calls = run("teacher_assist", "问助手", current_user="t1", message="你好", subject="2")
    check(first(calls, K_ANSWER) == py["answer"], "assist_prompt 只有空白时用默认", first(calls, K_ANSWER)[:80])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
