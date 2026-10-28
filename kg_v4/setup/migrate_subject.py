#!/usr/bin/env python
"""kg_v4 多科目迁移（M1）：建 1 号科目「日语语法」，把现有学生登记进去、现有教师登记为协作。幂等。

用法（解释器用仓库的 .venv）：
  .venv/bin/python kg_v4/setup/migrate_subject.py [项目目录]

做的事（只动 subject_* 五张表，别的表一行不动）：
  1. 先跑 ensure_db：新表、subject_id 列（默认 1，旧行直接是 1）、三张表的唯一键重建（迁移 重建，先备份 app.db.bak-时间）
  2. subject_info 没有 id=1 就插入：jp_grammar / 日语语法 / language / 能力全开 / N5–N1 / choice,fill / public / active；
     owner = 库里第一个教师（没有教师就是 system）
  3. 全部学生（account_user.role=student）在 subject_student 里没有 (1, 学生) 的行就补 active
     （K79 起学生范围统一走 subject.列科目学生，没有「1 号=全部学生」的特例，所以已有学生必须登记；
     之后新建的学生由 account.建学生 自动登记；已撤销的行不动）
  4. 全部教师在 subject_teacher 里没有 (1, 教师) 的行就补 editor
  5. 旧数据 subject_id 显式回填 1（K79 加）：
     - 默认值本来就是 1 的表（kg/vocab/lesson/progress/quiz/dictation/tutor/report/teacher_assist/textbook_import 各表，
       含 dictation_progress、quiz_progress、progress_mastery 等），把 subject_id 为 0 或空的行显式改成 1
     - teacher_rules_setting / teacher_rules_relay 的 subject_id 默认值是 0（0=全部科目）：ADD COLUMN 之后旧行会变成 0，
       不改的话日语既有设定会混进别的科目的提示词。所以「这是第一次迁移」时把这两张表的 0 全改成 1。
       「第一次」的判据（任一成立）：迁移前这两张表还没有 subject_id 列；迁移前 subject_info 里还没有 1 号科目。
       判据成立时先在 setup_meta（本脚本建：key 文本主键, value 文本）写 rules_subject_fix=pending 持久标记，
       0→1 回填与标记改 done 在同一事务里提交；所以回填中途失败后重跑，标记仍是 pending，会补修；
       成功后标记是 done，重跑不再动（新建的「全部科目」设定存 0，是合法的）。没有标记的库（已迁移完的旧库）也不动
重复运行不新增任何行（返回的计数全是 0）。init_data.py 新库初始化时也会调用 ensure_subject()。
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

JP_CAPS = {"vocab": 1, "dictation": 1, "lesson": 1, "levels": 1, "jp_judge": 1, "textbook_import": 1}


# subject_id 的含义不是「所属科目」或允许为 0 的表，回填时不碰
SKIP_BACKFILL = {"subject_info", "subject_teacher", "subject_student", "subject_pref", "subject_ai",
                 "teacher_rules_setting", "teacher_rules_relay"}
RULES_TABLES = ("teacher_rules_setting", "teacher_rules_relay")
META_KEY = "rules_subject_fix"      # setup_meta 里的持久标记：pending=待修规则表的 0→1，done=已修


def pre_state(db):
    """ensure_db 之前调用：返回 {规则表缺列: bool, 无1号科目: bool}，决定要不要把 teacher_rules 的 0 改成 1。
    判据成立且 setup_meta 里还没有标记时，写 pending 标记（持久，回填成功才改 done）。"""
    con = sqlite3.connect(str(db))
    try:
        def cols(t):
            return [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
        missing = any(cols(t) and "subject_id" not in cols(t) for t in RULES_TABLES)
        has_info = bool(cols("subject_info"))
        no_one = (not has_info) or not con.execute("SELECT 1 FROM subject_info WHERE id = 1").fetchone()
        if missing or no_one:
            con.execute("CREATE TABLE IF NOT EXISTS setup_meta (key TEXT PRIMARY KEY, value TEXT)")
            con.execute("INSERT OR IGNORE INTO setup_meta (key, value) VALUES (?, 'pending')", (META_KEY,))
            con.commit()
        return {"规则表缺列": missing, "无1号科目": no_one}
    finally:
        con.close()


def rules_fix_pending(db):
    """setup_meta 里 rules_subject_fix 是 pending 才返回 True（没有表、没有标记、done 都是 False）。"""
    con = sqlite3.connect(str(db))
    try:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='setup_meta'").fetchone():
            return False
        r = con.execute("SELECT value FROM setup_meta WHERE key = ?", (META_KEY,)).fetchone()
        return bool(r) and r[0] == "pending"
    finally:
        con.close()


def backfill_subject_id(db, fix_rules):
    """旧行 subject_id 显式回填 1。返回 {表: 改的行数}（只列改了的）。幂等。
    fix_rules 为真时，teacher_rules_setting / teacher_rules_relay 里 subject_id=0 的行也改成 1（仅第一次迁移）。"""
    con = sqlite3.connect(str(db))
    out = {}
    try:
        con.execute("BEGIN IMMEDIATE")
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for t in tables:
            if not any(r[1] == "subject_id" for r in con.execute(f'PRAGMA table_info("{t}")')):
                continue
            if t in RULES_TABLES:
                if not fix_rules:
                    continue
            elif t in SKIP_BACKFILL:
                continue
            n = con.execute(f'UPDATE "{t}" SET subject_id = 1 WHERE subject_id IS NULL OR subject_id = 0').rowcount
            if n:
                out[t] = n
        if fix_rules:
            con.execute("UPDATE setup_meta SET value = 'done' WHERE key = ?", (META_KEY,))
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
    return out


def ensure_subject(db):
    """db：app.db 路径。返回 {科目: 新建0/1, 学生: 新登记数, 教师: 新登记数}。表必须已建好（ensure_db 之后）。"""
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    con = sqlite3.connect(str(db))
    out = {"科目": 0, "学生": 0, "教师": 0}
    try:
        con.execute("BEGIN IMMEDIATE")
        if not con.execute("SELECT 1 FROM subject_info WHERE id = 1").fetchone():
            if con.execute("SELECT 1 FROM subject_info WHERE code = 'jp_grammar'").fetchone():
                raise SystemExit("subject_info 里已有 code=jp_grammar 但 id 不是 1，不自动处理，请人工核对")
            t = con.execute("SELECT username FROM account_user WHERE role = 'teacher' ORDER BY id LIMIT 1").fetchone()
            con.execute("INSERT INTO subject_info (id, code, name, intro, kind, caps, levels, qtypes, visibility, owner, "
                        "status, created_at, updated_at) VALUES (1, 'jp_grammar', '日语语法', '', 'language', ?, "
                        "'N5,N4,N3,N2,N1', 'choice,fill', 'public', ?, 'active', ?, ?)",
                        (json.dumps(JP_CAPS, separators=(",", ":")), t[0] if t else "system", now, now))
            out["科目"] = 1
        for (u,) in con.execute("SELECT username FROM account_user WHERE role = 'student' ORDER BY id").fetchall():
            c = con.execute("INSERT OR IGNORE INTO subject_student (subject_id, learner, assigned_by, status, created_at) "
                            "VALUES (1, ?, '', 'active', ?)", (u, now))
            out["学生"] += c.rowcount
        for (u,) in con.execute("SELECT username FROM account_user WHERE role = 'teacher' ORDER BY id").fetchall():
            c = con.execute("INSERT OR IGNORE INTO subject_teacher (subject_id, teacher, role, created_at) "
                            "VALUES (1, ?, 'editor', ?)", (u, now))
            out["教师"] += c.rowcount
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(argv[0] if argv else Path(__file__).resolve().parents[1]).resolve()
    if not (root / "entities").is_dir():
        print(f"不是项目目录：{root}")
        return 2
    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    from gen.project import ensure_db
    db = root / "app.db"
    if db.is_file():
        pre_state(db)       # 旧库：判据成立就写 pending 标记
    print(ensure_db(root))
    r = ensure_subject(db)
    print(f"多科目迁移：新建科目 {r['科目']}、新登记学生 {r['学生']}、新登记教师 {r['教师']}")
    fix_rules = rules_fix_pending(db)       # 看持久标记，不看 pre：上次回填中途失败时 pre 已全是 False
    bf = backfill_subject_id(db, fix_rules)
    print(f"subject_id 回填 1：{bf if bf else '没有需要改的行'}（teacher_rules 的 0→1：{'做' if fix_rules else '不做（不是第一次迁移）'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
