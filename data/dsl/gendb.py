# -*- coding: utf-8 -*-
"""干净环境的建库脚本：从 .entity 生成 SQL 并建库。

    py gendb.py                      预览生成的 SQL，不写文件
    py gendb.py --check              只校验 .entity
    py gendb.py --create             建库
    py gendb.py --create --demo      建库并塞假数据
    py gendb.py --show               看库里现在有什么

跟主项目的 `py -m tools.gendb` 的区别：

    实体   dsl/entities/ 而不是 mcp/entities/
    SQL    dsl/work/_schema.sql
    库     dsl/work/试验.db

隔离的是数据，不是代码——生成器和模板仍然是主项目那套。改坏了删掉
dsl/work/ 就行，不会碰到教学那边的库。

## 假数据怎么塞

按 entities/试验.entity 里的三张表（author / post / rating）来。

之前这里抄的是教学库的表名，建表成功、塞数据时炸「no such table:
learner」——建表用的是 .entity，塞数据用的是硬编码的另一套表名，两边
本来就对不上。现在改成读实际存在的表：表对不上就跳过并说一句，而不是
抛异常。这个环境的用途是试生成器，不该因为示例数据不匹配就中断。
"""

import argparse
import random
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / "work"

# 往上找到含 tools/entity.py 的目录，把它加进 path
for base in [HERE, *HERE.parents]:
    if (base / "tools" / "entity.py").is_file():
        if str(base) not in sys.path:
            sys.path.insert(0, str(base))
        PROJECT = base
        break
else:
    print("找不到 tools/entity.py。把这个目录放到项目里，或者指定 PYTHONPATH。")
    raise SystemExit(1)

from tools.entity import (EntitySyntaxError, check, parse,   # noqa: E402
                          render_db, validate)


def load(entity_dir: Path) -> list:
    """读目录下所有 .entity，合成一份实体列表。

    多个文件是有意支持的：表多了之后按领域分文件比堆在一个里清楚。
    重名由 validate 拦住。
    """
    if not entity_dir.is_dir():
        raise SystemExit(f"找不到 {entity_dir}")
    files = sorted(entity_dir.glob("*.entity"))
    if not files:
        raise SystemExit(f"{entity_dir} 下没有 .entity 文件")

    entities = []
    for f in files:
        try:
            entities.extend(parse(f.read_text(encoding="utf-8")))
        except EntitySyntaxError as e:
            raise SystemExit(f"{f.name} {e}")
    return entities


def tables_of(con: sqlite3.Connection) -> list:
    cur = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")
    return [r[0] for r in cur.fetchall()]


def show(db: Path) -> int:
    if not db.is_file():
        print(f"库还不存在：{db}")
        return 1
    con = sqlite3.connect(db)
    print(f"\n库 {db}（{db.stat().st_size:,} 字节）")
    names = tables_of(con)
    if not names:
        print("  没有表")
    for t in names:
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        print(f"  {t}　{n} 行　{'、'.join(cols)}")
    con.close()
    return 0


def create(db: Path, sql: str) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    # executescript 会先提交当前事务，DROP + CREATE 一起跑没问题。
    # 脚本里的 PRAGMA 只对这个连接有效——应用侧连接时要自己再开一次。
    con.executescript(sql)
    con.commit()
    print(f"已建表：{'、'.join(tables_of(con))}")
    con.close()


# ----------------------------------------------------------------------
# 假数据
# ----------------------------------------------------------------------

作者表 = [("a01", "小李", "资深"), ("a02", "小王", "熟练"),
          ("a03", "小张", "新手")]
标题词 = ["关于缓存的几点想法", "为什么不用 ORM", "一次线上事故复盘",
          "读《代码整洁之道》", "周报模板", "重构那个老模块"]


