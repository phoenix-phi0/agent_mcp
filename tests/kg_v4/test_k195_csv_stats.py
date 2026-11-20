# -*- coding: utf-8 -*-
"""K195：assist_file.csv统计 的行为锁定（约定 K195 改为与代码一致：按 text 按行按逗号切，不用 读CSV）。
不用 读CSV 的原因：它按 UTF-8 读文件，GBK 文件抛解码错，「调用 … 出错时」接不住，存附件会整个失败——
本测试的 GBK 用例就是防这个回归（K195 fix2 曾按旧约定改成 读CSV，GBK 用例直接崩）。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_k195_csv_stats.py
    KG_V4_SRC=/别的/kg_v4 … 可拿别的版本（如基线）跑同一组用例对照

经 存附件 走 csv统计，读回 rows 和库里的 stats。离线，不调模型。
"""

import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(os.environ.get("KG_V4_SRC") or ROOT / "kg_v4")
sys.path.insert(0, str(ROOT))

from tools.dslagent.packs.dslproj import cases as K, project as P  # noqa: E402

passed = failed = 0


def check(ok, msg, detail=None):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg + ("" if ok or detail is None else f"\n      {detail}"))


tmp = Path(tempfile.mkdtemp(prefix="kg_v4_k195_csv_"))
ws = tmp / "kg_v4"
shutil.copytree(SRC, ws, ignore=K.COPY_IGNORE, symlinks=True)
os.environ["DSL_NOW"] = K.DEFAULT_NOW
SQL = K.build_sql(ws, P.closure(ws, "assist_file"))
(ws / "uploads").mkdir(exist_ok=True)
SUBJECT = ("subject_info", dict(code="math", name="数学", kind="general", caps="x", levels="", qtypes="choice", visibility="public",
                                owner="t1", status="active", created_at="2026-01-01", updated_at="2026-01-01"))
_eng = []
_seq = iter(range(1, 10**6))


def stats_of(name, data):
    db = K.reset_db(ws, SQL)
    con = sqlite3.connect(db)
    con.execute(f"INSERT INTO {SUBJECT[0]}({', '.join(SUBJECT[1])}) VALUES({', '.join('?' * len(SUBJECT[1]))})", list(SUBJECT[1].values()))
    con.commit()
    con.close()
    p = ws / "uploads" / name
    p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    if not _eng:
        _eng.append(K.make_engine(ws))
    r, err = K.call(_eng[0], "assist_file", "存附件", dict(current_user="t1", file_path=f"uploads/{name}", file_name=name, file_ext="csv"), f"c{next(_seq)}")
    K.settle()
    con = sqlite3.connect(db)
    st = (con.execute("select stats from teacher_assist_file").fetchone() or [""])[0]
    con.close()
    return (r or {}).get("rows"), st, err


def main():
    print(f"kg_v4 源：{SRC}")
    print("一、普通 UTF-8 csv（与改前逐字一致）")
    rows, st, err = stats_of("s.csv", "姓名,分数,备注\n甲,80,\n乙,90.5,好\n丙,,好\n")
    check(rows == 3 and st == "共 3 行，3 列：姓名、分数、备注\n姓名：文本列，缺失 0\n分数：均值 85.25，最低 80，最高 90.5，缺失 1\n备注：文本列，缺失 1",
          "rows=3，stats 逐字", (rows, st, err))
    rows, st, err = stats_of("crlf.csv", "a,b\r\n1,x\r\n\r\n2,y\r\n")
    check(rows == 2 and st.startswith("共 2 行，2 列：a、b\na：均值 1.50，最低 1，最高 2，缺失 0"), "CRLF、中间空行跳过", (rows, st, err))
    rows, st, err = stats_of("only.csv", "a,b\n")
    check(rows == 0 and st == "只有表头，没有数据行：a、b", "只有表头", (rows, st, err))

    print("二、带引号的 csv（约定写明不处理引号：不崩、按逗号切）")
    rows, st, err = stats_of("q.csv", '姓名,分数\n"张, 三",80\n"李四",90\n')
    check(err in ("", None) and rows == 2 and st.startswith("共 2 行，2 列：姓名、分数"), "格子里有逗号：照常存，rows=2（列会错位，已知限制）", (rows, st, err))

    print("三、BOM 与 GBK")
    rows, st, err = stats_of("bom.csv", "﻿编号,值\n1,2\n3,4\n")
    check(rows == 2 and st.startswith("共 2 行，2 列：编号、值\n编号：均值 2.00，最低 1，最高 3，缺失 0"), "带 BOM：首列名不带 BOM", (rows, st, err))
    rows, st, err = stats_of("gbk.csv", "姓名,分数\n甲,80\n乙,90\n".encode("gbk"))
    check(err in ("", None) and rows == 2 and "分数：均值 85.00，最低 80，最高 90，缺失 0" in st, "GBK：照常统计（不崩）", (rows, st, err))

    print("四、表头逗号后带空格")
    rows, st, err = stats_of("sp.csv", "姓名, 分数\n甲, 80\n乙, 90\n")
    check(rows == 2 and "共 2 行，2 列：姓名、分数" in st and "分数：均值 85.00，最低 80，最高 90，缺失 0" in st, "列名、格子去首尾空白后照常统计", (rows, st, err))

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
