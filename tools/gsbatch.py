# -*- coding: utf-8 -*-
"""GSBatch：把一批提示词交给 Goose 的无头模式（goose run）逐条跑。

接口跟 tools/cxbatch.py 对齐（describe / submit / status / wait / jobs /
cancel）。submit 起一个脱离当前进程的后台执行器
（python -m tools.gsbatch _run <job_id>），进度和输出写进
JOBS/<job_id>/job.json。

## goose run（按 1.55 的帮助）

- 一条任务：`goose run --no-profile --output-format stream-json -i - …`
  提示词走标准输入。`--no-profile` 不加载用户配置里的扩展，只挂
  `--with-builtin` 给的内置扩展（默认 developer：读写文件、跑 shell）。
- stream-json 的 stdout 前几行是 banner（不是 JSON），里面有会话 id
  （形如 20261023_1），记成 session_id。之后每行一个事件：
  `message`（assistant 的 text / thinking / toolRequest，user 的
  toolResponse，文本是逐字流）、`error`、`complete`（token 合计）。
- `complete` 里的 token 是**整个会话**的累计值。share 模式续接时，这条的
  token = 本次累计 − 上一条累计。
- 续接：`goose run --resume --session-id <id>`。会话存在 goose 的
  sessions.db 里（zai 走本批的 GOOSE_PATH_ROOT，chatgpt_codex 走默认目录）。
- PREAMBLE 走 `--system`（追加的系统提示，不替换 goose 默认的）。
- 环境：GOOSE_DISABLE_KEYRING=1、GOOSE_DISABLE_SESSION_NAMING=true（省掉
  起名那次额外调用）、GOOSE_MODE=auto / chat。父进程的 GOOSE_* 一律去掉，
  免得实验用的 GOOSE_PATH_ROOT 之类漏进来。

## provider 和推理强度

goose 1.55 自带的 zai_coding_plan **不发 reasoning_effort**
（GOOSE_THINKING_EFFORT 也没用，模型名加 -low 会 400），所以强度都靠本地
代理往请求里补。分两条路：

- zai_low（默认，模型默认 glm-5.3-flash，强度 low）：直接用全局配置里的
  自定义 provider zai_low（~/.config/goose/custom_providers/zai_low.json，
  base_url 是 127.0.0.1:18766 的常驻代理 ~/.local/share/goose-effort/proxy.py，
  请求里没有 reasoning_effort 就补 low）。不设 GOOSE_PATH_ROOT，跑之前先执行
  一次 ~/.local/share/goose-effort/start_proxy.sh（在跑就直接退出）。这个代理
  的日志 req.jsonl 不分任务，实际响应模型只能按时间窗去对（同一时间段有别的
  goose 请求会混进来），记在 model_used，来源写在 model_used_src。
  effort 传 None 也是 low（代理的缺省）。
- zai_low 配别的强度，或 provider=zai_coding_plan：goose 自己不发
  reasoning_effort，18766 那个代理只会补 low，所以走本批自己的代理（下面），
  每条任务在本批的 GOOSE_PATH_ROOT（GROOT，默认 ~/.goose-batch/groot）里写
  一个临时自定义 provider（engine=openai，同参数），base_url：

      http://127.0.0.1:<PORT>/gsb/<effort>/<job_id>/<n>/api/coding/paas/v4

  代理（python -m tools.gsbatch _proxy，只听 127.0.0.1，第一次用时由执行器
  拉起，之后常驻复用）把请求转发到 https://api.z.ai，路径里有 effort 就补上
  `reasoning_effort=<effort>` 和 `thinking.type=enabled`，effort 是 `-` 就原样
  转发。每个请求的参数（不含消息、工具、请求头）和响应里的 model / usage
  记到 JOBS/<job_id>/task_<n>.llm.jsonl——实际响应模型和推理 token 就从这里
  来，按任务分得清。key 由 goose 自己放进 Authorization 头，代理只转发、不记。
  端口默认 18767（GSBATCH_PROXY_PORT），不跟 18766 抢。
  zai_coding_plan 配 effort=None 就原样转发（服务器缺省，≈ max）。
  强度：minimal / low / medium / high / max（low 实测最好：3/3、约 55 秒）。
  服务器对不认识的值不报错、按缺省处理。
- chatgpt_codex：用 goose 默认配置目录里已登录的公司账号（不设
  GOOSE_PATH_ROOT，不经代理）。强度走 CHATGPT_CODEX_REASONING_EFFORT：
  minimal / low / medium / high / xhigh。拿不到实际响应模型，只记请求的。

## key

- ZAI_CODING_PLAN_API_KEY 只放进子进程环境：取父进程的
  ZAI_CODING_PLAN_API_KEY，没有就取 ZHIPU_API_KEY。不写文件、不进
  job.json、不打印。自定义 provider 文件里只写 api_key_env 这个变量名。
- goose 没有沙箱，developer 的 shell 能看到环境变量。所以子进程里去掉
  名字像凭证的变量（*TOKEN*、*SECRET*、*PASSWORD*、*API_KEY* 等），只留
  这条要用的那一个。

## 附加工具（extra_tools，默认开）

auto 且挂了 developer 时，再用 `--with-extension` 挂一个 stdio MCP 扩展
gsb_tools（tools/gsb_tools_mcp.py，纯标准库）：read_files 一次读多个文件 / 多段，
run_wait 跑命令并阻塞等结束，wait_pid 等已在跑的进程。goose 每轮只执行一个工具，
这几个一次做完多步，省掉分段读文件和 sleep 轮询的来回。PREAMBLE 后面追加
PREAMBLE_TOOLS 两句提示。

- probe（默认开，前提是 extra_tools 开着）：扩展带 GSB_PROBE=1 启动，多出
  probe / probe_wait 两个工具：把大量阅读 / 对照 / 调研派给 Codex CLI
  （gpt-6-luna，强制 `-s read-only`，固定只读前言，不带任何 --dangerously*），
  只收结论。后台独立进程组跑，单次最多阻塞 270 秒，没跑完返回 still_running +
  probe_id；wait=false 立即返回 id，probe_wait 一次等多个。超时杀进程组。
  codex 靠 ~/.codex/auth.json 登录（只留 HOME / PATH 等，不放行任何密钥变量）。
  用的是公司 ChatGPT 额度，probe=False 关掉；关掉时 PREAMBLE 不加第 8 句。
- review（默认开，前提同 probe）：扩展带 GSB_REVIEW=1，多出 review / review_wait：
  同一套 codex 只读执行，派审查员按任务书（task_file）独立审查改动（默认工作区相对
  HEAD 的未提交改动 + 暂存区；给 base 审 base..HEAD + 未提交改动），可核对报告草稿
  （report_file），按固定格式交回「通过 / 有问题」和问题清单。这只是「初步审查」：
  返回文本开头提示逐条自行核实，没有 文件:行号 出处的意见标「无出处，低可信」。
  PREAMBLE 加第 9 句：commit / push 和写最终报告前调 review；意见是线索不是定论，
  阻断 / 应修核实后先改，报告里附审查结论。review=False 关掉。

- goose 对 --with-extension 的扩展固定 300 秒单次调用超时（命令行改不了），
  所以单次最多阻塞 GSB_MAX_BLOCK（EXTRA_TOOLS_MAX_BLOCK=270）秒，没跑完返回
  still_running + pid，命令继续跑，模型再调 wait_pid。
- 续接（--resume）时不再传 --with-extension：会话里已经存了这个扩展，再传会报
  “extension name 'gsb_tools' is already in use” 直接退出。
- 扩展进程继承 goose 的环境，启动时自己再删掉名字像凭证的变量（包括
  ZAI_CODING_PLAN_API_KEY），它跑的命令看不到任何 key。

## 权限：goose 没有沙箱

- 不传 / auto（也收 acceptEdits）：GOOSE_MODE=auto，工具自动批准。
  **能写 cwd 以外的地方**——cwd 只是起点，check_workdir 只挡掉明显危险的
  目录。要严格只读就用 chat。
- chat（也收 readonly）：GOOSE_MODE=chat，一个扩展都不挂，只回答。
- approve / smart_approve 不收：没人能点批准，会干等到超时。

## 用法

    from tools import gsbatch

    gsbatch.describe()
    j = gsbatch.submit(["任务一", "任务二"], effort="low")
    gsbatch.wait(j["job_id"])
    gsbatch.cancel(j["job_id"])
"""

