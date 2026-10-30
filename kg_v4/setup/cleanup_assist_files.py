#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""kg_v4 教师助手附件清理（M4-P2，D8）。手动或 cron 跑；DSL 没有删文件的动词，所以写在脚本里。

用法（解释器用仓库的 .venv）：
  .venv/bin/python kg_v4/setup/cleanup_assist_files.py [--db kg_v4/app.db] [--days 30] [--keep 20] [--apply]

默认 dry-run：只打印要删的行和文件，不改库、不删文件；加 --apply 才真删。
要删的行（attached=1 的一律跳过）：
  1. status=deleted 的全部；
  2. status=ok 且 last_used_at 早于 --days 天前的；
  3. 每位老师每个科目 status=ok 的行超过 --keep 个时，按 last_used_at 从旧到新（同时间 id 小的先）删到只剩 --keep 个
     （attached=1 的那行计数但不删）。
--apply：先在一个事务里删行，提交后再删磁盘文件；某行的 path 已没有任何 teacher_assist_file 行引用，并且
textbook_import_* 表里没有叫 path / file_path 的列引用同一路径时才删文件；文件不存在不算错。
上传文件的相对路径（uploads/…）相对 --db 所在目录。只读写 teacher_assist_file 这一张表。正式库上跑之前照例先备份。
"""
import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path


def pick_rows(con, days, keep, now):
    """→ (要删的行 [dict], 跳过的当前附件数)。"""
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "select id, teacher, subject_id, name, path, status, attached, last_used_at"
        " from teacher_assist_file order by id")]
    skipped = sum(1 for r in rows if r["attached"] == 1)
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    chosen = {}
    for r in rows:
        if r["attached"] == 1:
            continue
        if r["status"] == "deleted":
            chosen[r["id"]] = r
        elif r["status"] == "ok" and (r["last_used_at"] or "") < cutoff:
            chosen[r["id"]] = r
    groups = {}
    for r in rows:
        if r["status"] == "ok":
            groups.setdefault((r["teacher"], r["subject_id"]), []).append(r)
    for g in groups.values():
        left = [r for r in g if r["id"] not in chosen]
        over = len(left) - keep
        if over <= 0:
            continue
        old_first = sorted(left, key=lambda r: (r["last_used_at"] or "", r["id"]))
        for r in old_first:
            if over <= 0:
                break
            if r["attached"] == 1:
                continue
            chosen[r["id"]] = r
            over -= 1
    return sorted(chosen.values(), key=lambda r: r["id"]), skipped


def other_refs(con, path, ignore_ids=()):
    """path 是否还被别处引用（teacher_assist_file 里不在 ignore_ids 里的行，或 textbook_import_* 里的 path / file_path 列）。"""
    for (i,) in con.execute("select id from teacher_assist_file where path=?", (path,)):
        if i not in ignore_ids:
            return True
    tables = [r[0] for r in con.execute(
        "select name from sqlite_master where type='table' and name like 'textbook_import%'")]
    for t in tables:
        for c in [c[1] for c in con.execute('pragma table_info("%s")' % t)]:
            if c in ("path", "file_path") and con.execute(
                    'select 1 from "%s" where "%s"=? limit 1' % (t, c), (path,)).fetchone():
                return True
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="清理教师助手附件（默认 dry-run）")
    ap.add_argument("--db", default="kg_v4/app.db")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--keep", type=int, default=20)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    db = Path(a.db)
    if not db.is_file():
        print("找不到库文件：%s" % db)
        return 1
    base = db.resolve().parent
    con = sqlite3.connect(db)
    try:
        victims, skipped = pick_rows(con, a.days, a.keep, datetime.now())
        files = []
        for r in victims:
            print("行 id=%s teacher=%s subject_id=%s name=%s last_used_at=%s path=%s"
                  % (r["id"], r["teacher"], r["subject_id"], r["name"], r["last_used_at"], r["path"]))
        if not a.apply:
            # 预演：假设这些行都删了，哪些文件会跟着删
            ids = {r["id"] for r in victims}
            seen = set()
            for r in victims:
                p = r["path"]
                if p in seen:
                    continue
                seen.add(p)
                if not other_refs(con, p, ids):
                    files.append(p)
                    print("文件 %s" % p)
            print("将删 %d 行、%d 个文件（跳过当前附件 %d 个）（dry-run，没有改动；加 --apply 执行）"
                  % (len(victims), len(files), skipped))
            return 0
        con.execute("begin")
        try:
            for r in victims:
                con.execute("delete from teacher_assist_file where id=?", (r["id"],))
            con.commit()
        except Exception:
            con.rollback()
            raise
        done = set()
        n_files = 0
        for r in victims:
            p = r["path"]
            if not p or p in done:
                continue
            done.add(p)
            if other_refs(con, p):
                continue
            f = Path(p)
            f = f if f.is_absolute() else base / p
            try:
                f.unlink()
                n_files += 1
                print("删文件 %s" % p)
            except FileNotFoundError:
                pass
        print("删了 %d 行、%d 个文件（跳过当前附件 %d 个）" % (len(victims), n_files, skipped))
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
