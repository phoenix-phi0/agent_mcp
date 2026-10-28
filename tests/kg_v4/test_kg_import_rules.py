#!/usr/bin/env python
# -*- coding: utf-8 -*-
# kg_v4 导入规则测试（K110，对应 K108 约定）：约定用例只能断言返回的顶层键，
# 行级 reason 原文、报错原文、路径反例、HTTP 正路、teacher_assist 的功能说明在这里断。
#   1) 行尾多余 |：预检行 reason / 确认导入报错原文；
#   2) 同文件重复编号：前面各行「被第N行覆盖」、最后一行「本文件重复，以本行为准」；
#   3) csv 缺列 vs 某行空值；
#   4) 路径反例（反斜杠、..、uploads/ 后为空、子目录、绝对路径、非 uploads）→ 400「导入文件路径不对」；
#   5) HTTP 正路：页面上传 → 预检 → 用回填的 imp_file 确认，成功导入；
#   6) teacher_assist chitchat 的 context_text 含「图谱管理」。
#
#     cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_kg_import_rules.py
# 退出码 0 全过 / 1 有失败 / 2 环境起不来。离线（假模型），临时目录，不碰仓库文件。
import http.cookiejar
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2]))
import e2e_walk as E  # noqa: E402
from tools.dslagent.packs.dslproj import cases as K  # noqa: E402

ok_n = fail_n = 0
TEACHER = {"current_role": "teacher", "auth_mode": "on"}
PATH_ERR = "导入文件路径不对"


def ck(ok, msg, detail=""):
    global ok_n, fail_n
    if ok:
        ok_n += 1
        print("  OK " + msg)
    else:
        fail_n += 1
        print("  XX " + msg + "\n      " + str(detail)[:500])


def put(ws, rel, text):
    p = Path(ws) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))


def count_points(ws, codes):
    import sqlite3
    con = sqlite3.connect(Path(ws) / "app.db")
    try:
        q = ",".join("?" * len(codes))
        return con.execute(f"select count(*) from kg_point where code in ({q})", codes).fetchone()[0]
    finally:
        con.close()


def in_process(ws):
    os.environ.setdefault("DSL_NOW", K.DEFAULT_NOW)
    eng = K.make_engine(ws)
    n = [0]

    def call(mod, fn, **args):
        n[0] += 1
        r, err = K.call(eng, mod, fn, args, "r%d" % n[0])
        K.settle()
        return r, err

    def err_of(e):
        if isinstance(e, dict):
            return e.get("code"), str(e.get("error", ""))
        return None, str(e)

    def pre(kind, path):
        return call("kg", "导入预检", kind=kind, file_path=path, learner="t1", **TEACHER)

    def conf(kind, path):
        return call("kg", "确认导入", kind=kind, file_path=path, learner="t1", **TEACHER)

    print("一、行尾多余 |")
    put(ws, "uploads/t1.txt", "R1|甲|\nR2|乙")
    r, e = pre("point", "uploads/t1.txt")
    want = "项数多了：知识点每行最多2项（编号|名称），行尾多余的|也算一项"
    rows = (r or {}).get("rows") or []
    ck(not e and rows and rows[0].get("reason") == want, "预检第1行 reason 原文", (r, e))
    ck(not e and (r["total"], r["ok_count"], r["error_count"]) == (2, 1, 1), "预检 total=2 ok=1 err=1", (r, e))
    r, e = conf("point", "uploads/t1.txt")
    c, m = err_of(e)
    ck(str(c) == "400" and m == "导入文件有错（第1行：" + want + "）", "确认导入报错原文带行号", (r, e))
    ck(count_points(ws, ["R1", "R2"]) == 0, "确认失败后库里 0 行")

    print("二、同文件重复编号")
    put(ws, "uploads/t2.txt", "D1|甲\nD1|乙\nD1|丙")
    r, e = pre("point", "uploads/t2.txt")
    rs = [x.get("reason") for x in ((r or {}).get("rows") or [])]
    ck(not e and rs == ["被第3行覆盖", "被第3行覆盖", "本文件重复，以本行为准"], "三行 reason", (rs, e))
    # 库里已有 D1 且 title 相同：第 1 行「内容相同；被第3行覆盖」
    put(ws, "uploads/t2a.txt", "D1|甲")
    r, e = conf("point", "uploads/t2a.txt")
    ck(not e, "先导入 D1|甲", (r, e))
    r, e = pre("point", "uploads/t2.txt")
    rs = [x.get("reason") for x in ((r or {}).get("rows") or [])]
    ck(not e and rs and rs[0] == "内容相同；被第3行覆盖" and rs[2] == "本文件重复，以本行为准",
       "库里已有且相同：第1行「内容相同；被第3行覆盖」", (rs, e))

    print("三、csv 缺列 / 某行空值")
    put(ws, "uploads/c1.csv", "code,name\nC1,甲")
    r, e = pre("point", "uploads/c1.csv")
    c, m = err_of(e)
    ck(str(c) == "400" and m == "导入文件读不了（缺title）", "表头缺 title：整份不认", (r, e))
    put(ws, "uploads/c2.csv", "code,title\nC1,甲\n,乙")
    r, e = conf("point", "uploads/c2.csv")
    c, m = err_of(e)
    ck(str(c) == "400" and m == "导入文件有错（第3行：缺编号）", "某行空值：确认导入报第3行缺编号", (r, e))
    put(ws, "uploads/c3.csv", "code,title\n,甲\n,乙")
    r, e = pre("point", "uploads/c3.csv")
    ck(not e and (r["total"], r["ok_count"], r["error_count"]) == (2, 0, 2), "整列全空逐行报错（不是缺列）", (r, e))

    print("四、路径反例")
    put(ws, "uploads/ok.txt", "Z1|甲")
    put(ws, "outside.txt", "Z1|甲")
    put(ws, "uploads/sub/p.txt", "Z1|甲")
    bad = ["uploads\\p.txt", "uploads/../outside.txt", "uploads/", "uploads/sub/p.txt",
           "outside.txt", "kg_in/p.txt", "/tmp/p.txt", "C:/uploads/p.txt"]
    for p in bad:
        for fn, label in ((pre, "预检"), (conf, "确认")):
            r, e = fn("point", p)
            c, m = err_of(e)
            ck(str(c) == "400" and m == PATH_ERR, f"{label} {p!r} → 400 {PATH_ERR}", (r, e))
    ck(count_points(ws, ["Z1"]) == 0, "路径被拒后库里 0 行")
    r, e = pre("point", "uploads/ok.txt")
    ck(not e and r["total"] == 1 and r["error_count"] == 0, "对照：uploads/ok.txt 预检通过", (r, e))

    print("六、teacher_assist chitchat 功能说明")
    r, e = call("teacher_assist", "取助手上下文", intent="chitchat", learner="t1", **TEACHER)
    ctx = (r or {}).get("context_text", "") if isinstance(r, dict) else str(r)
    ck(not e and "图谱管理" in ctx, "context_text 含「图谱管理」", (e, ctx[:300]))


