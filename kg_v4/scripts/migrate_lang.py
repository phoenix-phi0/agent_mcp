# -*- coding: utf-8 -*-
"""account_user 加 lang 列（界面语言，默认 'zh'）——手写安全迁移，可重复执行。

    用法：.venv/bin/python kg_v4/scripts/migrate_lang.py [库文件]
          库文件不给就是项目根的 app.db

规则（照实体字段 lang 文本 必填 默认 zh）：
  · 已有列就直接退出（重复执行、续跑都安全）；
  · 先备份（<库>.bak_lang_<时间戳>），再在显式事务里 ALTER TABLE——sqlite3 默认
    不给 DDL 开事务（ALTER 一执行就落盘），必须 isolation_level=None + BEGIN，
    失败才真能 ROLLBACK 撤掉加列；备份另外保留，人工可回滚；
  · 迁完校验：行数不变、每行 lang 都在 ('zh','ja') 里，校验不过报非零退出码。

正式库上线时在停服窗口执行：先停服务 → 跑本脚本 → 看输出校验 → 起服务。
"""
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(argv) -> int:
    db = Path(argv[1]) if len(argv) > 1 else ROOT / "kg_v4" / "app.db"
    if not db.is_file():
        print(f"[出错] 库不存在：{db}")
        return 1
    # isolation_level=None：sqlite3 默认只给 DML 开隐式事务，ALTER TABLE 这种 DDL
    # 一执行就自动落盘，rollback 撤不回——显式 BEGIN 了才真能回滚
    con = sqlite3.connect(db, isolation_level=None)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(account_user)")}
        if not cols:
            print("[出错] 没有 account_user 表，不像 kg_v4 的库：", db)
            return 1
        if "lang" in cols:
            print("lang 列已存在，不用再迁（可重复执行）")
            return 0
        bak = db.with_name(db.name + ".bak_lang_" + time.strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(db, bak)
        print(f"已备份到 {bak}")
        before = con.execute("SELECT COUNT(*) FROM account_user").fetchone()[0]
        try:
            con.execute("BEGIN")
            con.execute("ALTER TABLE account_user ADD COLUMN lang TEXT NOT NULL DEFAULT 'zh'")
            n, bad = con.execute(
                "SELECT COUNT(*), SUM(lang NOT IN ('zh','ja')) FROM account_user").fetchone()
            if n != before or (bad or 0) != 0:
                raise RuntimeError(f"校验不过：{before}→{n} 行，lang 非法值 {bad} 个")
            con.execute("COMMIT")
        except Exception as e:
            con.execute("ROLLBACK")
            print(f"[出错] 已回滚，库没动：{e}")
            print(f"如需回滚，从备份恢复：cp {bak} {db}")
            return 1
        print(f"迁移完成：{n} 个账号都有 lang（默认 zh），行数不变，校验通过")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
