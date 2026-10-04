# -*- coding: utf-8 -*-
"""查 word 表里「一条塞了多个词」的记录。

    cd /home/ysc/mcp && .venv/bin/python kg/wordlint.py
    cd /home/ysc/mcp && .venv/bin/python kg/wordlint.py --全部   # 不截断

一条记录是一个词。这条约束没写进 .entity——数据库拦不住「貯める／溜める」
这种值，它是合法文本。但出题时这条记录既不是「貯める」也不是「溜める」，
两边都答不对，而且不报错。同样的问题已经出现两次（手填的时候、导入的
时候），所以留下这个检查。

查四项：

  假名列只该有假名。出现「・」「／」「、」基本就是两个词挤在了一起。
  汉字列只该有汉字、假名和数字（「1日」「2月」是正常写法）。
  中文列**既有假名又有分隔号**，多半是把原词的异体写进了释义。两个条件
    都要满足，缺一个就不报：光有假名不算，「憎む 的可能形」这类释义本来
    就该引原形；光有斜杠也不算，「吃/喝（尊敬语）」是一个词的两个义项。
    早先只查「有假名或有斜杠」，报出 128 条，一条真问题都没有——那样的
    检查会被当成噪音直接忽略，等于没查。
  同一个「汉字+假名」出现在多条记录里，是反过来的同一个毛病：一个词散在
    多行。导入器按这个组合认词，所以重复意味着两条都会被更新成不同的值，
    之后哪条生效看运气。

义项用「；」分是允许的——义项是同一个词的不同意思，不是多个词。但四个
以上一般是没拆开，列出来人看一眼。
"""

import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

DB = Path(__file__).resolve().parent / "app.db"

_KANA = r"ぁ-ゖ゛-ゟァ-ヺー-ヿ"
# 假名区间里 ・(30FB) 是分隔号不是假名，上面的区间已经把它排除在外
KANA_OK = re.compile(rf"^[{_KANA}]+$")
# 汉字列：汉字 + 假名 + 々 + 数字（「1日」「2月」是正常写法）
KANJI_OK = re.compile(rf"^[一-鿿々{_KANA}0-9０-９]+$")
# 释义里混进词形：要同时有假名和分隔号，见模块文档
HAS_KANA = re.compile(rf"[{_KANA}]")
HAS_SLASH = re.compile(r"[・/／]")

# 一眼能认出的「两个词挤一起」的记号
SPLITTERS = "・/／、，,;；|｜＋+&＆ 　"

LIMIT = 40


def main(argv: list[str]) -> int:
    if not DB.is_file():
        print(f"没有这个库：{DB}")
        return 1
    show_all = "--全部" in argv
    con = sqlite3.connect(DB)

    rows = con.execute(
        "SELECT id, kanji, kana, meaning FROM word ORDER BY id").fetchall()
    tot, = con.execute("SELECT COUNT(*) FROM word").fetchone()
    con.close()

    bad_kana, bad_kanji, bad_meaning, many = [], [], [], []
    for wid, kanji, kana, meaning in rows:
        if kana and not KANA_OK.match(kana):
            bad_kana.append((wid, kanji, kana, meaning, _why(kana)))
        if kanji and not KANJI_OK.match(kanji):
            bad_kanji.append((wid, kanji, kana, meaning, _why(kanji)))
        if meaning:
            if HAS_KANA.search(meaning) and HAS_SLASH.search(meaning):
                bad_meaning.append((wid, kanji, kana, meaning, "假名+分隔号"))
            if meaning.count("；") >= 3:
                many.append((wid, kanji, kana, meaning, ""))

    seen = Counter((k or "", a) for _, k, a, _ in rows)
    dup = [(wid, kanji, kana, meaning, f"共 {seen[(kanji or '', kana)]} 条")
           for wid, kanji, kana, meaning in rows
           if seen[(kanji or "", kana)] > 1]

    print(f"word 共 {tot} 条")
    _report("假名列有非假名字符", bad_kana, show_all, "多半是两个词挤一起")
    _report("汉字列有非汉字非假名非数字字符", bad_kanji, show_all)
    _report("中文列混进了词形", bad_meaning, show_all, "既有假名又有分隔号")
    _report("同一个汉字+假名出现在多条记录", dup, show_all, "一个词散在多行")
    _report("中文列义项四个以上", many, show_all, "不一定是错，人看一眼")

    return 1 if (bad_kana or bad_kanji or bad_meaning or dup) else 0


def _why(s: str) -> str:
    return "".join(sorted({c for c in s if c in SPLITTERS}))


def _report(title: str, rows: list, show_all: bool, note: str = "") -> None:
    print(f"\n{title}：{len(rows)} 条" + (f"（{note}）" if note else ""))
    shown = rows if show_all else rows[:LIMIT]
    for wid, kanji, kana, meaning, why in shown:
        tail = f"   ← {why}" if why else ""
        print(f"  {wid:5} | {kanji or '―':12} | {kana:16} | "
              f"{(meaning or '')[:34]}{tail}")
    if len(rows) > len(shown):
        print(f"  …还有 {len(rows) - len(shown)} 条，加 --全部 看完")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
