# -*- coding: utf-8 -*-
"""批量导入单词。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_word_import.py

  一、正常导入：中文键、英文键混着，有汉字的、没汉字的
  二、重复导入同一份文件：更新，不多出行
  三、同音词（はし：桥、筷子）靠汉字区分，不会被合成一条
  四、知识点不存在：词照样导，只是不挂，报告里单独列出
  五、缺假名或中文：跳过，报出行号
  六、文件中途坏掉：整批回滚，一行都不写
"""

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.kg_dag import import_file                                  # noqa: E402
from tools.entity import render_sql                                   # noqa: E402
from tools.word_import import WordError, format_report, import_words  # noqa: E402

KG = ROOT / "kg"
passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


WORDS = [
    {"汉字": "食べる", "假名": "たべる", "中文": "吃", "知识点": "verb-groups"},
    {"假名": "そこ", "中文": "那里"},                                  # 没有汉字
    {"kanji": "橋", "kana": "はし", "meaning": "桥", "point": "noun"},   # 英文键
    {"汉字": "箸", "假名": "はし", "中文": "筷子", "知识点": "noun"},     # 同音不同字
    {"汉字": "本", "假名": "ほん", "中文": "书", "知识点": "没有这个"},   # 知识点不存在
    {"汉字": "犬", "中文": "狗"},                                       # 缺假名
    {"汉字": "猫", "假名": "ねこ"},                                     # 缺中文
]


def main():
    ws = Path(tempfile.mkdtemp(prefix="wordimp_"))
    for d in ("entities", "queries", "content"):
        shutil.copytree(KG / d, ws / d)
    text = "\n\n".join(f.read_text(encoding="utf-8")
                       for f in sorted((ws / "entities").glob("*.entity")))
    con = sqlite3.connect(ws / "app.db")
    con.executescript(render_sql(text))
    con.commit()
    con.close()
    import_file(ws / "app.db", ws / "queries", ws / "content" / "kg.jsonl")

    def words():
        con = sqlite3.connect(ws / "app.db")
        try:
            return con.execute(
                "SELECT kanji, kana, meaning, point FROM word ORDER BY id").fetchall()
        finally:
            con.close()

    f = ws / "content" / "words.jsonl"
    f.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in WORDS),
                 encoding="utf-8")

    print("一、正常导入")
    r = import_words(ws / "app.db", ws / "queries", f)
    print("    " + format_report(r).replace("\n", "\n    "))
    check(r["new"] == 5 and r["updated"] == 0, f"新增 5 条：新增 {r['new']}，更新 {r['updated']}")
    check([x[1] for x in words()] == ["たべる", "そこ", "はし", "はし", "ほん"],
          f"库里：{[x[1] for x in words()]}")
    check(words()[0] == ("食べる", "たべる", "吃", "verb-groups"), f"第一条：{words()[0]}")
    check(words()[1] == (None, "そこ", "那里", None), f"没有汉字的：{words()[1]}")
    check(words()[2] == ("橋", "はし", "桥", "noun"), f"英文键也认：{words()[2]}")

    print("二、同音词")
    check(words()[3] == ("箸", "はし", "筷子", "noun"),
          f"はし 的另一个词单独一条：{words()[3]}")

    print("三、知识点不存在")
    check(words()[4] == ("本", "ほん", "书", None), f"词导进来了，但没挂：{words()[4]}")
    check([x[2] for x in r["unknown_point"]] == ["没有这个"],
          f"报告里列出来了：{r['unknown_point']}")

    print("四、缺字段")
    check([no for no, _ in r["skipped"]] == [6, 7], f"跳过第 6、7 条：{r['skipped']}")

    print("五、再导一遍同一份文件")
    r2 = import_words(ws / "app.db", ws / "queries", f)
    check(r2["new"] == 0 and r2["updated"] == 5,
          f"全是更新：新增 {r2['new']}，更新 {r2['updated']}")
    check(len(words()) == 5, f"行数没变：{len(words())}")

    print("六、改了中文再导，是更新")
    changed = [dict(WORDS[0], 中文="吃（改）")]
    f2 = ws / "content" / "w2.jsonl"
    f2.write_text(json.dumps(changed[0], ensure_ascii=False), encoding="utf-8")
    import_words(ws / "app.db", ws / "queries", f2)
    check(words()[0][2] == "吃（改）" and len(words()) == 5,
          f"改了中文，还是那一条：{words()[0]}")

    print("七、文件中途坏掉")
    bad = ws / "content" / "bad.jsonl"
    bad.write_text('{"假名": "いぬ", "中文": "狗"}\n{"假名": "ねこ", \n',
                   encoding="utf-8")
    before = len(words())
    try:
        import_words(ws / "app.db", ws / "queries", bad)
        check(False, "坏文件应该报错")
    except WordError as e:
        check("第 2 行" in str(e), f"报错指出行号：{e}")
    check(len(words()) == before, "一行都没写进去")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
