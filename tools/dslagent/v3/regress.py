"""build.zs 末尾的两步（verbs/v3 的 全量回归 / 接口冒烟 是它们的壳）：

  全量回归   所有模块（含已完成、约定 hash 没变的）重新跑一次「加载检查 + 比对约定 + 跑用例」；
            不过的标未完成、记回归原因，按依赖分层重做（第一轮任务就带着这个原因），最多 2 轮，仍不过 终止 失败。
  接口冒烟   项目拷到临时目录、按全部 entities 建库，用 tools.dsl_http 的真实 Router（进程内 Flask 测试客户端）
            加载全部 routes / services；约定里每个接口取所调函数第一条正常用例，用 cases.seed_case 造的
            「同一份数据」各跑一次「直接调用」与「走 HTTP」，核对状态码与返回是否一致（结构不同算失败，
            值不同但结构一样只记备注——大概率是随机 / 时间字段）。不过的模块同全量回归的规则重做。
            多人模式（角色 / 登录）留给 A3；这里先留 login 参数占位，默认不开。

两步共用 _redo_rounds：检查一遍所有模块 → 全过就通过；不过的标未完成、按 plan/top.zs 的依赖分层分组，
每层一次 并行执行「做一个模块」（带上这次查出的原因）→ 下一轮重新检查；2 轮都有模块不过就 终止 失败。
"""
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
            bad = [r for r in rs if isinstance(r, dict) and r.get("状态") != "成功"]
            if bad:
                lines = "\n".join(f"{(r.get('参数') or {}).get('模块') or '?'}：{r.get('原因') or r.get('状态')}" for r in bad)
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


def _smoke_one(ws, sql, module, iface, case, notes):
    """同一份种子数据上各跑一次「直接调用」与「走 HTTP」→ "" 或失败原因；notes 收集只记备注的软差异。"""
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

    db.write_bytes(seed)
    for suf in ("-wal", "-shm", "-journal"):
        try:
            Path(str(db) + suf).unlink()
        except OSError:
            pass
    try:
        from tools.dsl_http import Router
        # login=False：多人模式（认证 / 角色）的接入留给 A3，这里先占位不开
        router = Router(Path(ws) / "routes", Path(ws), Path(ws) / "sessions", real=False, login=False)
        client = router.app().test_client()
        args = {k: _val(v) for k, v in case["调用"]["参数"].items()}
        if iface["方法"] == "GET":
            resp = client.get(iface["路径"], query_string=args)
        else:
            resp = client.open(iface["路径"], method=iface["方法"], json=args)
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
        for m in mods:
            try:
                c, _ = P.load_contract(project, m)
            except P.ProjError as e:
                reasons.setdefault(m, []).append(f"约定加载失败：{e}")
                continue
            for iface in c["接口"]:
                if iface.get("上传"):          # B2 之前约定里不会有这个字段，先占位
                    notes.append(f"{m} {iface['方法']} {iface['路径']}：上传接口暂跳过（留给 B2）")
                    continue
                case = _first_case(c, iface["函数"])
                if case is None:
                    notes.append(f"{m} {iface['方法']} {iface['路径']}：没有 {iface['函数']} 的正常用例，跳过")
                    continue
                why = _smoke_one(ws, sql, m, iface, case, notes)
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
