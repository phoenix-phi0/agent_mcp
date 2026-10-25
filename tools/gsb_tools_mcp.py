# -*- coding: utf-8 -*-
"""gsbatch 给 goose 任务挂的小 MCP 服务器（stdio，纯标准库）。

goose 1.55 每轮只执行一个工具，所以这里的工具都一次做完多步：

- read_files：一次读多个文件（可带行号范围、可用 glob），带行号返回。
- multi_edit：一次对同一文件多处或多个文件做 before→after 精确替换（默认原子提交）。
- run_wait：跑一条 shell 命令并阻塞等它结束，返回退出码、用时、输出末尾。
- wait_pid：等一个已经在跑的进程结束（比如后台跑的回归），返回 log 末尾。
- list_iface_templates / check_iface_template / write_iface_template：管理
  tools/dslagent/templates/iface/*.zs 接口封装模板（列、校验、参数化写入）。
  只写该目录，先按 iftpl 同一套解析校验通过才落盘；不要手改 iftpl.py。
- probe / probe_wait（GSB_PROBE=1 时才有）：把大量阅读 / 对照 / 调研派给只读探针，
  只收回最后一条回复。后端由 GSB_PROBE_BACKEND 选择：claude（默认，Claude CLI claude-haiku-5-5，plan 模式，
  只挂 builtins + gsb_read_files，关 connectors）或 codex（codex exec
  gpt-6-luna，-s read-only）。后台跑、可并行；单次最多阻塞
  GSB_MAX_BLOCK 秒，没跑完返回 still_running + probe_id，再调 probe_wait。
- GSB_TOOLS_ONLY：逗号分隔工具名（如 read_files），只暴露这些工具。给 Claude /
  Codex 探针挂「仅多文件读取」MCP 时用，避免带上 multi_edit / Notion 等。
- review / review_wait（GSB_REVIEW=1 时才有）：始终走 Codex 只读执行，派一个审查员
  按任务书独立审查改动（工作区 diff 或 base..HEAD），按固定格式交回「通过 / 有问题」
  和问题清单。codex 用 ~/.codex/auth.json
  的 ChatGPT 登录（靠 HOME），不需要也不放行任何密钥环境变量。
- verify / verify_wait（GSB_VERIFY=1 时才有）：始终走 Codex，但用 workspace-write 沙箱、
  工作目录锁在自己的临时目录 /tmp/verify_<id>/（起本地服务要监听端口，放开 network_access），
  派验证 agent 做全量回归 / 起服务逐接口实测 / 基线对比：它自己摸项目、优先用项目已有入口、
  没有才写临时脚本；被验项目与仓库只读，结束时核对它们的 git status / 文件清单，
  变了在结果里标「违规改动」。最终回复严格按 JSON 交回（必须带「环境」：解释器、引擎、
  起法），解析时核对其解释器是不是被验仓库的 .venv、引擎是不是被验仓库里那份，
  不符就在摘要里标「⚠ 环境不符」，结论按「无法验证」对待。

goose 对 stdio 扩展的单次工具调用有超时（--with-extension 固定 300 秒，
命令行改不了），所以单次调用最多阻塞 GSB_MAX_BLOCK 秒（默认 270）。
命令没跑完就返回 still_running + pid + log_path，进程继续跑，
模型再调 wait_pid 接着等；命令自己的 timeout_secs 到了由后台线程杀进程组。

安全：启动时就把名字像凭证的环境变量（*TOKEN*、*API_KEY* 等），以及
把凭证嵌进值里的壳变量（如 __CURSOR_SANDBOX_ENV_RESTORE）从本进程环境
里删掉；跑命令 / 探针时再滤一遍，避免 env/printenv 把密钥露给模型。
"""

import difflib
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
from pathlib import Path

_SECRET_NAME = re.compile(r"TOKEN|SECRET|PASSW|API_?KEY|ACCESS_KEY|PRIVATE_KEY|CREDENTIAL", re.I)
# Cursor 沙箱会把被藏起来的密钥塞进这个“恢复脚本”环境变量的值里；变量名本身
# 不含 TOKEN，旧逻辑漏掉后，子进程 env/printenv 会把真实凭证露给模型。
_DROP_ENV_EXACT = frozenset({"__CURSOR_SANDBOX_ENV_RESTORE"})
_SECRET_IN_VALUE = re.compile(
    r"\bexport\s+[A-Z0-9_]*(?:TOKEN|SECRET|PASSW|API_?KEY|ACCESS_KEY|PRIVATE_KEY|CREDENTIAL)[A-Z0-9_]*\s*=",
    re.I,
)


def _leaky_env(k: str, v: str = "") -> bool:
    if k in _DROP_ENV_EXACT or k.startswith("__CURSOR_SANDBOX_ENV"):
        return True
    if _SECRET_NAME.search(k):
        return True
    if v and _SECRET_IN_VALUE.search(v):
        return True
    return False


for _k in [k for k in list(os.environ) if _leaky_env(k, os.environ.get(k, ""))]:
    os.environ.pop(_k, None)

SERVER = {"name": "gsb_tools", "version": "1.0"}
MAX_BLOCK = max(1, int(os.environ.get("GSB_MAX_BLOCK") or 270))
LOG_DIR = os.environ.get("GSB_LOG_DIR") or "/tmp/gsb_tools"
_START_TS = time.strftime("%Y%m%d-%H%M%S")   # 本进程启动时间（编辑备份目录用）
MAX_FILES = 50
DEF_PER_FILE, DEF_TOTAL = 60000, 200000
MAX_TIMEOUT = 3600
PROBE_ON = os.environ.get("GSB_PROBE") == "1"
REVIEW_ON = os.environ.get("GSB_REVIEW") == "1"
_PROBE_BACKEND_RAW = (os.environ.get("GSB_PROBE_BACKEND") or "claude").strip().lower()
PROBE_BACKEND = _PROBE_BACKEND_RAW if _PROBE_BACKEND_RAW in ("codex", "claude") else "claude"
PROBE_MODEL = os.environ.get("GSB_PROBE_MODEL") or (
    "claude-haiku-5-5" if PROBE_BACKEND == "claude" else "gpt-6-luna")
REVIEW_MODEL = os.environ.get("GSB_REVIEW_MODEL") or "gpt-6-luna"
VERIFY_ON = os.environ.get("GSB_VERIFY") == "1"
VERIFY_MODEL = os.environ.get("GSB_VERIFY_MODEL") or "gpt-6-luna"
PROBE_EFFORTS = ("low", "medium", "high")
PROBE_MAX_TIMEOUT = 1800
PROBE_MAX_REPLY = 30000
_PROBE_DIR = Path(__file__).resolve().parent
PROBE_CLAUDE_RUN = _PROBE_DIR / "probe_claude_run.py"
PROBE_CLAUDE_MCP = os.environ.get("GSB_PROBE_CLAUDE_MCP") or str(_PROBE_DIR / "probe_claude_mcp.json")
PROBE_CLAUDE_SETTINGS = os.environ.get("GSB_PROBE_CLAUDE_SETTINGS") or str(
    _PROBE_DIR / "probe_claude_settings.json")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,79}$")
PROBE_PREAMBLE = """你是一个只读探针，另一个 agent 把阅读 / 对照 / 调研的活派给你，只收你的结论。规则：
1. 只读：不创建、修改、删除任何文件，不用 git 的写操作（commit / checkout / reset / stash / push 等），不装东西。
2. 结论要带依据：文件路径和行号（path:line）。
3. 只交回要求的内容和格式，不复述过程。
4. 你的最后一条回复就是交付结果。
5. 一次读多个文件或同一文件多段时，优先用 read_files（若有该工具），不要分多次 cat/sed。

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


# verify 的固定前言：只验证不修、只写自己的临时目录、运行环境必须是被验仓库自己的
# .venv + 引擎、优先项目已有入口、结论带证据、严格 JSON（带「环境」字段）。
VERIFY_PREAMBLE = """你是验证 agent：主任务只交代「验什么」，你自己去摸项目、写临时脚本、跑，只交回结论。规则：
1. 只做验证不修东西：发现 bug 如实写进「发现」，不修、不顺手改进；不改被验项目和它所在仓库的任何文件，引擎仓库（见第 3 条，与被验仓库分离时两边都不许改）也不许动，不用 git 写操作（add/commit/checkout/reset/stash 等）动被验仓库。
2. 你只能写自己的临时目录 {tmp}（沙箱强制，别处写不进去）：要实验先把被验项目拷进来（cp -a），临时脚本也放这里。拷进临时目录的只是被验「项目」（数据、约定、.zs/.ui），引擎代码不拷。
3. 运行环境（有过教训：验证员用了别的目录下的旧引擎快照加系统 python，得出过时的「不通过」）：
   - Python 解释器：{env_py} 不要用系统 python3 / python（缺依赖，也不能证明是被验仓库的环境）。
   - 引擎代码（gen、tools、verbs）：{env_repo}。不要用别的目录（如 /workspace/dslagent_exp 下其他快照）的 gen / tools / verbs；不确定就先跑 python -c "import gen,tools;print(gen.__file__,tools.__file__)" 核对。
   - 起法优先用项目已有入口和 README / 报告里写过的起法（如 kg 项目用 make_app(real=False, login=…)）；`gen run` 会编译全部 .ui，项目里有还没实现接口的 .ui 时会编译不过——这属进行中的正常中间态，写进「发现」，换不编译 .ui 的起法（如 tools.dsl_http.Router / make_app）继续验，不要因此判业务不通过。
