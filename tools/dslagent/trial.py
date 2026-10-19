"""试调检查（程序，不调模型）：接口文件通过静态检查后，在项目副本里真调一遍新接口。

做法：
- 把项目拷到临时目录（不带 app.db / 会话 / 前端产物），按实体定义建一个空库；
- 按实体给每个表造几行合成数据（外键指向已造好的行、枚举取选项、必填都有值、唯一列各不相同）；
- 路由器用 tools.dsl_http.Router（mock 模式，不碰真模型），Flask 测试客户端调接口；开着登录的项目为每个角色造一个合成账号
  （user 表里 trial_<角色>，role=角色），按接口的「角色」带上对应令牌，没写角色的按每个角色各调一遍，公开接口不带令牌；
- 每个接口按单文件计划的入参调：必填给值；计划标了「可选入参」的再分别「不传」「传空串」各调一遍；每次调用前库恢复成造数后的样子。

判定（只看接口自己的毛病，业务 4xx 算正常）：
- 500（含「接口出错」「脚本出错」）→ 不过；
- 接口项带「响应」（接口约定）时，200 的响应缺约定里的 state / lists 键或 messages → 不过；约定里列的业务错误码与 403 / 404 等 4xx 都算正常；
- 数据库约束错误（外键 / 非空 / 唯一 / 其它 IntegrityError，不管回 409 还是 400）→ 不过。靠 hook 住 tools.db_errors.translate 认，
  手写的 `返回 {...} 409` 不会误伤；
- 400 参数错、401/403、404 查无此项、502 模型没回应 → 正常。
不过的报错带接口、方法、入参、角色、状态码和响应原话，供重写时带回。
"""
import contextlib
import io
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

LIMIT_OPT = 5               # 一个接口最多对这么多个可选入参分别试
RESP_CHARS = 300
SKIP_DIRS = {"sessions", "web", "node_modules", ".git", "__pycache__"}
SKIP_FILES = {".auth_secret"}
IDENT_NAMES = {"username", "user", "learner", "student", "teacher", "owner", "current_user", "account", "user_name"}


# ================================================================== 造数

def _val(f, ent, i, taken):
    """第 i 行（从 1 起）某列的合成值。"""
    t = f.type
    if f.options:
        return f.options[(i - 1) % len(f.options)]
    if t == "整数":
        return i
    if t == "小数":
        return i + 0.5
    if t == "布尔":
        return 1 if i % 2 else 0
    if t == "日期":
        return f"2026-01-{i:02d} 00:00:00"
    if t in ("文件", "多文件"):
        return f"files/{ent}_{f.name}_{i}.txt"
    return f"{ent}_{f.name}_{i}"


