# -*- coding: utf-8 -*-
"""assist_file.csv统计 的行为锁定。

K195：约定曾改为「按行按逗号切、不用 读CSV」——读CSV 按 UTF-8 读文件，GBK 文件抛解码错，「调用 … 出错时」接不住，
存附件会整个失败（K195 fix2 曾改成 读CSV，GBK 用例直接崩），本测试的 GBK 用例就是防这个回归。
K196：引擎 data 包新增按**字符串**解析的 解析CSV文本，csv统计 改用它（text 已由 读文档 解码，GBK 不会再崩），
按 CSV 规则处理引号、引号内逗号 / 换行、转义引号。普通 csv（无引号）的 rows、stats 必须与 K195 版逐字一致
（ORDINARY 里的期望值是用 K195 版 ddadfb5 的 kg_v4 跑出来的原文）。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_k195_csv_stats.py
    KG_V4_SRC=/别的/kg_v4 … 可拿别的版本（如基线）跑同一组用例对照
    … --ordinary-only        只跑普通 csv 逐字一致那一段（拿基线跑时用：基线不处理引号，其余段本来就不过）

经 存附件 走 csv统计，读回 rows 和库里的 stats；>200 行的再经 取附件文本 看【资料】只给前 200 行。离线，不调模型。
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
    print(("  ✓ " if ok else "  ✗ ") + msg + ("" if ok or detail is None else f"\n      {detail!r}"))


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


def stats_of(name, data, want_text=False):
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
    if not want_text:
        return (r or {}).get("rows"), st, err
    t, err2 = K.call(_eng[0], "assist_file", "取附件文本", dict(current_user="t1", file_id=str((r or {}).get("file_id", ""))), f"c{next(_seq)}")
    K.settle()
    return (r or {}).get("rows"), st, err, (t or {}), err2


# 普通 csv（无引号）：期望值是 K195 版（ddadfb5，按行按逗号切）跑出来的原文，K196 改用 解析CSV文本 后必须逐字一致
ORDINARY = [
    ("s.csv", "姓名,分数,备注\n甲,80,\n乙,90.5,好\n丙,,好\n", 3,
     "共 3 行，3 列：姓名、分数、备注\n姓名：文本列，缺失 0\n分数：均值 85.25，最低 80，最高 90.5，缺失 1\n备注：文本列，缺失 1"),
    ("crlf.csv", "a,b\r\n1,x\r\n\r\n2,y\r\n", 2,
     "共 2 行，2 列：a、b\na：均值 1.50，最低 1，最高 2，缺失 0\nb：文本列，缺失 0"),
    ("only.csv", "a,b\n", 0, "只有表头，没有数据行：a、b"),
    ("bom.csv", "﻿编号,值\n1,2\n3,4\n", 2,
     "共 2 行，2 列：编号、值\n编号：均值 2.00，最低 1，最高 3，缺失 0\n值：均值 3.00，最低 2，最高 4，缺失 0"),
    ("gbk.csv", "姓名,分数\n甲,80\n乙,90\n".encode("gbk"), 2,
     "共 2 行，2 列：姓名、分数\n姓名：文本列，缺失 0\n分数：均值 85.00，最低 80，最高 90，缺失 0"),
    ("sp.csv", "姓名, 分数\n甲, 80\n乙, 90\n", 2,
     "共 2 行，2 列：姓名、分数\n姓名：文本列，缺失 0\n分数：均值 85.00，最低 80，最高 90，缺失 0"),
    ("ragged.csv", "a,b,c\n1,2\n3,4,5,6\n,,\n  \n-1.50,x,7\n", 4,
     "共 4 行，3 列：a、b、c\na：均值 0.83，最低 -1.5，最高 3，缺失 1\nb：文本列，缺失 1\nc：均值 6.00，最低 5，最高 7，缺失 2"),
    ("neg.csv", "v,w\n-3,0.10\n-1,0.20\n", 2,
     "共 2 行，2 列：v、w\nv：均值 -2.00，最低 -3，最高 -1，缺失 0\nw：均值 0.15，最低 0.1，最高 0.2，缺失 0"),
    ("wide.csv", ",".join(f"c{i}" for i in range(1, 33)) + "\n" + ",".join(str(i) for i in range(1, 33)) + "\n", 1,
     "共 1 行，32 列：" + "、".join(f"c{i}" for i in range(1, 31)) + "\n"
     + "\n".join(f"c{i}：均值 {i}.00，最低 {i}，最高 {i}，缺失 0" for i in range(1, 31)) + "\n（另有 2 列未列出）"),
    ("trail.csv", "a,b,\n1,2,\n", 1, "共 1 行，3 列：a、b、\na：均值 1.00，最低 1，最高 1，缺失 0\nb：均值 2.00，最低 2，最高 2，缺失 0\n：文本列，缺失 1"),
]


def ordinary():
    print("一、普通 csv（无引号）：rows、stats 与 K195 版逐字一致")
    for name, data, want_rows, want_st in ORDINARY:
        rows, st, err = stats_of(name, data)
        check(err in ("", None) and rows == want_rows and st == want_st, f"{name}：rows={want_rows}，stats 逐字", (rows, st, err))


def quoted():
    print("二、带引号（K196：按 CSV 规则解析）")
    rows, st, err = stats_of("q.csv", '姓名,分数\n"张, 三",80\n"李四",90\n')
    check(err in ("", None) and rows == 2 and st == "共 2 行，2 列：姓名、分数\n姓名：文本列，缺失 0\n分数：均值 85.00，最低 80，最高 90，缺失 0",
          "引号内逗号：不错列，分数列仍是数值列", (rows, st, err))
    rows, st, err = stats_of("nl.csv", '姓名,备注,分数\n张三,"第一行\n第二行",80\n李四,"好",90\n')
    check(err in ("", None) and rows == 2 and st == "共 2 行，3 列：姓名、备注、分数\n姓名：文本列，缺失 0\n备注：文本列，缺失 0\n分数：均值 85.00，最低 80，最高 90，缺失 0",
          "引号内换行：不拆行（rows=2）", (rows, st, err))
    rows, st, err = stats_of("esc.csv", '说明,值\n"他说""好""",1\n"a,""b""",3\n')
    check(err in ("", None) and rows == 2 and st == "共 2 行，2 列：说明、值\n说明：文本列，缺失 0\n值：均值 2.00，最低 1，最高 3，缺失 0",
          '转义引号 ""：不错列', (rows, st, err))
    rows, st, err = stats_of("qh.csv", '"姓名","总分, 满分100"\n甲,80\n')
    check(err in ("", None) and rows == 1 and st.startswith("共 1 行，2 列：姓名、总分, 满分100\n"), "表头带引号和逗号：列名完整", (rows, st, err))

    print("三、GBK、BOM、表头带空格、只有表头（带引号）")
    rows, st, err = stats_of("gbkq.csv", '姓名,评语,分数\n张三,"好, 很好",80\n李四,"一般\n还行",70\n'.encode("gbk"))
    check(err in ("", None) and rows == 2 and st == "共 2 行，3 列：姓名、评语、分数\n姓名：文本列，缺失 0\n评语：文本列，缺失 0\n分数：均值 75.00，最低 70，最高 80，缺失 0",
          "GBK + 引号内逗号 / 换行：不崩、列正确", (rows, st, err))
    rows, st, err = stats_of("bomq.csv", '﻿"编号",值\n1,"2"\n')
    check(err in ("", None) and rows == 1 and st == "共 1 行，2 列：编号、值\n编号：均值 1.00，最低 1，最高 1，缺失 0\n值：均值 2.00，最低 2，最高 2，缺失 0",
          "BOM + 带引号的首列名：列名干净，数值列", (rows, st, err))
    rows, st, err = stats_of("spq.csv", ' 姓名 , "分 数" \n 甲 , " 80 "\n')
    check(err in ("", None) and rows == 1 and st == "共 1 行，2 列：姓名、分 数\n姓名：文本列，缺失 0\n分 数：均值 80.00，最低 80，最高 80，缺失 0",
          "表头和格子带空格（逗号后有空格再开引号也认）：去首尾空白", (rows, st, err))
    rows, st, err = stats_of("onlyq.csv", '"a, x",b\n\n')
    check(err in ("", None) and rows == 0 and st == "只有表头，没有数据行：a, x、b", "只有表头（带引号）", (rows, st, err))

    print("四、坏格式不崩")
    rows, st, err = stats_of("bad.csv", 'a,b\n1,2\n"没闭合,3\n')
    check(err in ("", None) and rows == 2 and st.startswith("共 2 行，2 列：a、b\n") and "\n（注意：CSV 格式有问题" in st,
          "引号没闭合：照常存，stats 末尾带「（注意：…）」", (rows, st, err))


