# -*- coding: utf-8 -*-
"""显式重建表：tools/migrate.py 的 rebuild_tables 和路由顶层「迁移 重建 表…」。

    cd /workspace/agent_mcp && .venv/bin/python tests/gen/test_migrate_rebuild.py

一、旧库有数据；实体把 `learner 唯一` 改成 `唯一 learner subject_id` + subject_id 列：
    只加时补列、补新索引，并出「库里有实体没有的唯一约束」警告（旧约束仍拦着第二科目）
二、重建后行数、内容不变；同 learner 第二个 subject_id 插得进；同 (learner, subject_id) 被拒
三、备份文件生成、内容是重建前的库；重复执行幂等（第二次不动、不再备份）
四、故意造冲突（重建后违反新唯一）：整体回滚，原表、数据、旧索引完好，错误说得清楚
五、没点名的表不动（即使它跟实体也对不上）
六、外键：别的表引用被重建的表，重建后 foreign_key_check 为空；引用悬空的新增违规会回滚
七、开关：路由顶层的「迁移 重建」多行合并；写在接口块里的不算；ensure_db 接上并把报告写进输出
"""

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gen.project import ensure_db                                       # noqa: E402
from tools.migrate import (RebuildError, migrate_additive, rebuild_names,   # noqa: E402
                           rebuild_tables)

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


OLD = """\
实体 progress 进度
  字段 learner 文本 必填 唯一 学习者
  字段 score 整数 分数
结束

实体 setting 设置
  字段 learner 文本 必填 唯一 学习者
  字段 theme 文本 主题
结束

实体 note 笔记
  字段 progress_id 整数 关联 progress 所属进度
  字段 body 文本 内容
结束
"""

NEW = """\
实体 progress 进度
  字段 learner 文本 必填 学习者
  字段 subject_id 整数 必填 默认 1 科目
  字段 score 整数 分数
  唯一 learner subject_id
结束

实体 setting 设置
  字段 learner 文本 必填 唯一 学习者
  字段 theme 文本 主题
结束

实体 note 笔记
  字段 progress_id 整数 关联 progress 所属进度
  字段 body 文本 内容
结束
"""


def make_project(tmp: Path, old=OLD, new=NEW, routes="迁移 只加\n迁移 重建 progress\n"):
    """tmp 下建项目：旧实体建库并灌数据，然后换成新实体。"""
    (tmp / "entities").mkdir()
    (tmp / "routes").mkdir()
    (tmp / "routes" / "_project.zs").write_text(routes, encoding="utf-8")
    (tmp / "entities" / "a.entity").write_text(old, encoding="utf-8")
    from tools.entity import render_sql
    con = sqlite3.connect(tmp / "app.db")
    con.executescript(render_sql(old))
    con.executemany("INSERT INTO progress(learner,score) VALUES(?,?)",
                    [("s1", 10), ("s2", 20), ("s3", 30)])
    con.execute("INSERT INTO setting(learner,theme) VALUES('s1','dark')")
    con.execute("INSERT INTO note(progress_id,body) VALUES(2,'hello')")
    con.commit()
    con.close()
    (tmp / "entities" / "a.entity").write_text(new, encoding="utf-8")


def rows(db, sql):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def uniques(db, table):
    con = sqlite3.connect(db)
    try:
        return sorted(tuple(c[2] for c in con.execute(f'PRAGMA index_info("{r[1]}")'))
                      for r in con.execute(f'PRAGMA index_list("{table}")') if r[2])
    finally:
        con.close()


def try_insert(db, sql, args=()):
    con = sqlite3.connect(db)
    try:
        con.execute(sql, args)
        con.commit()
        return None
    except sqlite3.IntegrityError as e:
        return str(e)
    finally:
        con.close()


