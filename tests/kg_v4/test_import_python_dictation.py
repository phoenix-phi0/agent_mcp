# -*- coding: utf-8 -*-
"""K192：Python 默写题库导入脚本 kg_v4/scripts/import_python_dictation.py。

在临时目录里用真实实体建库（gen.project.ensure_db），造日语 1 号、Python 2 号科目和 34 个知识点，
逐条验：dry-run 不写、apply 136 题、再导幂等且 id 不变、改内容只更新不换 id、文件少题不删、
坏文件（缺日文、错知识点、重复 id）零写入、写库中途出错整批回滚、别的科目和学习记录不动、
--enable-caps 合并键且没题时拒绝。

    .venv/bin/python tests/kg_v4/test_import_python_dictation.py
"""
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "kg_v4" / "scripts" / "import_python_dictation.py"
BANK = ROOT / "content" / "python_v1" / "dictation" / "questions.json"
PY = sys.executable

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}  {detail}")


def run(db, *extra):
    r = subprocess.run([PY, str(SCRIPT), "--db", str(db), "--subject", "python", *extra],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def count(db, sql, args=()):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, args).fetchone()[0]
    finally:
        con.close()


def main():
    from gen.project import ensure_db
    tmp = Path(tempfile.mkdtemp(prefix="k192_imp_"))
    try:
        proj = tmp / "kg_v4"
        shutil.copytree(ROOT / "kg_v4", proj, ignore=shutil.ignore_patterns("app.db*", "web", "data"))
        ensure_db(proj)
        db = proj / "app.db"
        bank = json.loads(BANK.read_text(encoding="utf-8"))
        points = sorted({q["point_code"] for q in bank["questions"]})
        con = sqlite3.connect(db)
        now = "2026-01-01 00:00:00"
        for code, kind, caps in (("jp_grammar", "language", '{"vocab":1,"dictation":1}'),
                                 ("python", "general", '{"kg":1,"quiz":1,"progress":1,"tutor":1}')):
            con.execute("INSERT INTO subject_info (code, name, intro, kind, caps, levels, qtypes, visibility, owner,"
                        " status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (code, code, "", kind, caps, "", "choice", "public", "t1", "active", now, now))
        for pc in points:
            con.execute("INSERT INTO kg_point (code, title, subject_id) VALUES (?,?,2)", (pc, pc))
        con.execute("INSERT INTO kg_point (code, title, subject_id) VALUES ('python.alien','x',1)")
        # 别的科目已有一道同 code 的题、和一条 Python 作答历史：导入不能动它们
        con.execute("INSERT INTO dictation_question (subject_id, code, point_code, kind, level, prompt_zh, prompt_ja,"
                    " answer, accepted_json, explain_zh, explain_ja, enabled) VALUES"
                    " (1,'python.dict.001','x','term','入门','别科','別','a','[\"a\"]','e','e',1)")
        con.execute("INSERT INTO dictation_question_attempt (learner, subject_id, question_id, direction, answer,"
                    " correct, hinted, at) VALUES ('me',2,2,'term','x',0,0,?)", (now,))
        con.commit()
        con.close()

        print("1. 预检（默认不写）")
        rc, out = run(db, "--file", str(BANK))
        check("dry-run 退出 0", rc == 0, out)
        check("dry-run 报新增 136", "新增 136" in out, out)
        check("知识点覆盖 34/34", "34/34" in out, out)
        check("dry-run 没写库", count(db, "SELECT COUNT(*) FROM dictation_question WHERE subject_id=2") == 0)

        print("2. apply")
        rc, out = run(db, "--file", str(BANK), "--apply")
        check("apply 退出 0", rc == 0, out)
        n = count(db, "SELECT COUNT(*) FROM dictation_question WHERE subject_id=2")
        check("Python 136 题", n == 136, n)
        check("术语 68、代码 68", count(db, "SELECT COUNT(*) FROM dictation_question WHERE subject_id=2 AND kind='term'") == 68
              and count(db, "SELECT COUNT(*) FROM dictation_question WHERE subject_id=2 AND kind='output'") == 68)
        check("34 个知识点", count(db, "SELECT COUNT(DISTINCT point_code) FROM dictation_question WHERE subject_id=2") == 34)
        check("中日字段都不空", count(db, "SELECT COUNT(*) FROM dictation_question WHERE subject_id=2 AND"
                                    " (trim(prompt_ja)='' OR trim(explain_ja)='' OR trim(prompt_zh)='' OR trim(explain_zh)='')") == 0)
        q3 = [q for q in bank["questions"] if q["id"] == "python.dict.004"][0]
        con = sqlite3.connect(db)
        row = con.execute("SELECT answer, accepted_json FROM dictation_question WHERE subject_id=2 AND code='python.dict.004'").fetchone()
        ids1 = dict(con.execute("SELECT code, id FROM dictation_question WHERE subject_id=2"))
        con.close()
        check("代码题答案逐字节原样（含末尾换行）", row[0] == q3["answer"] and json.loads(row[1]) == q3["accepted"], row)
        check("别的科目的同 code 题没动", count(db, "SELECT COUNT(*) FROM dictation_question WHERE subject_id=1 AND prompt_zh='别科'") == 1)
        check("作答历史没动", count(db, "SELECT COUNT(*) FROM dictation_question_attempt") == 1)
        check("没写译文表", count(db, "SELECT COUNT(*) FROM subject_content_translation") == 0)

        print("3. 再导一次：幂等")
        rc, out = run(db, "--file", str(BANK), "--apply")
        check("再导新增 0 更新 0 不变 136", "新增 0、更新 0、不变 136" in out, out)
        con = sqlite3.connect(db)
        ids2 = dict(con.execute("SELECT code, id FROM dictation_question WHERE subject_id=2"))
        con.close()
        check("id 不变", ids1 == ids2)

        print("4. 改内容、少题：只更新、不删、id 不变")
        b2 = json.loads(json.dumps(bank))
        b2["questions"][0]["explain_zh"] += "（改）"
        removed = b2["questions"].pop()["id"]
        f2 = tmp / "b2.json"
        f2.write_text(json.dumps(b2, ensure_ascii=False), encoding="utf-8")
        rc, out = run(db, "--file", str(f2), "--apply")
        check("更新 1、保留 1", "更新 1" in out and "保留不删）1" in out, out)
        con = sqlite3.connect(db)
        ids3 = dict(con.execute("SELECT code, id FROM dictation_question WHERE subject_id=2"))
        con.close()
        check("缺席题还在、id 全不变", ids3 == ids1 and removed in ids3)

        print("5. 坏文件零写入")
        before = count(db, "SELECT total_changes()")
        snap = count(db, "SELECT group_concat(id||explain_zh, '|') FROM dictation_question")
        for name, mut in (("缺日文", lambda b: b["questions"][3].__setitem__("prompt_ja", "")),
                          ("别科目知识点", lambda b: b["questions"][5].__setitem__("point_code", "python.alien")),
                          ("重复 id", lambda b: b["questions"][7].__setitem__("id", b["questions"][6]["id"])),
                          ("答案不在 accepted", lambda b: b["questions"][9].__setitem__("accepted", ["zzz"])),
                          ("等级不对", lambda b: b["questions"][10].__setitem__("difficulty", "N5"))):
            b3 = json.loads(json.dumps(bank))
            b3["questions"][0]["explain_zh"] += "（坏批）"
            mut(b3)
            f3 = tmp / "b3.json"
            f3.write_text(json.dumps(b3, ensure_ascii=False), encoding="utf-8")
            rc, out = run(db, "--file", str(f3), "--apply")
            check(f"{name}：退出 1 且拒收", rc == 1 and "零写入" in out, out[-300:])
        check("坏文件后内容不变", count(db, "SELECT group_concat(id||explain_zh, '|') FROM dictation_question") == snap)
        del before

        print("6. 写库中途出错整批回滚")
        con = sqlite3.connect(db)
        con.execute("CREATE TRIGGER k192_boom BEFORE UPDATE ON dictation_question WHEN NEW.code='python.dict.100'"
                    " BEGIN SELECT RAISE(ABORT, 'k192 注入'); END")
        con.commit()
        con.close()
        b4 = json.loads(json.dumps(bank))
        for q in b4["questions"]:
            q["explain_ja"] += "（全改）"
        f4 = tmp / "b4.json"
        f4.write_text(json.dumps(b4, ensure_ascii=False), encoding="utf-8")
        rc, out = run(db, "--file", str(f4), "--apply")
        check("注入失败退出 1、提示回滚", rc == 1 and "整批回滚" in out, out[-300:])
        check("一条也没改", count(db, "SELECT COUNT(*) FROM dictation_question WHERE explain_ja LIKE '%（全改）'") == 0)
        con = sqlite3.connect(db)
        con.execute("DROP TRIGGER k192_boom")
        con.commit()
        con.close()

        print("7. 打开 caps")
        rc, out = run(db, "--enable-caps")
        check("预检不写", rc == 0 and count(db, "SELECT caps FROM subject_info WHERE id=2") == '{"kg":1,"quiz":1,"progress":1,"tutor":1}', out)
        rc, out = run(db, "--enable-caps", "--apply")
        caps = json.loads(count(db, "SELECT caps FROM subject_info WHERE id=2"))
        check("caps 合并 dictation=1、其余键保留", rc == 0 and caps == {"kg": 1, "quiz": 1, "progress": 1, "tutor": 1, "dictation": 1}, caps)
        rc, out = run(db, "--enable-caps", "--apply")
        check("再开一次不改", rc == 0 and "不用改" in out, out)
        check("1 号科目 caps 没动", count(db, "SELECT caps FROM subject_info WHERE id=1") == '{"vocab":1,"dictation":1}')
        con = sqlite3.connect(db)
        con.execute("DELETE FROM dictation_question WHERE subject_id=2")
        con.execute("UPDATE subject_info SET caps='{\"kg\":1}' WHERE id=2")
        con.commit()
        con.close()
        rc, out = run(db, "--enable-caps", "--apply")
        check("没题时拒绝打开", rc == 1 and count(db, "SELECT caps FROM subject_info WHERE id=2") == '{"kg":1}', out)

        print("8. 参数")
        r = subprocess.run([PY, str(SCRIPT), "--subject", "python", "--file", str(BANK)], capture_output=True, text=True)
        check("不给 --db 拒绝", r.returncode != 0)
        rc, out = subprocess.run([PY, str(SCRIPT), "--db", str(db), "--subject", "jp_grammar", "--file", str(BANK)],
                                 capture_output=True, text=True).returncode, ""
        check("科目不是 python 拒绝", rc == 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"通过 {ok}、失败 {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
