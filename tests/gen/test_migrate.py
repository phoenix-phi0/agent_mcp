# -*- coding: utf-8 -*-
"""老库只加不改：tools/migrate.py 的 migrate_additive 和「迁移 只加」开关。

    cd /home/ysc/mcp && .venv/bin/python tests/gen/test_migrate.py

一、老库缺表、缺列、缺索引：补齐；已有的行一条不少，已有表的建表语句一个字没变
二、重复执行幂等：第二次什么都不补
三、补不了的、对不上的只告警不动表：列类型/必填不一样、库里多出来的列、
    必填又没默认值的新列、唯一索引撞上已有的重复行
四、同表同列同唯一性的索引已经有了（名字不一样）：不重复建
五、实体的「唯一 a b」行：渲染成唯一索引；只写一列、写了不存在的列报错
六、开关：路由顶层写了「迁移 只加」的项目，ensure_db 碰到已有的库会补；
    没写的项目（demo 这类）库原样不动；写在接口块里的不算
"""

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gen.project import ensure_db                         # noqa: E402
from tools.entity import EntitySyntaxError, render_sql    # noqa: E402
from tools.migrate import migrate_additive, switch_on     # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


# 老版本：两张表
OLD = """\
实体 learner 学习者
  字段 code 文本 必填 唯一 编号
  字段 name 文本 名字
结束

实体 mastery 掌握
  字段 learner 文本 必填 学习者
  字段 point 文本 必填 知识点
  字段 right 整数 必填 默认 0 答对
结束
"""

# 新版本：加了一张表、几列、两个索引、一个多列唯一
NEW = """\
实体 learner 学习者
  字段 code 文本 必填 唯一 编号
  字段 name 文本 名字
  字段 level 文本 等级
结束

实体 mastery 掌握
  字段 learner 文本 必填 索引 学习者
  字段 point 文本 必填 知识点
  字段 right 整数 必填 默认 0 答对
  字段 total 整数 必填 默认 0 答题数
  字段 note 文本 备注
  唯一 learner point
结束

实体 score 得分
  字段 learner 文本 必填 索引 学习者
  字段 value 整数 必填 分
结束
"""


def make_db(path: Path, entity_text: str) -> Path:
    con = sqlite3.connect(path)
    con.executescript(render_sql(entity_text, strict=True))
    con.commit()
    con.close()
    return path


def schema(path: Path) -> dict:
    con = sqlite3.connect(path)
    try:
        return {r[0]: r[1] for r in con.execute(
            "SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL")}
    finally:
        con.close()


