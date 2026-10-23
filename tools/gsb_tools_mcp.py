# -*- coding: utf-8 -*-
"""gsbatch 给 goose 任务挂的小 MCP 服务器（stdio，纯标准库）。

goose 1.55 每轮只执行一个工具，所以这里的工具都一次做完多步：

- read_files：一次读多个文件（可带行号范围、可用 glob），带行号返回。
- run_wait：跑一条 shell 命令并阻塞等它结束，返回退出码、用时、输出末尾。
- wait_pid：等一个已经在跑的进程结束（比如后台跑的回归），返回 log 末尾。
- probe / probe_wait（GSB_PROBE=1 时才有）：把大量阅读 / 对照 / 调研派给
  Codex CLI（codex exec，默认 gpt-6-luna，强制 -s read-only），只收回最后一条
  回复。后台跑、可并行；单次调用最多阻塞 GSB_MAX_BLOCK 秒，没跑完返回
  still_running + probe_id，再调 probe_wait 接着等。
- review / review_wait（GSB_REVIEW=1 时才有）：同一套 codex 只读执行，派一个审查员
  按任务书独立审查改动（工作区 diff 或 base..HEAD），按固定格式交回「通过 / 有问题」
  和问题清单。codex 用 ~/.codex/auth.json
  的 ChatGPT 登录（靠 HOME），不需要也不放行任何密钥环境变量。

goose 对 stdio 扩展的单次工具调用有超时（--with-extension 固定 300 秒，
命令行改不了），所以单次调用最多阻塞 GSB_MAX_BLOCK 秒（默认 270）。
命令没跑完就返回 still_running + pid + log_path，进程继续跑，
模型再调 wait_pid 接着等；命令自己的 timeout_secs 到了由后台线程杀进程组。

安全：启动时就把名字像凭证的环境变量（*TOKEN*、*API_KEY* 等）从本进程环境
里删掉，跑的命令拿到的是干净环境。
"""

import glob as _glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

_SECRET_NAME = re.compile(r"TOKEN|SECRET|PASSW|API_?KEY|ACCESS_KEY|PRIVATE_KEY|CREDENTIAL", re.I)
for _k in [k for k in os.environ if _SECRET_NAME.search(k)]:
    os.environ.pop(_k, None)

SERVER = {"name": "gsb_tools", "version": "1.0"}
MAX_BLOCK = max(1, int(os.environ.get("GSB_MAX_BLOCK") or 270))
LOG_DIR = os.environ.get("GSB_LOG_DIR") or "/tmp/gsb_tools"
MAX_FILES = 50
DEF_PER_FILE, DEF_TOTAL = 60000, 200000
MAX_TIMEOUT = 3600
PROBE_ON = os.environ.get("GSB_PROBE") == "1"
REVIEW_ON = os.environ.get("GSB_REVIEW") == "1"
PROBE_MODEL = os.environ.get("GSB_PROBE_MODEL") or "gpt-6-luna"
PROBE_EFFORTS = ("low", "medium", "high")
PROBE_MAX_TIMEOUT = 1800
PROBE_MAX_REPLY = 30000
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,79}$")
PROBE_PREAMBLE = """你是一个只读探针，另一个 agent 把阅读 / 对照 / 调研的活派给你，只收你的结论。规则：
1. 只读：不创建、修改、删除任何文件，不用 git 的写操作（commit / checkout / reset / stash / push 等），不装东西。
2. 结论要带依据：文件路径和行号（path:line）。
3. 只交回要求的内容和格式，不复述过程。
4. 你的最后一条回复就是交付结果。

任务：
"""

_REF_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./~^@{}\-]{0,199}$")
REVIEW_PROMPT = """你是代码审查员，独立审查另一个 agent 刚做完的改动，结论给它在 commit / push、写最终报告之前用。
只读：可以在仓库里跑只读命令（git status / diff / log / show、rg、cat、只读测试），不创建、修改、删除任何文件，
不用 git 写操作（add / commit / checkout / reset / stash / push 等），不装东西；测试要写文件跑不了就说明，不要绕。

仓库：{wd}
{task}
审查范围：{scope}
{report}{extra}
必查：
(a) 任务书里的每个要求有没有做到，没做到的逐条列出；
(b) 有没有违反任务书的规则：改了不该改的文件、改了只读目录、提交或推送了不该提交的东西、调了不该调的模型等；
(c) git status 里有没有不属于本任务的改动混进暂存区或提交；
(d) 有报告草稿时，核对里面的数字和结论是否和实际一致（计数用命令实际数，不要估）；
(e) 明显的 bug 或回归风险。
不提风格类小问题，除非影响正确性。结论要有依据（文件:行号、命令输出）。

最后一条回复就是交付结果，按这个格式：
结论：通过 / 有问题（二选一；有阻断或应修就是有问题）
问题清单：（没有写「无」）
- [阻断 / 应修 / 建议] 文件:行号 — 问题说明。依据：……
必查项：
(a) ……
(b) ……
(c) ……
(d) ……（没有报告草稿写「无报告草稿」）
(e) ……
{status}"""

# ----------------------------------------------------------------------
# read_files


