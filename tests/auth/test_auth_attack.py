# -*- coding: utf-8 -*-
"""认证的攻击和边界测试。test_auth.py 测正常路径和几种明显的伪造，
这里测更刁钻的。

    cd /home/ysc/mcp && .venv/bin/python tests/auth/test_auth_attack.py

  一、SQL 注入：登录框、标题里塞注入串
  二、改自己的记录时顺手把 owner 改成别人
  三、A 项目的令牌拿到 B 项目用
  四、奇怪的输入：中文密码、超长密码、缺字段、值是数组、请求体不是 JSON
  五、用户名大小写：Alice 和 alice 是不是两个人
  六、已知限制：用户被删了，令牌在过期前照样能用（只记录，不算失败）
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gen.project import add_auth, ensure_db, generate, init, make_app  # noqa: E402
from tools.auth import COOKIE, make_token, secret_for                  # noqa: E402

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


def make_project(base: Path, name: str):
    root = base / name
    init(root, sample=False)
    add_auth(root)
    (root / "entities" / "note.entity").write_text(NOTE, encoding="utf-8")
    generate(root, "private")
    ensure_db(root)
    app, _ = make_app(root, real=False)
    return root, app


def post(client, path, **form):
    r = client.post(path, json={"form": form})
    return r.status_code, (r.get_json(silent=True) or {}), r


def with_cookie(app, token, path="/note/list", **form):
    c = app.test_client()
    try:
        c.set_cookie(COOKIE, token)
    except TypeError:
        c.set_cookie("localhost", COOKIE, token)
    return post(c, path, **form)


def main():
    base = Path(tempfile.mkdtemp(prefix="attack_"))
    root, app = make_project(base, "a")

    def db(sql, *args):
        con = sqlite3.connect(root / "app.db")
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    alice = app.test_client()
    post(alice, "/auth/register", username="alice", password="alicepass")
    post(alice, "/note/create", title="alice 的", body="")

    print("一、SQL 注入")
    for bad in ["' OR '1'='1", "alice' --", "alice'; DROP TABLE user; --"]:
        st, body, r = post(app.test_client(), "/auth/login", username=bad, password="x' OR '1'='1")
        check(st == 400 and COOKIE not in r.headers.get("Set-Cookie", ""),
              f"登录框里的注入串被当成普通字符串，登录失败：{bad!r}")
    check(len(db("SELECT * FROM user")) == 1, "user 表还在，只有 alice")
    st, body, r = post(app.test_client(), "/auth/register", username="x' OR 1=1 --", password="123456")
    check(st == 400, "带引号和空格的用户名注册被拒（用户名规则挡住的）")
    title = "a'); DELETE FROM note; --"
    st, _, _ = post(alice, "/note/create", title=title, body="")
    check(st == 200 and (title,) in db("SELECT title FROM note"),
          "标题里的注入串原样存进去了，note 表没被删")

    print("二、改自己的记录时顺手改 owner")
    post(alice, "/auth/logout")
    bob = app.test_client()
    post(bob, "/auth/register", username="bob", password="bobpass1")
    post(bob, "/note/create", title="bob 的", body="")
    bob_id = db("SELECT id FROM note WHERE owner='bob'")[0][0]
    st, _, _ = post(bob, "/note/update", id=bob_id, title="bob 改过", body="", owner="alice")
    check(st == 200, f"bob 改自己的记录成功：{st}")
    check(db("SELECT title, owner FROM note WHERE id=?", bob_id) == [("bob 改过", "bob")],
          "标题改了，owner 还是 bob——SET 里根本没有 owner")
    st, body, _ = post(alice, "/note/list")
    post(alice, "/auth/login", username="alice", password="alicepass")
    st, body, _ = post(alice, "/note/list")
    check("bob 改过" not in str(body), "alice 的列表里没有 bob 那条")

    print("三、A 项目的令牌拿到 B 项目")
    root_b, app_b = make_project(base, "b")
    token_a = make_token("alice", secret_for(root))
    check(with_cookie(app, token_a)[0] == 200, "在 A 项目里能用（对照）")
    check(with_cookie(app_b, token_a)[0] == 401, "到 B 项目 401——每个项目的密钥不同")
    check(secret_for(root) != secret_for(root_b), "两个项目的密钥确实不一样")

    print("四、奇怪的输入")
    c = app.test_client()
    st, _, _ = post(c, "/auth/register", username="张三", password="密码是中文的口令")
    check(st == 200, f"中文用户名、中文密码能注册：{st}")
    c2 = app.test_client()
    st, _, _ = post(c2, "/auth/login", username="张三", password="密码是中文的口令")
    check(st == 200, "中文密码能登录")
    long_pw = "长" * 2000
    st, _, _ = post(app.test_client(), "/auth/register", username="long", password=long_pw)
    c3 = app.test_client()
    st2, _, _ = post(c3, "/auth/login", username="long", password=long_pw)
    check(st == 200 and st2 == 200, "两千个字的密码能注册也能登录")
    st, body, _ = post(app.test_client(), "/auth/register")
    check(st == 400, f"注册缺字段：{st} {body}")
    st, body, _ = post(app.test_client(), "/auth/login")
    check(st == 400, f"登录缺字段：{st} {body}")
    st, body, _ = post(alice, "/note/create", title=["数", "组"], body={"x": 1})
    check(st < 500, f"值是数组/对象不崩：{st}")
    r = alice.post("/note/list", data="这不是 JSON", content_type="text/plain")
    check(r.status_code < 500, f"请求体不是 JSON 不崩：{r.status_code}")
    r = alice.post("/note/list", data="{坏的", content_type="application/json")
    check(r.status_code < 500, f"JSON 是坏的不崩：{r.status_code}")
    r = app.test_client().post("/note/list", data="{坏的", content_type="application/json")
    check(r.status_code == 401, "没登录时坏请求也是 401，检查在读请求体之前")

    print("五、用户名大小写")
    st, _, _ = post(app.test_client(), "/auth/register", username="Alice", password="another1")
    check(st == 200, "Alice 能注册——区分大小写，跟 alice 是两个人")
    upper = app.test_client()
    post(upper, "/auth/login", username="Alice", password="another1")
    st, body, _ = post(upper, "/note/list")
    check((body.get("lists") or {}).get("notes") == [], "Alice 看不到 alice 的数据")

    print("六、已知限制（只记录）")
    token = make_token("bob", secret_for(root))
    con = sqlite3.connect(root / "app.db")
    con.execute("DELETE FROM user WHERE username='bob'")
    con.commit()
    con.close()
    st, _, _ = with_cookie(app, token)
    print(f"    用户 bob 从库里删掉之后，他的令牌{'照样能用' if st == 200 else '失效了'}（{st}）"
          "——令牌是无状态的，服务器不查库。要能吊销得改成服务器端存会话表。")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