4. 先摸清项目怎么跑：README、现有测试、回归 / 冒烟入口（如 tools/dslagent/v3 的回归、接口冒烟）；优先用项目已有入口，没有才自己写临时脚本。
5. 起本地服务时日志写文件别接管道；记下 PID，结束时按进程组停掉（kill -TERM -PGID），不要用 pkill。
6. 结论必须有证据：每项检查给出跑的命令和关键输出原文片段；多读文件可用 read_files 工具（若挂着）。
7. 不读取、不打印任何 key、token、认证文件；不装新依赖。
8. 最后一条回复就是交付结果，严格按这个 JSON 交回，不要包代码围栏、不要附加别的文字：
{{"状态": "成功|失败", "结果": {{"结论": "通过|不通过|无法验证", "环境": {{"python": "实际用的解释器绝对路径", "引擎": "实际 import 的 gen / tools 绝对路径（用 python -c 'import gen,tools;print(gen.__file__,tools.__file__)' 取）", "起法": "实际起服务 / 跑回归用的命令"}}, "检查": [{{"项": "...", "通过": true/false, "证据": "命令与关键输出"}}], "发现": ["不在要求内但发现的问题"], "说明": "..."}}}}
（「状态」= 验证本身有没有跑完；「结果.结论」= 被验对象过没过；「环境」必填：python 必须是引擎仓库的 .venv、引擎必须在引擎仓库根下（引擎仓库通常就是被验项目所在仓库，分离时按主任务交代的引擎仓库判），不符就只能给「无法验证」。）

