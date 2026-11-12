# -*- coding: utf-8 -*-
"""按模型的通道和提供方把调用分给智谱、Claude Code、ZCode。

模型名先查档位/别名，再用 config.parse_model 规范成「通道:提供方/模型」，
这里只看 (channel, provider) 分派，不再判断字符串前缀：

    api:zhipu/glm-5.3      内层客户端（智谱，或测试里的假客户端）
    api:anthropic/…        预留，调用时报「api:anthropic 还没接入」
    cli:claude[/haiku]     本机 claude -p（无头模式），不写模型用它自己的默认
    cli:zcode              本机 zcode -p（不能选模型）

旧写法（裸名、claude:sonnet、zcode、zcode:xx）由 parse_model 换成上面的规范名，
行为不变。转给内层客户端时：名字本来就是旧写法（裸名、别名指向裸名……）就
传调用方给的原名（不传就是 None），内层的行为一点不变；规范名 api:zhipu/x
传 x。

不传模型时看内层客户端的默认模型（client.model）：它是 cli 通道（比如
models.json 的 default 档位填了 cli:claude/sonnet）就也走 CLI，否则原样交给内层。

## 能力：带工具、流式

这次调用需要什么能力，由调用本身决定，引擎和 Agent 不用另外声明：
chat_raw 带 tools → 需要「带工具」；stream / stream_messages → 需要「流式」。
各后端支持什么查 config.BACKENDS（数据，不是 if）：

    不支持（no）    报错，信息里有规范名、能力和办法
    降级（degraded）照常调用，效果打折（CLI 的流式是整段一次性返回）

档位写了 fallback（{"model": "cli:claude/opus", "fallback": "api:zhipu/glm-5.3"}）
时，缺能力就改用 fallback，记一条 warning 日志；fallback 自己也缺就报错。
别名指向这种档位时一样（resolve_model 返回的 ModelRef 带着档位名）。

主模型走 CLI 时，fallback 还接「这次没跑成」：超时、排队太久没轮到、退出码
非 0、输出不对（BackendError，不含缺能力的 CapabilityError），同样记一条
warning 改用 fallback 再问一次。没写 fallback 就照旧报错。做题页「请老师
总结」用过平衡档（cli:claude/sonnet），claude 卡住时学习者干等三分钟最后
拿到一个 500——有智谱兜着就不至于。

## 为什么包在引擎和 Agent 上，而不是各个造客户端的地方

造客户端的地方有六七处（HTTP 路由、flows、fs_server、agent 工具……），
最后都是交给 DSLEngine 或 Agent。在这两处包一层（wrap 是幂等的），
新加的入口不用记得包。

## 两个 CLI 后端的限制

- 慢：每次起一个进程，claude 一次纯问答十秒上下
- 吃订阅额度（Claude 是 Max 订阅的 5 小时窗口 + 周上限，ZCode 是 Z.AI 账号）
- 不支持带工具（见上）
- 流式降级：等整段生成完一次性 yield
- temperature 忽略
- 纯问答：claude 用 --tools "" --strict-mcp-config 并换掉系统提示词，
  zcode 禁掉全部内置工具；都在空的临时目录里跑，读不到项目文件

同时运行的进程数用信号量限住（默认各 2 个），见 _slots。排队等不到
（默认 30 秒，DSL_<名字>_QUEUE_WAIT / <名字>_queue_wait）就报 BackendError，
有 fallback 的档位就改用 fallback，不会一直排下去。

单次超时默认 90 秒（DSL_<名字>_TIMEOUT / <名字>_timeout 可调）：这些调用
大多是网页上的人在等，sonnet 一次总结实测十秒上下，90 秒还没回多半是卡了，
早点交给 fallback 比让人干等三分钟强。

## Windows：经 WSL 调

Windows 上的 Python 跑 DSL 时，claude / zcode 多半只装在 WSL 里。这时通过
wsl.exe 调 WSL 里的那份。设置 cli_via_wsl（环境变量 DSL_CLI_VIA_WSL >
config.json > 默认 "auto"）：

    "auto"   只在 Windows 上、且本机找不到对应程序时走 WSL（默认）
    true     Windows 上强制走 WSL（本机有也不用）
    false    不走 WSL，找不到就报原来的错

另有 wsl_distro（发行版，不填用默认的）、wsl_claude_bin / wsl_zcode_bin
（WSL 里的路径，不填就在 WSL 的登录 shell 里 command -v，再找不到用
$HOME/.local/bin/<名字>）、wsl_exe（wsl.exe 的路径，一般不用填）。都是
环境变量 DSL_<大写> > config.json。不是 Windows（is_windows() 为假）时
这些都不起作用。

传参：wsl.exe 的命令行上只有一段固定的 bash 脚本（_WSL_SCRIPT，纯 ASCII，
没有反斜杠），提示词、系统提示词、模型等全部参数都 base64 后从**标准输入**
传，WSL 里解码后直接当 argv 交给程序（不经 shell 拼接）。这样中文日语、
换行、引号、$、反引号、%、^、& 都碰不到 Windows 命令行解析、cmd 和 bash。
claude 的提示词再从它自己的标准输入读（claude -p 不带提示词参数时读
stdin），不受单个参数 128KB 的限制；zcode 没有读 stdin 的办法，提示词仍是
argv（WSL 里解码后传，安全，但单个参数上限 128KB）。

WSL 侧在 mktemp -d 的空目录里跑、跑完删；unset ANTHROPIC_API_KEY；用
timeout(1) 自己限时（超时先 TERM，5 秒后 KILL），Windows 这边比它多等
WSL_GRACE 秒再杀 wsl.exe——光杀 wsl.exe 不保证 WSL 里的进程跟着退，靠
WSL 侧的 timeout 兜底，所以最多残留到超时后 5 秒。
"""

import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from typing import NamedTuple

from . import config
from .zhipu import strip_json

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 90
DEFAULT_MAX_PROCS = 2
DEFAULT_QUEUE_WAIT = 30

# 没给系统提示词时换上这句。不换的话 claude -p 用 Claude Code 自己那段
# 几千字的编程助手提示词，慢、费额度，回答也带着「我来帮你改代码」的腔调
DEFAULT_SYSTEM = "你是一个有帮助的助手。直接回答用户的问题，不要多余的寒暄。"

JSON_ASK = "\n\n只输出 JSON 本身，不要代码围栏，不要任何解释。"


class BackendError(RuntimeError):
    """claude / zcode 起不来、超时、或者报了错；后端还没接入。"""


class CapabilityError(BackendError):
    """模型不具备这次调用需要的能力（如 cli 通道带工具），也没有可用的 fallback。"""


def _setting(env: str, key: str, default: int) -> int:
    """环境变量 > config.json > 默认值。"""
    raw = os.environ.get(env) or config.get(key)
    try:
        return int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        return default


# 信号量按后端各一个，第一次用时按当时的设置建
_SLOTS: dict = {}
_SLOTS_LOCK = threading.Lock()


def _slots(backend: str) -> threading.BoundedSemaphore:
    with _SLOTS_LOCK:
        if backend not in _SLOTS:
            n = _setting(f"DSL_{backend.upper()}_MAX_PROCS",
                         f"{backend}_max_procs", DEFAULT_MAX_PROCS)
            _SLOTS[backend] = threading.BoundedSemaphore(max(1, n))
        return _SLOTS[backend]


# ----------------------------------------------------------------------
# Windows → WSL

# Windows 这边比 WSL 侧的 timeout 多等几秒：正常超时由 WSL 侧报（退出码
# 124），这边再杀 wsl.exe 只是兜底
WSL_GRACE = 15

# 标准输入的第一行，对不上说明协议两头版本不一致
_WSL_MAGIC = "DSLWSL1"
# WSL 侧输出正文前先打这一行：登录 shell 的 profile 往 stdout 打的东西在它前面，丢掉
_WSL_MARK = "DSLWSL-OUT"

