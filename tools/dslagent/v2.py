"""规划路径 v2 的核心（DSLAGENT_PLANNER=v2 时 runner.run 转到这里；缺省仍走 runner 的模板 / 规划路径）。
与任务类型无关；任务类型相关的两半按环境变量插拔（目前都只有 code）：
  资料包 packs/（DSLAGENT_PACK，缺省 code）：收集资料、补查、补查提示、规划提示里这类任务专属的说明（接口见 packs/__init__.py）
  验收   verify/（DSLAGENT_VERIFY，缺省跟随 PACK）：验收、补改、边界复核（接口见 verify/__init__.py）
旧路径兼容：tools.dslagent.v2pack 转发到 packs.code；搬走的名字（v2.PRE_SYS、v2._fix_user、v2.full_test …）仍可从 v2 取到。

规划方式 DSLAGENT_PLAN_MODE（缺省 read；cbatch 透传 dsl_options.plan_mode）：
  full  下面 1–3 的老流程：资料包 + 补查结果全塞进规划的 user（提示与改动前逐字一致）。
  read  规划输入只有 任务原文 + 文件大纲（pack.plan_outline；包没实现就只有任务原文），system = 原 system 去掉讲资料包各节的那句 + 一小段
        「用 dsl 工具读」；没有 1（collect）、没有 2（补查）；规划调用挂 dslmcp --readonly（读片段 / 搜索代码 / 查引用 / 设 / 打印），
        workdir = 待改项目，--max-turns 12，保险同下（空闲超时、文本 invoke 拦截、超长输出、重试一次）；计划检查不过的那次重写也走 read。
        每次规划的工具调用（工具名、参数、返回字数）写进运行目录 plan_tools.json。

流程（流程本身与任务类型无关，细节由包 / 验收实现）：
  1 资料包：pack.collect 确定性收集（不调模型）。
  2 补查：一次短调用（pack.QUERY_SYS）列出要补查的项（≤8），pack.extra 执行后并入资料包；回「够了」就跳过。
  3 规划：一次调用（plan_system()）输出 .zs（#改法、#清单、预算、派任务 / 并行派任务 / 终止）；strip_prose → autoclose →
    白名单 + 包专属检查（pack.plan_problems）→ 假模型空跑；有错带着错误重写 1 次，仍错判失败（不执行）。
  4 执行：仓库 DSL 引擎（V2Engine = AgentEngine + 测试闸门）跑计划。计划里的 跑测试 只在结果会改变走向时真跑
    （test_gate：结果变量被 打印 / 终止 以外的语句用到，或所在 如果 的分支不全是 打印 / 终止），否则给「通过」
    的占位结果，验收时统一跑。终止 成功 才往下验收，否则回滚到开局、判失败。
  5 验收：verify.check（通过 / 缺口 / 补改入参）；有缺口 verify.fix 派 1 次补改，补改后再 check 一次。
  6 边界复核：verify.boundary（可选）；仍失败 → 状态 超出预期（不报成功）。
  7 回复：reply = {结果, 状态, 原因}；v2 记各步耗时、调用次数、费用（calls.json 逐次）。
子任务回复格式：缺省 json；DSLAGENT_SUBTASK=tool 时子任务挂 dslmcp 的 dsl 工具读 / 搜 / 改文件（toolsub.py），每个子任务的结果记在 v2.子任务。
按步骤指定模型：环境变量 DSLAGENT_MODELS（JSON，cbatch 透传 dsl_options.models）{plan, sub, fix, bound} → 模型串，见 engines.py（claude / codex / grok / opencode）；
没写的步骤 sonnet；每次调用按 tag 选引擎（Model.spec），calls.json 逐条记 engine / model / effort，result.json 的 v2.models 记生效的四步。
模型调用：claude CLI，--system-prompt 替换默认提示，--tools "" --strict-mcp-config --setting-sources "" --disable-slash-commands
（同 plan35 proto），单轮流式；run(model=…) 可换成假模型（测试用）。
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import dslcheck as DC
from . import engines, packs, verify
from .snap import DIFF_CAP, changed, code_hash, diff_text, restore, snapshot  # noqa: F401  旧名仍从 v2 取

PKG = Path(__file__).resolve().parent
LIB = PKG / "lib"
VERBS = PKG / "verbs"
MODEL = "sonnet"
MAX_CALLS = 20           # 补查 1 + 规划 1（+重写 1）+ 计划内 ≤12 + 补改 1 + 边界 1 + 边界补改 1，留余量
WALL = 900
IDLE_SEC = 60            # 首 token 之后这么久没有新流事件就杀掉该次调用
MAX_OUT = 20000          # 单次调用累计输出超过这么多字符就杀掉（reason=输出超长）
TOOL_MARKS = ("<invoke", "<function_calls")   # 流里出现这些 = 模型在写工具调用格式（reason=输出工具调用格式）
GUARD_REASONS = ("首字前静默超时", "空闲超时", "输出工具调用格式", "输出超长", "尝试调用工具")
SKIP_NOTE = "未跑（这次测试的结果不改变计划走向，验收时统一跑一次全量测试）"


class Stop(Exception):
    pass


def enabled():
    return (os.environ.get("DSLAGENT_PLANNER") or "").strip().lower() == "v2"


# ------------------------------------------------------------------ 提示词

SUB_SYS = ("你是子任务执行者，被一个自动化流程调用。只根据用户消息里给你的数据完成任务，不能读别的文件，也不能运行任何东西。"
           "按用户消息末尾的输出格式只输出一个 JSON 对象（不要代码围栏、不要别的文字）。"
           "修改内容 edits 每项字段名固定为 file（相对项目根路径）、old（从给你的原文一字不差抄，含缩进，不带「  12| 」行号前缀，"
           "在文件里只出现一次）、new（替换后的文本）。不要改测试文件（tests/ 下、test_*.py）。")

RULES_HEAD = r"""【规划规则（这次要写的脚本）】
- 第一行 用包 common text code；第二行写 预算 调用 N 秒 M（N ≤ 12，含 问JSON / 派任务 / 并行派任务 里的每次调用和重问；M ≤ 600）。"""

RULES_STOP = r"""- 全部改完 终止 成功 一句话；做不到 终止 失败 原因；前提不符或范围远超描述 终止 超出预期 原因。不要打印「结论：」行。"""

RULES_OUT = r"""- 只输出 .zs 脚本本身（含 #改法 / #清单 段），不要代码围栏，不要任何解释文字。"""