被验项目：{project}
{base_line}验证任务：
{instructions}
"""


def _repo_root_of(proj):
    """从被验项目推引擎仓库根：git toplevel 优先；非 git 就向上找带 gen/ + tools/ 的
    目录。推不出返回 None（前言里交代「先找仓库的 .venv」）。"""
    rc, top = _git(proj, "rev-parse", "--show-toplevel")
    if rc == 0:
        return os.path.realpath(top.strip())
    d = os.path.realpath(proj)
    if not os.path.isdir(d):
        d = os.path.dirname(d)
    while True:
        if os.path.isdir(os.path.join(d, "gen")) and os.path.isdir(os.path.join(d, "tools")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return None
        d = up


def _upward_repo(d):
    """从 d 向上找带 gen/ + tools/ 的目录（引擎仓库根），找不到返回 None。"""
    d = os.path.realpath(os.path.expanduser(str(d)))
    while True:
        if os.path.isdir(os.path.join(d, "gen")) and os.path.isdir(os.path.join(d, "tools")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return None
        d = up


def _engine_repo_of(proj, engine_repo=None, cwd=None):
    """定引擎仓库根（前言的 .venv / PYTHONPATH 和交付时的「环境」核对都用它）：
    显式 engine_repo → 被验项目向上探测（_repo_root_of）→ 调用方 cwd（或 MCP 进程 cwd）
    向上找带 gen/ + tools/ 的仓库根。都没有返回 None（前言交代「先找」）。"""
    if engine_repo not in (None, ""):
        d = os.path.realpath(os.path.expanduser(str(engine_repo)))
        if not os.path.isdir(d):
            raise ValueError(f"engine_repo 不是目录：{d}")
        if not (os.path.isdir(os.path.join(d, "gen")) and os.path.isdir(os.path.join(d, "tools"))):
            raise ValueError(f"engine_repo 要是带 gen/ 和 tools/ 的引擎仓库根：{d}")
        return d
    repo = _repo_root_of(proj)
    if repo:
        return repo
    return _upward_repo(cwd or os.getcwd())


def _env_lines(proj, repo=None):
    """前言里的运行环境交代：返回 (引擎仓库根或 None, 解释器句, 引擎句)。repo 缺省时
    从被验项目自己推（旧口径）；verify 传 _engine_repo_of 定出的引擎仓库根。"""
    repo = _repo_root_of(proj) if repo is None else repo
    if repo:
        py = os.path.join(repo, ".venv", "bin", "python")
        env_py = (f"一律用 {py}。" if os.path.isfile(py)
                  else f"引擎仓库（{repo}）下没有 {py}：不要改用系统 python 或别处的解释器"
                       f"（交付时「环境」核对要求解释器在该仓库 .venv 下，不符按无法验证）；"
                       f"找不到就如实写进「说明」，结论给「无法验证」。")
        env_repo = (f"一律用引擎仓库（{repo}）里的那份，跑任何 python 前设 PYTHONPATH={repo}；"
                    f"不要拷引擎进临时目录")
    else:
        env_py = "先找被验仓库的 .venv/bin/python"
        env_repo = ("先从被验项目向上找仓库根（带 gen/ 和 tools/ 的那份；被验项目推不出，"
                    "再从当前工作目录向上找），跑任何 python 前"
                    "设 PYTHONPATH 指向它；实在推不出，把找的过程和结果如实写进「说明」")
    return repo, env_py, env_repo

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


# read_files 的凭证黑名单：basename 精确 / 通配 / 包含，加上路径片段，全部大小写不敏感。
_READ_DENY_NAMES = frozenset({"auth.json", ".auth_secret", ".env", ".netrc", ".git-credentials"})


def _deny_read(path):
    """True 表示疑似凭证文件，read_files 拒读。"""
    low = str(path).replace("\\", "/").lower()
    name = low.rsplit("/", 1)[-1]
    if name in _READ_DENY_NAMES:
        return True
    if name.endswith((".pem", ".key")) or name.startswith("id_rsa") \
            or "credential" in name or "secret" in name:
        return True
    if "/.ssh/" in low:                 # .ssh 整目录都是凭证
        return True
    if "/.codex/" in low:               # codex 只拦凭证类，普通日志 / 会话记录放行
        return (name in ("auth.json", "tokens.json", ".credentials.json")
                or "token" in name or "credential" in name or "secret" in name
                or name.endswith((".pem", ".key")))
    return False


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
            deny = [h for h in hits if _deny_read(h)]
            hits = [h for h in hits if not _deny_read(h)]
            if not hits and not deny:
                specs.append(dict(sp, path=p, err="glob 没匹配到文件"))
            for h in hits:
                specs.append(dict(sp, path=h))
            for h in deny:
                specs.append(dict(sp, path=h, deny=True))
        else:
            specs.append(dict(sp, path=p, deny=_deny_read(p)))
    parts, used, n_ok, n_err, n_deny, skipped = [], 0, 0, 0, 0, []
    if len(specs) > MAX_FILES:
        skipped = [s["path"] for s in specs[MAX_FILES:]]
        specs = specs[:MAX_FILES]
    for sp in specs:
        left = total_cap - used
        if left < 200:
            skipped.append(sp["path"])
            continue
        if sp.pop("deny", False):
            parts.append(f"===== {sp['path']}：拒绝读取（疑似凭证文件） =====\n")
            n_deny += 1
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
    if n_deny:
        summary += f"，拒绝读取 {n_deny} 个（疑似凭证文件）"
    if skipped:
        summary += f"；超出总上限 {total_cap} 字或 {MAX_FILES} 个文件，没读：" + ", ".join(skipped[:20])
        if len(skipped) > 20:
            summary += f" 等 {len(skipped)} 个"
    return "\n".join(parts) + f"\n[{summary}]"


# ----------------------------------------------------------------------
# multi_edit（精确替换，可多文件 / 同文件多处；默认原子）

MAX_EDITS = 20
DIFF_PER_EDIT = 1500
DIFF_TOTAL = 6000
_BLOCKED_BASENAMES = frozenset({"config.json"})


def _edit_hint(text, before):
    """找不到时给点线索：有没有长得像的行（对齐 fsedit._hint）。"""
    first = before.strip().splitlines()[0] if before.strip() else ""
    if not first:
        return ""
    probe = first[:20]
    hits = [r for r in text.splitlines() if probe in r]
    if not hits:
        return "连近似的行都没有，确认路径和内容对不对。"
    return ("有这么几行看着像，注意空格和引号：\n"
            + "\n".join("  " + h for h in hits[:3]))


def _edit_diff(before, after, path, cap):
    """只显示变化的那几行；超 cap 截断。"""
    rows = list(difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile=path, tofile=path, lineterm="", n=2))
    s = "\n".join(rows)
    if len(s) > cap:
        s = s[:cap] + f"\n…（diff 截断，共 {len(s)} 字）"
    return s


def _writable_path(path, cwd=None):
    """任务工作目录内可写路径：不限 data/，但拒 .git 与 config.json。"""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path 要是非空字符串")
    wd = os.path.realpath(cwd or os.getcwd())
    if not os.path.isdir(wd):
        raise ValueError(f"cwd 不是目录：{wd}")
    abs_p = os.path.realpath(_resolve(path, wd))
    if abs_p != wd and not abs_p.startswith(wd + os.sep):
        raise ValueError(f"路径越界：只能改任务工作目录内的文件（{wd}），收到：{path}")
    parts = Path(abs_p).parts
    if ".git" in parts:
        raise ValueError(f"拒绝改 .git 下的路径：{path}")
    if Path(abs_p).name in _BLOCKED_BASENAMES:
        raise ValueError(f"拒绝改受保护文件：{Path(abs_p).name}")
    if not os.path.isfile(abs_p):
        if os.path.isdir(abs_p):
            raise ValueError(f"是目录，不是文件：{path}")
        raise ValueError(f"文件不存在：{path}")
    return abs_p, wd


def _edit_backup(abs_path, text, wd):
    """改之前备份到 LOG_DIR/edit_backup/<pid>_<启动时间>/，按进程分开避免并发互相覆盖；
    同一文件多次修改各留一份（文件名加序号）；newline="" 原样保留行尾；失败不影响主流程。"""
    try:
        bdir = Path(LOG_DIR) / "edit_backup" / f"{os.getpid()}_{_START_TS}"
        bdir.mkdir(parents=True, exist_ok=True)
        rel = os.path.relpath(abs_path, wd).replace(os.sep, "__")
        dst = bdir / rel
        n = 0
        while dst.exists():
            n += 1
            dst = bdir / f"{rel}.{n}"
        with open(dst, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    except (OSError, ValueError):
        pass


def _norm_edit(it, idx):
    if not isinstance(it, dict):
        raise ValueError(f"edits[{idx}] 要是对象 {{path, before, after, count?}}，收到：{it!r}")
    path = it.get("path")
    before = it.get("before")
    after = it.get("after")
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f"edits[{idx}].path 要是非空字符串")
    if not isinstance(before, str) or before == "":
        raise ValueError(f"edits[{idx}].before 要是非空字符串（空串会误匹配）")
    if not isinstance(after, str):
        raise ValueError(f"edits[{idx}].after 要是字符串")
    count = it.get("count", 1)
    try:
        count = int(count)
    except (TypeError, ValueError) as e:
        raise ValueError(f"edits[{idx}].count 要是正整数") from e
    if count < 1:
        raise ValueError(f"edits[{idx}].count 要 ≥ 1")
    return {"path": path.strip(), "before": before, "after": after, "count": count}


def multi_edit(edits, atomic=True, cwd=None):
    """一次做多处 before→after 精确替换。

    默认 atomic=True：全部在内存里按顺序套用（后刀看得到前刀结果），全部成功才写盘；
    任一失败整批不落盘，并说明是第几刀、实际出现几次、附近原文。
    atomic=False：每刀成功就立刻写盘，失败时前面已写的保留。
    """
    if isinstance(edits, dict):
        edits = [edits]
    if not isinstance(edits, list) or not edits:
        raise ValueError("edits 要是非空列表")
    if len(edits) > MAX_EDITS:
        raise ValueError(f"一次最多 {MAX_EDITS} 处改动，收到 {len(edits)}；拆成几次调")
    specs = [_norm_edit(it, i) for i, it in enumerate(edits)]
    atomic = True if atomic is None else bool(atomic)

    originals = {}
    resolved = []
    wd0 = None
    for i, sp in enumerate(specs):
        abs_p, wd = _writable_path(sp["path"], cwd)
        wd0 = wd0 or wd
        if abs_p not in originals:
            try:
                with open(abs_p, "r", encoding="utf-8", newline="") as f:   # 原样保留 \r\n
                    originals[abs_p] = f.read()
            except OSError as e:
                raise ValueError(f"edits[{i}] 读失败 {sp['path']}：{e}") from e
        resolved.append((abs_p, sp["path"], wd))

    working = dict(originals)
    results = []
    written = set()

    def fail(i, disp, msg):
        prefix = "未落盘" if atomic else ("未继续写" if written else "未落盘")
        raise ValueError(f"edits[{i}] 失败（{prefix}）：{msg}")

    for i, sp in enumerate(specs):
        abs_p, disp, wd = resolved[i]
        cur = working[abs_p]
        found = cur.count(sp["before"])
        if found == 0:
            hint = _edit_hint(cur, sp["before"])
            if "\r\n" in cur and "\n" in sp["before"] and "\r\n" not in sp["before"]:
                hint = ((hint + "\n") if hint else "") + \
                    "注意：文件是 CRLF（或含 \\r\\n）行尾，before/after 里的换行要写成 \\r\\n。"
            fail(i, disp, f"{disp} 里找不到那段内容。" + hint)
        if found != sp["count"]:
            fail(i, disp,
                 f"{disp} 里那段出现了 {found} 次，但 count={sp['count']}。"
                 f"要全改就传 count={found}，只改一处就把 before 写长一点让它唯一。")
        updated = cur.replace(sp["before"], sp["after"], sp["count"])
        results.append((i, disp, found, cur, updated, abs_p, wd))
        working[abs_p] = updated
        if not atomic:
            if abs_p not in written:
                _edit_backup(abs_p, originals[abs_p], wd)
            with open(abs_p, "w", encoding="utf-8", newline="") as f:   # 原样保留行尾
                f.write(updated)
            written.add(abs_p)

    if atomic:
        for abs_p, new_text in working.items():
            if new_text == originals[abs_p]:
                continue
            _edit_backup(abs_p, originals[abs_p], wd0)
            with open(abs_p, "w", encoding="utf-8", newline="") as f:   # 原样保留行尾
                f.write(new_text)
            written.add(abs_p)

    parts = [f"已改 {len(results)} 处" + ("（原子提交）" if atomic else "（逐条落盘）")
             + f"，涉及 {len(written)} 个文件"]
    used = 0
    for i, disp, found, before_t, after_t, abs_p, wd in results:
        left = DIFF_TOTAL - used
        if left < 80:
            parts.append(f"--- edits[{i}] {disp}（{found} 处）：diff 总上限已满，省略 ---")
            continue
        cap = min(DIFF_PER_EDIT, left)
        d = _edit_diff(before_t, after_t, disp, cap)
        block = f"--- edits[{i}] {disp}（{found} 处）---\n{d}"
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


# ----------------------------------------------------------------------
# run_wait / wait_pid

_PROCS = {}          # pid -> {"p": Popen, "t0", "deadline", "log", "cmd", "killed"}
_PLOCK = threading.Lock()
_KEEP_DONE = 50      # 已结束且交付过的条目最多保留这么多个（防 _PROCS/_PROBES 无限增长）


def _gc_keep(d, keep=_KEEP_DONE):
    """d 里已结束（t1 有值）且交付过（delivered）的条目，按结束时间只留最近 keep 个；
    保留期内「结论前面已经返回过」的提示逻辑不受影响。调用方需持 _PLOCK。"""
    done = sorted((v.get("t1") or 0, k) for k, v in d.items()
                  if v.get("t1") is not None and v.get("delivered"))
    for _, k in done[:-keep]:
        d.pop(k, None)


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
    env = {k: v for k, v in os.environ.items() if not _leaky_env(k, v)}
    with open(log, "wb") as lf:
        p = subprocess.Popen(["bash", "-c", command], cwd=wd, env=env, stdin=subprocess.DEVNULL,
                             stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    t0 = time.time()
    with _PLOCK:
        _PROCS[p.pid] = {"p": p, "t0": t0, "deadline": t0 + to, "log": log, "cmd": command,
                         "killed": False}
    threading.Thread(target=_watchdog, args=(p.pid,), daemon=True).start()
    r = _wait_own(p.pid, min(to + 5, MAX_BLOCK), tail_lines, _cancel or threading.Event())
    with _PLOCK:
        rr = _PROCS.get(p.pid)
        if rr and rr["p"].poll() is not None:   # 直接跑完的也算已交付，交给 _gc_keep 回收
            rr["delivered"] = True
            rr["t1"] = rr.get("t1") or time.time()
        _gc_keep(_PROCS)
    return r


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
        with _PLOCK:
            rr = _PROCS.get(pid)
            if rr and rr["p"].poll() is not None:
                rr["delivered"] = True
                rr["t1"] = rr.get("t1") or time.time()
            _gc_keep(_PROCS)
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
# probe / probe_wait（派给 Codex 或 Claude CLI 的只读探针）

_PROBES = {}         # probe_id -> {...}
_PSEQ = [0]


def _codex_bin():
    return os.environ.get("GSB_CODEX_BIN") or shutil.which("codex")


def _claude_bin():
    return os.environ.get("GSB_CLAUDE_BIN") or shutil.which("claude")


PROBE_RETRY_WAITS = tuple(int(x) for x in os.environ.get("GSB_PROBE_RETRY_WAITS", "20,40,60,90,120").split(",") if x.strip())
_CAPACITY_RE = re.compile(
    r"at capacity|overloaded|rate.?limit|too many requests|429|temporarily unavailable", re.I)
_USAGE_LIMIT_RE = re.compile(r"usage.?limit|credit.?balance", re.I)  # 用量上限：不重试


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
        tail = _tail(r["log"], 15)
        if _USAGE_LIMIT_RE.search(tail):     # 用量上限：重试也不会好，直接按失败收场
            r["usage_limit"] = True
            break
        if not _CAPACITY_RE.search(tail):
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


def _codex_opts(effort, timeout_secs, model, cwd, default_model=None):
    eff = str(effort or "medium").strip().lower()
    if eff not in PROBE_EFFORTS:
        raise ValueError(f"effort 只能是 {' / '.join(PROBE_EFFORTS)}，收到：{effort!r}")
    to = int(timeout_secs or 900)
    if not 1 <= to <= PROBE_MAX_TIMEOUT:
        raise ValueError(f"timeout_secs 要在 1~{PROBE_MAX_TIMEOUT}")
    m = str(model or default_model or PROBE_MODEL).strip()
    if not _MODEL_RE.match(m):
        raise ValueError(f"model 不对：{model!r}")
    wd = _resolve(cwd) if cwd else os.getcwd()
    if not os.path.isdir(wd):
        raise ValueError(f"cwd 不是目录：{wd}")
    exe = _codex_bin()
    if not exe:
        raise ValueError("找不到 codex（PATH 里没有）")
    return eff, to, m, wd, exe


def _probe_opts(effort, timeout_secs, model, cwd):
    """校验探针参数；按 PROBE_BACKEND 检查对应 CLI。"""
    eff = str(effort or "medium").strip().lower()
    if eff not in PROBE_EFFORTS:
        raise ValueError(f"effort 只能是 {' / '.join(PROBE_EFFORTS)}，收到：{effort!r}")
    to = int(timeout_secs or 900)
    if not 1 <= to <= PROBE_MAX_TIMEOUT:
        raise ValueError(f"timeout_secs 要在 1~{PROBE_MAX_TIMEOUT}")
    backend = PROBE_BACKEND
    default_m = "claude-haiku-5-5" if backend == "claude" else "gpt-6-luna"
    m = str(model or PROBE_MODEL or default_m).strip()
    if not _MODEL_RE.match(m):
        raise ValueError(f"model 不对：{model!r}")
    wd = _resolve(cwd) if cwd else os.getcwd()
    if not os.path.isdir(wd):
        raise ValueError(f"cwd 不是目录：{wd}")
    if backend == "claude":
        exe = _claude_bin()
        if not exe:
            raise ValueError("找不到 claude（PATH 里没有；或设 GSB_CLAUDE_BIN）")
        if not PROBE_CLAUDE_RUN.is_file():
            raise ValueError(f"找不到 Claude 探针启动器：{PROBE_CLAUDE_RUN}")
        if not Path(PROBE_CLAUDE_MCP).is_file():
            raise ValueError(f"找不到 Claude MCP 配置：{PROBE_CLAUDE_MCP}")
        if not Path(PROBE_CLAUDE_SETTINGS).is_file():
            raise ValueError(f"找不到 Claude settings：{PROBE_CLAUDE_SETTINGS}")
    else:
        exe = _codex_bin()
        if not exe:
            raise ValueError("找不到 codex（PATH 里没有）")
    return backend, eff, to, m, wd, exe


def _new_probe_id(kind):
    """probe / review / verify 共用的 id：p1-<pid>-<ts> / r… / v…。"""
    with _PLOCK:
        _PSEQ[0] += 1
        return f"{kind[0]}{_PSEQ[0]}-{os.getpid()}-{int(time.time() * 1000) % 100000}"


def _codex_start(kind, prompt, eff, to, m, wd, exe, sandbox="read-only", extra_cfg=None,
                 pid_=None):
    """后台起一个 codex exec（probe / review 固定 read-only；verify 用 workspace-write
    且 -C 锁在自己的临时目录），登记到 _PROBES，返回 id。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    if pid_ is None:
        pid_ = _new_probe_id(kind)
    base = os.path.join(LOG_DIR, f"{kind}_{time.strftime('%Y%m%d-%H%M%S')}_{pid_}")
    log, out, prompt_f = base + ".log", base + ".reply.txt", base + ".prompt.txt"
    with open(prompt_f, "w", encoding="utf-8") as f:
        f.write(prompt)
    # probe / review 固定只读；不带任何 --dangerously* / --approve-for-me / full-auto。
    # verify 走 workspace-write 且 -C 是自己的临时目录（被验项目 / 仓库都不在可写根里）
    cmd = [exe, "exec", "-m", m, "-s", sandbox, "--skip-git-repo-check", "--color", "never",
           "-c", f"model_reasoning_effort={eff}"]
    for cfg in extra_cfg or ():
        cmd += ["-c", cfg]
    cmd += ["-C", wd, "-o", out]
    # 给探针挂只含 read_files 的 MCP（schema 很小）；GSB_PROBE_READ_FILES=0 关掉
    if os.environ.get("GSB_PROBE_READ_FILES", "1") != "0":
        py = sys.executable or "python3"
        script = str(Path(__file__).resolve())
        # 内联 TOML 表：command / args / env
        cmd += [
            "-c", f'mcp_servers.gsb_read_files.command={py!r}',
            "-c", f'mcp_servers.gsb_read_files.args=[{script!r}]',
            "-c", 'mcp_servers.gsb_read_files.env.GSB_TOOLS_ONLY="read_files"',
        ]
    cmd.append("-")
    env = {k: v for k, v in os.environ.items() if not _leaky_env(k, v)}
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
                         "stop": False, "launch": launch, "kind": kind,
                         "backend": "codex"}
    threading.Thread(target=_probe_watchdog, args=(pid_,), daemon=True).start()
    return pid_


