# -*- coding: utf-8 -*-
"""K192：把 Python 默写题库（content/python_v1/dictation/questions.json）导入 dictation_question。
默认只预检不写库，--apply 才写。

    .venv/bin/python kg_v4/scripts/import_python_dictation.py --db 库路径 --subject python --file questions.json [--apply]
    .venv/bin/python kg_v4/scripts/import_python_dictation.py --db 库路径 --subject python --enable-caps [--apply]

预检（任何一条不过就零写入，退出码 1）：
  - schema 为 python-dictation-v1，questions 是非空列表；
  - 科目：subject_info 里 code=--subject 的那一行存在，且 code 是 python（本脚本只给 Python 用）；
  - 每题 id 非空且全文件唯一；type 为 term/output；difficulty 为 入门/基础/进阶；
    prompt_zh/prompt_ja/explain_zh/explain_ja/answer 非空（output 题的 answer 允许内容为空白以外的任意文本）；
    accepted 是非空字符串列表且含 answer；
  - point_code 全部是本科目 kg_point 里的知识点（别的科目同名不算）；
  - 表 dictation_question 已存在（新表由服务启动时的「迁移 只加」或 init_data 建，本脚本不建表）。
  代码输出不在这里执行（生产不依赖执行器）；--verify-code 时先跑仓库校验器
  content/python_v1/dictation/check_dictation.py，不过就零写入（只在开发/测试副本上用）。

写入：一个显式事务，按 (subject_id, code) upsert——已有的题更新内容、保持 id 不变；新题插入；
文件里没有的旧题不删、不停用；只写本科目的行；不碰作答、进度和别的表；不写译文表
（双语字段直接进 prompt_ja/explain_ja）。出错整批回滚。重复导入幂等（内容相同计「不变」）。

--enable-caps：独立步骤，题库导入并验收后才做。把本科目 caps JSON 合并上 "dictation":1，
其余键原样保留；本科目还没有已启用的题时拒绝。默认同样只预检，--apply 才写。
"""
import json
import pathlib
import sqlite3
import subprocess
import sys

SCHEMA = "python-dictation-v1"
LEVELS = ("入门", "基础", "进阶")
KINDS = ("term", "output")
COLS = ("point_code", "kind", "level", "prompt_zh", "prompt_ja", "answer",
        "accepted_json", "explain_zh", "explain_ja", "enabled")


def arg(a, name, default=None):
    if name in a:
        i = a.index(name)
        if i + 1 >= len(a):
            sys.exit(f"{name} 缺值")
        return a[i + 1]
    return default


def subject_row(con, code):
    r = con.execute("SELECT id, code, caps FROM subject_info WHERE code=?", (code,)).fetchone()
    if not r:
        return None, f"subject_info 里没有 code={code} 的科目"
    if r[1] != "python":
        return None, f"科目 {code} 不是 python，本脚本只导 Python 默写题库"
    return r, ""