# 在 WSL 里由 bash -lc 跑。放在 wsl.exe 的命令行上，所以只用 ASCII、不用
# 反斜杠（Windows 命令行解析只认反斜杠和双引号，双引号由 list2cmdline 转义）。
# 标准输入：魔数 / b64(程序名) / b64(路径，可空) / 超时秒数 / 参数个数 N /
# N 行 b64(参数) / 余下全部 = b64(交给程序的标准输入)
_WSL_SCRIPT = """set -u
r(){ IFS= read -r L || L=; }
b(){ printf %s "$1" | base64 -d -i; }
r; case $L in DSLWSL1*) ;; *) echo 'dsl-wsl: bad stdin header' >&2; exit 91;; esac
r; name=$(b "$L"); r; bin=$(b "$L"); r; t=${L//[!0-9]/}; r; n=${L//[!0-9]/}
args=(); i=0
while [ "$i" -lt "${n:-0}" ]; do r; v=$(b "$L"; printf x); args+=("${v%x}"); i=$((i+1)); done
d=$(mktemp -d "${TMPDIR:-/tmp}/dsl_wsl_XXXXXX") || exit 92
trap 'rm -rf "$d"' EXIT
cd "$d" || exit 92
base64 -d -i > "$d/.in" || exit 91
export PATH="$HOME/.local/bin:$PATH"
[ -n "$bin" ] || bin=$(command -v "$name") || bin="$HOME/.local/bin/$name"
command -v "$bin" > /dev/null || { echo "dsl-wsl: $name not found: $bin" >&2; exit 93; }
unset ANTHROPIC_API_KEY CLAUDECODE CLAUDE_PID CLAUDE_EFFORT
for v in ${!CLAUDE_CODE_*}; do unset "$v"; done
echo DSLWSL-OUT
timeout -k 5 "${t:-180}" "$bin" "${args[@]}" < "$d/.in"
"""

_WSL_EXIT = {91: "传参协议对不上（标准输入被改坏了？）",
             92: "WSL 里建不了临时目录"}


def is_windows() -> bool:
    """是不是 Windows。包成函数是为了测试里替换。"""
    return os.name == "nt"


def _text_setting(env: str, key: str):
    """环境变量 > config.json；都没有返回 None。"""
    raw = os.environ.get(env)
    if raw in (None, ""):
        raw = config.get(key)
    if isinstance(raw, str):
        raw = raw.strip()
    return raw if raw not in (None, "") else None


def via_wsl_setting():
    """cli_via_wsl 规范成 "auto" / True / False，带来源。"""
    if os.environ.get("DSL_CLI_VIA_WSL", "").strip():
        raw, src = os.environ["DSL_CLI_VIA_WSL"], "环境变量 DSL_CLI_VIA_WSL"
    elif config.get("cli_via_wsl") not in (None, ""):
        raw, src = config.get("cli_via_wsl"), "config.json 的 cli_via_wsl"
    else:
        return "auto", "默认"
    if isinstance(raw, bool):
        return raw, src
    s = str(raw).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True, src
    if s in ("0", "false", "no", "off"):
        return False, src
    return "auto", src


def wsl_exe() -> str:
    exe = _text_setting("DSL_WSL_EXE", "wsl_exe") or shutil.which("wsl.exe")
    if exe:
        return exe
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    return os.path.join(root, "System32", "wsl.exe")


def _decode(raw: bytes) -> str:
    """wsl.exe 自己的报错（发行版不存在之类）是 UTF-16LE，WSL 里程序的输出是 UTF-8。"""
    if not raw:
        return ""
    # 英文的 UTF-16 一半是 0 字节；中文的 UTF-16 没有 0 字节，但多半不是合法 UTF-8
    if raw.count(b"\x00") > len(raw) // 4:
        return raw.decode("utf-16-le", errors="replace").replace("\x00", "")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    if len(raw) % 2 == 0:
        try:
            return raw.decode("utf-16-le")
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


