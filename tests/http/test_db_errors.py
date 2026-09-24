# -*- coding: utf-8 -*-
"""db 包出错时一律报错，不伪装成数据。

    cd /home/ysc/mcp && .venv/bin/python tests/http/test_db_errors.py

早先事务外出错时：「查询」返回 [{"错误": …}]、「查一行」返回 {"错误": …}、
「查一值」「写库」「写库表」返回 "[出错] …" 文本。都看起来像正常结果——
列表多一行空白；写失败了，调用方判「影响 等于 0」不成立，接着回「已保存」。

这里用 Flask 测试客户端直接打接口，确认每种出错都变成错误响应，而且出错
之后的语句（比如「消息 系统 已保存」）不会执行。
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dsl_http import Router      # noqa: E402

ROUTES = """\
接口 POST /q_missing
  用包 db http
  设 行表 = 查询 app.db no_such_query
  设 组.notes = {行表}
  响应 lists {组}
结束


接口 POST /q_param
  用包 db http
  设 一条 = 查一行 app.db note_one
  响应 form {一条}
结束


接口 POST /count
  用包 db http
  设 n = 查一值 app.db note_count
  返回 {"n":"{n}"}
结束


接口 POST /save
  用包 db http
  设 影响 = 写库表 app.db note_insert {请求}
  消息 系统 已保存 ok
结束


接口 POST /save_positional
  用包 db http
  设 影响 = 写库 app.db note_insert title={title}
  消息 系统 已保存 ok
结束


接口 POST /save_tx
  用包 db http
  事务 app.db
    设 影响 = 写库表 app.db note_insert {请求}
  结束
  消息 系统 已保存 ok
结束


接口 POST /save_null
  用包 db http
  设 影响 = 写库 app.db note_insert_null
  消息 系统 已保存 ok
结束


接口 POST /tag
  用包 db http
  设 影响 = 写库表 app.db tag_insert {请求}
  消息 系统 已保存 ok
结束
"""

QUERIES = {
    "note_one": "SELECT id, title FROM note WHERE id = :id",
    "note_count": "SELECT count(*) FROM note",
    "note_insert": "INSERT INTO note(title) VALUES(:title)",
    "note_insert_null": "INSERT INTO note(title) VALUES(NULL)",
    "tag_insert": "INSERT INTO tag(note_id) VALUES(CAST(:note_id AS INTEGER))",
}

# 只用来给报错翻译字段名：title 的中文名是「标题」
ENTITY = "实体 note 笔记\n  字段 title 文本 必填 唯一 标题\n结束\n"

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def main():
    ws = Path(tempfile.mkdtemp(prefix="dberr_"))
    (ws / "routes").mkdir()
    (ws / "routes" / "t.zs").write_text(ROUTES, encoding="utf-8")
    (ws / "queries").mkdir()
    for name, sql in QUERIES.items():
        (ws / "queries" / f"{name}.sql").write_text(sql, encoding="utf-8")
    con = sqlite3.connect(ws / "app.db")
    con.execute("CREATE TABLE note(id INTEGER PRIMARY KEY, title TEXT UNIQUE NOT NULL)")
    con.execute("CREATE TABLE tag(id INTEGER PRIMARY KEY, "
                "note_id INTEGER NOT NULL REFERENCES note(id))")
    con.commit()
    con.close()
    (ws / "entities").mkdir()
    (ws / "entities" / "note.entity").write_text(ENTITY, encoding="utf-8")

    app = Router(ws / "routes", ws, ws / "sessions", real=False).app()
    c = app.test_client()

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {}), r.get_data(as_text=True)

    def count():
        con = sqlite3.connect(ws / "app.db")
        try:
            return con.execute("SELECT count(*) FROM note").fetchone()[0]
        finally:
            con.close()

    print("一、读")
    st, body, text = post("/q_missing")
    check(st >= 400 and "lists" not in body,
          f"查询名写错：{st}，没有列表数据（早先是一行假数据）")
    check("no_such_query" in text, "报错里说了是哪个查询")
    st, body, text = post("/q_param")
    check(st >= 400 and "form" not in body, f"查一行少参数：{st}，没有 form（早先是一个假对象）")

    print("二、写：失败不能报「已保存」")
    st, body, text = post("/save", title="第一 条")
    check(st == 200 and "已保存" in text and count() == 1, f"正常保存：{st}（对照）")
    st, body, text = post("/save", title="第一 条")
    check(st == 409 and "已保存" not in text, f"标题重复（唯一约束）：{st}，没有「已保存」")
    check(body.get("error") == "标题已经存在，换一个",
          f"报的是人话，字段名用了实体里的标签：{body.get('error')}")
    check("UNIQUE" not in text and "t.zs" not in text, "不把 SQLite 原文、脚本文件名给用户")
    check(count() == 1, "库里仍然只有一条")
    st, body, text = post("/save")
    check(st == 500 and "已保存" not in text,
          f"写库表少参数：{st}——这是脚本的毛病，仍按服务器出错算")
    st, body, text = post("/save_positional", title="第一 条")
    check(st == 409 and "已保存" not in text, f"写库（按位置传参）也一样：{st}")
    st, body, _ = post("/save_null")
    check(st == 400 and body.get("error") == "标题不能为空", f"必填为空：{st} {body}")
    st, body, _ = post("/tag", note_id=999)
    check(st == 409 and "关联的记录不存在" in body.get("error", ""),
          f"关联的记录不存在（外键）：{st} {body}")

    print("三、事务里照旧回滚")
    st, body, text = post("/save_tx", title="第一 条")
    check(st == 409 and "已保存" not in text and count() == 1,
          f"事务里重复：{st}，回滚了，同样是人话：{body.get('error')}")
    st, body, text = post("/save_tx", title="第二条")
    check(st == 200 and count() == 2, "事务里正常保存（对照）")

    print("四、查一值")
    st, body, _ = post("/count")
    check(st == 200 and str(body.get("n")) == "2", f"count：{body}")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