def _claude_start(kind, prompt, eff, to, m, wd, exe):
    """后台起 Claude CLI 只读探针（经 probe_claude_run.py），登记到 _PROBES。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    with _PLOCK:
        _PSEQ[0] += 1
        pid_ = f"{kind[0]}{_PSEQ[0]}-{os.getpid()}-{int(time.time() * 1000) % 100000}"
    base = os.path.join(LOG_DIR, f"{kind}_{time.strftime('%Y%m%d-%H%M%S')}_{pid_}")
    log, out, prompt_f = base + ".log", base + ".reply.txt", base + ".prompt.txt"
    with open(prompt_f, "w", encoding="utf-8") as f:
        f.write(prompt)
    py = sys.executable or "python3"
    mcp_cfg = PROBE_CLAUDE_MCP
    if os.environ.get("GSB_PROBE_READ_FILES", "1") == "0":
        empty = base + ".mcp_empty.json"
        with open(empty, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {}}, f)
        mcp_cfg = empty
    cmd = [py, str(PROBE_CLAUDE_RUN),
           "--model", m, "--effort", eff, "--cwd", wd,
           "--prompt-file", prompt_f, "--out", out, "--log", log,
           "--mcp-config", mcp_cfg, "--settings", PROBE_CLAUDE_SETTINGS,
           "--claude-bin", exe]
    env = {k: v for k, v in os.environ.items() if not _leaky_env(k, v)}
    env["ENABLE_CLAUDEAI_MCP_SERVERS"] = "0"
    open(log, "wb").close()

    def launch():
        with open(log, "ab") as lf:
            return subprocess.Popen(cmd, cwd=wd, env=env, stdin=subprocess.DEVNULL,
                                    stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    p = launch()
    t0 = time.time()
    with _PLOCK:
        _PROBES[pid_] = {"p": p, "t0": t0, "t1": None, "deadline": t0 + to, "log": log,
                         "out": out, "killed": False, "model": m, "effort": eff,
                         "delivered": False, "timeout": to, "retries": 0,
                         "stop": False, "launch": launch, "kind": kind,
                         "backend": "claude"}
    threading.Thread(target=_probe_watchdog, args=(pid_,), daemon=True).start()
    return pid_


def probe(instructions, cwd=None, effort="medium", timeout_secs=900, wait=True, model=None,
          _cancel=None):
    if not isinstance(instructions, str) or not instructions.strip():
        raise ValueError("instructions 要是非空字符串：写清楚探针要做什么、交回什么格式")
    backend, eff, to, m, wd, exe = _probe_opts(effort, timeout_secs, model, cwd)
    prompt = PROBE_PREAMBLE + instructions.strip() + "\n"
    if backend == "claude":
        pid_ = _claude_start("probe", prompt, eff, to, m, wd, exe)
        label = f"Claude {m}"
    else:
        pid_ = _codex_start("probe", prompt, eff, to, m, wd, exe)
        label = m
    if not wait:
        return (f"probe_id：{pid_}\n状态：started（后台跑，{label}，强度 {eff}，超时 {to} 秒，后端 {backend}）\n"
                f"派完别的探针后用 probe_wait(probe_ids=[...]) 一起等结果")
    return probe_wait([pid_], _cancel=_cancel)


def _git(wd, *args):
    try:
        r = subprocess.run(["git", "-C", wd, *args], capture_output=True, text=True, timeout=30,
                           env={k: v for k, v in os.environ.items() if not _leaky_env(k, v)},
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
    eff, to, m, wd, exe = _codex_opts(effort, timeout_secs, model, cwd, default_model=REVIEW_MODEL)
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
    be = r.get("backend") or "codex"
    head = f"===== {kind}_id：{pid_}（{r['model']} / {r['effort']} / {be}）"
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
    elif r.get("usage_limit"):
        st = f"failed（退出码 {rc}）：模型用量上限（usage limit / credit balance），这类错误不自动重试"
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
    if kind == "verify":
        if r.get("viols") is None:
            r["viols"] = _verify_violations(r)
        for v in r["viols"]:
            lines.append(f"⚠ 违规改动：{v}（验证期间被验项目 / 仓库变了；上面 JSON 的结论照旧，"
                         "是否采信主任务自己判断）")
        if reply:
            d, jerr = _verify_parse(reply)
            if d is None:
                lines.append(f"验证 JSON：解析失败（{jerr}），下面按原文返回")
            else:
                lines.append(f"验证 JSON：已解析；{_verify_summary(d)}")
                bad_env = _verify_env_check(d, r.get("verify_repo"))
                if bad_env:
                    lines.append(f"⚠ 环境不符：{bad_env}——结论按「无法验证」对待"
                                 "（验证员原文照录，不改）")
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
        lines += [{"review": "--- 初步审查意见（原文）---",
                   "verify": "--- 验证的最终回复（原文）---"}.get(kind, "--- 探针的最终回复 ---"),
                  reply]
    if st != "done":
        if kind == "review":
            lines.insert(1, "初步审查没完成：过几分钟再调一次 review；还是不行就自己逐条核对，并在报告里写明「未经初步审查」及原因。")
        if kind == "verify":
            lines.insert(1, "验证没完成：可以稍后重新派一次 verify（超时给大些），或自己核对并在报告里写明。")
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
        parts.append(f"===== id：{x} =====\n错误：没有这个 id（只认本会话里 probe / review / verify 返回的 id）\n")
    if running:
        parts.append(f"[{len(running)} 个还在跑（本次最多等 {MAX_BLOCK} 秒）：再调 "
                     f"{_tool}({_arg}={json.dumps(running)}) 接着等，不要 sleep]")
    with _PLOCK:
        _gc_keep(_PROBES)    # 交付完的旧条目只留最近 N 个；最近交付过的仍能提示「前面已经返回过」
    return "\n".join(parts)



# ----------------------------------------------------------------------
# verify / verify_wait（派专用验证 agent：workspace-write 沙箱锁在临时目录里做验证）

_VERIFY_SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules"})
VERIFY_WORK_PARENT = "/tmp"


def _manifest(root, cap=6000):
    """{相对路径: 大小} 快照；超过 cap 个文件返回 None（太大，不逐文件核对，靠 git status）。"""
    out, n = {}, 0
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in _VERIFY_SKIP_DIRS]
        for fn in fns:
            p = os.path.join(dp, fn)
            try:
                out[os.path.relpath(p, root)] = os.stat(p).st_size
            except OSError:
                continue
            n += 1
            if n > cap:
                return None
    return out


def _verify_watch(*roots):
    """派 verify 前给要保护的目录拍快照：git 仓库记 porcelain 状态 + HEAD（仓库根），
    目录本身再记一份文件清单（gitignore 的文件 git 看不见）。"""
    items, seen_git, seen_root = [], set(), set()
    for root in roots:
        if not root:
            continue
        root = os.path.realpath(root)
        if not os.path.isdir(root) or root in seen_root:
            continue
        seen_root.add(root)
        rc, top = _git(root, "rev-parse", "--show-toplevel")
        if rc == 0:
            g = os.path.realpath(top.strip())
            if g not in seen_git:
                seen_git.add(g)
                items.append({"root": g, "git": True,
                              "status": sorted(_git(g, "status", "--porcelain")[1].splitlines()),
                              "head": _git(g, "rev-parse", "HEAD")[1].strip()})
            # 项目目录本身再记一份文件清单：gitignore 的文件 git status 看不见
            if root not in {it["root"] for it in items}:
                items.append({"root": root, "manifest": _manifest(root)})
        else:
            items.append({"root": root, "manifest": _manifest(root)})
    return items


def _verify_violations(r):
    """验证结束后的违规改动核对：返回描述列表，空 = 没变化。只是线索：并发作业
    也可能动过同一仓库，是否采信主任务自己判断。"""
    out = []
    for it in r.get("verify_watch") or []:
        root = it["root"]
        if it.get("git"):
            now = sorted(_git(root, "status", "--porcelain")[1].splitlines())
            added = [x for x in now if x not in it["status"]]
            gone = [x for x in it["status"] if x not in now]
            head = _git(root, "rev-parse", "HEAD")[1].strip()
            if added or gone or head != it["head"]:
                det = []
                if added:
                    det.append(f"新增/改动 {len(added)} 项（如 {added[:3]}）")
                if gone:
                    det.append(f"消失 {len(gone)} 项（如 {gone[:3]}）")
                if head != it["head"]:
                    det.append(f"HEAD {it['head'][:10]} → {head[:10]}")
                out.append(f"{root}：git status 变了（{'；'.join(det)}）")
        elif "manifest" in it:
            if it["manifest"] is None:
                continue
            m2 = _manifest(root)
            if m2 is None:
                out.append(f"{root}：文件太多，结束时没法逐文件核对")
                continue
            m1 = it["manifest"]
            added = sorted(set(m2) - set(m1))
            gone = sorted(set(m1) - set(m2))
            chg = sorted(k for k in set(m2) & set(m1) if m2[k] != m1[k])
            if added or gone or chg:
                out.append(f"{root}：文件清单变了（新增 {len(added)} 如 {added[:3]}；"
                           f"删除 {len(gone)} 如 {gone[:3]}；大小变化 {len(chg)} 如 {chg[:3]}）")
    return out


def _verify_parse(reply):
    """从验证员最后一条回复里取 JSON：允许 ```json 围栏和前后杂字。
    返回 (dict, None) 或 (None, 原因)。"""
    if not isinstance(reply, str) or not reply.strip():
        return None, "回复为空"
    t = reply.strip()
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", t, re.S)
    if m and m.group(1).lstrip().startswith("{"):
        t = m.group(1).strip()
    if not t.startswith("{"):
        i, j = t.find("{"), t.rfind("}")
        if 0 <= i < j:
            t = t[i:j + 1]
    try:
        d = json.loads(t)
    except json.JSONDecodeError as e:
        return None, f"JSON 解析失败：{e}"
    if not isinstance(d, dict) or not isinstance(d.get("结果"), dict):
        return None, "不是要求的格式（缺「结果」对象）"
    return d, None


def _verify_summary(d):
    res = d.get("结果") or {}
    checks = [c for c in (res.get("检查") or []) if isinstance(c, dict)]
    ok = sum(1 for c in checks if c.get("通过") is True)
    bad = sum(1 for c in checks if c.get("通过") is False)
    finds = res.get("发现") or []
    return (f"状态={d.get('状态') or '?'}；结论={res.get('结论') or '?'}；"
            f"检查 {len(checks)} 项（通过 {ok}，不通过 {bad}）；发现 {len(finds)} 条")


def _verify_env_check(d, repo):
    """核对结论 JSON 的「环境」：解释器必须是引擎仓库的 .venv、引擎必须在引擎仓库根下
    （repo 由 verify 按 engine_repo → 被验项目 → cwd 的顺序定出，可能与被验仓库分离）。
    不符返回原因（摘要标 ⚠，结论按「无法验证」对待），合规或缺仓库根返回 None。"""
    res = d.get("结果") or {}
    env = res.get("环境")
    if not isinstance(env, dict):
        return "结论 JSON 缺「环境」字段（应含 python / 引擎 / 起法）"
    miss = [k for k in ("python", "引擎", "起法") if not str(env.get(k) or "").strip()]
    if miss:
        return "「环境」缺：" + "、".join(miss)
    if not repo:
        return None
    r = os.path.realpath(repo)
    # 解释器按报告的路径本身判（abspath，不解符号链接）：venv 里的 python 通常是指向系统
    # python3 的符号链接，realpath 会跳出 .venv 而误报。
    py = os.path.abspath(os.path.expanduser(str(env["python"]).split()[0]))
    if not py.startswith(r + os.sep + ".venv" + os.sep):
        return f"解释器不是被验仓库的 .venv：{env['python']}（仓库根 {r}）"
    bad = [x for x in str(env["引擎"]).split()
           if not os.path.realpath(os.path.expanduser(x)).startswith(r + os.sep)]
    if bad:
        return f"引擎不在被验仓库根下：{' '.join(bad)}（仓库根 {r}）"
    return None


def verify(instructions, cwd=None, project=None, base=None, effort="medium",
           timeout_secs=900, wait=True, model=None, engine_repo=None, _cancel=None):
    """派一个验证 agent：codex workspace-write，-C 锁在 /tmp/verify_<id>/（临时目录），
    放开 network_access 好起本地服务；被验项目与仓库都不在可写根里，写不进去。
    派前给被验项目 / 仓库拍快照，结束时核对，变了标「违规改动」。
    引擎仓库（engine_repo）按 显式参数 → 被验项目向上探测 → cwd 向上探测 确定，前言和
    「环境」核对都用它；被验仓库（快照比对、禁写保护）仍是被验项目自己的仓库/目录，
    两者分离时两边都拍快照。"""
    if not isinstance(instructions, str) or not instructions.strip():
        raise ValueError("instructions 要是非空字符串：写清楚验什么（如「kg_v4 全量回归」）")
    eff, to, m, wd, exe = _codex_opts(effort, timeout_secs, model, cwd, default_model=VERIFY_MODEL)
    proj = os.path.realpath(_resolve(project, wd) if project else wd)
    if not os.path.isdir(proj):
        raise ValueError(f"project 不是目录：{proj}")
    base_line = ""
    if base not in (None, ""):
        base = str(base).strip()
        if not _REF_RE.match(base) or ".." in base:
            raise ValueError(f"base 要是一个 git 提交 / 分支 / tag，收到：{base!r}")
        if _git(proj, "rev-parse", "--show-toplevel")[0] != 0:
            raise ValueError(f"project 不是 git 仓库，不能用 base：{proj}")
        if _git(proj, "rev-parse", "--verify", "--quiet", base + "^{commit}")[0] != 0:
            raise ValueError(f"base 在仓库里找不到：{base!r}")
        base_line = (f"基线（对比用，只读）：git 提交 {base}。要跑基线就在你自己的目录里"
                     f"拷一份仓库再切过去，不准动原仓库的 HEAD 和工作区。\n")
    repo = _engine_repo_of(proj, engine_repo, wd)
    watch = _verify_watch(proj, wd, repo)
    pid_ = _new_probe_id("verify")
    tmp = os.path.join(VERIFY_WORK_PARENT, f"verify_{pid_}")
    os.makedirs(tmp, exist_ok=True)
    _, env_py, env_repo = _env_lines(proj, repo)
    prompt = VERIFY_PREAMBLE.format(tmp=tmp, project=proj, base_line=base_line,
                                    instructions=instructions.strip(),
                                    env_py=env_py, env_repo=env_repo)
    pid2 = _codex_start("verify", prompt, eff, to, m, tmp, exe, sandbox="workspace-write",
                        extra_cfg=["sandbox_workspace_write.network_access=true"], pid_=pid_)
    _PROBES[pid2].update(verify_watch=watch, project=proj, base=base, verify_repo=repo)
    if not wait:
        return (f"verify_id：{pid2}\n状态：started（后台验证，模型 {m}，强度 {eff}，超时 {to} 秒）\n"
                f"工作目录 {tmp}（只能写这里），被验项目 {proj} 只读\n"
                f"用 verify_wait(verify_ids=[\"{pid2}\"]) 等结果")
    return probe_wait([pid2], _cancel=_cancel, _tool="verify_wait", _arg="verify_ids")


def verify_wait(verify_ids, timeout_secs=None, _cancel=None):
    return probe_wait(verify_ids, timeout_secs, _cancel=_cancel,
                      _tool="verify_wait", _arg="verify_ids")



# ----------------------------------------------------------------------
# 接口封装模板（tools/dslagent/templates/iface/*.zs）

_IFACE_ENG = re.compile(r"^[a-z][a-z0-9_]*$")
_IFACE_CONSTRAINTS = ("snake", "snake_list", "free", "go")


def _iftpl():
    """惰性 import；扩展常被 `python gsb_tools_mcp.py` 拉起，需把仓库根放进 sys.path。"""
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    from tools.dslagent import iftpl as m
    return m


def _iface_dir():
    """模板目录：GSB_IFACE_DIR（测试用）或 iftpl.DIR（仓库内固定位置）。"""
    override = (os.environ.get("GSB_IFACE_DIR") or "").strip()
    if override:
        d = Path(os.path.realpath(override))
    else:
        d = Path(_iftpl().DIR).resolve()
    return d


def _iface_eng(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("英文文件名要是非空字符串（不含 .zs）")
    name = name.strip()
    if name.endswith(".zs"):
        name = name[:-3]
    if not _IFACE_ENG.match(name) or "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"英文文件名只能是小写字母开头的 [a-z0-9_]（收到：{name!r}）")
    return name


def _iface_path(eng, *, must_exist=False):
    d = _iface_dir()
    if not d.is_dir():
        raise ValueError(f"接口模板目录不存在：{d}")
    path = (d / f"{eng}.zs").resolve()
    # 防穿越：必须仍在 d 下
    try:
        path.relative_to(d)
    except ValueError as e:
        raise ValueError(f"路径越界，只允许写 {d}") from e
    if must_exist and not path.is_file():
        raise ValueError(f"没有这个模板文件：{eng}.zs（目录 {d}）")
    return path


def _iface_resolve_file(file, cwd=None):
    """把 file（英文名或路径）解析到 iface 目录内的 .zs；越界拒绝。"""
    if not isinstance(file, str) or not file.strip():
        raise ValueError("file 要是英文文件名或 iface 目录内的路径")
    file = file.strip()
    d = _iface_dir()
    if "/" not in file and "\\" not in file and not file.startswith("."):
        return _iface_path(_iface_eng(file), must_exist=True)
    p = Path(os.path.realpath(_resolve(file, cwd)))
    try:
        p.relative_to(d.resolve())
    except ValueError as e:
        raise ValueError(f"只允许读接口模板目录内的文件（{d}），收到：{p}") from e
    if not p.is_file() or p.suffix != ".zs":
        raise ValueError(f"不是 iface 目录里的 .zs 文件：{p}")
    return p


def _param_line(p):
    """一条参数 → 「参数 <名> <必填|可选> <约束> <含义>」或抛错。"""
    if isinstance(p, str):
        parts = p.split()
        if len(parts) < 4 or parts[1] not in ("必填", "可选") or parts[2] not in _IFACE_CONSTRAINTS:
            raise ValueError(
                f"参数字符串写法是「<名> <必填|可选> <{'/'.join(_IFACE_CONSTRAINTS)}> <含义…>」，收到：{p!r}")
        return "参数 " + " ".join(parts)
    if not isinstance(p, dict):
        raise ValueError(f"params 每项要是字符串或对象，收到：{p!r}")
    name = str(p.get("name") or p.get("名") or "").strip()
    req = p.get("required", p.get("必填"))
    if isinstance(req, bool):
        req_s = "必填" if req else "可选"
    else:
        req_s = str(req or "").strip()
    cons = str(p.get("constraint") or p.get("约束") or "").strip()
    meaning = str(p.get("meaning") or p.get("含义") or "").strip()
    if not name or req_s not in ("必填", "可选") or cons not in _IFACE_CONSTRAINTS or not meaning:
        raise ValueError(
            f"参数对象要有 name/名、required/必填(bool 或 必填|可选)、constraint/约束"
            f"（{'/'.join(_IFACE_CONSTRAINTS)}）、meaning/含义，收到：{p!r}")
    return f"参数 {name} {req_s} {cons} {meaning}"


def _body_block(b):
    """一个主体块 → ['主体' 或 '主体 当 …', '  行…', ...]。"""
    if isinstance(b, str):
        lines = [ln.rstrip() for ln in b.replace("\r", "").splitlines() if ln.strip()]
        if not lines:
            raise ValueError("主体块不能为空")
        # 字符串形式的主体：以「主体…」开头的行（无论原本缩进多少）顶格开新块，
        # 其余行去缩进后统一缩进两格，作为当前块的正文（K32：自动拆块，不再原样保留缩进）。
        blocks = []
        for ln in lines:
            if ln.strip().startswith("主体"):
                blocks.append([ln.strip()])
            elif blocks:
                blocks[-1].append("  " + ln.strip())
            else:
                blocks.append(["主体", "  " + ln.strip()])
        return [x for blk in blocks for x in blk]
    if not isinstance(b, dict):
        raise ValueError(f"body/bodies 每项要是字符串或 {{when, lines}}，收到：{b!r}")
    when = b.get("when") or b.get("当") or ""
    if isinstance(when, (list, tuple)):
        when = ",".join(str(x).strip() for x in when if str(x).strip())
    else:
        when = str(when).strip()
    lines = b.get("lines") or b.get("行") or []
    if isinstance(lines, str):
        lines = [ln for ln in lines.replace("\r", "").splitlines() if ln.strip()]
    if not isinstance(lines, list) or not lines:
        raise ValueError("主体块的 lines/行 要是非空列表")
    head = f"主体 当 {when}" if when else "主体"
    out = [head]
    for ln in lines:
        s = str(ln).rstrip()
        if not s.strip():
            continue
        out.append(s if s[:1].isspace() else ("  " + s.strip()))
    return out


def build_iface_template(name, title, purpose, params=None, example="", body=None, bodies=None):
    """拼出 .zs 文本（不含落盘）。"""
    eng = _iface_eng(name)
    if not isinstance(title, str) or not title.strip() or any(c.isspace() for c in title.strip()):
        raise ValueError("中文名（title）要是不含空格的非空字符串")
    title = title.strip()
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("用途（purpose）要是非空字符串")
    purpose = purpose.strip()
    example = (example or "").strip() if isinstance(example, str) else ""
    blocks = []
    if body is not None:
        blocks.append(body)
    if bodies is not None:
        if not isinstance(bodies, list):
            raise ValueError("bodies 要是主体块列表")
        blocks.extend(bodies)
    if not blocks:
        raise ValueError("至少给一个主体：body 或 bodies")
    lines = [
        f"# 接口封装模板（约定「## 接口」行写「模板 {title} …」；格式见 tools/dslagent/iftpl.py）。",
        f"模板 {title}",
        f"用途 {purpose}",
    ]
    for p_ in (params or []):
        lines.append(_param_line(p_))
    if example:
        lines.append(f"例子 {example}")
    for b in blocks:
        lines.extend(_body_block(b))
        if not lines[-1].endswith("\n"):
            pass
    text = "\n".join(lines) + "\n"
    # 顺带用文件名占位校验（eng 仅写入路径时用）
    return eng, text


_IFACE_HEAD_KW = ("主体", "模板", "用途", "参数", "例子")


def _indent_probs(text):
    """工具层检查：缩进行的「正文」若以顶层关键字开头，说明该行本意是顶格的段落头，
    现在会被当成上一个主体的正文（K32 之前 page_state_form.zs 就是这样坏的）。"""
    return [f"第 {n} 行：这一行要顶格写（现在被当成上一个主体的正文）"
            for n, ln in enumerate(text.splitlines(), 1)
            if ln[:1].isspace() and ln.strip().startswith(_IFACE_HEAD_KW)]


def _check_text(text, *, eng=None, path=None):
    """用 iftpl._parse 校验 + 工具层缩进检查；再查中文名与其它文件是否冲突。返回 (ok, 问题列表, tpl)。"""
    if not isinstance(text, str) or not text.strip():
        return False, ["模板内容为空"], None
    ift = _iftpl()
    tpl, probs = ift._parse(text)
    probs = list(probs) + _indent_probs(text)
    d = _iface_dir()
    if d.is_dir() and tpl.get("名"):
        for f in sorted(d.glob("*.zs")):
            if path is not None and f.resolve() == Path(path).resolve():
                continue
            if eng is not None and f.stem == eng:
                continue
            try:
                other, op = ift._parse(f.read_text(encoding="utf-8"))
            except OSError:
                continue
            if not op and other.get("名") == tpl["名"]:
                probs.append(f"中文名「{tpl['名']}」已与 {f.name} 冲突")
    return (not probs), probs, tpl


def list_iface_templates(cwd=None):  # noqa: ARG001  — cwd 保留与其它工具一致，目录由 _iface_dir 决定
    d = _iface_dir()
    if not d.is_dir():
        return f"接口模板目录不存在：{d}\n（还没有模板）"
    ift = _iftpl()
    rows = []
    bad = []
    for f in sorted(d.glob("*.zs")):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError as e:
            bad.append(f"{f.name}：读失败 {e}")
            continue
        tpl, probs = ift._parse(text)
        probs = probs + _indent_probs(text)
        if probs:
            bad.append(f"{f.name}：{'；'.join(probs)}")
            continue
        ps = "；".join(
            f"{k} {'必填' if tpl['参数'][k]['必填'] else '可选'} {tpl['参数'][k]['约束']}"
            f"（{tpl['参数'][k]['含义']}）" for k in tpl["顺序"])
        rows.append(
            f"- 文件 {f.name}｜模板 {tpl['名']}：{tpl['用途']}\n"
            f"  参数：{ps or '（无）'}\n"
            f"  例子：{tpl['例子'] or '（无）'}")
    out = [f"接口封装模板目录：{d}", f"共 {len(rows)} 个" + (f"，另有 {len(bad)} 个有问题" if bad else "")]
    out.extend(rows or ["（还没有模板）"])
    if bad:
        out.append("--- 有问题的文件 ---")
        out.extend(f"✗ {x}" for x in bad)
    return "\n".join(out)


def check_iface_template(content=None, file=None, cwd=None):
    if (content is None or content == "") and not file:
        raise ValueError("给 content（模板正文）或 file（英文名 / iface 内路径）之一")
    if content not in (None, "") and file:
        raise ValueError("content 和 file 不要一起传")
    eng = path = None
    if file:
        path = _iface_resolve_file(file, cwd)
        content = path.read_text(encoding="utf-8")
        eng = path.stem
    ok, probs, tpl = _check_text(content, eng=eng, path=path)
    if ok:
        name = tpl["名"]
        nparam = len(tpl["顺序"])
        nbody = len(tpl["主体"])
        where = f"（{path.name}）" if path else ""
        return (f"校验通过{where}：模板 {name}，{nparam} 个参数，{nbody} 个主体块。"
                f"用途：{tpl['用途']}")
    head = f"校验失败（{path.name}）" if path else "校验失败"
    return head + "：\n" + "\n".join(f"- {p}" for p in probs)


def write_iface_template(name, title, purpose, params=None, example="", body=None,
                         bodies=None, overwrite=False, text=None, cwd=None):  # noqa: ARG001
    """参数化写入或直接写 text；校验通过才落盘。"""
    if text is not None:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text 要是非空模板正文")
        eng = _iface_eng(name)
        content = text if text.endswith("\n") else text + "\n"
    else:
        eng, content = build_iface_template(name, title, purpose, params, example, body, bodies)
    path = _iface_path(eng, must_exist=False)
    if path.exists() and not overwrite:
        raise ValueError(f"已存在 {path.name}（要覆盖请传 overwrite=true）")
    ok, probs, tpl = _check_text(content, eng=eng, path=path if path.exists() else None)
    if not ok:
        return "写入取消（校验未通过，未落盘）：\n" + "\n".join(f"- {p}" for p in probs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return (f"已写入 {path}（模板 {tpl['名']}，{len(tpl['顺序'])} 个参数，"
            f"{len(tpl['主体'])} 个主体块" + ("，已覆盖" if overwrite else "") + "）")



# ----------------------------------------------------------------------
# MCP（JSON-RPC 2.0 over stdio，一行一条）

TOOLS = [
    {"name": "read_files",
     "description": ("优先用本工具，不要用 shell 的 cat/head/tail/sed -n/less 读文件。一次读多个文件"
                     "（或同一文件的多段），带行号返回，一次读完。files 每项是路径字符串（读整个文件）或 "
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
    {"name": "multi_edit",
     "description": ("优先用本工具，不要用 shell 的 sed/awk 或逐次 edit 改文件。一次对同一文件多处或多个文件做 before→after 精确替换（语义同 goose 内置 edit / fsedit）："
                     "before 必须正好出现 count 次（默认 1），多了少了都报错。"
                     "默认 atomic=true：全部在内存按顺序套用（后刀看得到前刀结果），全部成功才写盘，"
                     "任一失败整批不落盘并说明是第几刀。"
                     f"一次最多 {MAX_EDITS} 处。同一文件要改多处（超过 2 处）或一次改多个文件时用它；"
                     "单处改动仍可用内置 edit。路径限任务工作目录，拒绝 .git 与 config.json。"
                     "返回每处的短 diff，不回整文件。"),
     "inputSchema": {"type": "object", "properties": {
         "edits": {"type": "array", "description": "改动列表，每项 {path, before, after, count?}",
                   "items": {"type": "object", "properties": {
                       "path": {"type": "string"},
                       "before": {"type": "string", "description": "要替换的原文（必须唯一或配合 count）"},
                       "after": {"type": "string", "description": "替换成的新文"},
                       "count": {"type": "integer", "description": "before 必须正好出现的次数，默认 1"}},
                       "required": ["path", "before", "after"]}},
         "atomic": {"type": "boolean", "description": "默认 true：全成才写盘；false 则逐条落盘"},
         "cwd": {"type": "string", "description": "工作目录，默认任务工作目录"}},
         "required": ["edits"]}},
    {"name": "run_wait",
     "description": ("优先用本工具，不要在 shell 里把命令放后台再 sleep 轮询。跑一条 shell 命令（bash -c）并阻塞等它结束，返回退出码、用时、输出末尾 N 行；完整输出写到 "
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
     "description": ("优先用本工具，不要在 shell 里 sleep 轮询等进程结束。阻塞等一个进程结束（run_wait 返回 still_running 的 pid，或已在后台跑的进程），"
                     f"单次最多 {MAX_BLOCK} 秒，返回是否结束和 log 末尾。等后台任务用它，不要用 sleep 轮询。"),
     "inputSchema": {"type": "object", "properties": {
         "pid": {"type": "integer"},
         "log_path": {"type": "string", "description": "要看末尾的输出文件"},
         "timeout_secs": {"type": "integer", "description": f"本次最多等几秒，默认且最多 {MAX_BLOCK}"},
         "tail_lines": {"type": "integer", "description": "默认 60"}},
         "required": ["pid"]}},
    {"name": "list_iface_templates",
     "description": ("列出接口封装模板（tools/dslagent/templates/iface/*.zs）：英文文件名、中文名、用途、"
                     "参数摘要、例子。现有模板盖不住新接口形态时先 list，再 check / write_iface_template 加模板；"
                     "不要改 iftpl.py 引擎。"),
     "inputSchema": {"type": "object", "properties": {
         "cwd": {"type": "string", "description": "保留参数；模板目录固定为仓库 iface 目录（或 GSB_IFACE_DIR）"}},
         "required": []}},
    {"name": "check_iface_template",
     "description": ("校验一份接口封装模板，不落盘。给 content（.zs 正文）或 file（英文名如 list，或 iface 目录内路径）。"
                     "用与 iftpl 相同的解析规则，返回通过说明或问题列表。"),
     "inputSchema": {"type": "object", "properties": {
         "content": {"type": "string", "description": "模板正文（与 file 二选一）"},
         "file": {"type": "string", "description": "英文文件名（可带 .zs）或 iface 目录内路径"},
         "cwd": {"type": "string", "description": "解析相对 file 路径时的工作目录"}},
         "required": []}},
    {"name": "write_iface_template",
     "description": ("参数化写入一个接口封装模板到 templates/iface/<英文名>.zs："
                     "先拼成 .zs → 同一套校验 → 通过才落盘，失败不写。overwrite 默认 false。"
                     "也可直接传 text 作为完整正文（仍要 name 作文件名）。不要改 iftpl.py。"),
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "英文文件名（不含路径，小写 [a-z][a-z0-9_]*）"},
         "title": {"type": "string", "description": "中文名（模板首行，不含空格）"},
         "purpose": {"type": "string", "description": "用途一句话"},
         "params": {"type": "array", "description": "参数列表：对象 {name,required,constraint,meaning} 或字符串「名 必填|可选 约束 含义」",
                    "items": {"anyOf": [{"type": "string"}, {"type": "object"}]}},
         "example": {"type": "string", "description": "例子行（接口行示例）"},
         "body": {"description": "缺省主体：字符串或 {when, lines}"},
         "bodies": {"type": "array", "description": "更多主体块（含「主体 当 …」）",
                    "items": {"anyOf": [{"type": "string"}, {"type": "object"}]}},
         "text": {"type": "string", "description": "若给出则忽略 title/purpose/…，直接当 .zs 正文校验后写入"},
         "overwrite": {"type": "boolean", "description": "默认 false；已存在则拒绝"},
         "cwd": {"type": "string"}},
         "required": ["name"]}},

]

def _probe_tool_description():
    if PROBE_BACKEND == "claude":
        be = (f"Claude CLI 的 {PROBE_MODEL}，permission-mode=plan 只读，"
              "只挂 Read/Glob/Grep/Bash + gsb_read_files，关掉无关 MCP/connectors")
    else:
        be = f"Codex CLI 的 {PROBE_MODEL}，强制 read-only 沙箱"
    return (f"派一个只读探针（{be}）去做大量阅读 / 对照 / 调研，"
            "只收回它的最终结论，主任务上下文保持轻量。instructions 写清楚要读什么、查什么、交回什么格式。"
            "探针不改文件，改代码你自己做；关键结论自己抽查核实。互不相干的几块可以并行派："
            "每个 probe 传 wait=false 立即拿到 probe_id，再用 probe_wait 一起等。"
            f"wait=true（默认）时单次最多阻塞 {MAX_BLOCK} 秒，没跑完返回 still_running 和 probe_id。")


PROBE_TOOLS = [
    {"name": "probe",
     "description": _probe_tool_description(),
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
     "description": (f"派一个独立审查员（Codex CLI 的 {REVIEW_MODEL}，强制 read-only 沙箱）对你的改动做初步审查："
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
         "model": {"type": "string", "description": f"默认 {REVIEW_MODEL}，一般不用传"}},
         "required": []}},
    {"name": "review_wait",
     "description": f"等初步审查的结论（单次最多阻塞 {MAX_BLOCK} 秒），没审完再调一次接着等。",
     "inputSchema": {"type": "object", "properties": {
         "review_ids": {"type": "array", "items": {"type": "string"}},
         "timeout_secs": {"type": "integer", "description": f"本次最多等几秒，默认且最多 {MAX_BLOCK}"}},
         "required": ["review_ids"]}},
]

VERIFY_TOOLS = [
    {"name": "verify",
     "description": (f"派一个专用验证 agent（Codex CLI 的 {VERIFY_MODEL}，workspace-write 沙箱，"
                     "工作目录锁在它自己的临时目录 /tmp/verify_<id>/）去做验证：全量回归、起本地服务"
                     "逐接口实测、全套测试基线 vs 改后对比。它自己去摸项目（README / 现有测试 / 回归"
                     "冒烟入口），优先用项目已有入口，没有才写临时脚本；起的服务自己停。被验项目与"
                     "仓库只读；结束时核对它们的 git status / 文件清单，有变化在结果里标「违规改动」"
                     "（只是线索，可能有并发作业动过同一仓库）。被验项目不在引擎仓库下时传 engine_repo "
                     "或保证 cwd 在引擎仓库（engine_repo 定出的引擎仓库根同时用于前言和「环境」核对；"
                     "被验仓库的快照比对不变）。最终回复严格按 JSON 交回，verify_wait "
                     "解析；解析失败按原文返回并标明；结论 JSON 必须带「环境」（解释器 / 引擎 / 起法），"
                     "不符在摘要里标「⚠ 环境不符」且结论按「无法验证」对待。回归、起服务实测、基线对比交给 verify，"
                     "不要自己现写一次性验证脚本。wait=true（默认）单次最多阻塞 "
                     f"{MAX_BLOCK} 秒，没跑完返回 still_running 和 verify_id，再调 verify_wait。"),
     "inputSchema": {"type": "object", "properties": {
         "instructions": {"type": "string", "description": "验什么：如「kg_v4 全量回归」「起服务按前端动作逐个打 auth_login、student_* 并核对返回键」「全套测试基线 vs 改后，基线用 HEAD」"},
         "cwd": {"type": "string", "description": "工作目录，默认任务工作目录"},
         "project": {"type": "string", "description": "被验项目路径（默认 cwd）；结束时核对它和所在仓库没被改"},
         "engine_repo": {"type": "string", "description": "引擎仓库根（带 gen/ 和 tools/，含 .venv）：被验项目所用引擎所在的仓库。不传时先从被验项目向上探测，推不出再从 cwd 向上找；被验项目不在引擎仓库下时传这个或保证 cwd 在引擎仓库"},
         "base": {"type": "string", "description": "基线 git 提交（对比用；验证员只会在自己的目录里拷仓库切基线，不动原仓库）"},
         "effort": {"type": "string", "enum": list(PROBE_EFFORTS), "description": "推理强度，默认 medium"},
         "timeout_secs": {"type": "integer", "description": f"默认 900，最多 {PROBE_MAX_TIMEOUT}，超时杀掉"},
         "wait": {"type": "boolean", "description": "默认 true；false 立即返回 verify_id（并行派多个时用）"},
         "model": {"type": "string", "description": f"默认 {VERIFY_MODEL}，一般不用传"}},
         "required": ["instructions"]}},
    {"name": "verify_wait",
     "description": (f"等一个或多个验证的结果（单次最多阻塞 {MAX_BLOCK} 秒）。全部结束就返回各自的"
                     "状态、解析出的验证 JSON 摘要和原文（违规改动、环境不符会单独标出）；还有没跑完的会"
                     "列出来，再调一次接着等。"),
     "inputSchema": {"type": "object", "properties": {
         "verify_ids": {"type": "array", "items": {"type": "string"}},
         "timeout_secs": {"type": "integer", "description": f"本次最多等几秒，默认且最多 {MAX_BLOCK}"}},
         "required": ["verify_ids"]}},
]

if PROBE_ON:
    TOOLS = TOOLS + PROBE_TOOLS
if REVIEW_ON:
    TOOLS = TOOLS + REVIEW_TOOLS
if VERIFY_ON:
    TOOLS = TOOLS + VERIFY_TOOLS

# 探针专用：只暴露少数工具（典型 GSB_TOOLS_ONLY=read_files）
_ONLY = [x.strip() for x in (os.environ.get("GSB_TOOLS_ONLY") or "").split(",") if x.strip()]
if _ONLY:
    _have = {t["name"]: t for t in TOOLS}
    _miss = [n for n in _ONLY if n not in _have]
    if _miss:
        raise SystemExit(f"GSB_TOOLS_ONLY 里没有这些工具：{', '.join(_miss)}")
    TOOLS = [_have[n] for n in _ONLY]
    SERVER = {**SERVER, "name": "gsb_read_files" if _ONLY == ["read_files"] else "gsb_tools_subset"}

_OUT = threading.Lock()
_CANCELS = {}


def _priority_instructions():
    """initialize 里的「工具用法」优先级说明：按实际暴露的工具动态生成，
    没挂的不写（GSB_TOOLS_ONLY 子集也不会提示不存在的工具）。"""
    have = {t["name"] for t in TOOLS}
    p = []
    if "read_files" in have:
        p.append("读文件一律用 read_files（可一次多个文件、带行号范围、glob），不要用 shell 的 "
                 "cat/head/tail/sed -n/less 读；grep/rg 搜索可以照用，但看搜到的内容回 read_files。")
    if "run_wait" in have or "wait_pid" in have:
        if {"run_wait", "wait_pid"} <= have:
            p.append("测试、构建等长命令用 run_wait 阻塞等结果，后台进程等结束用 wait_pid；"
                     "不要在 shell 里 sleep 轮询，sleep 超过 10 秒一律改用 wait_pid。")
        else:
            p.append(("测试、构建等长命令用 run_wait 阻塞等结果" if "run_wait" in have
                      else "等后台进程结束用 wait_pid") + "；不要在 shell 里 sleep 轮询。")
    if "multi_edit" in have:
        p.append("同一文件改 2 处以上、或一次改多个文件，用 multi_edit 一次提交（默认原子）；"
                 "单处小改可用内置 edit。")
    if "list_iface_templates" in have:
        names = "/".join(n for n in ("list_iface_templates", "check_iface_template",
                                     "write_iface_template") if n in have)
        p.append(f"接口封装模板用 {names}，不要手写模板文件、不要改 iftpl.py。")
    if "probe" in have:
        p.append("大量阅读 / 对照派 probe 只收结论，wait=false 可并行。")
    if "review" in have:
        p.append("改完代码、commit/push 和写报告前用 review 做初步审查；意见只是线索，核实后再改。")
    if "verify" in have:
        p.append("回归、起服务实测、基线对比交给 verify（wait=false + verify_wait 可并行），"
                 "不要自己现写验证脚本；被验项目不在引擎仓库下时传 engine_repo 或保证 cwd 在引擎仓库。")
    return ("工具用法：" + "".join(p)) if p else ""


def _send(obj):
    s = json.dumps(obj, ensure_ascii=False)
    with _OUT:
        sys.stdout.write(s + "\n")
        sys.stdout.flush()


def _call(name, args, cancel):
    if name == "read_files":
        return read_files(args.get("files"), args.get("max_chars_per_file"),
                          args.get("max_total_chars"))
    if name == "multi_edit":
        a = args.get("atomic")
        return multi_edit(args.get("edits"), True if a is None else bool(a), args.get("cwd"))
    if name == "run_wait":
        return run_wait(args.get("command"), args.get("cwd"), args.get("timeout_secs") or 900,
                        args.get("tail_lines") or 60, args.get("log_path"), _cancel=cancel)
    if name == "wait_pid":
        return wait_pid(args.get("pid"), args.get("log_path"), args.get("timeout_secs"),
                        args.get("tail_lines") or 60, _cancel=cancel)
    if name == "list_iface_templates":
        return list_iface_templates(args.get("cwd"))
    if name == "check_iface_template":
        return check_iface_template(args.get("content"), args.get("file"), args.get("cwd"))
    if name == "write_iface_template":
        return write_iface_template(
            args.get("name"), args.get("title"), args.get("purpose"), args.get("params"),
            args.get("example") or "", args.get("body"), args.get("bodies"),
            bool(args.get("overwrite")), args.get("text"), args.get("cwd"))
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
    if name == "verify":
        w = args.get("wait")
        return verify(args.get("instructions"), args.get("cwd"), args.get("project"),
                      args.get("base"), args.get("effort") or "medium",
                      args.get("timeout_secs") or 900, True if w is None else bool(w),
                      args.get("model"), args.get("engine_repo"), _cancel=cancel)
    if name == "verify_wait":
        return verify_wait(args.get("verify_ids"), args.get("timeout_secs"), _cancel=cancel)
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
                "instructions": (
                    "一次读多个文件或同一文件多段时用 read_files，带行号返回；不要分多次 cat/sed。"
                    if _ONLY == ["read_files"] else _priority_instructions())}})
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