def multipart(fields, fname, content):
    b = uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += (f'--{b}\r\nContent-Disposition: form-data; name="imp_upload"; filename="{fname}"\r\n'
            f'Content-Type: text/plain\r\n\r\n').encode() + content + f"\r\n--{b}--\r\n".encode()
    return out, f"multipart/form-data; boundary={b}"


def http_path(tmp):
    print("五、HTTP 正路：页面上传 → 预检 → 回填的 imp_file 确认")
    proj = E.build_workspace(tmp / "http", E.REPO / "kg_v4", kg_mgmt=True)
    port = E.free_port()
    proc = E.start_server(proj, port, open(tmp / "server.log", "w"))
    try:
        base = f"http://127.0.0.1:{port}"
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def post(path, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            req = urllib.request.Request(base + path, data=data, method="POST", headers={"Content-Type": ctype})
            try:
                with op.open(req, timeout=60) as r:
                    return r.status, r.read().decode("utf-8")
            except urllib.error.HTTPError as ex:
                return ex.code, ex.read().decode("utf-8", "replace")

        st, tx = post("/account/login", {"username": E.TEACHER_USER, "password": E.TEST_PASSWORD})
        ck(st == 200, "t1 登录", (st, tx))
        body, ct = multipart({"imp_kind": "知识点"}, "p.txt", "H1|正路甲\nH2|正路乙".encode())
        st, tx = post("/kg/manage/import/preview", body, ct)
        try:
            j = json.loads(tx)
        except ValueError:
            j = {}
        form = j.get("form") or (j.get("state") or {}).get("form") or {}
        f = form.get("imp_file", "")
        ck(st == 200 and f.startswith("uploads/") and "/" not in f[len("uploads/"):], "预检回填 imp_file 在 uploads/ 下", (st, tx[:300]))
        st, tx = post("/kg/manage/import/confirm", {"imp_kind": "知识点", "imp_file": f})
        ck(st == 200 and "H1" in tx and "H2" in tx, "用回填的 imp_file 确认导入成功", (st, tx[:300]))
        st, tx = post("/kg/manage/import/confirm", {"imp_kind": "知识点", "imp_file": "kg_in/p.txt"})
        ck(st == 400, "确认页面传 kg_in/p.txt → 400", (st, tx[:200]))
    finally:
        E.stop_server(proc)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="kg_import_rules_"))
    try:
        try:
            ws = E.build_workspace(tmp / "proc", E.REPO / "kg_v4", kg_mgmt=True)
        except Exception as ex:
            print("环境起不来：", ex)
            return 2
        in_process(ws)
        try:
            http_path(tmp)
        except Exception as ex:
            ck(False, "HTTP 段出错", repr(ex))
        print(f"\n通过 {ok_n}/共 {ok_n + fail_n}")
        return 1 if fail_n else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