PLAN_MODE_ENV = "DSLAGENT_PLAN_MODE"
PLAN_MODES = ("read", "full")
READ_MAX_TURNS = 12
READ_TAIL = "需要看代码时用 dsl 工具读：读片段（按大纲里的 文件:起-止）、搜索代码、查引用。只读，不改文件。读够了直接输出完整 .zs。"
# read 方式下 system 里与「按需读」矛盾的说法：(原文, 换成)。原文必须在 full 的 system 里出现（read_system 里断言）。
READ_SUBS = (
    ("你看不到别的文件，也不能运行任何东西。", "代码不在消息里，" + READ_TAIL + "你不能运行任何东西。"),
    ("- 改法：数据包 / 补查结果里能看到原文的改动，", "- 改法：读到原文的改动，"),
    ("- 子任务：数据包里没有原文、或要看运行结果才能决定怎么改的，", "- 子任务：没读到原文、或要看运行结果才能决定怎么改的，"),
    ("脚本必须覆盖数据包和补查结果里查到的**每一个**位置", "先用 搜索代码 / 查引用 把所有位置找全，脚本必须覆盖找到的**每一个**位置"),
    ("不用 定位.zs / 读改测.zs（数据包已给原文）。", "不用 定位.zs / 读改测.zs。"),
    ("你看不到代码，只能靠脚本里的动词去读；读到的内容要嵌进 问JSON 的提示词里，模型才看得到",
     "脚本里 问JSON / 派任务 调的模型看不到代码：要它看的内容用脚本里的动词读出来（派任务 可用入参「文件:起-止」），嵌进提示词里它才看得到"),
)

_PLAN_SYS = {}


def plan_mode(value=None):
    """规划方式：环境变量 DSLAGENT_PLAN_MODE（缺省 read）；不认识的取值报 ValueError。"""
    v = (os.environ.get(PLAN_MODE_ENV) if value is None else value) or ""
    v = v.strip().lower() or PLAN_MODES[0]
    if v not in PLAN_MODES:
        raise ValueError(f"{PLAN_MODE_ENV} 取值不对：{v!r}，可用：{'、'.join(PLAN_MODES)}")
    return v


def plan_rules(pack):
    """规划规则：通用的几行 + 资料包专属的几段（见 packs/__init__.py 的 PLAN_RULES / PLAN_RULES_END）。"""
    return "\n".join([RULES_HEAD, pack.PLAN_RULES, RULES_STOP, pack.PLAN_RULES_END, RULES_OUT])


def plan_system(pack=None, mode="full"):
    """规划的 system。mode=full：原文；mode=read：去掉开头讲资料包各节的那句（换成一句话说明 user 里是什么），再按 READ_SUBS 换掉与按需读矛盾的说法（READ_TAIL 放在开头说明里）。"""
    pack = pack or packs.current()
    if mode == "read":
        return read_system(pack)
    if pack.NAME not in _PLAN_SYS:
        from . import prompts as DPR
        keep = ("赋值右边不要以", "一条语句只能写在一行", "修改内容的字段名固定为", "你看不到代码")
        tips = "【写法要点（节选）】\n" + "\n".join(
            "- " + b.strip() for b in DPR.TIPS.split("\n- ") if b.strip().startswith(keep))
        _PLAN_SYS[pack.NAME] = (
            f"你是「分支式规划者」。用户消息会给你一个{pack.TASK_DESC}、一份{pack.PACK_DESC}，后面可能有「补查结果」，同等对待。"
            "你看不到别的文件，也不能运行任何东西。"
            "你要写一段中文 DSL 脚本（.zs），交给 DSL 引擎直接执行（不再改写）；脚本里的 派任务 / 问JSON 会调另一个模型，"
            "它只看得到你写进提示词、入参里的数据。\n\n"
            f"{DPR.CHEAT}\n\n{DPR.VERBS}\n\n{tips}\n\n{plan_rules(pack)}\n\n"
            "【示例（分支式规划的写法示例，只示意写法，不是答案）】\n"
            + (LIB / "示例_分支规划.zs").read_text(encoding="utf-8"))
    return _PLAN_SYS[pack.NAME]


