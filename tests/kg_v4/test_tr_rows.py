# -*- coding: utf-8 -*-
"""kg_v4 teacher_rules 列表行的科目列与 can_edit（K90b）：约定用例的「得」只能比返回字典的顶层键，
数组行里的值核对不了，这里补上。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_tr_rows.py

拷一份 kg_v4 到临时目录，用约定用例的运行器（cases.seed_case / make_engine / call）造数据、调函数，
再逐行核对 note_subject_label / note_subject_scope / can_edit（传达同理）。离线，不调模型。
  负责人 t1（科目 2 的 owner）、协作教师 t2（科目 2 的 editor）、单人模式（不传 auth_mode）三种身份；
  设定页的保存、启停、删除返回的刷新表也要按登录的人算（协作教师看到「全部科目」的行 can_edit=0）。
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


SEED = """
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=2 teacher=t2 role=editor created_at=2026-01-01
  先 数据 teacher_rules_setting kind=memory content=A enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00 subject_id=0
  先 数据 teacher_rules_setting kind=memory content=B enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00 subject_id=2
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00 subject_id=0
  先 数据 teacher_rules_relay urgency=normal must_info=Y rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00 subject_id=2
"""
ON1 = "learner=t1 current_role=teacher auth_mode=on subject=2"
ON2 = "learner=t2 current_role=teacher auth_mode=on subject=2"
# (名, 调用, 取哪张表, 期望 {id: (label, scope, can_edit)})
NOTE = ("note_id", "note_subject_label", "note_subject_scope")
RELAY = ("relay_id", "relay_subject_label", "relay_subject_scope")
OWNER = {1: ("全部科目", "全部科目", 1), 2: ("数学", "当前科目", 1)}
EDITOR = {1: ("全部科目", "全部科目", 0), 2: ("数学", "当前科目", 1)}
# 在 SEED 之外多造一行科目 1 的设定，核对列表不带出别的科目
EXTRA = {"设定列表 只看本科目和全部科目（科目 1 的不出现，共 2 行）":
         "  先 数据 teacher_rules_setting kind=memory content=C enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00 subject_id=1\n"}
SCENES = [
    ("设定列表 负责人", f"设定列表 {ON1}", None, NOTE, OWNER),
    ("设定列表 协作教师", f"设定列表 {ON2}", None, NOTE, EDITOR),
    ("设定列表 单人模式", "设定列表 subject=2", None, NOTE, OWNER),
    ("设定列表 只看本科目和全部科目（科目 1 的不出现，共 2 行）", "设定列表 subject=2", None, NOTE, OWNER),
    ("传达列表 负责人", f"传达列表 {ON1}", None, RELAY, OWNER),
    ("传达列表 协作教师", f"传达列表 {ON2}", None, RELAY, EDITOR),
    ("传达列表 单人模式", "传达列表 subject=2", None, RELAY, OWNER),
    ("设定首页页面 协作教师 class_notes", f"设定首页页面 {ON2}", "class_notes", NOTE, EDITOR),
    ("设定首页页面 协作教师 class_relays", f"设定首页页面 {ON2}", "class_relays", RELAY, EDITOR),
    ("保存设定页面 协作教师 刷新表", "保存设定页面 note_id=2 note_kind=记忆 note_content=B2 current_user=t2 current_role=teacher auth_mode=on subject=2",
     "class_notes", NOTE, EDITOR),
    ("设置设定启用页面 协作教师 刷新表", f"设置设定启用页面 note_id=2 enabled=0 {ON2}", "class_notes", NOTE, EDITOR),
    ("删除设定页面 协作教师 刷新表", f"删除设定页面 note_id=2 {ON2}", "class_notes", NOTE, {1: EDITOR[1]}),
    ("保存传达页面 协作教师 刷新表", "保存传达页面 relay_id=2 relay_point=Y2 current_user=t2 current_role=teacher auth_mode=on subject=2",
     "class_relays", RELAY, EDITOR),
    ("设置传达启用页面 协作教师 刷新表", f"设置传达启用页面 relay_id=2 enabled=0 {ON2}", "class_relays", RELAY, EDITOR),
    ("删除传达页面 协作教师 刷新表", f"删除传达页面 relay_id=2 {ON2}", "class_relays", RELAY, {1: EDITOR[1]}),
]


def rows_of(r, key):
    v = r.get(key) if (key and isinstance(r, dict)) else r
    if isinstance(v, dict) and "items" in v:
        v = v["items"]
    return v if isinstance(v, list) else None


tmp = Path(tempfile.mkdtemp(prefix="kg_v4_tr_rows_"))
ws = tmp / "kg_v4"
shutil.copytree(SRC, ws, ignore=K.COPY_IGNORE, symlinks=True)
os.environ.setdefault("DSL_NOW", K.DEFAULT_NOW)
try:
    base = (ws / "contracts" / "teacher_rules.md").read_text(encoding="utf-8")
    head = base.split("\n## 用例", 1)[0]
    text = head + "\n## 用例\n" + "".join(f"用例 场景{i}{SEED}{EXTRA.get(n, '')}  调用 {call}\n  得 有返回\n\n" for i, (n, call, *_r) in enumerate(SCENES))
    c, probs = C.parse(text)
    check(not probs, "场景能按约定用例语法解析", probs[:3])
    sql = K.build_sql(ws, P.closure(ws, "teacher_rules"))
    for (name, _, key, (idk, labk, scok), want), u in zip(SCENES, c["用例"]):
        why = K.seed_case(ws, sql, "teacher_rules", u)
        if why:
            check(False, name, f"造数据失败：{why}")
            continue
        eng = K.make_engine(ws)
        r, err = K.call(eng, "teacher_rules", u["调用"]["目标"], u["调用"]["参数"], "c")
        K.settle()
        rows = rows_of(r, key) if err in ("", None) else None
        if rows is None:
            check(False, name, f"报错 {err} 或返回不是表：{r!r}"[:400])
            continue
        got = {int(x[idk]): (x.get(labk), x.get(scok), int(x.get("can_edit", -1))) for x in rows}
        check(got == want, name, f"期望 {want}，实际 {got}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
