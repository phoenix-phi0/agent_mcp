# -*- coding: utf-8 -*-
"""CXBatch：把一批提示词交给 Codex 的非交互模式（codex exec）逐条跑。

接口跟 tools/obatch.py 对齐（describe / submit / status / wait / jobs /
cancel）。submit 起一个脱离当前进程的后台执行器
（python -m tools.cxbatch _run <job_id>），进度和输出写进
JOBS/<job_id>/job.json。

## codex exec（按 0.162 的帮助和官方非交互文档）

- 一条任务：`codex exec --json --color never -s <sandbox> -C <cwd> … -`
  提示词走标准输入（参数用 `-`）。这样提示词以 `-` 开头也不会被当成选项。
- `--json` 的 stdout 是 JSONL。用到的事件：`thread.started`（thread_id，
  记成 session_id）、`item.completed` 里 `type=agent_message` 的 text、
  `turn.completed` 的 usage、`turn.failed` 和 `error`。
- 续接：`codex exec resume <thread_id> -`。resume 不收 `-s` / `-C` /
  `--color`，沙箱和工作目录沿用这条线程第一次的设置。
- 工作目录不是 git 仓库时加 `--skip-git-repo-check`（任务自带的空目录
  就不是）。是 git 仓库就不加，留给 Codex 自己的仓库检查。
- 一律 `--ignore-rules`，不吃用户和项目的 execpolicy。config.toml 仍加载
  （模型、MCP 之类），但沙箱和 approval_policy 由下面的参数盖掉。
- 环境交代走 `-c developer_instructions=...`（TOML 多行字符串）。
  推理强度走 `-c model_reasoning_effort=...`。
- 费用不在事件流里，不估算，cost_usd 留空。

## 权限：默认只读，不收放开沙箱

`codex exec` 自己的默认就是只读沙箱。这里再显式传 `-s`，避免
config.toml 里的 sandbox_mode 把批量放宽。

- 不传 / readonly：`-s read-only`
- acceptEdits：`-s workspace-write`（工作目录里可改文件、跑本地命令；
  网络默认仍关）
- danger-full-access、bypassPermissions、--full-auto 不收。批量没人看着。

另外每条都传 `-c approval_policy="never"`：没有人能点批准，要问的话
这条会干等着被超时杀掉。超出沙箱的操作直接失败，回到模型。

## 用法

    from tools import cxbatch

    cxbatch.describe()
    j = cxbatch.submit(["任务一", "任务二"])
    cxbatch.wait(j["job_id"])
    cxbatch.cancel(j["job_id"])
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

JOBS = Path(os.environ.get("CXBATCH_HOME")
            or Path.home() / ".codex-batch" / "jobs")

# systemd 起的 MCP 服务 PATH 里没有 ~/.local/bin
CODEX_BIN = (os.environ.get("CXBATCH_CODEX") or shutil.which("codex")
             or str(Path.home() / ".local" / "bin" / "codex"))

MAX_TASKS = 10
MAX_CONCURRENCY = 5
TASK_TIMEOUT = 600
MAX_OUTPUT = 100_000
PREVIEW = 500

# 不传 model 就用 Codex 自己的默认（config.toml 或 CLI 默认）。
# 本机缓存里见过的可见模型写在 describe()，不在提交时卡死名单——模型名换得勤。
PERMISSION_MODES = ("readonly", "acceptEdits")
SANDBOX = {None: "read-only", "readonly": "read-only",
           "acceptEdits": "workspace-write"}

EFFORTS = ("minimal", "low", "medium", "high", "xhigh")
EFFORT_ALIASES = {"极低": "minimal", "低": "low", "中": "medium",
                  "高": "high", "极高": "xhigh"}
DEFAULT_EFFORT = "medium"

# 嵌套在 Codex 沙箱里再起 codex 时，这些会让子进程以为自己已经在沙箱里。
_ENV_DROP = {"CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED", "CODEX_THREAD_ID"}

_MODEL_RE = re.compile(r"^[A-Za-z0-9_.:\-]+$")

# 只写环境交代，不放任何 key
PREAMBLE = """这是批量任务里的一条，没有人在旁边看着，也没法回答你的问题。

1. 同一件事失败两次就停下来报告：失败在哪一步、报的什么错、本来想做什么。
2. 单条任务有时间上限（600 秒），超时会被直接杀掉。输出很长时先停下来说明。
3. 没让你改文件的任务就别改，只报告。默认是只读沙箱；要改文件，调用方得传
   permission_mode=acceptEdits（工作目录内可写，网络仍关）。