def read_intro_cut(pack):
    """read 方式下 system 里去掉的那一句（讲资料包各节 / 补查结果）→ 换成的那句。"""
    old = f"用户消息会给你一个{pack.TASK_DESC}、一份{pack.PACK_DESC}，后面可能有「补查结果」，同等对待。"
    return old, f"用户消息会给你一个{pack.TASK_DESC}，后面附候选文件的大纲。"


def read_system(pack):
    full = plan_system(pack, "full")
    old, new = read_intro_cut(pack)
    assert old in full, "规划 system 开头句变了，read 方式要同步改 read_intro_cut"
    s = full.replace(old, new, 1)
    for a, b in READ_SUBS:
        assert a in s, f"规划 system 里找不到「{a[:20]}…」，read 方式要同步改 READ_SUBS"
        s = s.replace(a, b, 1)
    return s


def plan_user(task, pack):
    return f"【任务原文】\n{task}\n\n【数据包】\n{pack}"


def plan_user_read(task, outline=""):
    """read 方式的 user：任务原文 + 文件大纲（包没有大纲就只有任务原文）。"""
    return f"【任务原文】\n{task}" + (f"\n\n{outline}" if outline else "")


def parse_json(text):
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < i:
        raise ValueError("回复里没有 JSON 对象")
    return json.loads(s[i:j + 1])


# ------------------------------------------------------------------ 模型调用


def call_claude(system, user, timeout=300, model=None, reply_path=None, idle=None, mcp_config=None, max_turns=1, allow_tool=None):
    """claude -p（model 缺省 MODEL），自定系统提示，无工具 / MCP / 技能，单轮，流式（记首 token）。返回 text / sec / ttft / cost / usage / rc / stderr / reason。
    首 token 之后 idle 秒没有任何新流事件 → killpg（reason=空闲超时）；首 token 前只受总超时管。
    流式累计文本出现 <invoke / <function_calls → killpg（reason=输出工具调用格式）；累计超过 MAX_OUT 字符 → killpg（reason=输出超长）。
    reply_path：边收流边把文本增量追加进该文件，被杀时已收到的内容也在；返回的 partial 是已收到的流文本。
    mcp_config（DSLAGENT_SUBTASK=tool）：多挂一个 MCP（--mcp-config + --strict-mcp-config，内置工具仍 --tools ""，只许 allow_tool 那一个），
    --max-turns 用 max_turns；text 是最后一轮的最终回复（中途轮次里的文字、真实工具调用不算），「输出工具调用格式」只查当前这一轮的文字，
    返回里多 num_turns / tool_calls / subtype。"""
    from tools.cbatch import CLAUDE_BIN
    from .pool import child_env
    from .runner import tmp_dir
    tmp = tmp_dir()
    cwd = tmp / "v2_empty"
    cwd.mkdir(parents=True, exist_ok=True)
    cmd = [os.environ.get("CBATCH_CLAUDE") or CLAUDE_BIN, "-p", "--model", model or MODEL, "--output-format", "stream-json",
           "--verbose", "--include-partial-messages", "--max-turns", str(max_turns), "--tools", "", "--setting-sources", "",
           "--strict-mcp-config", "--disable-slash-commands", "--system-prompt", system]
    if mcp_config:
        cmd += ["--mcp-config", str(mcp_config), "--allowedTools", allow_tool or "mcp__dsl__dsl"]
    idle = idle or IDLE_SEC
    t0 = time.time()
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         cwd=cwd, env=child_env(tmp), start_new_session=True)
    err_buf, killed = [], []
    last = [time.time()]
    fh = None
    if reply_path:
        try:
            fh = open(reply_path, "w", encoding="utf-8")
        except OSError:
            fh = None

    def feed():
        try:
            p.stdin.write(user)
            p.stdin.close()
        except OSError:
            pass

    def drain():
        err_buf.append(p.stderr.read())

    def kill(why="总超时"):
        killed.append(why)
        try:
            os.killpg(p.pid, 9)
        except OSError:
            pass
    th = [threading.Thread(target=feed, daemon=True), threading.Thread(target=drain, daemon=True)]
    for t in th:
        t.start()
    timer = threading.Timer(timeout, kill)
    timer.start()
    text, result, ttft, streamed = "", None, None, ""
    turn_text, total_chars = "", 0          # mcp 模式：当前这一轮的流文本 / 全部轮的累计字数
    msgs, tool_calls, tool_ids = {}, 0, set()                # mcp 模式：消息 id → {text, tool}（按出现顺序），真实工具调用块数
    done = threading.Event()

    def watch():
        while not done.wait(min(1.0, max(0.05, idle / 4))):
            if ttft is not None and time.time() - last[0] > idle:
                kill("空闲超时")
                return
    wd = threading.Thread(target=watch, daemon=True)
    wd.start()
    try:
        for line in p.stdout:
            last[0] = time.time()
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            ty = ev.get("type")
            if ty == "stream_event":
                se = ev.get("event") or {}
                if se.get("type") == "message_start":
                    turn_text = ""
                if se.get("type") == "content_block_delta":
                    if ttft is None:
                        ttft = round(time.time() - t0, 2)
                    d = se.get("delta") or {}
                    if d.get("type") == "text_delta" and d.get("text"):
                        streamed += d["text"]
                        turn_text += d["text"]
                        total_chars += len(d["text"])
                        if not killed:
                            if any(m in (turn_text if mcp_config else streamed) for m in TOOL_MARKS):
                                kill("输出工具调用格式")
                            elif (total_chars if mcp_config else len(streamed)) > MAX_OUT:
                                kill("输出超长")
                        if fh:
                            try:
                                fh.write(d["text"])
                                fh.flush()
                            except OSError:
                                pass
            elif ty == "assistant":
                if mcp_config:
                    m = msgs.setdefault(ev["message"].get("id") or f"m{len(msgs)}", {"text": "", "tool": False})
                    for b in ev["message"].get("content", []):
                        if b.get("type") == "text":
                            m["text"] += b["text"]
                        elif b.get("type") == "tool_use":
                            m["tool"] = True
                            tool_ids.add(b.get("id") or len(tool_ids))
                            tool_calls = len(tool_ids)
                    continue
                for b in ev["message"].get("content", []):
                    if b.get("type") == "text":
                        text += b["text"]
            elif ty == "result":
                result = ev
        p.wait()
    finally:
        timer.cancel()
        done.set()
        for t in th:
            t.join(timeout=5)
        if fh:
            fh.close()
    reason = killed[0] if killed else None
    if mcp_config:
        last_msg = list(msgs.values())[-1] if msgs else None
        text = (last_msg["text"] if last_msg and not last_msg["tool"] else "") if result is None or result.get("is_error") \
            else (result.get("result") or "")
    err = "".join(x or "" for x in err_buf) + (f"\n[{reason}被杀]" if killed else "")
    res = result or {}
    u = res.get("usage", {}) or {}
    usage = {"input": u.get("input_tokens"), "output": u.get("output_tokens"),
             "cache_read": u.get("cache_read_input_tokens"), "cache_creation": u.get("cache_creation_input_tokens")}
    return {"text": text, "sec": round(time.time() - t0, 1), "rc": p.returncode, "ttft": ttft,
            "cost": res.get("total_cost_usd") or 0.0, "usage": usage, "stderr": err[-500:], "reason": reason,
            "partial": streamed, "num_turns": res.get("num_turns"), "tool_calls": tool_calls,
            "subtype": res.get("subtype")}


