# -*- coding: utf-8 -*-
"""K182：把译文 tsv（tbl、row_key、field、text 四列，首行表头与 # 注释跳过）导入 subject_content_translation。
默认只预检不写库，--apply 才写。

    .venv/bin/python kg_v4/scripts/import_content_ja.py --db 路径 --dir 译文目录 [--apply]

预检：4 列、tbl/field 白名单、row_key 在原表存在、quiz options 译文按 ^ 拆开的个数与原文一致、
text 无制表符、换行必须写成字面 \\n（导入时转真实换行）。
以 # text-encoding: json-string 开头的文件使用 JSON 字符串转义，保留代码中的字面反斜线。
写入：显式事务逐行 upsert（ON CONFLICT 更新 text/updated_at），重复导入幂等；出错整批回滚。
"""
import datetime
import json
import pathlib
import sqlite3
import sys

KEY = {"kg_point": ("code", {"title"}), "kg_item": ("code", {"name"}),
       "quiz_question": ("question_no", {"stem", "options", "explain"}),
       "subject_info": ("code", {"name", "intro"}),
       "lesson_text": ("code", {"title", "summary", "explain", "orig_title"}),
       "lesson_series": ("code", {"name", "intro"})}
LANG = "ja"


def main():
    a = sys.argv[1:]
    db = pathlib.Path(a[a.index("--db") + 1])
    d = pathlib.Path(a[a.index("--dir") + 1])
    do_apply = "--apply" in a
    rows, errs = [], []
    for f in sorted(d.glob("*.tsv")):
        lines = f.read_text(encoding="utf-8").splitlines()
        json_encoding = bool(lines and lines[0] == "# text-encoding: json-string")
        for ln, line in enumerate(lines, 1):
            if not line or line.startswith("#") or line == "tbl\trow_key\tfield\ttext":
                continue
            p = line.split("\t")
            if len(p) != 4:
                errs.append(f"{f.name}:{ln}: 应为 4 列，实际 {len(p)}")
                continue
            tbl, rk, fd, text = p
            if tbl not in KEY:
                errs.append(f"{f.name}:{ln}: 未知表 {tbl}")
                continue
            if fd not in KEY[tbl][1]:
                errs.append(f"{f.name}:{ln}: {tbl} 不收字段 {fd}")
                continue
            if not text.strip():
                errs.append(f"{f.name}:{ln}: 译文为空")
                continue
            if "\t" in text:
                errs.append(f"{f.name}:{ln}: text 含制表符")
                continue
            if "\n" in text.replace("\\n", ""):
                errs.append(f"{f.name}:{ln}: text 有真实换行（换行应写成字面 \\n）")
                continue
            if json_encoding:
                try:
                    text = json.loads('"' + text + '"')
                except ValueError:
                    errs.append(f"{f.name}:{ln}: JSON 转义不合法")
                    continue
            else:
                text = text.replace("\\n", "\n")
            rows.append((f.name, ln, tbl, rk, fd, text))
    con = sqlite3.connect(str(db), isolation_level=None)
    try:
        for fn, ln, tbl, rk, fd, text in rows:
            if not con.execute(f"SELECT 1 FROM {tbl} WHERE {KEY[tbl][0]}=?", (rk,)).fetchone():
                errs.append(f"{fn}:{ln}: row_key 不存在：{tbl}/{rk}")
        for fn, ln, tbl, rk, fd, text in rows:
            if tbl == "quiz_question" and fd == "options":
                o = con.execute("SELECT options FROM quiz_question WHERE question_no=?", (rk,)).fetchone()
                if o and len(o[0].split("^")) != len(text.split("^")):
                    errs.append(f"{fn}:{ln}: options 个数不一致：{rk} 原{len(o[0].split('^'))} 译{len(text.split('^'))}")
        if errs:
            print(f"预检未通过（{len(errs)} 条），未写库：")
            for e in errs[:40]:
                print(" -", e)
            sys.exit(1)
        print(f"预检通过：{len(rows)} 行")
        if not do_apply:
            print("（预检模式，未写库；加 --apply 写入）")
            return
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute("BEGIN")
        for _, _, tbl, rk, fd, text in rows:
            con.execute(
                "INSERT INTO subject_content_translation(tbl,row_key,field,lang,text,updated_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(tbl,row_key,field,lang) DO UPDATE SET text=excluded.text, updated_at=excluded.updated_at",
                (tbl, rk, fd, LANG, text, now))
        con.execute("COMMIT")
        n = con.execute("SELECT COUNT(*) FROM subject_content_translation WHERE lang=?", (LANG,)).fetchone()[0]
        print(f"已写入：subject_content_translation(lang=ja) 现 {n} 行（{db}）")
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        con.close()


main()
