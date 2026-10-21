"""build.zs 末尾两步的检查实现（verbs/v3 的 全量回归 / 接口冒烟 是它们的壳）：

  全量回归   对有代码的模块跑「加载检查 + 比对约定 + 跑用例」，只报告。
  接口冒烟   项目拷到临时目录、按全部 entities 建库，用 tools.dsl_http 的真实 Router（进程内 Flask 测试客户端）
            加载全部 routes / services；约定里每个接口取所调函数第一条正常用例，用 cases.seed_case 造的
            「同一份数据」各跑一次「直接调用」与「走 HTTP」，核对状态码与返回是否一致（结构不同算失败，
            值不同但结构一样只记备注——大概率是随机 / 时间字段）。只报告。

            多人模式（任一模块约定头部写了「认证 必须」或「认证 可选」）：起 Router 时 login=True；非公开接口
            先核对「不登录 401」，再按接口要求的角色补一个有这个角色的调用人账号登录，带着登录态再跑一次 HTTP
            （见 _make_actor / _login_cookie）。调用人账号只用来发请求，不是用例里本来就有的数据行。

两个检查都不重做模块、不改 state：不过的模块怎么重做由 plan/build.zs 里的 .zs 流程写出来
（检查 → 按依赖分层重做不过的模块 → 再检查，最多 2 轮，仍不过 终止 失败）。
"""
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path


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
    reasons, notes = smoke_detail(project, mods)
    return {m: (m not in reasons, "；".join(reasons.get(m, []))) for m in mods}, notes


def smoke_detail(project, mods):
    """→ ({模块: [不过的原因（每个接口 / 每项检查一条）]}（过了的模块没有键）, 备注列表)。run_smoke 是它的汇总形式。"""
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
            return {m: [why] for m in mods}, notes
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
        return reasons, notes
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ 检查：只报告，不重做、不改 state

def code_files(project, module, mods):
    """模块现有的代码文件（项目相对路径，按 entities / services / routes / queries 排）。"""
    from ..packs.dslproj import project as P
    root = Path(project)
    out = []
    for rel in (f"entities/{module}.entity", f"services/{module}.zs"):
        if (root / rel).is_file():
            out.append(rel)
    out += [f.relative_to(root).as_posix() for f in P.route_files(project, module, mods)]
    qd = root / "queries"
    out += [f.relative_to(root).as_posix() for f in sorted(qd.glob(f"{module}_*.sql"))] if qd.is_dir() else []
    return out


def _code_modules(project, mods):
    return [m for m in mods if code_files(project, m, mods)]


SEG_LINES = 400      # 派任务 每个文件（每段）最多读 400 行
SEG_MAX = 5          # 一个文件最多切 5 段，再长的后面读不到


def segment_refs(project, rel):
    """项目里的文件 → 给 派任务 的入参项：不超过 400 行就是文件名，更长切成「文件:起-止」几段（最多 SEG_MAX 段）。"""
    p = Path(project) / rel
    n = len(p.read_text(encoding="utf-8", errors="replace").splitlines()) if p.is_file() else 0
    if n <= SEG_LINES:
        return [rel]
    return [f"{rel}:{a}-{min(a + SEG_LINES - 1, n)}" for a in range(1, min(n, SEG_LINES * SEG_MAX) + 1, SEG_LINES)]


def code_inputs(project, mods):
    """有代码的模块 → [{module, files}]：files 是 派任务 的入参列表（contracts/<m>.md + 该模块全部代码文件，超 400 行的按段切开）。"""
    out = []
    for m in _code_modules(project, mods):
        refs = segment_refs(project, f"contracts/{m}.md")
        for f in code_files(project, m, mods):
            refs += segment_refs(project, f)
        out.append({"module": m, "files": refs})
    return out


def _merge_items(rows):
    """[(issue, module)] → 条目列表；同一条 issue 文本只留一条，模块名并到一起（建库失败这类全体模块同一原因）。"""
    merged = {}
    for issue, m in rows:
        merged.setdefault(issue, [])
        if m not in merged[issue]:
            merged[issue].append(m)
    return merged