class Proc(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


def _b64(s: str) -> str:
    return base64.b64encode((s or "").encode("utf-8")).decode("ascii")


def run_wsl(name: str, args: list, stdin: str, timeout: int,
            label: str) -> Proc:
    """在 WSL 里跑 name（claude / zcode），参数和标准输入都走 base64。"""
    distro = _text_setting("DSL_WSL_DISTRO", "wsl_distro")
    binp = _text_setting(f"DSL_WSL_{name.upper()}_BIN", f"wsl_{name}_bin") or ""
    cmd = [wsl_exe()]
    if distro:
        cmd += ["-d", distro]
    cmd += ["--cd", "~", "--exec", "bash", "-lc", _WSL_SCRIPT, "dsl-wsl"]
    payload = "\n".join([_WSL_MAGIC, _b64(name), _b64(binp), str(int(timeout)),
                         str(len(args)), *(_b64(a) for a in args),
                         _b64(stdin)]) + "\n"
    try:
        p = subprocess.run(cmd, input=payload.encode("ascii"),
                           capture_output=True, timeout=timeout + WSL_GRACE,
                           creationflags=getattr(subprocess,
                                                 "CREATE_NO_WINDOW", 0))
    except FileNotFoundError:
        raise BackendError(f"{label}：找不到 wsl.exe（{cmd[0]}），WSL 装了吗？"
                           f"可以用 DSL_WSL_EXE 指定路径") from None
    except subprocess.TimeoutExpired:
        raise BackendError(
            f"{label} 超过 {timeout} 秒没有返回，已杀掉 wsl.exe"
            f"（WSL 侧的 timeout 也没生效，WSL 里可能有残留进程）") from None
    out, err = _decode(p.stdout), _decode(p.stderr)
    head, sep, body = out.partition(_WSL_MARK + "\n")
    if not sep:
        head, sep, body = out.partition(_WSL_MARK + "\r\n")
    out = body if sep else out
    rc = p.returncode
    if rc == 124 or (rc == 137 and sep):
        raise BackendError(f"{label} 超过 {timeout} 秒没有返回，WSL 侧已杀掉"
                           f"（可用 DSL_{name.upper()}_TIMEOUT 调大）")
    if rc == 93 and not sep:
        raise BackendError(
            f"{label}：WSL 里找不到 {name}（{_head(err, 2)}）。装了吗？可以用 "
            f"wsl_{name}_bin / DSL_WSL_{name.upper()}_BIN 指定 WSL 里的路径")
    if rc in _WSL_EXIT and not sep:
        raise BackendError(f"{label}：{_WSL_EXIT[rc]}\nstderr：{_head(err)}")
    if not sep:
        # 没跑到脚本里（wsl.exe 起不来、发行版不存在……）
        raise BackendError(
            f"{label}：wsl.exe 退出码 {rc}，没跑起来"
            f"（发行版：{distro or '默认'}）：{_head(err) or _head(out, 3)}")
    return Proc(rc, out, err)


class Route(NamedTuple):
    backend: object       # CLI 后端对象；None = 内层客户端（api:zhipu）
    spec: object          # 最后用的 ModelSpec（用了 fallback 就是 fallback 的）
    model: object         # 交给后端的模型名


def _choose(spec, tier, fallback, needs):
    """按能力表挑主模型或 fallback；缺能力又没有可用 fallback 就报错。"""
    missing = [n for n in needs if spec.cap(n) == "no"]
    if not missing:
        return spec
    need = missing[0]
    cap = config.CAPS.get(need, need)
    if fallback is None:
        extra = f"（档位「{tier}」没写 fallback）" if tier else ""
        raise CapabilityError(config.capability_error(spec, need, extra))
    bad = [n for n in needs if fallback.cap(n) == "no"]
    if bad:
        raise CapabilityError(
            f"档位「{tier}」的模型 {spec.canonical} 不支持「{cap}」，它的 fallback "
            f"{fallback.canonical}（{fallback.backend.label}）也不支持"
            f"「{config.CAPS.get(bad[0], bad[0])}」。办法：把 fallback 换成 api "
            f"通道的模型（如 api:zhipu/glm-5.3）")
    log.warning("档位「%s」：%s 不支持「%s」，这次改用 fallback %s",
                tier, spec.canonical, cap, fallback.canonical)
    return fallback


def route(model, needs=(), default=None) -> Route:
    """这次调用交给谁。model 不传时按 default（内层客户端的默认模型）分派。

    needs 是这次调用需要的能力（config.CAPS 的键）。
    """
    if not isinstance(model, str):
        model = None
    resolved = config.resolve_spec(
        model or (default if isinstance(default, str) else None))
    if resolved is None:
        return Route(None, None, model)
    spec, tier, fallback = resolved
    use = _choose(spec, tier, fallback, needs)
    if not use.backend.ready:
        raise BackendError(
            f"模型 {use.canonical}：{use.channel}:{use.provider} 还没接入。"
            f"先用 api:zhipu/…（智谱）或 cli:claude/…（本机 Claude Code）")
    if use.channel == "cli":
        return Route(_BACKENDS[use.provider], use, use.model)
    # api:zhipu → 内层客户端。旧写法传原名，保证内层收到的跟以前一样
    if use is spec and (model is None or spec.legacy):
        return Route(None, use, model)
    return Route(None, use, use.model)


def _render(messages: list) -> tuple:
    """消息列表拼成 (提示词, 系统提示词)。CLI 只收一段文字，历史只能拼进去。"""
    system = "\n\n".join(m.get("content") or "" for m in messages
                         if m.get("role") == "system") or None
    turns = [m for m in messages if m.get("role") != "system"]
    if len(turns) == 1 and turns[0].get("role") == "user":
        return turns[0].get("content") or "", system
    who = {"user": "用户", "assistant": "助手", "tool": "工具结果"}
    lines = [f"{who.get(m.get('role'), m.get('role'))}：{m.get('content') or ''}"
             for m in turns if m.get("content")]
    prompt = ("下面是到目前为止的对话记录。请以助手的身份回复最后一条用户消息，"
              "只输出回复本身，不要加「助手：」前缀。\n\n" + "\n\n".join(lines))
    return prompt, system


def _head(text: str, n: int = 5) -> str:
    lines = [x for x in (text or "").strip().splitlines() if x.strip()]
    return "\n".join(lines[:n])


class _CLIBackend:
    """两个 CLI 后端共用的部分：各种 chat 方法都归到 complete()。"""

    name = ""

    @staticmethod
    def binary() -> str:
        raise NotImplementedError

    def use_wsl(self) -> bool:
        """这次经不经 WSL。不经 WSL 又找不到本机程序时报原来的错。"""
        mode, _ = via_wsl_setting()
        if not is_windows() or mode is False:
            return False
        if mode is True:
            return True
        try:
            self.binary()
            return False
        except BackendError:
            return True

    def describe(self) -> str:
        """python -m tools.config 用：这个后端现在怎么调。"""
        try:
            wsl = self.use_wsl()
        except BackendError as e:  # pragma: no cover
            return f"✗ {e}"
        if not wsl:
            try:
                return f"本机 {self.binary()}"
            except BackendError as e:
                return f"本机，但{e}"
        binp = _text_setting(f"DSL_WSL_{self.name.upper()}_BIN",
                             f"wsl_{self.name}_bin")
        distro = _text_setting("DSL_WSL_DISTRO", "wsl_distro")
        return (f"经 WSL（{wsl_exe()}；发行版：{distro or '默认'}；WSL 里的路径："
                f"{binp or f'登录 shell 里 command -v {self.name}，找不到用 $HOME/.local/bin/{self.name}'}）")

    def complete(self, prompt: str, system, model: str) -> str:
        raise NotImplementedError

    def _call(self, prompt, system, model) -> str:
        slot = _slots(self.name)
        wait = _setting(f"DSL_{self.name.upper()}_QUEUE_WAIT",
                        f"{self.name}_queue_wait", DEFAULT_QUEUE_WAIT)
        if not slot.acquire(timeout=max(0, wait)):
            raise BackendError(f"{self.name} 同时在跑的进程满了，排队 {wait} 秒"
                               f"没轮到（可用 DSL_{self.name.upper()}_MAX_PROCS 调大）")
        try:
            return self.complete(prompt, system, model)
        finally:
            slot.release()

    def chat(self, prompt, system=None, temperature=None, model="", **kw):
        return self._call(prompt, system, model)

    def chat_messages(self, messages, temperature=None, model="", **kw):
        prompt, system = _render(messages)
        reply = self._call(prompt, system, model).strip()
        return reply[3:].lstrip() if reply.startswith("助手：") else reply

    def chat_raw(self, messages, model="", **kw):
        if kw.get("tools"):
            # 正常走不到这里：RouterClient 先按能力表拦了。直接用后端时兜底
            spec = config.parse_model(f"cli:{self.name}"
                                      + (f"/{model}" if model else ""))
            raise CapabilityError(config.capability_error(spec, "tools"))
        return {"choices": [{"message": {
                    "role": "assistant",
                    "content": self.chat_messages(messages, model=model)}}],
                "usage": {}}

    def chat_json_messages(self, messages, temperature=None, retries=0,
                           model="", **kw):
        msgs = [dict(m) for m in messages]
        for m in reversed(msgs):
            if m.get("role") == "user":
                m["content"] = (m.get("content") or "") + JSON_ASK
                break
        last = ""
        for _ in range(max(0, retries) + 1):
            last = self.chat_messages(msgs, model=model)
            try:
                return json.loads(strip_json(last))
            except json.JSONDecodeError:
                continue
        raise ValueError(f"{self.name} 没有返回合法 JSON。最后一次回复：{last[:200]}")

    def chat_json(self, prompt, system=None, temperature=None, retries=0,
                  model="", **kw):
        msgs = ([{"role": "system", "content": system}] if system else []) \
            + [{"role": "user", "content": prompt}]
        return self.chat_json_messages(msgs, retries=retries, model=model)

    def stream(self, prompt, system=None, temperature=None, model="", **kw):
        yield self.chat(prompt, system=system, model=model)

    def stream_messages(self, messages, temperature=None, model="", **kw):
        yield self.chat_messages(messages, model=model)


class ClaudeCLIClient(_CLIBackend):
    """claude -p 纯问答。走本机 Claude Code 的订阅登录，不用 API Key。

    可执行文件：CBATCH_CLAUDE 环境变量 > PATH 上的 claude > ~/.local/bin/claude
    （Windows 上可以经 WSL 调，见模块文档）
    超时：DSL_CLAUDE_TIMEOUT 环境变量 > config.json 的 claude_timeout > 90 秒
    """

    name = "claude"

    @staticmethod
    def binary() -> str:
        from . import cbatch
        # 每次现查环境变量：cbatch.CLAUDE_BIN 是导入时定的，测试换假程序要能生效
        exe = os.environ.get("CBATCH_CLAUDE") or cbatch.CLAUDE_BIN
        if not shutil.which(exe):
            raise BackendError(f"找不到 claude（{exe}），Claude Code 装了吗？"
                               f"可以用环境变量 CBATCH_CLAUDE 指定路径")
        return exe

    def complete(self, prompt, system, model) -> str:
        timeout = _setting("DSL_CLAUDE_TIMEOUT", "claude_timeout",
                           DEFAULT_TIMEOUT)
        opts = ["--output-format", "json",
                "--tools", "", "--strict-mcp-config",
                "--system-prompt", system or DEFAULT_SYSTEM]
        # "sonnet@low"：@ 后面是努力程度，见 config.EFFORTS
        model, effort = config.split_effort(model or "")
        if model:
            opts += ["--model", model]
        if effort:
            opts += ["--effort", effort]
        if self.use_wsl():
            label = "claude（经 WSL）"
            # 提示词从标准输入给：claude -p 不带提示词参数时读 stdin
            p = run_wsl("claude", ["-p", *opts], prompt, timeout, label)
        else:
            label = "claude"
            p = self._run_local([self.binary(), "-p", prompt, *opts], timeout)
        try:
            r = json.loads(p.stdout)
        except json.JSONDecodeError:
            r = None
        if not isinstance(r, dict):
            raise BackendError(
                f"{label} 退出码 {p.returncode}，输出不是 JSON："
                f"{_head(p.stdout, 3)[:300]}\nstderr：{_head(p.stderr)}")
        if p.returncode != 0 or r.get("is_error"):
            raise BackendError(
                f"{label} 报错（退出码 {p.returncode}）：{str(r.get('result') or r.get('subtype') or '')[:300]}"
                + (f"\nstderr：{_head(p.stderr)}" if p.stderr.strip() else ""))
        return r.get("result") or ""

    @staticmethod
    def _run_local(cmd, timeout):
        from .cbatch import _child_env
        env = _child_env()
        # 设了它 claude 就改走 API 计费，这里要的是订阅登录
        env.pop("ANTHROPIC_API_KEY", None)
        with tempfile.TemporaryDirectory(prefix="dsl_claude_") as cwd:
            try:
                return subprocess.run(cmd, cwd=cwd, env=env,
                                      stdin=subprocess.DEVNULL,
                                      capture_output=True, text=True,
                                      encoding="utf-8", errors="replace",
                                      timeout=timeout)
            except subprocess.TimeoutExpired:
                raise BackendError(f"claude 超过 {timeout} 秒没有返回"
                                   f"（可用 DSL_CLAUDE_TIMEOUT 调大）") from None


class ZCodeClient(_CLIBackend):
    """zcode -p 纯问答。zcode 不能选模型、没有系统提示词参数。

    可执行文件：ZCODE_BIN 环境变量 > PATH 上的 zcode > ~/.local/bin/zcode
    （Windows 上可以经 WSL 调，见模块文档）
    超时：DSL_ZCODE_TIMEOUT 环境变量 > config.json 的 zcode_timeout > 90 秒
    """

    name = "zcode"

    @staticmethod
    def binary() -> str:
        exe = os.environ.get("ZCODE_BIN") or shutil.which("zcode")
        if not exe:
            local = Path.home() / ".local" / "bin" / "zcode"
            exe = str(local) if local.is_file() else ""
        if not exe or not shutil.which(exe):
            raise BackendError("找不到 zcode，装了吗？"
                               "可以用环境变量 ZCODE_BIN 指定路径")
        return exe

    def complete(self, prompt, system, model) -> str:
        from .zcode_tool import ZCodeError, ZCodeJSONError, ZCodeTool
        timeout = _setting("DSL_ZCODE_TIMEOUT", "zcode_timeout",
                           DEFAULT_TIMEOUT)
        if system:
            prompt = f"{system}\n\n{prompt}"
        # 同 generate_code_text：--allowed-tools 在 0.16.5 里是坏的，
        # 用 --disallowedTools 把内置工具全禁掉
        args = ["--mode", "build", "--disallowedTools",
                *ZCodeTool.BUILTIN_TOOLS, "--json"]
        if self.use_wsl():
            label = "zcode（经 WSL）"
            # zcode 不读 stdin，提示词只能是参数；在 WSL 里解码后直接进 argv
            res = run_wsl("zcode", [*args, "-p", prompt], "", timeout, label)
        else:
            label = "zcode"
            tool = ZCodeTool(command=[self.binary()], timeout=timeout)
            with tempfile.TemporaryDirectory(prefix="dsl_zcode_") as cwd:
                try:
                    # input_text="" 给一个空的标准输入：在 MCP 服务里继承下来的
                    # 标准输入是协议管道，不能让子进程读
                    res = tool.run(prompt, extra_args=args, input_text="",
                                   cwd=cwd, check=False)
                except ZCodeError as e:
                    raise BackendError(f"zcode 起不来：{e}") from None
        if res.returncode != 0:
            raise BackendError(
                f"{label} 报错（退出码 {res.returncode}）："
                f"{_head(res.stderr) or _head(res.stdout, 3)[:300]}")
        try:
            data = ZCodeTool._parse_json_output(res.stdout)
        except ZCodeJSONError:
            raise BackendError(f"{label} 输出不是 JSON：{_head(res.stdout, 3)[:300]}"
                               f"\nstderr：{_head(res.stderr)}") from None
        if isinstance(data, dict) and data.get("ok") is False:
            raise BackendError(f"{label} 报错：{str(data.get('error') or data)[:300]}")
        text = ZCodeTool._extract_text(data)
        if text is None:
            raise BackendError(f"{label} 的输出里没有回复文本：{res.stdout[:300]}")
        return text


class GooseCLIClient(_CLIBackend):
    """goose run 纯问答，走 Z.AI 账号，跟 gsbatch 用同一套 zai_low 常驻代理。

    模型：cli:goose/glm-5.3；不写模型用 gsbatch 的默认（glm-5.3-flash）。
    provider：DSL_GOOSE_PROVIDER > config.json 的 goose_provider > zai_low。
    目前只接了 zai_low（强度 low，由 18766 的代理补）。
    key：调用方进程的环境变量 ZAI_CODING_PLAN_API_KEY（或 ZHIPU_API_KEY）。
    gsbatch 任务里的 shell 是洗过密钥的，在那里调会报「没有 key」——这是
    gsbatch 有意的，不要为了跑通把 key 写进文件。
    超时：DSL_GOOSE_TIMEOUT > config.json 的 goose_timeout > 90 秒。
    --system 是追加在 goose 自己的系统提示词后面的（不像 claude 能整段换掉）；
    不挂任何扩展、GOOSE_MODE=chat、--max-turns 1，所以没有工具可用。
    """

    name = "goose"

    @staticmethod
    def binary() -> str:
        from . import gsbatch
        exe = gsbatch.GOOSE_BIN
        if not exe or not shutil.which(exe):
            raise BackendError(f"找不到 goose（{exe}），装了吗？"
                               f"可以用环境变量 GSBATCH_GOOSE 指定路径")
        return exe

    def complete(self, prompt, system, model) -> str:
        from . import gsbatch
        if self.use_wsl():
            raise BackendError("goose 后端还不支持经 WSL 调")
        timeout = _setting("DSL_GOOSE_TIMEOUT", "goose_timeout", DEFAULT_TIMEOUT)
        provider = _text_setting("DSL_GOOSE_PROVIDER", "goose_provider") or "zai_low"
        if provider != "zai_low":
            raise BackendError(f"goose 后端目前只接了 zai_low，不支持 {provider}")
        key = gsbatch._zai_key()
        if not key:
            raise BackendError("goose：环境里没有 ZAI_CODING_PLAN_API_KEY"
                               "（gsbatch 任务的 shell 里拿不到，要在 MCP 服务"
                               "或 cbatch 起的进程里调）")
        try:
            gsbatch._ensure_zai_low()
        except gsbatch.GSBatchError as e:
            raise BackendError(f"goose：{e}") from None
        env = {k: v for k, v in gsbatch._child_env().items()
               if not k.startswith("GOOSE_") and not gsbatch._leaky_env(k, v)}
        env.update(GOOSE_DISABLE_KEYRING="1", GOOSE_DISABLE_SESSION_NAMING="true",
                   GOOSE_MODE="chat", ZAI_CODING_PLAN_API_KEY=key)
        cmd = [self.binary(), "run", "--no-profile", "--no-session",
               "--output-format", "stream-json", "--provider", provider,
               "--model", model or gsbatch.DEFAULT_MODELS[provider],
               "--max-turns", "1", "--system", system or DEFAULT_SYSTEM,
               "-i", "-"]
        with tempfile.TemporaryDirectory(prefix="dsl_goose_") as cwd:
            try:
                p = subprocess.run(cmd, cwd=cwd, env=env, input=prompt,
                                   capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   timeout=timeout)
            except subprocess.TimeoutExpired:
                raise BackendError(f"goose 超过 {timeout} 秒没有返回"
                                   f"（可用 DSL_GOOSE_TIMEOUT 调大）") from None
        r = gsbatch._parse(p.stdout)
        if r["error"] or p.returncode != 0:
            raise BackendError(f"goose 报错（退出码 {p.returncode}）："
                               f"{(r['error'] or _head(p.stderr) or _head(p.stdout, 3))[:300]}")
        if not r["text"]:
            raise BackendError(f"goose 的输出里没有回复文本：{_head(p.stdout, 3)[:300]}")
        return r["text"]


CODEX_DEFAULT_MODEL = "gpt-6-luna"
# project-read-only：给验收用。项目目录只读、临时目录可写（pytest 的输出捕获和 tmp_path 要写临时文件，
# 纯 read-only 下起不来，见 20261110-113224 那次 QA 连判两轮「需修改」）。实现上是 workspace-write，
# 但 -C 指向一个空的临时目录，项目目录不在可写范围里；跑完再比对项目文件，被改了就报错
CODEX_SANDBOXES = ("read-only", "workspace-write", "project-read-only")
_SNAP_SKIP = {".venv", ".pytest_cache", "__pycache__", ".git", "node_modules"}


def _tree_snapshot(root):
    """项目目录里每个文件的 (大小, 修改时间)；跳过虚拟环境和各种缓存。比对两次就知道有没有被改。"""
    out = {}
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SNAP_SKIP]
        for f in filenames:
            p = Path(dirpath) / f
            try:
                st = p.stat()
            except OSError:
                continue
            out[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns)
    return out


