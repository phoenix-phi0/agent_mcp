# -*- coding: utf-8 -*-
"""认证和「每人只看自己的数据」的测试。

    cd /home/ysc/mcp && .venv/bin/python tests/auth/test_auth.py

用 Flask 自带的测试客户端，不起服务——它自己管 cookie，跟浏览器一样：
登录拿到 cookie，之后的请求自动带上。

建一个临时项目：gen auth + 一个带 owner 的实体 + 「私有」模板，然后：

  一、生成：用户表被「私有」跳过；界面能编译，密码框是 password 类型
  二、没登录：受保护的接口 401，公开的能调
  三、注册即登录；cookie 是 HttpOnly + SameSite=Lax；库里存的是哈希
  四、伪造：请求体里塞 owner、塞「当前用户」，都改不了归属
  五、隔离：换一个人看不到、改不了、删不了前一个人的数据（404）
  六、登录失败：不区分没这个人和密码错，失败不发 cookie
  七、令牌：篡改、过期、换密钥签的，一律当没登录
  八、注册校验：重名、密码太短、用户名带空格
"""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gen.project import add_auth, build, ensure_db, generate, init, make_app  # noqa: E402
from tools.auth import COOKIE, make_token, secret_for                          # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


NOTE = """\
实体 note 笔记
  字段 title 文本 必填 标题
  字段 body 长文本 正文
  字段 owner 文本 必填 索引 归属
结束
"""


