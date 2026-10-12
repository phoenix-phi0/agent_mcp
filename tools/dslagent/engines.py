"""v2 的模型引擎：按步骤指定模型（cbatch dsl_options.models → 环境变量 DSLAGENT_MODELS，JSON）。

步骤：plan（规划 / 规划重写 / 补查）、sub（问 / 问JSON / 派任务 / 并行派任务）、fix（验收补改）、bound（边界复核及其补改）；没写的步骤 sonnet。
模型串：
  sonnet / opus / haiku（或 claude-… 完整名）   claude CLI（call_claude 在 v2.py）
  codex:<模型>[:<强度>]                          codex exec，强度 minimal|low|medium|high|xhigh，缺省 medium
  grok[:<强度>]                                  grok CLI，强度 low|medium|high|xhigh，缺省 low
  opencode:<provider/model>                      opencode run
各引擎的调用函数返回同一种 dict（text / sec / ttft / cost / usage / rc / stderr / reason / partial / num_turns / tool_calls / engine / model），
保险同 call_claude：首事件前静默、空闲超时、文本里的 <invoke 拦截、输出超长、总超时（killpg）；失败重试在 v2.Model 里（统一 1 次）。
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

STEPS = ("plan", "sub", "fix", "bound")
DEFAULT = "sonnet"
CODEX_EFFORTS = ("minimal", "low", "medium", "high", "xhigh")
GROK_EFFORTS = ("low", "medium", "high", "xhigh")
CODEX_EFFORT = "medium"
GROK_EFFORT = "low"
IDLE_OC = 120            # opencode 整段才发事件，空闲超时比逐字流宽
FIRST_CAP = 120          # 首个事件之前最多静默这么久（codex / grok / opencode）
ENV = "DSLAGENT_MODELS"

_CLAUDE_RX = re.compile(r"^(sonnet|opus|haiku|claude-[A-Za-z0-9._\-\[\]]+)$")
_CODEX_RX = re.compile(r"^[A-Za-z0-9_.\-]+$")
_OC_RX = re.compile(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.:\-]+$")


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
        if not _OC_RX.match(rest):
            raise ValueError(f"opencode 模型串要写成 opencode:<provider/model>，收到：{s!r}")
        return {"engine": "opencode", "model": rest, "effort": None, "spec": s}
    raise ValueError(f"模型串不认识：{s!r}。可写：sonnet / opus / haiku / claude-…、codex:<模型>[:<强度>]、grok[:<强度>]、opencode:<provider/model>")


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


def validate(models, plan_mode="read", subtask="json"):
    """normalize + 组合限制：read 方式下 plan 只支持 claude / codex（要挂只读 dsl 工具）；DSLAGENT_SUBTASK=tool 时 sub 只支持 claude。"""
    m = normalize(models)
    p = parse(m["plan"]) if "plan" in m else None
    if p and plan_mode == "read" and p["engine"] not in ("claude", "codex"):
        raise ValueError(f"models.plan={m['plan']!r}：read 规划方式要挂只读 dsl 工具，只支持 claude 和 codex；"
                         f"{p['engine']} 做规划请同时设 dsl_options.plan_mode=full")
    s = parse(m["sub"]) if "sub" in m else None
    if s and subtask == "tool" and s["engine"] != "claude":
        raise ValueError(f"models.sub={m['sub']!r}：DSLAGENT_SUBTASK=tool 时子任务要挂 dsl 工具，只支持 claude")
    return m


def step_of(tag):
    """调用 tag → 步骤：plan / plan_fix / preq → plan；dslNN[_…] → sub；fix → fix；bound / bfix → bound；其余 None。"""
    t = re.sub(r"_reask$", "", tag or "")
    if t in ("plan", "plan_fix", "preq"):
        return "plan"
    if re.match(r"^dsl\d+", t):
        return "sub"
    if t == "fix":
        return "fix"
    if t in ("bound", "bfix"):
        return "bound"
    return None


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


def _v2():
    from . import v2      # 保险阈值（MAX_OUT / IDLE_SEC / TOOL_MARKS）按 v2 里的当前值取，测试可改
    return v2


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
    """一次子进程调用的公共部分：起进程（新进程组）、stdin 喂入、stderr 收集、总超时 / 首事件前静默 / 空闲超时三道 killpg、事件落盘。"""

    def __init__(self, cmd, stdin_text, timeout, idle, first_cap, cwd, env, reply_path):
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
                self.efh = open(str(reply_path) + ".events", "w", encoding="utf-8")
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

    def kill(self, why="总超时"):
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
                self.kill("首字前静默超时")
                return
            if self.act and now - self.last > self.idle:
                self.kill("空闲超时")
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

    def text_guard(self, so_far):
        """流里出现 <invoke 等 → 杀；累计超过 MAX_OUT → 杀。"""
        if self.killed:
            return
        V = _v2()
        if any(m in so_far for m in V.TOOL_MARKS):
            self.kill("输出工具调用格式")
        elif len(so_far) > V.MAX_OUT:
            self.kill("输出超长")

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
    from .runner import tmp_dir
    tmp = tmp_dir()
    cwd = tmp / name
    cwd.mkdir(parents=True, exist_ok=True)
    return tmp, cwd


# ------------------------------------------------------------------ codex


def call_codex(system, user, timeout=300, reply_path=None, idle=None, model=None, effort=None, first_cap=None, mcp_config=None, **_ignored):
    """codex exec 单次调用。提示经 stdin（"-"），--json 事件流，-s read-only，--disable shell_tool，--ignore-user-config / --ignore-rules / --ephemeral，
    system 经 -c developer_instructions，推理强度 -c model_reasoning_effort（缺省 medium）。回复取最后一条 agent_message（-o 文件兜底）。
    mcp_config（同 call_claude 的 mcpServers json）：只把里面的 dsl 这一个 MCP 以 -c mcp_servers.dsl.* 挂上，工具审批 approve；
    mcp_tool_call 不算违规，次数记进 tool_calls；codex 没有 max-turns，靠总超时兜底。出现命令 / 改文件 / 联网事件即杀。"""
    V = _v2()
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
    pr = _Proc(cmd, user, timeout, idle or (180 if mcp_config else V.IDLE_SEC), first_cap or int(os.environ.get("DSLAGENT_CODEX_FIRST_CAP") or FIRST_CAP),
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
            pr.kill("尝试调用工具")
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


def call_grok(system, user, timeout=300, reply_path=None, idle=None, model=None, effort=None, first_cap=None, **_ignored):
    """grok（Grok Build CLI）单轮文本生成：--output-format streaming-json 流式（记首字时间），内置工具只留 read_file 且 --deny Read（--tools "" 关不掉），
    不开子代理 / 联网，dontAsk；系统提示用 --system-prompt-override，cwd 是空目录，提示放 -p 参数（单个参数不能超过 Linux 的 128KB）。
    流里一出现 tool_call / tool_call_update 事件（哪怕被拒）立即杀；空闲超时只按正文 / 推理增量（text / thought）刷新。
    cost 取 grok 自报的 total_cost_usd（无则 0）。"""
    V = _v2()
    tmp, cwd = _empty_cwd("v2_grok_empty")
    env = dict(os.environ)
    env["TMPDIR"] = str(tmp)
    cmd = [grok_bin(), "-p", user, "--output-format", "streaming-json", "--tools", "read_file", "--deny", "Read", "--deny", "MCPTool",
           "--permission-mode", "dontAsk", "--no-subagents", "--disable-web-search", "--reasoning-effort", effort or GROK_EFFORT,
           "--system-prompt-override", system]
    if model:
        cmd += ["--model", model]
    pr = _Proc(cmd, None, timeout, idle or V.IDLE_SEC, first_cap or int(os.environ.get("DSLAGENT_GROK_FIRST_CAP") or FIRST_CAP), cwd, env,
               reply_path)
    streamed, ttft, end, n_cmds = "", None, None, 0
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
        if ty in ("tool_call", "tool_call_update") and not pr.killed:
            pr.kill("尝试调用工具")
        if ty == "text" and ev.get("data"):
            if ttft is None:
                ttft = round(now - pr.t0, 2)
            streamed += ev["data"]
            pr.write_reply(ev["data"])
            pr.text_guard(streamed)
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
    return {"text": streamed if (end is not None and not reason and rc == 0) else "", "sec": round(time.time() - pr.t0, 1), "rc": rc,
            "ttft": ttft, "cost": res.get("total_cost_usd") or 0.0, "usage": usage, "stderr": err[-500:], "reason": reason,
            "partial": streamed, "num_turns": res.get("num_turns"), "tool_calls": 0, "engine": "grok", "model": model, "subtype": None}


# ------------------------------------------------------------------ opencode


def call_opencode(system, user, timeout=300, reply_path=None, idle=None, model=None, effort=None, first_cap=None, **_ignored):
    """opencode run 单次调用。命令与环境复用 tools/obatch.py 的精简 agent（OPENCODE_CONFIG_CONTENT 注入，tools 全关，steps 限轮，--format json），
    agent.prompt 换成 system；user 经 stdin 传（大提示放 argv 会超单参数上限）；不用 --pure。事件是整段（part）结束时才发，
    空闲超时按 text / reasoning 事件刷新（缺省 IDLE_OC 秒，比逐字流宽）；出现 tool 类事件即杀。"""
    from tools import obatch as OB
    tmp, cwd = _empty_cwd("v2_oc_empty")
    model = model or OB.DEFAULT_MODEL
    cfg = OB._config({"lean": True, "preamble": False, "max_steps": 3, "permission_mode": None})
    cfg["agent"][OB.AGENT]["prompt"] = system
    env = OB._child_env()
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    env["OPENCODE_DISABLE_CLAUDE_CODE"] = "1"
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(cfg, ensure_ascii=False)
    env["TMPDIR"] = str(tmp)
    cmd = [opencode_bin(), "run", "--format", "json", "--thinking", "--agent", OB.AGENT, "-m", model]
    if effort:
        cmd += ["--variant", effort]
    pr = _Proc(cmd, user, timeout, idle or IDLE_OC, first_cap or int(os.environ.get("DSLAGENT_OC_FIRST_CAP") or FIRST_CAP), cwd, env,
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
            pr.kill("尝试调用工具")
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
    """按 parse() 的结果调非 claude 引擎（claude 走 v2.call_claude，不经这里）。"""
    fn = {"codex": call_codex, "grok": call_grok, "opencode": call_opencode}[spec["engine"]]
    return fn(system, user, timeout, model=spec["model"], effort=spec["effort"], **kw)
