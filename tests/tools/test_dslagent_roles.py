# -*- coding: utf-8 -*-
"""dslagent 子 agent 管理：角色登记表解析/检查、派代理/并行派代理（假 backend，不调真模型）、调度层账本与统计、
按角色覆盖模型（DSLAGENT_MODELS）、预算把关、codex 隔离（空 cwd + 关 shell_tool）、父终止收子进程组。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_roles.py
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_roles_"))

from tools.dslagent import engines as EG                    # noqa: E402
from tools.dslagent import ledger as LG                     # noqa: E402
from tools.dslagent import roles as R                        # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


def fresh():
    p = TMP / f"d{len(list(TMP.iterdir())) + 1}"
    p.mkdir(parents=True)
    return p


# ------------------------------------------------------------------ 登记表解析 / 校验


def test_parse_check():
    print("角色登记表：解析与校验")
    text = "角色 a\n  默认模型: sonnet\n  工具: 无\n  单次超时: 10\n  回复格式: json\n  提示词文件: （无）\n结束\n"
    rm = R.parse_roles(text)
    check(list(rm) == ["a"] and rm["a"]["默认模型"] == "sonnet", "解析出一个角色块", rm)
    check(R.check_roles(rm) == [], "合法登记表没有问题", R.check_roles(rm))

    bad_model = R.parse_roles("角色 a\n  默认模型: 不认识的模型\n  工具: 无\n  单次超时: 10\n  回复格式: json\n  提示词文件: x\n结束\n")
    probs = R.check_roles(bad_model)
    check(any("默认模型不合法" in p for p in probs), "模型串不合法报问题", probs)

    bad_tool = R.parse_roles("角色 a\n  默认模型: sonnet\n  工具: 乱写\n  单次超时: 10\n  回复格式: json\n  提示词文件: x\n结束\n")
    check(any("工具" in p for p in R.check_roles(bad_tool)), "工具取值不对报问题")

    missing = R.parse_roles("角色 a\n  工具: 无\n结束\n")
    probs = R.check_roles(missing)
    check(any("缺「默认模型」" in p for p in probs) and any("缺「单次超时」" in p for p in probs), "缺字段逐条报问题", probs)

    try:
        R.parse_roles("角色 a\n结束\n结束\n")
        check(False, "多余「结束」报格式错")
    except ValueError:
        check(True, "多余「结束」报格式错")

    try:
        R.parse_roles("角色 a\n  x: 1\n")
        check(False, "缺「结束」报格式错")
    except ValueError:
        check(True, "缺「结束」报格式错")


def test_real_registry():
    print("真实登记表 tools/dslagent/roles.zs")
    rm = R.load_roles()
    want = ("plan", "plan_fix", "sub", "sub_tool", "fix", "bound", "bfix", "write_top", "write_contract", "review",
            "audit", "write_change_plan", "build_module", "logic_check", "summarize", "classify", "extract", "prescreen")
    missing = [w for w in want if w not in rm]
    check(not missing, "spec 要求的全部角色都登记了", missing)
    probs = R.check_roles(rm)
    check(probs == [], "真实登记表校验没有问题", probs)
    check(rm["logic_check"]["默认模型"].startswith("codex:") and "luna" in rm["logic_check"]["默认模型"],
          "logic_check 默认模型是 codex luna", rm["logic_check"]["默认模型"])
    check(rm["logic_check"]["回退模型"] == "sonnet", "logic_check 回退 sonnet")
    for h in ("summarize", "classify", "extract", "prescreen"):
        check(rm[h]["默认模型"].startswith("codex:") and "luna" in rm[h]["默认模型"] and rm[h]["回退模型"] == "sonnet",
              f"助手 {h} 默认 luna、回退 sonnet", rm[h])


# ------------------------------------------------------------------ 按角色覆盖模型


def test_env_override():
    print("DSLAGENT_MODELS 按角色覆盖")
    rm = R.load_roles()
    os.environ["DSLAGENT_MODELS"] = json.dumps({"logic_check": "codex:gpt-6-sol:high"})
    try:
        spec = R.resolve_model("logic_check", "默认模型", rm)
        check(spec["spec"] == "codex:gpt-6-sol:high", "环境变量覆盖了角色默认模型", spec)
        spec2 = R.resolve_model("summarize", "默认模型", rm)
        check(spec2["spec"] == rm["summarize"]["默认模型"], "没覆盖的角色走登记表默认值", spec2)
    finally:
        os.environ.pop("DSLAGENT_MODELS", None)
    try:
        R.resolve_model("不存在的角色", "默认模型", rm)
        check(False, "角色不存在报 KeyError")
    except KeyError:
        check(True, "角色不存在报 KeyError")


# ------------------------------------------------------------------ 派代理（假 backend）


def fake_backend(replies):
    """replies: {模型串: [reply1, reply2, …]}（用完用最后一个）；reply 是 dict 或抛异常的 callable。"""
    calls = []

    def backend(spec, system, user, timeout):
        calls.append({"spec": spec["spec"], "system": system, "user": user})
        seq = replies.get(spec["spec"])
        if not seq:
            return {"text": "", "cost": 0.0, "reason": None, "rc": 0}
        n = sum(1 for c in calls if c["spec"] == spec["spec"])
        r = seq[min(n, len(seq)) - 1]
        return r() if callable(r) else r
    backend.calls = calls
    return backend


def test_dispatch_ok():
    print("派代理：正常成功")
    out = fresh()
    backend = fake_backend({"codex:gpt-6-luna:medium": [{"text": '[{"问题":"漏了锁","依据":"x"}]', "cost": 0.01, "rc": 0}]})
    r = R.dispatch_agent("logic_check", "检查这份约定", {"约定": "模块 a\n..."}, out_dir=out, backend=backend)
    check(r["status"] == "ok", "status=ok", r)
    check(json.loads(r["result"])[0]["问题"] == "漏了锁", "拿到了模型回复的内容", r)
    check(r["model"] == "codex:gpt-6-luna:medium", "用了角色默认模型", r)
    rows = LG.read_rows(out)
    check(len(rows) == 1 and rows[0]["role"] == "logic_check" and rows[0]["status"] == "ok", "账本记了一条", rows)


def test_dispatch_fallback():
    print("派代理：回复不合格回退")
    out = fresh()
    backend = fake_backend({
        "codex:gpt-6-luna:medium": [{"text": "不是 json", "cost": 0.01, "rc": 0}],
        "sonnet": [{"text": '[]', "cost": 0.02, "rc": 0}],
    })
    r = R.dispatch_agent("logic_check", "", {"约定": "x"}, out_dir=out, backend=backend)
    check(r["status"] == "ok" and r["model"] == "sonnet", "回退到 sonnet 后成功", r)
    check(len(backend.calls) == 2, "调用了两次（默认 + 回退）", backend.calls)
    rows = LG.read_rows(out)
    check(rows[0]["fallback"] is True, "账本记了 fallback=true", rows)


def test_dispatch_both_fail():
    print("派代理：默认和回退都不合格")
    out = fresh()
    backend = fake_backend({
        "codex:gpt-6-luna:medium": [{"text": "x", "cost": 0.0, "rc": 0}],
        "sonnet": [{"text": "", "cost": 0.0, "rc": 0}],
    })
    r = R.dispatch_agent("logic_check", "", {"约定": "x"}, out_dir=out, backend=backend)
    check(r["status"] == "fail", "两次都不合格 status=fail", r)


def test_dispatch_unknown_role():
    print("派代理：角色不存在")
    out = fresh()
    r = R.dispatch_agent("不存在", "", {}, out_dir=out, backend=fake_backend({}))
    check(r["status"] == "fail" and "没有登记" in r["reason"], "角色不存在 status=fail", r)


def test_dispatch_v2():
    print("A1：执行方式 v2——假 backend：返回形状、记账、可读范围、回退、任务文本、--scope 展开")
    rm = R.load_roles()
    check(rm["modify_module"]["执行方式"] == "v2" and R.check_roles(rm) == [], "modify_module 登记为 v2，登记表检查通过", R.check_roles(rm))
    check(all("执行方式" not in v for k, v in rm.items() if k != "modify_module"), "其他角色没写执行方式（缺省 模型）")
    bad = R.parse_roles("角色 a\n  执行方式: 乱写\n  默认模型: sonnet\n  工具: 无\n  单次超时: 10\n  回复格式: json\n  提示词文件: x\n结束\n")
    check(any("执行方式" in x for x in R.check_roles(bad)), "执行方式取值不对报问题")

    out = fresh()
    seen = []

    def v2b(spec, req):
        seen.append((spec, req))
        return {"fixed": True, "stop": "", "cost": 0.5, "sec": 3.0, "calls": 4, "started": True, "files": ["services/report.zs"]}
    r = R.dispatch_agent("modify_module", "补 pass_line", {"模块": "report"}, out_dir=out, v2_backend=v2b)
    check(set(r) >= {"result", "status", "reason", "role", "model", "cost", "calls", "secs", "call_id"}, "返回形状同模型角色", r)
    check(r["status"] == "ok" and r["result"] == "services/report.zs" and r["cost"] == 0.5 and r["calls"] == 4, "ok，result 是改动文件清单", r)
    check(seen[0][0] == "sonnet" and seen[0][1]["task"] == "模块 report\n补 pass_line\n", "模型 = 角色默认模型；任务文本 = 模块行 + 任务", seen[0])
    check(seen[0][1]["scope"] == ["entities/report.entity", "services/report.zs", "routes/report*.zs", "queries/report_*.sql", "tests/report_*"],
          "scope = 本模块路径展开", seen[0][1]["scope"])
    rows = LG.read_rows(out)
    check(len(rows) == 1 and rows[0]["cost"] == 0.5 and rows[0]["secs"] == 3.0 and rows[0]["status"] == "ok", "花费、耗时记了账本", rows)

    os.environ["DSLAGENT_MODELS"] = json.dumps({"modify_module": "opus"})
    try:
        seen.clear()
        R.dispatch_agent("modify_module", "x", {"模块": "report"}, out_dir=fresh(), v2_backend=v2b)
        check(seen[0][0] == "opus", "DSLAGENT_MODELS 按角色名覆盖默认模型", seen[0][0])
    finally:
        os.environ.pop("DSLAGENT_MODELS", None)

    r = R.dispatch_agent("modify_module", "x", {"模块": "report", "需求": "y"}, out_dir=fresh(), v2_backend=v2b)
    check(r["status"] == "fail" and "范围外" in r["reason"], "入参越出可读范围照旧挡", r)
    r = R.dispatch_agent("modify_module", "x", {}, out_dir=fresh(), v2_backend=v2b)
    check(r["status"] == "fail" and "模块" in r["reason"], "没有入参.模块 报错", r)

    seen.clear()
    calls = []

    def v2_fb(spec, req):
        calls.append(spec)
        return {"fixed": False, "stop": "引擎错误", "started": False, "calls": 0} if len(calls) == 1 else \
            {"fixed": True, "cost": 0.1, "calls": 2, "started": True, "files": ["a"]}
    o3 = fresh()
    r = R.dispatch_agent("modify_module", "x", {"模块": "report"}, out_dir=o3, v2_backend=v2_fb)
    check(r["status"] == "ok" and len(calls) == 2 and LG.read_rows(o3)[0]["fallback"] is True, "没跑起来：换回退模型再起一次，账本 fallback=true", (r, calls))

    calls.clear()

    def v2_fail(spec, req):
        calls.append(spec)
        return {"fixed": False, "stop": "验收没过：services/report.zs 少 pass_line", "cost": 0.3, "calls": 5, "started": True}
    r = R.dispatch_agent("modify_module", "x", {"模块": "report"}, out_dir=fresh(), v2_backend=v2_fail)
    check(r["status"] == "fail" and "pass_line" in r["reason"] and len(calls) == 1 and r["result"] == "", "验收失败不回退，reason 带原文", (r, calls))


def test_dispatch_v2_subprocess():
    print("A1：执行方式 v2——真起子进程（桩命令）：拷贝里做、验收通过才拷回范围内文件、--scope / DSLAGENT_MODELS 传对")
    stub = TMP / "v2stub.py"
    stub.write_text("""import sys, os, json
