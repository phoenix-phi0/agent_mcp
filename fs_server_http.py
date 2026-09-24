"""MCP 服务器：文件读写 + 智谱调用 + DSL + agent。

目录约定：

    mcp/                     ← BASE，项目根
        fs.py                本文件
        config.json          智谱配置（不在 data 内，外部读不到）
        tools/               DSL 引擎、渲染器、UI 引擎
        agents/              agent 框架
        templates/           Jinja 模板（db / backend / frontend）
        verbs/               动词包（会被执行，必须不可外部写入）
        workspace/japanese/  日语 agent 的工作目录
        data/                ← DATA，唯一对外可写的目录

启动：
    py fs.py
    cloudflared tunnel --url http://127.0.0.1:8000

连接器 URL 填 https://<隧道域名>/mcp
"""

import contextlib
import importlib
import inspect
import io
import json
import re
import secrets
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from fastmcp import FastMCP

BASE = Path(__file__).resolve().parent          # mcp/
DATA = BASE / "data"                            # 唯一可写目录
VERBS = BASE / "verbs"                          # 动词包
WORKSPACE = BASE / "workspace" / "japanese"     # 日语 agent 工作目录
DATA.mkdir(exist_ok=True)

if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

# 换成你自己生成的：py -c "import uuid;print(uuid.uuid4())"
KEY = "8d055c36-0f9d-472a-b0cb-54ecacceb5ac"

# 默认加载的动词包，按顺序，后者覆盖前者
PACKS = ["common", "quiz", "japanese", "web"]

# 可用的 agent：名字 -> (模块, 工厂函数)
_AGENTS = {
    "teacher": ("agents.japanese", "make_teacher"),
    "web": ("agents.web", "make_builder"),
}

# ZCode 内置工具。MCP 接口只允许选择只读工具，避免通过该入口编辑文件或
# 执行 shell；传空字符串可以完全不带内置工具。
_ZCODE_BUILTIN_TOOLS = (
    "Read", "Grep", "Glob", "Bash", "Edit", "Write", "WebFetch",
    "WebSearch", "TodoWrite", "Agent", "Skill",
)
_ZCODE_READONLY_TOOLS = frozenset({"Read", "Grep", "Glob"})

# ----------------------------------------------------------------------
# tools 调用白名单
#
# 为什么是白名单而不是任意 import：这套目录的安全性建立在「可写的地方
# （data/）不会被执行，会执行的地方（tools/ verbs/ agents/）不可写」
# 这条界线上。一个能调任意函数、参数还由调用方给的入口，等于把这条界线
# 抹掉——tools 里有能写文件的函数，路径参数一给就出去了。
#
# 加一行的成本是改这个字典重启一次；抹掉界线的成本是整套假设作废。
# 这个入口是给排查用的，agent 的常规路径仍然是 .zs + 动词。
# ----------------------------------------------------------------------
_CALLABLE = {
    # UI 引擎
    "ui.parse":      ("tools.ui", "parse"),
    "ui.dump":       ("tools.ui", "dump"),
    "ui.check":      ("tools.ui", "check"),
    "ui.bind":       ("tools.ui", "bind"),
    "ui.validate":   ("tools.ui", "validate"),
    "ui.compile":    ("tools.ui", "compile_ui"),
    "ui.backends":   ("tools.ui", "BACKENDS"),
    # 把 .ui 里的「全部字段 article」展开成具体字段。收两个路径（相对
    # data/），自己去读——比把 .entity 全文塞进 JSON 参数转义一遍顺手，
    # 而 tool_call_file 一次只能塞一个文件，这件事要两个。
    "ui.expand":     ("tools.ui_entity", "check_files"),
    # 实体（数据模型）
    "entity.parse":    ("tools.entity", "parse"),
    "entity.check":    ("tools.entity", "check"),
    "entity.validate": ("tools.entity", "validate"),
    "entity.dump":     ("tools.entity", "dump"),
    "entity.sql":      ("tools.entity", "render_sql"),
    # ZBatch 批量任务（跑在 Windows 上的小服务，把提示词逐条交给 WSL 的
    # zcode）。submit 单次上限 10 条、服务没跑时不自动拉起——见 zbatch.py
    # 模块文档里的理由。
    "zbatch.describe": ("tools.zbatch", "describe"),
    "zbatch.submit":   ("tools.zbatch", "submit"),
    "zbatch.status":   ("tools.zbatch", "status"),
    "zbatch.wait":     ("tools.zbatch", "wait"),
    "zbatch.jobs":     ("tools.zbatch", "jobs"),
    "zbatch.cancel":   ("tools.zbatch", "cancel"),
    # 精确编辑：改几行不用重写整个文件。
    #
    # write_file 只能整个覆盖，改 ui.py（1132 行）里的两行要把一千一百行
    # 原样搬一遍——那实际压垮过服务器两次，交给 zcode 做同样的事也超时。
    # 这几个的路径基准是 BASE（项目根），不是 data/——它们存在的意义就是
    # 改 tools/ verbs/ 这些 data 之外的代码。
    #
    # 越界、config.json 和 .git 在 fsedit 里挡掉了；每次改动前自动备份到
    # .edit_backup/，file.restore 能撤回上一次。
    "file.edit":    ("tools.fsedit", "edit"),
    "file.append":  ("tools.fsedit", "append"),
    "file.show":    ("tools.fsedit", "show"),
    "file.restore": ("tools.fsedit", "restore"),
    # 渲染器
    "render.types":     ("tools.render", "TYPES"),
    "render.to_sql":    ("tools.render", "to_sql"),
    "render.to_python": ("tools.render", "to_python"),
    "render.to_widget": ("tools.render", "to_widget"),
    "render.db":        ("tools.render", "db_renderer"),
    "render.backend":   ("tools.render", "backend_renderer"),
    "render.frontend":  ("tools.render", "frontend_renderer"),
}

