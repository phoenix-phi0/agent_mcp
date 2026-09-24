"""auth 包：注册、登录、退出。配合路由文件里的「认证 必须」用。

    用包 auth http

    接口 POST /auth/login 动作 auth_login 公开
      设 用户 = 登录 app.db user_by_name {请求}
      如果 {用户} 为空
        返回 {"error":"用户名或密码不对"} 400
      结束
      消息 系统 已登录 ok
    结束

## 为什么是这种形状

**动词收整个 {请求}，不收一个个参数。** 动词参数按空格切，密码里有
空格就会被切开；而且把密码拆成脚本变量传来传去，它就会出现在日志、
报错信息里。整个字典交进来，密码只在这个文件的 Python 里出现。

**动词只提出登录/退出要求，cookie 由路由器设。** 签名密钥、cookie 的
HttpOnly/SameSite 这些属性集中在路由器一处，不散在动词里。

**登录失败不区分「没这个人」和「密码错」**，返回同样的空串；没这个人时
也照样算一次哈希，让两种情况花的时间差不多——不然能枚举出哪些用户名
存在。
"""

import json
import re
import sqlite3
from pathlib import Path

# 加载时注入
WORKSPACE = Path(".")
PACK_DIR = Path(".")

# 用户名不许有空格：它会被当成 {当前用户} 传进「查询 … 当前用户={当前用户}」
# 这类按空格切的动词参数里。
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@\-\u4e00-\u9fff]{1,40}$")
MIN_PASSWORD = 6


def register(reg, workspace):
    workspace = Path(workspace).resolve()
    project_root = PACK_DIR.parent.parent

    def safe(path: str) -> Path:
        p = (workspace / path).resolve()
        if p != workspace and workspace not in p.parents:
            raise ValueError(f"路径越界：{path}")
        return p

    def load_sql(name: str) -> str:
        # 跟 db 包同一个规则：workspace 下有 queries/ 就用它，没有退回项目根
        qdir = workspace / "queries"
        if not qdir.is_dir():
            qdir = project_root / "queries"
        f = (qdir / f"{name}.sql").resolve()
        if qdir.resolve() not in f.parents or not f.is_file():
            raise ValueError(f"没有查询：{name}")
        return f.read_text(encoding="utf-8")

    def as_dict(arg) -> dict:
        if isinstance(arg, dict):
            return arg
        try:
            d = json.loads(arg)
        except (TypeError, json.JSONDecodeError):
            return {}
        return d if isinstance(d, dict) else {}

    def connect(db: str) -> sqlite3.Connection:
        con = sqlite3.connect(safe(db))
        con.execute("PRAGMA foreign_keys = ON")
        return con

    @reg.verb("注册一个用户并直接登录。收整个 {请求}，要有 username 和 "
              "password。成功返回用户名，失败返回 [出错] 开头的说明。"
              "例如 注册用户 app.db user_insert {请求}")
    def 注册用户(库: str, 语句名: str, 参数表) -> str:
        from tools.auth import hash_password
        from tools.http_ctx import request_auth

        form = as_dict(参数表)
        name = str(form.get("username") or "").strip()
        password = str(form.get("password") or "")
        if not USERNAME_RE.match(name):
            return "[出错] 用户名只能用字母、数字、汉字和 _ . @ -，不能有空格，最长 40"
        if len(password) < MIN_PASSWORD:
            return f"[出错] 密码至少 {MIN_PASSWORD} 位"
        try:
            sql = load_sql(语句名)
            con = connect(库)
            try:
                con.execute(sql, {"username": name,
                                  "password_hash": hash_password(password)})
                con.commit()
            finally:
                con.close()
        except sqlite3.IntegrityError:
            return "[出错] 用户名已被占用"
        except (ValueError, sqlite3.Error) as e:
            return f"[出错] {e}"
        request_auth({"login": name})
        return name

    @reg.verb("核对用户名和密码，对了就登录。收整个 {请求}。成功返回用户名，"
              "失败返回空串（不区分没这个人和密码错）。"
              "例如 登录 app.db user_by_name {请求}")
    def 登录(库: str, 语句名: str, 参数表) -> str:
        from tools.auth import dummy_verify, verify_password
        from tools.http_ctx import request_auth

        form = as_dict(参数表)
        name = str(form.get("username") or "").strip()
        password = str(form.get("password") or "")
        try:
            sql = load_sql(语句名)
            con = connect(库)
            try:
                row = con.execute(sql, {"username": name}).fetchone()
            finally:
                con.close()
        except (ValueError, sqlite3.Error):
            return ""
        if row is None:
            dummy_verify(password)
            return ""
        # 查询返回 (username, password_hash)
        if not verify_password(password, row[1]):
            return ""
        request_auth({"login": row[0]})
        return row[0]

    @reg.verb("退出登录（删掉登录 cookie）。")
    def 退出登录() -> str:
        from tools.http_ctx import request_auth

        request_auth({"logout": True})
        return "ok"
