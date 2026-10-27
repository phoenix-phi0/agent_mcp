#!/usr/bin/env python
"""kg_v4 多科目迁移（M1）：建 1 号科目「日语语法」，把现有学生登记进去、现有教师登记为协作。幂等。

用法（解释器用仓库的 .venv）：
  .venv/bin/python kg_v4/setup/migrate_subject.py [项目目录]

做的事（只动 subject_* 五张表，别的表一行不动）：
  1. 先跑 ensure_db：新表、subject_id 列（默认 1，旧行直接是 1）、三张表的唯一键重建（迁移 重建，先备份 app.db.bak-时间）
  2. subject_info 没有 id=1 就插入：jp_grammar / 日语语法 / language / 能力全开 / N5–N1 / choice,fill / public / active；
     owner = 库里第一个教师（没有教师就是 system）
  3. 全部学生（account_user.role=student）在 subject_student 里没有 (1, 学生) 的行就补 active
  4. 全部教师在 subject_teacher 里没有 (1, 教师) 的行就补 editor
重复运行不新增任何行（返回的计数全是 0）。init_data.py 新库初始化时也会调用 ensure_subject()。
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

JP_CAPS = {"vocab": 1, "dictation": 1, "lesson": 1, "levels": 1, "jp_judge": 1, "textbook_import": 1}


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
    print(ensure_db(root))
    r = ensure_subject(root / "app.db")
    print(f"多科目迁移：新建科目 {r['科目']}、新登记学生 {r['学生']}、新登记教师 {r['教师']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