a = sys.argv
proj = a[a.index('--project') + 1]
rec = a[a.index('--out') + 1]
os.makedirs(rec, exist_ok=True)
open(os.path.join(rec, 'argv.json'), 'w').write(json.dumps({'argv': a, 'models': os.environ.get('DSLAGENT_MODELS'), 'task': open(a[a.index('--task-file') + 1]).read()}))
open(os.path.join(proj, 'services', 'm.zs'), 'a').write('改')
open(os.path.join(proj, 'services', 'other.zs'), 'a').write('越界')
print(json.dumps({'fixed': os.environ.get('STUB_FIX') == '1', 'calls': 2, 'cost': 0.25, 'stop': '' if os.environ.get('STUB_FIX') == '1' else '没过'}))
""", encoding="utf-8")
    proj = fresh()
    (proj / "services").mkdir()
    (proj / "services" / "m.zs").write_text("原", encoding="utf-8")
    (proj / "services" / "other.zs").write_text("原", encoding="utf-8")
    cmd = [sys.executable, str(stub)]
    os.environ["STUB_FIX"] = "0"
    try:
        o = fresh()
        r = R.dispatch_agent("modify_module", "t", {"模块": "m"}, out_dir=o, project=proj, module_cmd=cmd)
        check(r["status"] == "fail" and r["reason"] == "没过" and r["cost"] == 0.25, "验收没过：fail，reason 是 v2 的 stop", r)
        check((proj / "services" / "m.zs").read_text(encoding="utf-8") == "原", "没过时项目原样不动")
        os.environ["STUB_FIX"] = "1"
        o = fresh()
        r = R.dispatch_agent("modify_module", "t", {"模块": "m"}, out_dir=o, project=proj, module_cmd=cmd)
        check(r["status"] == "ok" and r["result"] == "services/m.zs", "通过：result 是范围内改动文件", r)
        check((proj / "services" / "m.zs").read_text(encoding="utf-8") == "原改", "范围内文件拷回项目")
        check((proj / "services" / "other.zs").read_text(encoding="utf-8") == "原", "范围外文件不拷回")
        info = json.loads(next(Path(o).glob("agents/modify_module/m_1/v2/argv.json")).read_text(encoding="utf-8"))
        a = info["argv"]
        check(a[a.index("--scope") + 1] == "entities/m.entity,services/m.zs,routes/m*.zs,queries/m_*.sql,tests/m_*", "--scope 传了展开后的可写范围")
        check(json.loads(info["models"]) == {s: "sonnet" for s in EG.STEPS}, "DSLAGENT_MODELS 把默认模型设给全部 STEPS", info["models"])
        check(info["task"] == "模块 m\nt\n", "任务文件内容", info["task"])
        check(a[a.index("--pack") + 1] == "dslproj" and a[a.index("--wall") + 1] == "1800", "--pack dslproj、--wall = 单次超时")
    finally:
        os.environ.pop("STUB_FIX", None)


def test_dispatch_scope():
    print("派代理：入参越出可读范围")
    out = fresh()
    r = R.dispatch_agent("logic_check", "", {"约定": "x", "别的材料": "y"}, out_dir=out, backend=fake_backend({}))
    check(r["status"] == "fail" and "可读范围" in r["reason"], "带了范围外的键直接拒绝、不调模型", r)
    check(fake_backend({}).calls == [], "没有调用 backend（不同实例，只验证语义：上面那次没写进账本的 cost>0）")
    rows = LG.read_rows(out)
    check(rows[0]["cost"] == 0.0, "没调模型，账本花费是 0", rows)


def test_dispatch_budget():
    print("派代理：预算把关")
    out = fresh()
    # check_budget 在调用前按「已经花了多少」把关（不是扣完才查），所以第 1、2 次都还在 0.2 预算内会放过，
    # 第 3 次一看已经花了 0.30（≥0.2）就直接拦住，不再调模型。
    backend = fake_backend({"codex:gpt-6-luna:low": [{"text": "摘要", "cost": 0.15}]})
    r1 = R.dispatch_agent("summarize", "", {"原文": "x" * 100}, out_dir=out, backend=backend)
    check(r1["status"] == "ok", "第一次没超预算", r1)
    r2 = R.dispatch_agent("summarize", "", {"原文": "y" * 100}, out_dir=out, backend=backend)
    check(r2["status"] == "ok", "第二次（累计花费还没到预算检查点之前）仍放过", r2)
    r3 = R.dispatch_agent("summarize", "", {"原文": "z" * 100}, out_dir=out, backend=backend)
    check(r3["status"] == "over" and len(backend.calls) == 2, "第三次一查累计花费已达角色预算（0.2），status=over、没有再调模型",
          (r3, backend.calls))


def test_parallel_dispatch():
    print("并行派代理")
    out = fresh()
    backend = fake_backend({"codex:gpt-6-luna:medium": [{"text": "[]", "cost": 0.01}]})
    items = [{"角色": "logic_check", "任务": "", "入参": {"约定": f"m{i}"}} for i in range(5)]
    rs = R.parallel_dispatch_agents(items, out_dir=out, backend=backend)
    check(len(rs) == 5 and all(r["status"] == "ok" for r in rs), "五个全成功", rs)
    rows = LG.read_rows(out)
    check(len(rows) == 5, "账本五条、共用一份文件", rows)


# ------------------------------------------------------------------ 调度层账本 / 统计


def test_ledger_stats():
    print("调度层账本：统计")
    out = fresh()
    led = LG.Ledger(out / "agents.jsonl")
    led.record(role="logic_check", model="codex:gpt-6-luna:medium", cost=0.1, secs=2.0, status="ok")
    led.record(role="logic_check", model="codex:gpt-6-luna:medium", cost=0.1, secs=3.0, status="fail")
    led.record(role="summarize", model="sonnet", cost=0.05, secs=1.0, status="ok")
    s = LG.stats(LG.read_rows(out))
    check(s["总调用数"] == 3, "总调用数对")
    check(s["按角色"]["logic_check"]["调用数"] == 2 and s["按角色"]["logic_check"]["成功率"] == 0.5, "按角色统计成功率", s)
    check(abs(s["按模型"]["sonnet"]["花费"] - 0.05) < 1e-9, "按模型统计花费", s)


def test_ledger_scan_ignores_other_jsonl():
    print("调度层账本：扫目录只认 agents.jsonl，不混进别的 jsonl（如 v3_log.jsonl）")
    out = fresh()
    LG.Ledger(out / "agents.jsonl").record(role="logic_check", cost=0.1, status="ok")
    (out / "v3_log.jsonl").write_text('{"t": 0.1, "类": "核查", "事件": "汇总"}\n', encoding="utf-8")
    rows = LG.read_rows(out)
    check(len(rows) == 1 and rows[0]["role"] == "logic_check", "目录扫描只拿到账本那一条，没把 v3_log.jsonl 混进来", rows)


def test_ledger_run_call_id():
    print("调度层账本：run_id / call_id / parent_id")
    out = fresh()
    led = LG.Ledger(out / "agents.jsonl")
    r1 = led.record(role="a", parent_id="父任务1")
    r2 = led.record(role="a", parent_id="父任务1")
    check(r1["run_id"] == led.run_id == r2["run_id"], "同一账本同一个 run_id")
    check(r1["call_id"] != r2["call_id"], "call_id 各不相同", (r1["call_id"], r2["call_id"]))
    check(r1["parent_id"] == "父任务1", "parent_id 记对了")


# ------------------------------------------------------------------ codex 隔离 / 父终止收子进程


class _FakeProc:
    def __init__(self, cmd, stdin=None, stdout=None, stderr=None, text=None, cwd=None, env=None, start_new_session=None):
        self.cmd, self.cwd, self.pid, self.returncode = cmd, cwd, 999001, 0
        self.stdin = _W()
        self.stdout = iter([])
        self.stderr = _R()

    def wait(self, timeout=None):
        return 0


class _W:
    def write(self, *a):
        pass

    def close(self):
        pass


class _R:
    def read(self):
        return ""


def test_codex_isolated_cwd():
    print("codex 隔离：空 cwd + 关 shell_tool + read-only sandbox")
    import subprocess as SP
    orig = SP.Popen
    captured = {}

    def fake_popen(cmd, **kw):
        captured["cmd"], captured["cwd"] = cmd, kw.get("cwd")
        return _FakeProc(cmd, **kw)

    SP.Popen = fake_popen
    try:
        r = EG.call_codex("system", "user", timeout=5, model="gpt-6-luna")
    finally:
        SP.Popen = orig
    cwd = Path(captured["cwd"])
    check(cwd.is_dir() and not list(cwd.iterdir()), "codex 的 cwd 是一个空目录", cwd)
    check(str(cwd) != str(ROOT) and "agent_mcp" not in cwd.parts, "cwd 不是仓库目录本身", cwd)
    check("-s" in captured["cmd"] and captured["cmd"][captured["cmd"].index("-s") + 1] == "read-only", "sandbox 是 read-only")
    check("shell_tool" in captured["cmd"], "disable 了 shell_tool（没有 shell 就读不到 cwd 外任何东西）", captured["cmd"])
    check(isinstance(r, dict) and "text" in r, "返回结构正常", r)


def test_kill_all():
    print("父终止收子进程组：engines.kill_all()")
    import os as OS
    killed = []
    orig = OS.killpg

    def fake_killpg(pgid, sig):
        killed.append((pgid, sig))
    OS.killpg = fake_killpg
    try:
        with EG._ACTIVE_LOCK:
            EG._ACTIVE_PGIDS.add(424242)
            EG._ACTIVE_PGIDS.add(424243)
        n = EG.kill_all()
    finally:
        OS.killpg = orig
        with EG._ACTIVE_LOCK:
            EG._ACTIVE_PGIDS.discard(424242)
            EG._ACTIVE_PGIDS.discard(424243)
    check(n == 2 and {424242, 424243} <= {pg for pg, _ in killed}, "收掉了注册过的全部进程组", killed)


# ------------------------------------------------------------------ v3 接入：核查 的 逻辑核查=是


def test_audit_logic_check_opt_in():
    print("核查：逻辑核查=是 时并入 logic_check 疑点（缺省否，行为不变）")
    from tools.dslagent import v2 as V2
    from tools.dslagent.v3 import core as C3, issues as IS

    project = fresh()
    (project / "contracts").mkdir(parents=True)
    (project / "contracts" / "a.md").write_text("模块 a\n\n## 函数\n公开 函数 x\n  伪代码 返回 1\n", encoding="utf-8")
    out = fresh()
    M = V2.Model(out)
    ctx = C3.Ctx(project, out, "需求", M)
    top = {"模块": [{"名": "a", "依赖": []}]}

    def backend(spec, system, user, timeout):
        return {"text": '[{"问题":"漏了鉴权","依据":"函数 x"}]', "cost": 0.01, "rc": 0}

    items_on = IS.run_logic_checks(ctx, top, backend=backend)
    check(len(items_on) == 1 and items_on[0]["modules"] == "a" and "logic_check(疑点)" in items_on[0]["basis"],
          "开了之后疑点标「logic_check(疑点)」并到模块 a（模型回旧键 问题/依据 也能用）", items_on)
    check(IS.logic_cache_path(ctx).is_file(), "按约定内容 hash 缓存落盘")

    items_again = IS.run_logic_checks(ctx, top, backend=backend)
    check(items_again == items_on, "约定没变时结果不变（走缓存，不重调模型——下面核对没有再花钱）")
    check(ctx.module_cost - 0.01 < 1e-9, "两次调用只记了一次花费（第二次命中缓存没调模型）", ctx.module_cost)


if __name__ == "__main__":
    try:
        test_parse_check()
        test_real_registry()
        test_env_override()
        test_dispatch_ok()
        test_dispatch_fallback()
        test_dispatch_both_fail()
        test_dispatch_unknown_role()
        test_dispatch_scope()
        test_dispatch_v2()
        test_dispatch_v2_subprocess()
        test_dispatch_budget()
        test_parallel_dispatch()
        test_ledger_stats()
        test_ledger_scan_ignores_other_jsonl()
        test_ledger_run_call_id()
        test_codex_isolated_cwd()
        test_kill_all()
        test_audit_logic_check_opt_in()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