def big():
    print("五、超过 200 行：【资料】只给前 200 行，统计按全部行")
    data = "序号,分数\n" + "".join(f"{i},{i}\n" for i in range(1, 251))
    rows, st, err, t, err2 = stats_of("big.csv", data, want_text=True)
    check(err in ("", None) and rows == 250 and st == "共 250 行，2 列：序号、分数\n序号：均值 125.50，最低 1，最高 250，缺失 0\n分数：均值 125.50，最低 1，最高 250，缺失 0",
          "统计按全部 250 行", (rows, st, err))
    lines = (t.get("text") or "").split("\n")
    check(err2 in ("", None) and t.get("mode") == "csv" and str(t.get("truncated")) == "1" and len(lines) == 202
          and lines[0] == "序号,分数" and lines[200] == "200,200" and lines[201] == "（共 250 行，只给了前 200 行；统计见上面，是按全部行算的）"
          and t.get("stats") == st, "取附件文本：表头 + 前 200 行 + 提示行，truncated=1，stats 同库里", (t.get("mode"), t.get("truncated"), len(lines), lines[-2:], err2))
    data = '序号,备注\n' + "".join(f'{i},"第{i}条, 带逗号"\n' for i in range(1, 231))
    rows, st, err = stats_of("bigq.csv", data)
    check(err in ("", None) and rows == 230 and st == "共 230 行，2 列：序号、备注\n序号：均值 115.50，最低 1，最高 230，缺失 0\n备注：文本列，缺失 0",
          "230 行带引号：统计按全部行、不错列", (rows, st, err))


def main():
    print(f"kg_v4 源：{SRC}")
    ordinary()
    if "--ordinary-only" not in sys.argv:
        quoted()
        big()
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