def _resolve(p, cwd=None):
    p = os.path.expanduser(str(p))
    return p if os.path.isabs(p) else os.path.join(cwd or os.getcwd(), p)


def _norm_spec(it):
    if isinstance(it, str):
        return {"path": it, "start": None, "end": None}
    if isinstance(it, dict) and it.get("path"):
        def num(v):
            if v in (None, ""):
                return None
            return int(v)
        return {"path": str(it["path"]), "start": num(it.get("start")), "end": num(it.get("end"))}
    raise ValueError(f"files 里每项要是路径字符串或 {{path, start, end}}，收到：{it!r}")


def _read_one(path, start, end, cap):
    """返回 (标题, 正文, 是否截断)。出错抛 OSError/ValueError。"""
    if not os.path.exists(path):
        raise ValueError("不存在")
    if os.path.isdir(path):
        raise ValueError("是目录，不是文件")
    with open(path, "rb") as f:
        if b"\0" in f.read(8192):
            raise ValueError(f"二进制文件（{os.path.getsize(path)} 字节），不读")
    s = max(1, start or 1)
    e = end if end and end > 0 else None
    if e is not None and e < s:
        raise ValueError(f"行号范围不对：start={start} end={end}")
    big = os.path.getsize(path) > 50_000_000
    out, used, total, cut, last = [], 0, 0, False, None
    with open(path, "r", encoding="utf-8", errors="replace", newline=None) as f:
        for n, line in enumerate(f, 1):
            total = n
            if e is not None and n > e:
                if big:
                    break
                continue
            if n < s or cut:
                continue
            row = f"{n}\t{line.rstrip(chr(10)).rstrip(chr(13))}\n"
            if used + len(row) > cap:
                if not out:                      # 一行就超了：截这一行
                    out.append(row[:cap] + "…\n")
                    used += cap
                    last = n
                else:
                    last = n - 1
                cut = True
                continue
            out.append(row)
            used += len(row)
    shown_end = (last if cut else min(e, total) if e else total)
    if s > total and total > 0:
        head = f"{path}（共 {total} 行，start={s} 超出文件末尾）"
    elif total == 0:
        head = f"{path}（空文件）"
    else:
        head = f"{path}（第 {s}-{shown_end} 行，共 {total} 行）"
    body = "".join(out)
    if cut:
        body += f"…（超出单文件上限 {cap} 字，截断在第 {shown_end} 行；要看后面用 start={shown_end + 1}）\n"
    return head, body, cut


def read_files(files, max_chars_per_file=DEF_PER_FILE, max_total_chars=DEF_TOTAL, cwd=None):
    if isinstance(files, (str, dict)):
        files = [files]
    if not isinstance(files, list) or not files:
        raise ValueError("files 要是非空列表")
    per = max(200, int(max_chars_per_file or DEF_PER_FILE))
    total_cap = max(200, int(max_total_chars or DEF_TOTAL))
    specs = []
    for it in files:
        sp = _norm_spec(it)
        p = _resolve(sp["path"], cwd)
        if any(c in sp["path"] for c in "*?["):
            hits = sorted(h for h in _glob.glob(p, recursive=True) if os.path.isfile(h))
            if not hits:
                specs.append(dict(sp, path=p, err="glob 没匹配到文件"))
            for h in hits:
                specs.append(dict(sp, path=h))
        else:
            specs.append(dict(sp, path=p))
    parts, used, n_ok, n_err, skipped = [], 0, 0, 0, []
    if len(specs) > MAX_FILES:
        skipped = [s["path"] for s in specs[MAX_FILES:]]
        specs = specs[:MAX_FILES]
    for sp in specs:
        left = total_cap - used
        if left < 200:
            skipped.append(sp["path"])
            continue
        if sp.get("err"):
            parts.append(f"===== {sp['path']}：错误：{sp['err']} =====\n")
            n_err += 1
            continue
        try:
            head, body, _ = _read_one(sp["path"], sp["start"], sp["end"], min(per, left))
            parts.append(f"===== {head} =====\n{body}")
            used += len(body)
            n_ok += 1
        except (OSError, ValueError) as e:
            parts.append(f"===== {sp['path']}：错误：{e} =====\n")
            n_err += 1
    summary = f"读了 {n_ok} 个，出错 {n_err} 个，共 {used} 字"
    if skipped:
        summary += f"；超出总上限 {total_cap} 字或 {MAX_FILES} 个文件，没读：" + ", ".join(skipped[:20])
        if len(skipped) > 20:
            summary += f" 等 {len(skipped)} 个"
    return "\n".join(parts) + f"\n[{summary}]"


# ----------------------------------------------------------------------
# run_wait / wait_pid

_PROCS = {}          # pid -> {"p": Popen, "t0", "deadline", "log", "cmd", "killed"}
_PLOCK = threading.Lock()


def _killpg(pid):
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    for _ in range(20):
        time.sleep(0.1)
        try:
            os.killpg(pid, 0)
        except (ProcessLookupError, PermissionError):
            return
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _tail(path, n):
    n = max(1, min(int(n or 60), 2000))
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 400_000))
            data = f.read().decode("utf-8", "replace")
    except OSError as e:
        return f"（读不到 log：{e}）"
    lines = data.splitlines()
    t = lines[-n:]
    head = f"（输出共 {size} 字节，下面是末尾 {len(t)} 行）\n" if len(lines) > n or size > 400_000 else ""
    s = head + "\n".join(t)
    return s[-60000:]


