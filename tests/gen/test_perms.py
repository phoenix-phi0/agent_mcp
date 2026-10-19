# -*- coding: utf-8 -*-
"""private 项目的 gen 权限（程序套，不靠模型）。

    cd /workspace/agent_mcp && .venv/bin/python tests/gen/test_perms.py

一、增删改查接口头行带「角色 <第一个角色>」：只改 gen 块，只有一个角色不加，非 private 不动，重复套结果不变
二、user 的列表 / 单条 / 更新 sql 不碰 password_hash
三、关公开注册：/auth/register 保留接口头、回 403；不关则原样
四、已有项目重新套：gen 块被还原后补回，模型追加的接口 / 内容 / 换行原样保留
五、端到端（Flask test client）：学生调 /user/list、/question/delete 被拒 403，教师能调且 user 列表没有 password_hash，/auth/register 403
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools/dslagent/verbs/newproj/defs"))

from gen import project as P        # noqa: E402
import _gencore as GC               # noqa: E402

passed = failed = 0


def check(ok, msg, extra=""):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg + ("" if ok or extra == "" else f"\n      {str(extra)[:600]}"))


QUESTION = "实体 question 题目\n  字段 title 文本 必填 题干\n结束\n"
NOTE = "实体 note 笔记\n  字段 owner 文本 必填 属主\n  字段 body 文本 必填 内容\n结束\n"


def project(tag, tpl="private", roles=("teacher", "student"), no_register=False, ents=(QUESTION,)):
    root = Path(tempfile.mkdtemp(prefix=f"perms_{tag}_")) / "p"
    root.mkdir(parents=True)
    P.init(root, sample=False)
    for i, t in enumerate(ents):
        (root / "entities" / f"e{i}.entity").write_text(t, encoding="utf-8")
    r = GC.generate(root, tpl, roles=list(roles) if roles else None, no_register=no_register)
    assert r["ok"] == "是", r
    return root


def heads(root, f):
    return [l for l in (root / "routes" / f).read_text(encoding="utf-8").splitlines() if l.startswith("接口 ")]


def main():
    print("一、增删改查接口头行带角色")
    r = project("a")
    hs = heads(r, "question.zs") + heads(r, "user.zs")
    check(len(hs) == 10 and all(h.endswith(" 角色 teacher") for h in hs), "private + 两个角色：question / user 共 10 个接口都带「角色 teacher」", hs)
    check(all(not h.endswith("角色 teacher") for h in heads(r, "auth.zs")) and "公开" in "".join(heads(r, "auth.zs")), "auth.zs 的登录 / 注册 / 退出不动（仍公开）", heads(r, "auth.zs"))
    r1 = project("b", roles=("teacher",))
    check(not any("角色" in h for h in heads(r1, "question.zs") + heads(r1, "user.zs")), "只有一个角色：不加角色")
    r2 = project("c", tpl="full", roles=None)
    check(not any("角色" in h for h in heads(r2, "question.zs")) and not (r2 / "routes/auth.zs").exists(), "非 private：不加角色，也没有 auth")
    r3 = project("d", ents=(QUESTION, NOTE))
    check(all(h.endswith(" 角色 teacher") for h in heads(r3, "note.zs") + heads(r3, "question.zs")), "有 owner 的实体（private 模板）和没有的（full）同样加角色")
    before = {f.name: f.read_bytes() for f in (r / "routes").glob("*.zs")}
    log = P.apply_perms(r, ["teacher", "student"], False)
    check(log == [] and before == {f.name: f.read_bytes() for f in (r / "routes").glob("*.zs")}, "重复套：没有任何改动（幂等）", log)

    print("二、user 查询不出 password_hash")
    qd = r / "queries"
    check(all("password_hash" not in (qd / f"user_{n}.sql").read_text(encoding="utf-8") for n in ("list", "one", "update")), "user_list / user_one / user_update 都不碰 password_hash")
    check("username" in (qd / "user_list.sql").read_text(encoding="utf-8") and "id" in (qd / "user_one.sql").read_text(encoding="utf-8"), "其它列还在")
    check("password_hash" in (qd / "user_insert.sql").read_text(encoding="utf-8") and "password_hash" in (qd / "user_by_name.sql").read_text(encoding="utf-8"), "注册 / 登录用的 sql 不动")
    r1_sql = (r1 / "queries" / "user_list.sql").read_text(encoding="utf-8")
    check("password_hash" not in r1_sql, "只有一个角色时也隐藏 password_hash")

    print("三、关公开注册")
    check("动作 auth_register 公开" in (r / "routes/auth.zs").read_text(encoding="utf-8") and "403" not in (r / "routes/auth.zs").read_text(encoding="utf-8").split("/auth/login")[0], "不关：/auth/register 原样公开")
    rc = project("e", no_register=True)
    a = (rc / "routes/auth.zs").read_text(encoding="utf-8")
    seg = a.split("接口 POST /auth/register")[1].split("\n结束")[0]
    check("动作 auth_register 公开" in a and "403" in seg and "注册用户" not in seg and "/auth/login" in a and "登录 app.db" in a, "关：接口头保留（界面动作还在），内容回 403，登录不动", seg)
    check(P.apply_perms(rc, ["teacher", "student"], True) == [], "关注册重复套不变")

    print("四、已有项目重新套（保留追加部分）")
    root = project("f")
    qf = root / "routes" / "question.zs"
    appended = "\r\n\r\n接口 POST /question/extra 动作 question_extra\r\n  用包 db http\r\n  返回 {\"ok\":\"1\"}\r\n结束\r\n"
    text = qf.read_text(encoding="utf-8").replace("\n", "\r\n").replace(" 角色 teacher", "")
    qf.write_bytes((text.rstrip("\r\n") + appended).encode("utf-8"))
    (root / "queries/user_list.sql").write_text("SELECT id, username, password_hash\nFROM user\n", encoding="utf-8")
    log = P.apply_perms(root, ["teacher", "student"], True)
    raw = qf.read_bytes().decode("utf-8")
    check(raw.count(" 角色 teacher") == 5 and "\r\n" in raw and "\r\n" not in raw.replace("\r\n", ""), "gen 的 5 个块补回角色，CRLF 换行保持", raw.count(" 角色 teacher"))
    check("接口 POST /question/extra 动作 question_extra\r\n" in raw and raw.endswith(appended.lstrip("\r\n")), "追加的接口原样（头行不加角色，内容与换行不变）")
    check("password_hash" not in (root / "queries/user_list.sql").read_text(encoding="utf-8") and any("auth.zs" in x for x in log), "user 查询重新去掉 password_hash；注册这次也关上了", log)
    # 模型把追加接口的路径写成和 gen 一样但动作不同：不认作 gen 块
    ext = root / "routes" / "question.zs"
    ext.write_text(ext.read_text(encoding="utf-8").replace("question_extra", "question_other").replace("/question/extra", "/question/list2"), encoding="utf-8")
    check(P.gen_block("接口 POST /question/list 动作 question_extra", {"question"}) == "" and P.gen_block("接口 POST /question/list 动作 question_refresh", {"question"}) == "question", "gen_block 只认路径 + 动作都对得上的")
    check(P.gen_block("接口 POST /question/list 动作 question_refresh 公开", {"question"}) == "", "标了公开的不当 gen 块（不替人加角色）")

    print("五、端到端（Flask test client）")
    from tools.auth import COOKIE, make_token
    root = project("g", no_register=True)
    con = sqlite3.connect(root / "app.db")
    con.execute("INSERT INTO user(username, password_hash, role) VALUES('t1','hash-t','teacher'),('s1','hash-s','student')")
    con.execute("INSERT INTO question(title) VALUES('q1')")
    con.commit()
    con.close()
    app, router = P.make_app(root, login=True)
    cl = app.test_client()

    def call(user, path):
        cl.delete_cookie(COOKIE)
        if user:
            cl.set_cookie(COOKIE, make_token(user, router._secret()))
        return cl.post(path, json={"form": {"id": 1}})
    r = call("s1", "/user/list")
    check(r.status_code == 403, f"学生调 /user/list → 403（{r.status_code}）")
    check(call("s1", "/question/delete").status_code == 403 and call("s1", "/question/create").status_code == 403, "学生调 /question/delete、/question/create → 403")
    r = call("t1", "/user/list")
    body = r.get_data(as_text=True)
    check(r.status_code == 200 and "t1" in body and "hash-t" not in body and "password_hash" not in body, f"教师 /user/list → 200 且没有 password_hash（{r.status_code}）", body[:200])
    r = call("t1", "/user/one")
    check(r.status_code == 200 and "hash-" not in r.get_data(as_text=True), "教师 /user/one 也没有哈希")
    r = call(None, "/auth/register")
    check(r.status_code == 403, f"匿名 /auth/register → 403（{r.status_code}，不再公开自助注册）")
    check(call(None, "/question/list").status_code == 401, "匿名调 CRUD 仍是 401")

    print(f"\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