import fcntl
import http.client
import json
import os
import re
import shutil
import signal
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

from .cbatch import _child_env, _now, _pid_alive, _settle
from .zcode_tool import UnsafeWorkdirError, check_workdir

ROOT = Path(__file__).resolve().parents[1]

JOBS = Path(os.environ.get("GSBATCH_HOME")
            or Path.home() / ".goose-batch" / "jobs")

# 本批自己的 goose 配置根（zai 走这里；chatgpt_codex 用默认目录里的登录）
GROOT = Path(os.environ.get("GSBATCH_GOOSE_ROOT")
             or Path.home() / ".goose-batch" / "groot")

# systemd 起的 MCP 服务 PATH 里没有 ~/.local/bin
GOOSE_BIN = (os.environ.get("GSBATCH_GOOSE") or shutil.which("goose")
             or str(Path.home() / ".local" / "bin" / "goose"))

PROXY_PORT = int(os.environ.get("GSBATCH_PROXY_PORT") or 18767)
# 全局 zai_low 用的常驻代理（别的会话装的，这里只检查、不改）
ZAI_LOW_START = Path(os.environ.get("GSBATCH_ZAI_LOW_START")
                     or Path.home() / ".local" / "share" / "goose-effort" / "start_proxy.sh")
ZAI_LOW_PORT = int(os.environ.get("GSBATCH_ZAI_LOW_PORT") or 18766)
ZAI_LOW_LOG = Path(os.environ.get("GSBATCH_ZAI_LOW_LOG")
                   or Path.home() / ".local" / "share" / "goose-effort" / "req.jsonl")
UPSTREAM = os.environ.get("GSBATCH_ZAI_UPSTREAM") or "https://api.z.ai"
ZAI_PATH = "/api/coding/paas/v4"

MAX_TASKS = 10
MAX_CONCURRENCY = 5
TASK_TIMEOUT = 600
MAX_OUTPUT = 100_000
PREVIEW = 500

PROVIDERS = ("zai_low", "zai_coding_plan", "chatgpt_codex")
ZAI = ("zai_low", "zai_coding_plan")
DEFAULT_PROVIDER = "zai_low"
DEFAULT_MODELS = {"zai_low": "glm-5.3-flash", "zai_coding_plan": "glm-5.3-flash",
                  "chatgpt_codex": "gpt-6-sol"}
DEFAULT_MODEL = DEFAULT_MODELS[DEFAULT_PROVIDER]
# 自定义 provider 的模型表（dynamic_models=false）。传了别的模型会临时加进去。
ZAI_MODELS = ("glm-5.3-flash", "glm-5.3", "glm-5-turbo", "glm-5", "glm-4.6", "glm-4.5-air")

PERMISSION_MODES = ("auto", "chat")
PERM_ALIASES = {None: "auto", "": "auto", "auto": "auto", "acceptEdits": "auto",
                "chat": "chat", "readonly": "chat"}

PROVIDER_EFFORTS = {
    "zai_low": ("minimal", "low", "medium", "high", "max"),
    "zai_coding_plan": ("minimal", "low", "medium", "high", "max"),
    "chatgpt_codex": ("minimal", "low", "medium", "high", "xhigh"),
}
EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")   # 面板用的并集
EFFORT_ALIASES = {"极低": "minimal", "低": "low", "中": "medium", "高": "high", "极高": "xhigh"}
DEFAULT_EFFORT = "low"

DEFAULT_EXTENSIONS = ("developer",)
# 附加工具：stdio MCP 扩展（read_files / run_wait / wait_pid）
EXTRA_TOOLS_NAME = "gsb_tools"
EXTRA_TOOLS_SCRIPT = Path(__file__).resolve().parent / "gsb_tools_mcp.py"
EXTRA_TOOLS_PY = os.environ.get("GSBATCH_TOOLS_PYTHON") or (
    str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").is_file()
    else sys.executable)
EXTRA_TOOLS_MAX_BLOCK = 270     # goose 对 stdio 扩展单次调用 300 秒就掐断
_EXT_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9_.:\-]+$")
_SESSION_RE = re.compile(r"\b(\d{8}_\d+)\b")
_SECRET_NAME = re.compile(r"TOKEN|SECRET|PASSW|API_?KEY|ACCESS_KEY|PRIVATE_KEY|CREDENTIAL", re.I)

# 只写环境交代，不放任何 key
PREAMBLE = """这是批量任务里的一条，没有人在旁边看着，也没法回答你的问题。

1. 同一件事失败两次就停下来报告：失败在哪一步、报的什么错、本来想做什么。
2. 单条任务有时间上限（默认 600 秒），超时会被直接杀掉。输出很长时先停下来说明。
3. 没让你改文件的任务就别改，只报告。要改文件只改当前工作目录里的，别碰目录外面。
4. 没有人能批准。工具调用失败就换个办法或者报告，不要等批准。
5. 最后一段回复就是这条任务的结果，写清楚结论。"""

# 挂了附加工具时追加在 PREAMBLE 后面
PREAMBLE_TOOLS = """6. 读多个文件或同一文件的多段，用 read_files 一次读完，别用 cat/sed 分几次读。
7. 跑测试等长命令用 run_wait 阻塞等结果，没跑完就调 wait_pid 接着等，不要放后台再 sleep 轮询。"""

# 开了 probe 时再追加
PREAMBLE_PROBE = ("8. 要读很多文件再对照 / 总结时，派给 probe 只收结论，互不相干的几块可以并行派"
                  "（wait=false 再 probe_wait）；探针只读，改代码自己做；关键结论自己抽查。")

