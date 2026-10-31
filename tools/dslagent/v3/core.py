"""v3 的运行上下文 Ctx（项目、记录目录、v2 的 Model、状态、花费上限）、状态 plan/state.json、跑 v3.zs 的引擎 V3Engine 和入口 run()。

动词（verbs/v3）通过 `current_engine().v3` 拿 Ctx；子引擎（执行 / 脚本动词 / 并行执行）沿用同一个 Ctx。
状态 plan/state.json：{"模块": {名: {"通过": true, "约定hash": …, "时间": …}}}；约定 hash 变了视为未完成（续跑规则）。
"""
import json
import threading
import time
from pathlib import Path

from tools.dsl import DSLEngine
from tools.dsl_core import ScriptHalt

from .. import common as C
from .. import v2 as V2
from ..packs.dslproj import contract as DC
from . import contracts as VC

HERE = Path(__file__).resolve().parent
V3_ZS = HERE / "v3.zs"
PROMPTS = HERE / "prompts"
SYNTAX_NAME = "project_syntax.md"
MAX_CALLS = 2000          # Model 自己的总调用上限放得很宽；真正的上限是 v3.zs 里的「预算」
WALL = 36000
STOP_KINDS = {"top": "顶层", "contract": "约定", "build": "build", "顶层": "顶层", "约定": "约定"}


def prompt_text(name):
    return (PROMPTS / name).read_text(encoding="utf-8").strip()


def syntax_text(ctx=None):
    """项目 DSL 写法说明全文；文件不存在或为空 → 空串（有 ctx 时记日志）。"""
    f = PROMPTS / SYNTAX_NAME
    text = f.read_text(encoding="utf-8") if f.is_file() else ""
    if not text and ctx is not None:
        ctx.log("语法说明", 说明=f"{SYNTAX_NAME} 不存在或为空，不带写法说明（syntax 注入空串）")
    return text