4. 没有人能批准。超出沙箱的命令会直接失败，不要重试着等批准。
5. 最后一段回复就是这条任务的结果，写清楚结论。"""

_WANTS_WRITE = re.compile(
    r"写(?!清楚|明|出来)|修改|改成|改掉|创建|新建|删除|删掉|保存|生成.{0,6}文件"
    r"|\b(write|edit|create|modify|save|delete|patch)\b", re.I)

_SECRET = re.compile(
    r"(sk-|ghp_|gho_|github_pat_|AKIA)[A-Za-z0-9_\-]{8,}"
    r"|((?:api[_-]?key|token|secret|password|passwd|authorization)\s*[:=]\s*)\S+"
    r"|(Bearer\s+)\S+", re.I)


class CXBatchError(Exception):
    """参数不对，或者任务不存在。"""


# ----------------------------------------------------------------------
# 参数


def _check_model(model):
    """None / 空串表示不传 --model。别的必须是模型名样子。"""
    if model is None or (isinstance(model, str) and not model.strip()):
        return None
    m = str(model).strip()
    if not _MODEL_RE.match(m) or len(m) > 80:
        raise CXBatchError(f"model 要是模型名（字母数字、. _ : -），收到：{model!r}")
    return m


def _norm_effort(v):
    """推理强度。None 或空串表示不传 -c，用 Codex 自己的默认。"""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    k = EFFORT_ALIASES.get(str(v).strip(), str(v).strip().lower())
    if k not in EFFORTS:
        raise CXBatchError(
            f"effort 只能是 {' / '.join(EFFORTS)}"
            f"（或中文 {' / '.join(EFFORT_ALIASES)}），"
            f"None 或空串表示不传，收到：{v!r}")
    return k


def _sandbox(permission_mode) -> str:
    if permission_mode in ("danger-full-access", "bypassPermissions", "full-auto"):
        raise CXBatchError(
            "不收 danger-full-access / bypassPermissions：批量任务没人看着。"
            "要改文件用 permission_mode='acceptEdits'（workspace-write，网络仍关）")
    if permission_mode not in SANDBOX:
        raise CXBatchError(
            f"permission_mode 只能是 {' / '.join(PERMISSION_MODES)}，"
            f"不传等于 readonly，收到：{permission_mode!r}")
    return SANDBOX[permission_mode]


def _precheck(items, sandbox: str) -> list:
    if sandbox != "read-only":
        return []
    out = []
    for i, it in enumerate(items, 1):
        if _WANTS_WRITE.search(it["prompt"]):
            out.append(
                f"第 {i} 条看着要写文件，但沙箱是 read-only。"
                f"要改文件传 permission_mode='acceptEdits'，否则会在写入时失败")
    return out


def _toml_string(s: str) -> str:
    """放进 -c 值里的 TOML 字符串。多行用基本多行串，里面的三个引号拆开。"""
    body = s.replace("\\", "\\\\").replace('"""', '""\\"')
    return '"""\n' + body + '\n"""'


def _config_args(o: dict, t: dict) -> list:
    xs = ['approval_policy="never"']
    effort = t["effort"] if "effort" in t else o.get("effort")
    if effort:
        xs.append(f'model_reasoning_effort="{effort}"')
    if o.get("preamble", True):
        xs.append("developer_instructions=" + _toml_string(PREAMBLE))
    return xs


def _command(d: dict, t: dict, resume: str = None) -> list:
    o = d["options"]
    model = t.get("model") or o.get("model")
    git = (Path(d["cwd"]) / ".git").exists()
    if resume:
        # resume 不收 -s / -C / --color，见模块文档
        cmd = [CODEX_BIN, "exec", "resume", "--json"]
    else:
        cmd = [CODEX_BIN, "exec", "--json", "--color", "never",
               "-s", o["sandbox"], "-C", d["cwd"]]
    cmd.append("--ignore-rules")
    if not git:
        cmd.append("--skip-git-repo-check")
    for c in _config_args(o, t):
        cmd += ["-c", c]
    if model:
        cmd += ["-m", model]
    if resume:
        cmd.append(resume)
    cmd.append("-")          # 提示词在标准输入
    return cmd


def _env() -> dict:
    env = _child_env()
    for k in _ENV_DROP:
        env.pop(k, None)
    return env


def _mask(s: str) -> str:
    return _SECRET.sub(lambda m: (m.group(2) or m.group(3) or "") + "***", s)


def _show_cmd(cmd: list) -> list:
    out = []
    for a in cmd:
        a = _mask(a)
        if a.startswith("developer_instructions=") and len(a) > 80:
            a = a[:80] + f"…（共 {len(a)} 字）"
        elif len(a) > 300:
            a = a[:300] + f"…（共 {len(a)} 字）"
        out.append(a)
    return out


