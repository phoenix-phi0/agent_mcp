import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""角色卡走 Claude Platform（model: platform:<模型>）：卡的校验和调用链路。离线，不连 API。

- 必须写 agentic.cwd，而且只能是 work/<项目>；不写 allowed_tools、mcp_tools、sandbox；
- effort 可以写，模型名不对就报错；外部换模型时也认 platform:；
- 调用时把提示词、系统提示、项目名交给运行器子进程（这里换成桩脚本），拿回 JSON、记下用量；
- 运行器报错要变成清楚的 DSLError。
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from tools.dsl import DSLEngine, DSLError
from verbs.workflow import _agents
from tools import workflow_ctl

ROOT = Path(__file__).resolve().parents[2]

STUB = r'''
import json, sys
req = json.load(sys.stdin)
open(sys.argv[0] + ".req.json", "w").write(json.dumps(req, ensure_ascii=False))
mode = open(sys.argv[0] + ".mode").read().strip()
if mode == "ok":
    print("worker 日志之类的杂项")
    print(json.dumps({"text": json.dumps({"decide": "通过", "summary": "好"}), "session": "sesn_x",
                      "seconds": 3.5, "tool_calls": 4, "usage": {"input_tokens": 100}}))
elif mode in ("lazy", "lazy2"):
    redo = "重做说明" in req["prompt"]
    reads = 5 if (mode == "lazy" and redo) else 0
    print(json.dumps({"text": json.dumps({"decide": "通过", "summary": "redo" if redo else "first"}),
                      "session": "sesn_l", "seconds": 40.0, "tool_calls": 1 + reads,
                      "usage": {"reads": reads, "active_seconds": 12.5, "tools": {"bash": 1 + reads}}}))
elif mode == "error":
    print(json.dumps({"error": "会话没有正常结束（timeout）", "session": "sesn_y"}))
else:
    print("Traceback: 坏了", file=sys.stderr)
'''


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


class Client:
    offline = False

    def chat_messages(self, *a, **k):
        raise AssertionError("platform 卡不该走 client")


def card(directory, name, data, soul="你是测试卡。"):
    folder = Path(directory, "agents", name)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SOUL.md").write_text(soul, encoding="utf-8")
    (folder / "agent.json").write_text(json.dumps(data), encoding="utf-8")


def engine(directory):
    e = DSLEngine(client=Client(), workdir=directory, verbose=False, verbs_root=ROOT / "verbs")
    e.vars["project"] = "lib"
    return e


def raises(fn, pattern, msg):
    with unittest.TestCase().assertRaisesRegex(DSLError, pattern):
        fn()
    print('  ✓', msg)


def test_card_rules():
    with tempfile.TemporaryDirectory() as d:
        e = engine(d)
        ok = {"model": "platform:claude-sonnet-5-5", "effort": "medium", "agentic": {"cwd": "work/{project}", "timeout": 600}}
        card(d, "QA_P", ok)
        p = _agents.load_agent(e, "QA_P")
        check(p["model"] == "platform:claude-sonnet-5-5@medium" and p["agentic"]["project"] == "lib",
              "合法的卡：effort 拼进模型名，项目名取自 cwd")
        check(_agents._uses_submit(e, p, ("x", {})) is False, "platform 不用 submit 工具，按 JSON Schema 回")
        card(d, "NO_CWD", {"model": "platform:claude-sonnet-5-5"})
        raises(lambda: _agents.load_agent(e, "NO_CWD"), "要写 agentic.cwd", "不写 agentic：报错")
        card(d, "BAD_CWD", {"model": "platform:claude-sonnet-5-5", "agentic": {"cwd": "work"}})
        raises(lambda: _agents.load_agent(e, "BAD_CWD"), "必须是 work/<项目>", "cwd 不是 work/<项目>：报错")
        card(d, "TOOLS", {"model": "platform:claude-sonnet-5-5",
                          "agentic": {"cwd": "work/{project}", "allowed_tools": ["Read"]}})
        raises(lambda: _agents.load_agent(e, "TOOLS"), "沙箱管", "写了 allowed_tools：报错（权限由沙箱管）")
        card(d, "BAD_MODEL", {"model": "platform:gpt-6", "agentic": {"cwd": "work/{project}"}})
        raises(lambda: _agents.load_agent(e, "BAD_MODEL"), "模型配置无效", "不是 claude 模型：报错")
        check(workflow_ctl._check_model("platform:claude-haiku-5-5") == "platform:claude-haiku-5-5",
              "外部换模型也认 platform:")


