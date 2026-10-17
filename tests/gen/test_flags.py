# -*- coding: utf-8 -*-
"""实体旗标「系统」「级联删除」。

    cd /workspace/agent_mcp && .venv/bin/python tests/gen/test_flags.py

一、解析与校验（含错误用法）
二、生成的 sql / zs / ui 内容
三、建表 SQL：级联用 ON DELETE CASCADE，没标的仍是 RESTRICT
四、进程内起 make_app，Flask test client 端到端
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gen.project import build, ensure_db, generate, init, make_app   # noqa: E402
from gen.templates_ import render                                     # noqa: E402
from tools.entity import (EntitySyntaxError, parse, render_sql,       # noqa: E402
                          validate)

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


ENTITIES = """\
实体 project 项目
  字段 name 文本 必填 名称
  字段 status 枚举 草稿,已提交,已通过 必填 默认 草稿 系统 状态
结束

实体 task 任务
  字段 project_id 整数 必填 索引 关联 project 项目 级联删除
  字段 title 文本 必填 标题
结束

实体 note 备注
  字段 task_id 整数 必填 索引 关联 task 任务 级联删除
  字段 body 文本 必填 内容
结束

实体 memo 便签
  字段 project_id 整数 必填 关联 project 项目
  字段 text 文本 必填 内容
