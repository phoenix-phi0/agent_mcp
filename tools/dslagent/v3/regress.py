"""build.zs 末尾的两步（verbs/v3 的 全量回归 / 接口冒烟 是它们的壳）：

  全量回归   所有模块（含已完成、约定 hash 没变的）重新跑一次「加载检查 + 比对约定 + 跑用例」；
            不过的标未完成、记回归原因，按依赖分层重做（第一轮任务就带着这个原因），最多 2 轮，仍不过 终止 失败。
  接口冒烟   项目拷到临时目录、按全部 entities 建库，用 tools.dsl_http 的真实 Router（进程内 Flask 测试客户端）
            加载全部 routes / services；约定里每个接口取所调函数第一条正常用例，用 cases.seed_case 造的
            「同一份数据」各跑一次「直接调用」与「走 HTTP」，核对状态码与返回是否一致（结构不同算失败，
            值不同但结构一样只记备注——大概率是随机 / 时间字段）。不过的模块同全量回归的规则重做。

            多人模式（任一模块约定头部写了「认证 必须」或「认证 可选」）：起 Router 时 login=True；非公开接口
            先核对「不登录 401」，再按接口要求的角色补一个有这个角色的调用人账号登录，带着登录态再跑一次 HTTP
            （见 _make_actor / _login_cookie）。调用人账号只用来发请求，不是用例里本来就有的数据行。

两步共用 _redo_rounds：检查一遍所有模块 → 全过就通过；不过的标未完成、按 plan/top.zs 的依赖分层分组，
每层一次 并行执行「做一个模块」（带上这次查出的原因）→ 下一轮重新检查；2 轮都有模块不过就 终止 失败。
"""
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

from . import top as VT


def _accept_module(project, module, mods):
    """加载检查 + 比对约定 + 跑用例，三项都过才算过。→ (ok, 原因)。"""
    from ..packs.dslproj import cases as K
    from ..packs.dslproj import project as P
    probs = P.load_problems(project, module, mods)
    try:
        c, _ = P.load_contract(project, module)
    except P.ProjError as e:
        return False, f"约定加载失败：{e}"
    cmp = P.compare(project, module, c, mods)
    kr = K.run(project, module)
    parts = []
    if probs:
        parts.append("加载检查：" + "；".join(probs))
    if not cmp["一致"]:
        parts.append("比对约定：" + "；".join(cmp["差异"]))
    if not kr["全过"]:
        parts.append("跑用例：" + kr["原因"])
    return not parts, "\n".join(parts)


def _redo_rounds(ctx, eng, top, kind, check_all):
    """check_all() → {模块: (ok, 原因)}（每轮都重新算）。不过的 标记未完成 + 记验收，按依赖分层重做；
    最多 2 轮，第 2 轮仍有不过的就 抛 ScriptHalt 失败。全过返回 {"状态": "通过"}。"""
    from tools.dsl_core import ScriptHalt
    layers = VT.layers(top)
    for rnd in (1, 2):
        results = check_all()
        fails = {m: r for m, (ok, r) in results.items() if not ok}
        for m, r in fails.items():
            ctx.log("验收", 模块=m, 通过=False, 说明=f"{kind}：{r}"[:1500])
        if not fails:
            return {"状态": "通过", "轮数": rnd}
        for m in fails:
            ctx.unmark_done(m)
        if rnd == 2:
            lines = "\n".join(f"{m}：{r}" for m, r in fails.items())
            raise ScriptHalt("失败", f"{kind}两轮仍未通过：\n{lines}"[:2000], "")
        for layer in layers:
            group = [m for m in layer if m in fails]
            if not group:
                continue
            jobs = [{"脚本": "做一个模块", "参数": {"模块": m, "最多": "3", "末次模型": "opus", "起始原因": f"{kind}发现问题：{fails[m]}"}}
                    for m in group]
            sub = eng._sub_engine()
            sub.vars["_regress_jobs"] = jobs
            sub.run("用包 common v3\n设 rs = 并行执行 {_regress_jobs} 并发=" + str(min(3, len(jobs))) + "\n返回 {rs}\n")
            rs = sub.returned[0] if sub.returned else []
            bad = [r for r in rs if isinstance(r, dict) and r.get("status") != "成功"]
            if bad:
                lines = "\n".join(f"{(r.get('params') or {}).get('模块') or '?'}：{r.get('reason') or r.get('status')}" for r in bad)
                raise ScriptHalt("失败", f"{kind}重做未通过：\n{lines}"[:2000], "")
    return {"状态": "通过"}        # 理论上到不了这里（第 2 轮不过已经抛了）


