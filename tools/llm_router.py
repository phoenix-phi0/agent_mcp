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

同时运行的进程数用信号量限住（默认各 2 个），见 _slots。

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
import tempfile
import threading
from pathlib import Path

from typing import NamedTuple

from . import config
from .zhipu import strip_json

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 180
DEFAULT_MAX_PROCS = 2

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
        with _slots(self.name):
            return self.complete(prompt, system, model)

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
    超时：DSL_CLAUDE_TIMEOUT 环境变量 > config.json 的 claude_timeout > 180 秒
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
        if model:
            opts += ["--model", model]
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
    超时：DSL_ZCODE_TIMEOUT 环境变量 > config.json 的 zcode_timeout > 180 秒
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


_BACKENDS = {"claude": ClaudeCLIClient(), "zcode": ZCodeClient()}


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

    def _pick(self, model, needs=()):
        """(CLI 后端或 None, 交给它的模型名)。None 就是交给内层。

        内层是离线的假客户端（MockClient(offline=True)，gen run 不带 --real
        时就是它）就什么都不分派、模型名原样交给它：不然「用 快」解析成
        cli:claude/haiku，测试和 mock 模式的服务会真去起 claude -p。
        """
        if getattr(self._inner, "offline", False) is True:
            return None, model
        r = route(model, needs, default=getattr(self._inner, "model", None))
        return r.backend, r.model

    def chat(self, prompt, system=None, temperature=None, model=None, **kw):
        b, m = self._pick(model)
        if b:
            return b.chat(prompt, system=system, model=m)
        return self._inner.chat(prompt, system=system, temperature=temperature,
                                model=m, **kw)

    def chat_messages(self, messages, temperature=None, model=None, **kw):
        b, m = self._pick(model)
        if b:
            return b.chat_messages(messages, model=m)
        return self._inner.chat_messages(messages, temperature=temperature,
                                         model=m, **kw)

    def chat_raw(self, messages, model=None, **kw):
        b, m = self._pick(model, ("tools",) if kw.get("tools") else ())
        if b:
            return b.chat_raw(messages, model=m, **kw)
        return self._inner.chat_raw(messages, model=m, **kw)

    def chat_json(self, prompt, system=None, temperature=None, model=None,
                  **kw):
        b, m = self._pick(model)
        if b:
            return b.chat_json(prompt, system=system, model=m,
                               retries=kw.get("retries", 0))
        return self._inner.chat_json(prompt, system=system,
                                     temperature=temperature, model=m, **kw)

    def chat_json_messages(self, messages, temperature=None, model=None, **kw):
        b, m = self._pick(model)
        if b:
            return b.chat_json_messages(messages, model=m,
                                        retries=kw.get("retries", 0))
        return self._inner.chat_json_messages(messages, temperature=temperature,
                                              model=m, **kw)

    def stream(self, prompt, system=None, temperature=None, model=None, **kw):
        b, m = self._pick(model, ("stream",))
        if b:
            return b.stream(prompt, system=system, model=m)
        return self._inner.stream(prompt, system=system,
                                  temperature=temperature, model=m, **kw)

    def stream_messages(self, messages, temperature=None, model=None, **kw):
        b, m = self._pick(model, ("stream",))
        if b:
            return b.stream_messages(messages, model=m)
        return self._inner.stream_messages(messages, temperature=temperature,
                                           model=m, **kw)


def wrap(client):
    """套一层 RouterClient；已经套过的原样返回。None 原样返回。"""
    if client is None or isinstance(client, RouterClient):
        return client
    return RouterClient(client)
