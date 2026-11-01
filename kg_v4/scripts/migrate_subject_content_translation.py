# -*- coding: utf-8 -*-
"""K182：建 subject_content_translation 表（只加不改）。幂等，可重复执行。

    .venv/bin/python kg_v4/scripts/migrate_subject_content_translation.py [--db 路径]

默认对项目库 kg_v4/app.db；正式库在 deploy 后、导译文前对 kg_v4_data/app.db 执行。
显式事务，失败回滚。
"""
import pathlib
import sqlite3
import sys

HERE = pathlib.Path(__file__).resolve().parent
DB = HERE.parent / "app.db"
if "--db" in sys.argv:
    DB = pathlib.Path(sys.argv[sys.argv.index("--db") + 1])

con = sqlite3.connect(str(DB), isolation_level=None)
try:
    con.execute("BEGIN")
    con.execute("""CREATE TABLE IF NOT EXISTS subject_content_translation (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tbl TEXT NOT NULL,
  row_key TEXT NOT NULL,
  field TEXT NOT NULL,
  lang TEXT NOT NULL,
  text TEXT NOT NULL,
  updated_at TEXT NOT NULL
)""")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_subject_content_translation ON subject_content_translation(tbl, row_key, field, lang)")
    con.execute("COMMIT")
    n = con.execute("SELECT COUNT(*) FROM subject_content_translation").fetchone()[0]
    print(f"ok: subject_content_translation 就绪，当前 {n} 行（{DB}）")
except Exception:
    con.execute("ROLLBACK")
    raise
finally:
    con.close()