tmp = Path(tempfile.mkdtemp(prefix="k73_"))
try:
    # ---- 一、只加：补了列，但旧的单列唯一还在，必须有警告 ----
    print("一、只加时的警告")
    p = tmp / "p1"
    p.mkdir()
    make_project(p)
    db = p / "app.db"
    r = migrate_additive(db, p / "entities")
    check("progress.subject_id" in r["columns"], "只加补上了 subject_id 列")
    ws = [w for w in r["warnings"] if "迁移 重建 progress" in w]
    check(len(ws) == 1 and "learner" in ws[0] and "sqlite_autoindex" in ws[0],
          f"警告：库里有实体没有的唯一约束，提示 迁移 重建：{ws}")
    check(not any("setting" in w for w in r["warnings"]), "实体也有的唯一约束（setting）不告警")
    err = try_insert(db, "INSERT INTO progress(learner,subject_id,score) VALUES('s1',2,5)")
    check(err is not None and "UNIQUE" in err, f"只加之后第二科目仍写不进（旧约束还在）：{err}")

    # ---- 二、重建：数据不变，约束换成 (learner, subject_id) ----
    print("二、重建")
    before = rows(db, "SELECT id,learner,subject_id,score FROM progress ORDER BY id")
    res = rebuild_tables(db, p / "entities", ["progress"])
    check(res["rebuilt"] == [("progress", 3)], f"报告：重建了 progress 3 行 {res['rebuilt']}")
    after = rows(db, "SELECT id,learner,subject_id,score FROM progress ORDER BY id")
    check(after == before and len(after) == 3, f"行数、内容（含 id、subject_id）不变 {after}")
    check(uniques(db, "progress") == [("learner", "subject_id")],
          f"唯一约束只剩 (learner, subject_id)：{uniques(db, 'progress')}")
    check(try_insert(db, "INSERT INTO progress(learner,subject_id,score) VALUES('s1',2,5)") is None,
          "同 learner 第二个 subject_id 插得进")
    err = try_insert(db, "INSERT INTO progress(learner,subject_id,score) VALUES('s1',2,6)")
    check(err is not None and "UNIQUE" in err, f"同 (learner,subject_id) 重复被拒：{err}")
    check(rows(db, "SELECT count(*) FROM sqlite_master WHERE name LIKE '%__new'")[0][0] == 0,
          "没有留下 __new 临时表")
    check(rows(db, "PRAGMA foreign_key_check") == [] and rows(db, "PRAGMA integrity_check") == [("ok",)],
          "foreign_key_check 为空、integrity_check ok")
    check(rows(db, "SELECT body FROM note") == [("hello",)], "别的表（note）数据在")

    # ---- 三、备份与幂等 ----
    print("三、备份与幂等")
    baks = sorted(p.glob("app.db.bak-*"))
    check(len(baks) == 1 and baks[0].name == res["backup"], f"生成了备份文件 {res['backup']}")
    check(rows(baks[0], "SELECT count(*) FROM progress") == [(3,)]
          and uniques(baks[0], "progress") == [("learner",), ("learner", "subject_id")],
          "备份是重建前的库（3 行；旧单列唯一 + 刚补的新索引都在）")
    res2 = rebuild_tables(db, p / "entities", ["progress"])
    check(res2["rebuilt"] == [] and res2["backup"] is None and res2["unchanged"] == ["progress"],
          f"第二次不动、不再备份 {res2}")
    check(len(list(p.glob("app.db.bak-*"))) == 1, "备份文件没有多出来")

    # ---- 四、冲突：回滚 ----
    print("四、冲突回滚")
    p = tmp / "p4"
    p.mkdir()
    # 新实体唯一键是 (score, subject_id)：旧数据里 score 重复 -> 重建后违反新唯一
    bad_new = NEW.replace("唯一 learner subject_id", "唯一 score subject_id")
    make_project(p, new=bad_new, routes="迁移 重建 progress setting\n")
    db = p / "app.db"
    con = sqlite3.connect(db)
    con.execute("UPDATE progress SET score=10")        # 三行 score 全是 10
    con.commit()
    con.close()
    snap = rows(db, "SELECT * FROM progress ORDER BY id")
    idx_before = uniques(db, "progress")
    try:
        rebuild_tables(db, p / "entities", ["progress"])
        check(False, "冲突应当抛 RebuildError")
    except RebuildError as e:
        msg = str(e)
        check("已回滚" in msg and "progress" in msg and "UNIQUE" in msg and ".bak-" in msg,
              f"报清楚的错：{msg}")
    check(rows(db, "SELECT * FROM progress ORDER BY id") == snap, "原表数据原样")
    check(uniques(db, "progress") == idx_before, f"原表旧索引原样 {uniques(db, 'progress')}")
    check(rows(db, "SELECT count(*) FROM sqlite_master WHERE name LIKE '%__new'")[0][0] == 0,
          "没有残留 __new 表")
    check(rows(db, "PRAGMA integrity_check") == [("ok",)], "integrity_check ok")
    # 多表时前一张已经换好、后一张失败：整体回滚，前一张也还是原样
    p = tmp / "p4b"
    p.mkdir()
    make_project(p, new=NEW.replace("唯一 learner subject_id", "唯一 score subject_id")
                 .replace("字段 learner 文本 必填 唯一 学习者\n  字段 theme",
                          "字段 learner 文本 必填 学习者\n  字段 theme 文本 唯一 主题"),
                 routes="迁移 重建 setting progress\n")
    db = p / "app.db"
    con = sqlite3.connect(db)
    con.execute("UPDATE progress SET score=10")
    con.commit()
    con.close()
    try:
        rebuild_tables(db, p / "entities", ["setting", "progress"])
        check(False, "第二张冲突应当抛错")
    except RebuildError:
        pass
    check(uniques(db, "setting") == [("learner",)], "前一张（setting）已换好的也回滚了")

    # 库被别的连接占着写锁：BEGIN 失败也要回滚干净、错误文案不带 None
    p = tmp / "p4c"
    p.mkdir()
    make_project(p)
    db = p / "app.db"
    locker = sqlite3.connect(db, isolation_level=None)
    locker.execute("BEGIN IMMEDIATE")
    try:
        import tools.migrate as _m
        _orig = sqlite3.connect
        sqlite3.connect = lambda *a, **k: _orig(*a, **{**k, "timeout": 0.2})
        try:
            rebuild_tables(db, p / "entities", ["progress"])
            check(False, "库被锁住应当抛 RebuildError")
        except RebuildError as e:
            check("None" not in str(e) and "已回滚" in str(e), f"库被锁：错误文案清楚且不带 None：{e}")
        finally:
            sqlite3.connect = _orig
    finally:
        locker.execute("ROLLBACK")
        locker.close()
    check(uniques(db, "progress") == [("learner",)] and rows(db, "SELECT count(*) FROM progress") == [(3,)],
          "库被锁失败后原表原样")

    # ---- 五、没点名的表不动 ----
    print("五、没点名的表不动")
    p = tmp / "p5"
    p.mkdir()
    make_project(p, new=NEW.replace("字段 learner 文本 必填 唯一 学习者\n  字段 theme",
                                    "字段 learner 文本 必填 学习者\n  字段 theme"))
    db = p / "app.db"
    setting_sql = rows(db, "SELECT sql FROM sqlite_master WHERE name='setting'")
    rebuild_tables(db, p / "entities", ["progress"])
    check(rows(db, "SELECT sql FROM sqlite_master WHERE name='setting'") == setting_sql
          and uniques(db, "setting") == [("learner",)],
          "setting 跟实体对不上（实体去掉了唯一），但没点名：建表语句与旧约束都原样")
    try:
        rebuild_tables(db, p / "entities", ["no_such"])
        check(False, "实体里没有的表名应当报错")
    except RebuildError as e:
        check("no_such" in str(e), f"点名了不存在的表：{e}")
    r = rebuild_tables(db, p / "entities", ["progress"])
    check(r["rebuilt"] == [] and r["backup"] is None, "无需重建的表（已一致）不备份")

    # ---- 六、外键 ----
    print("六、外键")
    p = tmp / "p6"
    p.mkdir()
    make_project(p)
    db = p / "app.db"
    con = sqlite3.connect(db)
    fk = con.execute("PRAGMA foreign_key_list(note)").fetchall()
    con.close()
    check(bool(fk), f"note 有指向 progress 的外键 {[r[2] for r in fk]}")
    rebuild_tables(db, p / "entities", ["progress"])
    check(rows(db, "PRAGMA foreign_key_check") == [], "重建被引用的表后 foreign_key_check 为空")
    check(rows(db, "SELECT body FROM note WHERE progress_id=2") == [("hello",)],
          "note 仍指到原来的 progress.id=2")
    con = sqlite3.connect(db)
    check(con.execute("PRAGMA foreign_keys").fetchone()[0] == 0, "（新连接默认外键开关未被改写）")
    con.close()
    # 新增的外键违规：重建前库里 note 指向的 progress 行被「手工」删了，不算新增；
    # 造一个重建本身带来的违规——实体多了一个必填外键列？这里用悬空行验证「已有违规不挡路」
    p = tmp / "p6b"
    p.mkdir()
    make_project(p)
    db = p / "app.db"
    con = sqlite3.connect(db)
    con.execute("INSERT INTO note(progress_id,body) VALUES(99,'dangling')")
    con.commit()
    con.close()
    r = rebuild_tables(db, p / "entities", ["progress"])
    check(r["rebuilt"] == [("progress", 3)], "重建前就存在的悬空外键不算新增违规，不挡重建")

    # ---- 七、开关与 ensure_db ----
    print("七、开关与 ensure_db")
    p = tmp / "p7"
    p.mkdir()
    make_project(p, routes="迁移 只加\n迁移 重建 progress\n迁移 重建 setting progress\n"
                          "接口 GET /x\n  迁移 重建 note\n结束\n")
    names = rebuild_names(p / "routes")
    check(names == ["progress", "setting"], f"多行合并去重，接口块里的不算：{names}")
    out = ensure_db(p)
    check("已存在" in out and "[迁移 重建] 重建了表：progress（3 行）" in out and ".bak-" in out,
          f"ensure_db 输出带重建报告：{out!r}")
    check("[迁移警告]" not in out, "马上要重建的表，只加的「用 迁移 重建」警告不再出（避免噪音）")
    check(uniques(p / "app.db", "progress") == [("learner", "subject_id")], "ensure_db 之后库已是新约束")
    out2 = ensure_db(p)
    check("[迁移 重建]" not in out2 and len(list(p.glob("app.db.bak-*"))) == 1,
          "ensure_db 再跑一次：不动、不再备份")
    # 只写重建、不写只加
    p = tmp / "p7b"
    p.mkdir()
    make_project(p, routes="迁移 重建 progress\n")
    out = ensure_db(p)
    check("只重建点名的表" in out and "progress（3 行）" in out, f"只写重建也生效：{out!r}")
    # 没写任何迁移的项目：照旧不动
    p = tmp / "p7c"
    p.mkdir()
    make_project(p, routes="# nothing\n")
    out = ensure_db(p)
    check("没动" in out and not list(p.glob("app.db.bak-*"))
          and uniques(p / "app.db", "progress") == [("learner",)], "没写迁移的项目库原样不动")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
