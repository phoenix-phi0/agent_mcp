# -*- coding: utf-8 -*-
"""kg_v4 教师助手附件（M4-P2）的补充测试：约定用例里造不出的长文本、csv 文件、20 个配额、清理脚本。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_assist_files.py

拷一份 kg_v4 到临时目录，用约定用例的运行器（cases.build_sql / reset_db / call）造数据、调 assist_file 的公开函数；
清理脚本 setup/cleanup_assist_files.py 在临时库上以子进程跑。离线，不调模型。
  类型白名单与原文（xlsx、图片、其他）、10MB 上限、配额 20 个 409、同 path 不建新行
  取附件文本：<=6000 字全文、>6000 字 keyword / headtail、>50000 字只给开头、csv 统计与前 200 行
  挂上 / 移除 / 删除；只读老师 / 学生 / 跨科目
  清理脚本：dry-run 不动、--apply 跳过 attached=1、同 path 被引用不删文件
"""

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "kg_v4"
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


tmp = Path(tempfile.mkdtemp(prefix="kg_v4_assist_files_"))
ws = tmp / "kg_v4"
shutil.copytree(SRC, ws, ignore=K.COPY_IGNORE, symlinks=True)
os.environ["DSL_NOW"] = K.DEFAULT_NOW
SQL = K.build_sql(ws, P.closure(ws, "assist_file"))
(ws / "uploads").mkdir(exist_ok=True)

SUBJECTS = [
    ("subject_info", dict(code="jp_grammar", name="日语语法", kind="language", caps="x", levels="", qtypes="choice", visibility="public",
                          owner="t1", status="active", created_at="2026-01-01", updated_at="2026-01-01")),
    ("subject_info", dict(code="math", name="数学", kind="general", caps="x", levels="", qtypes="choice", visibility="public",
                          owner="t1", status="active", created_at="2026-01-01", updated_at="2026-01-01")),
]


def row(**kw):
    r = dict(teacher="t1", subject_id=1, name="a.txt", ext="txt", size=1, path="uploads/a.txt", pages=0, chars=1, text="x", stats="",
             rows=0, status="ok", attached=0, created_at="2026-01-01 00:00:00", last_used_at="2026-01-01 00:00:00")
    r.update(kw)
    return ("teacher_assist_file", r)


def seed(rows=()):
    db = K.reset_db(ws, SQL)
    con = sqlite3.connect(db)
    try:
        for table, kv in list(SUBJECTS) + list(rows):
            con.execute(f"INSERT INTO {table}({', '.join(kv)}) VALUES({', '.join('?' * len(kv))})", list(kv.values()))
        con.commit()
    finally:
        con.close()
    return db


def q(db, sql, *a):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, a).fetchall()
    finally:
        con.close()


_eng = []
_n = [0]


def run(fn, **args):
    """→ (结果, 报错码, 报错原文)"""
    if not _eng:
        _eng.append(K.make_engine(ws))
    _n[0] += 1
    r, err = K.call(_eng[0], "assist_file", fn, args, f"t{_n[0]}")
    K.settle()
    if isinstance(err, dict):
        return r, str(err.get("code")), str(err.get("error", ""))
    return r, ("" if err in ("", None) else str(err)), ("" if err in ("", None) else str(err))


def put(rel, text, binary=False):
    p = ws / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if binary:
        p.write_bytes(text)
    else:
        p.write_text(text, encoding="utf-8")


def text_row(n, **kw):
    """一个已存好的长文本附件行（text 取前 50000 字）"""
    body = kw.pop("body")
    return row(chars=n, text=body[:50000], attached=1, **kw)


def para(i):
    return "第%d段：" % i + ("关于主题%d的说明。" % i) * 10