# 开了 review 时再追加
PREAMBLE_REVIEW = """9. 改了代码的任务，在 commit/push 和写最终报告前调 review 做初步审查（给 task_file，有报告草稿就给 report_file）。初步审查意见只是参考线索，不是定论，可能误报也可能漏报；阻断和应修的问题核实后先改，改完可以再审一次。报告里附上审查结论。"""

_WANTS_WRITE = re.compile(
    r"写(?!清楚|明|出来)|修改|改成|改掉|创建|新建|删除|删掉|保存|生成.{0,6}文件"
    r"|\b(write|edit|create|modify|save|delete|patch)\b", re.I)

_SECRET = re.compile(
    r"(sk-|ghp_|gho_|github_pat_|AKIA)[A-Za-z0-9_\-]{8,}"
    r"|((?:api[_-]?key|token|secret|password|passwd|authorization)\s*[:=]\s*)\S+"
    r"|(Bearer\s+)\S+", re.I)


class GSBatchError(Exception):
    """参数不对，或者任务不存在。"""


# ----------------------------------------------------------------------
# 参数


def _check_provider(p):
    if p is None or (isinstance(p, str) and not p.strip()):
        return DEFAULT_PROVIDER
    p = str(p).strip()
    if p not in PROVIDERS:
        raise GSBatchError(f"provider 只能是 {' / '.join(PROVIDERS)}，收到：{p!r}")
    return p


def _check_model(model, provider):
    """None / 空串表示用这个 provider 的默认模型。"""
    if model is None or (isinstance(model, str) and not model.strip()):
        return DEFAULT_MODELS[provider]
    m = str(model).strip()
    if not _MODEL_RE.match(m) or len(m) > 80:
        raise GSBatchError(f"model 要是模型名（字母数字、. _ : -），收到：{model!r}")
    return m


def _norm_effort(v, provider):
    """推理强度。None 或空串表示不设（zai 走代理但不注入，codex 不设环境变量）。"""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    k = EFFORT_ALIASES.get(str(v).strip(), str(v).strip().lower())
    # 两家最高档名字不一样，互相认
    if provider in ZAI and k == "xhigh":
        k = "max"
    elif provider == "chatgpt_codex" and k == "max":
        k = "xhigh"
    ok = PROVIDER_EFFORTS[provider]
    if k not in ok:
        raise GSBatchError(
            f"{provider} 的 effort 只能是 {' / '.join(ok)}"
            f"（或中文 {' / '.join(EFFORT_ALIASES)}），"
            f"None 或空串表示不设，收到：{v!r}")
    return k


def _perm(permission_mode) -> str:
    if permission_mode in ("approve", "smart_approve", "manual"):
        raise GSBatchError(
            "不收 approve / smart_approve：批量任务没人能点批准，会干等到超时。"
            "要工具就用 auto，只要回答用 chat")
    if permission_mode in ("bypassPermissions", "danger-full-access"):
        raise GSBatchError(
            "goose 没有沙箱，auto 本来就是工具自动批准；不另收 bypassPermissions。"
            "要改文件用 permission_mode='auto'（或 acceptEdits）")
    if permission_mode not in PERM_ALIASES:
        raise GSBatchError(
            f"permission_mode 只能是 {' / '.join(PERMISSION_MODES)}"
            f"（也收 acceptEdits=auto、readonly=chat），不传等于 auto，收到：{permission_mode!r}")
    return PERM_ALIASES[permission_mode]


def _check_extensions(exts):
    if exts is None:
        return list(DEFAULT_EXTENSIONS)
    if isinstance(exts, str):
        exts = [s.strip() for s in exts.split(",")]
    out = []
    for e in exts:
        e = str(e).strip()
        if not e:
            continue
        if not _EXT_RE.match(e):
            raise GSBatchError(f"extensions 里要是 goose 内置扩展名（小写字母数字下划线），收到：{e!r}")
        if e not in out:
            out.append(e)
    return out


def _precheck(items, perm: str, exts: list) -> list:
    out = []
    if perm == "chat" or "developer" not in exts:
        for i, it in enumerate(items, 1):
            if _WANTS_WRITE.search(it["prompt"]):
                out.append(f"第 {i} 条看着要写文件，但没挂 developer 扩展（或 permission_mode=chat），"
                           "写不了文件")
    return out


def _zai_key():
    return os.environ.get("ZAI_CODING_PLAN_API_KEY") or os.environ.get("ZHIPU_API_KEY") or ""


def _route(prov: str, effort) -> str:
    """zai_low 直连全局 provider（强度 low 或不设）；别的 zai 走本批代理；codex 直连。"""
    if prov == "zai_low" and effort in (None, "low"):
        return "zai_low"
    if prov in ZAI:
        return "proxy"
    return "direct"


def _task_effort(o: dict, t: dict):
    return t["effort"] if "effort" in t else o.get("effort")


def _provider_name(job_id: str, n: int) -> str:
    return "gsbt_" + job_id.replace("-", "_") + f"_{n}"


def _extra_tools_on(o: dict) -> bool:
    return bool(o.get("extra_tools")) and o["permission_mode"] == "auto" \
        and "developer" in (o.get("extensions") or [])


def _probe_on(o: dict) -> bool:
    return _extra_tools_on(o) and bool(o.get("probe"))


def _review_on(o: dict) -> bool:
    return _extra_tools_on(o) and bool(o.get("review"))


def _extra_tools_arg(o: dict = None) -> str:
    # goose 按空白切分这串（name:ENV=值 … 命令 参数…），路径里不能有空格
    envs = ""
    if o is not None:
        envs += " GSB_PROBE=1" if _probe_on(o) else ""
        envs += " GSB_REVIEW=1" if _review_on(o) else ""
    return (f"{EXTRA_TOOLS_NAME}:GSB_MAX_BLOCK={EXTRA_TOOLS_MAX_BLOCK}{envs} "
            f"{EXTRA_TOOLS_PY} {EXTRA_TOOLS_SCRIPT}")


def _system_prompt(o: dict) -> str:
    if not _extra_tools_on(o):
        return PREAMBLE
    return (PREAMBLE + "\n" + PREAMBLE_TOOLS + ("\n" + PREAMBLE_PROBE if _probe_on(o) else "")
            + ("\n" + PREAMBLE_REVIEW if _review_on(o) else ""))


