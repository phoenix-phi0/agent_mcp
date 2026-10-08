# -*- coding: utf-8 -*-
"""CBatch：把一批提示词交给 Claude Code 的无头模式（claude -p）逐条跑。

接口跟 tools/zbatch.py 一样（describe / submit / status / wait / jobs /
cancel），换的是执行端：zbatch 交给 Windows 上的 ZBatch 服务去调 zcode，
这里直接在本机起 claude -p。

## 没有服务，只有一个后台进程

submit 起一个脱离当前进程的执行器（python -m tools.cbatch _run <job_id>），
它逐条跑任务，进度和输出写进 JOBS/<job_id>/job.json。查状态就是读这个
文件，取消就是杀执行器的进程组。

所以不用像 zbatch 那样先启动服务、找端口；调用方进程退出了，批量照样
跑完。代价是没有仪表盘——要看就 describe() 或直接看 job.json。

## 两道限制，跟 zbatch 同样的理由

**单次最多 MAX_TASKS 条。** 批量失控的代价比单次调用大得多。

**默认不放开权限。** claude -p 没人点「允许」，需要批准的工具调用会被
直接拒掉，于是默认只能读、不能写、不能随便跑命令。要写文件就显式传
permission_mode="acceptEdits" 或 allowed_tools=[...]——放不放开该是调用方
看着任务内容决定的，不该是默认值。

## 每条都是新进程

claude -p 跑完就退出，下一条重新起。share 模式靠 --resume 接上一条的
会话（上下文还在），isolated 模式各条互不相干。都不会碰到 MCP 进程里
缓存旧模块的问题。

## 环境变量要洗掉一层

在 Claude Code 会话里调这个模块时，环境里带着 CLAUDECODE、
CLAUDE_CODE_SESSION_ID 这些。原样传给子进程，claude -p 会以为自己是
当前会话的子会话。所以起子进程前把它们去掉，让每条任务是独立的会话。

## 用法

    from tools import cbatch

    cbatch.describe()                         # 最近跑了什么
    j = cbatch.submit(["任务一", "任务二"])    # 提交，立刻返回
    cbatch.status(j["job_id"])                # 查进度
    cbatch.wait(j["job_id"])                  # 等跑完
    cbatch.cancel(j["job_id"])

## 执行方式 engine

默认 engine="claude"，就是上面说的 claude -p，行为不变。另外两种：

- engine="dsl"：交给 tools/dslagent，在任务的 project 目录里**直接改文件**，要求项目测试能跑。按开局测试分两条路：
  有失败 → 修 bug 路径（固定模板 → 模型规划最多 2 版）；全过 → 任务路径（模型规划最多 2 版，
  可写/删文件、改模块名，完成＝测试全过 + 结论修好 + 完成前核对）。
  没成且 fallback（默认 true）就交给 claude -p 兜底：cwd=project，提示词带上 dsl 的记录摘要和改动 diff；
  兜底的权限沿用这批的 permission_mode / allowed_tools，都没给就是 acceptEdits + 只放行测试命令。
- engine="auto"：执行时判定（tools.dslagent.runner.decide_auto）：给了 project 且测试能跑时——初始有失败且
  （给了 test_cmd 或提示词里有失败测试 / Traceback）→ dsl 修 bug；初始全过、提示词没有报错说法、且任务文本里
  能抽出 ≥1 个明确产物（路径/标识符/JSON 键/行数约束等）→ dsl 任务路径；否则 → claude。判定理由记在 engine_reason。

dsl 在独立进程里跑（python -m tools.dslagent run），记录在任务目录 task_<n>/ 下；每条任务的
engine_used（template / plan / plan_task / claude_fallback / claude）、versions、calls、cost_usd、seconds、calls_log
都写在 job.json 里。
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

from .zcode_tool import UnsafeWorkdirError, check_workdir

ROOT = Path(__file__).resolve().parents[1]

# 任务目录。环境变量可以改，测试用临时目录。
JOBS = Path(os.environ.get("CBATCH_HOME")
            or Path.home() / ".claude-batch" / "jobs")

# 执行端。测试换成假的 claude，不花钱也不联网。
#
# PATH 里找不到就退到默认安装位置：MCP 服务（zmcp.service）是 systemd
# 起的，PATH 里没有 ~/.local/bin，只写 "claude" 在那边一定找不到。
CLAUDE_BIN = (os.environ.get("CBATCH_CLAUDE") or shutil.which("claude")
              or str(Path.home() / ".local" / "bin" / "claude"))

MAX_TASKS = 10

# 执行方式，见模块文档「执行方式 engine」
ENGINES = ("claude", "dsl", "auto")
# dsl 执行器的命令。测试换成假的，不调模型。
DSL_CMD = os.environ.get("CBATCH_DSL", "").split() or [sys.executable, "-m", "tools.dslagent"]

# 默认模型。不设的话用 Claude Code 自己的默认（Opus），批量任务多是跑命令、
# 贴结果这类活，用不着，一条贵五倍。要别的就在 submit 里传 model。
DEFAULT_MODEL = "sonnet"

# model="auto"：先让一个便宜的评估调用把整批任务看一遍，每条分一档。
#
# 一次评估整批，不是每条评一次：多花的是一次调用（约两分钱、几秒），
# 跟任务条数无关。评估在执行器里做，submit 照样立刻返回。
#
# 评估失败（超时、输出不是要的格式、给了不认识的档）就整批退回
# AUTO_FALLBACK，不让任务卡住——选错档的代价是贵一点或差一点，任务
# 跑不了的代价更大。失败原因记在 job.json 的 auto 里。
#
# 评估只给难度档，档到 (模型, effort) 的对应在这里定：换模型只改这张表，
# 不用改提示词。最低一档原来是 haiku，Haiku 4.5 是上一代（知识截止
# 2025-02），退役日期「不早于 2026-10-15」；Sonnet 5.5 低 effort 在官方
# 测评上远强于它、按任务算花费也差不多，所以换成 sonnet + low。
# effort 为 None 就不带 --effort，用 claude 自己的默认。
AUTO_TIERS = {"easy": ("sonnet", "low"),
              "normal": ("sonnet", None),
              "hard": ("opus", None)}
AUTO_JUDGE = ("sonnet", "low")
AUTO_FALLBACK = (DEFAULT_MODEL, None)
AUTO_TIMEOUT = 90
# 每条提示词给评估看的长度上限。难度看开头基本就够了，整段塞进去是白花钱。
AUTO_PEEK = 2000

AUTO_PROMPT = """下面是一批要交给编程助手（Claude Code，能读写文件、跑命令）执行的任务。
给每条任务定一个难度档，在够用的前提下选低的：

