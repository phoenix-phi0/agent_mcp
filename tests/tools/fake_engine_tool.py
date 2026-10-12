#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试用假 codex / grok / opencode / claude CLI（v2 按步骤指定模型的引擎）。不调真模型。
由测试里的包装脚本调用：`fake_engine_tool.py <引擎名> <真实 argv…>`。
FAKE_ENGINES = json 文件 {"codex": [attempt, …], "grok": […], "opencode": […], "claude": […]}；每次被调用取该引擎的下一个 attempt（计数放在
FAKE_ENGINES.<引擎>.n，超过就重复最后一个）。attempt：{"text": "回复", "mode": …, "call": "<dsl 代码>"}，mode：
  ok（缺省）正常回复 / silent 一个事件都不出（挂着）/ idle 先出一点再挂着 / invoke 回复里写 <invoke / big 回复 25000 字
  rc 退出码 3 + stderr / tool 出一个工具 / 命令事件。
  （只对 grok，read 规划用）reads 先发 at["reads"] = [[工具名, 参数, 返回字数], …] 这些工具调用（带返回内容）再回复 / write 发一个 write 工具调用后挂着。
call（只对带 mcp_servers.dsl 的 codex）：真的拉起那个 MCP 调一次 dsl 工具，再回复。
FAKE_REC：每次被调用记 {"engine", "argv", "stdin"} 一行。"""
import json
import os
import subprocess
import sys
import time

name, args = sys.argv[1], sys.argv[2:]
stdin_text = "" if name == "grok" else sys.stdin.read()
if name == "grok" and "-p" in args:
    stdin_text = args[args.index("-p") + 1]
if os.environ.get("FAKE_REC"):
    with open(os.environ["FAKE_REC"], "a", encoding="utf-8") as f:
        f.write(json.dumps({"engine": name, "argv": args, "stdin": stdin_text, "cwd": os.getcwd()}, ensure_ascii=False) + "\n")
path = os.environ["FAKE_ENGINES"]
atts = json.load(open(path, encoding="utf-8")).get(name) or [{"text": "（假引擎没有配置回复）"}]
cnt = path + f".{name}.n"
try:
    n = int(open(cnt).read())
except (OSError, ValueError):
    n = 0
open(cnt, "w").write(str(n + 1))
at = atts[min(n, len(atts) - 1)]
mode, text = at.get("mode", "ok"), at.get("text", "")
if mode == "invoke":
    text = "先看看 <invoke name=x>" + text
elif mode == "big":
    text = "x" * 25000


def out(o):
    print(json.dumps(o, ensure_ascii=False), flush=True)


if mode == "silent":
    time.sleep(60)
    sys.exit(0)
if mode == "rc":
    print("boom: 假引擎故意失败", file=sys.stderr)
    sys.exit(3)
now = int(time.time() * 1000)
if name == "codex":
    out({"type": "thread.started", "thread_id": "t1"})
    if mode == "tool":
        out({"type": "item.completed", "item": {"type": "command_execution", "command": "ls"}})
        time.sleep(30)
    arg = " ".join(args)
    if at.get("call") and "mcp_servers.dsl.command" in arg:
        cmd = json.loads(args[[i for i, a in enumerate(args) if a.startswith("mcp_servers.dsl.command=")][0]].split("=", 1)[1])
        margs = json.loads(args[[i for i, a in enumerate(args) if a.startswith("mcp_servers.dsl.args=")][0]].split("=", 1)[1])
        srv = subprocess.Popen([cmd, *margs], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")

        def rpc(i, method, params=None):
            srv.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params or {}}) + "\n")
            srv.stdin.flush()
            return json.loads(srv.stdout.readline())
        rpc(1, "initialize", {"protocolVersion": "2025-06-18"})
        srv.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        srv.stdin.flush()
        rpc(2, "tools/list")
        out({"type": "item.started", "item": {"type": "mcp_tool_call", "server": "dsl", "tool": "dsl"}})
        rpc(3, "tools/call", {"name": "dsl", "arguments": {"code": at["call"]}})
        out({"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "dsl", "tool": "dsl"}})
        srv.stdin.close()
    if mode == "idle":
        out({"type": "item.started", "item": {"type": "reasoning"}})
        time.sleep(30)
    out({"type": "item.completed", "item": {"type": "agent_message", "text": text}})
    out({"type": "turn.completed", "usage": {"input_tokens": 11, "output_tokens": 7, "cached_input_tokens": 3, "reasoning_output_tokens": 2}})
elif name == "grok":
    out({"type": "available_commands", "data": []})
    if mode == "tool":
        out({"type": "tool_call", "data": {"name": "read_file"}})
        time.sleep(30)
    if mode == "idle":
        out({"type": "text", "data": "部分"})
        time.sleep(30)
    if mode == "write":
        out({"type": "tool_call", "toolName": "write", "toolCallId": "w1", "rawInput": {"path": "x.txt"}})
        time.sleep(30)
    for k, (tn, tin, tn_chars) in enumerate(at.get("reads") or [], 1):
        out({"type": "text", "data": "我先看看。"})
        out({"type": "tool_call", "toolName": tn, "toolCallId": f"r{k}", "rawInput": tin})
        out({"type": "tool_call_update", "toolCallId": f"r{k}", "rawOutput": {"Content": {"content": "y" * tn_chars}}})
    for i in range(0, len(text), 200):
        out({"type": "text", "data": text[i:i + 200]})
    out({"type": "end", "stopReason": "end_turn", "total_cost_usd": 0.003, "usage": {"input_tokens": 9, "output_tokens": 5}})
elif name == "opencode":
    out({"type": "step_start", "timestamp": now, "sessionID": "s1", "part": {"type": "step-start"}})
    if mode == "tool":
        out({"type": "tool_use", "timestamp": now, "part": {"type": "tool", "tool": "bash"}})
        time.sleep(30)
    if mode == "idle":
        out({"type": "text", "timestamp": now, "part": {"type": "text", "text": "部分", "time": {"start": now, "end": now}}})
        time.sleep(30)
    out({"type": "text", "timestamp": now, "part": {"type": "text", "text": text, "time": {"start": now, "end": now + 5}}})
    out({"type": "step_finish", "timestamp": now, "part": {"type": "step-finish", "cost": 0.002, "tokens": {"input": 8, "output": 4, "reasoning": 1,
                                                                                                          "total": 13}}})
else:       # claude：stream-json 单轮
    out({"type": "system", "subtype": "init"})
    if mode == "idle":
        out({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "部分"}}})
        time.sleep(30)
    out({"type": "stream_event", "event": {"type": "message_start", "message": {"usage": {}}}})
    for i in range(0, len(text), 200):
        out({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text[i:i + 200]}}})
    out({"type": "assistant", "message": {"id": "m1", "content": [{"type": "text", "text": text}]}})
    out({"type": "result", "subtype": "success", "is_error": False, "result": text, "num_turns": 1, "total_cost_usd": 0.01,
         "usage": {"input_tokens": 5, "output_tokens": 20}})
