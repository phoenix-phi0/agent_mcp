"""角色卡走 Claude Platform 托管 agent（model 写 platform:<模型 ID>）。

模型在 Anthropic 那边推理，工具调用（bash、读写文件）由阿里云上的自托管 worker（ali-platform-worker
服务）在沙箱里执行：只看得见 work/<项目>，读不到 /root 下的密钥和各家登录信息。

真正调 API 的是 tools/platform_runner.py，用独立的 Python 环境（/opt/platform_venv，装了 anthropic SDK）
在子进程里跑：引擎进程不加载 SDK，也不碰 API 密钥。这里只把请求交给它，拿回最后一条回复。
"""
import json
import os
import subprocess
from pathlib import Path

RUNNER = os.environ.get("WF_PLATFORM_RUNNER") or str(Path(__file__).with_name("platform_runner.py"))
PYTHON = os.environ.get("WF_PLATFORM_PYTHON", "/opt/platform_venv/bin/python")


RETRY_NOTE = ("\n\n【重做说明】上一次你没有打开代码和测试文件就判了「通过」，那次结论作废。"
              "参考文本里的实现记录只是工程师的说法，不是证据。这次每一条验收都要自己用 grep / 读文件看到"
              "实现代码和测试断言，evidence 写「文件:行」并引用你看到的内容；没亲眼看到的放进 not_verified。")


def _decide(text):
    try:
        return json.loads(text).get("decide")
    except (ValueError, AttributeError):
        return None


def call(prompt, system, model, agentic, card):
    """返回 agent 最后一条回复的文本；用量写进 llm_router.LAST_USAGE，同 claude_agentic。

    agentic.min_reads：判「通过」时至少要有这么多次读代码的工具调用（见 platform_runner 的 reads），
    不够就当这次没做验收，带着重做说明再跑一次；还不够就报错。只跑测试、照抄上下文里的实现记录就判通过，
    A/B 里实际出现过。
    """
    need = agentic.get("min_reads") or 0
    text, res = _once(prompt, system, model, agentic, card)
    if need and _decide(text) == "通过" and (res.get("usage") or {}).get("reads", 0) < need:
        first = res.get("usage", {}).get("reads", 0)
        text, res = _once(prompt + RETRY_NOTE, system, model, agentic, card)
        reads = (res.get("usage") or {}).get("reads", 0)
        from tools import llm_router
        (llm_router.LAST_USAGE.get("value") or {})["retried"] = {"reason": "读代码太少", "first_reads": first}
        if _decide(text) == "通过" and reads < need:
            raise RuntimeError(f"platform：判了「通过」但两次都几乎没读代码（读代码 {first}、{reads} 次，"
                               f"卡上要求至少 {need} 次），结论不可信")
    return text


def _once(prompt, system, model, agentic, card):
    from tools import llm_router
    spec = model[len("platform:"):]
    model_id, _, effort = spec.partition("@")
    req = {"card": card, "model": model_id, "effort": effort or None, "system": system, "prompt": prompt,
           "project": agentic["project"], "timeout": agentic.get("timeout", 600)}
    try:
        out = subprocess.run([PYTHON, RUNNER], input=json.dumps(req, ensure_ascii=False),
                             capture_output=True, text=True, timeout=req["timeout"] + 120)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"platform 调用超过 {req['timeout'] + 120} 秒没有结束")
    try:
        res = json.loads(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise RuntimeError(f"platform 运行器没有返回结果（退出码 {out.returncode}）：{out.stderr[-800:]}")
    if res.get("usage") is not None:
        usage = res.get("usage") or {}
        value = {"backend": "platform", "session": res.get("session"),
                 "seconds": res.get("seconds"), "tool_calls": res.get("tool_calls"), **usage}
        # seconds 是从发出请求到拿回结果的总时间；平台的 active_seconds 只算模型推理，
        # 差值是 worker 上执行工具（跑测试最占时间）、排队和拉起沙箱的时间
        if isinstance(usage.get("active_seconds"), (int, float)) and isinstance(res.get("seconds"), (int, float)):
            value["non_model_seconds"] = round(res["seconds"] - usage["active_seconds"], 1)
        llm_router.LAST_USAGE["value"] = value
    if res.get("error"):
        raise RuntimeError(f"platform：{res['error']}")
    return res.get("text", ""), res
