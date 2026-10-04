# -*- coding: utf-8 -*-
"""把 item 表整张倒出来，顺手标出「一条塞了多个表达」的记录。

    cd /home/ysc/mcp && .venv/bin/python kg/itemdump.py

跟 wordlint 同一个毛病、不同的表：一条记录该是一个表达方式。
「てあげる てくれる てもらう」挤在一个 label 里的话，掌握度记在哪个
上面都不对——三个表达共用一条 mastery，学会一个就算学会三个。

标记规则：label 里出现空格、读点、斜杠、中点，就是挤了多个。
"""

import re
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "app.db"
MULTI = re.compile(r"[ 　、，,/／・･|｜]")


def main() -> int:
    if not DB.is_file():
        print(f"没有这个库：{DB}")
        return 1
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT code, label, point, form, after FROM item ORDER BY point, code"
    ).fetchall()
    con.close()

    bad = [r for r in rows if MULTI.search(r[1] or "")]
    print(f"item 共 {len(rows)} 条，其中 label 里挤了多个表达的 {len(bad)} 条\n")

    print("=== 挤了多个的 ===")
    for code, label, point, form, after in bad:
        print(f"  {code:24} | {label:40} | 功能 {point or '―':16} | "
              f"接 {form or '―'}")

    print("\n=== 全表 ===")
    for code, label, point, form, after in rows:
        mark = " ***" if MULTI.search(label or "") else ""
        print(f"  {code:24} | {label:40} | 功能 {point or '―':16} | "
              f"接 {form or '―':12} | 前 {after or '―'}{mark}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