def _snapshot_diff(before, after):
    """两次快照的差异：新增、删除、改动的文件（相对路径），各最多列 10 个。"""
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    return {k: v[:10] for k, v in (("新增", added), ("删除", removed), ("改动", changed)) if v}


def _codex_cmd(model, sandbox, cwd, out_file, mcp_env=None, effort="medium", network=None):
    """codex exec 的命令行。提示词从标准输入给（最后的「-」）。

    sandbox：read-only / workspace-write（只有 cwd 可写；放开网络，pip install 要用）。
    mcp_env：挂提交工具时传 SubmitChannel.env()，用内联 TOML 配一个 wf 服务。
    不带任何 --dangerously* / full-auto：越权的命令由 codex 的沙箱挡掉。"""
    exe = CodexCLIClient.binary()
    # 模型名可以带「@努力程度」（gpt-6-astra@high），同 cli:claude 的写法；不带用 effort 参数
    model, eff = config.split_effort(model or "")
    effort = eff or effort
    # --ignore-user-config：不读 ~/.codex/config.toml（登录照旧用 CODEX_HOME），这次调用的配置全由下面的
    # 参数给，同 claude 的 --strict-mcp-config。不加的话全局挂的 MCP 也会进来，比如 gsb_tools 的
    # run_wait / multi_edit 在 codex 沙箱外面跑命令、改文件，等于没有沙箱（实测验收调了 run_wait，一步卡 6 分钟）
    cmd = [exe, "exec", "--ignore-user-config", "-m", model or CODEX_DEFAULT_MODEL, "-s", sandbox,
           "--skip-git-repo-check", "--color", "never", "--json", "-c", f"model_reasoning_effort={effort}",
           "-C", str(cwd), "-o", str(out_file)]
    if sandbox not in ("read-only", "workspace-write"):
        raise BackendError(f"codex 命令行只收 read-only / workspace-write，收到 {sandbox}（project-read-only 要先换算）")
    # 网络：默认只有 workspace-write（实施要装依赖）放开；验收换算来的 workspace-write 传 network=False
    if sandbox == "workspace-write" and (network is None or network):
        cmd += ["-c", "sandbox_workspace_write.network_access=true"]
    if mcp_env is not None:
        from . import wf_submit
        env_toml = "{" + ", ".join(f"{k}={json.dumps(v)}" for k, v in mcp_env.items()) + "}"
        cmd += ["-c", f"mcp_servers.wf.command={json.dumps(sys.executable)}",
                "-c", f"mcp_servers.wf.args=[{json.dumps(str(wf_submit.SERVER))}]",
                "-c", f"mcp_servers.wf.env={env_toml}",
                # exec 模式审批策略是 never：不放行的话 submit 调用直接被拒（「requires approval」）。
                # 只放开 wf 这一个服务，它只有 submit 一个工具
                "-c", 'mcp_servers.wf.default_tools_approval_mode="approve"']
    return cmd + ["-"]