mcp = FastMCP("fs")

_agent_cache: dict = {}


# ----------------------------------------------------------------------
# 基础设施
# ----------------------------------------------------------------------


def check(key: str) -> None:
    """校验访问密钥。用 bytes 比较，非 ASCII 密钥也能用。"""
    if not secrets.compare_digest(key.encode("utf-8"), KEY.encode("utf-8")):
        raise ValueError("密钥错误")


def safe(path: str) -> Path:
    """限制在 data/ 内，挡住 ../ 和绝对路径。"""
    p = (DATA / path).resolve()
    if p != DATA and DATA not in p.parents:
        raise ValueError("路径越界")
    return p


@lru_cache(maxsize=1)
def _client():
    """懒加载真实客户端，没配 API Key 时只要不调它就不报错。"""
    from tools import ZhipuClient
    return ZhipuClient()


def _capture(fn) -> str:
    """执行 fn 并捕获 stdout/stderr。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            fn()
        except SystemExit:
            pass
        except Exception:
            import traceback
            traceback.print_exc()
    return buf.getvalue() or "(无输出)"


def _make_verbs(workspace: Path = DATA):
    """建动词表并加载动词包。workspace 决定动词里文件操作的根目录。"""
    from tools import make_verbs
    reg = make_verbs()
    reg.load_packs(VERBS, PACKS, workspace=workspace)
    return reg


def _drop_modules(*prefixes) -> None:
    """把已加载的模块踢掉，下次 import 时重新读文件。"""
    for name in [n for n in list(sys.modules) if n.startswith(prefixes)]:
        del sys.modules[name]


def _parse_zcode_output(output: str):
    """兼容 ZCode 返回单个 JSON 或逐行 JSON（JSONL）。"""
    text = output.strip()
    if not text:
        raise ValueError("ZCode 没有返回内容")
    try:
        return json.loads(text)
    except json.JSONDecodeError as whole_error:
        try:
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        except json.JSONDecodeError as line_error:
            raise ValueError(f"ZCode 返回的不是合法 JSON：{line_error}") from whole_error


def _extract_zcode_text(value):
    """从不同版本的 ZCode JSON 包装结构中取出最终文本。"""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for name in ("text", "output", "response", "result", "message", "content"):
            if name in value:
                found = _extract_zcode_text(value[name])
                if found:
                    return found
    elif isinstance(value, list):
        for item in reversed(value):
            found = _extract_zcode_text(item)
            if found:
                return found
    return None


def _strip_code_fence(text: str) -> str:
    """去掉模型偶尔附带的 Markdown 代码围栏。"""
    lines = text.strip().splitlines()
    if len(lines) >= 2 and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
    return "\n".join(lines).strip()


# ----------------------------------------------------------------------
# 文件（仅 data/）
# ----------------------------------------------------------------------


@mcp.tool
def list_dir(key: str, path: str = ".") -> str:
    """列出 data/ 下的目录内容。"""
    check(key)
    d = safe(path)
    if not d.is_dir():
        return f"不是目录: {path}"
    items = []
    for p in sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name)):
        items.append(f"{p.name}/" if p.is_dir() else p.name)
    return "\n".join(items) or "(空)"


@mcp.tool
def read_file(key: str, path: str) -> str:
    """读取 data/ 下的文本文件。"""
    check(key)
    return safe(path).read_text(encoding="utf-8")


@mcp.tool
def write_file(key: str, path: str, content: str) -> str:
    """写入 data/ 下的文本文件，父目录自动创建。"""
    check(key)
    f = safe(path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return "已写入"


# ----------------------------------------------------------------------
# 智谱
# ----------------------------------------------------------------------


@mcp.tool
def zhipu_info(key: str) -> str:
    """查看配置：模型、配置文件位置、Key 是否就绪。"""
    check(key)
    from tools import config
    cfg = config.load(reload=True)
    return (
        f"配置文件：{config.source()}\n"
        f"模型：{cfg.get('model')}\n"
        f"接口地址：{cfg.get('base_url')}\n"
        f"API Key：{'已设置' if cfg.get('api_key') else '缺失'}"
    )


@mcp.tool
def zhipu_chat(key: str, prompt: str, system: str = "",
               temperature: float = 0.7) -> str:
    """调用智谱模型，返回回复文本。"""
    check(key)
    return _client().chat(prompt, system=system or None, temperature=temperature)


@mcp.tool
def zhipu_tool_test(key: str) -> str:
    """发一次带工具定义的真实请求，返回原始响应结构。排查用。"""
    check(key)
    tools = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询某个城市的天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "城市名"}},
                "required": ["city"],
            },
        },
    }]
    data = _client().chat_raw(
        [{"role": "user", "content": "杭州今天天气怎么样？"}],
        tools=tools,
        tool_choice="auto",
    )
    return json.dumps(data, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------
# ZCode CLI（Windows MCP 服务 -> WSL）
# ----------------------------------------------------------------------


@mcp.tool
def zcode_generate(
    key: str,
    task: str,
    language: str = "",
    context: str = "",
    allowed_tools: str = "*",
    mode: str = "yolo",
    wsl_cwd: str = "~",
    distribution: str = "",
    wsl_user: str = "",
    timeout: int = 300,
) -> str:
    """通过 WSL 调用 ZCode，并直接返回生成的代码文本。

    allowed_tools:
        "*"                    开放全部内置工具
        ""                     禁用全部内置工具
        "Read,Grep,Glob,Bash"  只开放指定工具

    mode:
        build / edit / plan / yolo

    wsl_cwd:
        "~"                    当前 WSL 用户的主目录
        "/home/ysc/project"    指定 WSL 项目目录
    """
    check(key)

    from tools.zcode_tool import ZCodeTool

    if not task.strip():
        raise ValueError("task 不能为空")

    if mode not in {"build", "edit", "plan", "yolo"}:
        raise ValueError("mode 只能是 build、edit、plan 或 yolo")

    if not wsl_cwd:
        wsl_cwd = "~"

    if wsl_cwd != "~" and not wsl_cwd.startswith("/"):
        raise ValueError("wsl_cwd 必须是 ~ 或 WSL 绝对路径")

    if not 1 <= timeout <= 1800:
        raise ValueError("timeout 必须在 1 到 1800 秒之间")

    value = allowed_tools.strip()

    if value == "*":
        selected_tools = ZCodeTool.BUILTIN_TOOLS
    elif not value:
        selected_tools = ()
    else:
        selected_tools = tuple(
            dict.fromkeys(value.replace(",", " ").split())
        )

    unknown_tools = (
        set(selected_tools) - set(ZCodeTool.BUILTIN_TOOLS)
    )

    if unknown_tools:
        raise ValueError(
            "未知的 ZCode 工具："
            + "、".join(sorted(unknown_tools))
        )

    tool = ZCodeTool(timeout=timeout)

    return tool.generate_code_text_wsl(
        task=task.strip(),
        wsl_cwd=wsl_cwd,
        distribution=distribution.strip() or None,
        user=wsl_user.strip() or None,
        language=language.strip() or None,
        context=context.strip() or None,
        allowed_tools=selected_tools,
        mode=mode,
        timeout=timeout,
    )


# ----------------------------------------------------------------------
# DSL
# ----------------------------------------------------------------------


def _run_dsl(script: str, real: bool) -> str:
    """执行一段 DSL。

    提成普通函数是为了让 dsl_run 和 dsl_run_file 都能调，不必去取被
    @mcp.tool 包装后的原函数——`.fn` 属性只在部分 fastmcp 版本上存在，
    换个版本就会报 'function' object has no attribute 'fn'。
    """
    from tools import DSLEngine, MockClient

    verbs = _make_verbs(DATA)
    client = _client() if real else MockClient()
    engine = DSLEngine(client, workdir=DATA, verbose=False, verbs=verbs)

    out = engine.run(script)

    if verbs.warnings:
        out += "\n\n[动词加载警告]\n" + "\n".join("  " + w for w in verbs.warnings)
    if not real:
        calls = "\n".join(
            f"  {c['type']}: {c.get('prompt', '')[:60]}" for c in client.calls
        )
        out += f"\n\n--- 模拟调用 {len(client.calls)} 次 ---\n{calls}"
    return out


@mcp.tool
def dsl_run(key: str, script: str, real: bool = False) -> str:
    """执行 DSL 脚本。real=False 用假客户端，不消耗额度。"""
    check(key)
    return _run_dsl(script, real)


@mcp.tool
def dsl_run_file(key: str, path: str, real: bool = False) -> str:
    """执行 data/ 下的 DSL 脚本文件。"""
    check(key)
    return _run_dsl(safe(path).read_text(encoding="utf-8"), real)


@mcp.tool
def dsl_help(key: str) -> str:
    """返回 DSL 的语句说明。"""
    check(key)
    from tools import dsl
    return dsl.__doc__ or "无说明"


@mcp.tool
def list_verbs(key: str) -> str:
    """列出所有已加载的动词，按包分组。"""
    check(key)
    from tools import make_verbs
    reg = make_verbs()
    available = reg.available_packs(VERBS)
    reg.load_packs(VERBS, PACKS, workspace=DATA)

    out = (
        f"已加载的包：{', '.join(reg.packs) or '(无)'}\n"
        f"目录下可用的包：{', '.join(available) or '(无)'}\n\n"
        + reg.describe()
    )
    if reg.warnings:
        out += "\n\n[警告]\n" + "\n".join("  " + w for w in reg.warnings)
    return out


@mcp.tool
def run_tests(key: str) -> str:
    """运行 tools/test_dsl.py，返回测试报告。"""
    check(key)
    _drop_modules("tools")
    import tools.test_dsl as t
    return _capture(t.main)


# ----------------------------------------------------------------------
# tools 调用（排查用）
# ----------------------------------------------------------------------


@mcp.tool
def list_calls(key: str) -> str:
    """列出 tool_call 能调的名字，带签名。"""
    check(key)
    out = []
    for name, (mod_name, attr) in sorted(_CALLABLE.items()):
        try:
            obj = getattr(importlib.import_module(mod_name), attr)
            sig = str(inspect.signature(obj)) if callable(obj) else "(常量)"
        except Exception as e:
            sig = f"<加载失败 {type(e).__name__}: {e}>"
        out.append(f"  {name:<18} {mod_name}.{attr} {sig}")
    return "可调用：\n" + "\n".join(out)


@mcp.tool
def tool_call(key: str, name: str, args: str = "{}", reset: bool = False) -> str:
    """调用 tools 下白名单内的函数，用于排查。

    name 见 list_calls；args 是关键字参数的 JSON 对象。
    reset=True 先卸载 tools.* 再调，改了源码不用重启服务器。

    只认白名单：tools 里有能写文件的函数，开放任意调用会让「可写目录
    不被执行、可执行目录不可写」这条界线失效。要加新函数，改 fs.py 的
    _CALLABLE。

    这是排查入口，不是 agent 的常规路径——agent 走 .zs + 动词，那条路
    有语法检查、空跑和行号。
    """
    check(key)
    if name not in _CALLABLE:
        return f"不在白名单：{name}\n可用：{'、'.join(sorted(_CALLABLE))}"

    if reset:
        _drop_modules("tools")

    mod_name, attr = _CALLABLE[name]
    try:
        obj = getattr(importlib.import_module(mod_name), attr)
    except Exception:
        import traceback
        return "加载失败：\n" + traceback.format_exc()

    if not callable(obj):
        return json.dumps(obj, ensure_ascii=False, default=str, indent=2)

    try:
        kwargs = json.loads(args or "{}")
    except json.JSONDecodeError as e:
        return f"args 不是合法 JSON：{e}"
    if not isinstance(kwargs, dict):
        return "args 要是一个 JSON 对象（关键字参数），比如 {\"text\": \"...\"}"

    try:
        result = obj(**kwargs)
    except Exception:
        import traceback
        return "调用出错：\n" + traceback.format_exc()

    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str, indent=2)


@mcp.tool
def tool_call_file(key: str, name: str, path: str, arg: str = "text",
                   args: str = "{}", reset: bool = False) -> str:
    """同 tool_call，但先读 data/ 下的文件，当作某个参数传进去。

    省得把整份 .ui 文本塞进 JSON 里转义。arg 是接收文件内容的参数名。
    """
    check(key)
    text = safe(path).read_text(encoding="utf-8")
    try:
        kwargs = json.loads(args or "{}")
    except json.JSONDecodeError as e:
        return f"args 不是合法 JSON：{e}"
    if not isinstance(kwargs, dict):
        return "args 要是一个 JSON 对象"
    kwargs[arg] = text
    return tool_call(key, name, json.dumps(kwargs, ensure_ascii=False), reset)


# ----------------------------------------------------------------------
# Agent
# ----------------------------------------------------------------------


def _get_agent(name: str):
    """按名字取 agent，第一次取时才构造。"""
    if name not in _AGENTS:
        raise ValueError(f"没有 agent「{name}」，可用：{', '.join(_AGENTS)}")
    if name not in _agent_cache:
        mod_name, factory = _AGENTS[name]
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "init_workspace"):
            mod.init_workspace()
        _agent_cache[name] = getattr(mod, factory)()
    return _agent_cache[name]


@mcp.tool
def agent_send(key: str, message: str, agent: str = "teacher",
               reset: bool = False) -> str:
    """跟 agent 对话一轮。

    agent：teacher（日语教师）或 web（网页生成）。
    reset=True 清空所有 agent 的历史并重新加载代码。
    """
    check(key)

    if reset:
        _drop_modules("agents", "tools")
        _agent_cache.clear()
        _client.cache_clear()

    a = _get_agent(agent)

    # 只统计本轮新增的工具调用
    before = len(a.tool_log)
    reply = a.send(message)
    new_calls = a.tool_log[before:]

    # 流程正文直接呈现，不依赖模型转述
    flow_outputs = [
        x["result"] for x in new_calls
        if x["name"] == "run_flow" and not x["result"].startswith("[")
    ]
    body = "\n\n".join(flow_outputs)
    full = f"{body}\n\n---\n{reply}" if body else reply

    log = "\n".join(
        f"  {x['name']}({x['arguments'][:60]}) → {x['result'][:80]}"
        for x in new_calls
    )
    return (
        f"{full}\n\n"
        f"--- 工具调用 ---\n{log or '(无)'}\n"
        f"--- token {a.usage['total']} ---"
    )


@mcp.tool
def agent_state(key: str, agent: str = "teacher") -> str:
    """查看 agent 当前状态：工具列表、对话轮数、token 消耗。"""
    check(key)
    if agent not in _AGENTS:
        return f"没有 agent「{agent}」，可用：{', '.join(_AGENTS)}"
    if agent not in _agent_cache:
        return f"agent「{agent}」尚未启动，先调 agent_send"
    return _agent_cache[agent].dump_state()


@mcp.tool
def agent_transcript(key: str, agent: str = "teacher") -> str:
    """导出 agent 的对话记录，调试用。"""
    check(key)
    if agent not in _AGENTS:
        return f"没有 agent「{agent}」，可用：{', '.join(_AGENTS)}"
    if agent not in _agent_cache:
        return f"agent「{agent}」尚未启动"
    return _agent_cache[agent].transcript()


@mcp.tool
def list_agents(key: str) -> str:
    """列出可用的 agent 及各自是否已启动。"""
    check(key)
    lines = []
    for name, (mod, factory) in _AGENTS.items():
        状态 = "已启动" if name in _agent_cache else "未启动"
        lines.append(f"  {name} — {mod}.{factory}（{状态}）")
    return "可用 agent：\n" + "\n".join(lines)


# ----------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="http", port=8000)