class Model:
    """全部模型调用的入口：计数、墙钟、费用、逐次记录（calls/NN_tag.*.txt、self.log）。
    backend(system, user, tag, timeout) → dict（text, cost, …）或 str；只有指定了非 MODEL 的模型（规划那次）才多传 model=。"""

    def __init__(self, out, backend=None, max_calls=MAX_CALLS, deadline=None, routes=None):
        self.out = Path(out)
        self.real = backend is None
        self.routes = routes or {}          # 步骤 → 模型串（engines.STEPS；没写的步骤走 claude MODEL）
        self.backend = backend or (lambda s, u, tag, timeout, model=None, **kw: call_claude(s, u, timeout, model, **kw))
        self.max_calls, self.deadline = max_calls, deadline
        self.n, self.cost, self.log = 0, 0.0, []
        self.lock = threading.Lock()
        (self.out / "calls").mkdir(parents=True, exist_ok=True)

    def spec(self, tag, model=None):
        """这次调用用的 {engine, model, effort, spec}：DSLAGENT_MODELS 里写了该步骤就用它，否则 model 参数（旧的规划模型透传），再否则 sonnet。"""
        step = engines.step_of(tag)
        s = self.routes.get(step) if step else None
        if s:
            return engines.parse(s)
        m = model or MODEL           # 旧的透传（DSLAGENT_PLAN_MODEL）：任意串当 claude 模型名，不校验
        return {"engine": "claude", "model": m, "effort": None, "spec": m}

    def __call__(self, system, user, tag, model=None):
        """一次调用；因空闲超时 / rc≠0 / 空回复失败时同输入重试 1 次（计入调用数和费用，记录 retry=1 和首次失败原因）。"""
        try:
            return self._once(system, user, tag, model)
        except RuntimeError as e:
            reason = getattr(e, "reason", None) or str(e)
            return self._once(system, user, tag, model, retry=reason)

    def _once(self, system, user, tag, model=None, retry=None):
        with self.lock:
            if self.n >= self.max_calls:
                raise Stop(f"总模型调用已满 {self.max_calls} 次（{tag}）")
            if self.deadline and time.time() > self.deadline:
                raise Stop(f"墙钟用完（{tag} 前）")
            self.n += 1
            n = self.n
        left = (self.deadline - time.time()) if self.deadline else 300
        t0 = time.time()
        sp = self.spec(tag, model)
        kw = {"model": sp["spec"]} if sp["spec"] != MODEL else {}
        rp = self.out / "calls" / f"{n:02d}_{tag}.reply.txt"
        if self.real:
            kw["reply_path"] = rp
        tmo = max(30, min(300, left + 5))
        if self.real and sp["engine"] != "claude":
            r = engines.call(sp, system, user, tmo, reply_path=rp)
        else:
            r = self.backend(system, user, tag, tmo, **kw)
        if isinstance(r, str):
            r = {"text": r}
        rec = {"n": n, "tag": tag, "sec": r.get("sec", round(time.time() - t0, 2)), "ttft": r.get("ttft"),
               "cost": r.get("cost") or 0.0, "usage": r.get("usage"), "rc": r.get("rc"),
               "engine": sp["engine"], "model": sp["model"] or ("默认" if sp["engine"] == "grok" else MODEL), "effort": sp["effort"],
               "sys_chars": len(system), "user_chars": len(user), "t_start": round(t0, 3)}
        if retry:
            rec["retry"] = 1
            rec["first_fail"] = retry
        with self.lock:
            self.cost += rec["cost"]
            self.log.append(rec)
        try:
            (self.out / "calls" / f"{n:02d}_{tag}.prompt.txt").write_text(f"[system]\n{system}\n\n[user]\n{user}",
                                                                          encoding="utf-8")
            rp.write_text(
                (r.get("text") or r.get("partial") or "") + ("\n\n[stderr]\n" + r["stderr"] if r.get("stderr") else ""), encoding="utf-8")
        except OSError:
            pass
        bad = r.get("reason") in GUARD_REASONS or (r.get("rc") not in (None, 0)) or not (r.get("text") or "").strip()
        if bad:
            why = r.get("reason") or (f"rc={r.get('rc')}" if r.get("rc") not in (None, 0) else "空回复")
            rec["failed"] = why
            e = RuntimeError(f"模型没有回应（{why}，rc={r.get('rc')}）：{(r.get('stderr') or '')[-200:]}")
            e.reason = why
            if retry:
                e.args = (f"{e.args[0]}；首次失败：{retry}",)
            raise e
        return r["text"]


