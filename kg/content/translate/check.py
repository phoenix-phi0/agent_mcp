# -*- coding: utf-8 -*-
"""合完之后直接看库里成了什么样。

    cd /home/ysc/mcp && .venv/bin/python kg/content/translate/check.py
    cd /home/ysc/mcp && .venv/bin/python kg/content/translate/check.py 2069 1991

merge.py 只管写回 words_jlpt.jsonl，真正入库是 `py -m kg import` 干的。
中间隔着一层，所以写回成功不等于库里对了——这个脚本查库，不查文件。

看三件事：
  1. 还有多少条释义是英文（等级标记 [N1] 里的 N 不算，先剔掉再判）
  2. 按等级分组，各自还剩多少英文的
  3. 抽几条看看长相，确认不是串行（释义得跟汉字对得上）

第三件事可以带编号跑：merge.py 只核对编号对不对齐，编号对齐而译文
整体错位一行它查不出来——那得人眼看汉字和释义配不配。所以哪一批有
疑问就把那批的几个编号传进来。
"""

import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent.parent / "app.db"

# 等级标记本身带字母，判「还有英文吗」之前先剔掉
PLAIN = ("replace(replace(replace(replace(replace("
         "meaning,'[N1]',''),'[N2]',''),'[N3]',''),'[N4]',''),'[N5]','')")

# 不传编号时的默认抽查对象，覆盖各等级
DEFAULT_IDS = (874, 4339, 7704, 3412, 5398, 2140)


def main(argv: list[str]) -> int:
    if not DB.is_file():
        print(f"没有这个库：{DB}")
        return 1

    try:
        ids = tuple(int(a) for a in argv) or DEFAULT_IDS
    except ValueError:
        print(f"参数要是词的编号（整数），收到：{' '.join(argv)}")
        return 1

    con = sqlite3.connect(DB)

    tot, = con.execute("SELECT COUNT(*) FROM word").fetchone()
    en, = con.execute(
        f"SELECT COUNT(*) FROM word WHERE {PLAIN} GLOB '*[A-Za-z]*'").fetchone()
    print(f"word 共 {tot} 条，释义还是英文的 {en} 条，中文的 {tot - en} 条")

    print("\n按等级：")
    rows = con.execute(f"""
        SELECT CASE WHEN meaning GLOB '[[]N[1-5][]]*'
                    THEN substr(meaning, 2, 2) ELSE '(无标记)' END AS lv,
               COUNT(*),
               SUM(CASE WHEN {PLAIN} GLOB '*[A-Za-z]*' THEN 1 ELSE 0 END)
          FROM word GROUP BY lv ORDER BY lv
    """).fetchall()
    for lv, n, e in rows:
        print(f"  {lv:8} 共 {n:5}  还是英文 {e:5}")

    print(f"\n抽查 {len(ids)} 条（确认释义没跟别的词串行）：")
    holes = set(ids)
    marks = ",".join("?" * len(ids))
    for r in con.execute(
            f"SELECT id, kanji, kana, meaning FROM word"
            f" WHERE id IN ({marks}) ORDER BY id", ids):
        holes.discard(r[0])
        print("  " + " | ".join(str(x) for x in r))
    if holes:
        print(f"  库里没有这些编号：{sorted(holes)}")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