def _watchdog(pid):
    """命令自己的 timeout 到了就杀进程组（单次调用返回后也管用）。"""
    with _PLOCK:
        r = _PROCS.get(pid)
    if not r:
        return
    while r["p"].poll() is None:
        if time.time() >= r["deadline"]:
            r["killed"] = True
            _killpg(pid)
            r["p"].wait()
            return
        time.sleep(0.5)


def _wait_own(pid, block, tail_lines, cancel):
    r = _PROCS[pid]
    end = time.time() + block
    while r["p"].poll() is None and time.time() < end and not cancel.is_set():
        time.sleep(0.2)
    rc = r["p"].poll()
    el = round(time.time() - r["t0"], 1)
    if rc is None:
        left = round(r["deadline"] - time.time())
        return (f"状态：still_running（还在跑，本次已等 {block} 秒，单次调用最多等 {MAX_BLOCK} 秒）\n"
                f"pid：{pid}\nlog_path：{r['log']}\n已用时：{el} 秒，离命令超时还有 {left} 秒\n"
                f"接着等：调 wait_pid(pid={pid}, log_path=\"{r['log']}\")，不要用 sleep\n"
                f"--- 输出末尾 ---\n{_tail(r['log'], min(tail_lines, 20))}")
    st = "timeout（超过 timeout_secs，已杀掉整个进程组）" if r["killed"] else "finished"
    return (f"状态：{st}\n退出码：{rc}\n用时：{el} 秒\nlog_path：{r['log']}\n"
            f"--- 输出末尾 ---\n{_tail(r['log'], tail_lines)}")