def _tool_call(self, system, user, tag, mcp_config, max_turns=6, model=None):
    """DSLAGENT_SUBTASK=tool：一次带 MCP 的多轮调用（计 1 次调用数，费用、逐次记录同 _once）。不重试、不抛模型失败——
    失败原因（保险触发 / rc≠0 / 空回复）放在返回的 failed 里，由 toolsub 决定重试还是兜底。返回 backend 的 dict。"""
    with self.lock:
        if self.n >= self.max_calls:
            raise Stop(f"总模型调用已满 {self.max_calls} 次（{tag}）")
        if self.deadline and time.time() > self.deadline:
            raise Stop(f"墙钟用完（{tag} 前）")
        self.n += 1
        n = self.n
    left = (self.deadline - time.time()) if self.deadline else 300
    t0 = time.time()
    rp = self.out / "calls" / f"{n:02d}_{tag}.reply.txt"
    sp = self.spec(tag, model)
    kw = {"reply_path": rp} if self.real else {}
    if sp["spec"] != MODEL:
        kw["model"] = sp["spec"]
    tmo = max(30, min(300, left + 5))
    if self.real and sp["engine"] != "claude":
        r = engines.call(sp, system, user, tmo, reply_path=rp, mcp_config=str(mcp_config))
    else:
        r = self.backend(system, user, tag, tmo, mcp_config=str(mcp_config), max_turns=max_turns, **kw)
    if isinstance(r, str):
        r = {"text": r}
    rec = {"n": n, "tag": tag, "sec": r.get("sec", round(time.time() - t0, 2)), "ttft": r.get("ttft"),
           "cost": r.get("cost") or 0.0, "usage": r.get("usage"), "rc": r.get("rc"), "tool": 1,
           "num_turns": r.get("num_turns"), "tool_calls": r.get("tool_calls"), "subtype": r.get("subtype"),
           "engine": sp["engine"], "model": sp["model"] or MODEL, "effort": sp["effort"], "sys_chars": len(system), "user_chars": len(user), "t_start": round(t0, 3)}
    with self.lock:
        self.cost += rec["cost"]
        self.log.append(rec)
    try:
        (self.out / "calls" / f"{n:02d}_{tag}.prompt.txt").write_text(f"[system]\n{system}\n\n[user]\n{user}", encoding="utf-8")
        rp.write_text((r.get("text") or r.get("partial") or "") + ("\n\n[stderr]\n" + r["stderr"] if r.get("stderr") else ""),
                      encoding="utf-8")
    except OSError:
        pass
    if r.get("reason") in GUARD_REASONS:
        rec["failed"] = r["failed"] = r["reason"]
    elif r.get("subtype") == "error_max_turns":
        rec["failed"] = r["failed"] = "轮数用尽"
    elif r.get("rc") not in (None, 0):
        rec["failed"] = r["failed"] = f"rc={r.get('rc')}"
    elif not (r.get("text") or "").strip():
        rec["failed"] = r["failed"] = "空回复"
    r["call_n"] = n
    return r


Model.tool_call = _tool_call