class Ctx:
    def __init__(self, project, out, req, M, cost_cap=None, module_cmd=None, module_wall=1800, module_calls=None,
                 impl_model=None, brief=False):
        self.project, self.out, self.req, self.M = Path(project), Path(out), req, M
        self.cost_cap, self.module_cmd, self.module_wall = cost_cap, module_cmd, module_wall
        self.module_calls = module_calls       # 派代理（执行方式=v2 的角色）的「预算 调用 N」下限；None = 不干预（change2 的 --max-turns）
        self.impl_model = impl_model           # modify_module 用的模型串（change2 / fix2 --impl-model）；None = 角色登记表的默认模型
        self.brief = brief                     # 给 modify_module 附本模块实现简报（--brief，v3/brief.py）；核查员不给
        self.usage = None                      # 引擎的 Usage（run() 里挂上）：预算按它算
        self.lock = threading.RLock()
        self.module_cost = 0.0
        self.attempts = {}                     # (种类, 模块) → 写了几次
        self.last_text = {}                    # (种类, 模块) → 上一次写的文本（重写时带上）
        self.rounds = {}                       # 模块 → 做了几轮
        self.records = {"规划": [], "模块": [], "验收": []}
        self.t0 = time.time()
        (self.out).mkdir(parents=True, exist_ok=True)

    # -- 记录
    def log(self, kind, **ev):
        row = {"t": round(time.time() - self.t0, 1), "类": kind, **ev}
        with self.lock:
            self.records.setdefault(kind, []).append(row)
            with (self.out / "v3_log.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    # -- 花费 / 预算
    def cost(self):
        return self.M.cost + self.module_cost

    def guard(self):
        """花费到上限就让整个流程「终止 超出预期」。派代理 / 并行派代理 / 做模块 调用前后查，模型客户端（GuardedClient）每次调用前查。"""
        if self.cost_cap is not None and self.cost() >= self.cost_cap:
            raise ScriptHalt("超出预期", f"花费 ${self.cost():.2f} 达到上限 ${self.cost_cap:.2f}，不再调用模型（已花费 ${self.cost():.2f}）", "")

    def take_call(self, n=1):
        """记 n 次模型调用进预算（v3.zs 的「预算 调用 N」）；超了抛 ScriptHalt。"""
        if self.usage is None:
            return
        for _ in range(n):
            self.usage.take()

    # -- 文件
    def top_path(self):
        return self.project / "plan" / "top.zs"

    def state_path(self):
        return self.project / "plan" / "state.json"

    def load_state(self):
        try:
            return json.loads(self.state_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"模块": {}}

    def contract_hash(self, module):
        f = VC.path_of(self.project, module)
        return DC.hash_of(f.read_text(encoding="utf-8")) if f.is_file() else None

    def is_done(self, module):
        with self.lock:
            e = self.load_state().get("模块", {}).get(module)
        h = self.contract_hash(module)
        return bool(e and e.get("通过") and h and e.get("约定hash") == h)

    def mark_done(self, module):
        h = self.contract_hash(module)
        if h is None:
            raise ValueError(f"没有 contracts/{module}.md，不能标记完成")
        with self.lock:
            st = self.load_state()
            st.setdefault("模块", {})[module] = {"通过": True, "约定hash": h, "时间": time.strftime("%Y-%m-%d %H:%M:%S")}
            self.state_path().parent.mkdir(parents=True, exist_ok=True)
            self.state_path().write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


class GuardedClient(V2.Client):
    """每次模型调用（派任务 / 问JSON 等经 chat_messages，工具模式经 run_tool）之前先过 ctx.guard()：花费已到 --cost-cap 就抛 ScriptHalt「超出预期」，
    不再发起这次调用。ScriptHalt 是 ScriptReturn，派任务 / 并行派任务原样往外抛，整个流程按「终止 超出预期」结束。
    超出幅度不会超过「上限之前最后一次调用」的花费（一次调用内部无法中断）。"""

    def __init__(self, M, ctx):
        super().__init__(M)
        self.ctx = ctx

    def chat_messages(self, messages, *a, **kw):
        self.ctx.guard()
        return super().chat_messages(messages, *a, **kw)

    def run_tool(self, *a, **kw):
        self.ctx.guard()
        return super().run_tool(*a, **kw)


class V3Engine(DSLEngine):
    """跑 v3.zs / build.zs 的引擎：DSLEngine + 一个 Ctx（子引擎沿用）。"""
    v3 = None

    def _sub_engine(self):
        sub = super()._sub_engine()
        sub.__class__ = type(self)
        sub.v3 = self.v3
        return sub


def _load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def ctx_of(engine=None):
    from tools.dsl import current_engine
    eng = engine or current_engine()
    c = getattr(eng, "v3", None)
    if c is None:
        raise RuntimeError("v3 的动词只能在 python -m tools.dslagent v3 起的流程里用（引擎上没有 v3 上下文）")
    return c


def run(req, project, out, stop_after=None, backend=None, cost_cap=None, wall=WALL, module_cmd=None, module_wall=1800, script=None, skip=None):
    """跑 v3.zs（script 给了就跑 v3/ 下那个顶层脚本，如 build2，不带 .zs）。req：需求文本；backend：假模型（测试用）；module_cmd：替换「做模块」起的子进程命令（测试用）。
    → {status, reason, at, 花费, 用时, 记录…}，同时写 out/result.json。"""
    project, out = Path(project), Path(out)
    project.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "req.md").write_text(req, encoding="utf-8")
    stop = STOP_KINDS.get((stop_after or "").strip(), "") if stop_after else ""
    if stop_after and not stop:
        raise ValueError(f"--stop-after 只能是 top / contract / build，收到 {stop_after!r}")
    M = V2.Model(out, backend=backend, max_calls=MAX_CALLS, deadline=time.time() + wall)
    prev_calls = _load_json(out / "calls.json", [])
    seen = [int(f.name.split("_", 1)[0]) for f in (out / "calls").glob("*_*.prompt.txt") if f.name.split("_", 1)[0].isdigit()]
    M.n = max([len(prev_calls)] + seen)                    # 续跑：calls/ 里的文件接着编号，不覆盖上一次的
    old = out / "result.json"
    if old.is_file():                                      # 续跑：上一次的 result.json 留着（result_run<k>.json）
        k = 1
        while (out / f"result_run{k}.json").exists():
            k += 1
        old.rename(out / f"result_run{k}.json")
    ctx = Ctx(project, out, req, M, cost_cap=cost_cap, module_cmd=module_cmd, module_wall=module_wall)
    eng = V3Engine(client=GuardedClient(M, ctx), workdir=project, verbose=False, verbs_root=C.VERBS)
    eng.v3, ctx.usage = ctx, eng.usage
    eng.vars.update({"req": req, "project": str(project), "stop_after": stop, **({"skip": skip} if skip else {})})
    res, err = {"status": "成功", "reason": "", "at": ""}, None
    try:
        eng.run_file(HERE / f"{script}.zs" if script else V3_ZS)   # 文件跑：脚本里的「执行」先找同级目录
        if eng.halted is not None:
            res = dict(eng.halted)
    except Exception as e:  # noqa: BLE001  引擎 / 动词出错：记成失败，不往外抛
        res = {"status": "失败", "reason": f"{type(e).__name__}: {e}"[:600], "at": ""}
        err = e
    res.update(花费=round(ctx.cost(), 4), 规划花费=round(M.cost, 4), 模块花费=round(ctx.module_cost, 4),
               用时=round(time.time() - ctx.t0, 1), 模型调用=M.n, 记录=ctx.records, 输出=eng.output[-20:])
    if err is not None:
        import traceback
        res["堆栈"] = "".join(traceback.format_exception(err))[-3000:]
    (out / "calls.json").write_text(json.dumps(prev_calls + M.log, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def brief_impact(ctx):
    """--brief 时开始前先算影响面（契约 git HEAD vs 工作区）：写 out/brief_impact.json、brief_impact.md，记一行日志、打印到 stderr。
    只是建议：不改 --modules，出错也不挡流程。"""
    import sys
    from . import brief as B
    try:
        base = B.git_base_texts(ctx.project)
        imp = B.impact(base, B.load_contracts(ctx.project)[1]) if base is not None else None
    except Exception as e:  # noqa: BLE001
        ctx.log("简报影响面", 状态="出错", 原因=f"{type(e).__name__}: {e}"[:300])
        return None
    md = B.impact_md(imp)
    (ctx.out / "brief_impact.json").write_text(json.dumps(imp, ensure_ascii=False, indent=1), encoding="utf-8")
    (ctx.out / "brief_impact.md").write_text(md + "\n", encoding="utf-8")
    if imp is None:
        ctx.log("简报影响面", 状态="没有", 原因=md)
    else:
        ctx.log("简报影响面", 建议模块=imp["建议模块"], 参考模块=sorted(imp["参考模块"]), 可能漏改契约=imp["可能漏改契约"],
                改动函数数=len(imp["改动函数"]))
    print("[实现简报·影响面（只是建议，没有改 --modules）]\n" + md, file=sys.stderr, flush=True)
    return imp


def run_entry(script, project, out, req, extra_vars=None, backend=None, cost_cap=None, wall=WALL,
              module_cmd=None, module_wall=1800, module_calls=None, impl_model=None, brief=False):
    """跑 v3/ 下的顶层脚本（核查.zs / 修改.zs，script 不带 .zs）：req 是需求全文。
    impl_model / brief：change2 / fix2 的 --impl-model / --brief（只作用于 modify_module，见 verbs/v3/defs/派代理.py）；brief 时开始前还写影响面（brief_impact）。
    → {status, reason, at, 花费, 用时, 模型调用[, returned]}，同时写 out/<script>_result.json。"""
    project, out = Path(project), Path(out)
    project.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    M = V2.Model(out, backend=backend, max_calls=MAX_CALLS, deadline=time.time() + wall)
    prev_calls = _load_json(out / "calls.json", [])
    ctx = Ctx(project, out, req, M, cost_cap=cost_cap, module_cmd=module_cmd, module_wall=module_wall,
              module_calls=module_calls, impl_model=impl_model, brief=brief)
    eng = V3Engine(client=GuardedClient(M, ctx), workdir=project, verbose=False, verbs_root=C.VERBS)
    eng.v3, ctx.usage = ctx, eng.usage
    if impl_model or brief:
        ctx.log("实现设置", impl_model=impl_model or "", brief=bool(brief))
    if brief:
        brief_impact(ctx)
    syntax = syntax_text(ctx)
    eng.vars.update({"req": req, "syntax": syntax, "scope": "", "modules": "", **(extra_vars or {})})   # scope / modules：audit2 / fix2 的模块范围，缺省空 = 全部
    res, err = {"status": "成功", "reason": "", "at": ""}, None
    try:
        eng.run_file(HERE / f"{script}.zs")
        if eng.halted is not None:
            res = dict(eng.halted)
        elif eng.returned:
            res["returned"] = eng.returned[0]
    except Exception as e:  # noqa: BLE001  引擎 / 动词出错：记成失败，不往外抛
        res = {"status": "失败", "reason": f"{type(e).__name__}: {e}"[:600], "at": ""}
        err = e
    res.update(花费=round(ctx.cost(), 4), 用时=round(time.time() - ctx.t0, 1), 模型调用=M.n, 记录=ctx.records)
    if err is not None:
        import traceback
        res["堆栈"] = "".join(traceback.format_exception(err))[-3000:]
    (out / "calls.json").write_text(json.dumps(prev_calls + M.log, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"{script}_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