def run_wait(command, cwd=None, timeout_secs=900, tail_lines=60, log_path=None, _cancel=None):
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command 要是非空字符串")
    to = int(timeout_secs or 900)
    if not 1 <= to <= MAX_TIMEOUT:
        raise ValueError(f"timeout_secs 要在 1~{MAX_TIMEOUT}")
    wd = _resolve(cwd) if cwd else os.getcwd()
    if not os.path.isdir(wd):
        raise ValueError(f"cwd 不是目录：{wd}")
    if log_path:
        log = _resolve(log_path)
    else:
        os.makedirs(LOG_DIR, exist_ok=True)
        log = os.path.join(LOG_DIR, f"run_{time.strftime('%Y%m%d-%H%M%S')}_{os.getpid()}_{int(time.time()*1000)%100000}.log")
    os.makedirs(os.path.dirname(log) or ".", exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not _SECRET_NAME.search(k)}
    with open(log, "wb") as lf:
        p = subprocess.Popen(["bash", "-c", command], cwd=wd, env=env, stdin=subprocess.DEVNULL,
                             stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    t0 = time.time()
    with _PLOCK:
        _PROCS[p.pid] = {"p": p, "t0": t0, "deadline": t0 + to, "log": log, "cmd": command,
                         "killed": False}
    threading.Thread(target=_watchdog, args=(p.pid,), daemon=True).start()
    return _wait_own(p.pid, min(to + 5, MAX_BLOCK), tail_lines, _cancel or threading.Event())


def _pid_state(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            s = f.read()
        return s[s.rindex(")") + 2]
    except (OSError, ValueError):
        return None


def wait_pid(pid, log_path=None, timeout_secs=None, tail_lines=60, _cancel=None):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        raise ValueError("pid 要是整数") from None
    if pid <= 1:
        raise ValueError("pid 不对")
    block = min(int(timeout_secs or MAX_BLOCK), MAX_BLOCK)
    cancel = _cancel or threading.Event()
    with _PLOCK:
        own = pid in _PROCS
    if own:
        r = _wait_own(pid, block, tail_lines, cancel)
        if log_path and _resolve(log_path) != _PROCS[pid]["log"]:
            r += f"\n--- {log_path} 末尾 ---\n{_tail(_resolve(log_path), tail_lines)}"
        return r
    t0 = time.time()
    st = _pid_state(pid)
    if st is None:
        res = f"状态：finished（进程 {pid} 不存在，可能早就结束了；拿不到退出码）"
    else:
        while time.time() - t0 < block and not cancel.is_set():
            st = _pid_state(pid)
            if st is None or st == "Z":
                break
            time.sleep(0.5)
        el = round(time.time() - t0, 1)
        if st is None or st == "Z":
            res = f"状态：finished（进程 {pid} 已结束，等了 {el} 秒；不是本工具起的，拿不到退出码）"
        else:
            res = (f"状态：still_running（进程 {pid} 还在跑，本次等了 {el} 秒，单次最多等 {MAX_BLOCK} 秒）\n"
                   f"接着等就再调一次 wait_pid，不要用 sleep")
    if log_path:
        res += f"\nlog_path：{_resolve(log_path)}\n--- 输出末尾 ---\n{_tail(_resolve(log_path), tail_lines)}"
    return res


# ----------------------------------------------------------------------
# probe / probe_wait（派给 codex exec 的只读探针）

_PROBES = {}         # probe_id -> {...}
_PSEQ = [0]


def _codex_bin():
    return os.environ.get("GSB_CODEX_BIN") or shutil.which("codex")


PROBE_RETRY_WAITS = tuple(int(x) for x in os.environ.get("GSB_PROBE_RETRY_WAITS", "20,40,60,90,120").split(",") if x.strip())
_CAPACITY_RE = re.compile(r"at capacity|rate.?limit|429 Too Many|temporarily unavailable", re.I)


def _probe_watchdog(pid):
    """盯着探针：到点杀进程组；模型满载 / 限流这类临时错误在超时前自动重试几次。"""
    r = _PROBES[pid]
    while True:
        while r["p"].poll() is None:
            if time.time() >= r["deadline"]:
                r["killed"] = True
                _killpg(r["p"].pid)
                r["p"].wait()
                break
            time.sleep(0.5)
        if r["killed"] or r["p"].returncode == 0 or r["retries"] >= len(PROBE_RETRY_WAITS):
            break
        if not _CAPACITY_RE.search(_tail(r["log"], 15)):
            break
        w = PROBE_RETRY_WAITS[r["retries"]]
        if time.time() + w + 30 >= r["deadline"]:
            break
        r["retries"] += 1
        with open(r["log"], "ab") as lf:
            lf.write(f"\n[gsb_tools] 临时错误，{w} 秒后第 {r['retries']} 次重试\n".encode())
        end = time.time() + w
        while time.time() < end and not r["stop"]:
            time.sleep(0.5)
        if r["stop"]:
            break
        r["p"] = r["launch"]()
    r["t1"] = time.time()


def _codex_opts(effort, timeout_secs, model, cwd):
    eff = str(effort or "medium").strip().lower()
    if eff not in PROBE_EFFORTS:
        raise ValueError(f"effort 只能是 {' / '.join(PROBE_EFFORTS)}，收到：{effort!r}")
    to = int(timeout_secs or 900)
    if not 1 <= to <= PROBE_MAX_TIMEOUT:
        raise ValueError(f"timeout_secs 要在 1~{PROBE_MAX_TIMEOUT}")
    m = str(model or PROBE_MODEL).strip()
    if not _MODEL_RE.match(m):
        raise ValueError(f"model 不对：{model!r}")
    wd = _resolve(cwd) if cwd else os.getcwd()
    if not os.path.isdir(wd):
        raise ValueError(f"cwd 不是目录：{wd}")
    exe = _codex_bin()
    if not exe:
        raise ValueError("找不到 codex（PATH 里没有）")
    return eff, to, m, wd, exe


def _codex_start(kind, prompt, eff, to, m, wd, exe):
    """后台起一个 codex exec（强制只读），登记到 _PROBES，返回 id。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    with _PLOCK:
        _PSEQ[0] += 1
        pid_ = f"{kind[0]}{_PSEQ[0]}-{os.getpid()}-{int(time.time() * 1000) % 100000}"
    base = os.path.join(LOG_DIR, f"{kind}_{time.strftime('%Y%m%d-%H%M%S')}_{pid_}")
    log, out, prompt_f = base + ".log", base + ".reply.txt", base + ".prompt.txt"
    with open(prompt_f, "w", encoding="utf-8") as f:
        f.write(prompt)
    # 固定只读；不带任何 --dangerously* / --approve-for-me / workspace-write
    cmd = [exe, "exec", "-m", m, "-s", "read-only", "--skip-git-repo-check", "--color", "never",
           "-c", f"model_reasoning_effort={eff}", "-C", wd, "-o", out, "-"]
    env = {k: v for k, v in os.environ.items() if not _SECRET_NAME.search(k)}
    open(log, "wb").close()

    def launch():
        with open(prompt_f, "rb") as pin, open(log, "ab") as lf:
            return subprocess.Popen(cmd, cwd=wd, env=env, stdin=pin, stdout=lf,
                                    stderr=subprocess.STDOUT, start_new_session=True)
    p = launch()
    t0 = time.time()
    with _PLOCK:
        _PROBES[pid_] = {"p": p, "t0": t0, "t1": None, "deadline": t0 + to, "log": log,
                         "out": out, "killed": False, "model": m, "effort": eff,
                         "delivered": False, "timeout": to, "retries": 0,
                         "stop": False, "launch": launch, "kind": kind}
    threading.Thread(target=_probe_watchdog, args=(pid_,), daemon=True).start()
    return pid_


def probe(instructions, cwd=None, effort="medium", timeout_secs=900, wait=True, model=None,
          _cancel=None):
    if not isinstance(instructions, str) or not instructions.strip():
        raise ValueError("instructions 要是非空字符串：写清楚探针要做什么、交回什么格式")
    eff, to, m, wd, exe = _codex_opts(effort, timeout_secs, model, cwd)
    pid_ = _codex_start("probe", PROBE_PREAMBLE + instructions.strip() + "\n", eff, to, m, wd, exe)
    if not wait:
        return (f"probe_id：{pid_}\n状态：started（后台跑，模型 {m}，强度 {eff}，超时 {to} 秒）\n"
                f"派完别的探针后用 probe_wait(probe_ids=[...]) 一起等结果")
    return probe_wait([pid_], _cancel=_cancel)


def _git(wd, *args):
    try:
        r = subprocess.run(["git", "-C", wd, *args], capture_output=True, text=True, timeout=30,
                           env={k: v for k, v in os.environ.items() if not _SECRET_NAME.search(k)},
                           stdin=subprocess.DEVNULL)
        return r.returncode, r.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def _existing_file(p, wd, what):
    if p in (None, ""):
        return None
    if not isinstance(p, str):
        raise ValueError(f"{what} 要是路径字符串")
    f = os.path.normpath(_resolve(p, wd))
    if not os.path.isfile(f):
        raise ValueError(f"{what} 不存在或不是文件：{f}")
    return f


def review(task_file=None, instructions=None, cwd=None, base=None, report_file=None,
           effort="medium", timeout_secs=900, wait=True, model=None, _cancel=None):
    if instructions is not None and not isinstance(instructions, str):
        raise ValueError("instructions 要是字符串")
    extra = (instructions or "").strip()
    eff, to, m, wd, exe = _codex_opts(effort, timeout_secs, model, cwd)
    tf = _existing_file(task_file, wd, "task_file")
    rf = _existing_file(report_file, wd, "report_file")
    if not tf and not extra:
        raise ValueError("task_file 和 instructions 至少给一个：审查员要知道任务要求")
    rc, top = _git(wd, "rev-parse", "--show-toplevel")
    is_git = rc == 0
    if base not in (None, ""):
        base = str(base).strip()
        if not _REF_RE.match(base) or ".." in base:
            raise ValueError(f"base 要是一个 git 提交 / 分支 / tag（不要写 a..b），收到：{base!r}")
        if not is_git:
            raise ValueError(f"cwd 不是 git 仓库，不能用 base：{wd}")
        if _git(wd, "rev-parse", "--verify", "--quiet", base + "^{commit}")[0] != 0:
            raise ValueError(f"base 在仓库里找不到：{base!r}")
        scope = (f"从 {base} 到 HEAD 的提交（git log / git diff {base}..HEAD）"
                 "加上还没提交的改动（git diff HEAD，含暂存区）和未跟踪文件（git status --porcelain）")
    elif is_git:
        base = None
        scope = "工作区相对 HEAD 的未提交改动（git diff HEAD，含暂存区；git diff --cached 看暂存区）和未跟踪文件（git status --porcelain）"
    else:
        base = None
        scope = "cwd 不是 git 仓库：按任务书直接核对相关文件"
    status = ""
    if is_git:
        st = _git(wd, "status", "--short", "--branch")[1].splitlines()
        if len(st) > 80:
            st = st[:80] + [f"…（共 {len(st)} 行）"]
        status = ("\n派审查时的 git status --short --branch（供对照，以你自己跑的为准）：\n"
                  + ("\n".join(st) or "（干净）") + "\n")
    prompt = REVIEW_PROMPT.format(
        wd=wd,
        task=(f"任务书：{tf}（先完整读一遍，逐条对照）" if tf else "任务书：无，要求见下面「补充说明」"),
        scope=scope,
        report=(f"报告草稿：{rf}（逐条核对里面的说法和数字）\n" if rf else "报告草稿：无\n"),
        extra=(f"补充说明（主任务写的：做了什么、要特别核对的点）：\n{extra}\n" if extra else ""),
        status=status)
    pid_ = _codex_start("review", prompt, eff, to, m, wd, exe)
    r = _PROBES[pid_]
    r.update(task_file=tf, report_file=rf, base=base)
    if not wait:
        return (f"review_id：{pid_}\n状态：started（后台审查，模型 {m}，强度 {eff}，超时 {to} 秒）\n"
                f"用 review_wait(review_ids=[\"{pid_}\"]) 等结论")
    return probe_wait([pid_], _cancel=_cancel, _tool="review_wait", _arg="review_ids")


REVIEW_NOTICE = "以下为初步审查意见，请逐条自行核实后再处理。"
_SRC_RE = re.compile(r"(?:[\w.\-]*/)*[\w\-]+\.\w+(?:[:：]\s*L?\d+|#L\d+)|(?:[\w.\-]*/)+[\w.\-]+[:：]\d+")
_ITEM_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)、])\s*(?:\*\*)?\s*[\[【]\s*(阻断|应修|建议)\s*[\]】]")


def _mark_unsourced(reply):
    """问题清单里没有 文件:行号 出处的条目，行尾标「无出处，低可信」。"""
    out, n = [], 0
    for ln in reply.splitlines():
        if _ITEM_RE.match(ln) and not _SRC_RE.search(ln):
            ln += "　【无出处，低可信】"
            n += 1
        out.append(ln)
    return "\n".join(out), n


def _probe_tokens(log):
    try:
        with open(log, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 200000))
            t = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    m = re.findall(r"tokens used\s*:?\s*\n?\s*([\d,]+)", t, re.I)
    if not m:
        return None
    n = [int(x.replace(",", "")) for x in m]
    # 自动重试过的话，把每次的都加上
    return f"{sum(n):,}" + (f"（{len(n)} 次运行合计）" if len(n) > 1 else "")


def _probe_report(pid_):
    r = _PROBES[pid_]
    rc = r["p"].poll()
    now = r["t1"] or time.time()
    el = round(now - r["t0"], 1)
    kind = r.get("kind", "probe")
    head = f"===== {kind}_id：{pid_}（{r['model']} / {r['effort']}）"
    if r["t1"] is None:
        left = round(r["deadline"] - time.time())
        return f"{head} =====\n状态：still_running（已用时 {el} 秒，离超时 {left} 秒）\n", False
    tok = _probe_tokens(r["log"])
    try:
        with open(r["out"], encoding="utf-8", errors="replace") as f:
            reply = f.read().strip()
    except OSError:
        reply = ""
    if r["killed"]:
        st = f"timeout（超过 {r['timeout']} 秒，已杀掉进程组）"
    elif rc == 0 and reply:
        st = "done"
    else:
        st = f"failed（退出码 {rc}）"
    lines = [f"{head} =====", f"状态：{st}", f"用时：{el} 秒"]
    if r["retries"]:
        lines.append(f"（模型临时满载 / 限流，自动重试了 {r['retries']} 次）")
    if tok:
        lines.append(f"tokens used：{tok}")
    if r["delivered"] and st == "done":
        lines.append(f"（结论前面已经返回过，全文在 {r['out']}）")
        return "\n".join(lines) + "\n", True
    r["delivered"] = True
    if reply:
        if len(reply) > PROBE_MAX_REPLY:
            reply = reply[:PROBE_MAX_REPLY] + f"\n…（截断，共 {len(reply)} 字，全文在 {r['out']}）"
        if kind == "review":
            reply, nsrc = _mark_unsourced(reply)
            v = re.search(r"结论[：:]\s*\**\s*(通过|有问题)", reply)
            nb = len(re.findall(r"\[\s*阻断\s*\]|【\s*阻断\s*】", reply))
            ns = len(re.findall(r"\[\s*应修\s*\]|【\s*应修\s*】", reply))
            lines.insert(0, REVIEW_NOTICE)
            lines.append(f"初步审查结论：{v.group(1) if v else '没按格式给出（看下面原文）'}"
                         f"（阻断 {nb} 条，应修 {ns} 条" + (f"，其中 {nsrc} 条无出处、低可信" if nsrc else "")
                         + "）——只是线索，不是定论")
        lines += ["--- 初步审查意见（原文）---" if kind == "review" else "--- 探针的最终回复 ---", reply]
    if st != "done":
        if kind == "review":
            lines.insert(1, "初步审查没完成：过几分钟再调一次 review；还是不行就自己逐条核对，并在报告里写明「未经初步审查」及原因。")
        lines += [f"--- log 末尾（{r['log']}）---", _tail(r["log"], 40)]
    return "\n".join(lines) + "\n", True


def probe_wait(probe_ids, timeout_secs=None, _cancel=None, _tool="probe_wait", _arg="probe_ids"):
    if isinstance(probe_ids, str):
        probe_ids = [x.strip() for x in probe_ids.split(",") if x.strip()]
    if not isinstance(probe_ids, list) or not probe_ids:
        raise ValueError(f"{_arg} 要是非空列表")
    ids = [str(x) for x in probe_ids]
    bad = [x for x in ids if x not in _PROBES]
    block = min(int(timeout_secs or MAX_BLOCK), MAX_BLOCK)
    cancel = _cancel or threading.Event()
    end = time.time() + block
    live = [x for x in ids if x in _PROBES]
    while time.time() < end and not cancel.is_set():
        if all(_PROBES[x]["t1"] is not None for x in live):
            break
        time.sleep(0.3)
    parts, running = [], []
    for x in live:
        txt, fin = _probe_report(x)
        parts.append(txt)
        if not fin:
            running.append(x)
    for x in bad:
        parts.append(f"===== id：{x} =====\n错误：没有这个 id（只认本会话里 probe / review 返回的 id）\n")
    if running:
        parts.append(f"[{len(running)} 个还在跑（本次最多等 {MAX_BLOCK} 秒）：再调 "
                     f"{_tool}({_arg}={json.dumps(running)}) 接着等，不要 sleep]")
    return "\n".join(parts)


# ----------------------------------------------------------------------
# MCP（JSON-RPC 2.0 over stdio，一行一条）

TOOLS = [
    {"name": "read_files",
     "description": ("一次读多个文件（或同一文件的多段），带行号返回。读多个文件、多段代码时用它一次读完，"
                     "不要用 shell 的 cat/sed/head 分几次读。files 每项是路径字符串（读整个文件）或 "
                     "{path, start, end}（行号从 1 开始，含首尾）。路径可用 glob（如 src/**/*.py）。"
                     "相对路径按任务工作目录。出错的文件单独标出，不影响其他文件。"),
     "inputSchema": {"type": "object", "properties": {
         "files": {"type": "array", "description": "路径字符串，或 {path, start, end}",
                   "items": {"anyOf": [{"type": "string"}, {"type": "object", "properties": {
                       "path": {"type": "string"}, "start": {"type": "integer"},
                       "end": {"type": "integer"}}, "required": ["path"]}]}},
         "max_chars_per_file": {"type": "integer", "description": f"单文件字数上限，默认 {DEF_PER_FILE}"},
         "max_total_chars": {"type": "integer", "description": f"总字数上限，默认 {DEF_TOTAL}"}},
         "required": ["files"]}},
    {"name": "run_wait",
     "description": ("跑一条 shell 命令（bash -c）并阻塞等它结束，返回退出码、用时、输出末尾 N 行；完整输出写到 "
                     "log_path。跑测试、构建等长命令用它，不要放后台再用 sleep 轮询。单次调用最多阻塞 "
                     f"{MAX_BLOCK} 秒：没跑完会返回 still_running 和 pid，命令继续跑，再调 wait_pid 接着等。"
                     "超过 timeout_secs 会杀掉整个进程组。"),
     "inputSchema": {"type": "object", "properties": {
         "command": {"type": "string"},
         "cwd": {"type": "string", "description": "工作目录，默认任务工作目录"},
         "timeout_secs": {"type": "integer", "description": f"命令总超时，默认 900，最多 {MAX_TIMEOUT}"},
         "tail_lines": {"type": "integer", "description": "返回输出末尾几行，默认 60"},
         "log_path": {"type": "string", "description": "完整输出写到这个文件，默认自动生成"}},
         "required": ["command"]}},
    {"name": "wait_pid",
     "description": ("阻塞等一个进程结束（run_wait 返回 still_running 的 pid，或已在后台跑的进程），"
                     f"单次最多 {MAX_BLOCK} 秒，返回是否结束和 log 末尾。等后台任务用它，不要用 sleep 轮询。"),
     "inputSchema": {"type": "object", "properties": {
         "pid": {"type": "integer"},
         "log_path": {"type": "string", "description": "要看末尾的输出文件"},
         "timeout_secs": {"type": "integer", "description": f"本次最多等几秒，默认且最多 {MAX_BLOCK}"},
         "tail_lines": {"type": "integer", "description": "默认 60"}},
         "required": ["pid"]}},
]

PROBE_TOOLS = [
    {"name": "probe",
     "description": ("派一个只读探针（Codex CLI 的 gpt-6-luna，强制 read-only 沙箱）去做大量阅读 / 对照 / 调研，"
                     "只收回它的最终结论，主任务上下文保持轻量。instructions 写清楚要读什么、查什么、交回什么格式。"
                     "探针不改文件，改代码你自己做；关键结论自己抽查核实。互不相干的几块可以并行派："
                     "每个 probe 传 wait=false 立即拿到 probe_id，再用 probe_wait 一起等。"
                     f"wait=true（默认）时单次最多阻塞 {MAX_BLOCK} 秒，没跑完返回 still_running 和 probe_id。"),
     "inputSchema": {"type": "object", "properties": {
         "instructions": {"type": "string", "description": "探针要做什么、交回什么格式"},
         "cwd": {"type": "string", "description": "探针的工作目录，默认任务工作目录"},
         "effort": {"type": "string", "enum": list(PROBE_EFFORTS), "description": "推理强度，默认 medium"},
         "timeout_secs": {"type": "integer", "description": f"默认 900，最多 {PROBE_MAX_TIMEOUT}，超时杀掉"},
         "wait": {"type": "boolean", "description": "默认 true；false 立即返回 probe_id（并行派多个时用）"},
         "model": {"type": "string", "description": f"默认 {PROBE_MODEL}，一般不用传"}},
         "required": ["instructions"]}},
    {"name": "probe_wait",
     "description": (f"等一个或多个探针的结果（单次最多阻塞 {MAX_BLOCK} 秒）。全部结束就返回各自的状态、用时、"
                     "最终回复全文；还有没跑完的会列出来，再调一次接着等。"),
     "inputSchema": {"type": "object", "properties": {
         "probe_ids": {"type": "array", "items": {"type": "string"}},
         "timeout_secs": {"type": "integer", "description": f"本次最多等几秒，默认且最多 {MAX_BLOCK}"}},
         "required": ["probe_ids"]}},
]
REVIEW_TOOLS = [
    {"name": "review",
     "description": ("派一个独立审查员（Codex CLI 的 gpt-6-luna，强制 read-only 沙箱）对你的改动做初步审查："
                     "改完代码、git commit / push 之前，以及写最终报告之前调一次。审查员自己在 cwd 跑只读命令"
                     "（git diff / status、rg、只读测试），按任务书逐条核对要求和规则、有没有混进无关改动、"
                     "报告里的数字是否属实、明显 bug，交回「结论：通过 / 有问题」和问题清单（阻断 / 应修 / 建议）。"
                     "初步审查意见只是参考线索，不是定论，可能误报也可能漏报。改完可以再审一次。"
                     f"单次最多阻塞 {MAX_BLOCK} 秒，没审完返回 still_running 和 review_id，再调 review_wait。"),
     "inputSchema": {"type": "object", "properties": {
         "task_file": {"type": "string", "description": "任务书路径（相对 cwd 或绝对）；不给就在 instructions 里写明要求"},
         "instructions": {"type": "string", "description": "补充说明：做了什么、要特别核对的点"},
         "cwd": {"type": "string", "description": "仓库目录，默认任务工作目录"},
         "base": {"type": "string", "description": "对比的 git 基准（提交 / 分支）；不给审工作区相对 HEAD 的未提交改动（含暂存区），给了审 base..HEAD 加未提交改动"},
         "report_file": {"type": "string", "description": "报告草稿路径，让审查员核对里面的说法和数字"},
         "effort": {"type": "string", "enum": list(PROBE_EFFORTS), "description": "推理强度，默认 medium"},
         "timeout_secs": {"type": "integer", "description": f"默认 900，最多 {PROBE_MAX_TIMEOUT}，超时杀掉"},
         "wait": {"type": "boolean", "description": "默认 true；false 立即返回 review_id"},
         "model": {"type": "string", "description": f"默认 {PROBE_MODEL}，一般不用传"}},
         "required": []}},
    {"name": "review_wait",
     "description": f"等初步审查的结论（单次最多阻塞 {MAX_BLOCK} 秒），没审完再调一次接着等。",
     "inputSchema": {"type": "object", "properties": {
         "review_ids": {"type": "array", "items": {"type": "string"}},
         "timeout_secs": {"type": "integer", "description": f"本次最多等几秒，默认且最多 {MAX_BLOCK}"}},
         "required": ["review_ids"]}},
]

if PROBE_ON:
    TOOLS = TOOLS + PROBE_TOOLS
if REVIEW_ON:
    TOOLS = TOOLS + REVIEW_TOOLS

_OUT = threading.Lock()
_CANCELS = {}


def _send(obj):
    s = json.dumps(obj, ensure_ascii=False)
    with _OUT:
        sys.stdout.write(s + "\n")
        sys.stdout.flush()


def _call(name, args, cancel):
    if name == "read_files":
        return read_files(args.get("files"), args.get("max_chars_per_file"),
                          args.get("max_total_chars"))
    if name == "run_wait":
        return run_wait(args.get("command"), args.get("cwd"), args.get("timeout_secs") or 900,
                        args.get("tail_lines") or 60, args.get("log_path"), _cancel=cancel)
    if name == "wait_pid":
        return wait_pid(args.get("pid"), args.get("log_path"), args.get("timeout_secs"),
                        args.get("tail_lines") or 60, _cancel=cancel)
    if name == "probe":
        w = args.get("wait")
        return probe(args.get("instructions"), args.get("cwd"), args.get("effort") or "medium",
                     args.get("timeout_secs") or 900, True if w is None else bool(w),
                     args.get("model"), _cancel=cancel)
    if name == "probe_wait":
        return probe_wait(args.get("probe_ids"), args.get("timeout_secs"), _cancel=cancel)
    if name == "review":
        w = args.get("wait")
        return review(args.get("task_file"), args.get("instructions"), args.get("cwd"),
                      args.get("base"), args.get("report_file"), args.get("effort") or "medium",
                      args.get("timeout_secs") or 900, True if w is None else bool(w),
                      args.get("model"), _cancel=cancel)
    if name == "review_wait":
        return probe_wait(args.get("review_ids"), args.get("timeout_secs"), _cancel=cancel,
                          _tool="review_wait", _arg="review_ids")
    raise KeyError(name)


def _handle_call(mid, params):
    name = params.get("name")
    args = params.get("arguments") or {}
    cancel = threading.Event()
    _CANCELS[mid] = cancel
    try:
        if name not in {t["name"] for t in TOOLS}:
            _send({"jsonrpc": "2.0", "id": mid,
                   "error": {"code": -32602, "message": f"没有这个工具：{name}"}})
            return
        try:
            text, err = _call(name, args, cancel), False
        except (ValueError, TypeError, OSError) as e:
            text, err = f"参数或执行出错：{e}", True
        except Exception as e:      # noqa: BLE001
            text, err = f"内部错误：{type(e).__name__}: {e}", True
        if not cancel.is_set():
            _send({"jsonrpc": "2.0", "id": mid,
                   "result": {"content": [{"type": "text", "text": text}], "isError": err}})
    finally:
        _CANCELS.pop(mid, None)


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        if not isinstance(msg, dict):
            continue
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if method is None:
            continue                         # 客户端发来的响应，不处理
        if method == "initialize":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": params.get("protocolVersion") or "2025-03-26",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER,
                "instructions": "读多个文件用 read_files 一次读完；等长命令用 run_wait / wait_pid，不要 sleep 轮询。"}})
        elif method == "notifications/cancelled":
            c = _CANCELS.get(params.get("requestId"))
            if c:
                c.set()
        elif method.startswith("notifications/"):
            continue
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            threading.Thread(target=_handle_call, args=(mid, params), daemon=True).start()
        elif mid is not None:
            _send({"jsonrpc": "2.0", "id": mid,
                   "error": {"code": -32601, "message": f"不支持：{method}"}})
    # stdin 关了（goose 退出）：杀掉还在跑的命令
    with _PLOCK:
        for pid, r in _PROCS.items():
            if r["p"].poll() is None:
                _killpg(pid)
        for r in _PROBES.values():
            r["stop"] = True
            if r["p"].poll() is None:
                _killpg(r["p"].pid)


if __name__ == "__main__":
    main()
