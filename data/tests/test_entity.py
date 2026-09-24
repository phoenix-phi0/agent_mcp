# -*- coding: utf-8 -*-
"""端到端测试：一份实体定义 + 一份界面描述 → 数据库 + 前端。

    cd mcp
    py data/tests/test_entity.py

验的是整套东西的核心主张：改一行实体定义，SQL、模型、前端一起变，
三边没有一处需要手工同步。

不需要 node，也不需要网络——SQL 用 sqlite 真建一次库，模型只查语法。
前端的运行时行为归 test_page.js 管。
"""

import re
import sqlite3
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent.parent
sys.path.insert(0, str(BASE))

from tools.entity import (parse as parse_ent, validate as validate_ent,  # noqa: E402
                          field_table, options_map, render_db, dump)
from tools.ui import compile_ui                                          # noqa: E402

PASS = FAIL = 0


def check(name, actual, expected):
    global PASS, FAIL
    good = actual == expected
    PASS, FAIL = (PASS + 1, FAIL) if good else (PASS, FAIL + 1)
    print(f"  {'OK  ' if good else 'FAIL'} {name}")
    if not good:
        print(f"         期望 {expected!r}\n         实际 {actual!r}")


def ok(name, cond, extra=""):
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if cond else (PASS, FAIL + 1)
    print(f"  {'OK  ' if cond else 'FAIL'} {name}{'' if cond else '  ' + extra}")


def build(ent_text, ui_text):
    """一份实体 + 一份界面 → 数据库文件 + app.js。

    注意 fields 和 options_map 都来自实体，调用方不手写。
    """
    ents = parse_ent(ent_text)
    problems = validate_ent(ents)
    db = render_db(ents, db_name="blog")
    r = compile_ui(ui_text, backend="vue", fields=field_table(ents),
                   require_bind=True,
                   options={"title": "博客", "options_map": options_map(ents)})
    return ents, problems, db, r["result"]["files"]["app.js"], r["issues"]


def main() -> int:
    ent_text = (HERE / "blog.ent").read_text(encoding="utf-8")
    ui_text = (HERE / "blog.ui").read_text(encoding="utf-8")
    ents, problems, db, js, issues = build(ent_text, ui_text)

    print("\n【1. 实体解析】")
    print(dump(ents))
    check("一个实体", len(ents), 1)
    check("六个字段", len(ents[0].fields), 6)
    check("无问题", problems, [])
    check("UI 侧无 issue", [str(i) for i in issues], [])

    print("\n【2. 建表 SQL —— 真拿 sqlite 跑一遍】")
    sql = db["schema.sql"]
    with tempfile.TemporaryDirectory() as tmp:
        con = sqlite3.connect(str(Path(tmp) / "t.db"))
        con.executescript(sql)
        cols = {r[1]: (r[2], bool(r[3])) for r in con.execute("PRAGMA table_info(article)")}
        check("列齐了", sorted(cols),
              ["body", "featured", "id", "published_at", "status", "title", "views"])
        check("title 是 VARCHAR 且 NOT NULL", cols["title"], ("VARCHAR(255)", True))
        check("body 是 TEXT 且可空", cols["body"], ("TEXT", False))
        check("published_at 是 DATETIME", cols["published_at"][0], "DATETIME")

        con.execute("INSERT INTO article (title,status) VALUES ('甲','draft')")
        ok("插入合法行", True)

        try:
            con.execute("INSERT INTO article (title,status) VALUES ('乙','nope')")
            ok("CHECK 挡住非法枚举", False, "→ 非法值插进去了")
        except sqlite3.IntegrityError:
            ok("CHECK 挡住非法枚举", True)

        try:
            con.execute("INSERT INTO article (status) VALUES ('draft')")
            ok("NOT NULL 挡住缺必填", False, "→ 缺 title 也插进去了")
        except sqlite3.IntegrityError:
            ok("NOT NULL 挡住缺必填", True)
        con.close()

    print("\n【3. SQLAlchemy 模型】")
    models = db["models.py"]
    compile(models, "models.py", "exec")          # 语法不对会抛
    ok("语法合法", True)
    ok("类名从表名派生 article → Article", "class Article(Base):" in models)
    ok("必填字段不是 Optional", "title: Mapped[str]" in models)
    ok("可空字段是 Optional", "body: Mapped[Optional[str]]" in models)
    ok("日期字段带 datetime import", "from datetime import datetime" in models)

    print("\n【4. 前端控件由实体的类型推出】")
    for fname, want in [("status", "radio"), ("published_at", "date"),
                        ("featured", "checkbox"), ("title", "text")]:
        ok(f"{fname} → {want}", f'type="{want}" v-model="form.{fname}"' in js)
    ok("body 长文本 → textarea", '<textarea v-model="form.body"' in js)

    print("\n【5. 必填和选项也来自实体（.ui 里没写）】")
    ok("title 带 required", 'v-model="form.title" required' in js)
    check("枚举选项", re.findall(r'v-model="form.status" value="(\w+)"', js),
          ["draft", "published", "archived"])

    print("\n【6. 改一行实体定义，三边一起变】")
    # 6a. 枚举加一个选项
    t2 = ent_text.replace("draft,published,archived", "draft,review,published,archived")
    _, _, db2, js2, _ = build(t2, ui_text)
    ok("SQL 的 CHECK 跟着变", "'review'" in db2["schema.sql"])
    check("前端选项跟着变",
          re.findall(r'v-model="form.status" value="(\w+)"', js2),
          ["draft", "review", "published", "archived"])

    # 6b. 类型和必填一起改
    t3 = ent_text.replace("字段 body 长文本 正文", "字段 body 文本 必填 正文")
    _, _, db3, js3, _ = build(t3, ui_text)
    ok("SQL：TEXT → VARCHAR NOT NULL",
       "body VARCHAR(255) NOT NULL" in db3["schema.sql"])
    ok("模型：去掉 Optional", "body: Mapped[str]" in db3["models.py"]
       and "body: Mapped[Optional[str]]" not in db3["models.py"])
    ok("前端：textarea → input required",
       'v-model="form.body" required' in js3 and "<textarea" not in js3)

    print("\n【7. 校验】")
    from tools.entity import parse as _p
    bad = _p("实体 x\n  字段 id 整数\n  字段 a 枚举\n  字段 a 文本\n结束\n")
    msgs = " | ".join(validate_ent(bad))
    ok("挡住手写 id", "不用写 id" in msgs)
    ok("挡住没选项的枚举", "要给选项" in msgs)
    ok("挡住重复字段名", "重复的字段名" in msgs)

    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}\n{'=' * 50}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