def _known_models() -> list:
    """本机模型缓存里 visibility 不是 hide 的 slug。读不到就空列表。"""
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    try:
        data = json.loads((home / "models_cache.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for m in data.get("models") or []:
        if not isinstance(m, dict) or m.get("visibility") == "hide":
            continue
        slug = m.get("slug")
        if isinstance(slug, str) and slug not in out:
            out.append(slug)
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
        raise CXBatchError(f"没有这个任务：{job_id}") from None


def _save(d: dict) -> None:
    f = _job_dir(d["id"]) / "job.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, f)


# ----------------------------------------------------------------------
# 对外接口


def submit(tasks, name: str = "", model: str = None, cwd: str = None,
           timeout: int = TASK_TIMEOUT, concurrency: int = 1,
           mode: str = "isolated", permission_mode: str = None,
           preamble: bool = True, effort: str = DEFAULT_EFFORT) -> dict:
    """提交一批任务，立刻返回，不等跑完。

    tasks：提示词列表，或 {prompt, model, effort} 字典列表。
        model / effort 缺省跟这批的一样；effort 显式给 None 或空串表示这条不传。
    model：传给 --model。不传用 Codex 自己的默认。
    cwd：不传用任务目录下的空目录。传了按 check_workdir 校验
        （不收 ~、/、家目录、含凭证的目录）。
    timeout：单条秒数上限，超时杀掉这条的进程组。
    concurrency：isolated 模式下同时跑几条（1~5）。share 一律顺序。
    mode：isolated 各条独立；share 后一条用 exec resume 接前一条的线程，
        前一条失败就开新线程。
    permission_mode：readonly（默认）或 acceptEdits。不收 danger-full-access。
    preamble：把 PREAMBLE 放进 developer_instructions。
    effort：推理强度，默认 medium。None 或空串不传。

    返回 {"job_id", "status", "tasks", "dir", "sandbox", "warnings"}。
    """
    default_model = _check_model(model)
    job_effort = _norm_effort(effort)
    sandbox = _sandbox(permission_mode)
    items = []
    for t in tasks:
        if isinstance(t, str) and t.strip():
            items.append({"prompt": t, "model": default_model, "effort": job_effort})
        elif isinstance(t, dict) and str(t.get("prompt") or "").strip():
            items.append({
                "prompt": t["prompt"],
                "model": _check_model(t["model"]) if t.get("model") else default_model,
                "effort": _norm_effort(t["effort"]) if "effort" in t else job_effort,
            })
        else:
            raise CXBatchError(f"任务要是非空字符串或含 prompt 的字典，收到：{t!r}")
    if not items:
        raise CXBatchError("一条任务都没有")
    if len(items) > MAX_TASKS:
        raise CXBatchError(f"一次最多 {MAX_TASKS} 条，这次给了 {len(items)} 条。")
    if mode not in ("share", "isolated"):
        raise CXBatchError(f"mode 只能是 share 或 isolated，收到：{mode}")
    try:
        concurrency = int(concurrency)
        timeout = int(timeout)
    except (TypeError, ValueError):
        raise CXBatchError("concurrency / timeout 要是整数") from None
    if not 1 <= concurrency <= MAX_CONCURRENCY:
        raise CXBatchError(f"concurrency 要在 1~{MAX_CONCURRENCY}，收到：{concurrency}")
    if timeout < 1:
        raise CXBatchError("timeout 要大于 0")
    if shutil.which(CODEX_BIN) is None and not Path(CODEX_BIN).is_file():
        raise CXBatchError(f"找不到 {CODEX_BIN}，Codex 装了吗？")
    warnings = _precheck(items, sandbox)
    if cwd:
        try:
            cwd = check_workdir(cwd)
        except UnsafeWorkdirError as e:
            raise CXBatchError(f"cwd 不能用：{e}") from None

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
                    "concurrency": concurrency, "sandbox": sandbox,
                    "permission_mode": permission_mode,
                    "preamble": bool(preamble), "effort": job_effort},
        "warnings": warnings, "cmd": None,
        "tasks": [dict(it, status="pending", output="", error="", session_id=None,
                       seconds=None, tokens=None, cost_usd=None, rc=None,
                       stderr="", cmd=None) for it in items],
    }
    d["cmd"] = _show_cmd(_command(d, {"prompt": "<提示词>", "model": default_model,
                                      "effort": job_effort}))
    _save(d)

    subprocess.run([sys.executable, "-m", "tools.cxbatch", "_detach", job_id],
                   cwd=str(ROOT), stdin=subprocess.DEVNULL, check=True,
                   env=dict(os.environ, CXBATCH_HOME=str(JOBS)))
    return {"job_id": job_id, "status": "queued", "tasks": len(items),
            "dir": str(jd), "sandbox": sandbox, "warnings": warnings}


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
    """取消：杀掉执行器和每条正在跑的 codex（按记下的进程组），没跑的标成 cancelled。"""
    d = _load(job_id)
    if d["status"] not in ("queued", "running"):
        return {"job_id": job_id, "status": d["status"], "note": "已经结束了"}
    if not d.get("pid"):
        raise CXBatchError("执行器还没起来，过几秒再取消")
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
    exe = shutil.which(CODEX_BIN) or (CODEX_BIN if Path(CODEX_BIN).is_file() else None)
    models = _known_models()
    lines = [f"执行端：{exe or f'找不到 {CODEX_BIN}'}", f"任务目录：{JOBS}"]
    if models:
        lines.append("本机缓存里可见的模型：" + "、".join(models)
                     + "（不传 model 用 Codex 自己的默认，不限于这份名单）")
    else:
        lines.append("没读到模型缓存。不传 model 就用 Codex 自己的默认。")
    js = jobs(5)
    lines.append(f"最近 {len(js)} 个任务" if js else "还没有任务")
    for j in js:
        lines.append(f"  {j['id']}  {j['status']:10} {j['progress']:6} {j['name'][:30]}")
    lines += [
        "",
        "权限（codex exec 的沙箱，再加 approval_policy=never，避免干等批准）：",
        "  不传 / readonly   -s read-only",
        "  acceptEdits       -s workspace-write（目录内可写、可跑本地命令，网络默认关）",
        "  danger-full-access / bypassPermissions 不收",
        "",
        "推理强度 effort（-c model_reasoning_effort）："
        "minimal / low / medium / high / xhigh，也收 极低/低/中/高/极高；默认 medium。",
        "  None 或空串 = 不传，用 Codex 自己的默认。单条可在任务字典里覆盖。",
        "",
        "mode=share 用 exec resume 接上一条的 thread_id。isolated 可用 concurrency（1~5）。",
        "每条的原始事件流在任务目录 task_<n>.raw.jsonl / task_<n>.stderr.log。",
        "费用不在事件流里，不估算。",
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------------
# 执行器（在后台进程里跑）


def _add_usage(tok, usage):
    if not isinstance(usage, dict):
        return tok
    tok = dict(tok or {"input": 0, "cached_input": 0, "output": 0, "reasoning": 0})
    tok["input"] += usage.get("input_tokens") or 0
    tok["cached_input"] += usage.get("cached_input_tokens") or 0
    tok["output"] += usage.get("output_tokens") or 0
    tok["reasoning"] += usage.get("reasoning_output_tokens") or 0
    return tok


def _err_text(e: dict) -> str:
    msg = e.get("message")
    if msg is None and isinstance(e.get("error"), dict):
        msg = e["error"].get("message")
    elif msg is None and e.get("error"):
        msg = e.get("error")
    if isinstance(msg, dict):
        msg = msg.get("message") or json.dumps(msg, ensure_ascii=False)
    return str(msg or e.get("type") or "")[:500]


def _parse(stdout: str) -> dict:
    """JSONL → {text, session_id, tokens, error}。"""
    r = {"text": [], "session_id": None, "tokens": None, "error": ""}
    for line in stdout.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(e, dict):
            continue
        typ = e.get("type")
        if typ == "thread.started" and e.get("thread_id"):
            r["session_id"] = e["thread_id"]
        elif typ == "item.completed":
            item = e.get("item") or {}
            if item.get("type") in ("agent_message", "assistant_message") and item.get("text"):
                r["text"].append(item["text"])
        elif typ == "turn.completed":
            r["tokens"] = _add_usage(r["tokens"], e.get("usage"))
        elif typ in ("turn.failed", "error"):
            r["tokens"] = _add_usage(r["tokens"], e.get("usage"))
            msg = _err_text(e)
            if msg:
                r["error"] = msg
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
        p = subprocess.Popen(cmd, cwd=d["cwd"], env=_env(), stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             start_new_session=True)
    except OSError as e:
        t.update(status="error", error=f"起不来 codex：{e}", seconds=0)
        return
    (jd / f"task_{n}.pid").write_text(str(p.pid))
    try:
        out, err = p.communicate(t["prompt"], timeout=d["options"]["timeout"])
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

    parsed = _parse(out or "")
    text = "\n".join(parsed["text"])
    if len(text) > MAX_OUTPUT:
        text = text[:MAX_OUTPUT] + f"\n…（输出太长，已截断，共 {len(text)} 字）"
    t.update(output=text, session_id=parsed["session_id"], tokens=parsed["tokens"])
    if p.returncode != 0:
        t.update(status="error",
                 error=(f"退出码 {p.returncode} " + (parsed["error"] or t["stderr"])).strip())
    elif parsed["error"]:
        t.update(status="error", error=parsed["error"])
    elif not text:
        t.update(status="error", error="codex 正常退出但没有文本输出（事件流里没有 agent_message）")
    else:
        t["status"] = "done"


def _detach(job_id: str) -> None:
    with open(_job_dir(job_id) / "runner.log", "ab") as log:
        subprocess.Popen([sys.executable, "-m", "tools.cxbatch", "_run", job_id],
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