- easy：机械的活。跑一条命令贴输出、读文件摘一段、按明确说明改一两处、简单问答。
- normal：常规开发。写一个函数或一个小模块、改 bug、写测试、读几个文件后总结。
- hard：难的活。跨多个文件的设计或重构、原因不明的排查、要权衡取舍的方案、
  需求含糊要自己判断的。

只输出一个 JSON 数组，不要别的文字、不要代码块标记。每条任务一个对象，
按编号顺序：[{"i": 1, "tier": "easy", "reason": "一句话理由"}, ...]

"""

# 单条任务的时间上限（秒）。超时就杀掉这一条，接着跑下一条。
TASK_TIMEOUT = 600

# 拼进系统提示的交代。理由见 zbatch.PREAMBLE：执行端不会认输，没人告诉它
# 什么时候该停，它会一直重试到被超时杀掉，什么都留不下。
#
# 走 --append-system-prompt 而不是拼在提示词前面：每条都带上，share 模式
# 续接会话时也不会被当成用户说的话重复一遍。
PREAMBLE = """这是批量任务里的一条，没有人在旁边看着，也没法回答你的问题。

1. 同一件事失败两次就停下来报告：失败在哪一步、报的什么错、本来想做什么。
2. 单条任务有时间上限，超时会被直接杀掉。输出很长时先停下来说明。
3. 没让你改文件的任务就别改，只报告。
4. 最后一段回复就是这条任务的结果，写清楚结论。"""

# 要从子进程环境里去掉的变量，见模块文档「环境变量要洗掉一层」
_ENV_DROP_PREFIX = ("CLAUDE_CODE_",)
_ENV_DROP = {"CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT"}


class CBatchError(Exception):
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
        raise CBatchError(f"没有这个任务：{job_id}") from None


def _save(d: dict) -> None:
    """先写临时文件再改名：查状态的人随时在读，不能读到写了一半的。"""
    f = _job_dir(d["id"]) / "job.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, f)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _pid_alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _settle(d: dict) -> dict:
    """job.json 说在跑、执行器却已经没了（被 kill -9、机器重启），改成 died。

    不改的话 wait 会一直等一个永远不会结束的任务。
    """
    if d.get("status") == "queued" and not d.get("pid"):
        # 执行器还没起来写 pid。刚提交时正常，一分钟还没动静就是起不来了
        # （看 runner.log）
        age = (datetime.now() - datetime.fromisoformat(d["created"])).total_seconds()
        if age < 60:
            return d
    if d.get("status") in ("queued", "running") and not _pid_alive(d.get("pid")):
        d["status"] = "died"
        d["note"] = "执行器进程已经不在了，job.json 停在中途"
        for t in d["tasks"]:
            if t["status"] == "running":
                t["status"] = "died"
    return d


# ----------------------------------------------------------------------
# 对外接口


def _engine_fields(it: dict, i: int, engine, project, test_cmd, fallback,
                   dsl_options) -> None:
    """定下一条任务的 engine 和 dsl 字段（任务里的优先于这批的默认值），不对就报错。

    claude 任务只多一个 engine 键，别的字段一律不带——它的执行跟原来一字不差。
    """
    eng = it.pop("_engine", engine) or "claude"
    own = {k: it.pop("_" + k) for k in ("project", "test_cmd", "fallback", "dsl_options")
           if "_" + k in it}
    if eng not in ENGINES:
        raise CBatchError(f"第 {i} 条：engine 只能是 {' / '.join(ENGINES)}，收到：{eng!r}")
    it["engine"] = eng
    if eng == "claude":
        return
    proj = own.get("project", project)
    if eng == "dsl" and not proj:
        raise CBatchError(f"第 {i} 条：engine=dsl 要给 project（要修的项目目录，dsl 会直接改里面的文件）")
    if proj:
        # 规则同 cwd：家目录、/、含凭证的目录不行
        try:
            proj = check_workdir(proj)
        except UnsafeWorkdirError as e:
            raise CBatchError(f"第 {i} 条：project 不能用：{e}") from None
    fb = own.get("fallback", fallback)
    if isinstance(fb, str):
        fb = fb.strip().lower() not in ("0", "false", "no", "否", "")
    opts = own.get("dsl_options", dsl_options) or {}
    if not isinstance(opts, dict):
        raise CBatchError(f"第 {i} 条：dsl_options 要是字典，收到：{opts!r}")
    it.update(project=proj or None, test_cmd=own.get("test_cmd", test_cmd) or None,
              fallback=bool(fb), dsl_options=opts, engine_reason="")


def submit(tasks, name: str = "", mode: str = "isolated", cwd: str = None,
           model: str = DEFAULT_MODEL, permission_mode: str = None,
           allowed_tools=None, timeout: int = TASK_TIMEOUT,
           preamble: bool = True, engine: str = "claude", project: str = None,
           test_cmd: str = None, fallback: bool = True,
           dsl_options: dict = None) -> dict:
    """提交一批任务，立刻返回，不等跑完。

    tasks：提示词列表，或 {prompt, outfile} 字典列表。outfile 给了的话，
        那条的最终回复另存一份到这个文件（相对 cwd）。
    mode="isolated"：每条独立。默认这个：一条跑偏不会带歪后面的。
    mode="share"：后一条用 --resume 接前一条的会话，适合「先读、再改」。
        前一条失败了，后一条就从头开新会话，不接一个坏掉的上下文。
    cwd：claude 在哪个目录跑，决定它能看到哪些文件和项目设置。默认当前目录。
        不收 ~、/、家目录和含 .ssh 等凭证的父目录（当前目录是这些也不行）。
    model：默认 sonnet（DEFAULT_MODEL）。传 None 或空串就不带 --model，
        用 Claude Code 自己的默认。传 "auto" 就先评估难度，每条分到
        AUTO_TIERS 里的一档（模型加 effort），见 AUTO_PROMPT；分到的结果和
        理由记在每条任务的 model、effort、model_reason 里。
    permission_mode / allowed_tools：原样传给 claude，见模块文档「默认不
        放开权限」。
    timeout：单条任务的秒数上限。dsl 任务的 dsl 部分和兜底的 claude 各算一次。
    engine：claude（默认）/ dsl / auto，见模块文档「执行方式 engine」。
        project、test_cmd、fallback、dsl_options 是这批的默认值，tasks 里的字典可以逐条覆盖
        （{"prompt": …, "engine": "dsl", "project": "/path", "test_cmd": "…", "fallback": false}）。
        engine=dsl 必须有 project（任务里或这里）；test_cmd 缺省按项目探测 pytest / unittest。
        dsl_options 是调试用的：{"max_plan": 2, "template": true, "inject": {...}}。

    返回 {"job_id", "status", "tasks", "dir"}。
    """
    items = []
    for t in tasks:
        if isinstance(t, str) and t.strip():
            items.append({"prompt": t, "outfile": ""})
        elif isinstance(t, dict) and t.get("prompt"):
            items.append({"prompt": t["prompt"],
                          "outfile": t.get("outfile", "")})
            for k in ("engine", "project", "test_cmd", "fallback", "dsl_options"):
                if k in t:
                    items[-1]["_" + k] = t[k]
        else:
            raise CBatchError(f"任务要是非空字符串或含 prompt 的字典，收到：{t!r}")

    if not items:
        raise CBatchError("一条任务都没有")
    if len(items) > MAX_TASKS:
        raise CBatchError(f"一次最多 {MAX_TASKS} 条，这次给了 {len(items)} 条。")
    if mode not in ("share", "isolated"):
        raise CBatchError(f"mode 只能是 share 或 isolated，收到：{mode}")
    # bypassPermissions 等于什么都不拦，还没人看着。真要放开到那一步，该是
    # 人在终端里自己跑 claude，不是一次工具调用的参数。MCP 那边谁都能传
    # 这个参数，所以在这里挡，不指望调用方自觉。
    if permission_mode == "bypassPermissions":
        raise CBatchError("不收 bypassPermissions：批量任务没人看着，"
                          "要放开就用 acceptEdits 或 allowed_tools 指定到具体工具")
    if shutil.which(CLAUDE_BIN) is None:
        raise CBatchError(f"找不到 {CLAUDE_BIN}，Claude Code 装了吗？")
    for i, it in enumerate(items, 1):
        _engine_fields(it, i, engine, project, test_cmd, fallback, dsl_options)

    # 家目录、/ 不行：claude 能读工作目录下的一切，那里有 .ssh、
    # .git-credentials 和各 CLI 的登录凭证。规则同 zcode_tool.check_workdir
    try:
        cwd = check_workdir(cwd or os.getcwd())
    except UnsafeWorkdirError as e:
        raise CBatchError(f"cwd 不能用：{e}") from None

    # 编号带毫秒：jobs() 按编号排新旧，只到秒的话同一秒提交的几批顺序是
    # 随机的（后面那段是随机串）。测试连着提交时撞上的。
    now = datetime.now()
    job_id = now.strftime("%Y%m%d-%H%M%S-") + f"{now.microsecond // 1000:03d}" \
        + uuid.uuid4().hex[:4]
    jd = _job_dir(job_id)
    jd.mkdir(parents=True)

    d = {
        "id": job_id, "name": name, "mode": mode, "cwd": cwd,
        "status": "queued", "created": _now(), "started": None,
        "finished": None, "pid": None,
        "options": {"model": model, "permission_mode": permission_mode,
                    "allowed_tools": list(allowed_tools or []),
                    "timeout": int(timeout), "preamble": bool(preamble),
                    "engine": engine},
        "auto": None,
        "tasks": [dict(it, status="pending", output="", error="",
                       model=None if model == "auto" else (model or None),
                       effort=None, model_reason="",
                       session_id=None, cost_usd=None, turns=None,
                       seconds=None, engine_used=None, versions=None,
                       calls=None, calls_log=None) for it in items],
    }
    _save(d)

    # 经一个中间进程起执行器（_detach），中间进程马上退出、在这里收掉。
    # 执行器于是成了孤儿、归 init 管，跑完由 init 回收。
    #
    # 直接 Popen 的话执行器是调用方的子进程：调用方（MCP 服务、测试）
    # 活着又不 wait 它，它跑完就成了僵尸，kill(pid, 0) 照样成功——
    # 「执行器死了」永远判不出来，wait 会空等到超时。测试撞上的。
    subprocess.run([sys.executable, "-m", "tools.cbatch", "_detach", job_id],
                   cwd=str(ROOT), stdin=subprocess.DEVNULL, check=True,
                   env=dict(os.environ, CBATCH_HOME=str(JOBS)))

    # pid 由执行器自己写进 job.json，这里不再写：执行器可能已经开跑、把
    # status 改成 running 了，这时候再存一次 d 会把它改回 queued。
    return {"job_id": job_id, "status": "queued", "tasks": len(items),
            "dir": str(jd)}


def status(job_id: str, full: bool = False) -> dict:
    """查一个任务的进度和输出。

    full=False 时每条输出截断到 500 字，理由同 zbatch.status：批量输出
    加起来很容易几万字，全塞进对话里挤掉上下文。
    """
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
    """等一个任务跑完，返回最终状态。超时返回当前状态，不报错——
    「还在跑」本身就是有用的信息。"""
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
    """取消：整组杀掉执行器和它正在跑的那条 claude，没跑的标成 cancelled。"""
    d = _load(job_id)
    if d["status"] not in ("queued", "running"):
        return {"job_id": job_id, "status": d["status"], "note": "已经结束了"}
    if not d.get("pid"):
        raise CBatchError("执行器还没起来，过几秒再取消")
    # 先落标记再杀：执行器被杀前要是刚好写了一次 job.json，标记不会被盖掉
    # ——它每次写之前都会重读这个标记（见 _run）。
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
    """人话版的概况：执行端在不在、最近跑了什么。排查时先跑这个。"""
    exe = shutil.which(CLAUDE_BIN)
    lines = [f"执行端：{exe or f'找不到 {CLAUDE_BIN}'}",
             f"任务目录：{JOBS}"]
    js = jobs(5)
    lines.append(f"最近 {len(js)} 个任务" if js else "还没有任务")
    for j in js:
        lines.append(f"  {j['id']}  {j['status']:10} {j['progress']:6} "
                     f"{j['name'][:30]}")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# 执行器（在后台进程里跑）


def _child_env() -> dict:
    return {k: v for k, v in os.environ.items()
            if k not in _ENV_DROP and not k.startswith(_ENV_DROP_PREFIX)}


def _classify(d: dict) -> None:
    """model="auto" 时给每条任务定档，结果写进 t["model"]、t["effort"] 和 d["auto"]。

    评估调用不开工具（--tools ""）、不连 MCP、换掉默认系统提示，在任务目录
    里跑而不是 cwd——它只需要看提示词，不该去读项目文件，也不该把项目的
    CLAUDE.md 读进来白占 token。
    """
    body = AUTO_PROMPT + "\n\n".join(
        f"### 任务 {i}\n{t['prompt'][:AUTO_PEEK]}"
        for i, t in enumerate(d["tasks"], 1))
    judge_model, judge_effort = AUTO_JUDGE
    cmd = [CLAUDE_BIN, "-p", body, "--output-format", "json",
           "--model", judge_model, "--effort", judge_effort,
           "--tools", "", "--strict-mcp-config",
           "--system-prompt", "你负责给任务评估难度。只输出 JSON。"]
    info = {"judge": f"{judge_model}/{judge_effort}", "ok": False, "error": "",
            "cost_usd": None}
    fallback = "/".join(x for x in AUTO_FALLBACK if x)
    picks = {}
    try:
        p = subprocess.run(cmd, cwd=str(_job_dir(d["id"])), env=_child_env(),
                           stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=AUTO_TIMEOUT)
        r = json.loads(p.stdout)
        info["cost_usd"] = r.get("total_cost_usd")
        text = (r.get("result") or "").strip()
        # 叮嘱了不要代码块，还是会有，剥掉
        if text.startswith("```"):
            text = text.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
        for x in json.loads(text):
            if x.get("tier") in AUTO_TIERS:
                picks[int(x["i"])] = (*AUTO_TIERS[x["tier"]],
                                      f"{x['tier']}：{x.get('reason', '')}")
        missing = [i for i in range(1, len(d["tasks"]) + 1) if i not in picks]
        if missing:
            info["error"] = f"第 {missing} 条没给出可用的档，用 {fallback}"
        else:
            info["ok"] = True
    except subprocess.TimeoutExpired:
        info["error"] = f"评估超过 {AUTO_TIMEOUT} 秒，整批用 {fallback}"
    except (json.JSONDecodeError, ValueError, TypeError, KeyError,
            AttributeError) as e:
        info["error"] = f"评估结果解析不了（{e}），没分到的用 {fallback}"

    for i, t in enumerate(d["tasks"], 1):
        t["model"], t["effort"], t["model_reason"] = picks.get(
            i, (*AUTO_FALLBACK, "评估没给出，用默认"))
    d["auto"] = info


def _command(d: dict, t: dict, resume: str = None) -> list:
    o = d["options"]
    cmd = [CLAUDE_BIN, "-p", t["prompt"], "--output-format", "json"]
    if resume:
        cmd += ["--resume", resume]
    if t.get("model"):
        cmd += ["--model", t["model"]]
    if t.get("effort"):
        cmd += ["--effort", t["effort"]]
    if o["permission_mode"]:
        cmd += ["--permission-mode", o["permission_mode"]]
    if o["allowed_tools"]:
        cmd += ["--allowed-tools", *o["allowed_tools"]]
    if o["preamble"]:
        cmd += ["--append-system-prompt", PREAMBLE]
    return cmd


def _run_one(d: dict, t: dict, resume: str = None) -> None:
    """跑一条，结果写回 t。不抛异常：一条坏了记下来，接着跑下一条。"""
    t0 = time.time()
    try:
        # 提示词走参数不走标准输入：-p 后面跟提示词是 claude 的常规用法，
        # 而且以 - 开头的提示词也不会被当成选项（它是 -p 的值）。
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
        # 不是 JSON 多半是 claude 自己没起来（参数错、没登录），原样留着
        t.update(status="error", output=p.stdout,
                 error=(p.stderr or f"退出码 {p.returncode}，输出不是 JSON").strip())
        return

    t.update(output=r.get("result") or "", session_id=r.get("session_id"),
             cost_usd=r.get("total_cost_usd"), turns=r.get("num_turns"))
    # 被拒的工具调用单独记：默认不放开权限，任务「成功」了但该写的文件
    # 没写，原因只在这里看得到。只留工具名，参数可能很长。
    denied = [x.get("tool_name", "?") for x in r.get("permission_denials") or []]
    if denied:
        t["denied"] = denied
    if r.get("is_error") or p.returncode != 0:
        t.update(status="error",
                 error=(r.get("subtype") or "") + (" " + p.stderr.strip()
                                                    if p.stderr.strip() else ""))
    else:
        t["status"] = "done"

    if t["outfile"] and t["output"]:
        f = Path(d["cwd"]) / t["outfile"]
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(t["output"], encoding="utf-8")
        except OSError as e:
            t["error"] = (t["error"] + f" 写 outfile 失败：{e}").strip()


# ---- engine=dsl / auto


def _decide(t: dict) -> str:
    """engine=auto：按 dslagent 的规则判一次，理由记进 t。返回 dsl 或 claude。"""
    from .dslagent.runner import decide_auto
    try:
        r = decide_auto(t["prompt"], t.get("project"), t.get("test_cmd"))
    except Exception as e:   # 判定本身坏了不该让任务卡住，退回默认
        r = {"engine": "claude", "reason": f"判定出错（{type(e).__name__}: {e}），用 claude", "test_cmd": None}
    t["engine_reason"] = "auto → " + r["engine"] + (f"（{r['kind']}）" if r.get("kind") else "") + "：" + r["reason"]
    if r["engine"] == "dsl" and r.get("test_cmd"):
        t["test_cmd"] = r["test_cmd"]
    return r["engine"]


def _run_dsl(d: dict, t: dict, i: int) -> dict:
    """在独立进程里跑 dslagent（它换掉 llm_router 的后端、设环境变量，都是进程级的），读回 result.json。

    跟执行器同一个进程组：cancel 整组杀时它和它起的 claude 一起走。超时先 TERM（它会关掉常驻
    claude、写下已有记录），10 秒还在就 KILL。
    """
    tdir = _job_dir(d["id"]) / f"task_{i}"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "task.txt").write_text(t["prompt"], encoding="utf-8")
    o = t.get("dsl_options") or {}
    timeout = d["options"]["timeout"]
    cmd = [*DSL_CMD, "run", "--project", t["project"], "--task-file", str(tdir / "task.txt"),
           "--out", str(tdir), "--wall", str(max(60, timeout - 60)),
           "--max-plan", str(int(o.get("max_plan", 2)))]
    if t.get("test_cmd"):
        cmd += ["--test-cmd", t["test_cmd"]]
    if o.get("template") is False:
        cmd.append("--no-template")
    if o.get("inject"):
        cmd += ["--inject", json.dumps(o["inject"], ensure_ascii=False)]
    t["calls_log"] = str(tdir / "calls.json")
    with open(tdir / "runner.log", "ab") as log:
        p = subprocess.Popen(cmd, cwd=str(ROOT), env=_child_env(), stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log)
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
    try:
        return json.loads((tdir / "result.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        tail = (tdir / "runner.log").read_text(encoding="utf-8", errors="replace")[-600:]
        why = f"超过 {timeout} 秒被杀" if p.returncode in (-15, -9, 143) else f"退出码 {p.returncode}"
        return {"fixed": False, "engine_used": None, "versions": 0, "calls": 0, "cost": 0,
                "stop": f"dsl 执行器没写出结果（{why}）：{tail}", "handoff": "", "report": "",
                "calls_log": str(tdir / "calls.json"), "dir": str(tdir), "test_cmd": t.get("test_cmd")}


def _fallback_prompt(t: dict, r: dict) -> str:
    note = r.get("handoff") or r.get("stop") or "（没有记录）"
    cmd = r.get("test_cmd") or t.get("test_cmd")
    what = "自动执行流程（中文 DSL agent）已经先试过，没能完成" if r.get("kind") == "task" else \
        "自动修复流程（中文 DSL agent）已经先试过，没能修好"
    return (f"{t['prompt']}\n\n【交接说明】另一个{what}。"
            f"它对项目做的修改还在（见下面的 diff），对的留着、不对的改回去；它的判断不一定对，请自己核实。"
            f"测试文件不要改。\n\n{note}"
            + (f"\n\n跑测试用：{cmd}" if cmd else ""))


def _run_engine(d: dict, t: dict, i: int, resume: str = None) -> None:
    """engine=dsl / auto 的一条：auto 先判定；dsl 没修好且 fallback 就交 claude 兜底。结果写回 t。"""
    t0 = time.time()
    if t["engine"] == "auto" and _decide(t) == "claude":
        _run_one(d, t, resume)
        t["engine_used"] = "claude"
        return
    r = _run_dsl(d, t, i)
    if r.get("kind"):
        t["dsl_kind"] = r["kind"]
    t.update(versions=r.get("versions"), calls=r.get("calls"), cost_usd=r.get("cost"),
             calls_log=r.get("calls_log") or t.get("calls_log"), dsl_dir=r.get("dir"),
             dsl_fixed=bool(r.get("fixed")), dsl_stop=r.get("stop", ""),
             engine_used=r.get("engine_used") or "dsl", output=r.get("report") or r.get("stop", ""))
    if r.get("fixed"):
        t.update(status="done", seconds=round(time.time() - t0, 1))
    elif t.get("fallback", True) and t.get("project"):
        o = d["options"]
        tools = list(o["allowed_tools"])
        if not o["permission_mode"] and not tools:
            cmd = r.get("test_cmd") or t.get("test_cmd")
            tools = ["Read", "Grep", "Glob", "Edit"] + ([f"Bash({cmd}*)"] if cmd else [])
        d2 = dict(d, cwd=t["project"],
                  options=dict(o, permission_mode=o["permission_mode"] or "acceptEdits", allowed_tools=tools))
        t2 = dict(t, prompt=_fallback_prompt(t, r), outfile="")
        _run_one(d2, t2)
        dsl_out = t["output"]
        for k in ("status", "output", "error", "session_id", "turns", "denied"):
            if k in t2:
                t[k] = t2[k]
        t["output"] = (t["output"] or "") + f"\n\n——（先跑的 DSL）{dsl_out}"
        t["cost_usd"] = round((r.get("cost") or 0) + (t2.get("cost_usd") or 0), 4)
        t["engine_used"] = "claude_fallback"
        t["seconds"] = round(time.time() - t0, 1)
    else:
        t.update(status="error", error=r.get("stop") or "dsl 没修好", seconds=round(time.time() - t0, 1))
    if t["outfile"] and t["output"]:
        f = Path(d["cwd"]) / t["outfile"]
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(t["output"], encoding="utf-8")
        except OSError as e:
            t["error"] = (t["error"] + f" 写 outfile 失败：{e}").strip()


def _detach(job_id: str) -> None:
    """起执行器然后自己退出，见 submit 里的说明。

    执行器开新会话（自己一个进程组，cancel 好整组杀），标准输入输出全接到
    文件上——调用方退出、终端关掉，它都不受影响。
    """
    with open(_job_dir(job_id) / "runner.log", "ab") as log:
        subprocess.Popen([sys.executable, "-m", "tools.cbatch", "_run", job_id],
                         cwd=str(ROOT), stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)


def _run(job_id: str) -> None:
    jd = _job_dir(job_id)
    cancelled = lambda: (jd / "cancel").exists()   # noqa: E731

    d = _load(job_id)
    d.update(status="running", started=_now(), pid=os.getpid())
    _save(d)

    if d["options"]["model"] == "auto":
        _classify(d)
        if cancelled():
            return
        _save(d)

    prev_session = None
    for i, t in enumerate(d["tasks"], 1):
        if cancelled():
            break
        t["status"] = "running"
        _save(d)
        resume = prev_session if d["mode"] == "share" else None
        if t.get("engine", "claude") == "claude":
            _run_one(d, t, resume)
            t["engine_used"] = "claude"
        else:
            _run_engine(d, t, i, resume)
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