def _command(d: dict, t: dict, n: int, resume: str = None) -> list:
    o = d["options"]
    prov = o["provider"]
    route = _route(prov, _task_effort(o, t))
    goose_prov = _provider_name(d["id"], n) if route == "proxy" else prov
    cmd = [GOOSE_BIN, "run", "--no-profile", "--output-format", "stream-json",
           "--provider", goose_prov, "--model", t.get("model") or o["model"]]
    if resume:
        cmd += ["--resume", "--session-id", resume]
    else:
        cmd += ["-n", f"gsb-{d['id']}-{n}"]
    if o["permission_mode"] == "auto" and o["extensions"]:
        cmd += ["--with-builtin", ",".join(o["extensions"])]
    if _extra_tools_on(o) and not resume:      # 续接时会话里已经有了，再传会报重名
        cmd += ["--with-extension", _extra_tools_arg(o)]
    if o.get("max_turns"):
        cmd += ["--max-turns", str(o["max_turns"])]
    if o.get("preamble", True):
        cmd += ["--system", _system_prompt(o)]
    cmd += ["-i", "-"]          # 提示词在标准输入
    return cmd


def _env(d: dict, t: dict) -> dict:
    o = d["options"]
    prov = o["provider"]
    env = {k: v for k, v in _child_env().items()
           if not k.startswith("GOOSE_") and not k.startswith("CHATGPT_CODEX_")
           and not _SECRET_NAME.search(k)}
    env.update(GOOSE_DISABLE_KEYRING="1", GOOSE_DISABLE_SESSION_NAMING="true",
               GOOSE_MODE="auto" if o["permission_mode"] == "auto" else "chat",
               GOOSE_CLI_MIN_PRIORITY="0.2")
    effort = _task_effort(o, t)
    route = _route(prov, effort)
    if route == "proxy":
        env["GOOSE_PATH_ROOT"] = str(GROOT)
    if prov in ZAI:
        env["ZAI_CODING_PLAN_API_KEY"] = _zai_key()
    elif effort:
        env["CHATGPT_CODEX_REASONING_EFFORT"] = effort
    return env


def _mask(s: str) -> str:
    return _SECRET.sub(lambda m: (m.group(2) or m.group(3) or "") + "***", s)


def _show_cmd(cmd: list) -> list:
    out = []
    for i, a in enumerate(cmd):
        a = _mask(a)
        if i and cmd[i - 1] == "--system" and len(a) > 60:
            a = a[:60] + f"…（共 {len(a)} 字）"
        elif len(a) > 300:
            a = a[:300] + f"…（共 {len(a)} 字）"
        out.append(a)
    return out


# ----------------------------------------------------------------------
# 本批的 goose 配置根和临时 provider


def _ensure_groot() -> None:
    cfg = GROOT / "config"
    (cfg / "custom_providers").mkdir(parents=True, exist_ok=True)
    f = cfg / "config.yaml"
    if not f.exists():
        f.write_text("GOOSE_TELEMETRY_ENABLED: false\n", encoding="utf-8")


def _provider_file(job_id: str, n: int) -> Path:
    return GROOT / "config" / "custom_providers" / (_provider_name(job_id, n) + ".json")


def _write_provider(job_id: str, n: int, model: str, effort) -> Path:
    """写这条任务的临时自定义 provider。只有变量名，没有 key。"""
    _ensure_groot()
    models = list(ZAI_MODELS)
    if model not in models:
        models.insert(0, model)
    body = {
        "name": _provider_name(job_id, n),
        "engine": "openai",
        "display_name": f"Z.AI Coding Plan via gsbatch proxy ({effort or '-'})",
        "description": "gsbatch 临时 provider：zai_coding_plan 同参数，经本地代理补 reasoning_effort",
        "api_key_env": "ZAI_CODING_PLAN_API_KEY",
        "base_url": f"http://127.0.0.1:{PROXY_PORT}/gsb/{effort or '-'}/{job_id}/{n}{ZAI_PATH}",
        "preserves_thinking": True,
        "dynamic_models": False,
        "models": [{"name": m, "context_limit": 1000000, "reasoning": True} for m in models],
        "supports_streaming": True,
    }
    f = _provider_file(job_id, n)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, f)
    return f


def _sweep_providers(max_age: int = 86400) -> None:
    """执行器被 kill -9 时留下的临时 provider，一天以上的清掉。"""
    try:
        for f in (GROOT / "config" / "custom_providers").glob("gsbt_*.json*"):
            if time.time() - f.stat().st_mtime > max_age:
                f.unlink(missing_ok=True)
    except OSError:
        pass


# ----------------------------------------------------------------------
# 本地代理（补 reasoning_effort、记响应模型和 usage）