def q(path: Path, sql: str):
    con = sqlite3.connect(path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def fresh_learner() -> str:
    path = Path(tempfile.mkdtemp(prefix="migrate_fresh_")) / "x.db"
    try:
        return schema(make_db(path, NEW))["learner"]
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="migrate_test_"))

    print("一、缺表、缺列、缺索引：补齐，数据不丢")
    db = make_db(tmp / "a.db", OLD)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO learner(code, name) VALUES('me', '我')")
    con.executemany("INSERT INTO mastery(learner, point, right) VALUES(?, ?, ?)",
                    [("me", "noun", 3), ("me", "verb", 1)])
    con.commit()
    con.close()
    s0 = schema(db)
    r = migrate_additive(db, NEW)
    check(r["tables"] == ["score"], f"补建了 score：{r['tables']}")
    check(sorted(r["columns"]) == ["learner.level", "mastery.note", "mastery.total"],
          f"补了三列：{r['columns']}")
    check(sorted(r["indexes"]) == ["idx_mastery_learner", "idx_score_learner",
                                   "ux_mastery_learner_point"], f"补了索引：{r['indexes']}")
    check(r["warnings"] == [], f"没有警告：{r['warnings']}")
    check(q(db, "SELECT learner, point, right, total, note FROM mastery ORDER BY point")
          == [("me", "noun", 3, 0, None), ("me", "verb", 1, 0, None)],
          "原有的行都在，新列是默认值 / 空")
    check(q(db, "SELECT code, name, level FROM learner") == [("me", "我", None)], "learner 的行在")
    s1 = schema(db)
    check(all(s1[k] == v for k, v in s0.items() if not k.startswith("sqlite_autoindex")
              and k not in ("learner", "mastery")),
          "别的对象原样")
    # ADD COLUMN 在原建表语句的「)」前面接一段；重建的话整句会是实体新渲染的样子
    check(s1["learner"].startswith(s0["learner"][:-1]) and s1["learner"] != fresh_learner(),
          "learner 只是多了一列（ALTER TABLE，没有重建）")
    fresh = schema(make_db(tmp / "fresh.db", NEW))
    check(s1["score"] == fresh["score"], "补建的表跟新建库的一模一样")
    con = sqlite3.connect(db)
    try:
        con.execute("INSERT INTO mastery(learner, point) VALUES('me', 'noun')")
        dup = False
    except sqlite3.IntegrityError:
        dup = True
    con.close()
    check(dup, "补上的多列唯一索引生效：同一人同一点不能有两行")

    print("二、幂等")
    r2 = migrate_additive(db, NEW)
    check(r2 == {"tables": [], "columns": [], "indexes": [], "warnings": []}, f"再跑一次什么都不补：{r2}")
    check(schema(db) == s1, "库结构没再变")

    print("三、对不上的只告警，不动表")
    db = tmp / "b.db"
    con = sqlite3.connect(db)
    # 手建的老表：code 不是必填、right 是 TEXT、多一列 legacy
    con.execute("CREATE TABLE learner (id INTEGER PRIMARY KEY AUTOINCREMENT, code VARCHAR(255) UNIQUE,"
                " name VARCHAR(255), legacy TEXT)")
    con.execute("CREATE TABLE mastery (id INTEGER PRIMARY KEY AUTOINCREMENT, learner VARCHAR(255) NOT NULL,"
                " point VARCHAR(255) NOT NULL, right TEXT)")
    con.execute("INSERT INTO learner(code, name, legacy) VALUES('me', '我', 'x')")
    con.executemany("INSERT INTO mastery(learner, point, right) VALUES(?, ?, ?)",
                    [("me", "noun", "3"), ("me", "noun", "4")])     # 重复：唯一索引建不起来
    con.commit()
    con.close()
    before = schema(db)
    must = NEW.replace("  字段 note 文本 备注", "  字段 note 文本 备注\n  字段 must 文本 必填 必须")
    r = migrate_additive(db, must)
    w = "\n".join(r["warnings"])
    check("learner.code" in w and "NOT NULL" in w, "列的必填不一样：告警")
    check("mastery.right" in w and "TEXT" in w and "INTEGER" in w, "列类型不一样：告警")
    check("learner.legacy" in w and "没删" in w, "库里多出来的列：告警，没删")
    check("mastery.must" in w and "必填又没有默认值" in w, "必填又没默认值的新列：告警，没加")
    check("ux_mastery_learner_point" in w and "重复" in w, "唯一索引撞上重复行：告警")
    check("mastery.must" not in r["columns"] and "ux_mastery_learner_point" not in r["indexes"],
          "加不了的没算进补了的")
    after = schema(db)
    check(all(after[k] == v for k, v in before.items() if k != "learner" and k != "mastery")
          and "legacy" in after["learner"] and "right TEXT" in after["mastery"],
          "已有的列一列没改、没删")
    check(q(db, "SELECT count(*) FROM mastery") == [(2,)] and
          q(db, "SELECT legacy FROM learner") == [("x",)], "数据一条没动（重复行也留着）")
    r2 = migrate_additive(db, must)
    check(r2["tables"] == r2["columns"] == r2["indexes"] == [] and r2["warnings"] == r["warnings"],
          "再跑一次：什么都不补，警告一样")

    print("四、等价的索引已经有了")
    db = make_db(tmp / "c.db", OLD)
    con = sqlite3.connect(db)
    con.execute("CREATE UNIQUE INDEX ux_mastery ON mastery(learner, point)")
    con.commit()
    con.close()
    r = migrate_additive(db, NEW)
    check("ux_mastery_learner_point" not in r["indexes"], f"同列同唯一性的 ux_mastery 在，不重复建：{r['indexes']}")
    names = [n for (n,) in q(db, "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='mastery'"
                                 " AND name NOT LIKE 'sqlite_%'")]
    check(sorted(names) == ["idx_mastery_learner", "ux_mastery"], f"mastery 上的索引：{names}")
    missing = tmp / "none.db"
    check(migrate_additive(missing, NEW)["tables"] == [] and not missing.exists(), "库不存在：不建库、不报错")

    print("五、实体的「唯一」行")
    sql = render_sql(NEW, strict=True)
    check("CREATE UNIQUE INDEX IF NOT EXISTS ux_mastery_learner_point\n    ON mastery(learner, point);" in sql,
          "渲染成唯一索引")
    for bad, why in (("实体 t x\n  字段 a 文本\n  唯一 a\n结束\n", "只写一列"),
                     ("实体 t x\n  字段 a 文本\n  唯一 a b\n结束\n", "不存在的列")):
        try:
            render_sql(bad, strict=True)
            check(False, f"{why}：没报错")
        except EntitySyntaxError as e:
            check(True, f"{why}：报错（{str(e)[:40]}）")

    print("六、开关")
    for name, routes, on in (("on", "服务 8100\n\n迁移 只加\n\n接口 POST /x\n  返回 1\n结束\n", True),
                             ("off", "服务 8100\n\n接口 POST /x\n  返回 1\n结束\n", False),
                             ("inner", "接口 POST /x\n  迁移 只加\n  返回 1\n结束\n", False)):
        proj = tmp / name
        for d in ("entities", "routes"):
            (proj / d).mkdir(parents=True)
        (proj / "entities" / "m.entity").write_text(NEW, encoding="utf-8")
        (proj / "routes" / "r.zs").write_text(routes, encoding="utf-8")
        make_db(proj / "app.db", OLD)
        s0 = schema(proj / "app.db")
        msg = ensure_db(proj)
        s1 = schema(proj / "app.db")
        check(switch_on(proj / "routes") == on, f"{name}：开关读出来是 {on}")
        if on:
            check("score" in s1 and "补建了表：score" in msg, f"{name}：ensure_db 补了表：{msg.splitlines()[-1]}")
        else:
            check(s1 == s0 and "没动" in msg, f"{name}：库原样不动（{msg.strip()}）")
    # 第一次跑（库不存在）照旧建库
    (tmp / "on" / "app.db").unlink()
    msg = ensure_db(tmp / "on")
    check("建了" in msg and "score" in schema(tmp / "on" / "app.db"), "库不存在时照旧按实体建")

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