def seed(db: Path, n: int = 12) -> None:
    """按 试验.entity 的三张表塞数据。

    表对不上就跳过并说一句，不抛异常——这个环境是用来试生成器的，
    示例数据不匹配不该让流程中断。
    """
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys = ON")
    有的表 = set(tables_of(con))

    需要 = {"author", "post", "rating"}
    缺的 = 需要 - 有的表
    if 缺的:
        print(f"跳过假数据：库里没有 {'、'.join(sorted(缺的))}。"
              f"--demo 是按 entities/试验.entity 写的，"
              f"换了实体定义就得跟着改 seed()")
        con.close()
        return

    for code, name, level in 作者表:
        con.execute(
            "INSERT OR IGNORE INTO author(code,name,level) VALUES(?,?,?)",
            (code, name, level))

    post_ids = []
    for i in range(n):
        code = random.choice(作者表)[0]
        # 标题有 UNIQUE 约束，加个序号免得撞
        cur = con.execute(
            "INSERT INTO post(author,title,body,views,published) "
            "VALUES(?,?,?,?,?)",
            (code, f"{random.choice(标题词)}（{i + 1}）",
             "正文若干。", random.randint(0, 500),
             1 if random.random() < 0.6 else 0))
        post_ids.append(cur.lastrowid)

    # 评分是复合主键（打分人 + 文章），同一个人对同一篇只能有一条。
    # 用 INSERT OR IGNORE 让随机重复自然落掉，正好验证主键生效。
    评分数 = 0
    for _ in range(n * 2):
        code = random.choice(作者表)[0]
        pid = random.choice(post_ids)
        cur = con.execute(
            "INSERT OR IGNORE INTO rating(author,post,score) VALUES(?,?,?)",
            (code, pid, random.randint(1, 5)))
        评分数 += cur.rowcount

    con.commit()
    print(f"已塞 {len(作者表)} 个作者、{n} 篇文章、{评分数} 条评分"
          f"（重复的打分被复合主键挡掉了）")
    con.close()


def main() -> int:
    p = argparse.ArgumentParser(description="干净环境的建库脚本")
    p.add_argument("--entities", default=str(HERE / "entities"))
    p.add_argument("--out", default=str(WORK / "_schema.sql"))
    p.add_argument("--db", default=str(WORK / "试验.db"))
    p.add_argument("--check", action="store_true", help="只校验，不生成")
    p.add_argument("--create", action="store_true", help="建库")
    p.add_argument("--demo", action="store_true", help="建完塞假数据")
    p.add_argument("--show", action="store_true", help="只看库里有什么")
    args = p.parse_args()

    if args.show:
        return show(Path(args.db))

    entity_dir = Path(args.entities)

    if args.check:
        for f in sorted(entity_dir.glob("*.entity")):
            print(f"── {f.name} ──")
            print(check(f.read_text(encoding="utf-8")))
        return 0

    entities = load(entity_dir)
    problems = validate(entities)
    if problems:
        print(f"校验发现 {len(problems)} 个问题，先修好：")
        for x in problems:
            print("  -", x)
        return 1

    try:
        sql = render_db(entities)["schema.sql"]
    except Exception as e:
        print(f"渲染失败：{type(e).__name__}: {e}")
        print("如果提示某个过滤器不存在，转默认值 / 主键名 要加进 tools/render.py")
        return 1

    print(f"实体 {len(entities)} 个：{'、'.join(e.name for e in entities)}\n")

    if not args.create:
        print(sql)
        print("\n（只是预览。加 --create 建库）")
        return 0

    WORK.mkdir(exist_ok=True)
    out = Path(args.out)
    out.write_text(sql, encoding="utf-8")
    print(f"已写入 {out}")

    db = Path(args.db)
    if db.is_file() and sys.stdin.isatty():
        ans = input(f"这会删掉 {db} 里的全部数据，确定？(y/N) ")
        if ans.strip().lower() not in ("y", "yes"):
            print("取消")
            return 1

    create(db, sql)
    if args.demo:
        seed(db)
    return show(db)


if __name__ == "__main__":
    raise SystemExit(main())
