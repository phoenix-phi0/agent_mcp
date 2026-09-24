"""MCP 服务器：文件读写 + 智谱调用 + DSL + agent。

目录约定：

    mcp/                     ← BASE，项目根
        fs.py                本文件
        config.json          智谱配置（不在 data 内，外部读不到）
        tools/               DSL 引擎与客户端
        agents/              agent 框架
        verbs/               动词包（会被执行，必须不可外部写入）
            common/
            quiz/
            japanese/
        workspace/japanese/  agent 的工作目录
        data/                ← DATA，唯一对外可写的目录

启动：
    py fs.py
    cloudflared tunnel --url http://127.0.0.1:8000

连接器 URL 填 https://<隧道域名>/mcp
"""

import contextlib
import io
import secrets
import sys
from functools import lru_cache
from pathlib import Path

from fastmcp import FastMCP

BASE = Path(__file__).resolve().parent          # mcp/
DATA = BASE / "data"                            # 唯一可写目录
VERBS = BASE / "verbs"                          # 动词包
WORKSPACE = BASE / "workspace" / "japanese"     # agent 工作目录
DATA.mkdir(exist_ok=True)

if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

# 换成你自己生成的：py -c "import uuid;print(uuid.uuid4())"
KEY = "8d055c36-0f9d-472a-b0cb-54ecacceb5ac"

# 默认加载的动词包，按顺序，后者覆盖前者
PACKS = ["common", "quiz", "japanese"]

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
    import json
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
# DSL
# ----------------------------------------------------------------------


@mcp.tool
def dsl_run(key: str, script: str, real: bool = False) -> str:
    """执行 DSL 脚本。real=False 用假客户端，不消耗额度。"""
    check(key)
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
def dsl_run_file(key: str, path: str, real: bool = False) -> str:
    """执行 data/ 下的 DSL 脚本文件。"""
    check(key)
    return dsl_run.fn(key, safe(path).read_text(encoding="utf-8"), real)


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
    for name in [n for n in list(sys.modules) if n.startswith("tools")]:
        del sys.modules[name]
    import tools.test_dsl as t
    return _capture(t.main)


# ----------------------------------------------------------------------
# Agent
# ----------------------------------------------------------------------


@mcp.tool
def agent_send(key: str, message: str, reset: bool = False) -> str:
    """跟日语教师 agent 对话一轮。reset=True 清空历史并重新加载代码。"""
    check(key)

    if reset:
        for name in [n for n in list(sys.modules)
                     if n.startswith(("agents", "tools"))]:
            del sys.modules[name]
        _agent_cache.clear()
        _client.cache_clear()

    from agents.japanese import make_teacher, init_workspace

    if "teacher" not in _agent_cache:
        init_workspace()
        _agent_cache["teacher"] = make_teacher()

    a = _agent_cache["teacher"]

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
def agent_state(key: str) -> str:
    """查看 agent 当前状态：工具列表、对话轮数、token 消耗。"""
    check(key)
    if "teacher" not in _agent_cache:
        return "agent 尚未启动，先调 agent_send"
    return _agent_cache["teacher"].dump_state()


@mcp.tool
def agent_transcript(key: str) -> str:
    """导出 agent 的对话记录，调试用。"""
    check(key)
    if "teacher" not in _agent_cache:
        return "agent 尚未启动"
    return _agent_cache["teacher"].transcript()


# ----------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="http", port=8000)