def seed(db, entities, roles, rows=3, text=None):
    """建空库 + 造数。每表 rows+1 行：前 rows 行互相引用，最后一行是「备用行」没人引用——要新建带唯一约束的记录时，
    入参取备用行的值（pick），免得拿现成的值去撞唯一约束把合成数据的毛病算成接口的。返回 ({表: [{列: 值}…]}, {角色: 用户名})。"""
    from tools.entity import order, render_sql
    sql = render_sql(text, strict=True)
    con = sqlite3.connect(db)
    data, accounts = {}, {r: f"trial_{r}" for r in roles}
    try:
        con.executescript(sql)
        con.execute("PRAGMA foreign_keys=OFF")
        for e in order(entities):
            n = max(rows + 1, len(roles)) if e.name == "user" else rows + 1
            tab = data.setdefault(e.name, [])
            for i in range(1, n + 1):
                row = {}
                for f in e.fields:
                    if f.system and f.default:
                        continue
                    if f.default and not f.required and not f.ref:
                        continue
                    if f.ref:
                        target = next((x for x in entities if x.name == f.ref), None)
                        rs = data.get(f.ref) or []
                        key = target.key_name if target else "id"
                        m_ = min(rows, len(rs))
                        row[f.name] = (rs[(i - 1) % m_].get(key, ((i - 1) % m_) + 1) if rs else i)
                    else:
                        row[f.name] = _val(f, e.name, i, None)
                if e.name == "user":
                    if "username" in row:
                        row["username"] = (list(accounts.values()) + [f"trial_u{k}" for k in range(1, n + 1)])[i - 1]
                    if "role" in row and i <= len(roles):
                        row["role"] = roles[i - 1]
                    elif "role" in row and e.field("role") and not e.field("role").options:
                        row["role"] = roles[0] if roles else row["role"]
                for f in e.fields:               # 属主列：第一行属第一个合成账号，免得「只看自己的」查询全空
                    if f.name == "owner" and accounts and f.name in row:
                        row[f.name] = list(accounts.values())[(i - 1) % len(accounts)]
                cols = list(row)
                if cols:
                    con.execute(f"INSERT INTO {e.name}({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [row[c] for c in cols])
                else:
                    con.execute(f"INSERT INTO {e.name} DEFAULT VALUES")
                if e.has_implicit_id:
                    row["id"] = i
                tab.append(row)
        con.commit()
    finally:
        con.close()
    return data, accounts


# ================================================================== 入参取值

def _uniq_cols(entities):
    """{(实体名, 列名)}：单列唯一的列，和「唯一 a b」组里的列。"""
    out = set()
    for e in entities:
        for f in e.fields:
            if f.unique:
                out.add((e.name, f.name))
        for g in e.uniques:
            out |= {(e.name, c) for c in g}
    return out


def pick(name, data, accounts, entities, user):
    """某个入参的合成值：先看是不是实体列（取第 1 行的值；带唯一约束的列取备用行 / 新值，免得新建时撞唯一），再看 *_id / id / 账号名。"""
    if name in IDENT_NAMES or name == "current_user":
        return user or (next(iter(accounts.values()), "trial_user"))
    if name == "id":
        return 1
    uq = _uniq_cols(entities)
    for e in entities:
        rows = data.get(e.name) or []
        if rows and name in rows[0]:
            f = e.field(name)
            if (e.name, name) in uq and f is not None and not f.options:
                if f.ref or f.type in ("整数", "小数"):
                    return rows[-1][name]
                return f"{rows[0][name]}_新"
            return rows[0][name]
    if name.endswith("_id"):
        return 1
    if name in ("limit", "n", "count", "page", "size", "num", "number", "score", "level", "rank", "offset"):
        return 1
    if name.startswith(("is_", "has_")):
        return 1
    return f"试调_{name}"


# ================================================================== 调用

class _Hook:
    """hook 住 tools.db_errors.translate：任何被翻译成 ClientError 的 IntegrityError 都记下来。"""

    def __init__(self):
        self.hits = []

    def __enter__(self):
        import tools.db_errors as DE
        self.DE, self.orig = DE, DE.translate

        def wrapped(exc, workspace):
            ce = self.orig(exc, workspace)
            self.hits.append(f"{ce.status} {ce.message}（{exc}）")
            return ce
        DE.translate = wrapped
        return self

    def __exit__(self, *a):
        self.DE.translate = self.orig
        return False


def copy_project(root, dst):
    root = Path(root)

    def ignore(d, names):
        return [n for n in names if (n in SKIP_DIRS and Path(d) == root) or n in SKIP_FILES or n.endswith((".db", ".db-journal", ".pyc"))]
    shutil.copytree(root, dst, ignore=ignore)


def _variants(ins, opts):
    """[(说明, 要传的键集合, 值覆盖)]：全给；每个可选入参分别不传 / 传空串。"""
    out = [("入参全给", list(ins), {})]
    for o in [x for x in ins if x in opts][:LIMIT_OPT]:
        out.append((f"可选入参 {o} 不传", [k for k in ins if k != o], {}))
        out.append((f"可选入参 {o} 传空串", list(ins), {o: ""}))
    return out


def _short(x):
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
    s = s.replace("\n", " ")
    return s[:RESP_CHARS] + ("…" if len(s) > RESP_CHARS else "")


def run(root, items_by_file, rows=3):
    """root：项目目录（不会被改）；items_by_file：{接口文件相对路径: [单文件计划里的接口项]}。
    返回 {"problems": {文件: [报错…]}, "calls": 调用次数, "skipped": 没法试调的原因（空 = 正常）}。"""
    out = {"problems": {}, "calls": 0, "skipped": ""}
    tmp = Path(tempfile.mkdtemp(prefix="trial_"))
    try:
        try:
            _run(Path(root), tmp / "p", items_by_file, rows, out)
        except Exception as e:  # noqa: BLE001 -- 试调自己的毛病不当成接口的毛病
            out["skipped"] = f"{type(e).__name__}: {e}"[:300]
            out["problems"] = {}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def _run(root, ws, items_by_file, rows, out):
    from tools.dsl_http import Router, auth_config
    from tools.entity import parse

    copy_project(root, ws)
    ents_text = "\n\n".join(f.read_text(encoding="utf-8") for f in sorted((ws / "entities").glob("*.entity")))
    entities = parse(ents_text)
    cfg = auth_config(ws / "routes")
    login = bool(cfg["mandatory"] or cfg["optional"])
    roles = list(cfg["roles"])
    if login and not roles:
        ur = next((e for e in entities if e.name == "user"), None)
        f = ur.field("role") if ur else None
        roles = list(f.options) if f and f.options else (["student"] if f and f.default else [])
        if not roles:
            roles = sorted({it.get("角色") for its in items_by_file.values() for it in its if it.get("角色")})
    if login and not roles:
        roles = ["user"]
    db = ws / "app.db"
    data, accounts = seed(db, entities, roles if login else [], rows, ents_text)
    shutil.copyfile(db, ws / ".seed.db")
    router = Router(ws / "routes", ws, ws / "sessions", real=False, login=login)
    app = router.app()
    cl = app.test_client()
    from tools.auth import COOKIE, make_token
    for rel, items in items_by_file.items():
        for it in items:
            ep = router.table.get(("POST", it["路径"])) or next((v for (m, p), v in router.table.items() if p == it["路径"]), None)
            if ep is None:
                continue
            ins, opts = list(it.get("入参") or []), set(it.get("可选入参") or [])
            if login and not ep.public:
                who = [ep.role] if ep.role else list(roles)
            else:
                who = [None]
            for wi, role in enumerate(who):
                user = accounts.get(role, "") if (login and role) else ""
                for vi, (desc, keys, over) in enumerate(_variants(ins, opts)):
                    if wi and vi:
                        continue                   # 每个角色只全给一遍；可选入参的变体只用第一个角色
                    form = {k: pick(k, data, accounts, entities, user) for k in keys}
                    form.update(over)
                    shutil.copyfile(ws / ".seed.db", db)
                    cl.delete_cookie(COOKIE)
                    if user:
                        cl.set_cookie(COOKIE, make_token(user, router._secret()))
                    err = io.StringIO()
                    with _Hook() as hk, contextlib.redirect_stderr(err):
                        resp = cl.post(it["路径"], json={"form": form})
                    out["calls"] += 1
                    code, body = resp.status_code, resp.get_data(as_text=True)
                    why = ""
                    if hk.hits:
                        why = "数据库约束错误：" + hk.hits[0]
                    elif code >= 500 and code != 502:
                        why = "接口出错"
                    elif code == 200 and it.get("响应"):
                        miss = missing_keys(body, it["响应"])
                        if miss:
                            why = "响应缺约定里的键：" + "、".join(miss)
                    if why:
                        out["problems"].setdefault(rel, []).append(
                            f"[试调不过] {rel} 接口 POST {it['路径']}（{desc}"
                            f"{'；账号 ' + user + '（角色 ' + role + '）' if user else ''}）入参 {json.dumps(form, ensure_ascii=False)}"
                            f" → {code}：{why}；响应：{_short(body)}")
                        break                      # 同一接口同一角色一个报错够了
    return out


def missing_keys(body, spec):
    """约定的响应键（state / lists 里的键，messages=是）在 200 的响应里找不到的。键可在响应的 state / lists 下，也可直接在顶层（`返回 {...}` 的写法）。"""
    try:
        resp = json.loads(body)
    except ValueError:
        resp = None
    if not isinstance(resp, dict):
        resp = {}
    miss = []
    for grp in ("state", "lists"):
        sub = resp.get(grp) if isinstance(resp.get(grp), dict) else {}
        miss += [f"{grp}.{k}" for k in spec.get(grp, []) if k not in sub and k not in resp]
    if spec.get("messages") == "是" and not resp.get("messages"):
        miss.append("messages")
    return miss


def problems_flat(res):
    return [x for xs in res["problems"].values() for x in xs]
