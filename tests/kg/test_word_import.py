# -*- coding: utf-8 -*-
"""批量导入单词（DSL 版，kg/routes/word_import.zs）。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_word_import.py

  一、正常导入：有汉字的、没汉字的
  二、重复导入同一份文件：更新，不多出行
  三、同音词（はし：桥、筷子）靠汉字区分，不会被合成一条
  四、知识点不存在：词照样导，只是不挂，报告里单独计数
  五、缺假名：跳过，报出第几条（缺中文照样导——假名表那类条目没有意思）

导入早先是 Python（tools/word_import.py），理由是引擎缺两样：遍历拿不到
下标、可选字段缺了会留成 {项.kanji} 字面量。两样补上之后改成了 DSL，这个
测试也跟着走接口——测的必须是实际走的那条路，不然 DSL 版坏了测试照样全绿。
"""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import import_graph, import_words, make_ws  # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


WORDS = [
    {"kanji": "食べる", "kana": "たべる", "meaning": "吃", "point": "verb-groups"},
    {"kana": "そこ", "meaning": "那里"},                       # 没有汉字
    {"kanji": "橋", "kana": "はし", "meaning": "桥", "point": "noun"},
    {"kanji": "箸", "kana": "はし", "meaning": "筷子", "point": "noun"},  # 同音不同字
    {"kanji": "本", "kana": "ほん", "meaning": "书", "point": "没有这个"},  # 知识点不存在
    {"kanji": "犬", "meaning": "狗"},                          # 缺假名
    {"kanji": "猫", "kana": "ねこ"},                           # 没有中文，照样导
]


def main():
    ws = make_ws(Path(tempfile.mkdtemp(prefix="wordimp_")))
    import_graph(ws)

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
    r = import_words(ws)
    print("    " + json.dumps(r, ensure_ascii=False))
    check(r.get("new") == "6", f"新增 6 条：{r.get('new')}")
    check([x[1] for x in words()] == ["たべる", "そこ", "はし", "はし", "ほん", "ねこ"],
          f"库里：{[x[1] for x in words()]}")
    check(words()[0] == ("食べる", "たべる", "吃", "verb-groups"), f"第一条：{words()[0]}")
    check(words()[1] == (None, "そこ", "那里", None),
          f"没有汉字、没挂知识点的，两列都是 NULL 不是空串：{words()[1]}")

    print("二、同音词")
    check(words()[2] == ("橋", "はし", "桥", "noun")
          and words()[3] == ("箸", "はし", "筷子", "noun"),
          f"はし 两条各自独立：{words()[2]}、{words()[3]}")

    print("三、知识点不存在")
    check(words()[4] == ("本", "ほん", "书", None), f"词导进来了，但没挂：{words()[4]}")
    check(r.get("bad_point") == "1", f"报告里计了数：bad_point={r.get('bad_point')}")
    check("第5条" in (r.get("note") or ""), f"说清是第几条：{r.get('note')}")

    print("四、缺字段")
    check(r.get("skipped") == "1", f"只跳过缺假名的 1 条：{r.get('skipped')}")
    check("第6条" in (r.get("note") or ""), f"行号对得上：{r.get('note')}")

    print("五、再导一遍同一份文件")
    r2 = import_words(ws)
    check(r2.get("new") == "0" and r2.get("updated") == "6",
          f"全是更新：新增 {r2.get('new')}，更新 {r2.get('updated')}")
    check(len(words()) == 6, f"行数没变：{len(words())}")
    check(r2.get("no_point") == "3",
          f"没挂知识点的计数第二遍也在（更新路径上也要数）：{r2.get('no_point')}")

    print("六、改了中文再导，是更新")
    f.write_text(json.dumps(dict(WORDS[0], meaning="吃（改）"), ensure_ascii=False),
                 encoding="utf-8")
    import_words(ws)
    check(words()[0][2] == "吃（改）" and len(words()) == 6,
          f"改了中文，还是那一条：{words()[0]}")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