def _failed_text(failed):
    return "\n".join(f"{f['module']}：{f['reason']}" for f in failed)[:2000]


def audit_regression(ctx, top):
    """核查用：对所有有代码的模块跑 加载检查 + 比对约定 + 跑用例，只报告（不 unmark、不重做、不记验收）。
    → {count, items: [{issue, modules, basis}], failed: [{module, reason}], failed_text, summary, code_modules}；
    failed 每个不过的模块一条（reason 是该模块的失败原文），failed_text 是「模块：原因」一行一个，供 .zs 决定重做谁；
    code_modules 是有代码的模块 [{module, files}]（files 见 code_inputs），供 核查.zs 对每个有代码的模块派代码核查。"""
    mods = [m["名"] for m in top["模块"]]
    code_mods = _code_modules(ctx.project, mods)
    if not code_mods:
        return {"count": 0, "items": [], "failed": [], "failed_text": "", "summary": "还没有代码，跳过",
                "code_modules": []}
    items = []
    failed = []
    for m in code_mods:
        ok, why = _accept_module(ctx.project, m, mods)
        if not ok:
            items.append({"issue": f"模块 {m} 全量回归不过：{why[:1500]}", "modules": m, "basis": "全量回归"})
            failed.append({"module": m, "reason": why})
    summary = (f"{len(code_mods)} 个有代码的模块，{len(items)} 个不过：" + "；".join(i["modules"] for i in items)) if items \
        else f"{len(code_mods)} 个有代码的模块全部通过"
    return {"count": len(items), "items": items, "failed": failed, "failed_text": _failed_text(failed), "summary": summary,
            "code_modules": code_inputs(ctx.project, mods)}


def _next_smoke_no(out):
    n = 1
    while (Path(out) / f"smoke_{n}.json").exists() or (Path(out) / f"smoke_{n}.txt").exists():
        n += 1
    return n


def audit_smoke(ctx, top):
    """只报告；每个不过的接口（或每项检查）一条 item。完整结果存 out/smoke_<n>.json / .txt。
    → {count, items, failed: [{module, reason}], failed_text, notes, notes_text, summary, files}；没有代码时跳过。
    failed 每个不过的模块一条（reason 是该模块所有问题用「；」连起来的原文）；notes 是只记备注的软差异。"""
    import json
    mods = [m["名"] for m in top["模块"]]
    code_mods = _code_modules(ctx.project, mods)
    if not code_mods:
        return {"count": 0, "items": [], "failed": [], "failed_text": "", "notes": [], "notes_text": "", "summary": "还没有代码，跳过"}
    reasons, notes = smoke_detail(ctx.project, code_mods)
    merged = _merge_items((why, m) for m, lst in reasons.items() for why in lst)
    items = [{"issue": why, "modules": ",".join(ms), "basis": "接口冒烟"} for why, ms in merged.items()]
    n = _next_smoke_no(ctx.out)
    f = ctx.out / f"smoke_{n}.json"
    f.write_text(json.dumps({"模块": {m: {"通过": m not in reasons, "原因": reasons.get(m, [])} for m in code_mods},
                             "备注": notes}, ensure_ascii=False, indent=2), encoding="utf-8")
    t = ctx.out / f"smoke_{n}.txt"
    t.write_text(f"接口冒烟：{len(code_mods)} 个有代码的模块，{len(reasons)} 个不过；{len(items)} 条问题；备注 {len(notes)} 条\n"
                 + "\n".join([i["issue"] for i in items] + notes) + "\n", encoding="utf-8")
    summary = f"{len(code_mods)} 个有代码的模块，{len(reasons)} 个不过，{len(items)} 条问题" if items else f"{len(code_mods)} 个有代码的模块冒烟全部通过"
    failed = [{"module": m, "reason": "；".join(reasons[m])} for m in code_mods if m in reasons]
    return {"count": len(items), "items": items, "failed": failed, "failed_text": _failed_text(failed), "notes": notes,
            "notes_text": "\n".join(notes)[:1500], "summary": summary, "files": [str(f), str(t)]}
