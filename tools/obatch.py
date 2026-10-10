# -*- coding: utf-8 -*-
"""OBatch：把一批提示词交给 opencode 的非交互模式（opencode run）逐条跑。

接口跟 tools/gbatch.py 对齐（describe / submit / status / wait / jobs / cancel），
执行器的做法一样：submit 起一个脱离当前进程的后台执行器
（python -m tools.obatch _run <job_id>），进度和输出写进 JOBS/<job_id>/job.json。
多出来的是 concurrency：isolated 模式下几条同时跑。

## opencode 1.18.35 的相关参数（实测）

- 非交互单次：`opencode run [message..] --format json -m provider/model`。
  `--format json` 输出事件流（一行一个 JSON）：step_start / text / step_finish /
  error。step_finish 带 tokens{total,input,output,reasoning,cache} 和 cost，
  text 事件带最终回复、每个事件有毫秒时间戳（首字秒就是第一个 text 事件的时间
  减去进程启动时间）。
- 系统提示：没有命令行开关。用环境变量 OPENCODE_CONFIG_CONTENT 注入一份内联配置，
  里面定义一个 agent（obatch），agent.prompt 就是替换后的系统提示。
- 关工具：同一个 agent 的 tools 字段，`{"*": false}` 全关。（debug agent 能看到
  生效结果。）
- 最大轮数：agent.steps。
- 关 MCP：内联配置 mcp 为空对象是「合并」不是「清空」，所以 lean 靠关工具（"*": false
  连 MCP 工具一起关）；本机全局配置里目前也没有配 MCP。做不到的：不连接 MCP 服务本身
  （连接仍会发生，只是模型看不到工具）。
- 续接：`-s <sessionID>`（share 模式用，sessionID 取自事件流）；`-c` 是接最近一个，
  批量不用。
- 权限：opencode run 默认全放行（"*": allow），没人批准的问题不存在。lean=False 时
  permission_mode 用 agent.permission 收紧：readonly（edit/bash 禁）、
  acceptEdits（edit 放行、bash 禁）、不传（opencode 默认）。
- 工作目录：Popen 的 cwd（也有 --dir，但 cwd 够用）。
- 不要加 `--pure`：实测 1.18.35 加了它 run 卡住不出任何输出直到被杀。
- opencode 没有「追加系统提示」的开关：lean=False 时 PREAMBLE 拼在提示词前面；
  lean=True 时并进 agent.prompt。
- 起步慢：一条「回复 OK」要 12~20 秒（启动 + 标题生成），不算模型时间。

## lean

lean=True（缺省）：短系统提示、关全部工具、最大轮数 max_steps（缺省 5）、
OPENCODE_DISABLE_CLAUDE_CODE=1（不去读 CLAUDE.md 和 ~/.claude 的 skills）。
只适合问答、改写、分析这类不碰文件的任务。lean=False：opencode 默认 agent 和
系统提示，可读写文件。

## 用法

    from tools import obatch

    j = obatch.submit(["任务一", "任务二"], concurrency=2)
    obatch.wait(j["job_id"])
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from .cbatch import _child_env, _now, _pid_alive, _settle
from .zcode_tool import UnsafeWorkdirError, check_workdir

ROOT = Path(__file__).resolve().parents[1]

JOBS = Path(os.environ.get("OBATCH_HOME")
            or Path.home() / ".opencode-batch" / "jobs")

# systemd 起的 MCP 服务 PATH 里没有 ~/.opencode/bin，找不到就退到默认位置
OPENCODE_BIN = (os.environ.get("OBATCH_OPENCODE") or shutil.which("opencode")
                or str(Path.home() / ".opencode" / "bin" / "opencode"))

MAX_TASKS = 10
MAX_CONCURRENCY = 5
TASK_TIMEOUT = 600
MAX_OUTPUT = 100_000          # 单条输出存盘上限（字符），超出截断并注明
PREVIEW = 500                 # status(full=False) 每条输出的预览长度
DEFAULT_MODEL = "zhipuai-coding-plan/glm-5.3"
MODELS = ("zhipuai-coding-plan/glm-5.3", "zhipuai-coding-plan/glm-5.3-flash",
          "zhipuai-coding-plan/glm-5.3-highspeed", "zhipuai-coding-plan/glm-4.6v")
DEFAULT_STEPS = 5
PERMISSION_MODES = ("readonly", "acceptEdits")
AGENT = "obatch"

LEAN_SYSTEM = "你是简洁的助手。直接回答，不要寒暄，不要复述问题。"

# 只写环境交代，不放任何 key
PREAMBLE = """这是批量任务里的一条，没有人在旁边看着，也没法回答你的问题。

