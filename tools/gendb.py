# -*- coding: utf-8 -*-
"""从 .entity 生成建表 SQL，可选直接建库。

    py -m tools.gendb                   看看会生成什么，不写文件
    py -m tools.gendb --write           写到 queries/_schema.sql
    py -m tools.gendb --create          顺带建库
    py -m tools.gendb --create --demo   建库并塞假数据
    py -m tools.gendb --check           只校验 .entity，不生成

默认读 entities/ 下所有 .entity，库落在 workspace/japanese/学习.db。

## 为什么默认不写文件

生成的 SQL 带 DROP TABLE，跑错一次数据就没了。默认只打印，看清楚了再
加 --write 或 --create——这个顺序是给「改了字段名重新生成」那种场合留的
后悔余地。
"""

import argparse
import random
import sqlite3
import sys
from pathlib import Path

from . import packs
from .entity import EntitySyntaxError, check, parse, render_db, validate

ROOT = Path(__file__).resolve().parent.parent
ENTITY_DIR = ROOT / "entities"
SCHEMA_OUT = ROOT / "queries" / "_schema.sql"
DEFAULT_DB = packs.DATA_ROOT / "workspace" / "japanese" / "学习.db"

# 假数据用的课程和考点，跟真题库对得上
课程表 = ["doushi_01", "doushi_02", "fukushi_01", "keiyoshi_01"]
考点表 = ["词义", "汉字书写"]


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


def tables_of(con: sqlite3.Connection) -> list[str]:
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
    # 外键在脚本里已经 PRAGMA 开了，但那只对这个连接有效——应用侧连接
    # 时要自己再开一次。
    con.executescript(sql)
    con.commit()
    print(f"已建表：{'、'.join(tables_of(con))}")
    con.close()


def seed(db: Path, learner: str = "φ-0", n: int = 60) -> None:
    """塞一批假作答，顺带把错题本和掌握度算出来。

    错题本不是随机生成的，是**从作答流水汇总出来的**——真实链路里就该
    这样。直接塞随机错题的话两张表对不上，试查询时会得出互相矛盾的
    结果，那比没有数据更误导人。
    """
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute(
        "INSERT OR IGNORE INTO learner(code,name,level) VALUES(?,?,?)",
        (learner, "测试用", "N2"))

    错 = {}
    for i in range(n):
        course = random.choice(课程表)
        point = random.choice(考点表)
        q = f"{course}-{random.randint(1, 30):02d}-" \
            f"{'意味' if point == '词义' else '漢字'}"
        correct = 1 if random.random() < 0.7 else 0
        con.execute(
            "INSERT INTO answer(learner,question,course,point,given,"
            "correct,seconds,at) "
            "VALUES(?,?,?,?,?,?,?,datetime('now','localtime',?))",
            (learner, q, course, point, random.choice("ABCD"),
             correct, random.randint(5, 60), f"-{n - i} hours"))

        key = (q, course, point)
        if correct:
            # 答对了减一次，归零就不再是错题——跟真实逻辑一致
            if key in 错:
                错[key] -= 1
                if 错[key] <= 0:
                    del 错[key]
        else:
            错[key] = 错.get(key, 0) + 1

    for (q, course, point), times in 错.items():
        con.execute(
            "INSERT OR REPLACE INTO wrong(learner,question,course,point,times) "
            "VALUES(?,?,?,?,?)", (learner, q, course, point, times))

    for point in 考点表:
        row = con.execute(
            "SELECT count(*), sum(correct) FROM answer "
            "WHERE learner=? AND point=?", (learner, point)).fetchone()
        total, right = row[0] or 0, row[1] or 0
        con.execute(
            "INSERT OR REPLACE INTO mastery(learner,node,right_count,total,"
            "mastered) VALUES(?,?,?,?,?)",
            (learner, point, right, total,
             int(total >= 8 and right / max(total, 1) >= 0.8)))

    con.commit()
    print(f"已塞 {n} 条作答，{len(错)} 道错题（学习者 {learner}）")
    con.close()


def main() -> int:
    p = argparse.ArgumentParser(description="从 .entity 生成建表 SQL")
    p.add_argument("--entities", default=str(ENTITY_DIR))
    p.add_argument("--out", default=str(SCHEMA_OUT))
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--check", action="store_true", help="只校验，不生成")
    p.add_argument("--write", action="store_true", help="把 SQL 写进文件")
    p.add_argument("--create", action="store_true", help="建库（隐含 --write）")
    p.add_argument("--demo", action="store_true", help="建完塞假数据")
    p.add_argument("--learner", default="φ-0")
    args = p.parse_args()

    entities = load(Path(args.entities))

    if args.check:
        for f in sorted(Path(args.entities).glob("*.entity")):
            print(f"── {f.name} ──")
            print(check(f.read_text(encoding="utf-8")))
        return 0

    problems = validate(entities)
    if problems:
        print(f"校验发现 {len(problems)} 个问题，先修好：")
        for x in problems:
            print("  -", x)
        return 1

    try:
        sql = render_db(entities)["schema.sql"]
    except Exception as e:
        # 模板里的过滤器没注册时报的就是这个。说清楚要改哪儿，
        # 不然「UndefinedError: 转默认值」这种消息很难联想到 render.py
        print(f"渲染失败：{type(e).__name__}: {e}")
        print("如果提示某个过滤器不存在，看 _render_patch.md——"
              "转默认值 / 主键名 这两个要加进 tools/render.py")
        return 1

    print(f"实体 {len(entities)} 个："
          f"{'、'.join(e.name for e in entities)}\n")

    if not (args.write or args.create):
        # 默认只打印：生成的 SQL 带 DROP TABLE，跑错一次数据就没了
        print(sql)
        print("\n（只是预览。加 --write 写文件，--create 直接建库）")
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sql, encoding="utf-8")
    print(f"已写入 {out}")

    if args.create:
        db = Path(args.db)
        if db.is_file() and sys.stdin.isatty():
            ans = input(f"这会删掉 {db} 里的全部数据，确定？(y/N) ")
            if ans.strip().lower() not in ("y", "yes"):
                print("取消")
                return 1
        create(db, sql)
        if args.demo:
            seed(db, args.learner)
        return show(db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