ON = dict(current_role="teacher", auth_mode="on")
try:
    print("一、类型白名单与原文")
    db = seed()
    put("uploads/b.xlsx", "x")
    put("uploads/p.png", "x")
    put("uploads/z.zip", "x")
    r, c, e = run("存附件", current_user="t1", file_path="uploads/b.xlsx", file_name="成绩.xlsx", file_ext="xlsx")
    check(c == "400" and e == "不支持 Excel 文件，请在 Excel 里另存为 csv（逗号分隔）再上传", "xlsx：400 另存为 csv 原文", (c, e))
    r, c, e = run("存附件", current_user="t1", file_path="uploads/p.png", file_name="图.PNG", file_ext="")
    check(c == "400" and e == "本期不支持图片，可以把文字贴进对话里，或者传 PDF", "图片（只给文件名、大写扩展名）：400 本期不支持图片", (c, e))
    r, c, e = run("存附件", current_user="t1", file_path="uploads/z.zip", file_name="包.zip", file_ext="zip")
    check(c == "400" and e == "只支持 txt、md、csv、pdf、docx 文件", "其他类型：400 只支持 txt…", (c, e))
    check(q(db, "select count(*) from teacher_assist_file")[0][0] == 0, "被拒的三种都没写库")

    print("二、10MB 上限")
    put("uploads/big.txt", "内容")
    r, c, e = run("存附件", current_user="t1", file_path="uploads/big.txt", file_name="big.txt", file_size=10485761, file_ext="txt")
    check(c == "400" and "10MB" in e, "10485761 字节：400 附件不能超过 10MB", (c, e))
    r, c, e = run("存附件", current_user="t1", file_path="uploads/big.txt", file_name="big.txt", file_size=10485760, file_ext="txt")
    check(c == "" and r and r.get("ok") == 1, "刚好 10485760 字节可以存", (r, c, e))

    print("三、同 path 不建新行、配额 20 个 409")
    db = seed()
    put("uploads/a.txt", "第一个文件")
    r1, c, e = run("存附件", current_user="t1", file_path="uploads/a.txt", file_name="a.txt", file_ext="txt")
    r2, c2, e2 = run("存附件", current_user="t1", file_path="uploads/a.txt", file_name="a.txt", file_ext="txt")
    check(c == "" and c2 == "" and r1["reused"] == 0 and r2["reused"] == 1 and r1["file_id"] == r2["file_id"], "同 path 再传：reused=1、同一个 file_id", (r1, r2))
    check(q(db, "select count(*) from teacher_assist_file")[0][0] == 1, "同 path 再传没有新行")
    db = seed([row(name="f%d.txt" % i, path="uploads/f%d.txt" % i) for i in range(20)])
    put("uploads/new.txt", "新文件")
    r, c, e = run("存附件", current_user="t1", file_path="uploads/new.txt", file_name="new.txt", file_ext="txt")
    check(c == "409" and "20" in e, "已有 20 个 ok：再传新文件 409", (c, e))
    check(q(db, "select count(*) from teacher_assist_file")[0][0] == 20, "409 后没写库")
    r, c, e = run("存附件", current_user="t1", file_path="uploads/f3.txt", file_name="f3.txt", file_ext="txt")
    check(c == "" and r["reused"] == 1, "满 20 个时同 path 重传不占配额（reused=1）", (r, c, e))
    db = seed([row(name="f%d.txt" % i, path="uploads/f%d.txt" % i, status="ok" if i < 19 else "deleted") for i in range(20)])
    r, c, e = run("存附件", current_user="t1", file_path="uploads/new.txt", file_name="new.txt", file_ext="txt")
    check(c == "" and r["ok"] == 1, "deleted 的不占配额：19 个 ok + 1 个 deleted 还能再存", (r, c, e))

    print("四、取附件文本：全文 / keyword / headtail / 只给开头")
    paras = "\n\n".join(para(i) for i in range(1, 61))   # 约 60 段，每段 ~90 字，总长 > 6000
    n = len(paras)
    db = seed([text_row(n, body=paras)])
    r, c, e = run("取附件文本", current_user="t1", file_id=1)
    check(c == "" and r["mode"] == "headtail" and r["truncated"] == 1 and len(r["text"]) <= 6000 and "中间省略，全文 %d 字" % n in r["text"],
          "没有问题：headtail、总长不超过 6000", (c, e, r and (r["mode"], len(r["text"]))))
    check(r["text"].startswith(paras[:4480]) and r["text"].endswith(paras[-1500:]), "headtail：开头 4480 字 + 结尾 1500 字")
    r, c, e = run("取附件文本", current_user="t1", file_id=1, question="主题37，是什么")
    check(c == "" and r["mode"] == "keyword" and "第37段" in r["text"] and r["truncated"] == 1 and len(r["text"]) <= 6100,
          "问题带关键词：keyword 摘到「第37段」", (c, e, r and (r["mode"], r["text"][:80])))
    r, c, e = run("取附件文本", current_user="t1", file_id=1, question="完全无关的zzqq问法")
    check(c == "" and r["mode"] == "headtail", "关键词一段都没命中：退回 headtail", (c, e, r and r["mode"]))
    r, c, e = run("取附件文本", current_user="t1", file_id=1, max_chars=500)
    check(c == "" and len(r["text"]) <= 500 and r["truncated"] == 1, "max_chars=500 往小里要", (c, e, r and len(r["text"])))
    short = "短内容。" * 100
    db = seed([text_row(len(short), body=short)])
    r, c, e = run("取附件文本", current_user="t1", file_id=1)
    check(c == "" and r["mode"] == "full" and r["truncated"] == 0 and r["text"] == short, "<=6000 字：全文")
    big = ("很长的一行文字。" * 8000)[:60000]
    db = seed([text_row(60000, body=big)])
    r, c, e = run("取附件文本", current_user="t1", file_id=1)
    check(c == "" and r["mode"] == "headtail" and r["truncated"] == 1 and "结尾没有保存" in r["text"] and "中间省略" not in r["text"]
          and r["text"].startswith(big[:5940]), ">50000 字：只给开头并说明结尾没保存", (c, e, r and r["text"][-80:]))

    print("五、存附件：>50000 字只存前 50000、csv 统计")
    put("uploads/long.txt", ("很长的一行文字。" * 8000)[:60000])
    db = seed()
    r, c, e = run("存附件", current_user="t1", file_path="uploads/long.txt", file_name="long.txt", file_ext="txt")
    check(c == "" and r["chars"] == 60000, "chars 是全文字数 60000", (c, e, r))
    check(len(q(db, "select text from teacher_assist_file")[0][0]) == 50000, "库里 text 只存前 50000 字")
    put("uploads/s.csv", "姓名,分数,备注\n甲,80,\n乙,90.5,好\n丙,,好\n")
    db = seed()
    r, c, e = run("存附件", current_user="t1", file_path="uploads/s.csv", file_name="成绩.csv", file_ext="csv")
    check(c == "" and r["rows"] == 3 and r["ext"] == "csv", "csv：rows=3", (c, e, r))
    st = q(db, "select stats from teacher_assist_file")[0][0]
    check("共 3 行，3 列：姓名、分数、备注" in st and "分数：均值 85.25，最低 80，最高 90.5，缺失 1" in st and "姓名：文本列，缺失 0" in st,
          "csv 统计：行数、列名、数值列均值/最低/最高/缺失、文本列缺失", st)
    lines = ["编号,值"] + ["%d,%d" % (i, i * 2) for i in range(1, 301)]
    put("uploads/m.csv", "\n".join(lines) + "\n")
    db = seed()
    r, c, e = run("存附件", current_user="t1", file_path="uploads/m.csv", file_name="多行.csv", file_ext="csv")
    r2, c2, e2 = run("取附件文本", current_user="t1", file_id=r["file_id"])
    check(c2 == "" and r2["mode"] == "csv" and r2["truncated"] == 1 and "只给了前" in r2["text"] and "共 300 行" in r2["text"]
          and "\n201," not in r2["text"] and "\n200," in r2["text"], "csv 300 行：mode=csv、只给前 200 行、末尾说明共 300 行", (c2, e2, r2 and r2["text"][-120:]))
    check("均值" in r2["stats"], "csv：统计单独在 stats 里，按全部行算")

    print("六、挂上 / 移除 / 删除")
    db = seed([row(name="a.txt", path="uploads/a.txt", attached=1), row(name="b.txt", path="uploads/b.txt", attached=0)])
    r, c, e = run("挂上附件", current_user="t1", file_id=2)
    check(c == "" and q(db, "select id, attached from teacher_assist_file order by id") == [(1, 0), (2, 1)], "挂上：原来的摘下、新的挂上", (r, c, e))
    r, c, e = run("移除附件", current_user="t1")
    check(c == "" and r["dropped"] == 1 and q(db, "select attached, status from teacher_assist_file where id=2") == [(0, "ok")],
          "移除：只摘下，行还在（status=ok）", (r, c, e))
    r, c, e = run("移除附件", current_user="t1")
    check(c == "" and r["dropped"] == 0, "没有挂着的再移除：dropped=0 不报错", (r, c, e))
    r, c, e = run("删除附件", current_user="t1", file_id=2)
    check(c == "" and q(db, "select status, attached, text, stats from teacher_assist_file where id=2") == [("deleted", 0, "", "")], "删除：软删并清文本", (r, c, e))
    r, c, e = run("删除附件", current_user="t1", file_id=2)
    check(c == "404", "已删除的再删 404", (c, e))
    r, c, e = run("挂上附件", current_user="t1", file_id=2)
    check(c == "404", "已删除的不能挂上 404", (c, e))
    r, c, e = run("取附件文本", current_user="t1", file_id=2)
    check(c == "404", "已删除的取不到文本 404", (c, e))
    r, c, e = run("列附件", current_user="t1")
    check(c == "" and r["total"] == 1 and r["files"][0]["att_name"] == "a.txt", "列附件不含已删除的", (r, c, e))

    print("七、只读老师 / 学生 / 跨科目")
    put("uploads/a.txt", "内容")
    db = seed([row(teacher="t2", attached=1)])
    r, c, e = run("存附件", current_user="t2", file_path="uploads/a.txt", file_name="a.txt", file_ext="txt", subject=2, **ON)
    check(c == "403", "老师没有写权限的科目：存附件 403", (c, e))
    r, c, e = run("存附件", current_user="s1", file_path="uploads/a.txt", file_name="a.txt", file_ext="txt", current_role="student", auth_mode="on")
    check(c == "403", "学生：存附件 403", (c, e))
    r, c, e = run("删除附件", current_user="s1", file_id=1, current_role="student", auth_mode="on")
    check(c == "403", "学生：删除附件 403（不是 404 也不是成功）", (c, e))
    check(q(db, "select status, attached from teacher_assist_file")[0] == ("ok", 1), "被拒后别人的行没动")
    db = seed([row(subject_id=1, attached=1), row(subject_id=2, name="c.txt", path="uploads/c.txt", attached=1)])
    r, c, e = run("取附件文本", current_user="t1", file_id=2)
    check(c == "404", "取别的科目的附件（默认科目 1 下 id=2 是科目 2 的）404", (c, e))
    r, c, e = run("列附件", current_user="t1")
    check(c == "" and r["total"] == 1, "列附件只列当前科目")
    r, c, e = run("存附件", current_user="t1", file_path="uploads/a.txt", file_name="a.txt", file_ext="txt", subject=2)
    check(c == "" and q(db, "select id, attached from teacher_assist_file where subject_id=1") == [(1, 1)], "科目 2 存附件不摘科目 1 挂着的", (c, e))

    print("八、清理脚本")
    SCRIPT = SRC / "setup" / "cleanup_assist_files.py"

    def clean(db, *extra):
        p = subprocess.run([sys.executable, str(SCRIPT), "--db", str(db), *extra], capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def mk(rel):
        put(rel, "x")
        return ws / rel

    OLD, NEWER = "2020-01-01 00:00:00", "2099-01-01 00:00:00"
    rows = [
        row(name="del", path="uploads/del.txt", status="deleted", last_used_at=NEWER),                 # 1 deleted → 删
        row(name="old", path="uploads/old.txt", last_used_at=OLD),                                      # 2 过期 → 删
        row(name="cur", path="uploads/cur.txt", last_used_at=OLD, attached=1),                          # 3 过期但挂着 → 留
        row(name="fresh", path="uploads/fresh.txt", last_used_at=NEWER),                                # 4 新 → 留
        row(name="shared", path="uploads/shared.txt", last_used_at=OLD),                                # 5 过期，但同 path 被 6 引用 → 删行不删文件
        row(name="shared2", path="uploads/shared.txt", last_used_at=NEWER, teacher="t2"),               # 6 留
    ]
    db = seed(rows)
    files = {n: mk("uploads/%s.txt" % n) for n in ("del", "old", "cur", "fresh", "shared")}
    before = q(db, "select * from teacher_assist_file")
    rc, out = clean(db)
    check(rc == 0 and "dry-run" in out and "将删 3 行" in out and "跳过当前附件 1 个" in out, "dry-run：报告将删 3 行、跳过当前附件 1 个", out)
    check(q(db, "select * from teacher_assist_file") == before and all(f.exists() for f in files.values()), "dry-run：库和文件都没变")
    rc, out = clean(db, "--apply")
    left = [r[0] for r in q(db, "select id from teacher_assist_file order by id")]
    check(rc == 0 and left == [3, 4, 6] and "删了 3 行" in out, "--apply：删了 1、2、5，留下 3（挂着）、4、6", (out, left))
    check(not files["del"].exists() and not files["old"].exists(), "--apply：deleted 行和过期行的文件删了")
    check(files["cur"].exists() and files["fresh"].exists(), "--apply：attached=1 的行和新行的文件还在")
    check(files["shared"].exists(), "--apply：同 path 还被别的行引用，只删行不删文件")
    rc, out = clean(db, "--apply")
    check(rc == 0 and "删了 0 行" in out, "再跑一次没东西可删")

    # 超出 --keep：最旧的先删，挂着的计数但不删
    rows = [row(name="k%d" % i, path="uploads/k%d.txt" % i, last_used_at="2099-01-0%d 00:00:00" % (i + 1), attached=1 if i == 0 else 0)
            for i in range(5)]
    db = seed(rows)
    for i in range(5):
        mk("uploads/k%d.txt" % i)
    rc, out = clean(db, "--keep", "3", "--apply")
    left = [r[0] for r in q(db, "select id from teacher_assist_file order by id")]
    check(rc == 0 and left == [1, 4, 5], "--keep 3：5 个 ok 超 2 个，删最旧的非挂着的（id 2、3），挂着的 id 1 计数不删", (out, left))
    check(not (ws / "uploads/k1.txt").exists() and (ws / "uploads/k0.txt").exists(), "--keep：被删行的文件删了、挂着的还在")
    # 另一个老师 / 另一个科目分开数
    rows = [row(teacher="t1", name="a%d" % i, path="uploads/ka%d.txt" % i, last_used_at="2099-01-0%d 00:00:00" % (i + 1)) for i in range(3)] + \
           [row(teacher="t2", name="b%d" % i, path="uploads/kb%d.txt" % i, last_used_at="2099-01-0%d 00:00:00" % (i + 1)) for i in range(2)]
    db = seed(rows)
    rc, out = clean(db, "--keep", "2", "--apply")
    left = [r[0] for r in q(db, "select id from teacher_assist_file order by id")]
    check(rc == 0 and left == [2, 3, 4, 5], "--keep 按老师分开数：t1 3 个删最旧的，t2 2 个不动", (out, left))

    # M4-P3：未保存（draft）且 7 天前的教学材料一并删，saved 的不动；表不存在时跳过
    db = seed([])
    rc, out = clean(db, "--apply")
    check(rc == 0 and "删了 0 行" in out, "材料表不存在：跳过，不报错", out)
    con = sqlite3.connect(db)
    con.execute("create table teacher_assist_material(id integer primary key, teacher text, subject_id integer, kind text, title text,"
                " content text, status text, created_at text, updated_at text)")
    for t, st, ca in (
            ("旧未保存", "draft", "2020-01-01 00:00:00"),   # 1 → 删
            ("旧已保存", "saved", "2020-01-01 00:00:00"),   # 2 → 留
            ("新未保存", "draft", "2099-01-01 00:00:00")):  # 3 → 留
        con.execute("insert into teacher_assist_material(teacher, subject_id, kind, title, content, status, created_at, updated_at)"
                    " values('t1', 1, 'handout', ?, 'x', ?, ?, ?)", (t, st, ca, ca))
    con.commit()
    con.close()
    rc, out = clean(db)
    check(rc == 0 and "将删 1 份未保存材料" in out and len(q(db, "select id from teacher_assist_material")) == 3, "材料 dry-run：报告将删 1 份，库没变", out)
    rc, out = clean(db, "--apply")
    left = [r[0] for r in q(db, "select id from teacher_assist_material order by id")]
    check(rc == 0 and left == [2, 3], "材料 --apply：7 天前的 draft 删了，saved 和新的 draft 不动", (out, left))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