1. 同一件事失败两次就停下来报告：失败在哪一步、报的什么错、本来想做什么。
2. 单条任务有时间上限（600 秒），超时会被直接杀掉。输出很长时先停下来说明。
3. 没让你改文件的任务就别改，只报告。
4. 最后一段回复就是这条任务的结果，写清楚结论。"""

_MODEL_RE = re.compile(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.:\-]+$")


class OBatchError(Exception):
    """参数不对，或者任务不存在。"""


# ----------------------------------------------------------------------
# 参数


def _check_model(model) -> str:
    m = (model or DEFAULT_MODEL).strip()
    if not _MODEL_RE.match(m) or m not in MODELS:
        raise OBatchError(f"model 要写成 provider/model 且是可用的之一，收到：{model!r}。"
                          f"可用：{'、'.join(MODELS)}")
    return m


def _config(o: dict) -> dict:
    """OPENCODE_CONFIG_CONTENT 的内容；不需要内联配置时返回空字典。"""
    cfg = {"autoupdate": False, "share": "disabled"}
    if o["lean"]:
        prompt = LEAN_SYSTEM + ("\n\n" + PREAMBLE if o["preamble"] else "")
        cfg["agent"] = {AGENT: {"mode": "primary", "prompt": prompt,
                                "steps": int(o["max_steps"]), "tools": {"*": False}}}
    elif o["permission_mode"]:
        perm = {"edit": "deny", "bash": "deny"}
        if o["permission_mode"] == "acceptEdits":
            perm["edit"] = "allow"
        cfg["agent"] = {AGENT: {"mode": "primary", "permission": perm}}
    return cfg


def _uses_agent(o: dict) -> bool:
    return bool(o["lean"] or o["permission_mode"])


def _command(d: dict, t: dict, resume: str = None) -> list:
    o = d["options"]
    cmd = [OPENCODE_BIN, "run", "--format", "json", "-m", t.get("model") or o["model"]]
    if _uses_agent(o):
        cmd += ["--agent", AGENT]
    if resume:
        cmd += ["-s", resume]
    prompt = t["prompt"]
    if o["preamble"] and not o["lean"]:
        prompt = PREAMBLE + "\n\n" + prompt
    return cmd + ["--", prompt]


def _env(d: dict) -> dict:
    env = _child_env()
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    if d["options"]["lean"]:
        env["OPENCODE_DISABLE_CLAUDE_CODE"] = "1"
    cfg = _config(d["options"])
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(cfg, ensure_ascii=False)
    return env


def _show_cmd(cmd: list) -> list:
    out = []
    for a in cmd:
        out.append(a if len(a) <= 300 else a[:300] + f"…（共 {len(a)} 字）")
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
        raise OBatchError(f"没有这个任务：{job_id}") from None


def _save(d: dict) -> None:
    f = _job_dir(d["id"]) / "job.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, f)


# ----------------------------------------------------------------------
# 对外接口


def submit(tasks, name: str = "", model: str = None, cwd: str = None,
           timeout: int = TASK_TIMEOUT, concurrency: int = 1,
           mode: str = "isolated", lean: bool = True, preamble: bool = True,
           max_steps: int = DEFAULT_STEPS, permission_mode: str = None) -> dict:
    """提交一批任务，立刻返回，不等跑完。

    tasks：提示词列表，或 {prompt, model} 字典列表（单条可覆盖 model）。
    model：provider/model，默认 zhipuai-coding-plan/glm-5.3，写错报可用列表。
    cwd：不传用任务目录下的空目录；传了按 check_workdir 校验（不收 ~、/、家目录、
        含凭证的目录）。
    timeout：单条秒数上限，超时杀掉整组进程。
    concurrency：isolated 模式下同时跑几条（1~5）；share 模式一律顺序。
    mode：isolated 各条独立；share 后一条用 -s 接前一条的会话，前一条失败就开新会话。
    lean：见模块文档，缺省 True。max_steps 只在 lean 时用。
    preamble：附上环境交代 PREAMBLE。
    permission_mode：仅 lean=False 时有效，readonly / acceptEdits，见模块文档。

    返回 {"job_id", "status", "tasks", "dir", "warnings"}。
    """
    default_model = _check_model(model)
    items = []
    for t in tasks:
        if isinstance(t, str) and t.strip():
            items.append({"prompt": t, "model": default_model})
        elif isinstance(t, dict) and t.get("prompt"):
            items.append({"prompt": t["prompt"],
                          "model": _check_model(t["model"]) if t.get("model") else default_model})
        else:
            raise OBatchError(f"任务要是非空字符串或含 prompt 的字典，收到：{t!r}")
    if not items:
        raise OBatchError("一条任务都没有")
    if len(items) > MAX_TASKS:
        raise OBatchError(f"一次最多 {MAX_TASKS} 条，这次给了 {len(items)} 条。")
    if mode not in ("share", "isolated"):
        raise OBatchError(f"mode 只能是 share 或 isolated，收到：{mode}")
    try:
        concurrency = int(concurrency)
        timeout = int(timeout)
        max_steps = int(max_steps)
    except (TypeError, ValueError):
        raise OBatchError("concurrency / timeout / max_steps 要是整数") from None
    if not 1 <= concurrency <= MAX_CONCURRENCY:
        raise OBatchError(f"concurrency 要在 1~{MAX_CONCURRENCY}，收到：{concurrency}")
    if timeout < 1 or max_steps < 1:
        raise OBatchError("timeout 和 max_steps 要大于 0")
    if permission_mode is not None and permission_mode not in PERMISSION_MODES:
        raise OBatchError(f"permission_mode 只能是 {' / '.join(PERMISSION_MODES)}，"
                          f"收到：{permission_mode}")
    warnings = []
    if permission_mode and lean:
        warnings.append("lean=True 时工具全关，permission_mode 不起作用")
    if shutil.which(OPENCODE_BIN) is None:
        raise OBatchError(f"找不到 {OPENCODE_BIN}，opencode 装了吗？")
    if cwd:
        try:
            cwd = check_workdir(cwd)
        except UnsafeWorkdirError as e:
            raise OBatchError(f"cwd 不能用：{e}") from None

    now = datetime.now()
    job_id = now.strftime("%Y%m%d-%H%M%S-") + f"{now.microsecond // 1000:03d}" \
        + uuid.uuid4().hex[:4]
    jd = _job_dir(job_id)
    jd.mkdir(parents=True)
    if not cwd:
        (jd / "work").mkdir()
        cwd = str(jd / "work")

    d = {
        "id": job_id, "name": name, "mode": mode, "cwd": cwd,
        "status": "queued", "created": _now(), "started": None,
        "finished": None, "pid": None,
        "options": {"model": default_model, "timeout": timeout,
                    "concurrency": concurrency, "lean": bool(lean),
                    "preamble": bool(preamble), "max_steps": max_steps,
                    "permission_mode": permission_mode},
        "warnings": warnings, "cmd": None,
        "tasks": [dict(it, status="pending", output="", error="", session_id=None,
                       seconds=None, first_token_seconds=None, tokens=None,
                       cost=None, rc=None, stderr="", cmd=None) for it in items],
    }
    d["cmd"] = _show_cmd(_command(d, {"prompt": "<提示词>"}))
    _save(d)

    subprocess.run([sys.executable, "-m", "tools.obatch", "_detach", job_id],
                   cwd=str(ROOT), stdin=subprocess.DEVNULL, check=True,
                   env=dict(os.environ, OBATCH_HOME=str(JOBS)))
    return {"job_id": job_id, "status": "queued", "tasks": len(items),
            "dir": str(jd), "warnings": warnings}


def status(job_id: str, full: bool = False) -> dict:
    """查一个任务的进度和输出。full=False 时每条输出截断到 500 字。"""
    d = _settle(_load(job_id))
    done = sum(t["status"] not in ("pending", "running") for t in d["tasks"])
    d["progress"] = f"{done}/{len(d['tasks'])}"
    if not full:
        for t in d["tasks"]:
            out = t.get("output") or ""
            if len(out) > PREVIEW:
                t["output"] = out[:PREVIEW] + f"…（还有 {len(out) - PREVIEW} 字）"
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
                    "progress": f"{done}/{len(d['tasks'])}", "created": d["created"]})
        if len(out) >= limit:
            break
    return out


def _killpg(pid) -> None:
    try:
        os.killpg(int(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, TypeError, ValueError):
        pass


def cancel(job_id: str) -> dict:
    """取消：杀掉执行器和每条正在跑的 opencode（按记下的进程组），没跑的标成 cancelled。"""
    d = _load(job_id)
    if d["status"] not in ("queued", "running"):
        return {"job_id": job_id, "status": d["status"], "note": "已经结束了"}
    if not d.get("pid"):
        raise OBatchError("执行器还没起来，过几秒再取消")
    jd = _job_dir(job_id)
    (jd / "cancel").touch()
    for f in jd.glob("task_*.pid"):
        try:
            _killpg(f.read_text().strip())
        except OSError:
            pass
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
    exe = shutil.which(OPENCODE_BIN)
    lines = [f"执行端：{exe or f'找不到 {OPENCODE_BIN}'}", f"任务目录：{JOBS}",
             f"可用模型：{'、'.join(MODELS)}（默认 {DEFAULT_MODEL}）"]
    js = jobs(5)
    lines.append(f"最近 {len(js)} 个任务" if js else "还没有任务")
    for j in js:
        lines.append(f"  {j['id']}  {j['status']:10} {j['progress']:6} {j['name'][:30]}")
    lines += ["", "lean=True（缺省）：短系统提示、关全部工具、限 max_steps 轮；"
              "lean=False：opencode 默认行为（可读写文件），permission_mode=readonly/acceptEdits 可收紧。",
              "concurrency：isolated 模式同时跑几条（1~5）。每条的原始事件流在任务目录 "
              "task_<n>.raw.jsonl / task_<n>.stderr.log。"]
    return "\n".join(lines)


# ----------------------------------------------------------------------
# 执行器（在后台进程里跑）


def _parse(stdout: str) -> dict:
    """事件流 → {text, session_id, tokens, cost, first_ms, error}。"""
    r = {"text": [], "session_id": None, "tokens": None, "cost": None,
         "first_ms": None, "error": ""}
    tok = None
    for line in stdout.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(e, dict):
            continue
        r["session_id"] = e.get("sessionID") or r["session_id"]
        typ = e.get("type")
        part = e.get("part") or {}
        if typ == "text" and part.get("text"):
            r["text"].append(part["text"])
            if r["first_ms"] is None:
                r["first_ms"] = e.get("timestamp")
        elif typ == "step_finish":
            tk = part.get("tokens")
            if isinstance(tk, dict):
                tok = tok or {"total": 0, "input": 0, "output": 0, "reasoning": 0}
                for k in tok:
                    tok[k] += tk.get(k) or 0
            if part.get("cost") is not None:
                r["cost"] = (r["cost"] or 0) + part["cost"]
        elif typ == "error":
            err = e.get("error") or part
            msg = (err.get("data", {}) or {}).get("message") if isinstance(err, dict) else None
            r["error"] = (msg or json.dumps(err, ensure_ascii=False))[:500]
    r["tokens"] = tok
    return r


def _run_one(d: dict, t: dict, resume: str = None, n: int = 1) -> None:
    """跑一条，结果写回 t。不抛异常。"""
    jd = _job_dir(d["id"])
    cmd = _command(d, t, resume)
    t["cmd"] = _show_cmd(cmd)

    def keep(out, err):
        for name, s in ((f"task_{n}.raw.jsonl", out), (f"task_{n}.stderr.log", err)):
            if isinstance(s, bytes):
                s = s.decode("utf-8", "replace")
            try:
                (jd / name).write_text(s or "", encoding="utf-8")
            except OSError:
                pass

    t0 = time.time()
    try:
        p = subprocess.Popen(cmd, cwd=d["cwd"], env=_env(d), stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             start_new_session=True)
    except OSError as e:
        t.update(status="error", error=f"起不来 opencode：{e}", seconds=0)
        return
    (jd / f"task_{n}.pid").write_text(str(p.pid))
    try:
        out, err = p.communicate(timeout=d["options"]["timeout"])
    except subprocess.TimeoutExpired:
        _killpg(p.pid)
        out, err = p.communicate()
        (jd / f"task_{n}.pid").unlink(missing_ok=True)
        keep(out, err)
        t.update(status="timeout", seconds=round(time.time() - t0, 1), rc=p.returncode,
                 stderr=(err or "")[-500:],
                 error=f"超过 {d['options']['timeout']} 秒，已杀掉")
        return
    (jd / f"task_{n}.pid").unlink(missing_ok=True)
    t["seconds"] = round(time.time() - t0, 1)
    t["rc"] = p.returncode
    t["stderr"] = (err or "").strip()[-500:]
    keep(out, err)

    r = _parse(out or "")
    text = "".join(r["text"])
    if len(text) > MAX_OUTPUT:
        text = text[:MAX_OUTPUT] + f"\n…（输出太长，已截断，共 {len(text)} 字）"
    t.update(output=text, session_id=r["session_id"], tokens=r["tokens"], cost=r["cost"])
    if r["first_ms"]:
        t["first_token_seconds"] = round(max(r["first_ms"] / 1000 - t0, 0), 1)
    if p.returncode != 0:
        t.update(status="error", error=(f"退出码 {p.returncode} " + (r["error"] or t["stderr"])).strip())
    elif r["error"]:
        t.update(status="error", error=r["error"])
    elif not text:
        t.update(status="error", error="opencode 正常退出但没有文本输出（事件流里没有 text 事件）")
    else:
        t["status"] = "done"


def _detach(job_id: str) -> None:
    with open(_job_dir(job_id) / "runner.log", "ab") as log:
        subprocess.Popen([sys.executable, "-m", "tools.obatch", "_run", job_id],
                         cwd=str(ROOT), stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)


def _run(job_id: str) -> None:
    jd = _job_dir(job_id)
    cancelled = lambda: (jd / "cancel").exists()   # noqa: E731

    d = _load(job_id)
    d.update(status="running", started=_now(), pid=os.getpid())
    _save(d)
    lock = threading.Lock()

    def save():
        with lock:
            if not cancelled():
                _save(d)

    def work(n, t, resume=None):
        if cancelled():
            return
        w = dict(t, status="running")
        with lock:
            t["status"] = "running"
        save()
        try:
            _run_one(d, w, resume, n)
        except Exception as e:     # 一条坏了不拖垮整批
            w.update(status="error", error=f"执行器出错：{type(e).__name__}: {e}")
        with lock:
            t.clear()
            t.update(w)
        save()

    if d["mode"] == "share":
        prev = None
        for n, t in enumerate(d["tasks"], 1):
            if cancelled():
                break
            work(n, t, prev)
            prev = t["session_id"] if t["status"] == "done" else None
    else:
        q = list(enumerate(d["tasks"], 1))
        q_lock = threading.Lock()

        def worker():
            while True:
                with q_lock:
                    if not q:
                        return
                    n, t = q.pop(0)
                work(n, t)

        ths = [threading.Thread(target=worker, daemon=True)
               for _ in range(max(1, d["options"]["concurrency"]))]
        for th in ths:
            th.start()
        for th in ths:
            th.join()

    if cancelled():
        return          # cancel() 负责收尾
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
