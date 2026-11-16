"""claude 换端点（cli:claude/<端点>:<模型>）：模型名解析、子进程环境、角色卡加载。离线，不起 claude。"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import config, llm_router  # noqa: E402
from tools.llm_router import BackendError, claude_endpoint  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"：{detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def raises(fn):
    try:
        fn()
    except BackendError as e:
        return str(e)
    return None


saved = os.environ.pop("DASHSCOPE_API_KEY", None)
try:
    # 不带前缀：原样返回，环境不动
    env = {"ANTHROPIC_API_KEY": "x", "PATH": "/bin"}
    check("无前缀原样返回", claude_endpoint("sonnet", env) == "sonnet")
    check("无前缀不改环境", env == {"ANTHROPIC_API_KEY": "x", "PATH": "/bin"})
    check("空模型名", claude_endpoint("", {}) == "")

    # 带前缀但没有 key：报错，说出变量名
    msg = raises(lambda: claude_endpoint("bailian:deepseek-v4-pro", {}))
    check("没有 key 报错", msg is not None and "DASHSCOPE_API_KEY" in msg, msg)

    # 不认识的端点、缺模型
    os.environ["DASHSCOPE_API_KEY"] = "sk-sp-test-placeholder"
    msg = raises(lambda: claude_endpoint("nope:deepseek-v4-pro", {}))
    check("未知端点报错", msg is not None and "nope" in msg, msg)
    msg = raises(lambda: claude_endpoint("bailian:", {}))
    check("缺模型报错", msg is not None, msg)

    # 正常：设好端点、key、各档默认模型，清掉 API key 和 OAuth token
    env = {"ANTHROPIC_API_KEY": "should-go", "CLAUDE_CODE_OAUTH_TOKEN": "should-go", "PATH": "/bin"}
    name = claude_endpoint("bailian:deepseek-v4-pro", env)
    check("返回去掉前缀的模型名", name == "deepseek-v4-pro", name)
    base, _ = llm_router.CLAUDE_ENDPOINTS["bailian"]
    check("BASE_URL", env.get("ANTHROPIC_BASE_URL") == base)
    check("AUTH_TOKEN 取自环境变量", env.get("ANTHROPIC_AUTH_TOKEN") == "sk-sp-test-placeholder")
    check("各档默认模型都换掉", all(env.get(k) == "deepseek-v4-pro" for k in (
        "ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_SMALL_FAST_MODEL")))
    check("清掉 ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY" not in env)
    check("清掉 CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN" not in env)
    check("PATH 保留", env.get("PATH") == "/bin")

    # 模型名解析：带端点前缀、带 @努力程度 都能过
    spec = config.parse_model("cli:claude/bailian:deepseek-v4-pro")
    check("parse_model 认带端点的写法", (spec.channel, spec.provider, spec.model) ==
          ("cli", "claude", "bailian:deepseek-v4-pro"), str(spec))
    spec = config.parse_model("cli:claude/bailian:deepseek-v4-pro@high")
    name, effort = config.split_effort(spec.model)
    check("split_effort 拆出端点模型和强度", (name, effort) == ("bailian:deepseek-v4-pro", "high"), (name, effort))

    # 纯问答路径：_run_local 收到换好端点的 env（用假 claude 记下环境）
    tmp = Path(tempfile.mkdtemp(prefix="ep_test_"))
    fake = tmp / "claude"
    fake.write_text("#!/bin/sh\n"
                    f"env > {tmp}/env.txt\n"
                    "echo '{\"result\":\"ok\",\"is_error\":false}'\n", encoding="utf-8")
    fake.chmod(0o755)
    os.environ["CBATCH_CLAUDE"] = str(fake)
    os.environ["ANTHROPIC_API_KEY"] = "must-not-leak"
    try:
        out = llm_router.ClaudeCLIClient().complete("hi", "sys", "bailian:deepseek-v4.1-flash")
        seen = dict(line.split("=", 1) for line in (tmp / "env.txt").read_text().splitlines() if "=" in line)
        check("纯问答返回结果", out == "ok", out)
        check("纯问答子进程走端点", seen.get("ANTHROPIC_BASE_URL") == base and
              seen.get("ANTHROPIC_MODEL") == "deepseek-v4.1-flash")
        check("纯问答子进程没有 API key", "ANTHROPIC_API_KEY" not in seen)
        # 不带端点：照旧，不设 BASE_URL
        llm_router.ClaudeCLIClient().complete("hi", "sys", "sonnet")
        seen = dict(line.split("=", 1) for line in (tmp / "env.txt").read_text().splitlines() if "=" in line)
        check("普通模型不设 BASE_URL", "ANTHROPIC_BASE_URL" not in seen)
    finally:
        os.environ.pop("CBATCH_CLAUDE", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        shutil.rmtree(tmp, ignore_errors=True)

    # 角色卡：DeepSeek 两张卡能加载
    from verbs.workflow import _agents

    class Eng:
        workdir = ROOT / "workflow_demo"

        def expand(self, s):
            return s.replace("{project}", "_ep_card_check")

    for card, model in (("ENGINEER_DS", "cli:claude/bailian:deepseek-v4-pro"),
                        ("ENGINEER_DS_LITE", "cli:claude/bailian:deepseek-v4.1-flash")):
        try:
            p = _agents.load_agent(Eng(), card)
            check(f"{card} 能加载", p["model"] == model and p["agentic"] is not None, p["model"])
        except Exception as e:  # noqa: BLE001
            check(f"{card} 能加载", False, str(e))
    shutil.rmtree(ROOT / "workflow_demo/work/_ep_card_check", ignore_errors=True)
    # 探针、审查的 MCP 服务：继承了换端点的环境也要删干净，否则它起的 claude 带空 key 打端点报 401
    import subprocess
    code = ("import os, sys; sys.path.insert(0, 'tools'); import gsb_tools_mcp; "
            "print(','.join(k for k in ('ANTHROPIC_BASE_URL','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_MODEL',"
            "'ANTHROPIC_DEFAULT_SONNET_MODEL','ANTHROPIC_DEFAULT_HAIKU_MODEL') if k in os.environ) or 'clean')")
    child = dict(os.environ)
    claude_endpoint("bailian:deepseek-v4-pro", child)
    out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=child, capture_output=True,
                         text=True, timeout=60)
    check("gsb_tools_mcp 删掉端点变量和 key", out.stdout.strip().splitlines()[-1:] == ["clean"],
          out.stdout[-200:] + out.stderr[-300:])
    fmt = json.loads((ROOT / "workflow_demo/formats/cost_assignment.json").read_text(encoding="utf-8"))
    enum = fmt["properties"]["tasks"]["items"]["properties"]["agent"]["enum"]
    check("分配格式里有 DeepSeek 卡", {"ENGINEER_DS", "ENGINEER_DS_LITE"} <= set(enum))
finally:
    os.environ.pop("DASHSCOPE_API_KEY", None)
    if saved is not None:
        os.environ["DASHSCOPE_API_KEY"] = saved

print(f"\n通过 {0 if FAILS else 'all'}；失败 {len(FAILS)}" if FAILS else "\n全部通过")
sys.exit(1 if FAILS else 0)