结束
"""


def problems_of(text):
    try:
        return validate(parse(text))
    except EntitySyntaxError as e:
        return [str(e)]


def main():
    print("一、解析与校验")
    ents = {e.name: e for e in parse(ENTITIES)}
    st = ents["project"].field("status")
    check(st.system and st.default == "草稿" and st.label == "状态" and st.required,
          "系统旗标解析，标签仍是「状态」")
    t = ents["task"].field("project_id")
    check(t.cascade and t.ref == "project" and t.label == "项目",
          "级联删除写在标签后面也能解析，标签不被吞")
    t2 = parse("实体 a 甲\n  字段 x 整数 关联 a 级联删除 标签\n结束")[0].field("x")
    check(t2.cascade and t2.label == "标签", "级联删除写在标签前面也行")
    check(not ents["memo"].field("project_id").cascade, "没写的不是级联")
    check(validate(parse(ENTITIES)) == [], "示例实体校验通过")
    p = problems_of("实体 a 甲\n  字段 s 文本 必填 系统 状态\n结束")
    check(len(p) == 1 and "默认值" in p[0] and "s" in p[0], f"系统字段没默认值报错：{p}")
    check(problems_of("实体 a 甲\n  字段 owner 文本 必填 索引 系统\n结束") == [],
          "owner 带系统不要求默认值")
    p = problems_of("实体 a 甲\n  字段 n 整数 级联删除 数\n结束")
    check(len(p) == 1 and "级联删除" in p[0] and "关联" in p[0], f"没有关联却写级联删除报错：{p}")
    d = ents["project"].field("status").to_dict()
    check(d.get("system") is True and "cascade" not in d, "to_dict 只在有旗标时带键")
    check("system" not in ents["project"].field("name").to_dict(), "普通字段 to_dict 不变")

    print("二、生成的 sql / zs / ui")
    for set_name in ("default", "full"):
        files = render(ents["project"], set_name)
        ins = files["queries/project_insert.sql"]
        upd = files["queries/project_update.sql"]
        one = files["queries/project_one.sql"]
        lst = files["queries/project_list.sql"]
        check("status" not in ins and "INSERT INTO project(name)" in ins,
              f"{set_name}：insert 不含系统字段")
        check("status" not in upd and "name = :name" in upd, f"{set_name}：update 的 SET 没有系统字段")
        check("status" in one and "status" in lst, f"{set_name}：one/list 照常返回")
        zs = files["routes/project.zs"]
        check("status" not in zs, f"{set_name}：zs 不从请求取系统字段")
        ui = files["ui/project.ui"]
        check("全部字段 project 除 status" in ui, f"{set_name}：表单排除系统字段")
        check("列 status 状态" in ui, f"{set_name}：列表里仍显示")
    priv = parse("实体 q 记录\n  字段 owner 文本 必填 索引\n  字段 st 文本 必填 默认 草稿 系统 状态\n"
                 "  字段 body 文本 必填 内容\n结束")[0]
    pf = render(priv, "private")
    check("st" not in pf["queries/q_insert.sql"].replace("INSERT", "")
          and "st =" not in pf["queries/q_update.sql"], "private：insert/update 不含系统字段")
    check("全部字段 q 除 owner st" in pf["ui/q.ui"], "private：表单排除 owner 和系统字段")

    print("三、建表 SQL")
    sql = render_sql(ENTITIES, strict=True)
    check("REFERENCES project(id) ON DELETE CASCADE" in sql, "task → project 是 CASCADE")
    check("REFERENCES task(id) ON DELETE CASCADE" in sql, "note → task 是 CASCADE")
    memo = sql[sql.index("CREATE TABLE memo"):]
    check("ON DELETE RESTRICT" in memo and "CASCADE" not in memo, "memo 仍是 RESTRICT")

    print("四、端到端（make_app + Flask test client）")
    root = Path(tempfile.mkdtemp(prefix="flags_"))
    init(root, sample=False)
    (root / "entities" / "m.entity").write_text(ENTITIES, encoding="utf-8")
    generate(root, "full")
    ensure_db(root)
    build(root)
    app = make_app(root)[0]
    c = app.test_client()

    def post(path, body):
        r = c.post(path, json=body)
        try:
            return r.status_code, r.get_json(silent=True)
        except Exception:
            return r.status_code, None

    db = sqlite3.connect(root / "app.db")

    def q(sql, *a):
        return db.execute(sql, a).fetchall()

    s, _ = post("/project/create", {"name": "甲", "status": "已通过"})
    check(s == 200, f"create 成功：{s}")
    check(q("SELECT name, status FROM project") == [("甲", "草稿")],
          f"create 传别的状态仍写默认值：{q('SELECT name, status FROM project')}")
    pid = q("SELECT id FROM project")[0][0]
    s, _ = post("/project/update", {"id": pid, "name": "乙", "status": "已驳回"})
    check(q("SELECT name, status FROM project WHERE id=?", pid) == [("乙", "草稿")],
          "update 改得了普通字段、改不了系统字段")
    s, body = post("/project/one", {"id": pid})
    check(s == 200 and "草稿" in str(body), f"one 照常返回系统字段：{str(body)[:80]}")
    db.execute("UPDATE project SET status='已提交' WHERE id=?", (pid,))
    db.commit()
    s, body = post("/project/list", {})
    check("已提交" in str(body), "list 照常返回系统字段")

    # 三层：project → task → note
    for i in range(2):
        post("/task/create", {"project_id": pid, "title": f"t{i}"})
    tids = [r[0] for r in q("SELECT id FROM task")]
    for t_id in tids:
        post("/note/create", {"task_id": t_id, "body": "n"})
    check(len(q("SELECT * FROM task")) == 2 and len(q("SELECT * FROM note")) == 2, "三层数据建好")
    s, _ = post("/project/delete", {"id": pid})
    check(s == 200, f"删父成功：{s}")
    check(q("SELECT count(*) FROM project")[0][0] == 0
          and q("SELECT count(*) FROM task")[0][0] == 0
          and q("SELECT count(*) FROM note")[0][0] == 0, "三层级联：子孙都没了")

    # 未标级联：被拒，且父记录还在
    post("/project/create", {"name": "丙"})
    pid2 = q("SELECT id FROM project")[0][0]
    post("/memo/create", {"project_id": pid2, "text": "m"})
    s, body = post("/project/delete", {"id": pid2})
    check(s >= 400, f"未标级联的被引用时删除被拒：{s} {str(body)[:80]}")
    check(q("SELECT count(*) FROM project")[0][0] == 1
          and q("SELECT count(*) FROM memo")[0][0] == 1, "被拒后父子都还在")
    db.close()

    print(f"\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