def table_exists(con, name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def load_rows(path, points):
    errs, rows, seen = [], [], set()
    try:
        d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — 坏文件整批拒收
        return [], [f"读不了题库：{e}"]
    if not isinstance(d, dict) or d.get("schema") != SCHEMA:
        return [], [f"schema 不是 {SCHEMA}"]
    qs = d.get("questions")
    if not isinstance(qs, list) or not qs:
        return [], ["questions 为空或不是列表"]
    for n, q in enumerate(qs, 1):
        tag = f"第 {n} 题"
        if not isinstance(q, dict):
            errs.append(f"{tag}：不是对象")
            continue
        code = q.get("id")
        if not isinstance(code, str) or not code.strip():
            errs.append(f"{tag}：id 为空")
            continue
        tag = f"{tag}（{code}）"
        if code in seen:
            errs.append(f"{tag}：id 重复")
        seen.add(code)
        kind, level = q.get("type"), q.get("difficulty")
        if kind not in KINDS:
            errs.append(f"{tag}：type 不是 term/output：{kind!r}")
        if level not in LEVELS:
            errs.append(f"{tag}：difficulty 不是 入门/基础/进阶：{level!r}")
        for f in ("prompt_zh", "prompt_ja", "explain_zh", "explain_ja"):
            if not isinstance(q.get(f), str) or not q[f].strip():
                errs.append(f"{tag}：{f} 为空")
        ans, acc = q.get("answer"), q.get("accepted")
        if not isinstance(ans, str) or not ans.strip():
            errs.append(f"{tag}：answer 为空")
        if not isinstance(acc, list) or not acc or not all(isinstance(x, str) for x in acc):
            errs.append(f"{tag}：accepted 应为非空字符串列表")
        elif ans not in acc:
            errs.append(f"{tag}：accepted 不含 answer")
        pc = q.get("point_code")
        if pc not in points:
            errs.append(f"{tag}：point_code {pc!r} 不是本科目的知识点")
        rows.append({"code": code, "point_code": pc, "kind": kind, "level": level,
                     "prompt_zh": q.get("prompt_zh"), "prompt_ja": q.get("prompt_ja"),
                     "answer": ans, "accepted_json": json.dumps(acc, ensure_ascii=False),
                     "explain_zh": q.get("explain_zh"), "explain_ja": q.get("explain_ja"),
                     "enabled": 1})
    return rows, errs


def do_import(con, sid, rows, apply_):
    cur = {r[0]: r[1:] for r in con.execute(
        "SELECT code, " + ", ".join(COLS) + " FROM dictation_question WHERE subject_id=?", (sid,))}
    add = [r for r in rows if r["code"] not in cur]
    upd = [r for r in rows if r["code"] in cur and tuple(r[c] for c in COLS) != tuple(cur[r["code"]])]
    same = len(rows) - len(add) - len(upd)
    absent = sorted(set(cur) - {r["code"] for r in rows})
    print(f"新增 {len(add)}、更新 {len(upd)}、不变 {same}、拒收 0；库里有、文件里没有（保留不删）{len(absent)}")
    if not apply_:
        print("预检通过（没加 --apply，没写库）")
        return 0
    con.execute("BEGIN IMMEDIATE")
    try:
        for r in add:
            con.execute("INSERT INTO dictation_question (subject_id, code, " + ", ".join(COLS) + ") VALUES (?, ?, "
                        + ", ".join("?" for _ in COLS) + ")", (sid, r["code"], *[r[c] for c in COLS]))
        for r in upd:
            con.execute("UPDATE dictation_question SET " + ", ".join(f"{c}=?" for c in COLS)
                        + " WHERE subject_id=? AND code=?", (*[r[c] for c in COLS], sid, r["code"]))
        n = con.execute("SELECT COUNT(*) FROM dictation_question WHERE subject_id=?", (sid,)).fetchone()[0]
        con.execute("COMMIT")
    except Exception as e:  # noqa: BLE001
        con.execute("ROLLBACK")
        print(f"写库失败，整批回滚：{e}")
        return 1
    print(f"已写入：本科目 dictation_question 共 {n} 题")
    return 0


def enable_caps(con, sid, caps, apply_):
    n = con.execute("SELECT COUNT(*) FROM dictation_question WHERE subject_id=? AND enabled=1", (sid,)).fetchone()[0]
    if n == 0:
        print("本科目还没有可出的默写题，拒绝打开 dictation（先导入题库）")
        return 1
    try:
        c = json.loads(caps or "{}")
        if not isinstance(c, dict):
            raise ValueError("不是对象")
    except Exception as e:  # noqa: BLE001
        print(f"caps 不是合法 JSON 对象（{e}），不改")
        return 1
    if c.get("dictation") == 1:
        print(f"caps 已有 dictation=1，不用改：{caps}")
        return 0
    c["dictation"] = 1
    new = json.dumps(c, ensure_ascii=False, separators=(",", ":"))
    print(f"caps：{caps} → {new}（题 {n} 道）")
    if not apply_:
        print("预检通过（没加 --apply，没写库）")
        return 0
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute("UPDATE subject_info SET caps=? WHERE id=? AND caps IS ?", (new, sid, caps))
        if con.execute("SELECT changes()").fetchone()[0] != 1:
            raise RuntimeError("caps 在预检后被改过")
        con.execute("COMMIT")
    except Exception as e:  # noqa: BLE001
        con.execute("ROLLBACK")
        print(f"写库失败，回滚：{e}")
        return 1
    print("已打开 dictation")
    return 0


def main():
    a = sys.argv[1:]
    db, subj, fpath = arg(a, "--db"), arg(a, "--subject", "python"), arg(a, "--file")
    apply_ = "--apply" in a
    if not db:
        sys.exit("要用 --db 明确给库路径")
    if not pathlib.Path(db).is_file():
        sys.exit(f"库不存在：{db}")
    con = sqlite3.connect(db, isolation_level=None)
    con.execute("PRAGMA busy_timeout=5000")
    srow, err = subject_row(con, subj)
    if err:
        print(err)
        return 1
    sid, _, caps = srow
    if not table_exists(con, "dictation_question"):
        print("库里还没有 dictation_question 表（先用新版本启动一次服务或跑 init_data 建表）")
        return 1
    if "--enable-caps" in a:
        return enable_caps(con, sid, caps, apply_)
    if not fpath:
        sys.exit("要用 --file 给题库 JSON")
    if "--verify-code" in a:
        chk = pathlib.Path(fpath).resolve().parent / "check_dictation.py"
        r = subprocess.run([sys.executable, str(chk)], capture_output=True, text=True)
        print((r.stdout or r.stderr).strip().splitlines()[-1:] or ["（校验器无输出）"])
        if r.returncode != 0:
            print("仓库校验器不过，零写入")
            return 1
    points = {r[0] for r in con.execute("SELECT code FROM kg_point WHERE subject_id=?", (sid,))}
    rows, errs = load_rows(fpath, points)
    pcs = {r["point_code"] for r in rows}
    print(f"科目 {subj}（id={sid}）：文件 {len(rows)} 题，知识点覆盖 {len(pcs & points)}/{len(points)}，"
          f"术语 {sum(r['kind'] == 'term' for r in rows)}、代码输出 {sum(r['kind'] == 'output' for r in rows)}")
    if errs:
        for e in errs[:50]:
            print("拒收：" + e)
        print(f"预检不过（{len(errs)} 处），零写入")
        return 1
    return do_import(con, sid, rows, apply_)


if __name__ == "__main__":
    sys.exit(main())
