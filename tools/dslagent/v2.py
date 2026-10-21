"""规划路径 v2 的核心（DSLAGENT_PLANNER=v2 时 runner.run 转到这里；缺省仍走 runner 的模板 / 规划路径）。
与任务类型无关；任务类型相关的两半按环境变量插拔（目前都只有 code）：
  资料包 packs/（DSLAGENT_PACK，缺省 code）：文件大纲、规划提示里这类任务专属的说明（接口见 packs/__init__.py）
  验收   verify/（DSLAGENT_VERIFY，缺省跟随 PACK）：验收、补改、边界复核（接口见 verify/__init__.py）
旧路径兼容：tools.dslagent.v2pack 转发到 packs.code；搬走的名字（v2._fix_user、v2.full_test …）仍可从 v2 取到。

规划：规划输入只有 任务原文 + 文件大纲（pack.plan_outline；包没实现就只有任务原文），system = 原 system 去掉讲资料包各节的那句 + 一小段
「用 dsl 工具读」；规划调用挂 dslmcp --readonly（读片段 / 搜索代码 / 查引用 / 设 / 打印），workdir = 待改项目，--max-turns 12，
保险同下（空闲超时、文本 invoke 拦截、超长输出、重试一次）；计划检查不过的那次重写也走这条。
每次规划的工具调用（工具名、参数、返回字数）写进运行目录 plan_tools.json。
规划用 grok 时不挂 dsl 工具，用 grok 自带只读工具（read_file / grep / list_dir，cwd = 待改项目，写 / 命令 / 联网 / 子代理全禁，--max-turns 10），
system 里「用 dsl 工具读」那句换成 grok 版（agents/plan.md 的「变体：grok」）；出现别的工具调用即杀（调用被禁工具），累计读入超 200000 字即杀（读超限），杀掉后不原样重读，走收尾调用（tag plan_wrapup，不带工具，user 里附程序重取的已读内容 ≤120000 字，见 wrapup.py / plan.md「模板：收尾说明」）。
opencode 不能做规划（engines.validate 提交时报错）。老的 full 规划方式（资料包 + 补查）已删除，DSLAGENT_PLAN_MODE=full 报错。

流程（流程本身与任务类型无关，细节由包 / 验收实现）：
  1 大纲：pack.plan_outline 确定性收集文件大纲（不调模型）。
  3 规划：一次调用（plan_system()）输出 .zs（#改法、#清单、预算、派任务 / 并行派任务 / 终止）；strip_prose → autoclose →
    白名单 + 包专属检查（pack.plan_problems）→ 假模型空跑；有错带着错误重写 1 次，仍错判失败（不执行）。
    检查不过先由程序自动修机械错误（plan_autofix.py：赋值右边首词不是动词 / 说明句行 / 派任务参数过多，DSLAGENT_AUTOFIX=0 关闭），修好就不重写。
  4 执行：仓库 DSL 引擎（V2Engine = AgentEngine + 测试闸门）跑计划。计划里的 跑测试 只在结果会改变走向时真跑
    （test_gate：结果变量被 打印 / 终止 以外的语句用到，或所在 如果 的分支不全是 打印 / 终止），否则给「通过」
    的占位结果，验收时统一跑。终止 成功 才往下验收，否则回滚到开局、判失败。
  5 验收：verify.check（通过 / 缺口 / 补改入参）；有缺口 verify.fix 派 1 次补改，补改后再 check 一次。
  6 边界复核：verify.boundary（可选）；仍失败 → 状态 超出预期（不报成功）。code 验收有两条路：规划时给出的达标期望表（#期望表，
    在进 .zs 处理前切出，存 expect_table.json；覆盖 / 条数不达标补表 1 次）→ 程序按表调用函数核对，全过即成功、0 次模型调用，
    有失败 1 次 bound_judge 判表错再 bfix；无表 / 不达标 / 执行器出错 → 模型写 unittest 的旧路径。
  7 回复：reply = {result, status, reason}；v2 记各步耗时、调用次数、费用（calls.json 逐次）。
子任务回复格式：缺省 json；DSLAGENT_SUBTASK=tool 时子任务挂 dslmcp 的 dsl 工具读 / 搜 / 改文件（toolsub.py），每个子任务的结果记在 v2.子任务。
按步骤指定模型：环境变量 DSLAGENT_MODELS（JSON，cbatch 透传 dsl_options.models）{plan, sub, fix, bound} → 模型串（补表 table_fill 归 plan，bound_judge 归 bound），见 engines.py（claude / codex / grok / opencode）；
没写的步骤 sonnet；每次调用按 tag 选引擎（Model.spec），calls.json 逐条记 engine / model / effort，result.json 的 v2.models 记生效的四步。
模型调用：claude CLI，--system-prompt 替换默认提示，--tools "" --strict-mcp-config --setting-sources "" --disable-slash-commands
（同 plan35 proto），单轮流式；run(model=…) 可换成假模型（测试用）。
"""
import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

from . import common as C
from . import dslcheck as DC
from . import agents as AG
from . import dataset as DS
from . import engines, packs, verify
from . import scope as SC
from . import promptfile as PF
from . import plan_autofix as AF
from . import guard as G
from .snap import DIFF_CAP, changed, code_hash, diff_text, restore, snapshot  # noqa: F401  旧名仍从 v2 取

PKG, LIB, VERBS = C.PKG, C.LIB, C.VERBS
MODEL = engines.DEFAULT
MAX_CALLS = 20           # 规划 1（+重写 1）+ 计划内 ≤12 + 补改 1 + 边界 1 + 边界补改 1，留余量
WALL = 900
SKIP_NOTE = "未跑（这次测试的结果不改变计划走向，验收时统一跑一次全量测试）"


class Stop(Exception):
    pass


def enabled():
    return (os.environ.get("DSLAGENT_PLANNER") or "").strip().lower() == "v2"


# ------------------------------------------------------------------ 提示词

SUB_SYS = AG.SUB_JSON.system_text()

PLAN_MODE_ENV = "DSLAGENT_PLAN_MODE"      # 已去掉；只认空 / read，full 报「已移除」
READ_MAX_TURNS = AG.PLAN.turns


def check_plan_mode(value=None):
    """DSLAGENT_PLAN_MODE / dsl_options.plan_mode 已去掉（只剩 read 一种规划方式）：空或 read 忽略，full 和别的取值报 ValueError。"""
    v = ((os.environ.get(PLAN_MODE_ENV) if value is None else value) or "").strip().lower()
    if v in ("", "read"):
        return
    if v == "full":
        raise ValueError(f"{PLAN_MODE_ENV}=full 已移除：规划只有 read 一种方式（任务原文 + 文件大纲 + 按需读代码），不用再设 plan_mode")
    raise ValueError(f"{PLAN_MODE_ENV} 取值不对：{v!r}；这个选项已去掉，规划只有 read 一种方式")


def plan_system(pack=None, engine=None):
    """规划的 system：agents/plan.md 展开（公用块在 agents/shared/，资料包专属的规则按包名取）；engine=grok 时套 plan.md 里的 grok 变体。"""
    pack = pack or packs.current()
    ps = getattr(pack, "PLAN_SYSTEM", None)          # 包自带整份规划 system（要点 + 示例 .zs）；没有就是 code 式的 agents/plan.md
    if ps is not None:
        return ps(engine) if callable(ps) else ps
    return AG.PLAN.system_text(engine, getattr(pack, "RULES_KEY", pack.NAME))


def plan_user_read(task, outline="", extra=""):
    """read 方式的 user：任务原文 + 文件大纲（包没有大纲就只有任务原文）；extra 是验收按涉及的模块追加的说明（如专用夹具，没有就空）。"""
    return f"【任务原文】\n{task}" + (f"\n\n{outline}" if outline else "") + extra


# ------------------------------------------------------------------ 模型调用


call_claude = engines.call_claude      # 测试可替换 v2.call_claude；Model 缺省 backend 按名字取


