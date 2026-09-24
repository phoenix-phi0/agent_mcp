# -*- coding: utf-8 -*-
"""单词表，以及它跟知识点的关联。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_word.py

一个词属于一个知识点（word.point 指向 node.code），不是多对多。留空表示
还没挂——批量导入之后要能查出这种词，否则按知识点出题时它们等于不存在。

用 Flask 测试客户端打真接口，不起服务：省掉 shell 里那层 JSON 转义，
之前手写 curl 就是栽在这上面，三条请求全发的是带反斜杠的字面量。

库建在临时目录，不碰 kg/app.db。
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gen.project import make_app                    # noqa: E402
from tools.entity import render_sql                 # noqa: E402
from tools.kg_dag import import_file                # noqa: E402

KG = ROOT / "kg"

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def main():
    ws = Path(tempfile.mkdtemp(prefix="word_"))
    import shutil
    for d in ("entities", "queries", "routes", "content"):
        shutil.copytree(KG / d, ws / d)

    text = "\n\n".join(f.read_text(encoding="utf-8")
                       for f in sorted((ws / "entities").glob("*.entity")))
    con = sqlite3.connect(ws / "app.db")
    con.executescript(render_sql(text))
    con.commit()
    con.close()
    # 图先导进去，不然没有知识点可挂
    import_file(ws / "app.db", ws / "queries", ws / "content" / "kg.jsonl")

    app, _ = make_app(ws, real=False)
    c = app.test_client()

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    def words():
        con = sqlite3.connect(ws / "app.db")
        try:
            return con.execute("SELECT kana, point FROM word ORDER BY id").fetchall()
        finally:
            con.close()

    print("一、建词")
    st, body = post("/word/create", kanji="食べる", kana="たべる", meaning="吃",
                    point="verb-groups")
    check(st == 200, f"挂在 verb-groups 上的词：{st}")
    # 可选字段也要把键带上：SQL 里有 :kanji 就必须给，缺了直接报错。
    # 界面上不会漏——表单每个字段都会发出去，空的就是空串。
    st, body = post("/word/create", kanji="", kana="そこ", meaning="那里", point="")
    check(st == 200, f"没有汉字、也没挂知识点的词：{st} {body.get('error', '')}")
    # 没填的可选字段存成 NULL，不是空串——空串会被外键拿去找 code='' 的
    # 记录。生成的 insert 里是 NULLIF(:point, '')。
    check(words() == [("たべる", "verb-groups"), ("そこ", None)],
          f"库里：{words()}")

    print("二、挂到不存在的知识点")
    st, body = post("/word/create", kanji="", kana="てすと", meaning="测试",
                    point="没有这个")
    check(st == 409 and "关联的记录不存在" in body.get("error", ""),
          f"外键拦住了：{st} {body}")
    check(len(words()) == 2, "那条词没进库")

    def words_of(body):
        """接口把表格数据放在 lists 里，键是界面上那张表的名字。"""
        return (body.get("lists") or {}).get("words", [])

    print("三、按知识点取词")
    st, body = post("/point/words", point="verb-groups")
    check(st == 200 and [r["kana"] for r in words_of(body)] == ["たべる"],
          f"verb-groups 下面：{words_of(body)}")
    st, body = post("/point/words", point="masu-form")
    check(st == 200 and words_of(body) == [], "别的知识点下面没有")

    print("四、还没挂的词")
    st, body = post("/word/orphans")
    check(st == 200 and [r["kana"] for r in words_of(body)] == ["そこ"],
          f"查得出来：{words_of(body)}")

    print("五、改挂到别的知识点")
    wid = None
    con = sqlite3.connect(ws / "app.db")
    wid = con.execute("SELECT id FROM word WHERE kana='そこ'").fetchone()[0]
    con.close()
    st, body = post("/word/update", id=wid, kana="そこ", meaning="那里",
                    kanji="", point="masu-form")
    check(st == 200, f"改挂：{st} {body.get('error', '')}")
    st, body = post("/word/orphans")
    check(words_of(body) == [], "没挂的词清空了")
    st, body = post("/point/words", point="masu-form")
    check([r["kana"] for r in words_of(body)] == ["そこ"], "挂到 masu-form 下面了")

    print("六、删掉知识点时，挂着的词怎么办")
    con = sqlite3.connect(ws / "app.db")
    con.execute("PRAGMA foreign_keys = ON")
    try:
        con.execute("DELETE FROM node WHERE code='masu-form'")
        con.commit()
        check(False, "外键应该拦住：还有词挂在这个知识点上")
    except sqlite3.IntegrityError:
        check(True, "外键拦住了：知识点底下还有词，删不掉")
    finally:
        con.close()

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