def main():
    root = Path(tempfile.mkdtemp(prefix="auth_")) / "app"
    init(root, sample=False)
    add_auth(root)
    (root / "entities" / "note.entity").write_text(NOTE, encoding="utf-8")

    print("一、生成")
    lines = generate(root, "private")
    check(any("跳过实体 user" in x for x in lines), "用户表没有 owner，被「私有」跳过")
    check((root / "routes" / "note.zs").is_file(), "笔记的接口生成了")
    ensure_db(root)
    build(root)
    js = (root / "web" / "app.js").read_text(encoding="utf-8")
    check('type="password"' in js, "密码框是 password 类型（输入不明文显示）")
    first = json.loads(js.split("const screens = ", 1)[1].split(";", 1)[0])[0]["name"]
    check(first == "笔记列表", f"入口是应用界面而不是登录页：{first}")

    app, router = make_app(root, real=False)
    check(router.auth_required, "路由器认出了「认证 必须」")
    c = app.test_client()

    def post(client, path, **form):
        r = client.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {}), r

    def db(sql, *args):
        con = sqlite3.connect(root / "app.db")
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    print("二、没登录")
    st, body, _ = post(c, "/note/list")
    check(st == 401 and body.get("error") == "请先登录", f"受保护的接口 401：{st} {body}")
    st, body, _ = post(c, "/note/create", title="x", body="")
    check(st == 401 and not db("SELECT * FROM note"), "没登录建不了数据，库里是空的")
    st, body, _ = post(c, "/auth/me")
    check(st == 200 and body.get("user") == "", f"公开接口能调，当前用户是空：{body}")

    print("三、注册即登录")
    st, body, r = post(c, "/auth/register", username="alice", password="pass word 1")
    check(st == 200 and body.get("go") == "@来处", f"注册成功：{st} {body}")
    cookie = r.headers.get("Set-Cookie", "")
    check(COOKIE in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie,
          f"cookie 是 HttpOnly + SameSite=Lax：{cookie[:80]}…")
    st, body, _ = post(c, "/auth/me")
    check(body.get("user") == "alice", f"现在是 alice：{body}")
    h = db("SELECT password_hash FROM user WHERE username = 'alice'")[0][0]
    check(h.startswith("scrypt$") and "pass word" not in h, "库里存的是 scrypt 哈希，没有明文")

    print("四、伪造归属")
    st, body, _ = post(c, "/note/create", title="alice 的 笔记", body="正文",
                       owner="bob", 当前用户="bob")
    check(st == 200, f"建成了：{st}")
    rows = db("SELECT title, owner FROM note")
    check(rows == [("alice 的 笔记", "alice")],
          f"请求体里塞 owner=bob、当前用户=bob 都没用，归属是 alice：{rows}")
    st, body, _ = post(c, "/note/list")
    # 表格数据在 lists 里按数据键给，键就是界面上那张表的名字（notes）
    notes = (body.get("lists") or {}).get("notes", [])
    check(len(notes) == 1 and "owner" not in notes[0],
          f"列表 1 行，不带 owner 列：{notes}")
    note_id = notes[0]["id"]

    print("  退出")
    st, body, r = post(c, "/auth/logout")
    check(st == 200 and body.get("go") == "登录", f"退出：{body}")
    check(COOKIE in r.headers.get("Set-Cookie", "") and
          ("Max-Age=0" in r.headers.get("Set-Cookie", "") or
           "expires=Thu, 01 Jan 1970" in r.headers.get("Set-Cookie", "")),
          "cookie 被删掉")
    st, _, _ = post(c, "/note/list")
    check(st == 401, f"退出后又是 401：{st}")

    print("五、换一个人")
    post(c, "/auth/register", username="bob", password="bobpass")
    st, body, _ = post(c, "/note/list")
    check(st == 200 and (body.get("lists") or {}).get("notes") == [],
          f"bob 看不到 alice 的：{body.get('lists')}")
    st, body, _ = post(c, "/note/update", id=note_id, title="被 bob 改了", body="")
    check(st == 404, f"bob 改 alice 的记录：{st} {body}")
    st, body, _ = post(c, "/note/delete", id=note_id)
    check(st == 404, f"bob 删 alice 的记录：{st} {body}")
    st, body, _ = post(c, "/note/one", id=note_id)
    check(st == 404, f"bob 查 alice 的记录：{st}")
    check(db("SELECT title, owner FROM note") == [("alice 的 笔记", "alice")],
          "alice 的记录原封不动")
    post(c, "/note/create", title="bob 的", body="")
    check(sorted(db("SELECT owner FROM note")) == [("alice",), ("bob",)],
          "bob 建的归 bob")

    print("六、登录失败")
    c2 = app.test_client()
    st, body1, r1 = post(c2, "/auth/login", username="alice", password="错的")
    st2, body2, r2 = post(c2, "/auth/login", username="没这个人", password="错的")
    check(st == 400 and st2 == 400 and body1 == body2,
          f"密码错和没这个人，回的一模一样：{body1} / {body2}")
    check(COOKIE not in r1.headers.get("Set-Cookie", "") and
          COOKIE not in r2.headers.get("Set-Cookie", ""), "失败不发 cookie")
    st, _, _ = post(c2, "/note/list")
    check(st == 401, "失败之后仍然没登录")
    st, body, _ = post(c2, "/auth/login", username="alice", password="pass word 1")
    st, body, _ = post(c2, "/note/list")
    titles = [x["title"] for x in (body.get("lists") or {}).get("notes", [])]
    check(st == 200 and titles == ["alice 的 笔记"],
          f"密码带空格也能登录，看到自己的：{titles}")

    print("七、令牌")
    key = secret_for(root)
    good = make_token("alice", key)

    def with_cookie(value):
        """带着指定的 cookie 调一次受保护的接口。

        用测试客户端自己的 set_cookie，不手写 Cookie 头：手写的头会被
        客户端的 cookie 罐盖掉，服务器根本收不到——第一版就是这么写的，
        结果「正确的令牌能用」这条对照失败，后面几条「伪造的被拒」全都
        是白过的：cookie 压根没到，当然是 401。
        """
        fresh = app.test_client()
        try:
            fresh.set_cookie(COOKIE, value)                 # Werkzeug >= 2.3
        except TypeError:
            fresh.set_cookie("localhost", COOKIE, value)    # 更早的版本
        r = fresh.post("/note/list", json={"form": {}})
        return r.status_code

    check(with_cookie(good) == 200, "正确签名的令牌能用（对照）")
    payload, sig = good.rsplit(".", 1)
    forged = make_token("bob", key).rsplit(".", 1)[0] + "." + sig
    check(with_cookie(forged) == 401, "把用户名换成 bob、签名照抄：401")
    check(with_cookie(make_token("alice", key, ttl=-10)) == 401, "过期的：401")
    check(with_cookie(make_token("alice", b"x" * 32)) == 401, "别的密钥签的：401")
    check(with_cookie("乱写的") == 401, "格式都不对的：401")

    print("八、注册校验")
    st, body, _ = post(app.test_client(), "/auth/register", username="alice", password="whatever1")
    check(st == 400 and "已被占用" in body.get("error", ""), f"重名：{body}")
    st, body, _ = post(app.test_client(), "/auth/register", username="carol", password="123")
    check(st == 400 and "至少" in body.get("error", ""), f"密码太短：{body}")
    st, body, _ = post(app.test_client(), "/auth/register", username="有 空格", password="123456")
    check(st == 400 and "空格" in body.get("error", ""), f"用户名带空格：{body}")
    check(len(db("SELECT * FROM user")) == 2, "库里只有 alice 和 bob")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
