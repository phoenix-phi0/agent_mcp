"""auth 包：注册、登录、退出。配合路由文件里的「认证 必须」用。

    用包 auth http

    接口 POST /auth/login 动作 auth_login 公开
      设 user = 登录 app.db user_by_name {request}
      如果 {用户} 为空
        返回 {"error":"用户名或密码不对"} 400
      结束
      消息 系统 已登录 ok
    结束

## 为什么是这种形状

**动词收整个 {request}，不收一个个参数。** 动词参数按空格切，密码里有
空格就会被切开；而且把密码拆成脚本变量传来传去，它就会出现在日志、
报错信息里。整个字典交进来，密码只在这个文件的 Python 里出现。

**动词只提出登录/退出要求，cookie 由路由器设。** 签名密钥、cookie 的
HttpOnly/SameSite 这些属性集中在路由器一处，不散在动词里。

**登录失败不区分「没这个人」和「密码错」**，返回同样的空串；没这个人时
也照样算一次哈希，让两种情况花的时间差不多——不然能枚举出哪些用户名
存在。

**登录限流**：同一用户名或同一来源连续失败 5 次锁 5 分钟（tools/auth.py 的
LIMITER）。锁住时「登录」抛 429「登录失败次数太多」，不管用户名存不存在、
密码对不对都一样。

**管理员建号、重置密码、自己改密码**（教师给学生建账号这类不开放注册的项目）：

    建用户   app.db user_create {request}            不登录，返回用户名或 [出错]…
    重置密码 app.db user_set_password {request}      按 username 改，接口自己加「角色」
    改密码   app.db user_by_name user_set_password {request}
             只改 {current_user} 自己的：先核对 old_password，再写 new_password

user_create 的参数是请求里的全部字段（display_name、role……）加上算好的
password_hash；明文 password 不交给 SQL。
"""

import json
import re
import sqlite3
from pathlib import Path

# 加载时注入
WORKSPACE = Path(".")
PACK_DIR = Path(".")