class Model:
    """全部模型调用的唯一入口（有无工具是参数）：计数、墙钟、费用、逐次记录（calls/NN_tag.*.txt、self.log）。
    backend(system, user, tag, timeout) → dict（text, cost, …）或 str；只有指定了非 MODEL 的模型（规划那次）才多传 model=。
    __call__ = 无工具的一次调用（失败 → 同输入重试 1 次，仍失败抛 RuntimeError）；tool_call = 带 MCP / 只读工具的一次调用（不重试不抛模型失败，
    失败原因放在返回的 failed 里，由 plan_read_call / toolsub 决定重试还是兜底）。"""

    def __init__(self, out, backend=None, max_calls=MAX_CALLS, deadline=None, routes=None, call_max=None):
        self.out = Path(out)
        self.real = backend is None
        self.routes = routes or {}          # 步骤 → 模型串（engines.STEPS；没写的步骤走 claude MODEL）
        self.backend = backend or (lambda s, u, tag, timeout, model=None, **kw: call_claude(s, u, timeout, model, **kw))
        self.max_calls, self.deadline, self.call_max = max_calls, deadline, call_max
        self.n, self.cost, self.log = 0, 0.0, []
        self.n0, self.log_start, self.run_no = 0, 0, None      # 继续构建（modular --resume）：之前已有的调用数 / calls.json 条数；本次运行序号
        self.lock = threading.Lock()
        (self.out / "calls").mkdir(parents=True, exist_ok=True)

    def spec(self, tag, model=None, step=None):
        """这次调用用的 {engine, model, effort, spec}：DSLAGENT_MODELS 里写了该步骤就用它，否则 model 参数（旧的规划模型透传），再否则 sonnet。
        step 显式给（modbuild 的 mplan / mgen）时按它选；这两步没写就跟 sub 走。"""
        step = step or engines.step_of(tag)
        s = self.routes.get(step) if step else None
        if step in engines.MSTEPS and not s:
            s = self.routes.get("sub")
        if step == "plan_fix":       # 补改默认 sonnet，不跟 plan 走（也不吃旧的规划模型透传）
            return engines.plan_effort(engines.parse(s or engines.DEFAULT), tag)
        if s:
            return engines.plan_effort(engines.parse(s), tag)
        m = model or MODEL           # 旧的透传（DSLAGENT_PLAN_MODEL）：任意串当 claude 模型名，不校验
        return {"engine": "claude", "model": m, "effort": None, "spec": m}

    def __call__(self, system, user, tag, model=None, limits=None):
        """一次无工具调用；因保险触发 / rc≠0 / 空回复失败时同输入重试 1 次（计入调用数和费用，记录 retry=1 和首次失败原因）。返回回复文本。
        limits：这次调用单独放宽的 {idle, timeout}（如约定步骤，见 guard.contract_limits）；None = 用缺省保险。"""
        try:
            return self._text(self._call(system, user, tag, model, limits=limits))
        except RuntimeError as e:
            reason = getattr(e, "reason", None) or str(e)
            return self._text(self._call(system, user, tag, model, retry=reason, limits=limits))

    @staticmethod
    def _text(r):
        if r.get("failed"):
            e = RuntimeError(f"模型没有回应（{r['failed']}，rc={r.get('rc')}）：{(r.get('stderr') or '')[-200:]}"
                             + (f"；首次失败：{r['retry']}" if r.get("retry") else ""))
            e.reason = r["failed"]
            raise e
        return r["text"]

    def tool_call(self, system, user, tag, mcp_config, max_turns=6, model=None, read_cwd=None):
        """一次带工具的多轮调用：claude / codex 挂 mcp_config（dslmcp），grok 且给了 read_cwd 用自带只读工具。返回 backend 的 dict（含 failed / call_n）。"""
        return self._call(system, user, tag, model, tools={"mcp_config": mcp_config, "max_turns": max_turns, "read_cwd": read_cwd})

    def _call(self, system, user, tag, model=None, retry=None, tools=None, step=None, limits=None):
        with self.lock:
            if self.n >= self.max_calls:
                raise Stop(f"总模型调用已满 {self.max_calls} 次（{tag}）")
            if self.deadline and time.time() > self.deadline:
                raise Stop(f"墙钟用完（{tag} 前）")
            self.n += 1
            n = self.n
        t0 = time.time()
        tmo = G.call_timeout((self.deadline - t0) if self.deadline else None, self.call_max)
        if limits:          # 单个步骤放宽超时（modular 约定步骤）：总超时取 limits.timeout（仍不超过剩余墙钟），空闲超时传给引擎
            tmo = max(G.CALL_MIN, min(limits["timeout"], (self.deadline - t0) + 5)) if self.deadline else limits["timeout"]
        sp = self.spec(tag, model, step)
        system = AG.for_engine(system, tag, sp["engine"])
        rp = self.out / "calls" / f"{n:02d}_{tag}.reply.txt"
        kw = {"reply_path": rp} if self.real else {}
        if limits:
            kw["idle"] = limits["idle"]
        if sp["spec"] != MODEL:
            kw["model"] = sp["spec"]
        if tools is None:
            r = engines.call(sp, system, user, tmo, reply_path=rp, **({"idle": limits["idle"]} if limits else {})) if self.real and sp["engine"] != "claude" \
                else self.backend(system, user, tag, tmo, **kw)
        elif self.real and sp["engine"] == "grok" and tools["read_cwd"]:
            r = engines.call(sp, system, user, tmo, reply_path=rp, read_cwd=str(tools["read_cwd"]))     # grok 自带只读工具，不挂 dsl MCP
        elif self.real and sp["engine"] != "claude":
            r = engines.call(sp, system, user, tmo, reply_path=rp, mcp_config=str(tools["mcp_config"]))
        else:
            r = self.backend(system, user, tag, tmo, mcp_config=str(tools["mcp_config"]), max_turns=tools["max_turns"], **kw)
        if isinstance(r, str):
            r = {"text": r}
        rec = {"n": n, "tag": tag, "sec": r.get("sec", round(time.time() - t0, 2)), "ttft": r.get("ttft"),
               "cost": r.get("cost") or 0.0, "usage": r.get("usage"), "rc": r.get("rc"),
               "engine": sp["engine"], "model": _rec_model(sp), "effort": sp["effort"],
               "sys_chars": len(system), "user_chars": len(user), "t_start": round(t0, 3)}
        if self.run_no:
            rec["run"] = self.run_no
        if step:
            rec["step"] = step          # modbuild：mplan / mgen（calls.json 里连同实际 engine / model 一起记）
        if r.get("cost_est"):
            rec["cost_est"] = 1        # 被杀的调用没有 result 事件，费用是按流里 usage 估的
        if tools is not None:
            rec.update(tool=1, num_turns=r.get("num_turns"), tool_calls=r.get("tool_calls"), subtype=r.get("subtype"))
        if retry:
            rec["retry"] = 1
            rec["first_fail"] = retry
        with self.lock:
            self.cost += rec["cost"]
            self.log.append(rec)
        try:
            (self.out / "calls" / f"{n:02d}_{tag}.prompt.txt").write_text(f"[system]\n{system}\n\n[user]\n{user}", encoding="utf-8")
            rp.write_text((r.get("text") or r.get("partial") or "") + ("\n\n[stderr]\n" + r["stderr"] if r.get("stderr") else ""),
                          encoding="utf-8")
        except OSError:
            pass
        if r.get("reason") in G.GUARD_REASONS:
            why = r["reason"]
        elif r.get("subtype") == "error_max_turns":
            why = G.F_TURNS
        elif r.get("rc") not in (None, 0):
            why = f"rc={r.get('rc')}"
        elif not (r.get("text") or "").strip():
            why = G.F_EMPTY
        else:
            why = None
        if why:
            rec["failed"] = r["failed"] = why
        if retry:
            r["retry"] = retry
        r["call_n"] = n
        return r


def _rec_model(sp):
    """calls.json 记的模型：实际模型串（grok 没有模型名，记 grok；effort 另记）。"""
    m = sp["model"] or sp["engine"]
    return f"{m}:budget={sp['budget']}" if sp.get("budget") else m