def _proxy_ping(port: int = None):
    """返回代理报的 JOBS 目录；没起来返回 None。"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port or PROXY_PORT}/_gsb/ping",
                                    timeout=2) as r:
            s = r.read().decode("utf-8", "replace")
    except Exception:
        return None
    return s[len("gsbatch-proxy "):] if s.startswith("gsbatch-proxy ") else ""


def _ensure_proxy() -> None:
    """代理在就复用，不在就拉起来（常驻）。端口被别的程序占了就报错。"""
    got = _proxy_ping()
    if got == str(JOBS):
        return
    if got is not None:
        raise GSBatchError(
            f"127.0.0.1:{PROXY_PORT} 上的不是这个任务目录的 gsbatch 代理"
            f"（{got or '别的程序'}）。换 GSBATCH_PROXY_PORT 或停掉它")
    JOBS.mkdir(parents=True, exist_ok=True)
    lockf = JOBS.parent / "proxy.lock"
    with open(lockf, "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        if _proxy_ping() == str(JOBS):
            return
        env = {k: v for k, v in _child_env().items() if not _SECRET_NAME.search(k)}
        env.update(GSBATCH_HOME=str(JOBS), GSBATCH_PROXY_PORT=str(PROXY_PORT),
                   GSBATCH_ZAI_UPSTREAM=UPSTREAM)
        with open(JOBS.parent / "proxy.log", "ab") as log:
            subprocess.Popen([sys.executable, "-m", "tools.gsbatch", "_proxy"],
                             cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             env=env, start_new_session=True)
        for _ in range(50):
            time.sleep(0.1)
            got = _proxy_ping()
            if got == str(JOBS):
                return
        raise GSBatchError(f"代理起不来（127.0.0.1:{PROXY_PORT}），看 {JOBS.parent / 'proxy.log'}")


def _ensure_zai_low() -> None:
    """跑 zai_low 前先执行一次 start_proxy.sh（在跑就直接退出），再等端口能连上。"""
    if not ZAI_LOW_START.is_file():
        raise GSBatchError(f"找不到 {ZAI_LOW_START}，zai_low 的代理没装")
    env = {k: v for k, v in _child_env().items() if not _SECRET_NAME.search(k)}
    try:
        subprocess.run(["bash", str(ZAI_LOW_START)], env=env, timeout=15,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GSBatchError(f"start_proxy.sh 跑不起来：{e}") from None
    import socket
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", ZAI_LOW_PORT), timeout=1).close()
            return
        except OSError:
            time.sleep(0.1)
    raise GSBatchError(f"zai_low 的代理 127.0.0.1:{ZAI_LOW_PORT} 连不上")


def _zai_low_window(t0: float, t1: float, model: str) -> dict:
    """在 zai_low 代理的共用日志里找这段时间、这个模型的请求（尽力而为）。"""
    out = {"models": [], "efforts": [], "requests": 0}
    try:
        with open(ZAI_LOW_LOG, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 2_000_000))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return out
    for ln in lines:
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict) or not t0 - 1 <= (rec.get("t") or 0) <= t1 + 1:
            continue
        fw = rec.get("forwarded") or {}
        if fw.get("model") != model:
            continue
        out["requests"] += 1
        for m in rec.get("resp_models") or []:
            if m not in out["models"]:
                out["models"].append(m)
        if fw.get("reasoning_effort") and fw["reasoning_effort"] not in out["efforts"]:
            out["efforts"].append(fw["reasoning_effort"])
    return out


_PROXY_PATH = re.compile(r"^/gsb/([a-z\-]+)/([0-9A-Za-z\-]{1,64})/(\d{1,3})(/.*)$")


def _proxy_main() -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    up = urllib.parse.urlsplit(UPSTREAM)
    lock = threading.Lock()
    zai_efforts = PROVIDER_EFFORTS["zai_coding_plan"]

    def log(job, n, rec):
        jd = JOBS / job
        if not jd.is_dir():
            return
        with lock, open(jd / f"task_{n}.llm.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _plain(self, code, text):
            b = text.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path == "/_gsb/ping":
                return self._plain(200, f"gsbatch-proxy {JOBS}")
            self._forward(b"")

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            self._forward(self.rfile.read(n))

        def _forward(self, body):
            m = _PROXY_PATH.match(self.path)
            if not m:
                return self._plain(404, "gsbatch proxy: 路径要是 /gsb/<effort>/<job>/<n>/api/...")
            eff, job, n, rest = m.groups()
            if eff != "-" and eff not in zai_efforts:
                return self._plain(400, f"gsbatch proxy: effort 不对：{eff}")
            rec = {"t": round(time.time(), 3), "method": self.command, "path": rest}
            if body:
                try:
                    j = json.loads(body)
                    if eff != "-":
                        j["reasoning_effort"] = eff
                        th = j.get("thinking") if isinstance(j.get("thinking"), dict) else {}
                        th["type"] = "enabled"
                        j["thinking"] = th
                        body = json.dumps(j, ensure_ascii=False).encode()
                    rec["forwarded"] = {k: v for k, v in j.items() if k not in ("messages", "tools")}
                    rec["n_messages"] = len(j.get("messages") or [])
                except Exception as e:
                    rec["parse_err"] = repr(e)[:200]
            hdr = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "content-length", "accept-encoding", "connection")}
            hdr["Content-Length"] = str(len(body))
            hdr["Accept-Encoding"] = "identity"
            t0 = time.time()
            try:
                if up.scheme == "https":
                    c = http.client.HTTPSConnection(up.hostname, up.port or 443,
                                                    context=ssl.create_default_context(), timeout=1800)
                else:
                    c = http.client.HTTPConnection(up.hostname, up.port or 80, timeout=1800)
                c.request(self.command, rest, body=body or None, headers=hdr)
                r = c.getresponse()
            except Exception as e:
                rec.update(status=502, error=f"{type(e).__name__}: {e}"[:300])
                log(job, n, rec)
                return self._plain(502, f"gsbatch proxy: 上游连不上：{type(e).__name__}")
            rec["status"] = r.status
            models, usage, rc, tail, buf, first = set(), None, 0, b"", b"", None
            try:
                self.send_response(r.status)
                for k, v in r.getheaders():
                    if k.lower() not in ("transfer-encoding", "content-length", "connection",
                                         "content-encoding"):
                        self.send_header(k, v)
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Connection", "close")
                self.end_headers()
                while True:
                    chunk = r.read1(65536)
                    if not chunk:
                        break
                    if first is None:
                        first = time.time() - t0
                    self.wfile.write(b"%x\r\n" % len(chunk) + chunk + b"\r\n")
                    self.wfile.flush()
                    buf += chunk
                    *lines, buf = buf.split(b"\n")
                    for ln in lines:
                        ln = ln.strip()
                        if ln.startswith(b"data:") and ln[5:].strip() != b"[DONE]":
                            try:
                                ev = json.loads(ln[5:])
                            except Exception:
                                continue
                            if ev.get("model"):
                                models.add(ev["model"])
                            if ev.get("usage"):
                                usage = ev["usage"]
                            for ch in ev.get("choices") or []:
                                rc += len((ch.get("delta") or {}).get("reasoning_content") or "")
                        elif ln and not ln.startswith((b"data:", b":", b"event:")) \
                                and len(tail) < 20000:
                            tail += ln
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                rec["client_gone"] = True
            if tail.strip():
                try:
                    tj = json.loads(tail)
                    if tj.get("model"):
                        models.add(tj["model"])
                    usage = tj.get("usage") or usage
                    if tj.get("error"):
                        rec["error"] = tj["error"]
                except Exception:
                    rec["raw_tail"] = tail[:500].decode("utf-8", "replace")
            rec.update(resp_models=sorted(models), usage=usage, reasoning_chars=rc,
                       sec=round(time.time() - t0, 1), first_byte=first and round(first, 1))
            log(job, n, rec)

    class S(ThreadingHTTPServer):
        daemon_threads = True

    S(("127.0.0.1", PROXY_PORT), H).serve_forever()


# ----------------------------------------------------------------------
# job.json 读写


def _job_dir(job_id: str) -> Path:
    return JOBS / job_id


def _load(job_id: str) -> dict:
    if not re.match(r"^[0-9A-Za-z\-]{1,64}$", str(job_id)):
        raise GSBatchError(f"没有这个任务：{job_id}")
    f = _job_dir(job_id) / "job.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise GSBatchError(f"没有这个任务：{job_id}") from None


def _save(d: dict) -> None:
    f = _job_dir(d["id"]) / "job.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, f)


# ----------------------------------------------------------------------
# 对外接口


def submit(tasks, name: str = "", provider: str = DEFAULT_PROVIDER, model: str = None,
           cwd: str = None, timeout: int = TASK_TIMEOUT, concurrency: int = 1,
           mode: str = "isolated", permission_mode: str = None,
           extensions=None, max_turns: int = None,
           preamble: bool = True, effort: str = DEFAULT_EFFORT,
           extra_tools: bool = True, probe: bool = True, review: bool = True) -> dict:
    """提交一批任务，立刻返回，不等跑完。

    tasks：提示词列表，或 {prompt, model, effort} 字典列表。
        model / effort 缺省跟这批的一样；effort 显式给 None 或空串表示这条不设。
    provider：zai_low（默认，全局 provider + 18766 常驻代理）、zai_coding_plan
        （本批代理，effort=None 时不注入）或 chatgpt_codex（goose 里已登录的账号）。
    model：不传用 provider 的默认（zai = glm-5.3-flash，chatgpt_codex = gpt-6-sol）。
    cwd：不传用任务目录下的空目录。传了按 check_workdir 校验
        （不收 ~、/、家目录、含凭证的目录）。goose 没有沙箱，cwd 只是起点。
    timeout：单条秒数上限，超时杀掉这条的进程组。
    concurrency：isolated 模式下同时跑几条（1~5）。share 一律顺序。
    mode：isolated 各条独立；share 后一条用 --resume --session-id 接前一条的
        会话，前一条失败就开新会话。
    permission_mode：auto（默认，工具自动批准，也收 acceptEdits）或 chat
        （不挂扩展、只回答，也收 readonly）。
    extensions：auto 时挂的 goose 内置扩展，默认 ["developer"]（文件读写 + shell）。
        列表或逗号分隔字符串；[] 表示不挂。
    max_turns：传给 --max-turns，不传不限（靠 timeout 兜底）。
    preamble：把 PREAMBLE 经 --system 追加进系统提示。
    extra_tools：auto 且挂了 developer 时，再挂 gsb_tools 扩展（read_files /
        run_wait / wait_pid，减少调用次数），PREAMBLE 追加两句用法。False 不挂。
    probe：extra_tools 开着时再给 probe / probe_wait（派 Codex CLI gpt-6-luna 只读
        探针做大量阅读 / 调研，只收结论），PREAMBLE 再加一句。花公司 ChatGPT 额度，
        False 关掉。extra_tools 关了它也跟着关。
    review：extra_tools 开着时再给 review / review_wait（派 gpt-6-luna 只读审查员按任务书
        做初步审查、核对报告草稿），PREAMBLE 加第 9~12 句（commit/push、写报告前调 review；
        意见只是线索，先核实再改，通过也不免检，报告里逐条写处理）。
        同样花 ChatGPT 额度，False 关掉。
    effort：推理强度，默认 low。zai：minimal/low/medium/high/max（low 走
        zai_low 的常驻代理，别的走本批代理按请求补 reasoning_effort）；
        chatgpt_codex：minimal/low/medium/high/xhigh。None 或空串不设。

    返回 {"job_id", "status", "tasks", "dir", "provider", "model", "warnings"}。
    """
    prov = _check_provider(provider)
    default_model = _check_model(model, prov)
    job_effort = _norm_effort(effort, prov)
    perm = _perm(permission_mode)
    exts = _check_extensions(extensions)
    items = []
    for t in tasks:
        if isinstance(t, str) and t.strip():
            items.append({"prompt": t, "model": default_model, "effort": job_effort})
        elif isinstance(t, dict) and str(t.get("prompt") or "").strip():
            items.append({
                "prompt": t["prompt"],
                "model": _check_model(t["model"], prov) if t.get("model") else default_model,
                "effort": _norm_effort(t["effort"], prov) if "effort" in t else job_effort,
            })
        else:
            raise GSBatchError(f"任务要是非空字符串或含 prompt 的字典，收到：{t!r}")
    if not items:
        raise GSBatchError("一条任务都没有")
    if len(items) > MAX_TASKS:
        raise GSBatchError(f"一次最多 {MAX_TASKS} 条，这次给了 {len(items)} 条。")
    if mode not in ("share", "isolated"):
        raise GSBatchError(f"mode 只能是 share 或 isolated，收到：{mode}")
    try:
        concurrency = int(concurrency)
        timeout = int(timeout)
        max_turns = int(max_turns) if max_turns not in (None, "", 0) else None
    except (TypeError, ValueError):
        raise GSBatchError("concurrency / timeout / max_turns 要是整数") from None
    if not 1 <= concurrency <= MAX_CONCURRENCY:
        raise GSBatchError(f"concurrency 要在 1~{MAX_CONCURRENCY}，收到：{concurrency}")
    if timeout < 1:
        raise GSBatchError("timeout 要大于 0")
    if max_turns is not None and max_turns < 1:
        raise GSBatchError("max_turns 要大于 0")
    if shutil.which(GOOSE_BIN) is None and not Path(GOOSE_BIN).is_file():
        raise GSBatchError(f"找不到 {GOOSE_BIN}，goose 装了吗？")
    if prov in ZAI and not _zai_key():
        raise GSBatchError(
            f"环境里没有 ZHIPU_API_KEY（或 ZAI_CODING_PLAN_API_KEY），{prov} 用不了。"
            "调用方（MCP 服务 / batchmgr）的环境里得有这个变量")
    warnings = _precheck(items, perm, exts)
    if perm == "chat" and extensions:
        warnings.append("permission_mode=chat 不挂扩展，extensions 忽略")
    if cwd:
        try:
            cwd = check_workdir(cwd)
        except UnsafeWorkdirError as e:
            raise GSBatchError(f"cwd 不能用：{e}") from None

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
        "options": {"provider": prov, "model": default_model, "timeout": timeout,
                    "concurrency": concurrency, "permission_mode": perm,
                    "extensions": exts if perm == "auto" else [],
                    "max_turns": max_turns, "preamble": bool(preamble),
                    "effort": job_effort,
                    "extra_tools": bool(extra_tools) and perm == "auto" and "developer" in exts,
                    "probe": bool(probe) and bool(extra_tools) and perm == "auto"
                    and "developer" in exts,
                    "review": bool(review) and bool(extra_tools) and perm == "auto"
                    and "developer" in exts},
        "warnings": warnings, "cmd": None,
        "tasks": [dict(it, status="pending", output="", error="", session_id=None,
                       seconds=None, tokens=None, cost_usd=None, cost_est_usd=None,
                       model_used=None, tool_calls=0, rc=None, stderr="", cmd=None)
                  for it in items],
    }
    d["cmd"] = _show_cmd(_command(d, {"prompt": "<提示词>", "model": default_model}, 1))
    _save(d)

    subprocess.run([sys.executable, "-m", "tools.gsbatch", "_detach", job_id],
                   cwd=str(ROOT), stdin=subprocess.DEVNULL, check=True,
                   env=dict(os.environ, GSBATCH_HOME=str(JOBS)))
    return {"job_id": job_id, "status": "queued", "tasks": len(items), "dir": str(jd),
            "provider": prov, "model": default_model, "warnings": warnings}


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
    """取消：杀掉执行器和每条正在跑的 goose（按记下的进程组），没跑的标成 cancelled。"""
    d = _load(job_id)
    if d["status"] not in ("queued", "running"):
        return {"job_id": job_id, "status": d["status"], "note": "已经结束了"}
    if not d.get("pid"):
        raise GSBatchError("执行器还没起来，过几秒再取消")
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
    for n in range(1, len(d["tasks"]) + 1):
        _provider_file(job_id, n).unlink(missing_ok=True)
    d = _load(job_id)
    d["status"] = "cancelled"
    d["finished"] = _now()
    for t in d["tasks"]:
        if t["status"] in ("pending", "running"):
            t["status"] = "cancelled"
    _save(d)
    return {"job_id": job_id, "status": "cancelled"}


def describe() -> str:
    exe = shutil.which(GOOSE_BIN) or (GOOSE_BIN if Path(GOOSE_BIN).is_file() else None)
    px = _proxy_ping()
    lines = [f"执行端：{exe or f'找不到 {GOOSE_BIN}'}", f"任务目录：{JOBS}",
             f"goose 配置根（非 low 的 zai 用）：{GROOT}",
             f"zai_low 代理：127.0.0.1:{ZAI_LOW_PORT}（{ZAI_LOW_START}）",
             f"本批代理：127.0.0.1:{PROXY_PORT} → {UPSTREAM}"
             + ("（在跑）" if px == str(JOBS) else "（没在跑，第一次用 zai 时自动拉起）"
                if px is None else f"（端口被占：{px or '别的程序'}）"),
             "zai key：" + ("环境里有" if _zai_key() else "环境里没有 ZHIPU_API_KEY，zai 用不了")]
    js = jobs(5)
    lines.append(f"最近 {len(js)} 个任务" if js else "还没有任务")
    for j in js:
        lines.append(f"  {j['id']}  {j['status']:10} {j['progress']:6} {j['name'][:30]}")
    lines += [
        "",
        "provider / model：",
        "  zai_low（默认）          默认 glm-5.3-flash、effort low；全局 provider zai_low，",
        "                           经 18766 常驻代理补 low；响应模型按时间窗对日志（尽力而为）",
        "  zai_low + 别的强度 / zai_coding_plan  经本批代理，按任务记响应模型和推理 token",
        "  chatgpt_codex            goose 里已登录的账号，默认 gpt-6-sol；拿不到实际响应模型",
        "",
        "推理强度 effort（默认 low，也收 极低/低/中/高/极高）：",
        "  zai：minimal / low / medium / high / max，代理往请求里补 reasoning_effort",
        "       （zai_coding_plan + None = 不补，服务器缺省 ≈ max）",
        "  chatgpt_codex：minimal / low / medium / high / xhigh，走 CHATGPT_CODEX_REASONING_EFFORT",
        "  None 或空串 = 不设。单条可在任务字典里覆盖。",
        "",
        "权限（goose 没有沙箱）：",
        "  不传 / auto / acceptEdits  GOOSE_MODE=auto，挂 extensions（默认 developer），工具自动批准，",
        "                             能写 cwd 以外的地方",
        "  chat / readonly            不挂扩展，只回答",
        "  approve / smart_approve / bypassPermissions 不收",
        "",
        "extra_tools（默认开，auto + developer 时）：再挂 gsb_tools 扩展：read_files 一次读多个文件、",
        f"  run_wait 跑命令阻塞等结束、wait_pid 等已在跑的进程；单次调用最多阻塞 {EXTRA_TOOLS_MAX_BLOCK} 秒",
        "  （goose 对扩展 300 秒超时），没跑完返回 still_running。extra_tools=False 不挂。",
        "probe（默认开，跟着 extra_tools）：再给 probe / probe_wait，把大量阅读 / 对照 / 调研派给",
        "  Codex CLI gpt-6-luna 只读探针（-s read-only），只收结论；wait=false 并行派，probe_wait 一起等。",
        "  花公司 ChatGPT 额度，probe=False 关掉。",
        "review（默认开，跟着 extra_tools）：再给 review / review_wait，派 gpt-6-luna 只读审查员按任务书",
        "  做初步审查（默认工作区 diff，base 给了审 base..HEAD），核对报告草稿；PREAMBLE 第 9~12 句要求",
        "  commit/push、写最终报告前调，意见先核实再改、通过也自己逐条核对、报告逐条写处理。review=False 关掉。",
        "",
        "mode=share 用 --resume --session-id 接上一条的会话。isolated 可用 concurrency（1~5）。",
        "每条的原始事件流在任务目录 task_<n>.raw.jsonl / task_<n>.stderr.log，",
        "zai 的每次请求记录在 task_<n>.llm.jsonl。费用走订阅，cost_usd 留空，goose 自估放 cost_est_usd。",
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------------
# 执行器（在后台进程里跑）


def _err_text(e) -> str:
    if isinstance(e, dict):
        msg = e.get("message") or e.get("error") or e
        if isinstance(msg, dict):
            msg = msg.get("message") or json.dumps(msg, ensure_ascii=False)
        return str(msg)[:500]
    return str(e)[:500]


def _parse(stdout: str) -> dict:
    """stream-json → {text, session_id, complete, error, tool_calls, requested_model}。"""
    r = {"msgs": [], "session_id": None, "complete": None, "error": "",
         "tool_calls": 0, "requested_model": None}
    cur_id = None
    for line in stdout.splitlines():
        s = line.strip()
        if not s.startswith("{"):
            if r["session_id"] is None:
                m = _SESSION_RE.search(s)
                if m:
                    r["session_id"] = m.group(1)
            continue
        try:
            e = json.loads(s)
        except json.JSONDecodeError:
            continue
        if not isinstance(e, dict):
            continue
        typ = e.get("type")
        if typ == "message":
            msg = e.get("message") or {}
            inf = (msg.get("metadata") or {}).get("inference") or {}
            if inf.get("requestedModel"):
                r["requested_model"] = inf["requestedModel"]
            for c in msg.get("content") or []:
                ct = c.get("type") if isinstance(c, dict) else None
                if ct == "text" and msg.get("role") == "assistant" and c.get("text"):
                    if msg.get("id") != cur_id or not r["msgs"]:
                        r["msgs"].append("")
                        cur_id = msg.get("id")
                    r["msgs"][-1] += c["text"]
                elif ct == "toolRequest":
                    r["tool_calls"] += 1
                    cur_id = None
                elif ct == "error":
                    r["error"] = _err_text(c)
        elif typ == "error":
            r["error"] = _err_text(e.get("error") if e.get("error") is not None else e)
        elif typ == "complete":
            r["complete"] = e
    r["text"] = "\n\n".join(x.strip() for x in r["msgs"] if x.strip())
    return r


def _llm_summary(jd: Path, n: int) -> dict:
    """代理记的这条请求：实际响应模型、按请求累加的 usage、强度、出错。"""
    f = jd / f"task_{n}.llm.jsonl"
    out = {"models": [], "tokens": None, "efforts": [], "requests": 0, "errors": []}
    try:
        lines = f.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    tok = {"input": 0, "cached_input": 0, "output": 0, "reasoning": 0}
    seen = False
    for ln in lines:
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        out["requests"] += 1
        for m in rec.get("resp_models") or []:
            if m not in out["models"]:
                out["models"].append(m)
        eff = (rec.get("forwarded") or {}).get("reasoning_effort")
        if eff and eff not in out["efforts"]:
            out["efforts"].append(eff)
        if rec.get("error") or (rec.get("status") or 200) >= 400:
            out["errors"].append(f"HTTP {rec.get('status')} {_err_text(rec.get('error') or rec.get('raw_tail') or '')}")
        u = rec.get("usage")
        if isinstance(u, dict):
            seen = True
            tok["input"] += u.get("prompt_tokens") or 0
            tok["cached_input"] += (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
            tok["output"] += u.get("completion_tokens") or 0
            tok["reasoning"] += (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    if seen:
        out["tokens"] = tok
    return out


def _goose_tokens(c: dict, prev: dict = None):
    """complete 事件 → tokens。续接时减掉上一条的会话累计。"""
    if not isinstance(c, dict):
        return None, None
    tot = {"input": c.get("input_tokens") or 0, "cached_input": c.get("cache_read_input_tokens") or 0,
           "output": c.get("output_tokens") or 0, "reasoning": None,
           "total": c.get("total_tokens") or 0}
    if prev:
        tok = {k: (tot[k] - (prev.get(k) or 0)) if tot[k] is not None else None for k in tot}
    else:
        tok = dict(tot)
    return tok, tot


def _run_one(d: dict, t: dict, resume: str = None, n: int = 1, prev_total: dict = None) -> None:
    """跑一条，结果写回 t。不抛异常。"""
    jd = _job_dir(d["id"])
    o = d["options"]
    prov = o["provider"]
    effort = _task_effort(o, t)
    route = _route(prov, effort)
    model = t.get("model") or o["model"]
    cmd = _command(d, t, n, resume)
    t["cmd"] = _show_cmd(cmd)
    t["route"] = route
    pfile = None
    try:
        if route == "proxy":
            _ensure_proxy()
            pfile = _write_provider(d["id"], n, model, effort)
        elif route == "zai_low":
            _ensure_zai_low()
    except (GSBatchError, OSError) as e:
        t.update(status="error", error=f"zai 代理 / provider 准备失败：{e}", seconds=0)
        return

    def keep(out, err):
        for name, s in ((f"task_{n}.raw.jsonl", out), (f"task_{n}.stderr.log", err)):
            if isinstance(s, bytes):
                s = s.decode("utf-8", "replace")
            try:
                (jd / name).write_text(_mask(s or ""), encoding="utf-8")
            except OSError:
                pass

    t0 = time.time()
    try:
        p = subprocess.Popen(cmd, cwd=d["cwd"], env=_env(d, t), stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             start_new_session=True)
    except OSError as e:
        if pfile:
            pfile.unlink(missing_ok=True)
        t.update(status="error", error=f"起不来 goose：{e}", seconds=0)
        return
    (jd / f"task_{n}.pid").write_text(str(p.pid))
    try:
        out, err = p.communicate(t["prompt"], timeout=o["timeout"])
        timed_out = False
    except subprocess.TimeoutExpired:
        _killpg(p.pid)
        out, err = p.communicate()
        timed_out = True
    (jd / f"task_{n}.pid").unlink(missing_ok=True)
    if pfile:
        pfile.unlink(missing_ok=True)
    keep(out, err)
    t["seconds"] = round(time.time() - t0, 1)
    t["rc"] = p.returncode
    t["stderr"] = _mask((err or "").strip()[-500:])

    parsed = _parse(out or "")
    text = parsed["text"]
    if len(text) > MAX_OUTPUT:
        text = text[:MAX_OUTPUT] + f"\n…（输出太长，已截断，共 {len(text)} 字）"
    gtok, gtot = _goose_tokens(parsed["complete"], prev_total)
    llm = _llm_summary(jd, n) if route == "proxy" else None
    t.update(output=text, session_id=parsed["session_id"] or resume,
             tool_calls=parsed["tool_calls"], session_tokens=gtot,
             cost_est_usd=(parsed["complete"] or {}).get("cost_usd"))
    if llm and llm["tokens"]:
        t["tokens"] = dict(llm["tokens"], total=llm["tokens"]["input"] + llm["tokens"]["output"])
    else:
        t["tokens"] = gtok
    if llm:
        t["model_used"] = ", ".join(llm["models"]) or None
        t["llm_requests"] = llm["requests"]
        t["effort_sent"] = ", ".join(llm["efforts"]) or None
        t["model_used_src"] = "本批代理 task_<n>.llm.jsonl"
    elif route == "zai_low":
        w = _zai_low_window(t0, time.time(), model)
        t["model_used"] = ", ".join(w["models"]) or None
        t["llm_requests"] = w["requests"]
        t["effort_sent"] = ", ".join(w["efforts"]) or None
        t["model_used_src"] = "zai_low 代理日志按时间窗匹配（同时段别的请求会混进来）"
        t["model_requested"] = parsed["requested_model"]
    else:
        t["model_used"] = None
        t["model_requested"] = parsed["requested_model"]
    if timed_out:
        t.update(status="timeout", error=f"超过 {o['timeout']} 秒，已杀掉")
        return
    perr = parsed["error"] or (llm["errors"][-1] if llm and llm["errors"] else "")
    if p.returncode != 0:
        t.update(status="error",
                 error=(f"退出码 {p.returncode} " + (perr or t["stderr"])).strip())
    elif parsed["error"]:
        t.update(status="error", error=parsed["error"])
    elif parsed["complete"] is None:
        t.update(status="error", error="goose 没有发 complete 事件" + (f"：{perr}" if perr else ""))
    elif not text:
        t.update(status="error", error="goose 正常退出但没有文本输出" + (f"：{perr}" if perr else ""))
    else:
        t["status"] = "done"


def _detach(job_id: str) -> None:
    with open(_job_dir(job_id) / "runner.log", "ab") as log:
        subprocess.Popen([sys.executable, "-m", "tools.gsbatch", "_run", job_id],
                         cwd=str(ROOT), stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)


def _run(job_id: str) -> None:
    jd = _job_dir(job_id)
    cancelled = lambda: (jd / "cancel").exists()   # noqa: E731

    d = _load(job_id)
    d.update(status="running", started=_now(), pid=os.getpid())
    _save(d)
    _sweep_providers()
    lock = threading.Lock()

    def save():
        with lock:
            if not cancelled():
                _save(d)

    def work(n, t, resume=None, prev_total=None):
        if cancelled():
            return
        w = dict(t, status="running")
        with lock:
            t["status"] = "running"
        save()
        try:
            _run_one(d, w, resume, n, prev_total)
        except Exception as e:     # 一条坏了不拖垮整批
            w.update(status="error", error=f"执行器出错：{type(e).__name__}: {e}")
        with lock:
            t.clear()
            t.update(w)
        save()

    if d["mode"] == "share":
        prev, prev_total, prev_root = None, None, None
        for n, t in enumerate(d["tasks"], 1):
            if cancelled():
                break
            root = _route(d["options"]["provider"], _task_effort(d["options"], t)) == "proxy"
            if prev and root != prev_root:
                prev, prev_total = None, None     # 会话存在另一个配置根里，接不上
            work(n, t, prev, prev_total)
            prev_root = root
            ok = t["status"] == "done" and t.get("session_id")
            prev = t["session_id"] if ok else None
            prev_total = t.get("session_tokens") if ok else None
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
    elif len(sys.argv) == 2 and sys.argv[1] == "_proxy":
        _proxy_main()
    else:
        print(describe())
