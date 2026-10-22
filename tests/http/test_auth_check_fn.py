# -*- coding: utf-8 -*-
"""「认证 核对 <模块>.<函数>」：认证核对直接调业务函数。

    cd /workspace/agent_mcp && .venv/bin/python tests/http/test_auth_check_fn.py

覆盖：登录用户拿到 role、函数返回空当没登录（401 并删 cookie）、角色 403、公开接口免登录、
函数不存在回 500 和说明、旧写法「认证 核对 库 查询」回归不变。
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.auth import COOKIE, make_token            # noqa: E402
from tools.dsl_http import Router                    # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


SERVICE = """\
业务 account
  公开 函数 核对身份 username
    如果 {username} 等于 tom
      返回 {"username": "tom", "role": "teacher"}
    结束
    如果 {username} 等于 sue
      返回 {"username": "sue", "role": "student"}
    结束
    返回 ""
  结束

  公开 函数 找人 username
    报错 404 没有这个人
  结束
结束
"""

ROUTES = """\
认证 可选
认证 核对 {check}
认证 身份 learner 默认 me
认证 角色 teacher 教师
认证 角色 student 学生

接口 GET /me
  返回 {{"u": "{{current_user}}", "r": "{{current_role}}"}}
结束

接口 GET /t 角色 teacher
  返回 {{"ok": 1}}
结束

接口 GET /s 角色 student
  返回 {{"ok": 1}}
结束

接口 POST /login 公开
  返回 {{"ok": 1}}
结束
"""

OLD_SQL = "SELECT username, role FROM account_user WHERE username = :username\n"


def project(check_line, old=False):
    ws = Path(tempfile.mkdtemp(prefix="authfn_"))
    (ws / "routes").mkdir()
    (ws / "services").mkdir()
    (ws / "routes" / "account.zs").write_text(ROUTES.format(check=check_line), encoding="utf-8")
    (ws / "services" / "account.zs").write_text(SERVICE, encoding="utf-8")
    if old:
        (ws / "queries").mkdir()
        (ws / "queries" / "who.sql").write_text(OLD_SQL, encoding="utf-8")
        con = sqlite3.connect(ws / "app.db")
        con.execute("CREATE TABLE account_user(username TEXT, role TEXT)")
        con.execute("INSERT INTO account_user VALUES('tom','teacher'),('sue','student')")
        con.commit()
        con.close()
    router = Router(ws / "routes", ws, ws / "sessions", real=False, login=True)
    app = router.app()
    return router, app


def client_for(router, app, user):
    c = app.test_client()
    if user:
        c.set_cookie(COOKIE, make_token(user, router._secret()))
    return c


def suite(router, app, label):
    r = client_for(router, app, "tom").get("/me")
    check(r.status_code == 200 and r.get_json() == {"u": "tom", "r": "teacher"},
          f"{label}：登录用户 tom 拿到 role=teacher：{r.get_json()}")
    r = client_for(router, app, "sue").get("/me")
    check(r.get_json() == {"u": "sue", "r": "student"}, f"{label}：sue 是 student：{r.get_json()}")
    r = client_for(router, app, None).get("/me")
    check(r.status_code == 401, f"{label}：不登录 401")
    r = client_for(router, app, None).post("/login", json={})
    check(r.status_code == 200, f"{label}：公开接口免登录")
    r = client_for(router, app, "sue").get("/t")
    check(r.status_code == 403, f"{label}：学生调教师接口 403")
    r = client_for(router, app, "tom").get("/s")
    check(r.status_code == 403, f"{label}：教师调学生接口 403")
    r = client_for(router, app, "tom").get("/t")
    check(r.status_code == 200, f"{label}：教师调教师接口 200")
    r = client_for(router, app, "ghost").get("/me")
    check(r.status_code == 401 and COOKIE in r.headers.get("Set-Cookie", ""),
          f"{label}：查不到的用户 401 并删 cookie")


def main():
    print("一、函数写法")
    router, app = project("account.核对身份")
    check(router.auth_check_fn == ("account", "核对身份") and router.auth_check is None,
          "解析出 (模块, 函数)")
    suite(router, app, "函数")

    print("二、函数报 404 当没登录")
    router, app = project("account.找人")
    r = client_for(router, app, "tom").get("/me")
    check(r.status_code == 401, f"404 当没登录：{r.status_code}")

    print("三、函数不存在 / 不是公开 → 500 和说明")
    router, app = project("account.没有这个")
    r = client_for(router, app, "tom").get("/me")
    check(r.status_code == 500 and "没有这个" in (r.get_json() or {}).get("error", ""),
          f"500 带说明：{r.status_code} {r.get_json()}")
    router, app = project("nomod.核对身份")
    r = client_for(router, app, "tom").get("/me")
    check(r.status_code == 500 and "nomod" in (r.get_json() or {}).get("error", ""),
          f"模块不存在 500：{r.get_json()}")

    print("四、旧写法回归")
    router, app = project("app.db who", old=True)
    check(router.auth_check == ("app.db", "who") and router.auth_check_fn is None, "旧写法照旧解析")
    suite(router, app, "旧")

    print("五、两种写法同时写报错")
    try:
        ws = Path(tempfile.mkdtemp(prefix="authfn_"))
        (ws / "routes").mkdir()
        (ws / "routes" / "a.zs").write_text(
            "认证 可选\n认证 核对 account.核对身份\n认证 核对 app.db who\n", encoding="utf-8")
        Router(ws / "routes", ws, ws / "s", real=False)
        check(False, "应报错")
    except Exception as e:  # noqa: BLE001
        check("只能写一种" in str(e), f"报错：{e}")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