def plan_read_call(M, system, user, tag, project, model, out, tools, wrap=None):
    """plan_mode=read 的一次规划调用：挂只读 dslmcp（--readonly，workdir=待改项目）、--max-turns READ_MAX_TURNS，
    保险同 call_claude（空闲超时 / 输出工具调用格式）；失败（保险触发、rc≠0、空回复、轮数用尽）同输入重试 1 次，仍失败抛 RuntimeError。
    每次尝试的工具调用（工具名、参数、返回字数）追加进 tools，并整份写到 out/plan_tools.json。返回最终回复文本。
    grok 读超限（杀掉之后）不原样重试，改走 _wrapup（收尾调用，不带工具）；wrap 是记收尾情况的 dict（触发 / 次 / 段数 / 字数）。"""
    d = out / "toollogs"
    d.mkdir(parents=True, exist_ok=True)
    first = None
    for attempt in range(1, AG.PLAN.retry.times + 1):
        base = f"{tag}_a{attempt}"
        log, cfg = d / f"{base}.jsonl", d / f"{base}.mcp.json"
        cfg.write_text(json.dumps({"mcpServers": {"dsl": {"command": sys.executable, "args": [
            str(PKG / "dslmcp.py"), "--workdir", str(project), "--log", str(log), "--verbs-root", str(VERBS), "--readonly",
            "--state", str(d / f"{base}_state")]}}}, ensure_ascii=False), encoding="utf-8")
        r = M.tool_call(system, user, tag, cfg, READ_MAX_TURNS, model=model, read_cwd=project)
        rows = []
        try:
            for line in log.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
        except OSError:
            pass
        if r.get("calls") is not None:          # grok：事件流里记的内置工具调用
            tools.extend({"调用": tag, "尝试": attempt, "序": i, "工具": x["工具"], "参数": x["参数"], "返回字数": x["返回字数"], "状态": None}
                         for i, x in enumerate(r["calls"], 1))
        else:
            tools.extend({"调用": tag, "尝试": attempt, "序": i, "工具": "dsl", "参数": x.get("code"), "返回字数": x.get("out_chars"),
                          "状态": x.get("status")} for i, x in enumerate(rows, 1))
        try:
            (out / "plan_tools.json").write_text(json.dumps(tools, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
        text = (r.get("text") or "").strip()
        why = r.get("failed")
        if not why and G.has_mark(text):
            why = G.R_MARK
            for c in M.log:
                if c["n"] == r.get("call_n"):
                    c["failed"] = why
        if not why:
            return r["text"]
        if why in (G.R_READ_CAP, G.F_TURNS) and r.get("calls") is not None:       # grok 读超限 / 到轮数上限：不再原样重读，用已读内容收尾
            return _wrapup(M, system, user, project, model, r["calls"], wrap)
        if attempt == AG.PLAN.retry.times:
            raise RuntimeError(f"模型没有回应（{why}，rc={r.get('rc')}）：{(r.get('stderr') or '')[-200:]}；首次失败：{first}")
        first = why


def _wrapup(M, system, user, project, model, calls, wrap):
    """grok 读超限后的收尾调用（tag plan_wrapup）：按已记录的读取调用在项目里重新取出内容（wrapup.reread），
    system = 原 grok system + plan.md「模板：收尾说明」，user = 原 user + 「模板：收尾提示」（带已读内容），不给任何工具。失败的重试同 Model.__call__。"""
    from . import wrapup as WU
    content, n, chars = WU.reread(project, calls)
    if wrap is not None:
        wrap.update(触发=True, 次=wrap.get("次", 0) + 1, 段数=wrap.get("段数", 0) + n, 字数=wrap.get("字数", 0) + chars)
    sys2 = system + "\n\n" + PF.template("plan.md", "收尾说明")
    user2 = user + "\n\n" + PF.template("plan.md", "收尾提示", 已读内容=content)
    return M(sys2, user2, "plan_wrapup", model)


class Client:
    """DSL 引擎的模型客户端：问 / 问JSON / 派任务 / 并行派任务 都走 Model（同一套计数和记录）。"""
    offline = True       # llm_router 见 offline=True 不分派
    model = MODEL

    def __init__(self, M):
        self.M, self.k = M, 0
        self.lock = threading.Lock()

    def chat_messages(self, messages, temperature=None, model=None, **kw):
        from tools.llm_router import _render
        prompt, system = _render(messages)
        with self.lock:
            self.k += 1
            k = self.k
        try:
            return self.M(system or SUB_SYS, prompt, f"dsl{k:02d}")
        except Stop as e:
            raise RuntimeError(str(e)) from None

    def run_tool(self, system, user, workdir, label, max_turns=6):
        """DSLAGENT_SUBTASK=tool：起一个只挂 dsl 工具的 MCP（stdio，进程由 claude CLI 拉起，随这次调用结束），调一次多轮 claude。
        返回 Model.tool_call 的 dict，外加 tool_log（MCP 追加的每次工具调用日志行，文件在任务目录 toollogs/）。"""
        with self.lock:
            self.k += 1
            k = self.k
        d = self.M.out / "toollogs"
        d.mkdir(parents=True, exist_ok=True)
        tag = f"dsl{k:02d}_{label}"
        log = d / f"{tag}.jsonl"
        cfg = d / f"{tag}.mcp.json"
        cfg.write_text(json.dumps({"mcpServers": {"dsl": {"command": sys.executable, "args": [
            str(PKG / "dslmcp.py"), "--workdir", str(workdir), "--log", str(log), "--verbs-root", str(VERBS),
            "--state", str(d / f"{tag}_state")]}}},
            ensure_ascii=False), encoding="utf-8")
        try:
            r = self.M.tool_call(system, user, tag, cfg, max_turns)
        except Stop as e:
            raise RuntimeError(str(e)) from None
        rows = []
        try:
            for line in log.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
        except OSError:
            pass
        r["tool_log"] = rows
        return r

    def chat(self, prompt, system=None, temperature=None, model=None, **kw):
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        return self.chat_messages(msgs)

    def chat_json(self, prompt, system=None, temperature=None, model=None, **kw):
        from tools.zhipu import strip_json
        return json.loads(strip_json(self.chat(prompt, system=system)))


# ------------------------------------------------------------------ 项目快照 / 改法 / 测试


# 项目快照（snapshot / changed / code_hash / diff_text / restore）见 snap.py；改法套用 / 全量测试见 verify/。


# ------------------------------------------------------------------ 计划里的 跑测试：要不要真跑


def test_gate(script, verbs=("跑测试",)):
    """主脚本里每个「闸门动词」（包的 GATED_VERBS，缺省 跑测试）语句的行号（0 起，同引擎的 _at）→ 要不要真跑。
    真跑 ⇔ 结果变量被 打印 / 终止 以外的语句用到；如果 / 否则如果 的条件用到它时，整条 如果 链的各分支都只有 打印 / 终止、
    且（有 否则，或分支里没有 终止，或链后面到块尾也只有 打印 / 终止）才算不影响走向。不赋值的闸门动词不真跑。"""
    from tools.dsl_core import BLOCK_OPENERS, normalize, split_head
    from tools.dsl_sections import split_sections
    body = split_sections(script)[0]
    lines = [normalize(l).strip() for l in body.split("\n")]
    heads = [split_head(l) if l and not l.startswith("#") else ("", "") for l in lines]
    trivial = {"print", "halt", ""}

    def block_end(i):
        """lines[i] 是块开头 → 与它配对的 结束 的行号（找不到给 len）。"""
        d = 0
        for j in range(i, len(lines)):
            h = heads[j][0]
            if h in BLOCK_OPENERS:
                d += 1
            elif h == "end":
                d -= 1
                if d == 0:
                    return j
        return len(lines)

    def chain_of(j):
        """j 是 if / elif → (if 行, [(分支起, 分支止)], 有否则, 结束行)。"""
        i = j
        if heads[j][0] == "elif":       # 往回找配对的 如果
            d = 0
            for k in range(j - 1, -1, -1):
                h = heads[k][0]
                if h == "end":
                    d += 1
                elif h in BLOCK_OPENERS:
                    if d == 0:
                        i = k
                        break
                    d -= 1
        end = block_end(i)
        parts, has_else, start, d = [], False, i + 1, 0
        for k in range(i + 1, end):
            h = heads[k][0]
            if h in BLOCK_OPENERS:
                d += 1
            elif h == "end":
                d -= 1
            elif d == 0 and h in ("elif", "else"):
                parts.append((start, k))
                start = k + 1
                has_else = has_else or h == "else"
        parts.append((start, end))
        return i, parts, has_else, end

    def only_trivial(a, b):
        return all(heads[k][0] in trivial for k in range(a, b))

    def after_trivial(end):
        d = 0
        for k in range(end + 1, len(lines)):
            h = heads[k][0]
            if h in BLOCK_OPENERS:
                return False
            if h in ("end", "elif", "else"):
                return True
            if h not in trivial:
                return False
        return True

    def needed(var, i):
        ref = re.compile(r"\{\s*" + re.escape(var) + r"(?:[.}\s])")
        for j, l in enumerate(lines):
            if j == i or not ref.search(l):
                continue
            h = heads[j][0]
            if h in ("print", "halt", "#", ""):
                continue
            if h in ("if", "elif"):
                _, parts, has_else, end = chain_of(j)
                if not all(only_trivial(a, b) for a, b in parts):
                    return True
                halts = any(heads[k][0] == "halt" for a, b in parts for k in range(a, b))
                if has_else or not halts or after_trivial(end):
                    continue
            return True
        return False

    gate = {}
    for i, (h, rest) in enumerate(heads):
        if h in verbs:
            gate[i] = False
        elif h == "set":
            name, _, val = rest.partition("=")
            if split_head(val.strip())[0] in verbs:
                gate[i] = needed(name.strip(), i)
    return gate


def _engine_cls(pack=None):
    from .engine import AgentEngine
    gated = tuple(pack.GATED_VERBS) if pack is not None and hasattr(pack, "GATED_VERBS") else ("跑测试",)
    gate_note = getattr(pack, "GATE_NOTE", SKIP_NOTE)

    class V2Engine(AgentEngine):
        """AgentEngine + 闸门：主脚本里 test_gate 判为不影响走向的闸门动词（包的 GATED_VERBS，code = 跑测试）不真跑，给通过的占位结果；
        真跑的记下当时的代码哈希和结果（验收时代码没变就复用）。空跑时闸门动词一律给占位结果。"""
        gated_verbs = gated
        gate = None
        project = None
        tests = None
        lazy_reason = True

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.subtask_mode = DC.env_mode()

        def _no_edits(self, rest):
            """tool 模式：子任务在工具里改完了文件，结果里没有 edits——计划里的 改文件 {r.结果} 当空操作。"""
            args = [self.expand(a) for a in rest.split()]
            if len(args) != 1:
                return False
            try:
                e = args[0] if isinstance(args[0], dict) else json.loads(args[0])
            except (TypeError, json.JSONDecodeError):
                return False
            return (isinstance(e, dict) and isinstance(e.get("edits"), list) and not e["edits"]
                    and e.get("old") is None and not e.get("files"))

        def _do_verb(self, name, rest, lineno, assign_to=None):
            if name == "改文件" and self.subtask_mode == "tool" and not self.dry_run and self._no_edits(rest):
                return self._deliver({"ok": "是", "msg": "（结果里没有 edits：子任务在工具里已改好，空操作）", "n": 0}, assign_to)
            if name not in self.gated_verbs:
                return super()._do_verb(name, rest, lineno, assign_to)
            if self.dry_run:
                return self._deliver({"passed": "是", "summary": "（空跑）" + gate_note}, assign_to)
            log = self.tests if self.tests is not None else []
            if self._depth == 0 and self.gate is not None and not self.gate.get(self._at, True):
                log.append({"line": self._at + 1, "mode": "skipped"})
                return self._deliver({"passed": "是", "summary": gate_note}, assign_to)
            t0 = time.time()
            super()._do_verb(name, rest, lineno, assign_to)
            res = self.vars.get(assign_to) if assign_to else None
            if self.project is not None:
                v = res if isinstance(res, dict) else {}
                log.append({"line": self._at + 1, "mode": "real", "sec": round(time.time() - t0, 1),
                            "passed": v.get("passed") == "是", "summary": str(v.get("summary", ""))[:4000],
                            "hash": code_hash(snapshot(self.project)), "known": isinstance(res, dict)})
    return V2Engine


# ------------------------------------------------------------------ 3 规划检查


def scripts_for(plan_dir, subs):
    from . import plan as DP
    return {f"_plan/{k}": Path(plan_dir) / k for k in subs}      # 定位.zs / 读改测.zs 是旧路径的，v2 不映射


def check(project, work, script, task, pack=None):
    """plan.py 的检查 + 有 预算 + 资料包专属检查（pack.plan_problems，code：#清单、旧写法 正则）+ 空跑。
    返回 (问题文本或空, 主脚本, 子脚本, 记录)。"""
    from tools.dsl_sections import split_sections

    from . import plan as DP
    pack = pack or packs.current()
    rec = {}
    main, subs = DP.split_subs(script)
    probs = DP.whitelist_check(main, subs, libs=(), only=(packs.verbs_of(pack), packs.use_of(pack)))      # 白名单由包生成；v2 计划不用 执行 定位.zs / 读改测.zs
    body, _, cl, _ = split_sections(main)
    generic = []
    if not re.search(r"^\s*预算\s", body, re.M):
        generic.append("开头缺 预算 语句（第二行写 预算 调用 N 秒 M）")
    probs += pack.plan_problems(main, body, cl, generic) if hasattr(pack, "plan_problems") else generic
    if not probs:
        probs += DC.edit_problems(project, main)
    if probs:
        rec["阶段"] = "静态"
        return "白名单 / 格式检查没过：\n" + "\n".join(probs[:12]), main, subs, rec
    t0 = time.time()
    err, n, out = DP.dry_run(project, work, main, subs, task, scripts_for, MODEL, engine_cls=_engine_cls(pack))
    rec.update(阶段="空跑", 空跑秒=round(time.time() - t0, 1), 空跑假调用=n)
    return (f"用假模型空跑报错：{err}" if err else ""), main, subs, rec


# ------------------------------------------------------------------ 主流程


def run(project, task, out_dir, test_cmd=None, wall=WALL, model=None, max_calls=MAX_CALLS, boundary=True, scope=None, plan_fix=None, pack=None,
        call_max=None):
    """跑一次 v2。project 里直接改文件；记录写进 out_dir（calls/、calls.json、plan*.zs、outline.md、boundary/、result.json）。
    model：假模型 backend(system, user, tag, timeout) → str|dict（测试用），缺省走 claude CLI。
    scope：允许改动的路径（目录前缀 / 精确文件 / glob，"a/,b/" 或列表；缺省取包的 scope_for，再缺省看计划里的 #范围 块，都没有就不启用范围闸，见 scope.py）。
    pack：资料包名或包对象（缺省看环境变量 DSLAGENT_PACK，再缺省 code；接口见 packs/__init__.py）。
    test_cmd：交给验收 prepare 的「给定配置」（code 是测试命令，别的包不用）。
    call_max：单次模型调用的总超时上限（缺省 guard.CALL_MAX；entry.run_pack 缺省按包声明的 CALL_MAX 覆盖，仍不超过剩余墙钟）。
    返回结果字典（runner.run 同款字段 + reply / v2）。"""
    from . import plan as DP
    from . import prompts as DPR

    project = Path(project).resolve()
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    plan_tools, routes, reads = [], {}, {}
    record = model is None and call_claude is engines.call_claude or bool(os.environ.get(DS.ENV))      # 假模型的测试运行不写训练数据（除非显式给了目录）
    try:
        pack = packs.pick(pack) if pack is not None else packs.current()
        bad = packs.validate(pack)
        if bad:
            raise ValueError(f"资料包 {pack.NAME} 的声明不合格：" + "；".join(bad))
        ver = packs.verifier_of(pack)
        check_plan_mode()
        routes = engines.validate({**engines.from_env(), **({"plan_fix": plan_fix} if plan_fix else {})}, DC.env_mode())
    except ValueError as e:
        pack = ver = None
        pick_err = str(e)
    M = Model(out, backend=model, max_calls=max_calls, deadline=t_start + wall, routes=routes, call_max=call_max)
    steps, info = {}, {"检查": [], "重写": False, "子任务模式": DC.env_mode(), "子任务": []}
    res = {"project": str(project), "test_cmd": test_cmd, "kind": "task", "planner": "v2", "fixed": False,
           "engine_used": "v2", "versions": 0, "calls": 0, "cost": 0.0, "seconds": 0, "stop": "", "dir": str(out),
           "calls_log": str(out / "calls.json"), "version_log": [], "subcalls": [], "changed_files": [], "handoff": "",
           "report": "", "v2": info}
    state = {"status": "失败", "reason": ""}
    accept, bound = {}, {"跑了": False}
    scope_arg = SC.parse(scope)
    scope = scope_arg
    if pack is not None:
        try:
            scope = scope_arg = packs.scope_of(pack, task, project, scope)      # 命令行 / 参数优先，其次包声明的 scope_for
        except Exception as e:  # noqa: BLE001  包的 scope_for 出错按声明不合格处理
            pack = None
            pick_err = f"资料包 scope_for 出错：{type(e).__name__}: {str(e)[:200]}"

    def step(name, t0):
        steps[name] = round(time.time() - t0, 1)

    if pack is None:
        state["reason"] = pick_err
        return _recorded(_finish(res, out, M, steps, state, accept, bound, {}, {}, t_start), record, project, task, reads)
    cfg, cfg_err = ver.prepare(project, test_cmd, out)          # 验收开工前的准备（code：探测测试命令并设环境）
    res["test_cmd"] = cfg
    if cfg_err:
        state["reason"] = cfg_err
        return _recorded(_finish(res, out, M, steps, state, accept, bound, {}, {}, t_start), record, project, task, reads)
    test_cmd = cfg
    info["pack"] = pack.NAME
    info["models"] = engines.effective({**routes, **({} if "plan" in routes or not os.environ.get("DSLAGENT_PLAN_MODEL")
                                                     else {"plan": os.environ["DSLAGENT_PLAN_MODEL"]})})
    from . import reason as _R
    _R.STATE.update(snap=None, root=None, task="", log=[], fires=[])      # 上一次运行的开局快照不带过来；这次第一次写文件时再设
    base = snapshot(project, pack)
    cur = base
    main, subs, script = "", {}, ""
    try:
        # ---- 1 大纲（没有资料包全文、没有补查）
        t0 = time.time()
        o = packs.materials_of(pack, task, project, scope_arg)          # 资料：包给规划模型看什么（code = 文件大纲）
        outline = o["text"]
        info.update(o["记录"])
        strict = bool(getattr(pack, "STRICT_SCOPE", False))
        SC.activate(scope_arg if strict else None)           # 包声明 STRICT_SCOPE：规划时的空跑也按范围拦写；计划里的 #范围 块定下来后执行前再换一次
        info["大纲字符"] = len(outline)
        (out / "outline.md").write_text(outline, encoding="utf-8")
        first_user = plan_user_read(task, outline, ver.fixture_notes(outline) if hasattr(ver, "fixture_notes") else "")
        step("1大纲", t0)
        # ---- 3 规划
        t0 = time.time()
        problem = ""
        plan_model = os.environ.get("DSLAGENT_PLAN_MODEL") or MODEL
        if "plan" in routes:
            if os.environ.get("DSLAGENT_PLAN_MODEL") and os.environ["DSLAGENT_PLAN_MODEL"] != routes["plan"]:
                info["规划模型说明"] = f"models.plan={routes['plan']} 优先，没用 model={os.environ['DSLAGENT_PLAN_MODEL']}"
            plan_model = routes["plan"]
        info["规划模型"] = res["plan_model"] = plan_model
        wrap = {"触发": False, "次": 0, "段数": 0, "字数": 0}
        table, tnote = None, "无表"          # 规划回复里 #期望表 之后的块（验收按表核对边界）；plan_fix 回复里有新表就换，没有就保留原表
        if M.spec("plan", plan_model)["engine"] == "grok":
            info["收尾"] = wrap
        try:
            for k in range(1 + AG.PLAN.rewrites):
                user = first_user if k == 0 else DPR.fix_prompt(script, problem, table_kept=bool(table) and hasattr(ver, "keep_table")
                                                                  and not ver.problem_about_table(problem))
                tag = "plan" if k == 0 else "plan_fix"
                sp = M.spec(tag, plan_model)
                if k:
                    info.setdefault("plan_fix引擎", []).append({"引擎": sp["engine"], "模型": sp["model"], "强度": sp["effort"]})
                raw = plan_read_call(M, plan_system(pack, sp["engine"]), user, tag, project,
                                     plan_model, out, plan_tools, wrap)
                (out / f"plan_v{k + 1}.raw.txt").write_text(raw, encoding="utf-8")
                raw, plan_scope = SC.split(raw)       # #范围 块在进 .zs 处理之前切出；命令行 / 参数的范围优先
                if plan_scope and not scope_arg:
                    scope = plan_scope
                trec = None
                if hasattr(ver, "split_table"):
                    raw, rows, note = ver.split_table(raw)       # 表在进 .zs 处理（strip_prose / autoclose / check）之前切出
                    if k == 0:
                        table, tnote = rows, ("" if rows else note)
                    else:       # plan_fix：原表由程序保住（问题与表无关时不采用模型回的表）
                        table, trec = ver.keep_table(table, rows, problem)
                        info.setdefault("期望表保留", []).append(trec)
                        if table:
                            tnote = ""
                script, _ = DP.strip_prose(raw)
                script, n_close, _ = DP.autoclose(script)
                (out / f"plan_v{k + 1}.zs").write_text(script, encoding="utf-8")
                problem, main, subs, crec = check(project, out / "dry", script, task, pack)
                fixes, problem0 = [], problem
                if problem and AF.enabled():       # 先由程序修机械错误（见 plan_autofix.py）；修完没过的带着修过的计划和剩余报错去 plan_fix
                    (out / f"plan_v{k + 1}.orig.zs").write_text(script, encoding="utf-8")
                    script, fixes, problem, m2, s2, c2 = AF.autofix(
                        script, problem, lambda s_: check(project, out / "dry", s_, task, pack), packs.verbs_of(pack))
                    if fixes:
                        main, subs, crec = (m2, s2, c2) if m2 is not None else (main, subs, crec)
                        (out / f"plan_v{k + 1}.zs").write_text(script, encoding="utf-8")
                        info.setdefault("自动修复", []).append(f"自动修复：第 {k + 1} 版计划 {len(fixes)} 处（" + "、".join(
                            f"{t} ×{sum(1 for x in fixes if x['类型'] == t)}" for t in dict.fromkeys(x["类型"] for x in fixes))
                            + ("；修完检查通过" if not problem else "；仍有报错，交给 plan_fix"))
                info["检查"].append(dict(crec, 补结束=n_close, 问题=problem0[:1500], **({"plan_fix期望表": trec} if trec else {}),
                                       **({"自动修复": fixes, "自动修复后问题": problem[:1500]} if fixes else {})))
                if not problem:
                    break
                info["重写"] = True
        finally:      # 规划结束、执行还没开始：项目还是开局快照，grok 的读码返回内容此时重取（给训练数据用）
            reads.update(DS.capture_reads(project, plan_tools))
        exp = None
        if not problem and hasattr(ver, "table_stage"):     # 零调用检查（规则覆盖 + 每函数条数），不达标补表 1 次
            exp = ver.table_stage(M, task, table, tnote, main, out)
            info["期望表"] = {k: v for k, v in exp.items() if k != "rows"}
            info["期望表"]["表条数"] = len(exp["rows"] or [])
        step("3规划", t0)
        info["规划工具"] = {"次数": len(plan_tools), "返回字数": sum(x.get("返回字数") or 0 for x in plan_tools)}
        if problem:
            raise Stop("计划 .zs 重写 1 次仍没过检查：" + problem[:400])
        (out / "plan.zs").write_text(script, encoding="utf-8")
        # ---- 4 执行
        t0 = time.time()
        SC.activate(scope if strict else None)
        gate = test_gate(main, tuple(pack.GATED_VERBS) if hasattr(pack, "GATED_VERBS") else ("跑测试",))
        info["测试闸门"] = {str(k + 1): v for k, v in gate.items()}
        plan_dir = out / "plan_subs"
        DP.write_subs(plan_dir, subs)
        Eng = _engine_cls(pack)
        eng = Eng(client=Client(M), workdir=project, verbose=False, verbs_root=VERBS,
                  scripts=scripts_for(plan_dir, subs))
        eng.gate, eng.project, eng.tests = gate, project, []
        eng.model = MODEL
        eng.sublog = info["子任务"]
        eng.vars["task"] = task
        err = ""
        try:
            eng.run(main)
        except Exception as e:  # noqa: BLE001  脚本报错按失败处理
            err = f"{type(e).__name__}: {str(e)[:800]}"
        halted = eng.halted
        (out / "plan_out.txt").write_text("\n".join(eng.output) + (f"\n\n[报错] {err}" if err else "")
                                          + f"\n\n[终止] {json.dumps(halted, ensure_ascii=False)}", encoding="utf-8")
        info.update(终止=halted, 报错=err, 清单=eng.checklist, 计划内测试=eng.tests,
                    预算={"calls": eng.usage.calls, "max_calls": eng.usage.max_calls, "max_secs": eng.usage.max_secs})
        step("4执行", t0)
        res["versions"] = 1
        if err:
            raise Stop(f"脚本报错：{err}")
        if not halted:
            raise Stop("脚本跑完没有 终止（没自报成功）")
        if halted.get("status") != "成功":
            state["status"] = "超出预期" if halted.get("status") == "超出预期" else "失败"
            raise Stop(f"脚本终止 {halted.get('status')}：{str(halted.get('reason'))[:300]}")
        # ---- 5 验收
        t0 = time.time()
        cur, oos = _scope_gate(project, pack, base, scope, accept, "验收")
        pr = {"task": task, "base": base, "cur": cur, "main": main, "tests": eng.tests, "accept": accept,
              "test_cmd": test_cmd, "stage": "验收", "out": out, "bound": bound, "expect_table": exp, "scope": scope or []}
        chk = ver.check(project, pr, eng.checklist)
        if oos:
            _scope_merge(chk, task, oos, scope)
        if not chk["通过"]:
            accept["补改"] = ver.fix(M, project, chk, "fix")
            cur, oos = _scope_gate(project, pack, base, scope, accept, "补改后")
            pr.update(cur=cur, stage="补改后")
            chk = ver.check(project, pr, eng.checklist)
        accept["通过"] = chk["通过"]
        accept["测试摘要"] = chk["测试摘要"]
        step("5验收", t0)
        if not accept["通过"]:
            state.update(status="失败", reason=chk["原因"])
            raise _Done()
        if oos:      # 补改后仍越界（已恢复）：不判成功
            state.update(status="部分成功", reason=f"补改后仍越界改了范围外的文件（已恢复）：{'、'.join(oos)}；范围 {'、'.join(scope)}")
            raise _Done()
        # ---- 6 边界复核
        if boundary and hasattr(ver, "boundary"):
            t0 = time.time()
            state.update(ver.boundary(M, project, pr))
            step("6边界复核", t0)
        else:
            state.update(status="成功", reason="")
    except _Done:
        pass
    except Stop as e:
        state["reason"] = str(e)
        if state["status"] == "成功":
            state["status"] = "失败"
    except Exception as e:  # noqa: BLE001  流程自身出错不能让 cbatch 拿不到结果
        state.update(status="失败", reason=f"v2 流程出错：{type(e).__name__}: {str(e)[:400]}")
    finally:
        SC.activate(None)
    if state["status"] != "成功" and not accept:
        # 计划没跑成（检查没过 / 报错 / 没自报成功）：回滚到开局，项目保持原样
        now = snapshot(project, pack)
        restore(project, base, changed(base, now))
        info["回滚"] = changed(base, now)
    return _recorded(_finish(res, out, M, steps, state, accept, bound, base, snapshot(project, pack), t_start), record, project, task, reads)


# ------------------------------------------------------------------ 新建项目：跳过规划，直接执行固定模板

NEWPROJ_CALLS = 8        # 模板里 预算 调用 8：实体 / sql / zs / ui 各 ≤ 2 次
NEWPROJ_SPLIT_WALL = 2400      # split 模板默认墙钟（功能多，逐个写）
FEATURE_REC = re.compile(r"^功能记录 (\S+) (\S+) (通过|失败|跳过) (\d+)\s*$", re.M)
FEATURE_ERR = re.compile(r"^功能失败 (\S+) (\S+) (.*)$", re.M)
FEATURE_UNIMPL = re.compile(r"^功能未实现 (\S+) (.*)$", re.M)


def newproj_split_calls():
    """split 模板的总调用上限：4 + 功能数上限×10（NEWPROJ_SPLIT_MAX_FEATURES，默认 12）。模板里 预算 按实际功能数再收紧。"""
    try:
        n = max(1, int(os.environ.get("NEWPROJ_SPLIT_MAX_FEATURES") or 12))
    except ValueError:
        n = 12
    return 4 + 10 * n


def feature_records(output):
    """从引擎输出里解析「功能记录 名 步骤 结果 次数」「功能失败 名 步骤 原因」→ [{名, 步骤: {结果, 尝试, 重写}}, …]（保持出现顺序）。
    重写 = 尝试次数 - 1（跳过为 0）。失败的功能带 失败原因。"""
    feats = {}
    for m in FEATURE_REC.finditer(output):
        n, step, res, k = m.group(1), m.group(2), m.group(3), int(m.group(4))
        f = feats.setdefault(n, {"名": n, "步骤": {}})
        f["步骤"][step] = {"结果": res, "尝试": k, "重写": max(0, k - 1)}
    for m in FEATURE_ERR.finditer(output):
        f = feats.setdefault(m.group(1), {"名": m.group(1), "步骤": {}})
        f["失败步骤"], f["失败原因"] = m.group(2), m.group(3)[:600]
    for m in FEATURE_UNIMPL.finditer(output):
        f = feats.setdefault(m.group(1), {"名": m.group(1), "步骤": {}})
        try:
            v = json.loads(m.group(2))
            f["未实现规则"] = [str(x) for x in v] if isinstance(v, list) else [m.group(2)]
        except ValueError:
            f["未实现规则"] = [m.group(2)]
    return list(feats.values())


def _req_text(req):
    """需求：一行且是存在的文件路径就读文件，否则当需求原文。"""
    s = str(req or "")
    if s and "\n" not in s and len(s) < 500:
        try:
            if Path(s).is_file():
                return Path(s).read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return s.strip()


NEWPROJ_LAYERED_WALL = 3600     # layered 模板默认墙钟（文件多，逐个写）
NEWPROJ_MODULAR_WALL = 5400     # modular 模板默认墙钟（顶层规划 + 层次 + 分层逐文件，更多步）


def run_newproj(req, project, out_dir, model=None, wall=None, max_calls=None, split=False, layered=False, cost_cap=None, modular=False, resume=False, codex_cap=None, contract=None, from_plan=None):
    """新建项目入口：不规划，直接执行 packs/newproj/newproj.zs（pack=newproj）。
    req：需求原文，或一个存在的文本文件路径；project：要新建的项目目录（不存在就建，也是引擎工作目录）；
    out_dir：记录目录（calls/、calls.json、plan.zs、plan_out.txt、result.json）；model：假模型 backend（测试用）。
    步骤：模板过 check（白名单 + 空跑）→ 引擎执行（预算、模型调用计数 / 墙钟 / 费用同 v2）→ 终止 成功 才算成功。
    没有验收层；失败时已生成的文件留在项目里供排查（不回滚）。返回结果字典（同 run 的字段）。
    split=True：改跑 newproj_split.zs（功能清单 → 实体 → 逐个功能 sql / zs / ui，每个文件单独检查单独重写 1 次）；默认 False 仍是旧模板。
    split 时某功能两次不过只撤回该功能、继续下一个：结果 v2.功能 记每个功能每步的通过 / 重写次数，v2.结论 = 成功 | 部分成功 | 失败，
    部分成功时 fixed=False、stop 以「部分成功：」开头并列出失败功能（status 仍是 失败）。wall 缺省：旧模板 WALL，split NEWPROJ_SPLIT_WALL。
    layered=True：三级规划、一步步推进（layered.py，不走 DSL 模板）：确认分层 → 确认文件 → 逐层逐文件（每个文件先单独规划再生成，各自检查），失败的文件撤回并让依赖它的文件跳过；
    result.json v2.文件 记每个文件的层 / 实体 / 结果 / 尝试 / 重写 / 失败原因 / 未实现规则；cost_cap（缺省读环境变量 NEWPROJ_COST_CAP，不设不限）：Claude 侧累计花费达到就不再调模型，
    以「部分成功：花费达上限」结束。总调用上限随进度按文件数放宽（layered.py Run.bump）。wall 缺省 NEWPROJ_LAYERED_WALL。
    modular=True：顶层规划 → 层次 × 模块 → 按层逐层构建（modbuild.py）：能力清单（程序）→ 顶层规划（PLAN.md）→ 层次×模块（LAYERS.md）→ 数据 / 查询 / 流程 / 接口 / 界面逐层、
    层内按构建顺序逐模块，每个文件先规划再生成；capabilities.md / PLAN.md / LAYERS.md 写在 out_dir；result.json v2.文件 每文件记 层 / 模块 / 结果 / 尝试 / 失败原因 / 未实现规则，
    v2.顶层规划 / v2.层次 记两步的结果。cost_cap、失败隔离同 layered。wall 缺省 NEWPROJ_MODULAR_WALL。
    modular + resume=True（CLI --modular --resume）：继续上次的构建——project / out_dir 就是上次的；不重做顶层规划和层次×模块（读 out_dir/plan/top.zs、plan/layers.zs，老产物读 top.json / split.json 或从 result.json / calls/ 还原，见 modbuild.restore_state），
    上次通过且仍在磁盘、仍过检查的文件跳过，失败 / 跳过 / 未做的按原顺序重做（失败的带上次失败原因）；cost_cap 只算本次新花的；
    result.json 保留上次记录：v2.运行 逐次追加（序号 / 结论 / 花费 / 本次动过的文件…），v2.累计花费；calls.json 追加、每条标 run 序号；上次的 result.json 另存 result.run<N>.json。
    还原不了（没有 result.json / 规划还原不了）时不写任何文件，直接返回失败。
    modular 默认先约定接口（contract=None/True；contract=False = 原来的逐文件规划，--no-contract）：数据层后每模块一次调用写约定（模型写骨架文件：queries/*.sql、scripts/*.zs、routes/*.zs、ui/*.ui 的头部声明；CONTRACTS.md / contracts.json 由骨架生成），程序校验冻结，
    之后各文件只按约定实现并检查与约定一致，全部实现后试调一轮；v2.约定 记每模块约定项数。from_plan=旧输出目录（--from-plan）：读回旧运行的顶层规划与层次×模块，跳过前两步，新目录从数据层做起。"""
    from . import plan as DP
    if layered or modular:
        split = False
    if modular:
        layered = False
    wall = wall or (NEWPROJ_MODULAR_WALL if modular else NEWPROJ_LAYERED_WALL if layered else NEWPROJ_SPLIT_WALL if split else WALL)
    user_max = max_calls
    max_calls = max_calls or (2 if layered or modular else newproj_split_calls() if split else NEWPROJ_CALLS)

    project = Path(project).resolve()
    project.mkdir(parents=True, exist_ok=True)
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    task = _req_text(req)
    pack = packs.pick("newproj")
    try:
        routes = engines.validate(engines.from_env(), DC.env_mode())      # 同 run：DSLAGENT_MODELS；问 / 问JSON 的调用归 sub 步骤
    except ValueError as e:
        routes = {}
        route_err = str(e)
    else:
        route_err = ""
    M = Model(out, backend=model, max_calls=max_calls, deadline=t_start + wall, routes=routes)
    steps, info = {}, {"检查": [], "重写": False, "子任务模式": "json", "子任务": [], "pack": pack.NAME,
                  "模型": engines.effective(routes)}
    res = {"project": str(project), "test_cmd": "", "kind": "newproj", "planner": "v2", "fixed": False,
           "engine_used": "v2", "versions": 0, "calls": 0, "cost": 0.0, "seconds": 0, "stop": "", "dir": str(out),
           "calls_log": str(out / "calls.json"), "version_log": [], "subcalls": [], "changed_files": [], "handoff": "",
           "report": "", "v2": info}
    state = {"status": "失败", "reason": ""}
    base = snapshot(project, pack)
    try:
        if route_err:
            raise Stop("DSLAGENT_MODELS 不合格：" + route_err)
        if not task:
            raise Stop("需求为空")
        if resume and not modular:
            raise Stop("--resume 只用于 --modular")
        if from_plan and (not modular or resume):
            raise Stop("--from-plan 只用于 --modular，且不能和 --resume 一起用")
        if modular:
            from . import modbuild as MB
            from . import layered as LY
            info.update(split=False, layered=False, modular=True)
            rs = fp = None
            use_contract = True if contract is None else bool(contract)       # 先约定接口再按约定实现；--no-contract 走原来的逐文件规划
            if from_plan:
                try:
                    fp = MB.load_plan(from_plan, task)
                except MB.ResumeError as e:
                    state["reason"] = f"从已有规划开始：{e}"
                    res.update(stop=state["reason"], status="失败", fixed=False, reply={"result": {}, "status": "失败", "reason": state["reason"]})
                    return res
                info["从已有规划"] = {"目录": fp["from"], "从哪还原": fp["restored"]}
            if resume:
                try:
                    rs = MB.restore_state(out, task)
                except MB.ResumeError as e:         # 还原不了就原样返回：不能让失败的 _finish 把上次的 result.json / calls.json 盖掉
                    state["reason"] = f"继续构建：{e}"
                    res.update(stop=state["reason"], status="失败", fixed=False, reply={"result": {}, "status": "失败", "reason": state["reason"]})
                    return res
                if (out / "result.json").is_file():
                    shutil.copyfile(out / "result.json", out / f"result.run{rs['run_no'] - 1}.json")
                use_contract = rs["contract"]
                info["继续构建"] = {"序号": rs["run_no"], "从哪还原": rs["restored"] or ["plan/top.zs / plan/layers.zs"], "上次累计花费": rs["prior_cost"], "上次已用调用": rs["n0"]}
            t0 = time.time()
            try:
                out_m = MB.run_modular(M, task, project, Stop, cost_cap if cost_cap is not None else LY.env_cap(), user_max, out_dir=out, resume=rs, codex_cap=codex_cap, contract=use_contract, from_plan=fp)
            finally:
                steps["执行"] = round(time.time() - t0, 1)
            this = dict(out_m["本次"], 结论=out_m["结论"], 状态=out_m["状态"], 原因=out_m["原因"][:400], 花费=round(M.cost, 4), 调用=M.n - M.n0,
                        秒=round(time.time() - t_start, 1), 时间=time.strftime("%Y-%m-%d %H:%M:%S"))
            runs = [*(rs["runs"] if rs else []), this]
            info.update(文件=out_m["文件"], 清单=out_m["清单"], 整体问题=out_m["整体问题"], 结论=out_m["结论"], codex调用=out_m["codex调用"],
                        顶层规划=out_m["顶层规划"], 层次=out_m["层次"], 规则未覆盖=out_m["规则未覆盖"], 试调=out_m.get("试调"), 约定模式=out_m.get("约定模式"), 约定=out_m.get("约定"), contract=bool(out_m.get("约定模式")), 预算={"calls": M.n - M.n0, "max_calls": M.max_calls - M.n0},
                        运行=runs, 累计花费=round(sum(float(x.get("花费") or 0) for x in runs), 4))
            (out / "plan_out.txt").write_text(json.dumps(out_m, ensure_ascii=False, indent=1), encoding="utf-8")
            res["versions"] = 1
            if out_m["状态"] != "成功":
                raise Stop(out_m["原因"][:800])
            state.update(status="成功", reason="")
            return _finish(res, out, M, steps, state, {}, {"跑了": False}, base, snapshot(project, pack), t_start)
        if layered:
            from . import layered as LY
            info.update(split=False, layered=True)
            t0 = time.time()
            try:
                out_l = LY.run_with_cap(M, task, project, Stop, cost_cap if cost_cap is not None else LY.env_cap(), user_max)
            finally:
                steps["执行"] = round(time.time() - t0, 1)
            info.update(文件=out_l["文件"], 清单=out_l["清单"], 整体问题=out_l["整体问题"], 结论=out_l["结论"], codex调用=out_l["codex调用"],
                        预算={"calls": M.n, "max_calls": M.max_calls})
            (out / "plan_out.txt").write_text(json.dumps(out_l, ensure_ascii=False, indent=1), encoding="utf-8")
            res["versions"] = 1
            if out_l["状态"] != "成功":
                raise Stop(out_l["原因"][:800])
            state.update(status="成功", reason="")
            return _finish(res, out, M, steps, state, {}, {"跑了": False}, base, snapshot(project, pack), t_start)
        script = (pack.SPLIT_TEMPLATE if split else pack.TEMPLATE).read_text(encoding="utf-8")
        info["split"] = bool(split)
        (out / "plan.zs").write_text(script, encoding="utf-8")
        t0 = time.time()
        problem, main, subs, crec = check(project, out / "dry", script, task, pack)
        info["检查"].append(dict(crec, 问题=problem[:1500]))
        steps["检查"] = round(time.time() - t0, 1)
        if problem:
            raise Stop("固定模板没过检查：" + problem[:400])
        t0 = time.time()
        Eng = _engine_cls()
        eng = Eng(client=Client(M), workdir=project, verbose=False, verbs_root=VERBS, scripts={})
        eng.gate, eng.project, eng.tests = {}, project, []
        eng.model = MODEL
        eng.system = pack.model_system()       # 不设就落到子任务 JSON edits 的系统提示（SUB_SYS），与模板要求的分隔块格式冲突
        eng.sublog = info["子任务"]
        eng.vars["task"] = task
        err = ""
        try:
            eng.run(main)
        except Exception as e:  # noqa: BLE001  脚本报错按失败处理
            err = f"{type(e).__name__}: {str(e)[:800]}"
        halted = eng.halted
        if split:
            info["功能"] = feature_records("\n".join(eng.output))
        (out / "plan_out.txt").write_text("\n".join(eng.output) + (f"\n\n[报错] {err}" if err else "")
                                          + f"\n\n[终止] {json.dumps(halted, ensure_ascii=False)}", encoding="utf-8")
        info.update(终止=halted, 报错=err, 预算={"calls": eng.usage.calls, "max_calls": eng.usage.max_calls, "max_secs": eng.usage.max_secs})
        steps["执行"] = round(time.time() - t0, 1)
        res["versions"] = 1
        if err:
            raise Stop(f"脚本报错：{err}")
        if not halted:
            raise Stop("脚本跑完没有 终止（没自报成功）")
        if halted.get("status") != "成功":
            if split and str(halted.get("reason")).startswith("部分成功"):
                info["结论"] = "部分成功"
            raise Stop(f"脚本终止 {halted.get('status')}：{str(halted.get('reason'))[:400]}" if info.get("结论") != "部分成功" else str(halted.get("reason"))[:600])
        state.update(status="成功", reason="")
        info["结论"] = "成功"
    except Stop as e:
        state["reason"] = str(e)
    except Exception as e:  # noqa: BLE001  流程自身出错也要有结果
        state["reason"] = f"newproj 流程出错：{type(e).__name__}: {str(e)[:400]}"
    info.setdefault("结论", "失败")
    return _finish(res, out, M, steps, state, {}, {"跑了": False}, base, snapshot(project, pack), t_start)


def _scope_gate(project, pack, base, scope, accept, stage):
    """范围闸：快照对比，范围外的改动恢复成改前内容。返回 (恢复后的快照, 越界文件列表)；越界记进 accept["越界"]。没启用范围就原样返回。"""
    cur = snapshot(project, pack)
    oos = SC.outside(changed(base, cur), scope)
    if oos:
        restore(project, base, oos)
        cur = snapshot(project, pack)
        accept.setdefault("越界", []).append({"阶段": stage, "文件": oos, "范围": scope})
    return cur, oos


def _scope_merge(chk, task, oos, scope):
    """越界缺口并入验收结果：不通过，缺口列表加一条，补改入参追加范围说明（没有补改入参就以任务原文起头）。"""
    chk["通过"] = False
    chk["缺口列表"] = list(chk.get("缺口列表") or []) + [SC.gap(oos, scope)]
    chk["补改入参"] = (chk.get("补改入参") or f"【任务原文】\n{task}\n\n【缺口列表】\n1. {SC.gap(oos, scope)['说明']}") + SC.fix_note(oos, scope)
    chk["原因"] = (chk.get("原因") or "验收没过（已派 1 次补改）：") + f"；越界改动：{'、'.join(oos)}"


class _Done(Exception):
    pass


def _recorded(res, record, project, task, reads):
    """收尾后写一条训练样本（tools/dslagent/dataset.py）；写失败只在 stderr 记一行，不改 res。"""
    if record:
        DS.record(res["dir"], project=project, task=task, reads=reads)
    return res


def _finish(res, out, M, steps, state, accept, bound, base, now, t_start):
    ch = changed(base, now) if base is not None else []
    res.update(fixed=state["status"] == "成功", stop="" if state["status"] == "成功" else state["reason"],
               calls=M.n - M.n0, cost=round(M.cost, 4), seconds=round(time.time() - t_start, 1), changed_files=ch,
               diff=diff_text(base, now, 3000) if base is not None else "", status=state["status"])
    res["calls_by_purpose"] = {}
    for c in M.log[M.log_start:]:
        k = re.sub(r"\d+$|_reask$", "", c["tag"])
        res["calls_by_purpose"][k] = res["calls_by_purpose"].get(k, 0) + 1
    res["v2"].update(步骤秒=steps, 验收=accept, 边界复核=bound)
    tests = res["v2"].get("计划内测试") or []
    res["final_test"] = (accept.get("测试摘要") or "")[:2000]
    res["reply"] = {"result": {"改动文件": ch, "测试": accept.get("测试摘要", "")[:300],
                           "边界复核": bound.get("结论", "未跑"), "步骤秒": steps, "调用": M.n - M.n0,
                           "费用": round(M.cost, 4), "测试次数": {
                               "真跑": sum(1 for x in tests if x["mode"] == "real"),
                               "跳过": sum(1 for x in tests if x["mode"] == "skipped"),
                               "复用": sum(1 for x in accept.get("测试", []) if x["方式"] == "复用")}},
                    "status": state["status"], "reason": state["reason"]}
    res["report"] = report(res)
    if not res["fixed"]:
        res["handoff"] = (f"【停下原因】（v2 规划路径，状态 {state['status']}）{state['reason']}\n"
                          f"【它已经做的修改（相对开始时的 diff）】\n{res['diff'] or '（没有改动）'}\n"
                          f"【当前测试】\n{res['final_test'] or '（没跑到验收）'}")[:7000]
    try:
        (out / "calls.json").write_text(json.dumps(M.log, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    except OSError:
        pass
    return res


def report(res):
    r = res["reply"]
    head = (f"DSL v2 {r['status']}" + (f"：{r['reason']}" if r["reason"] else "")
            + f"；{res['calls']} 次模型调用，${res['cost']:.4f}，{res['seconds']}s")
    lines = [head, "各步秒：" + "，".join(f"{k} {v}" for k, v in r["result"]["步骤秒"].items()),
             f"边界复核：{r['result']['边界复核']}"]
    if res.get("changed_files"):
        lines.append("改动：" + "、".join(res["changed_files"]))
    lines.append(f"测试命令：{res['test_cmd']}")
    lines.append(f"记录：{res['dir']}")
    return "\n".join(lines)


# ------------------------------------------------------------------ 旧名兼容：搬走的名字仍可从 v2 取到

_MOVED = {
    "tools.dslagent.packs.code": ("OLD_RX_LINE",),
    "tools.dslagent.verify.code": (
        "FIX_SYS", "BOUND_SYS", "BFIX_SYS", "TEST_TIMEOUT", "BOUND_TIMEOUT", "FN_CAP", "FIX_CAP", "apply_edits", "full_test",
        "enclosing", "func_span", "scope_dirs", "residuals", "checklist_gaps", "_trace_refs", "_fix_fallback", "_fix_user",
        "_check_reply", "dispatch_fix", "test_python", "strip_code", "run_boundary", "_docs", "_changed_funcs", "_test_verb"),
}


def __getattr__(name):
    import importlib
    for mod, names in _MOVED.items():
        if name in names:
            return getattr(importlib.import_module(mod), name)
    if name == "RULES":
        return plan_rules(packs.current())
    if name == "K":
        return importlib.import_module("tools.dslagent.packs.code")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