def plan_read_call(M, system, user, tag, project, model, out, tools):
    """plan_mode=read 的一次规划调用：挂只读 dslmcp（--readonly，workdir=待改项目）、--max-turns READ_MAX_TURNS，
    保险同 call_claude（空闲超时 / 输出超长 / 输出工具调用格式）；失败（保险触发、rc≠0、空回复、轮数用尽）同输入重试 1 次，仍失败抛 RuntimeError。
    每次尝试的工具调用（工具名、参数、返回字数）追加进 tools，并整份写到 out/plan_tools.json。返回最终回复文本。"""
    d = out / "toollogs"
    d.mkdir(parents=True, exist_ok=True)
    first = None
    for attempt in (1, 2):
        base = f"{tag}_a{attempt}"
        log, cfg = d / f"{base}.jsonl", d / f"{base}.mcp.json"
        cfg.write_text(json.dumps({"mcpServers": {"dsl": {"command": sys.executable, "args": [
            str(PKG / "dslmcp.py"), "--workdir", str(project), "--log", str(log), "--verbs-root", str(VERBS), "--readonly",
            "--state", str(d / f"{base}_state")]}}}, ensure_ascii=False), encoding="utf-8")
        r = M.tool_call(system, user, tag, cfg, READ_MAX_TURNS, model=model)
        rows = []
        try:
            for line in log.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
        except OSError:
            pass
        tools.extend({"调用": tag, "尝试": attempt, "序": i, "工具": "dsl", "参数": x.get("code"), "返回字数": x.get("out_chars"),
                      "状态": x.get("status")} for i, x in enumerate(rows, 1))
        try:
            (out / "plan_tools.json").write_text(json.dumps(tools, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
        text = (r.get("text") or "").strip()
        why = r.get("failed")
        if not why and any(m in text for m in TOOL_MARKS):
            why = "输出工具调用格式"
            for c in M.log:
                if c["n"] == r.get("call_n"):
                    c["failed"] = why
        if not why:
            return r["text"]
        if attempt == 2:
            raise RuntimeError(f"模型没有回应（{why}，rc={r.get('rc')}）：{(r.get('stderr') or '')[-200:]}；首次失败：{first}")
        first = why


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


def test_gate(script):
    """主脚本里每个 跑测试 语句的行号（0 起，同引擎的 _at）→ 要不要真跑。
    真跑 ⇔ 结果变量被 打印 / 终止 以外的语句用到；如果 / 否则如果 的条件用到它时，整条 如果 链的各分支都只有 打印 / 终止、
    且（有 否则，或分支里没有 终止，或链后面到块尾也只有 打印 / 终止）才算不影响走向。不赋值的 跑测试 不真跑。"""
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
        if h == "跑测试":
            gate[i] = False
        elif h == "set":
            name, _, val = rest.partition("=")
            if split_head(val.strip())[0] == "跑测试":
                gate[i] = needed(name.strip(), i)
    return gate


def _engine_cls():
    from .engine import AgentEngine

    class V2Engine(AgentEngine):
        """AgentEngine + 测试闸门：主脚本里 test_gate 判为不影响走向的 跑测试 不真跑，给通过的占位结果；
        真跑的记下当时的代码哈希和结果（验收时代码没变就复用）。空跑时 跑测试 一律给占位结果。"""
        gate = None
        project = None
        tests = None

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
            if name != "跑测试":
                return super()._do_verb(name, rest, lineno, assign_to)
            if self.dry_run:
                return self._deliver({"passed": "是", "summary": "（空跑）" + SKIP_NOTE}, assign_to)
            log = self.tests if self.tests is not None else []
            if self._depth == 0 and self.gate is not None and not self.gate.get(self._at, True):
                log.append({"line": self._at + 1, "mode": "skipped"})
                return self._deliver({"passed": "是", "summary": SKIP_NOTE}, assign_to)
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
    m = {n: LIB / n for n in DP.LIBS}
    m.update({f"_plan/{k}": Path(plan_dir) / k for k in subs})
    return m


def check(project, work, script, task, pack=None):
    """plan.py 的检查 + 有 预算 + 资料包专属检查（pack.plan_problems，code：#清单、旧写法 正则）+ 空跑。
    返回 (问题文本或空, 主脚本, 子脚本, 记录)。"""
    from tools.dsl_sections import split_sections

    from . import plan as DP
    pack = pack or packs.current()
    rec = {}
    main, subs = DP.split_subs(script)
    probs = DP.whitelist_check(main, subs)
    body, _, cl, _ = split_sections(main)
    generic = []
    if not re.search(r"^\s*预算\s", body, re.M):
        generic.append("开头缺 预算 语句（第二行写 预算 调用 N 秒 M）")
    probs += pack.plan_problems(main, body, cl, generic)
    if probs:
        rec["阶段"] = "静态"
        return "白名单 / 格式检查没过：\n" + "\n".join(probs[:12]), main, subs, rec
    t0 = time.time()
    err, n, out = DP.dry_run(project, work, main, subs, task, scripts_for, MODEL, engine_cls=_engine_cls())
    rec.update(阶段="空跑", 空跑秒=round(time.time() - t0, 1), 空跑假调用=n)
    return (f"用假模型空跑报错：{err}" if err else ""), main, subs, rec


# ------------------------------------------------------------------ 主流程


def run(project, task, out_dir, test_cmd=None, wall=WALL, model=None, max_calls=MAX_CALLS, boundary=True):
    """跑一次 v2。project 里直接改文件；记录写进 out_dir（calls/、calls.json、plan*.zs、pack*.md、boundary/、result.json）。
    model：假模型 backend(system, user, tag, timeout) → str|dict（测试用），缺省走 claude CLI。
    返回结果字典（runner.run 同款字段 + reply / v2）。"""
    from . import plan as DP
    from . import prompts as DPR

    project = Path(project).resolve()
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    mode, plan_tools, routes = PLAN_MODES[0], [], {}
    try:
        pack, ver = packs.current(), verify.current()
        mode = plan_mode()
        routes = engines.validate(engines.from_env(), mode, DC.env_mode())
    except ValueError as e:
        pack = ver = None
        pick_err = str(e)
    else:
        test_cmd = ver.detect_cmd(project, test_cmd)
    M = Model(out, backend=model, max_calls=max_calls, deadline=t_start + wall, routes=routes)
    steps, info = {}, {"补查": None, "够了": None, "补查项": 0, "数据包字符": 0, "检查": [], "重写": False,
                       "子任务模式": DC.env_mode(), "子任务": []}
    res = {"project": str(project), "test_cmd": test_cmd, "kind": "task", "planner": "v2", "fixed": False,
           "engine_used": "v2", "versions": 0, "calls": 0, "cost": 0.0, "seconds": 0, "stop": "", "dir": str(out),
           "calls_log": str(out / "calls.json"), "version_log": [], "subcalls": [], "changed_files": [], "handoff": "",
           "report": "", "v2": info}
    state = {"状态": "失败", "原因": ""}
    accept, bound = {}, {"跑了": False}

    def step(name, t0):
        steps[name] = round(time.time() - t0, 1)

    if pack is None:
        state["原因"] = pick_err
        return _finish(res, out, M, steps, state, accept, bound, {}, {}, t_start)
    if not test_cmd:
        state["原因"] = ver.MISSING_MSG
        return _finish(res, out, M, steps, state, accept, bound, {}, {}, t_start)
    info["规划方式"] = mode
    info["models"] = engines.effective({**routes, **({} if "plan" in routes or not os.environ.get("DSLAGENT_PLAN_MODEL")
                                                     else {"plan": os.environ["DSLAGENT_PLAN_MODEL"]})})
    ver.setup(out, test_cmd)
    base = snapshot(project, pack)
    cur = base
    main, subs, script = "", {}, ""
    try:
        if mode == "full":
            # ---- 1 数据包
            t0 = time.time()
            coll = pack.collect(task, project)
            info.update(coll["记录"])
            step("1数据包", t0)
            # ---- 2 补查
            t0 = time.time()
            txt = M(pack.QUERY_SYS, plan_user(task, coll["text"]), "preq")
            try:
                q = parse_json(txt)
            except ValueError as e:
                q = {"够了": True, "_err": str(e)}
            info["补查"] = q
            info["够了"] = bool(q.get("够了")) if isinstance(q, dict) else True
            extra = ""
            if not info["够了"]:
                ex = pack.extra(project, q, coll)
                extra, info["补查记录"] = ex["text"], ex["log"]
                info["补查项"] = len(info["补查记录"])
                info.update(ex.get("记录") or {})
            full_pack = coll["text"] + ("\n\n" + extra if extra else "")
            info["数据包字符"] = len(full_pack)
            (out / "pack.md").write_text(full_pack, encoding="utf-8")
            step("2补查", t0)
            first_user = plan_user(task, full_pack)
        else:
            # ---- 1 大纲（read 方式：没有资料包全文、没有补查）
            t0 = time.time()
            outline = ""
            if hasattr(pack, "plan_outline"):
                o = pack.plan_outline(task, project)
                outline = o["text"]
                info.update(o.get("记录") or {})
            info["大纲字符"] = len(outline)
            (out / "outline.md").write_text(outline, encoding="utf-8")
            first_user = plan_user_read(task, outline)
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
        for k in range(2):
            user = first_user if k == 0 else DPR.fix_prompt(script, problem)
            if mode == "read":
                raw = plan_read_call(M, plan_system(pack, "read"), user, "plan" if k == 0 else "plan_fix", project, plan_model, out,
                                     plan_tools)
            else:
                raw = M(plan_system(pack), user, "plan" if k == 0 else "plan_fix", model=plan_model)
            (out / f"plan_v{k + 1}.raw.txt").write_text(raw, encoding="utf-8")
            script, _ = DP.strip_prose(raw)
            script, n_close, _ = DP.autoclose(script)
            (out / f"plan_v{k + 1}.zs").write_text(script, encoding="utf-8")
            problem, main, subs, crec = check(project, out / "dry", script, task, pack)
            info["检查"].append(dict(crec, 补结束=n_close, 问题=problem[:1500]))
            if not problem:
                break
            info["重写"] = True
        step("3规划", t0)
        if mode == "read":
            info["规划工具"] = {"次数": len(plan_tools), "返回字数": sum(x.get("返回字数") or 0 for x in plan_tools)}
        if problem:
            raise Stop("计划 .zs 重写 1 次仍没过检查：" + problem[:400])
        (out / "plan.zs").write_text(script, encoding="utf-8")
        # ---- 4 执行
        t0 = time.time()
        gate = test_gate(main)
        info["测试闸门"] = {str(k + 1): v for k, v in gate.items()}
        plan_dir = out / "plan_subs"
        DP.write_subs(plan_dir, subs)
        Eng = _engine_cls()
        eng = Eng(client=Client(M), workdir=project, verbose=False, verbs_root=VERBS,
                  scripts=scripts_for(plan_dir, subs), on_call=res["subcalls"].append)
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
        if halted.get("状态") != "成功":
            state["状态"] = "超出预期" if halted.get("状态") == "超出预期" else "失败"
            raise Stop(f"脚本终止 {halted.get('状态')}：{str(halted.get('原因'))[:300]}")
        # ---- 5 验收
        t0 = time.time()
        cur = snapshot(project, pack)
        pr = {"task": task, "base": base, "cur": cur, "main": main, "tests": eng.tests, "accept": accept,
              "test_cmd": test_cmd, "stage": "验收", "out": out, "bound": bound}
        chk = ver.check(project, pr, eng.checklist)
        if not chk["通过"]:
            accept["补改"] = ver.fix(M, project, chk, "fix")
            pr.update(cur=snapshot(project, pack), stage="补改后")
            chk = ver.check(project, pr, eng.checklist)
        accept["通过"] = chk["通过"]
        accept["测试摘要"] = chk["测试摘要"]
        step("5验收", t0)
        if not accept["通过"]:
            state.update(状态="失败", 原因=chk["原因"])
            raise _Done()
        # ---- 6 边界复核
        if boundary and hasattr(ver, "boundary"):
            t0 = time.time()
            state.update(ver.boundary(M, project, pr))
            step("6边界复核", t0)
        else:
            state.update(状态="成功", 原因="")
    except _Done:
        pass
    except Stop as e:
        state["原因"] = str(e)
        if state["状态"] == "成功":
            state["状态"] = "失败"
    except Exception as e:  # noqa: BLE001  流程自身出错不能让 cbatch 拿不到结果
        state.update(状态="失败", 原因=f"v2 流程出错：{type(e).__name__}: {str(e)[:400]}")
    if state["状态"] != "成功" and not accept:
        # 计划没跑成（检查没过 / 报错 / 没自报成功）：回滚到开局，项目保持原样
        now = snapshot(project, pack)
        restore(project, base, changed(base, now))
        info["回滚"] = changed(base, now)
    return _finish(res, out, M, steps, state, accept, bound, base, snapshot(project, pack), t_start)


class _Done(Exception):
    pass


def _finish(res, out, M, steps, state, accept, bound, base, now, t_start):
    ch = changed(base, now) if base else []
    res.update(fixed=state["状态"] == "成功", stop="" if state["状态"] == "成功" else state["原因"],
               calls=M.n, cost=round(M.cost, 4), seconds=round(time.time() - t_start, 1), changed_files=ch,
               diff=diff_text(base, now, 3000) if base else "", status=state["状态"])
    res["calls_by_purpose"] = {}
    for c in M.log:
        k = re.sub(r"\d+$|_reask$", "", c["tag"])
        res["calls_by_purpose"][k] = res["calls_by_purpose"].get(k, 0) + 1
    res["v2"].update(步骤秒=steps, 验收=accept, 边界复核=bound)
    tests = res["v2"].get("计划内测试") or []
    res["final_test"] = (accept.get("测试摘要") or "")[:2000]
    res["reply"] = {"结果": {"改动文件": ch, "测试": accept.get("测试摘要", "")[:300],
                           "边界复核": bound.get("结论", "未跑"), "步骤秒": steps, "调用": M.n,
                           "费用": round(M.cost, 4), "测试次数": {
                               "真跑": sum(1 for x in tests if x["mode"] == "real"),
                               "跳过": sum(1 for x in tests if x["mode"] == "skipped"),
                               "复用": sum(1 for x in accept.get("测试", []) if x["方式"] == "复用")}},
                    "状态": state["状态"], "原因": state["原因"]}
    res["report"] = report(res)
    if not res["fixed"]:
        res["handoff"] = (f"【停下原因】（v2 规划路径，状态 {state['状态']}）{state['原因']}\n"
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
    head = (f"DSL v2 {r['状态']}" + (f"：{r['原因']}" if r["原因"] else "")
            + f"；{res['calls']} 次模型调用，${res['cost']:.4f}，{res['seconds']}s")
    lines = [head, "各步秒：" + "，".join(f"{k} {v}" for k, v in r["结果"]["步骤秒"].items()),
             f"边界复核：{r['结果']['边界复核']}"]
    if res.get("changed_files"):
        lines.append("改动：" + "、".join(res["changed_files"]))
    lines.append(f"测试命令：{res['test_cmd']}")
    lines.append(f"记录：{res['dir']}")
    return "\n".join(lines)


# ------------------------------------------------------------------ 旧名兼容：搬走的名字仍可从 v2 取到

_MOVED = {
    "tools.dslagent.packs.code": ("PRE_SYS", "OLD_RX_LINE"),
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