def test_call():
    with tempfile.TemporaryDirectory() as d:
        stub = Path(d, "stub.py")
        stub.write_text(STUB, encoding="utf-8")
        os.environ["WF_PLATFORM_PYTHON"] = _sys.executable
        os.environ["WF_PLATFORM_RUNNER"] = str(stub)
        import importlib
        from tools import platform_agent
        importlib.reload(platform_agent)
        e = engine(d)
        card(d, "QA_P", {"model": "platform:claude-sonnet-5-5", "effort": "medium",
                         "agentic": {"cwd": "work/{project}", "timeout": 600}}, soul="你是 QA。")
        fmt = ("verdict", {"type": "object", "required": ["decide"], "properties": {"decide": {"type": "string"}}})
        Path(str(stub) + ".mode").write_text("ok")
        result = _agents.call_agent(e, "QA_P", "验收 fines", context={"m": 1}, node="模块验收", fmt=fmt)
        req = json.loads(Path(str(stub) + ".req.json").read_text(encoding="utf-8"))
        check(result == {"decide": "通过", "summary": "好"}, "拿回 JSON 结果（运行器前面打的杂项不影响）")
        check(req["model"] == "claude-sonnet-5-5" and req["effort"] == "medium" and req["project"] == "lib"
              and req["system"].startswith("你是 QA。") and "JSON Schema" in req["prompt"] and "验收 fines" in req["prompt"],
              "交给运行器：模型、effort、项目名、系统提示，提示词里带格式要求")
        usage = e._wf_last_call.get("usage") or {}
        check(usage.get("backend") == "platform" and usage.get("tool_calls") == 4 and usage.get("input_tokens") == 100,
              "用量记进运行记录")
        Path(str(stub) + ".mode").write_text("error")
        raises(lambda: _agents.call_agent(e, "QA_P", "x", fmt=fmt), "会话没有正常结束", "运行器报错：变成 DSLError")
        Path(str(stub) + ".mode").write_text("crash")
        raises(lambda: _agents.call_agent(e, "QA_P", "x", fmt=fmt), "没有返回结果.*坏了", "运行器崩了：带上 stderr")
        usage = None
        # min_reads：判通过却几乎没读代码 → 带重做说明再跑一次；还不读就报错
        card(d, "QA_R", {"model": "platform:claude-sonnet-5-5",
                         "agentic": {"cwd": "work/{project}", "min_reads": 3}}, soul="你是 QA。")
        Path(str(stub) + ".mode").write_text("lazy")
        result = _agents.call_agent(e, "QA_R", "验收 fines", fmt=fmt)
        req = json.loads(Path(str(stub) + ".req.json").read_text(encoding="utf-8"))
        usage = e._wf_last_call.get("usage") or {}
        check(result.get("summary") == "redo" and "重做说明" in req["prompt"],
              "第一次只跑测试就判通过：带着重做说明重跑，用第二次的结论")
        check(usage.get("retried", {}).get("first_reads") == 0 and usage.get("reads") == 5,
              "运行记录里看得出重做过、第一次读了几次")
        check(usage.get("non_model_seconds") == 27.5, "总耗时和模型推理时间分开记（差值是执行工具、排队和起沙箱）")
        Path(str(stub) + ".mode").write_text("lazy2")
        raises(lambda: _agents.call_agent(e, "QA_R", "x", fmt=fmt), "两次都几乎没读代码", "重做还不读：报错")
        Path(str(stub) + ".mode").write_text("ok")
        check(_agents.call_agent(e, "QA_P", "x", fmt=fmt)["decide"] == "通过", "没写 min_reads 的卡不受影响")
        card(d, "CL", {"model": "cli:claude/sonnet", "agentic": {"cwd": "work/x", "allowed_tools": ["Read"],
                                                                "min_reads": 2}})
        raises(lambda: _agents.load_agent(e, "CL"), "只给 platform", "min_reads 写在非 platform 卡上：报错")
        os.environ.pop("WF_PLATFORM_PYTHON"); os.environ.pop("WF_PLATFORM_RUNNER")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            print(name)
            fn()
    print("platform 卡：全部通过")