def _codex_usage(stdout, seconds=None):
    """codex exec --json 的事件流里加总每轮（turn.completed）的 token。订阅计费，不报美元。"""
    tot, turns = {}, 0
    for line in (stdout or "").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict) and ev.get("type") == "turn.completed":
            turns += 1
            for k, v in (ev.get("usage") or {}).items():
                if isinstance(v, (int, float)):
                    tot[k] = tot.get(k, 0) + v
    out = {"turns": turns or None, "input_tokens": tot.get("input_tokens"),
           "output_tokens": tot.get("output_tokens"), "cache_read": tot.get("cached_input_tokens"),
           "reasoning_tokens": tot.get("reasoning_output_tokens"), "billing": "subscription"}
    if seconds is not None:
        out["seconds"] = round(seconds, 1)
    return out


class CodexCLIClient(_CLIBackend):
    """codex exec 纯问答：只读沙箱、空的临时目录、不挂 MCP。ChatGPT 登录靠 HOME 下的 ~/.codex。

    codex 没有「整段换掉系统提示词」的参数，system 拼在提示词前面。
    超时：DSL_CODEX_TIMEOUT > config.json 的 codex_timeout > 90 秒。"""

    name = "codex"

    @staticmethod
    def binary() -> str:
        exe = os.environ.get("GSB_CODEX_BIN") or shutil.which("codex")
        if not exe:
            raise BackendError("找不到 codex（PATH 里没有；可用 GSB_CODEX_BIN 指定）")
        return exe

    def complete(self, prompt, system, model) -> str:
        if self.use_wsl():
            raise BackendError("codex 后端还不支持经 WSL 调")
        timeout = _setting("DSL_CODEX_TIMEOUT", "codex_timeout", DEFAULT_TIMEOUT)
        with tempfile.TemporaryDirectory(prefix="dsl_codex_") as cwd:
            out = Path(cwd) / "reply.txt"
            cmd = _codex_cmd(model, "read-only", cwd, out)
            text = f"{system or DEFAULT_SYSTEM}\n\n{prompt}"
            try:
                p = subprocess.run(cmd, cwd=cwd, env=_agentic_env(cwd, False), input=text,
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=timeout)
            except subprocess.TimeoutExpired:
                raise BackendError(f"codex 超过 {timeout} 秒没有返回（可用 DSL_CODEX_TIMEOUT 调大）") from None
            reply = out.read_text(encoding="utf-8").strip() if out.exists() else ""
        if p.returncode != 0 or not reply:
            raise BackendError(f"codex 报错（退出码 {p.returncode}）：{_head(p.stderr or p.stdout)[:300]}")
        return reply


BATCHMGR_URL = os.environ.get("BATCHMGR_URL", "http://127.0.0.1:8010")


BATCHMGR_TRY_TIMEOUT = int(os.environ.get("DSL_BATCHMGR_TRY_TIMEOUT") or 120)


