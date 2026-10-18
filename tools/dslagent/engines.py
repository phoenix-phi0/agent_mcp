"""v2 的模型引擎：按步骤指定模型（cbatch dsl_options.models → 环境变量 DSLAGENT_MODELS，JSON）。

步骤：plan（规划 / 规划重写）、sub（问 / 问JSON / 派任务 / 并行派任务）、fix（验收补改）、bound（边界复核及其补改）；没写的步骤 sonnet。
模型串：
  sonnet / opus / haiku（或 claude-… 完整名）   claude CLI（call_claude 在本文件）
  codex:<模型>[:<强度>]                          codex exec，强度 minimal|low|medium|high|xhigh，缺省 medium
  grok[:<强度>]                                  grok CLI，强度 low|medium|high|xhigh，缺省 low
  opencode:<provider/model>[:budget=<N>]         opencode run；budget = 思考 token 预算（正整数，只影响这次子进程），缺省不限
各引擎的调用函数返回同一种 dict（text / sec / ttft / cost / usage / rc / stderr / reason / partial / num_turns / tool_calls / engine / model），
保险（guard.py，四个引擎共用 _Proc）：首事件前静默、空闲超时、文本里的 <invoke 拦截、输出超长、总超时（killpg）；失败重试在 v2.Model 里（统一 1 次）。
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import agents as AG
from . import guard as G

STEPS = ("plan", "sub", "fix", "bound")
DEFAULT = "sonnet"
CODEX_EFFORTS = ("minimal", "low", "medium", "high", "xhigh")
GROK_EFFORTS = ("low", "medium", "high", "xhigh")
CODEX_EFFORT = "medium"
CODEX_PLAN_EFFORT = "high"        # codex 用作 plan 且模型串没写强度时的默认
ESCALATE_ENV = "DSLAGENT_CODEX_ESCALATE"      # 设成 0 关闭「plan 默认 high、plan_fix 升一档」
GROK_EFFORT = "low"
GROK_READ_TOOLS = ("read_file", "grep", "list_dir")      # read 规划放开的内置工具（只读）
GROK_DISABLED = ("write,search_replace,run_terminal_command,kill_command_or_subagent,todo_write,get_command_or_subagent_output,spawn_subagent,"
                 "scheduler_create,scheduler_delete,scheduler_list,monitor,search_tool,use_tool,workflow,web_search,open_page,open_page_with_find,"
                 "web_fetch,x_user_search,x_semantic_search,x_keyword_search,x_thread_fetch,image_gen,image_edit,image_to_video,reference_to_video,"
                 "send_feedback,ask_user_question,enter_plan_mode,exit_plan_mode")
GROK_MAX_TURNS = AG.PLAN.turns_grok
GROK_READ_CAP = 200000   # read 规划累计读入字数上限，超了杀
ENV = "DSLAGENT_MODELS"

_CLAUDE_RX = re.compile(r"^(sonnet|opus|haiku|claude-[A-Za-z0-9._\-\[\]]+)$")
_CODEX_RX = re.compile(r"^[A-Za-z0-9_.\-]+$")
_OC_RX = re.compile(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.:\-]+$")
_OC_BUDGET_RX = re.compile(r"^(.*):budget=(.*)$")
OC_BUDGET_MAX = 200000


# ------------------------------------------------------------------ 解析 / 校验


def parse(s):
    """模型串 → {"engine", "model", "effort", "spec"}；格式不对报 ValueError。claude 的 effort 是 None。"""
    if not isinstance(s, str) or not s.strip():
        raise ValueError(f"模型串要是非空字符串，收到：{s!r}")
    s = s.strip()
    head, _, rest = s.partition(":")
    if _CLAUDE_RX.match(s):
        return {"engine": "claude", "model": s, "effort": None, "spec": s}
    if head == "codex":
        model, _, eff = rest.partition(":")
        if not _CODEX_RX.match(model):
            raise ValueError(f"codex 模型串要写成 codex:<模型>[:<强度>]，收到：{s!r}")
        if eff and eff not in CODEX_EFFORTS:
            raise ValueError(f"codex 推理强度只能是 {'|'.join(CODEX_EFFORTS)}，收到：{eff!r}（{s!r}）")
        return {"engine": "codex", "model": model, "effort": eff or CODEX_EFFORT, "spec": s}
    if head == "grok":
        if ":" in rest or (s != "grok" and not rest):
            raise ValueError(f"grok 模型串要写成 grok[:<强度>]，收到：{s!r}")
        if rest and rest not in GROK_EFFORTS:
            raise ValueError(f"grok 推理强度只能是 {'|'.join(GROK_EFFORTS)}，收到：{rest!r}（{s!r}）")
        return {"engine": "grok", "model": None, "effort": rest or GROK_EFFORT, "spec": s}
    if head == "opencode":
        budget = None
        bm = _OC_BUDGET_RX.match(rest)
        if bm:
            rest, b = bm.groups()
            if not re.fullmatch(r"[1-9][0-9]{0,6}", b) or int(b) > OC_BUDGET_MAX:
                raise ValueError(f"opencode 思考预算要是 1–{OC_BUDGET_MAX} 的整数（写成 :budget=6000），收到：{b!r}（{s!r}）")
            budget = int(b)
        if not _OC_RX.match(rest):
            raise ValueError(f"opencode 模型串要写成 opencode:<provider/model>[:budget=<N>]，收到：{s!r}")
        out = {"engine": "opencode", "model": rest, "effort": None, "spec": s}
        if budget:
            out["budget"] = budget
        return out
    raise ValueError(f"模型串不认识：{s!r}。可写：sonnet / opus / haiku / claude-…、codex:<模型>[:<强度>]、grok[:<强度>]、opencode:<provider/model>[:budget=<N>]")


def normalize(value):
    """dsl_options.models（字典 / 字符串 / 空）→ {步骤: 模型串}，只含写了的步骤（字符串 = 四步都用它）。不合格报 ValueError。"""
    if value in (None, "", {}):
        return {}
    if isinstance(value, str):
        parse(value)
        return {k: value.strip() for k in STEPS}
    if not isinstance(value, dict):
        raise ValueError(f"models 要是字典或字符串，收到：{value!r}")
    bad = [k for k in value if k not in STEPS]
    if bad:
        raise ValueError(f"models 里步骤名不认识：{'、'.join(map(str, bad))}。可用：{'、'.join(STEPS)}")
    out = {}
    for k, v in value.items():
        if v in (None, ""):
            continue
        parse(v)
        out[k] = v.strip()
    return out


def validate(models, subtask="json"):
    """normalize + 组合限制：plan 要读代码，只支持 claude / codex / grok（claude / codex 挂只读 dsl 工具，grok 用自带只读工具；opencode 不能做规划）；
    DSLAGENT_SUBTASK=tool 时 sub 只支持 claude。"""
    m = normalize(models)
    p = parse(m["plan"]) if "plan" in m else None
    if p and p["engine"] not in ("claude", "codex", "grok"):
        raise ValueError(f"models.plan={m['plan']!r}：规划要读代码，只支持 claude / codex / grok，{p['engine']} 不能做规划")
    s = parse(m["sub"]) if "sub" in m else None
    if s and subtask == "tool" and s["engine"] != "claude":
        raise ValueError(f"models.sub={m['sub']!r}：DSLAGENT_SUBTASK=tool 时子任务要挂 dsl 工具，只支持 claude")
    return m


def plan_effort(sp, tag):
    """codex 规划步骤的强度调整（只动 codex）：plan 且模型串没写强度 → high；plan_fix 比 plan 的强度高一档（medium→high，high→xhigh，xhigh 不变）。
    DSLAGENT_CODEX_ESCALATE=0 关闭，回到模型串 / 缺省 medium。sub / fix / bound 等其它步骤不变。返回新的 spec 字典（不改入参）。"""
    t = (tag or "").removesuffix("_reask")
    if sp.get("engine") != "codex" or t not in ("plan", "plan_fix") or (os.environ.get(ESCALATE_ENV) or "").strip() == "0":
        return sp
    explicit = bool(sp["spec"].partition(":")[2].partition(":")[2])
    eff = sp["effort"] if explicit else CODEX_PLAN_EFFORT
    if t == "plan_fix":
        eff = CODEX_EFFORTS[min(CODEX_EFFORTS.index(eff) + 1, len(CODEX_EFFORTS) - 1)]
    return dict(sp, effort=eff)


def step_of(tag):
    """调用 tag → 步骤：plan / plan_fix → plan；dslNN[_…] → sub；fix → fix；bound / bfix / bound_judge → bound；table_fill（补表）→ plan；其余 None。"""
    a = AG.of_tag(tag)
    return a.step if a else None


def effective(models):
    """补全缺省（sonnet）后的 {步骤: 模型串}，记进结果用。"""
    return {k: (models or {}).get(k) or DEFAULT for k in STEPS}


def from_env():
    """读 DSLAGENT_MODELS（JSON）→ 校验后的 {步骤: 模型串}；没设 → {}。"""
    raw = (os.environ.get(ENV) or "").strip()
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except ValueError as e:
        raise ValueError(f"{ENV} 不是合法 JSON：{e}") from None
    return normalize(val)


# ------------------------------------------------------------------ 公共：进程、保险


def _bin(env_name, name, fallback):
    return os.environ.get(env_name) or shutil.which(name) or fallback


def codex_bin():
    return _bin("DSLAGENT_CODEX_BIN", "codex", str(Path.home() / ".local" / "bin" / "codex"))


def grok_bin():
    return _bin("DSLAGENT_GROK_BIN", "grok", str(Path.home() / ".grok" / "bin" / "grok"))


def opencode_bin():
    from tools import obatch as OB
    return os.environ.get("DSLAGENT_OC_BIN") or OB.OPENCODE_BIN


class _Proc:
    """一次子进程调用的公共部分（claude / codex / grok / opencode 共用）：起进程（新进程组）、stdin 喂入、stderr 收集、
    总超时 / 首事件前静默 / 空闲超时三道 killpg、文本保险（工具调用格式 / 超长）、事件落盘（events=False 不落）。"""

    def __init__(self, cmd, stdin_text, timeout, idle, first_cap, cwd, env, reply_path, events=True):
        self.t0 = time.time()
        self.killed, self.err_buf = [], []
        self.last = self.first = None          # 最近一次「有效活动」/ 首个事件的墙钟
        self.act = False                       # 是否已收到过正文 / 推理 / 工具活动（之后才算空闲）
        self.idle, self.first_cap = idle, first_cap
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, cwd=cwd, env=env, start_new_session=True)
        self.fh = self.efh = None
        if reply_path:
            try:
                self.fh = open(reply_path, "w", encoding="utf-8")
                self.efh = open(str(reply_path) + ".events", "w", encoding="utf-8") if events else None
            except OSError:
                pass
        self.done = threading.Event()
        self.th = threading.Thread(target=lambda: self.err_buf.append(self.p.stderr.read()), daemon=True)
        self.th.start()
        if stdin_text is not None:
            threading.Thread(target=self._feed, args=(stdin_text,), daemon=True).start()
        self.timer = threading.Timer(timeout, self.kill)
        self.timer.start()
        threading.Thread(target=self._watch, daemon=True).start()

    def _feed(self, text):
        try:
            self.p.stdin.write(text)
            self.p.stdin.close()
        except (OSError, ValueError):
            pass

    def kill(self, why=G.R_TOTAL):
        if not self.killed:
            self.killed.append(why)
        try:
            os.killpg(self.p.pid, 9)
        except OSError:
            pass

    def _watch(self):
        while not self.done.wait(min(1.0, max(0.05, self.idle / 4))):
            now = time.time()
            if self.first is None and now - self.t0 > self.first_cap:
                self.kill(G.R_FIRST)
                return
            if self.act and now - self.last > self.idle:
                self.kill(G.R_IDLE)
                return

    def event(self, now=None):
        """收到一个事件（首事件前静默的计时到此为止）。"""
        now = now or time.time()
        if self.first is None:
            self.first = self.last = now
        return now

    def active(self, now=None):
        """收到正文 / 推理 / 工具活动：刷新空闲计时。"""
        self.last = now or time.time()
        self.act = True

    def log_event(self, line):
        if self.efh:
            try:
                self.efh.write(f"{time.time() - self.t0:7.1f}s {line.strip()[:300]}\n")
                self.efh.flush()
            except OSError:
                pass

    def write_reply(self, s):
        if self.fh:
            try:
                self.fh.write(s)
                self.fh.flush()
            except OSError:
                pass

    def text_guard(self, so_far, total=None):
        """so_far 里出现 <invoke 等 → 杀；累计字数（缺省 len(so_far)，多轮调用传各轮累计 total）超过 MAX_OUT → 杀。"""
        if self.killed:
            return
        if G.has_mark(so_far):
            self.kill(G.R_MARK)
        elif (len(so_far) if total is None else total) > G.MAX_OUT:
            self.kill(G.R_LONG)

    def close(self):
        """读完 stdout 后收尾：等进程、停计时、关文件。返回 (reason, stderr 文本)。"""
        self.p.wait()
        self.timer.cancel()
        self.done.set()
        self.th.join(timeout=5)
        for f in (self.fh, self.efh):
            if f:
                f.close()
        reason = self.killed[0] if self.killed else None
        return reason, "".join(x or "" for x in self.err_buf) + (f"\n[{reason}被杀]" if self.killed else "")


def _empty_cwd(name):
    from .common import tmp_dir
    tmp = tmp_dir()
    cwd = tmp / name
    cwd.mkdir(parents=True, exist_ok=True)
    return tmp, cwd


# ------------------------------------------------------------------ claude


def call_claude(system, user, timeout=300, model=None, reply_path=None, idle=None, mcp_config=None, max_turns=1, allow_tool=None,
                first_cap=None):
    """claude -p（model 缺省 DEFAULT），自定系统提示，无内置工具 / 技能，流式（记首 token）。返回 text / sec / ttft / cost / usage / rc / stderr / reason。
    进程保险同 codex / grok / opencode（_Proc）：总超时、首个 API 事件前静默（FIRST_CAP）、首 token 之后 idle 秒没有新流事件（空闲超时）、
    文本里出现 <invoke / <function_calls（输出工具调用格式）、累计超过 MAX_OUT 字符（输出超长）。
    reply_path：边收流边把文本增量追加进该文件，被杀时已收到的内容也在；返回的 partial 是已收到的流文本。
    mcp_config（工具调用）：多挂一个 MCP（--mcp-config + --strict-mcp-config，内置工具仍 --tools ""，只许 allow_tool 那一个），
    --max-turns 用 max_turns；text 是最后一轮的最终回复（中途轮次里的文字、真实工具调用不算），「输出工具调用格式」只查当前这一轮的文字，
    超长按各轮累计，返回里多 num_turns / tool_calls / subtype。"""
    from tools.cbatch import CLAUDE_BIN

    from .common import child_env
    tmp, cwd = _empty_cwd("v2_empty")
    cmd = [os.environ.get("CBATCH_CLAUDE") or CLAUDE_BIN, "-p", "--model", model or DEFAULT, "--output-format", "stream-json",
           "--verbose", "--include-partial-messages", "--max-turns", str(max_turns), "--tools", "", "--setting-sources", "",
           "--strict-mcp-config", "--disable-slash-commands", "--system-prompt", system]
    if mcp_config:
        cmd += ["--mcp-config", str(mcp_config), "--allowedTools", allow_tool or "mcp__dsl__dsl"]
    pr = _Proc(cmd, user, timeout, idle or G.IDLE_SEC, first_cap or G.FIRST_CAP, cwd, child_env(tmp), reply_path, events=False)
    result, ttft, streamed = None, None, ""
    turn_text, total_chars = "", 0          # 当前这一轮的流文本 / 全部轮的累计字数
    text = ""
    msgs, tool_ids = {}, set()              # 消息 id → {text, tool}（按出现顺序），真实工具调用块 id
    for line in pr.p.stdout:
        if ttft is not None:
            pr.active()
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        ty = ev.get("type")
        if ty in ("stream_event", "assistant", "result"):
            pr.event()
        if ty == "stream_event":
            se = ev.get("event") or {}
            if se.get("type") == "message_start":
                turn_text = ""
            if se.get("type") == "content_block_delta":
                if ttft is None:
                    ttft = round(time.time() - pr.t0, 2)
                    pr.active()
                d = se.get("delta") or {}
                if d.get("type") == "text_delta" and d.get("text"):
                    streamed += d["text"]
                    turn_text += d["text"]
                    total_chars += len(d["text"])
                    if mcp_config:
                        pr.text_guard(turn_text, total_chars)
                    else:
                        pr.text_guard(streamed)
                    pr.write_reply(d["text"])
        elif ty == "assistant":
            if mcp_config:
                m = msgs.setdefault(ev["message"].get("id") or f"m{len(msgs)}", {"text": "", "tool": False})
                for b in ev["message"].get("content", []):
                    if b.get("type") == "text":
                        m["text"] += b["text"]
                    elif b.get("type") == "tool_use":
                        m["tool"] = True
                        tool_ids.add(b.get("id") or len(tool_ids))
                continue
            for b in ev["message"].get("content", []):
                if b.get("type") == "text":
                    text += b["text"]
        elif ty == "result":
            result = ev
    reason, err = pr.close()
    if mcp_config:
        last_msg = list(msgs.values())[-1] if msgs else None
        text = (last_msg["text"] if last_msg and not last_msg["tool"] else "") if result is None or result.get("is_error") \
            else (result.get("result") or "")
    res = result or {}
    u = res.get("usage", {}) or {}
    usage = {"input": u.get("input_tokens"), "output": u.get("output_tokens"),
             "cache_read": u.get("cache_read_input_tokens"), "cache_creation": u.get("cache_creation_input_tokens")}
    return {"text": text, "sec": round(time.time() - pr.t0, 1), "rc": pr.p.returncode, "ttft": ttft,
            "cost": res.get("total_cost_usd") or 0.0, "usage": usage, "stderr": err[-500:], "reason": reason,
            "partial": streamed, "num_turns": res.get("num_turns"), "tool_calls": len(tool_ids),
            "subtype": res.get("subtype")}


# ------------------------------------------------------------------ codex


def call_codex(system, user, timeout=300, reply_path=None, idle=None, model=None, effort=None, first_cap=None, mcp_config=None, **_ignored):
    """codex exec 单次调用。提示经 stdin（"-"），--json 事件流，-s read-only，--disable shell_tool，--ignore-user-config / --ignore-rules / --ephemeral，
    system 经 -c developer_instructions，推理强度 -c model_reasoning_effort（缺省 medium）。回复取最后一条 agent_message（-o 文件兜底）。
    mcp_config（同 call_claude 的 mcpServers json）：只把里面的 dsl 这一个 MCP 以 -c mcp_servers.dsl.* 挂上，工具审批 approve；
    mcp_tool_call 不算违规，次数记进 tool_calls；codex 没有 max-turns，靠总超时兜底。出现命令 / 改文件 / 联网事件即杀。"""
    tmp, cwd = _empty_cwd("v2_codex_empty")
    env = dict(os.environ)
    env["TMPDIR"] = str(tmp)
    last_file = tmp / f"v2_codex_last_{os.getpid()}_{threading.get_ident()}_{int(time.time() * 1000)}.txt"
    cmd = [codex_bin(), "exec", "--skip-git-repo-check", "--ephemeral", "--ignore-user-config", "--ignore-rules", "-s", "read-only",
           "--disable", "shell_tool", "--json", "-o", str(last_file),
           "-c", f"model_reasoning_effort={json.dumps(effort or CODEX_EFFORT)}",
           "-c", f"developer_instructions={json.dumps(system, ensure_ascii=False)}"]
    if mcp_config:
        srv = json.loads(Path(mcp_config).read_text(encoding="utf-8"))["mcpServers"]["dsl"]
        cmd += ["-c", f"mcp_servers.dsl.command={json.dumps(srv['command'])}",
                "-c", f"mcp_servers.dsl.args={json.dumps(srv['args'], ensure_ascii=False)}",
                "-c", 'mcp_servers.dsl.default_tools_approval_mode="approve"']
    if model:
        cmd += ["-m", model]
    cmd.append("-")
    pr = _Proc(cmd, user, timeout, idle or (G.IDLE_MCP if mcp_config else G.IDLE_SEC), first_cap or int(os.environ.get("DSLAGENT_CODEX_FIRST_CAP") or G.FIRST_CAP),
               cwd, env, reply_path)
    msgs, t_text, mcp_n, err_msg = [], [], 0, ""
    usage = {"input": None, "output": None, "cache_read": None, "reasoning": None}
    for line in pr.p.stdout:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        now = pr.event()
        ty, item = ev.get("type"), ev.get("item") or {}
        it = item.get("type")
        if ty in ("item.started", "item.completed", "item.updated"):
            pr.active(now)
        if ty == "item.completed" and it == "agent_message" and (item.get("text") or "").strip():
            if not t_text:
                t_text.append(now)
            msgs.append(item["text"])
            pr.write_reply(item["text"] + "\n")
            pr.text_guard(item["text"] if len(msgs) == 1 else "\n".join(msgs))
        elif ty == "turn.completed":
            u = ev.get("usage") or {}
            usage = {"input": u.get("input_tokens"), "output": u.get("output_tokens"),
                     "cache_read": u.get("cached_input_tokens"), "reasoning": u.get("reasoning_output_tokens")}
        elif ty in ("error", "turn.failed"):
            e = ev.get("error") or ev
            err_msg = (e.get("message") if isinstance(e, dict) else None) or json.dumps(e, ensure_ascii=False)[:500]
        if ty == "item.completed" and it == "mcp_tool_call":
            mcp_n += 1
        if it != "agent_message":
            pr.log_event(line)
        if not pr.killed and (it in ("command_execution", "file_change", "web_search") or (it == "mcp_tool_call" and not mcp_config)):
            pr.kill(G.R_TRY_TOOL)
    reason, err = pr.close()
    text = msgs[-1] if msgs else ""
    if not text and not pr.killed:
        try:
            text = last_file.read_text(encoding="utf-8")
        except OSError:
            pass
    try:
        last_file.unlink()
    except OSError:
        pass
    if err_msg:
        err = err_msg + "\n" + err
    rc = pr.p.returncode
    if err_msg and not rc and not reason:
        rc = 1
    return {"text": text if (not reason and rc == 0) else "", "sec": round(time.time() - pr.t0, 1), "rc": rc,
            "ttft": round(t_text[0] - pr.t0, 2) if t_text else None, "cost": 0.0, "usage": usage, "stderr": err[-500:], "reason": reason,
            "partial": "\n".join(msgs), "num_turns": mcp_n + 1, "tool_calls": mcp_n, "engine": "codex", "model": model, "subtype": None}


# ------------------------------------------------------------------ grok


def _grok_out_len(ro):
    """tool_call_update 的 rawOutput → 返回字数（有 Content.content 取它，否则整个对象的 json 长度）。"""
    try:
        c = ro.get("Content")
        if isinstance(c, dict) and isinstance(c.get("content"), str):
            return len(c["content"])
    except AttributeError:
        pass
    return len(json.dumps(ro, ensure_ascii=False)) if ro else 0


def call_grok(system, user, timeout=300, reply_path=None, idle=None, model=None, effort=None, first_cap=None, read_cwd=None, **_ignored):
    """grok（Grok Build CLI）单轮文本生成：--output-format streaming-json 流式（记首字时间），内置工具只留 read_file 且 --deny Read（--tools "" 关不掉），
    不开子代理 / 联网，dontAsk；系统提示用 --system-prompt-override，cwd 是空目录，提示放 -p 参数（单个参数不能超过 Linux 的 128KB）。
    流里一出现 tool_call / tool_call_update 事件（哪怕被拒）立即杀；空闲超时只按正文 / 推理增量（text / thought）刷新。
    cost 取 grok 自报的 total_cost_usd（无则 0）。
    read_cwd（read 规划，只用于 plan / plan_fix）：cwd = 该目录（待改项目），只放开 read_file / grep / list_dir（GROK_READ_TOOLS），其余内置工具
    （GROK_DISABLED）从工具表去掉并 deny 写 / 编辑 / 命令 / MCP，--max-turns GROK_MAX_TURNS；事件流里出现别的工具调用即杀（调用被禁工具），
    累计读入超过 GROK_READ_CAP 字即杀（读超限）；工具调用逐条记进返回的 calls（工具 / 参数 / 返回字数）；回复取最后一次工具调用之后的文本。
    到 --max-turns 时 grok 发 max_turns_reached 事件、end.stopReason=cancelled、rc=1、没有最终回复：read 规划里记 subtype=error_max_turns（v2 当轮数用尽，走收尾）。"""
    tmp, cwd = _empty_cwd("v2_grok_empty")
    env = dict(os.environ)
    env["TMPDIR"] = str(tmp)
    cmd = [grok_bin(), "-p", user, "--output-format", "streaming-json", "--tools", "read_file", "--deny", "Read", "--deny", "MCPTool",
           "--permission-mode", "dontAsk", "--no-subagents", "--disable-web-search", "--reasoning-effort", effort or GROK_EFFORT,
           "--system-prompt-override", system]
    if read_cwd:
        cwd = str(read_cwd)
        cmd = [grok_bin(), "-p", user, "--output-format", "streaming-json", "--tools", ",".join(GROK_READ_TOOLS), "--disallowed-tools", GROK_DISABLED,
               "--deny", "write", "--deny", "Edit", "--deny", "Bash", "--deny", "run_terminal_command", "--deny", "MCPTool",
               "--permission-mode", "dontAsk", "--no-subagents", "--disable-web-search", "--max-turns", str(GROK_MAX_TURNS),
               "--reasoning-effort", effort or GROK_EFFORT, "--system-prompt-override", system]
    if model:
        cmd += ["--model", model]
    pr = _Proc(cmd, None, timeout, idle or G.IDLE_SEC, first_cap or int(os.environ.get("DSLAGENT_GROK_FIRST_CAP") or G.FIRST_CAP), cwd, env,
               reply_path)
    streamed, ttft, end, n_cmds, max_turns_hit = "", None, None, 0, False
    calls, byid, cur = [], {}, ""
    for line in pr.p.stdout:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        now = pr.event()
        ty = ev.get("type")
        if ty in ("text", "thought") and ev.get("data"):
            pr.active(now)
        if ty == "available_commands":
            n_cmds += 1
        elif ty not in ("text", "thought"):
            pr.log_event(line)
        if read_cwd and ty in ("tool_call", "tool_call_update"):
            pr.active(now)
            if ty == "tool_call":
                name = ev.get("toolName")
                c = {"工具": name, "参数": ev.get("rawInput"), "返回字数": None}
                calls.append(c)
                byid[ev.get("toolCallId")] = c
                cur = ""
                if name not in GROK_READ_TOOLS and not pr.killed:
                    pr.kill(G.R_BAD_TOOL)
            else:
                c = byid.get(ev.get("toolCallId"))
                if c and ev.get("rawOutput"):
                    c["返回字数"] = _grok_out_len(ev["rawOutput"])
                    if not pr.killed and sum(x["返回字数"] or 0 for x in calls) > GROK_READ_CAP:
                        pr.kill(G.R_READ_CAP)
        elif ty in ("tool_call", "tool_call_update") and not pr.killed:
            pr.kill(G.R_TRY_TOOL)
        if ty == "text" and ev.get("data"):
            if ttft is None:
                ttft = round(now - pr.t0, 2)
            streamed += ev["data"]
            cur += ev["data"]
            pr.write_reply(ev["data"])
            pr.text_guard(streamed)
        elif ty == "max_turns_reached":
            max_turns_hit = True
        elif ty == "end":
            end = ev
    reason, err = pr.close()
    res = end or {}
    u = res.get("usage", {}) or {}
    usage = {"input": u.get("input_tokens"), "output": u.get("output_tokens"), "cache_read": u.get("cache_read_input_tokens"),
             "cache_creation": u.get("cache_creation_input_tokens"), "reasoning": u.get("reasoning_tokens")}
    rc = pr.p.returncode
    if end is not None and res.get("stopReason") not in (None, "end_turn") and not reason:
        reason, rc = f"stopReason={res.get('stopReason')}", rc or 1
    text = (cur if read_cwd else streamed) if (end is not None and not reason and rc == 0) else ""
    r = {"text": text, "sec": round(time.time() - pr.t0, 1), "rc": rc,
         "ttft": ttft, "cost": res.get("total_cost_usd") or 0.0, "usage": usage, "stderr": err[-500:], "reason": reason,
         "partial": streamed, "num_turns": res.get("num_turns"), "tool_calls": len(calls), "engine": "grok", "model": model,
         "subtype": "error_max_turns" if max_turns_hit and read_cwd else None}
    if read_cwd:
        r["calls"] = calls
    return r


# ------------------------------------------------------------------ opencode


def _oc_budget(cfg, model, budget):
    """把思考预算合并进 opencode 配置（原地改 cfg）：model 是 <provider>/<模型>；已有的同名配置项保留，只覆盖 enable_thinking / thinking_budget。"""
    prov, _, mid = model.partition("/")
    opts = cfg.setdefault("provider", {}).setdefault(prov, {}).setdefault("models", {}).setdefault(mid, {}).setdefault("options", {})
    opts.update({"enable_thinking": True, "thinking_budget": int(budget)})


def call_opencode(system, user, timeout=300, reply_path=None, idle=None, model=None, effort=None, first_cap=None, budget=None, **_ignored):
    """opencode run 单次调用。命令与环境复用 tools/obatch.py 的精简 agent（OPENCODE_CONFIG_CONTENT 注入，tools 全关，steps 限轮，--format json），
    agent.prompt 换成 system；user 经 stdin 传（大提示放 argv 会超单参数上限）；不用 --pure。事件是整段（part）结束时才发，
    空闲超时按 text / reasoning 事件刷新（缺省 IDLE_OC 秒，比逐字流宽）；出现 tool 类事件即杀。
    budget（正整数）→ 在注入的配置里合并 provider.<p>.models.<m>.options = {enable_thinking: true, thinking_budget: N}，只影响这次子进程。"""
    from tools import obatch as OB
    tmp, cwd = _empty_cwd("v2_oc_empty")
    model = model or OB.DEFAULT_MODEL
    cfg = OB._config({"lean": True, "preamble": False, "max_steps": 3, "permission_mode": None})
    cfg["agent"][OB.AGENT]["prompt"] = system
    if budget:
        _oc_budget(cfg, model, budget)
    env = OB._child_env()
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    env["OPENCODE_DISABLE_CLAUDE_CODE"] = "1"
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(cfg, ensure_ascii=False)
    env["TMPDIR"] = str(tmp)
    env["PWD"] = str(cwd)           # opencode 工作目录取 PWD；stdin 由 _Proc 写完即关
    cmd = [opencode_bin(), "run", "--format", "json", "--thinking", "--agent", OB.AGENT, "-m", model]
    if effort:
        cmd += ["--variant", effort]
    pr = _Proc(cmd, user, timeout, idle or G.IDLE_OC, first_cap or int(os.environ.get("DSLAGENT_OC_FIRST_CAP") or G.FIRST_CAP), cwd, env,
               reply_path)
    streamed, ttft, cost, n_tok, err_msg = "", None, 0.0, 0, ""
    tok = {"input": 0, "output": 0, "reasoning": 0, "total": 0}
    for line in pr.p.stdout:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        now = pr.event()
        ty, part = ev.get("type"), ev.get("part") or {}
        if ty in ("text", "reasoning") and (part.get("text") or "").strip():
            pr.active(now)
            if ty == "text":
                if ttft is None:
                    ttft = round(now - pr.t0, 2)
                streamed += part["text"]
                pr.write_reply(part["text"])
                pr.text_guard(streamed)
        elif ty == "step_finish":
            tk = part.get("tokens")
            if isinstance(tk, dict):
                for k in tok:
                    tok[k] += tk.get(k) or 0
                n_tok += 1
            cost += part.get("cost") or 0
        elif ty == "error":
            e = ev.get("error") or part
            msg = (e.get("data", {}) or {}).get("message") if isinstance(e, dict) else None
            err_msg = (msg or json.dumps(e, ensure_ascii=False))[:500]
        if ty not in ("text", "reasoning"):
            pr.log_event(line)
        if (ty in ("tool", "tool_use", "tool_call") or part.get("type") == "tool") and not pr.killed:
            pr.kill(G.R_TRY_TOOL)
    reason, err = pr.close()
    if err_msg:
        err = err_msg + "\n" + err
    rc = pr.p.returncode
    if err_msg and not rc and not reason:
        rc = 1
    usage = {"input": tok["input"] or None, "output": tok["output"] or None, "reasoning": tok["reasoning"] or None, "total": tok["total"] or None}
    return {"text": streamed if (not reason and rc == 0) else "", "sec": round(time.time() - pr.t0, 1), "rc": rc, "ttft": ttft,
            "cost": cost or 0.0, "usage": usage, "stderr": err[-500:], "reason": reason, "partial": streamed, "num_turns": n_tok,
            "tool_calls": 0, "engine": "opencode", "model": model, "subtype": None}


def call(spec, system, user, timeout, **kw):
    """按 parse() 的结果调引擎。"""
    fn = {"claude": call_claude, "codex": call_codex, "grok": call_grok, "opencode": call_opencode}[spec["engine"]]
    extra = {"budget": spec["budget"]} if spec.get("budget") else {}
    return fn(system, user, timeout, model=spec["model"], **({"effort": spec["effort"]} if spec["engine"] != "claude" else {}), **extra, **kw)
