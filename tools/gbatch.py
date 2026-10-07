# -*- coding: utf-8 -*-
"""GBatch：把一批提示词交给 Grok Build 的无头模式（grok -p）逐条跑。

接口跟 tools/cbatch.py 一样（describe / submit / status / wait / jobs /
cancel），执行器的做法也一样：submit 起一个脱离当前进程的后台执行器
（python -m tools.gbatch _run <job_id>），进度和输出写进
JOBS/<job_id>/job.json。理由见 cbatch.py 的模块文档，这里只写跟 claude
不一样的地方。

## 要批准的工具调用会让整条停下

claude -p 碰到要批准的调用是拒掉这一个、接着干，最后在
permission_denials 里列出来。grok -p 不是：它直接把这一回合中断，
输出 stopReason="cancelled"，退出码照样是 0，text 里只有它「打算做」的
那句话。不看 stopReason 的话，这条会被当成成功——实测过，让它建个文件，
返回「我来创建 a.txt」，文件根本没有。

所以 stopReason 不是 end_turn 的一律记 error，原因写进 error。

json 输出里没有「卡在哪个工具调用」的信息（只有 text / stopReason /
sessionId / 用量）。grok 把会话记录写在 $GROK_HOME（默认 ~/.grok）的
sessions/<编码后的目录>/<sessionId>/updates.jsonl，里面有每个 tool_call
和它失败的原因，被拒的那条是 "User cancelled the execution for tool …"。
_pending_calls 从那里读出来写进 error，比如「需要批准：Edit /tmp/x.py」。

## 权限：acceptEdits 单独传不管用

文档（22-permissions-and-safety.md）的模式表里写着 acceptEdits =「编辑
不用问」，但实测（grok 1.0.46）单传 --permission-mode acceptEdits，第一个
write 调用照样要批准、回合被中断。原因在 10-hooks.md：grok 运行时的模式
只有 default / auto / plan / bypassPermissions 四种，「Claude 的 acceptEdits
/ dontAsk 在 grok 里没有对应」——命令行收下这个值只是为了兼容，落到运行时
就是 default（问）。config.toml 的 ui.permission_mode 也只认 default / ask /
auto / always-approve。

所以对齐 cbatch 的语义：acceptEdits 时自动补一条 --allow Edit（grok 的
Edit 规则也管 write 工具）。要跑命令仍要显式放行 Bash，同 claude。

Bash 规则也有盖不住的：实测 --allow Bash --allow Edit 下，
`mkdir -p d && printf … > d/a.py && python3 d/a.py` 照样要批准、整条中断。
所以 PREAMBLE 叮嘱它用写文件工具、命令一条一条跑；_hint 认出这种情况。

其它模式按 grok 的语义：
- default / 不传：只有只读工具和内置的只读命令（ls、cat、git status…）
  不用批准，别的要批准，-p 里就是整条中断。
- dontAsk：只有 allow 规则和只读操作能跑，别的直接拒（文档说是 auto-deny，
  不是中断；没实测）。
- auto：分类器判断，判不放行的在 -p 里直接失败并告诉模型。
- plan：兼容用，等于只读。
- bypassPermissions：不收，见下。

allowed_tools 收 Claude 的工具名，翻译成 grok 的规则名，见 TOOL_MAP。

## 不收 bypassPermissions

grok 里 bypassPermissions 就是 --always-approve。理由同 cbatch：批量没人
看着，要放开就指定到具体工具。单独一个 "*" 规则等于全放开，一样不收。

## 其他差别

- 环境交代走 --rules（grok 的「追加到系统提示」），不是
  --append-system-prompt。
- 续接会话用 -r <sessionId>，续接后 sessionId 不变。
- 模型默认不指定，用 grok 自己的默认（`grok models` 看有哪些）。没有
  cbatch 的 model="auto"。
- grok 也读工作目录下的 .claude/settings.json 里的权限规则。

## 用法

    from tools import gbatch

    gbatch.describe()
    j = gbatch.submit(["任务一", "任务二"])
    gbatch.status(j["job_id"])
    gbatch.wait(j["job_id"])
    gbatch.cancel(j["job_id"])
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from .cbatch import _child_env, _now, _pid_alive, _settle
from .zcode_tool import UnsafeWorkdirError, check_workdir

ROOT = Path(__file__).resolve().parents[1]

JOBS = Path(os.environ.get("GBATCH_HOME")
            or Path.home() / ".grok-batch" / "jobs")

# 执行端。systemd 起的 MCP 服务 PATH 里没有 ~/.local/bin 和 ~/.grok/bin，
# 找不到就退到安装脚本的默认位置。
GROK_BIN = (os.environ.get("GBATCH_GROK") or shutil.which("grok")
            or str(Path.home() / ".grok" / "bin" / "grok"))

MAX_TASKS = 10
TASK_TIMEOUT = 600

# 同 cbatch.PREAMBLE，多一条：grok 要批准的调用会直接中断整条，提前说清楚
# 能让它少碰没放开的工具。
PREAMBLE = """这是批量任务里的一条，没有人在旁边看着，也没法回答你的问题。