def full_regression(ctx, eng, top):
    mods = [m["名"] for m in top["模块"]]

    def check_all():
        return {m: _accept_module(ctx.project, m, mods) for m in mods}
    return _redo_rounds(ctx, eng, top, "全量回归", check_all)


# ------------------------------------------------------------------ 接口冒烟

SMOKE_IGNORE = shutil.ignore_patterns(".*", "__pycache__", "node_modules", "venv", "env", "*.pyc", "*.db", "*.db-*", "sessions")


def _val(v):
    return "" if v == "空" else v


def _same_shape(a, b):
    """结构是否一致（类型、dict 的键集合、list 的长度），不比叶子的值——随机 / 时间字段靠这个放行。"""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return set(a) == set(b) and all(_same_shape(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same_shape(x, y) for x, y in zip(a, b))
    return True


def _first_case(c, fn):
    """约定里调了这个函数、不要求报错的第一条用例（接口冒烟只测「正常路径」）。"""
    for u in c["用例"]:
        if u["调用"] and u["调用"]["目标"] == fn and u["报错"] is None:
            return u
    return None


# ------------------------------------------------------------------ 多人模式：造调用人账号、拿登录态

ACTOR_PREFIX = "_smoke_actor"       # 造的调用人账号用户名前缀，一看就知道是冒烟造的，不跟用例数据撞


def _auth_table(ws, auth_check):
    """「认证 核对 库 查询名」的查询文本里 FROM 的表名；查不到返回 None。"""
    db, name = auth_check
    f = Path(ws) / "queries" / f"{name}.sql"
    if not f.is_file():
        return None
    m = re.search(r"\bFROM\s+(\w+)", f.read_text(encoding="utf-8"), re.I)
    return m.group(1) if m else None


def _login_endpoint(mods_contracts):
    """项目里找一个公开接口，调的函数名正好是「登录」（verbs/auth 包的约定写法：
    接口 POST /auth/login -> 登录 公开，函数收 username/password）。找不到返回 None。
    → (方法, 路径) 或 None。"""
    for c in mods_contracts.values():
        for i in c["接口"]:
            if i["公开"] and i["函数"] == "登录":
                return i["方法"], i["路径"]
    return None


class ActorError(Exception):
    """造不出调用人账号。missing_query=真：认证核对指的查询文件不存在（由 run_smoke 开头统一归到拥有认证核对的模块）。"""

    def __init__(self, why, missing_query=False):
        super().__init__(why)
        self.why = why
        self.missing_query = missing_query


def _missing_query_reason(q):
    return f"认证核对指的查询 {q}.sql 不存在，真实路由必 500"


def _make_actor(ws, db_path, auth, role):
    """造一个调用人账号（表在 认证 核对 指的库里——第一个参数，相对 ws；列至少有 username / password_hash，
    有角色要求再加 role 列；其他 NOT NULL 且无默认值的列补占位值）。→ (username, password)；造不出抛 ActorError。
    没有「认证 核对」时登录只认签名令牌，不查库——只要不需要角色，随便一个用户名都能登录（跟真实路由行为一致）。"""
    import random

    username = f"{ACTOR_PREFIX}_{role or 'any'}_{random.randrange(10 ** 9)}"
    password = "smoke_pw_1"
    if not auth["check"]:
        if role:
            raise ActorError(f"接口要求角色「{role}」，但项目没有「认证 核对」，查不到调用人的角色")
        return username, password
    db_name, q = auth["check"]
    table = _auth_table(ws, auth["check"])
    if table is None:
        if not (Path(ws) / "queries" / f"{q}.sql").is_file():
            raise ActorError(_missing_query_reason(q), missing_query=True)
        raise ActorError(f"认证核对的查询 {q}.sql 里找不到 FROM 表名，造不出调用人账号")
    db_file = Path(ws) / db_name
    if not db_file.is_file():
        raise ActorError(f"认证核对指的库文件 {db_name} 不存在（第一个参数要是库文件名，如 app.db）")
    con = sqlite3.connect(db_file)
    try:
        info = con.execute(f"PRAGMA table_info({table})").fetchall()
        cols = [r[1] for r in info]
        if not cols or "username" not in cols:
            raise ActorError(f"认证核对的表 {table} 在库 {db_name} 里不存在或没有 username 列，造不出调用人账号")
        from tools.auth import hash_password

        values = {"username": username}
        if "password_hash" in cols:
            values["password_hash"] = hash_password(password)
        if role:
            if "role" not in cols:
                raise ActorError(f"接口要求角色「{role}」，但认证核对的表 {table} 没有 role 列")
            values["role"] = role
        for _cid, name, typ, notnull, dflt, pk in info:
            if name in values or not notnull or dflt is not None or pk:
                continue
            numeric = bool(re.search(r"INT|REAL|NUM|FLOA|DOUB|BOOL", (typ or "").upper())) or "disabled" in name.lower()
            values[name] = 0 if numeric else "x"
        con.execute(f"INSERT INTO {table}({', '.join(values)}) VALUES({', '.join('?' * len(values))})",
                    list(values.values()))
        con.commit()
    except sqlite3.Error as e:
        raise ActorError(f"往认证核对的表 {table} 插入调用人账号失败：{e}")
    finally:
        con.close()
    return username, password


def _login_cookie(client, ws, username, password, login_ep):
    """拿这个账号的登录 cookie：优先走项目自己的公开登录接口（登录成功时它已经设好了 Set-Cookie，
    测试客户端自动收下）；接口不存在或登不上就直接签发（调路由层认证模块的签发函数，不走业务层）。"""
    from tools.auth import COOKIE, make_token, secret_for

    if login_ep:
        method, path = login_ep
        resp = client.open(path, method=method, json={"username": username, "password": password})
        if resp.status_code < 400 and client.get_cookie(COOKIE) is not None:
            return
    client.set_cookie(COOKIE, make_token(username, secret_for(Path(ws))))


def _smoke_one(ws, sql, module, iface, case, notes, auth, login, login_ep):
    """同一份种子数据上各跑一次「直接调用」与「走 HTTP」→ "" 或失败原因；notes 收集只记备注的软差异。
    多人模式（login=真）：非公开接口先核对「不登录 401」，再补一个有所需角色的调用人账号登录，带登录态再跑一次。"""
    from ..packs.dslproj import cases as K
    try:
        return _smoke_one_inner(ws, sql, module, iface, case, notes, auth, login, login_ep)
    finally:
        K.clear_case_files(ws, case)


def _smoke_one_inner(ws, sql, module, iface, case, notes, auth, login, login_ep):
    from ..packs.dslproj import cases as K
    why = K.seed_case(ws, sql, module, case)
    tag = f"{module} {iface['方法']} {iface['路径']}"
    if why:
        return f"{tag}：造数据失败：{why}"
    db = Path(ws) / "app.db"
    seed = db.read_bytes()
    try:
        eng = K.make_engine(ws)
        r, err = K.call(eng, module, case["调用"]["目标"], case["调用"]["参数"], "smoke")
        K.settle()
    except TimeoutError as e:
        return f"{tag}：直接调用超时：{e}"
    except Exception as e:  # noqa: BLE001
        return f"{tag}：直接调用出错：{type(e).__name__}: {e}"
    direct_status = 200 if err in ("", None) else err.get("code")
    direct_body = r if err in ("", None) else {"error": err.get("error")}

    def restore_seed():
        db.write_bytes(seed)
        for suf in ("-wal", "-shm", "-journal"):
            try:
                Path(str(db) + suf).unlink()
            except OSError:
                pass

    protected = login and not iface["公开"]
    restore_seed()
    try:
        from tools.dsl_http import Router
        router = Router(Path(ws) / "routes", Path(ws), Path(ws) / "sessions", real=False, login=login)
        client = router.app().test_client()
        args = {k: _val(v) for k, v in case["调用"]["参数"].items()}

        def call():
            if iface["方法"] == "GET":
                return client.get(iface["路径"], query_string=args)
            return client.open(iface["路径"], method=iface["方法"], json=args)

        if protected:
            resp0 = call()
            if resp0.status_code != 401:
                return f"{tag}：不登录应该 401，实际 {resp0.status_code}"
            try:
                actor = _make_actor(ws, db, auth, iface["角色"])
            except ActorError as e:
                if e.missing_query:
                    return ""       # 已由 run_smoke 开头归到拥有「认证 核对」的模块，这里不重复记
                return f"{tag}：造不出调用人账号（角色「{iface['角色'] or '（任意已登录）'}」）：{e.why}"
            _login_cookie(client, ws, actor[0], actor[1], login_ep)
            resp = call()
        else:
            resp = call()
        K.settle()
    except TimeoutError as e:
        return f"{tag}：HTTP 调用超时：{e}"
    except Exception as e:  # noqa: BLE001
        return f"{tag}：HTTP 调用出错：{type(e).__name__}: {e}"
    http_status = resp.status_code
    http_body = resp.get_json(silent=True)
    if direct_status != http_status:
        return f"{tag}：状态码不一致（直接调用 {direct_status}，HTTP {http_status}）"
    if direct_body != http_body:
        if not _same_shape(direct_body, http_body):
            return f"{tag}：返回结构不一致（直接调用 {direct_body!r}，HTTP {http_body!r}）"
        notes.append(f"{tag}：返回值不同、结构一致（记为随机 / 时间字段）：直接调用 {direct_body!r}，HTTP {http_body!r}")
    return ""


def _check_migrate(ws, sql, contracts, reasons):
    """「学习记录」表的老库迁移：拿掉这些表模拟老库 → 跑迁移该补齐 → 再跑一次该是空操作。查出的问题记进 reasons
    （归到拥有这张表的模块）。没有「学习记录」表，或 routes/ 没开「迁移 只加」就什么都不做。"""
    owners = {}
    for m, c in contracts.items():
        for t in c["表"]:
            if t.get("学习记录"):
                owners[t["名"]] = m
    if not owners:
        return
    import tools.migrate as MG
    if not MG.switch_on(ws / "routes"):
        for m in set(owners.values()):
            reasons.setdefault(m, []).append("模块有「学习记录」标注的表，但 routes/ 下没有「迁移 只加」声明")
        return
    tables, indexes = MG._statements(sql)
    old_tables = {k: v for k, v in tables.items() if k not in owners}
    old_indexes = []
    for ix in indexes:
        m = re.search(r"\bON\s+(\w+)", ix, re.I)
        if not (m and m.group(1) in owners):
            old_indexes.append(ix)
    old_sql = (";\n".join(list(old_tables.values()) + old_indexes) + ";\n") if (old_tables or old_indexes) else ""
    from ..packs.dslproj import cases as K
    K.reset_db(ws, old_sql)
    db = ws / "app.db"
    r1 = MG.migrate_additive(db, ws / "entities")
    missing = set(owners) - set(r1.get("tables") or [])
    if missing:
        for name in missing:
            reasons.setdefault(owners[name], []).append(f"老库补迁移没有把「学习记录」表「{name}」补齐")
        return
    r2 = MG.migrate_additive(db, ws / "entities")
    if r2.get("tables") or r2.get("columns") or r2.get("indexes"):
        for m in set(owners.values()):
            reasons.setdefault(m, []).append(f"迁移补齐老库后再跑一次应是空操作，实际又有变化：{r2}")


def run_smoke(project, mods):
    """→ ({模块: (ok, 原因)}, 备注列表)。project 不被改动（在临时拷贝里跑）。"""
    from ..packs.dslproj import cases as K
    from ..packs.dslproj import project as P
    project = Path(project)
    tmp = Path(tempfile.mkdtemp(prefix="dslagent_smoke_"))
    notes = []
    try:
        ws = tmp / "p"
        shutil.copytree(project, ws, ignore=SMOKE_IGNORE, symlinks=True)
        try:
            sql = K.build_sql(ws, mods)
        except Exception as e:  # noqa: BLE001
            why = f"建库失败：{type(e).__name__}: {e}"
            return {m: (False, why) for m in mods}, notes
        reasons = {}
        contracts = {}
        for m in mods:
            try:
                contracts[m], _ = P.load_contract(project, m)
            except P.ProjError as e:
                reasons.setdefault(m, []).append(f"约定加载失败：{e}")
        from tools.dsl_http import auth_config
        auth = auth_config(ws / "routes")
        login = bool(auth["mandatory"] or auth["optional"])
        login_ep = _login_endpoint(contracts) if login else None
        _check_migrate(ws, sql, contracts, reasons)
        if login and auth["check"]:
            q = auth["check"][1]
            if not (ws / "queries" / f"{q}.sql").is_file():
                owners = [m for m, c in contracts.items() if list(c["认证"]["核对"] or []) == list(auth["check"])]
                for m in owners or mods[:1]:
                    reasons.setdefault(m, []).append(_missing_query_reason(q))
        for m, c in contracts.items():
            for iface in c["接口"]:
                if iface.get("上传"):          # B2 之前约定里不会有这个字段，先占位
                    notes.append(f"{m} {iface['方法']} {iface['路径']}：上传接口暂跳过（留给 B2）")
                    continue
                case = _first_case(c, iface["函数"])
                if case is None:
                    notes.append(f"{m} {iface['方法']} {iface['路径']}：没有 {iface['函数']} 的正常用例，跳过")
                    continue
                why = _smoke_one(ws, sql, m, iface, case, notes, auth, login, login_ep)
                if why:
                    reasons.setdefault(m, []).append(why)
        return {m: (m not in reasons, "；".join(reasons.get(m, []))) for m in mods}, notes
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def interface_smoke(ctx, eng, top):
    mods = [m["名"] for m in top["模块"]]
    all_notes = []

    def check_all():
        results, notes = run_smoke(ctx.project, mods)
        all_notes.extend(notes)
        return results
    r = _redo_rounds(ctx, eng, top, "接口冒烟", check_all)
    if all_notes:
        ctx.log("验收", 模块="_接口冒烟", 通过=True, 说明="备注：\n" + "\n".join(all_notes)[:1500])
    return r
