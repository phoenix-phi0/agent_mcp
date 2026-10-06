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

acceptEdits 也不一定够：模型常用 shell 命令写文件（echo > a.txt），那走
的是 bash 的批准，不是编辑的。要它跑命令就用 allowed_tools 给到具体
规则，比如 ["Bash(python *)", "Edit"]，规则写法见
~/.grok/docs/user-guide/22-permissions-and-safety.md。

## 不收 bypassPermissions

grok 里 bypassPermissions 就是 --always-approve。理由同 cbatch：批量没人
看着，要放开就指定到具体工具。

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
   这类只读操作随便用；别的先想想是不是必须。
5. 最后一段回复就是这条任务的结果，写清楚结论。"""


class GBatchError(Exception):
    """参数不对，或者任务不存在。"""


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
           preamble: bool = True) -> dict:
    """提交一批任务，立刻返回，不等跑完。

    tasks：提示词列表，或 {prompt, outfile} 字典列表。outfile 给了的话，
        那条的最终回复另存一份到这个文件（相对 cwd）。
    mode：isolated 各条独立；share 后一条用 -r 接前一条的会话，前一条
        失败就开新会话。
    cwd：grok 在哪个目录跑。规则同 cbatch：不收 ~、/ 和含凭证的目录。
    model：传给 --model，默认不传（grok 自己的默认）。
    permission_mode：传给 --permission-mode（default / acceptEdits / auto /
        dontAsk）。不收 bypassPermissions。
    allowed_tools：权限规则列表，每条一个 --allow，如 "Bash(git *)"。
    timeout：单条任务的秒数上限。

    返回 {"job_id", "status", "tasks", "dir"}。
    """
    items = []
    for t in tasks:
        if isinstance(t, str) and t.strip():
            items.append({"prompt": t, "outfile": ""})
        elif isinstance(t, dict) and t.get("prompt"):
            items.append({"prompt": t["prompt"],
                          "outfile": t.get("outfile", "")})
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
                    "timeout": int(timeout), "preamble": bool(preamble)},
        "tasks": [dict(it, status="pending", output="", error="",
                       stop_reason=None, session_id=None, cost_usd=None,
                       turns=None, seconds=None) for it in items],
    }
    _save(d)

    # 经中间进程起执行器，理由见 cbatch.submit
    subprocess.run([sys.executable, "-m", "tools.gbatch", "_detach", job_id],
                   cwd=str(ROOT), stdin=subprocess.DEVNULL, check=True,
                   env=dict(os.environ, GBATCH_HOME=str(JOBS)))

    return {"job_id": job_id, "status": "queued", "tasks": len(items),
            "dir": str(jd)}


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
    return d


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
    if o["permission_mode"]:
        cmd += ["--permission-mode", o["permission_mode"]]
    for rule in o["allowed_tools"]:
        cmd += ["--allow", rule]
    if o["preamble"]:
        cmd += ["--rules", PREAMBLE]
    return cmd


def _run_one(d: dict, t: dict, resume: str = None) -> None:
    """跑一条，结果写回 t。不抛异常：一条坏了记下来，接着跑下一条。"""
    t0 = time.time()
    try:
        p = subprocess.run(_command(d, t, resume), cwd=d["cwd"],
                           env=_child_env(), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True,
                           timeout=d["options"]["timeout"])
    except subprocess.TimeoutExpired:
        t.update(status="timeout", seconds=round(time.time() - t0, 1),
                 error=f"超过 {d['options']['timeout']} 秒，已杀掉")
        return
    t["seconds"] = round(time.time() - t0, 1)

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
        t.update(status="error",
                 error="回合被中断（stopReason=cancelled）：多半是某个工具调用要批准、"
                       "没人批，整条就停了。output 只是它打算做的事，没做成。"
                       "要写文件或跑命令，传 permission_mode 或 allowed_tools")
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
    for t in d["tasks"]:
        if cancelled():
            break
        t["status"] = "running"
        _save(d)
        resume = prev_session if d["mode"] == "share" else None
        _run_one(d, t, resume)
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