1. 同一件事失败两次就停下来报告：失败在哪一步、报的什么错、本来想做什么。
2. 单条任务有时间上限，超时会被直接杀掉。输出很长时先停下来说明。
3. 没让你改文件的任务就别改，只报告。
4. 没人能批准工具调用：要批准的调用会让这条任务直接中断。读文件、查找
   这类只读操作随便用；别的先想想是不是必须。写文件用写文件/编辑工具，
   不要用 shell 重定向（echo/printf/cat > 文件、heredoc）；命令一条一条
   跑，不要用 && ; | 串起来——这些放行规则覆盖不到，会被中断。
5. 最后一段回复就是这条任务的结果，写清楚结论。"""

# grok 的 GROK_HOME（会话记录在它下面的 sessions/）
GROK_HOME = Path(os.environ.get("GROK_HOME") or Path.home() / ".grok")

PERMISSION_MODES = ("default", "acceptEdits", "auto", "dontAsk", "plan")

# 推理强度，传给 --reasoning-effort。CLI 自己的默认是 high，gbatch 默认 medium。
EFFORTS = ("low", "medium", "high", "xhigh")
EFFORT_ALIASES = {"低": "low", "中": "medium", "高": "high", "极高": "xhigh"}
DEFAULT_EFFORT = "medium"

# allowed_tools 里的 Claude 工具名 → grok 规则名。grok 认的工具名只有
# Bash / Read / Edit（Write 是别名）/ Grep（Glob 是别名）/ MCPTool /
# WebFetch / WebSearch，见 22-permissions-and-safety.md「Tool Names」。
# 认不出的名字 grok 自己也是跳过，这里跳过并记 warning。
TOOL_MAP = {
    "Bash": "Bash", "Read": "Read", "Edit": "Edit", "Grep": "Grep",
    "WebFetch": "WebFetch", "WebSearch": "WebSearch",
    "Write": "Edit", "MultiEdit": "Edit", "NotebookEdit": "Edit",
    "Glob": "Grep", "LS": "Read", "NotebookRead": "Read",
}
_TOOL_MAP_CI = {k.lower(): v for k, v in TOOL_MAP.items()}
# 带括号的规则：前缀是这些就原样保留（grok 的写法里 Write(...)、Glob(...)
# 也认）
RULE_PREFIXES = ("Bash", "Read", "Edit", "Write", "Grep", "Glob",
                 "WebFetch", "WebSearch", "MCPTool")

# grok 内部工具名 → 规则名，用来把被拒的调用说成能直接抄进 allowed_tools 的样子
_INTERNAL_TOOL = {
    "write": "Edit", "search_replace": "Edit",
    "run_terminal_command": "Bash", "run_terminal_cmd": "Bash", "monitor": "Bash",
    "read_file": "Read", "list_dir": "Read", "grep": "Grep",
    "web_fetch": "WebFetch", "web_search": "WebSearch",
}
_ARG_KEYS = ("file_path", "target_file", "target_directory", "path",
             "command", "url", "pattern", "tool_name")

# submit 时的静态预检：提示词里像要写文件 / 跑命令，权限却没放开。只提示，
# 不拦——关键词判断免不了误报。
_WANTS_WRITE = re.compile(
    r"写(?!清楚|明|出来)|修改|改成|改掉|创建|新建|删除|删掉|保存|生成.{0,6}文件"
    r"|\b(write|edit|create|modify|save|delete|patch)\b", re.I)
_WANTS_RUN = re.compile(
    r"运行|跑一?下|跑测试|跑通|执行|测试通过|安装"
    r"|\b(run|execute|pytest|unittest|npm|make|pip|install)\b", re.I)

# 记命令行时打码：常见的 key / token 样子
_SECRET = re.compile(
    r"(xai-|sk-|ghp_|gho_|github_pat_|AKIA)[A-Za-z0-9_\-]{8,}"
    r"|((?:api[_-]?key|token|secret|password|passwd|authorization)\s*[:=]\s*)\S+"
    r"|(Bearer\s+)\S+", re.I)


class GBatchError(Exception):
    """参数不对，或者任务不存在。"""


# ----------------------------------------------------------------------
# 权限参数


def _translate_tools(allowed_tools) -> tuple:
    """Claude 的工具名翻成 grok 规则，去重。返回 (规则列表, warnings)。"""
    rules, warnings = [], []
    for raw in allowed_tools or []:
        name = str(raw).strip()
        if not name:
            continue
        if name == "*":
            raise GBatchError("不收 \"*\" 规则：等于全放开（同 bypassPermissions），"
                              "要放开就指定到具体工具")
        if name.startswith("mcp__") or name.startswith("MCPTool("):
            rule = name                      # grok 两种写法都认
        elif "(" in name and name.endswith(")"):
            prefix = name.split("(", 1)[0]
            if prefix not in RULE_PREFIXES:
                warnings.append(f"allowed_tools 里的 {name!r}：grok 不认 {prefix} "
                                f"这类规则，已跳过")
                continue
            rule = name
        elif name.lower() in _TOOL_MAP_CI:
            rule = _TOOL_MAP_CI[name.lower()]
        else:
            warnings.append(f"allowed_tools 里的 {name!r}：grok 没有对应的规则名，"
                            f"已跳过（认得的：{'、'.join(TOOL_MAP)}，或 Bash(...) 这类带参数规则）")
            continue
        if rule not in rules:
            rules.append(rule)
    return rules, warnings


def _effective_rules(permission_mode, allowed_tools) -> tuple:
    """最终传给 --allow 的规则和 warnings。acceptEdits 补 Edit，见模块文档。"""
    rules, warnings = _translate_tools(allowed_tools)
    if permission_mode == "acceptEdits" and "Edit" not in rules:
        rules.append("Edit")
    return rules, warnings


def _grants(permission_mode, rules) -> tuple:
    """(能写文件, 能跑命令)。auto 交给分类器，算放开了。"""
    heads = {r.split("(", 1)[0] for r in rules}
    write = permission_mode == "auto" or bool(heads & {"Edit", "Write"})
    run = permission_mode == "auto" or "Bash" in heads
    return write, run


def _precheck(items, permission_mode, rules) -> list:
    can_write, can_run = _grants(permission_mode, rules)
    out = []
    for i, it in enumerate(items, 1):
        p = it["prompt"]
        if not can_write and _WANTS_WRITE.search(p):
            out.append(f"第 {i} 条看着要写文件，但没放行编辑：传 permission_mode="
                       f"'acceptEdits' 或 allowed_tools 加 'Edit'，不然会在第一次写"
                       f"文件时中断")
        if not can_run and _WANTS_RUN.search(p):
            out.append(f"第 {i} 条看着要跑命令，但没放行 Bash：allowed_tools 加 "
                       f"'Bash' 或具体的 'Bash(python3 *)'，不然除了 ls/cat/git status "
                       f"这类只读命令都会中断")
    return out


def _norm_effort(v, model=None):
    """推理强度归一成 low/medium/high/xhigh；None 或空串返回 None（不传参数）。
    非法值、或 grok-4.5 配 xhigh 报错。"""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    k = str(v).strip().lower()
    k = EFFORT_ALIASES.get(str(v).strip(), k)
    if k not in EFFORTS:
        raise GBatchError(f"effort 只能是 {' / '.join(EFFORTS)}"
                          f"（或中文 {' / '.join(EFFORT_ALIASES)}），"
                          f"None 或空串表示不传，收到：{v!r}")
    if k == "xhigh" and model and str(model).startswith("grok-4.5"):
        raise GBatchError(f"模型 {model} 不支持 effort=xhigh，请用 high 及以下")
    return k


def _mask(s: str) -> str:
    return _SECRET.sub(lambda m: (m.group(2) or m.group(3) or m.group(1) or "") + "***", s)


def _show_cmd(cmd: list) -> list:
    """记进 job.json 的命令行：打码，提示词和 --rules 截短。"""
    out = []
    for i, a in enumerate(cmd):
        prev = cmd[i - 1] if i else ""
        if prev == "--rules" and len(a) > 60:
            a = a[:60] + f"…（共 {len(a)} 字）"
        elif prev == "-p" and len(a) > 300:
            a = a[:300] + f"…（共 {len(a)} 字）"
        out.append(_mask(a))
    return out


# ----------------------------------------------------------------------
# job.json 读写


def _job_dir(job_id: str) -> Path:
    return JOBS / job_id


def _load(job_id: str) -> dict:
    f = _job_dir(job_id) / "job.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise GBatchError(f"没有这个任务：{job_id}") from None


def _save(d: dict) -> None:
    """先写临时文件再改名：查状态的人随时在读。"""
    f = _job_dir(d["id"]) / "job.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, f)


# ----------------------------------------------------------------------
# 对外接口


def submit(tasks, name: str = "", mode: str = "isolated", cwd: str = None,
           model: str = None, permission_mode: str = None,
           allowed_tools=None, timeout: int = TASK_TIMEOUT,
           preamble: bool = True, effort: str = DEFAULT_EFFORT) -> dict:
    """提交一批任务，立刻返回，不等跑完。

    tasks：提示词列表，或 {prompt, outfile} 字典列表。outfile 给了的话，
        那条的最终回复另存一份到这个文件（相对 cwd）。
    mode：isolated 各条独立；share 后一条用 -r 接前一条的会话，前一条
        失败就开新会话。
    cwd：grok 在哪个目录跑。规则同 cbatch：不收 ~、/ 和含凭证的目录。
    model：传给 --model，默认不传（grok 自己的默认）。
    permission_mode：传给 --permission-mode（default / acceptEdits / auto /
        dontAsk / plan），语义见模块文档「权限」。acceptEdits 自动补
        --allow Edit。不收 bypassPermissions。
    allowed_tools：权限规则列表，每条一个 --allow，如 "Bash(git *)"。
        Claude 的工具名会翻成 grok 的（TOOL_MAP），认不出的跳过并记进
        warnings。
    timeout：单条任务的秒数上限。
    effort：推理强度，传给 --reasoning-effort：low / medium / high / xhigh
        （也收 低/中/高/极高），默认 medium。None 或空串不传，用 grok 自己
        的默认（high）。tasks 里的字典可带 "effort" 单独覆盖。非法值直接
        报错；grok-4.5 系列不支持 xhigh。

    返回 {"job_id", "status", "tasks", "dir", "allow", "warnings"}。
    warnings 里有工具名翻译的问题，和「提示词像要写文件/跑命令但没放行」
    的预检提示（只提示，照样提交）。
    """
    job_effort = _norm_effort(effort, model)
    items = []
    for t in tasks:
        if isinstance(t, str) and t.strip():
            items.append({"prompt": t, "outfile": "", "effort": job_effort})
        elif isinstance(t, dict) and t.get("prompt"):
            items.append({"prompt": t["prompt"],
                          "outfile": t.get("outfile", ""),
                          "effort": _norm_effort(t["effort"], model)
                          if "effort" in t else job_effort})
        else:
            raise GBatchError(f"任务要是非空字符串或含 prompt 的字典，收到：{t!r}")

    if not items:
        raise GBatchError("一条任务都没有")
    if len(items) > MAX_TASKS:
        raise GBatchError(f"一次最多 {MAX_TASKS} 条，这次给了 {len(items)} 条。")
    if mode not in ("share", "isolated"):
        raise GBatchError(f"mode 只能是 share 或 isolated，收到：{mode}")
    if permission_mode == "bypassPermissions":
        raise GBatchError("不收 bypassPermissions（就是 --always-approve）：批量任务"
                          "没人看着，要放开就用 allowed_tools 指定到具体规则")
    if permission_mode and permission_mode not in PERMISSION_MODES:
        raise GBatchError(f"permission_mode 只能是 {' / '.join(PERMISSION_MODES)}，"
                          f"收到：{permission_mode}")
    rules, warnings = _effective_rules(permission_mode, allowed_tools)
    warnings += _precheck(items, permission_mode, rules)
    if shutil.which(GROK_BIN) is None:
        raise GBatchError(f"找不到 {GROK_BIN}，Grok Build 装了吗？")

    try:
        cwd = check_workdir(cwd or os.getcwd())
    except UnsafeWorkdirError as e:
        raise GBatchError(f"cwd 不能用：{e}") from None

    now = datetime.now()
    job_id = now.strftime("%Y%m%d-%H%M%S-") + f"{now.microsecond // 1000:03d}" \
        + uuid.uuid4().hex[:4]
    jd = _job_dir(job_id)
    jd.mkdir(parents=True)

    d = {
        "id": job_id, "name": name, "mode": mode, "cwd": cwd,
        "status": "queued", "created": _now(), "started": None,
        "finished": None, "pid": None,
        "options": {"model": model or None, "permission_mode": permission_mode,
                    "allowed_tools": list(allowed_tools or []),
                    "allow": rules,
                    "timeout": int(timeout), "preamble": bool(preamble),
                    "effort": job_effort},
        "warnings": warnings,
        "cmd": None,
        "tasks": [dict(it, status="pending", output="", error="",
                       stop_reason=None, session_id=None, cost_usd=None,
                       turns=None, seconds=None, cmd=None) for it in items],
    }
    # 提示词换成占位，先给个样子；每条实际跑的命令记在 tasks[i].cmd
    d["cmd"] = _show_cmd(_command(d, {"prompt": "<提示词>"}))
    _save(d)

    # 经中间进程起执行器，理由见 cbatch.submit
    subprocess.run([sys.executable, "-m", "tools.gbatch", "_detach", job_id],
                   cwd=str(ROOT), stdin=subprocess.DEVNULL, check=True,
                   env=dict(os.environ, GBATCH_HOME=str(JOBS)))

    return {"job_id": job_id, "status": "queued", "tasks": len(items),
            "dir": str(jd), "allow": rules, "warnings": warnings}


def status(job_id: str, full: bool = False) -> dict:
    """查一个任务的进度和输出。full=False 时每条输出截断到 500 字。"""
    d = _settle(_load(job_id))
    done = sum(t["status"] not in ("pending", "running") for t in d["tasks"])
    d["progress"] = f"{done}/{len(d['tasks'])}"
    if not full:
        for t in d["tasks"]:
            out = t.get("output") or ""
            if len(out) > 500:
                t["output"] = out[:500] + f"…（还有 {len(out) - 500} 字）"
    hint = _hint(d)
    if hint:
        d["hint"] = hint
    return d


def _hint(d: dict) -> str:
    """有任务因要批准被中断时，给出该加的参数。"""
    stuck = [t for t in d["tasks"] if t.get("stop_reason") == "cancelled"
             and t["status"] == "error"]
    if not stuck:
        return ""
    o = d["options"]
    have = list(o.get("allow") or o.get("allowed_tools") or [])
    need = []
    for t in stuck:
        for c in t.get("pending") or []:
            if c["tool"] not in need:
                need.append(c["tool"])
    if not need:                 # 不知道卡在哪，按最常见的给
        need = ["Edit", "Bash"]
    heads = {r.split("(", 1)[0] for r in have}
    add = [n for n in need if n not in have and n.split("(", 1)[0] not in heads]
    if not add:
        # 实测：--allow Bash 也不放行带重定向的串联命令（mkdir && printf … >
        # a.py && python3 a.py），只能让模型换写法
        shelly = any(c["tool"] == "Bash" and re.search(r"[<>`]|\$\(", c["arg"])
                     for t in stuck for c in t.get("pending") or [])
        return (f"第 {', '.join(str(d['tasks'].index(t) + 1) for t in stuck)} 条因工具调用要"
                f"批准被中断，但需要的规则已在 allow 里（{have}）："
                + ("被拦的命令带重定向/命令替换，Bash 规则覆盖不到。重跑时在提示词里写明"
                   "「用写文件工具建文件，命令一条一条跑，不要用 > 或 && 」"
                   if shelly else
                   "多半是 Bash 规则没覆盖到实际命令（链式命令每段都要匹配），"
                   "放宽成 'Bash' 或看 error 里的命令"))
    return (f"第 {', '.join(str(d['tasks'].index(t) + 1) for t in stuck)} 条因工具调用要批准"
            f"被中断。重跑时加 allowed_tools={have + add!r}"
            + ("（Bash 可以收窄成 'Bash(python3 *)' 这类）" if "Bash" in add else ""))


def wait(job_id: str, timeout: int = 300, every: int = 5) -> dict:
    """等一个任务跑完。超时返回当前状态，不报错。"""
    deadline = time.time() + timeout
    while True:
        d = status(job_id)
        if d["status"] not in ("queued", "running"):
            return d
        if time.time() >= deadline:
            d["_note"] = f"等了 {timeout} 秒还在跑，这是中途状态"
            return d
        time.sleep(every)


def jobs(limit: int = 10) -> list:
    """最近的任务（新的在前），每个只给概要。"""
    if not JOBS.is_dir():
        return []
    out = []
    for jd in sorted(JOBS.iterdir(), reverse=True):
        if not (jd / "job.json").is_file():
            continue
        d = _settle(_load(jd.name))
        done = sum(t["status"] not in ("pending", "running") for t in d["tasks"])
        out.append({"id": d["id"], "name": d["name"], "status": d["status"],
                    "progress": f"{done}/{len(d['tasks'])}",
                    "created": d["created"]})
        if len(out) >= limit:
            break
    return out


def cancel(job_id: str) -> dict:
    """取消：整组杀掉执行器和它正在跑的那条 grok，没跑的标成 cancelled。"""
    d = _load(job_id)
    if d["status"] not in ("queued", "running"):
        return {"job_id": job_id, "status": d["status"], "note": "已经结束了"}
    if not d.get("pid"):
        raise GBatchError("执行器还没起来，过几秒再取消")
    (_job_dir(job_id) / "cancel").touch()
    try:
        os.killpg(d["pid"], signal.SIGTERM)
    except (ProcessLookupError, TypeError):
        pass
    for _ in range(20):
        if not _pid_alive(d["pid"]):
            break
        time.sleep(0.1)
    d = _load(job_id)
    d["status"] = "cancelled"
    d["finished"] = _now()
    for t in d["tasks"]:
        if t["status"] in ("pending", "running"):
            t["status"] = "cancelled"
    _save(d)
    return {"job_id": job_id, "status": "cancelled"}


def describe() -> str:
    """人话版的概况：执行端在不在、最近跑了什么。"""
    exe = shutil.which(GROK_BIN)
    lines = [f"执行端：{exe or f'找不到 {GROK_BIN}'}",
             f"任务目录：{JOBS}"]
    js = jobs(5)
    lines.append(f"最近 {len(js)} 个任务" if js else "还没有任务")
    for j in js:
        lines.append(f"  {j['id']}  {j['status']:10} {j['progress']:6} "
                     f"{j['name'][:30]}")
    lines += [
        "",
        "权限参数（grok -p 里要批准的调用会让整条中断，不是只拒那一个）：",
        "  不传            只读工具和 ls/cat/git status 这类只读命令",
        "  acceptEdits     能写文件（自动补 --allow Edit）；跑命令还要 allowed_tools 加 Bash",
        "  dontAsk         只有 allowed_tools 和只读操作，别的直接拒",
        "  auto            分类器判断，不放行的直接失败",
        "  plan            只读",
        "  bypassPermissions 不收；\"*\" 规则也不收",
        "  allowed_tools   每条一个 --allow，例：['Edit', 'Bash(python3 *)', 'Bash(git *)']",
        "",
        "推理强度 effort（--reasoning-effort）：low / medium / high / xhigh，"
        "也收 低/中/高/极高；默认 medium。",
        "  轻任务（查文件、列清单、简单函数）用 low；复杂排查/重构用 high；",
        "  None 或空串 = 不传，用 CLI 自己的默认（high）。grok-4.5 系列不支持 xhigh。",
        "  tasks 里的 {\"prompt\": ..., \"effort\": \"low\"} 可单条覆盖 job 级。",
        "",
        "工具名映射（Claude → grok 规则，其余名字跳过并记 warnings）：",
    ]
    lines += [f"  {k:13} → {v}" for k, v in TOOL_MAP.items() if k != v]
    lines += ["  Bash(...) / Read(...) / Edit(...) / mcp__x__y / MCPTool(...)  原样保留",
              "",
              "每条的原始输出：任务目录/task_<n>.raw.json、task_<n>.stderr.log；"
              "实际命令行在 job.json 的 tasks[n].cmd"]
    return "\n".join(lines)


# ----------------------------------------------------------------------
# 执行器（在后台进程里跑）


def _command(d: dict, t: dict, resume: str = None) -> list:
    o = d["options"]
    cmd = [GROK_BIN, "-p", t["prompt"], "--output-format", "json"]
    if resume:
        cmd += ["-r", resume]
    if o["model"]:
        cmd += ["--model", o["model"]]
    # 任务级 effort 优先；老任务的 job.json 没有这个字段，就不传
    effort = t["effort"] if "effort" in t else o.get("effort")
    if effort:
        cmd += ["--reasoning-effort", effort]
    if o["permission_mode"]:
        cmd += ["--permission-mode", o["permission_mode"]]
    # 老任务的 job.json 没有 allow，退回原样的 allowed_tools
    for rule in o.get("allow", o["allowed_tools"]):
        cmd += ["--allow", rule]
    if o["preamble"]:
        cmd += ["--rules", PREAMBLE]
    return cmd


def _summary(tool: str, args) -> dict:
    """一个工具调用 → {tool: 规则名, arg: 参数摘要}。"""
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {"_": args}
    args = args if isinstance(args, dict) else {}
    rule = _INTERNAL_TOOL.get(tool, tool)
    if tool == "use_tool" and args.get("tool_name"):
        rule = f"MCPTool({args['tool_name']})"
    arg = next((str(args[k]) for k in _ARG_KEYS if args.get(k)), "")
    arg = " ".join(_mask(arg).split())
    return {"tool": rule, "arg": arg[:120] + ("…" if len(arg) > 120 else "")}


def _pending_calls(r: dict, session_id: str) -> tuple:
    """被中断时卡在哪些工具调用上。返回 (调用列表, 从哪读到的)。

    先看 json 输出本身（现在的 grok 不给，留着以后给了能直接用），再读
    会话记录 updates.jsonl，见模块文档。都没有就返回空列表。
    """
    for key in ("permission_denials", "pendingToolCalls", "pending_tool_calls"):
        xs = r.get(key)
        if isinstance(xs, list) and xs:
            return [_summary(x.get("tool_name") or x.get("toolName") or x.get("name", "?"),
                             x.get("tool_input") or x.get("rawInput") or x.get("arguments"))
                    for x in xs if isinstance(x, dict)], "json"
    if not session_id:
        return [], ""
    files = list((GROK_HOME / "sessions").glob(f"*/{session_id}/updates.jsonl"))
    if not files:
        return [], ""
    calls, failed = {}, []
    try:
        lines = files[0].read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], ""
    for line in lines:
        try:
            u = json.loads(line)["params"]["update"]
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        cid = u.get("toolCallId")
        if u.get("sessionUpdate") == "tool_call" and cid:
            calls[cid] = (u.get("title") or "?", u.get("rawInput"))
        elif u.get("sessionUpdate") == "tool_call_update" and u.get("status") == "failed":
            text = json.dumps(u.get("content"), ensure_ascii=False)
            if "cancel" in text.lower() and cid not in failed:
                failed.append(cid)
    return [_summary(*calls[c]) for c in failed if c in calls], "session"


def _run_one(d: dict, t: dict, resume: str = None, n: int = 1) -> None:
    """跑一条，结果写回 t。不抛异常：一条坏了记下来，接着跑下一条。

    grok 的 stdout / stderr 原样存到任务目录的 task_<n>.raw.json /
    task_<n>.stderr.log，命令行记进 t["cmd"]。
    """
    jd = _job_dir(d["id"])
    cmd = _command(d, t, resume)
    t["cmd"] = _show_cmd(cmd)

    def keep(out, err):
        for name, s in ((f"task_{n}.raw.json", out), (f"task_{n}.stderr.log", err)):
            if isinstance(s, bytes):
                s = s.decode("utf-8", "replace")
            try:
                (jd / name).write_text(s or "", encoding="utf-8")
            except OSError:
                pass

    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=d["cwd"],
                           env=_child_env(), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True,
                           timeout=d["options"]["timeout"])
    except subprocess.TimeoutExpired as e:
        keep(e.stdout, e.stderr)
        t.update(status="timeout", seconds=round(time.time() - t0, 1),
                 error=f"超过 {d['options']['timeout']} 秒，已杀掉")
        return
    t["seconds"] = round(time.time() - t0, 1)
    keep(p.stdout, p.stderr)

    try:
        r = json.loads(p.stdout)
    except json.JSONDecodeError:
        t.update(status="error", output=p.stdout,
                 error=(p.stderr or f"退出码 {p.returncode}，输出不是 JSON").strip())
        return

    stop = r.get("stopReason")
    t.update(output=r.get("text") or "", session_id=r.get("sessionId"),
             cost_usd=r.get("total_cost_usd"), turns=r.get("num_turns"),
             stop_reason=stop)
    if p.returncode != 0:
        t.update(status="error", error=(f"退出码 {p.returncode} " + p.stderr).strip())
    elif stop == "cancelled":
        # 见模块文档「要批准的工具调用会让整条停下」
        pending, src = _pending_calls(r, t["session_id"])
        if pending:
            t["pending"] = pending
            first = pending[0]
            what = f"需要批准：{first['tool']} {first['arg']}".strip()
            if len(pending) > 1:
                what += "；同一批没执行的还有：" + "，".join(
                    f"{c['tool']} {c['arg']}".strip() for c in pending[1:5])
                if len(pending) > 5:
                    what += f" 等 {len(pending)} 个"
        else:
            what = ("多半是某个工具调用要批准、没人批。拿不到卡在哪个调用："
                    "json 输出里没有这类信息，会话记录里也没找到")
        t.update(status="error",
                 error=f"回合被中断（stopReason=cancelled）。{what}。output 只是它"
                       "打算做的事，没做成。要写文件或跑命令，传 permission_mode="
                       "'acceptEdits' 或 allowed_tools（看 status 的 hint）")
    elif stop != "end_turn":
        t.update(status="error", error=f"没有正常结束（stopReason={stop}）")
    else:
        t["status"] = "done"

    if t["outfile"] and t["output"] and t["status"] == "done":
        f = Path(d["cwd"]) / t["outfile"]
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(t["output"], encoding="utf-8")
        except OSError as e:
            t["error"] = (t["error"] + f" 写 outfile 失败：{e}").strip()


def _detach(job_id: str) -> None:
    """起执行器然后自己退出，见 cbatch._detach。"""
    with open(_job_dir(job_id) / "runner.log", "ab") as log:
        subprocess.Popen([sys.executable, "-m", "tools.gbatch", "_run", job_id],
                         cwd=str(ROOT), stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)


def _run(job_id: str) -> None:
    jd = _job_dir(job_id)
    cancelled = lambda: (jd / "cancel").exists()   # noqa: E731

    d = _load(job_id)
    d.update(status="running", started=_now(), pid=os.getpid())
    _save(d)

    prev_session = None
    for n, t in enumerate(d["tasks"], 1):
        if cancelled():
            break
        t["status"] = "running"
        _save(d)
        resume = prev_session if d["mode"] == "share" else None
        _run_one(d, t, resume, n)
        prev_session = t["session_id"] if t["status"] == "done" else None
        if cancelled():
            return          # cancel() 负责收尾，这里再写会盖掉它
        _save(d)

    if cancelled():
        return
    d["finished"] = _now()
    st = {t["status"] for t in d["tasks"]}
    d["status"] = "done" if st == {"done"} else "partial" if "done" in st else "failed"
    _save(d)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "_run":
        _run(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "_detach":
        _detach(sys.argv[2])
    else:
        print(describe())