# 用户名规则、密码最短长度在 tools/auth.py（kg 的命令行建教师也用）
from tools.auth import MIN_PASSWORD, USERNAME_RE  # noqa: E402


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

    @reg.verb("注册一个用户并直接登录。收整个 {request}，要有 username 和 "
              "password。成功返回用户名，失败返回 [出错] 开头的说明。"
              "例如 注册用户 app.db user_insert {request}")
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

    @reg.verb("核对用户名和密码，对了就登录。收整个 {request}。成功返回用户名，"
              "失败返回空串（不区分没这个人和密码错）。同一用户名或来源连续失败 "
              "5 次锁 5 分钟（抛 429）。"
              "例如 登录 app.db user_by_name {request}")
    def 登录(库: str, 语句名: str, 参数表) -> str:
        from tools.auth import LIMITER, dummy_verify, verify_password
        from tools.db_errors import ClientError
        from tools.http_ctx import current_remote, request_auth

        form = as_dict(参数表)
        name = str(form.get("username") or "").strip()
        password = str(form.get("password") or "")
        keys = [(str(workspace), "name", name.lower())]
        if current_remote():
            keys.append((str(workspace), "remote", current_remote()))
        if LIMITER.locked(keys):
            raise ClientError("登录失败次数太多，请 5 分钟后再试", 429)
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
            LIMITER.fail(keys)
            return ""
        # 查询返回 (username, password_hash)
        if not verify_password(password, row[1]):
            LIMITER.fail(keys)
            return ""
        LIMITER.ok(keys)
        request_auth({"login": row[0]})
        return row[0]

    def write(库: str, 语句名: str, params: dict) -> int:
        sql = load_sql(语句名)
        # SQL 里用到、请求里没给的参数补 None：可选字段（显示名）没填时，
        # sqlite 报「没给 :display_name」比存成空更让人摸不着头脑
        for k in re.findall(r"(?<![:\w]):([A-Za-z_]\w*)", sql):
            params.setdefault(k, None)
        con = connect(库)
        try:
            cur = con.execute(sql, params)
            con.commit()
            return cur.rowcount
        finally:
            con.close()

    @reg.verb("管理员建一个用户，不登录。收整个 {request}，要有 username、password，"
              "其余字段（display_name、role……）原样交给 SQL。成功返回用户名，失败返回 "
              "[出错] 开头的说明。例如 建用户 app.db user_create {request}")
    def 建用户(库: str, 语句名: str, 参数表) -> str:
        from tools.auth import hash_password

        form = as_dict(参数表)
        name = str(form.get("username") or "").strip()
        password = str(form.get("password") or "")
        if not USERNAME_RE.match(name):
            return "[出错] 用户名只能用字母、数字、汉字和 _ . @ -，不能有空格，最长 40"
        if len(password) < MIN_PASSWORD:
            return f"[出错] 密码至少 {MIN_PASSWORD} 位"
        params = {k: v for k, v in form.items()
                  if k not in ("password", "old_password", "new_password")
                  and isinstance(v, (str, int, float, type(None)))}
        params.update(username=name, password_hash=hash_password(password))
        try:
            write(库, 语句名, params)
        except sqlite3.IntegrityError:
            return "[出错] 用户名已被占用"
        except (ValueError, sqlite3.Error) as e:
            return f"[出错] {e}"
        return name

    @reg.verb("管理员重置某个用户的密码。收整个 {request}，要有 username 和 new_password"
              "（或 password）。"
              "成功返回用户名，失败返回 [出错] 开头的说明。只管写，谁能调由接口的"
              "「角色」管。例如 重置密码 app.db user_set_password {request}")
    def 重置密码(库: str, 语句名: str, 参数表) -> str:
        from tools.auth import hash_password

        form = as_dict(参数表)
        name = str(form.get("username") or "").strip()
        password = str(form.get("new_password") or form.get("password") or "")
        if not name:
            return "[出错] 缺用户名"
        if len(password) < MIN_PASSWORD:
            return f"[出错] 密码至少 {MIN_PASSWORD} 位"
        try:
            n = write(库, 语句名, {"username": name,
                                  "password_hash": hash_password(password)})
        except (ValueError, sqlite3.Error) as e:
            return f"[出错] {e}"
        return name if n else "[出错] 没有这个用户"

    @reg.verb("登录的人改自己的密码：核对 old_password，再写 new_password（给了 "
              "new_password2 就要两次一样）。用户名只认 "
              "{current_user}，请求体里的 username 不算。成功返回用户名，失败返回 [出错]… "
              "例如 改密码 app.db user_by_name user_set_password {request}")
    def 改密码(库: str, 查询名: str, 语句名: str, 参数表) -> str:
        from tools.auth import hash_password, verify_password
        from tools.http_ctx import current_user

        form = as_dict(参数表)
        name = current_user()
        old = str(form.get("old_password") or "")
        new = str(form.get("new_password") or "")
        if not name:
            return "[出错] 先登录"
        if len(new) < MIN_PASSWORD:
            return f"[出错] 新密码至少 {MIN_PASSWORD} 位"
        if "new_password2" in form and str(form.get("new_password2") or "") != new:
            return "[出错] 两次输入的新密码不一样"
        try:
            con = connect(库)
            try:
                row = con.execute(load_sql(查询名), {"username": name}).fetchone()
            finally:
                con.close()
        except (ValueError, sqlite3.Error) as e:
            return f"[出错] {e}"
        if row is None or not verify_password(old, row[1]):
            return "[出错] 旧密码不对"
        try:
            write(库, 语句名, {"username": name, "password_hash": hash_password(new)})
        except (ValueError, sqlite3.Error) as e:
            return f"[出错] {e}"
        return name

    @reg.verb("退出登录（删掉登录 cookie）。")
    def 退出登录() -> str:
        from tools.http_ctx import request_auth

        request_auth({"logout": True})
        return "ok"