def _batchmgr_goose_json(prompt, system, model, schema, max_tries=3, timeout=900):
    """本进程环境里没有 Z.AI key 时，经 batchmgr（它的进程里有 key）跑一次 gsbatch 纯问答，
    要 JSON 回复、按 schema 校验，错了把错误附上重问，最多 max_tries 次。key 不经过本进程。

    返回 (结果 dict, 用量 dict)。batchmgr 连不上 / 一直交错 → BackendError。"""
    import time as _time
    import urllib.error
    import urllib.request
    from . import wf_submit

    def call(method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(BATCHMGR_URL + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise BackendError(f"batchmgr {path} 返回 {e.code}：{e.read().decode(errors='replace')[:300]}") from None
        except (urllib.error.URLError, OSError) as e:
            raise BackendError(f"goose：本进程环境里没有 Z.AI key，batchmgr（{BATCHMGR_URL}）也连不上：{e}") from None

    base = (f"{system or DEFAULT_SYSTEM}\n\n{prompt}\n\n按下面的 JSON Schema 只返回一个 JSON 对象，"
            f"不要代码围栏或解释：\n{json.dumps(schema, ensure_ascii=False)}")
    feedback, usage, t0 = "", {"billing": "subscription", "est_usd": 0.0, "tries": 0}, _time.time()
    for _ in range(max(1, max_tries)):
        # batchmgr 用「\n---\n」切任务：正文里的分隔线换掉，免得被拆成几条
        text = (base + feedback).replace("\n---\n", "\n- - -\n")
        # 每次尝试的超时：正常 20–40 秒；goose 偶尔卡住一个请求都不发（20261110-213459 那次卡满 600 秒才重试），
        # 设短一点好早点换下一次
        r = call("POST", "/api/submit", {"kind": "gsbatch", "prompts": text, "model": model or "",
                                         "permission_mode": "chat", "extra_tools": "false",
                                         "timeout": BATCHMGR_TRY_TIMEOUT, "name": "wf-goose"})
        jid = r.get("job_id")
        if not jid:
            raise BackendError(f"batchmgr 没有返回 job_id：{str(r)[:300]}")
        while True:
            _time.sleep(3)
            st = call("GET", f"/api/job/gsbatch/{jid}").get("job") or {}
            if st.get("status") not in ("queued", "running"):
                break
            if _time.time() - t0 > timeout:
                raise BackendError(f"goose（经 batchmgr）超过 {timeout} 秒没有返回，任务 {jid}")
        task = (st.get("tasks") or [{}])[0]
        usage["tries"] += 1
        usage.setdefault("attempts", []).append({"job": jid, "status": task.get("status"),
                                                 "seconds": task.get("seconds")})
        usage["est_usd"] = round(usage["est_usd"] + (task.get("cost_est_usd") or 0), 6)
        out = task.get("output") or ""
        try:
            result = json.loads(strip_json(out))
        except (ValueError, TypeError):
            feedback = f"\n\n上一次的回复不是 JSON 对象（开头：{out[:80]!r}），这次只返回 JSON。"
            continue
        errors = wf_submit.validate(schema, result) if isinstance(result, dict) else ["(顶层): 必须是对象"]
        if not errors:
            usage["seconds"] = round(_time.time() - t0, 1)
            usage["total_usd"] = usage["est_usd"]
            return result, usage
        feedback = "\n\n上一次的结果不符合格式，改掉这些再返回完整 JSON：\n" + "\n".join(errors[:10])
    raise BackendError(f"goose（经 batchmgr）{max_tries} 次都没有按格式返回。最后：{feedback[-400:]}")


_BACKENDS = {"claude": ClaudeCLIClient(), "zcode": ZCodeClient(),
             "goose": GooseCLIClient(), "codex": CodexCLIClient()}


class RouterClient:
    """包住原客户端，按模型的通道分派。api:zhipu 的调用转给内层。

    其它属性（model、calls、embed、image……）都读写到内层，
    所以拿它当原客户端用没有区别。
    """

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __setattr__(self, name, value):
        setattr(self._inner, name, value)

    def _plan(self, model, needs=()):
        """[(CLI 后端或 None, 交给它的模型名, 显示名), …]，按顺序试。None 就是
        交给内层。

        第一项是 route 挑的；它走 CLI、档位又写了 fallback（且 fallback 有这次
        要的能力）时，第二项是 fallback：CLI 这次没跑成就改用它。

        内层是离线的假客户端（MockClient(offline=True)，gen run 不带 --real
        时就是它）就什么都不分派、模型名原样交给它：不然「用 快」解析成
        cli:claude/haiku，测试和 mock 模式的服务会真去起 claude -p。
        """
        if getattr(self._inner, "offline", False) is True:
            return [(None, model, model)]
        default = getattr(self._inner, "model", None)
        r = route(model, needs, default=default)
        plan = [(r.backend, r.model, r.spec.canonical if r.spec else model)]
        if r.backend is None:
            return plan
        resolved = config.resolve_spec(
            model if isinstance(model, str) and model
            else (default if isinstance(default, str) else None))
        fb = resolved[2] if resolved else None
        if (fb is None or fb.canonical == r.spec.canonical
                or not fb.backend.ready
                or any(fb.cap(n) == "no" for n in needs)):
            return plan
        plan.append((_BACKENDS[fb.provider] if fb.channel == "cli" else None,
                     fb.model, fb.canonical))
        return plan

    def _pick(self, model, needs=()):
        """(CLI 后端或 None, 交给它的模型名)：_plan 的第一项。"""
        return self._plan(model, needs)[0][:2]

    def _run(self, model, needs, cli, inner):
        """按 _plan 的顺序试：CLI 报 BackendError（缺能力的除外）且后面还有
        fallback 就记一条 warning 换下一个。"""
        plan = self._plan(model, needs)
        for i, (b, m, label) in enumerate(plan):
            try:
                return cli(b, m) if b else inner(m)
            except CapabilityError:
                raise
            except BackendError as e:
                if i + 1 >= len(plan):
                    raise
                log.warning("%s 这次没跑成，改用 fallback %s：%s",
                            label, plan[i + 1][2], str(e)[:200])

    def chat(self, prompt, system=None, temperature=None, model=None, **kw):
        return self._run(
            model, (),
            lambda b, m: b.chat(prompt, system=system, model=m),
            lambda m: self._inner.chat(prompt, system=system,
                                       temperature=temperature, model=m, **kw))

    def chat_messages(self, messages, temperature=None, model=None, **kw):
        return self._run(
            model, (),
            lambda b, m: b.chat_messages(messages, model=m),
            lambda m: self._inner.chat_messages(messages, temperature=temperature,
                                                model=m, **kw))

    def chat_raw(self, messages, model=None, **kw):
        return self._run(
            model, ("tools",) if kw.get("tools") else (),
            lambda b, m: b.chat_raw(messages, model=m, **kw),
            lambda m: self._inner.chat_raw(messages, model=m, **kw))

    def chat_json(self, prompt, system=None, temperature=None, model=None,
                  **kw):
        return self._run(
            model, (),
            lambda b, m: b.chat_json(prompt, system=system, model=m,
                                     retries=kw.get("retries", 0)),
            lambda m: self._inner.chat_json(prompt, system=system,
                                            temperature=temperature, model=m, **kw))

    def chat_json_messages(self, messages, temperature=None, model=None, **kw):
        return self._run(
            model, (),
            lambda b, m: b.chat_json_messages(messages, model=m,
                                              retries=kw.get("retries", 0)),
            lambda m: self._inner.chat_json_messages(
                messages, temperature=temperature, model=m, **kw))

    # 流式：主模型是真流式（api）就原样返回内层的生成器。走 CLI 时本来就是
    # 整段一次性返回，在生成器里先跑完 CLI、出错再换 fallback——错是在迭代
    # 时才抛的，包在外面的 try 接不住
    def _stream(self, model, cli, inner):
        plan = self._plan(model, ("stream",))
        if plan[0][0] is None:
            return inner(plan[0][1])

        def gen():
            for i, (b, m, label) in enumerate(plan):
                try:
                    chunks = list(cli(b, m)) if b else None
                except CapabilityError:
                    raise
                except BackendError as e:
                    if i + 1 >= len(plan):
                        raise
                    log.warning("%s 这次没跑成，改用 fallback %s：%s",
                                label, plan[i + 1][2], str(e)[:200])
                    continue
                if chunks is None:
                    yield from inner(m)
                else:
                    yield from chunks
                return
        return gen()

    def stream(self, prompt, system=None, temperature=None, model=None, **kw):
        return self._stream(
            model,
            lambda b, m: b.stream(prompt, system=system, model=m),
            lambda m: self._inner.stream(prompt, system=system,
                                         temperature=temperature, model=m, **kw))

    def stream_messages(self, messages, temperature=None, model=None, **kw):
        return self._stream(
            model,
            lambda b, m: b.stream_messages(messages, model=m),
            lambda m: self._inner.stream_messages(
                messages, temperature=temperature, model=m, **kw))


# agentic 角色可以额外挂的 gsb_tools 工具（tools/gsb_tools_mcp.py）。只开不绕过命令白名单的：
# probe 是只读探针（Claude haiku，plan 模式），review 是独立审查员（只读）；*_wait 跟着自动挂上。
# 不开 run_wait（任意 shell）、read_files（任意路径）、multi_edit（与 Edit 重复）、verify（按引擎仓库
# 的 .venv 核对环境，普通项目会判「环境不符」）。
GSB_AGENT_TOOLS = ("probe", "review")     # 角色卡 agentic.mcp_tools 能写的全部
_GSB_WAIT = {"probe": "probe_wait", "review": "review_wait"}


def gsb_claude_bin():
    """claude 可执行文件的绝对路径：GSB_CLAUDE_BIN > PATH > ~/.local/bin/claude；都没有返回 None。"""
    for cand in (os.environ.get("GSB_CLAUDE_BIN"), shutil.which("claude"),
                 str(Path.home() / ".local" / "bin" / "claude")):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return os.path.abspath(cand)     # 不解开链接：claude 升级后链接指向新版本
    return None


def gsb_mcp(tools):
    """(mcpServers 里的一项, 要放行的工具名列表)。tools 为空返回 (None, [])。只管 probe、review。"""
    tools = [t for t in dict.fromkeys(tools or []) if t in _GSB_WAIT]
    if not tools:
        return None, []
    names = []
    for t in tools:
        names += [t, _GSB_WAIT[t]]
    env = {"GSB_TOOLS_ONLY": ",".join(names), "GSB_MAX_BLOCK": "270"}
    # 探针和审查要再起 claude：服务端只在 PATH 里找，而后台跑编排的进程 PATH 里常常没有 ~/.local/bin
    # （真跑时 review 报过「找不到 claude」）。这里找到绝对路径直接交给它
    claude = gsb_claude_bin()
    if claude:
        env["GSB_CLAUDE_BIN"] = claude
    if "probe" in tools:
        env.update(GSB_PROBE="1", GSB_PROBE_BACKEND="claude")
    if "review" in tools:
        env.update(GSB_REVIEW="1", GSB_REVIEW_BACKEND="claude")
    server = {"command": sys.executable,
              "args": [str(Path(__file__).resolve().with_name("gsb_tools_mcp.py"))], "env": env}
    return server, [f"mcp__gsb__{n}" for n in names]


def agent_mcp(tools, cost_log=None):
    """角色卡的 mcp_tools → ({服务名: 配置}, 要放行的工具名列表)。空的返回 ({}, [])。

    cost_log：挂上的工具自己再调模型时把费用记到这里（一行一次），_usage 加总进这一步的用量。
    现在挂的探针、审查没接这个，传了也不用；留着给以后要记账的工具。"""
    servers, allowed = {}, []
    server, names = gsb_mcp(tools)
    if server:
        servers["gsb"] = server
        allowed += names
    return servers, allowed


# 最近一次 claude_agentic / submit_call 的实际用量（claude 自己报的费用和 token），编排节点读了记进过程记录。
# 每个编排进程一次只跑一个节点，用模块变量就够；调用前清空，拿不到就是 None。
LAST_USAGE = {"value": None}


def _usage(result_json, cost_log=None, seconds=None):
    """从 claude -p --output-format json 的结果里取费用和用量；再加上 cost_log 里记的工具内部花费。"""
    out = {}
    if isinstance(result_json, dict):
        u = result_json.get("usage") or {}
        out = {"cost_usd": result_json.get("total_cost_usd"), "turns": result_json.get("num_turns"),
               "input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
               "cache_read": u.get("cache_read_input_tokens"),
               "cache_creation": u.get("cache_creation_input_tokens")}
    if cost_log and Path(cost_log).is_file():
        rows = [json.loads(x) for x in Path(cost_log).read_text(encoding="utf-8").splitlines() if x.strip()]
        costs = [r.get("cost_usd") for r in rows if isinstance(r.get("cost_usd"), (int, float))]
        out.update(tool_calls=len(rows), tool_cost_usd=round(sum(costs), 6))
    if seconds is not None:
        out["seconds"] = round(seconds, 1)
    if out.get("cost_usd") is not None or out.get("tool_cost_usd"):
        out["total_usd"] = round((out.get("cost_usd") or 0) + (out.get("tool_cost_usd") or 0), 6)
    return out or None


def _last_json(text):
    """标准输出里最后一个整行 JSON 对象（claude --output-format json 只打一行）。"""
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def claude_agentic(prompt, system, model, cwd, allowed_tools, timeout=600,
                   max_turns=40, venv=False, mcp_tools=None) -> str:
    """带工具的 claude -p：在 cwd 里按 allowed_tools 干活（acceptEdits），返回最后的回复文本。

    只给 workflow 的 agentic 角色用（verbs/workflow/_agents.py）。不经 RouterClient，
    所以不计入引擎的调用预算、没有 fallback。system 用 --append-system-prompt 追加在
    Claude Code 自己的系统提示词后面（它要靠那段提示词才会用工具）。allowed_tools 之外的
    工具在无头模式下直接被拒，拒了哪些记 warning。
    """
    spec = config.parse_model(model)
    if (spec.channel, spec.provider) != ("cli", "claude"):
        raise BackendError(f"agentic 只支持 cli:claude，收到 {spec.canonical}")
    if ClaudeCLIClient().use_wsl():
        raise BackendError("agentic 还不支持经 WSL 调")
    name, effort = config.split_effort(spec.model or "")
    cmd = [ClaudeCLIClient.binary(), "-p", prompt, "--output-format", "json",
           "--strict-mcp-config", "--permission-mode", "acceptEdits",
           "--max-turns", str(max_turns),
           "--append-system-prompt", system or DEFAULT_SYSTEM]
    if name:
        cmd += ["--model", name]
    if effort:
        cmd += ["--effort", effort]
    LAST_USAGE["value"] = None
    cost_log = Path(tempfile.mkdtemp(prefix="wf_cost_")) / "algo.jsonl"
    servers, extra = agent_mcp(mcp_tools, cost_log)
    if servers:
        cmd += ["--mcp-config", json.dumps({"mcpServers": servers}, ensure_ascii=False)]
    cmd += ["--allowed-tools", *allowed_tools, *extra]
    env = _agentic_env(cwd, venv)
    import time as _time
    t0 = _time.time()
    try:
        p = subprocess.run(cmd, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        LAST_USAGE["value"] = _usage(None, cost_log, _time.time() - t0)
        shutil.rmtree(cost_log.parent, ignore_errors=True)
        raise BackendError(f"claude（agentic）超过 {timeout} 秒没有返回") from None
    try:
        r = json.loads(p.stdout)
    except json.JSONDecodeError:
        r = None
    LAST_USAGE["value"] = _usage(r, cost_log, _time.time() - t0)
    shutil.rmtree(cost_log.parent, ignore_errors=True)
    if not isinstance(r, dict):
        raise BackendError(f"claude（agentic）退出码 {p.returncode}，输出不是 JSON："
                           f"{_head(p.stdout, 3)[:300]}\nstderr：{_head(p.stderr)}")
    denied = [x.get("tool_name", "?") for x in r.get("permission_denials") or []]
    if denied:
        log.warning("claude（agentic）被拒的工具调用：%s", denied)
    if p.returncode != 0 or r.get("is_error"):
        raise BackendError(f"claude（agentic）报错（退出码 {p.returncode}）："
                           f"{str(r.get('result') or r.get('subtype') or '')[:300]}")
    return strip_json(r.get("result") or "")


def _agentic_env(cwd, venv):
    """claude 子进程的环境：订阅登录（去掉 API key）；venv=True 时指向 cwd/.venv（没有就建）。"""
    from .cbatch import _child_env
    env = _child_env()
    env.pop("ANTHROPIC_API_KEY", None)
    if venv:
        # 项目专用虚拟环境：没有就建；agent 命令里的 python / pip / pytest 都指向它
        vdir = Path(cwd) / ".venv"
        if not (vdir / "bin" / "python").exists():
            base = shutil.which("python3") or sys.executable
            r = subprocess.run([base, "-m", "venv", str(vdir)], capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                raise BackendError(f"建虚拟环境失败：{_head(r.stderr)}")
            # 新环境先在沙箱外装好 pytest：codex 沙箱里联网装包很慢（实测第一个实施步骤 7 分钟耗在
            # pip install pytest 上），claude 也省一轮。装不上不拦，agent 自己还能装
            try:
                pr = subprocess.run([str(vdir / "bin" / "python"), "-m", "pip", "install", "-q",
                                     "--disable-pip-version-check", "pytest"],
                                    capture_output=True, text=True, timeout=300)
                if pr.returncode != 0:
                    logging.getLogger(__name__).warning("新虚拟环境预装 pytest 失败：%s", _head(pr.stderr))
            except subprocess.TimeoutExpired:
                logging.getLogger(__name__).warning("新虚拟环境预装 pytest 超过 300 秒，跳过")
        for k in ("PYTHONHOME", "PYTHONPATH", "CONDA_PREFIX"):
            env.pop(k, None)
        env["VIRTUAL_ENV"] = str(vdir)
        env["PATH"] = str(vdir / "bin") + os.pathsep + env.get("PATH", "")
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return env


def submit_call(prompt, system, model, schema, agentic=None, max_tries=3, timeout=None, via=None):
    """让模型用 submit 工具按格式交结果，返回结果 dict（已校验）。

    timeout：纯问答（非 agentic）这一次的超时秒数，角色卡的 timeout 传进来；不给就用
    DSL_<后端>_TIMEOUT / config.json / 默认 90 秒。claude、codex、本机 goose 都认；经 batchmgr 的
    goose 用 BATCHMGR_TRY_TIMEOUT（每次尝试）。agentic 的超时在 agentic["timeout"] 里。

    via：goose 走哪条路。None = 本进程有 Z.AI key 就本机起 goose，没有就经 batchmgr；
    "batchmgr" = 一律经 batchmgr（本机 goose 在 MCP 里审长约定 300 秒交不上，batchmgr 54 秒）。

    只支持 cli:claude 和 cli:goose。agentic（cwd、allowed_tools、timeout、max_turns、venv）
    只支持 claude：原来的工具照旧，额外多一个 submit。不经 RouterClient：不计入引擎的
    调用预算、没有 fallback（同 claude_agentic）。没交、或交错 max_tries 次，报 BackendError，
    信息里带最后几次的格式错误。
    """
    from . import wf_submit
    r = route(model)
    if r.backend is None or r.backend.name not in ("claude", "goose", "codex"):
        raise CapabilityError(f"按格式提交只支持 cli:claude、cli:goose 和 cli:codex，收到 {model}")
    backend = r.backend
    if backend.use_wsl():
        raise BackendError("按格式提交还不支持经 WSL 调")
    if agentic and backend.name not in ("claude", "codex"):
        raise BackendError(f"agentic 只支持 cli:claude 和 cli:codex，收到 {model}")
    if backend.name == "goose":
        from . import gsbatch
        if via == "batchmgr" or not gsbatch._zai_key():
            # 指定经 batchmgr，或本进程（MCP 服务 / 编排）环境里没有 Z.AI key：经 batchmgr 跑，key 只留在它那里
            LAST_USAGE["value"] = None
            result, usage = _batchmgr_goose_json(prompt, system, r.model, schema, max_tries)
            LAST_USAGE["value"] = usage
            return result
    ask = ("\n\n结果必须调用 submit 工具提交（参数就是结果本身，格式由工具定义）。"
           "不要把结果写在回复里。提交成功后不要再输出任何内容。")
    ch = wf_submit.SubmitChannel(schema, max_tries)
    LAST_USAGE["value"] = None
    cost_log = ch.dir / "algo_cost.jsonl"
    import time as _time
    t0 = _time.time()
    slot = _slots(backend.name)
    wait = _setting(f"DSL_{backend.name.upper()}_QUEUE_WAIT", f"{backend.name}_queue_wait",
                    DEFAULT_QUEUE_WAIT)
    if not slot.acquire(timeout=max(0, wait)):
        ch.close()
        raise BackendError(f"{backend.name} 同时在跑的进程满了，排队 {wait} 秒没轮到")
    try:
        if backend.name == "claude":
            name, effort = config.split_effort(r.model or "")
            servers, extra = agent_mcp((agentic or {}).get("mcp_tools"), cost_log)
            # 提示词从标准输入给：长参考文本（如 133KB 的重构分析）当命令行参数会超过单个参数 128KB 的上限（E2BIG）
            cmd = [ClaudeCLIClient.binary(), "-p", "--output-format", "json",
                   *ch.claude_args(servers or None)]
            if agentic:
                cwd = agentic["cwd"]
                timeout = agentic.get("timeout", 600)
                env = _agentic_env(cwd, agentic.get("venv"))
                cmd += ["--permission-mode", "acceptEdits",
                        "--max-turns", str(agentic.get("max_turns", 40)),
                        "--append-system-prompt", system or DEFAULT_SYSTEM,
                        "--allowed-tools", *agentic["allowed_tools"], *extra, wf_submit.CLAUDE_TOOL]
            else:
                cwd = ch.dir
                timeout = timeout or _setting("DSL_CLAUDE_TIMEOUT", "claude_timeout", DEFAULT_TIMEOUT)
                env = _agentic_env(cwd, False)
                # 纯问答：内置工具全关，只剩 submit；轮数留给交错重交
                cmd += ["--tools", "", "--max-turns", str(max_tries + 2),
                        "--system-prompt", system or DEFAULT_SYSTEM,
                        "--allowed-tools", wf_submit.CLAUDE_TOOL]
            if name:
                cmd += ["--model", name]
            if effort:
                cmd += ["--effort", effort]
            try:
                # grace：交了以后等它自己退出，才拿得到 claude 报的本次费用和用量
                result, out = ch.run(cmd, cwd, env, prompt + ask, timeout, "claude", grace=30)
            finally:
                LAST_USAGE["value"] = _usage(_last_json(getattr(ch, "stdout", "")), cost_log, _time.time() - t0)
        elif backend.name == "codex":
            # agentic：在 cwd 里干活，权限由 codex 沙箱管（workspace-write 只能写 cwd）；否则只读、空目录
            project, before, network, where = None, None, None, ""
            if agentic:
                cwd, sandbox = agentic["cwd"], agentic.get("sandbox") or "workspace-write"
                timeout = agentic.get("timeout", 600)
                env = _agentic_env(cwd, agentic.get("venv"))
                if sandbox == "project-read-only":
                    # 验收：codex 的工作目录换成空的临时目录（可写，放 pytest 的临时文件），项目目录不在可写范围
                    project, cwd = Path(cwd), ch.dir / "qa_scratch"
                    cwd.mkdir(exist_ok=True)
                    sandbox, network = "workspace-write", False
                    env = dict(env, TMPDIR=str(cwd), PYTHONDONTWRITEBYTECODE="1")
                    before = _tree_snapshot(project)
                    where = (f"【工作环境】项目目录（只读）：{project}。先 cd 进去再读文件、跑测试；"
                             f"临时文件写在 {cwd}（TMPDIR 已指向它）。不能改项目里的任何文件。\n\n")
            else:
                cwd, sandbox = ch.dir, "read-only"
                timeout = timeout or _setting("DSL_CODEX_TIMEOUT", "codex_timeout", DEFAULT_TIMEOUT)
                env = _agentic_env(cwd, False)
            if agentic and agentic.get("venv"):
                # codex 沙箱里的 shell 是登录 shell（bash -lc），会重置 PATH，环境变量里的虚拟环境不生效：
                # 直接告诉它绝对路径
                vpy = Path(project or agentic["cwd"]) / ".venv" / "bin" / "python"
                where += (f"【虚拟环境】命令里用 {vpy}（如 {vpy} -m pytest、{vpy} -m pip install -r requirements.txt）；"
                          f"沙箱里的 shell 不带这个环境，裸写 python / pytest 找不到。\n\n")
            reply_f = ch.dir / "codex_reply.txt"
            cmd = _codex_cmd(r.model, sandbox, cwd, reply_f, mcp_env=ch.env(), network=network)
            # 事件流带时间戳另存一份（哪一步慢就看两行之间的间隔），路径记进这一步的用量
            log_dir = Path(os.environ.get("DSL_CODEX_LOG_DIR") or Path(__file__).resolve().parents[1] / "data" / "codex_logs")
            event_log = None
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
                event_log = log_dir / f"{_time.strftime('%Y%m%d-%H%M%S')}_{os.getpid()}_{ch.dir.name}.log"
                cmd = [sys.executable, str(Path(__file__).with_name("ts_tee.py")), str(event_log), "--", *cmd]
            except OSError:
                event_log = None
            # codex 没有换系统提示词的参数：角色说明拼在最前面
            text = f"{system or DEFAULT_SYSTEM}\n\n{where}{prompt}{ask}"
            try:
                result, out = ch.run(cmd, cwd, env, text, timeout, "codex", grace=10)
            finally:
                LAST_USAGE["value"] = _codex_usage(getattr(ch, "stdout", ""), _time.time() - t0)
                if event_log is not None:
                    LAST_USAGE["value"]["event_log"] = str(event_log)
            if project is not None:
                diff = _snapshot_diff(before, _tree_snapshot(project))
                if diff:
                    raise BackendError(f"codex（只读验收）改动了项目文件：{diff}")
        else:
            from . import gsbatch
            provider = _text_setting("DSL_GOOSE_PROVIDER", "goose_provider") or "zai_low"
            if provider != "zai_low":
                raise BackendError(f"goose 后端目前只接了 zai_low，不支持 {provider}")
            key = gsbatch._zai_key()
            if not key:
                raise BackendError("goose：环境里没有 ZAI_CODING_PLAN_API_KEY"
                                   "（要在 MCP 服务或 cbatch 起的进程里调）")
            try:
                gsbatch._ensure_zai_low()
            except gsbatch.GSBatchError as e:
                raise BackendError(f"goose：{e}") from None
            timeout = timeout or _setting("DSL_GOOSE_TIMEOUT", "goose_timeout", DEFAULT_TIMEOUT)
            env = {k: v for k, v in gsbatch._child_env().items()
                   if not k.startswith("GOOSE_") and not gsbatch._leaky_env(k, v)}
            # auto：工具调用自动批准（只挂了 submit 一个扩展，--no-profile 不带别的）
            env.update(GOOSE_DISABLE_KEYRING="1", GOOSE_DISABLE_SESSION_NAMING="true",
                       GOOSE_MODE="auto", ZAI_CODING_PLAN_API_KEY=key)
            cmd = [GooseCLIClient.binary(), "run", "--no-profile", "--no-session",
                   "--output-format", "stream-json", "--provider", provider,
                   "--model", r.model or gsbatch.DEFAULT_MODELS[provider],
                   "--max-turns", str(max_tries + 3),
                   "--with-extension", ch.goose_extension(),
                   "--system", system or DEFAULT_SYSTEM, "-i", "-"]
            result, out = ch.run(cmd, ch.dir, env, prompt + ask, timeout, "goose")
        if result is None:
            tries = ch.errors()
            why = (f"交错 {len(tries)} 次：" + "；".join("、".join(t["errors"][:3]) for t in tries[-2:])
                   if tries else "没有调用 submit")
            raise BackendError(f"{backend.name} 没有按格式提交（{why}）。输出末尾：{_head(out[-1500:], 8)[:600]}")
        return result
    except wf_submit.SubmitError as e:
        raise BackendError(str(e)) from None
    finally:
        slot.release()
        ch.close()


def wrap(client):
    """套一层 RouterClient；已经套过的原样返回。None 原样返回。"""
    if client is None or isinstance(client, RouterClient):
        return client
    return RouterClient(client)
