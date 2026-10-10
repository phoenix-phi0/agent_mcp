#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试用假 claude CLI（tool 模式）：按 FAKE_STEPS 文件里的脚本演一遍多轮对话，真的去拉起 --mcp-config 里的 MCP 服务并 tools/call，
输出 stream-json。FAKE_STEPS = {"attempts": [[step, ...], ...]}；每次被调用取下一个 attempt（计数放在 FAKE_STEPS.n）。
step：{"call": "<dsl 代码>"} 一轮工具调用 / {"text": "…"} 一轮文字（最后一轮 = 最终回复）/ {"sleep": 秒}。
轮数超过 --max-turns → 输出 error_max_turns 的 result（rc=1）。不调真模型。"""
import json
import subprocess
import sys
import time

args = sys.argv[1:]
opt = lambda n, d=None: args[args.index(n) + 1] if n in args and args.index(n) + 1 < len(args) else d  # noqa: E731
sys.stdin.read()
path = __import__("os").environ["FAKE_STEPS"]
cfg = json.load(open(path, encoding="utf-8"))
n = cfg.get("n", 0)
cfg["n"] = n + 1
json.dump(cfg, open(path, "w", encoding="utf-8"), ensure_ascii=False)
steps = cfg["attempts"][min(n, len(cfg["attempts"]) - 1)]
max_turns = int(opt("--max-turns", "1"))
srv = None
if opt("--mcp-config"):
    mc = json.load(open(opt("--mcp-config"), encoding="utf-8"))["mcpServers"]["dsl"]
    srv = subprocess.Popen([mc["command"], *mc["args"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")


def rpc(i, method, params=None):
    srv.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params or {}}) + "\n")
    srv.stdin.flush()
    return json.loads(srv.stdout.readline())


def out(o):
    print(json.dumps(o, ensure_ascii=False), flush=True)


out({"type": "system", "subtype": "init", "tools": ["mcp__dsl__dsl"]})
if srv:
    rpc(1, "initialize", {"protocolVersion": "2025-06-18"})
    srv.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    srv.stdin.flush()
    rpc(2, "tools/list")
turns, calls, last_text, rid = 0, 0, "", 10
for st in steps:
    if "sleep" in st:
        time.sleep(st["sleep"])
        continue
    if turns >= max_turns:
        out({"type": "result", "subtype": "error_max_turns", "is_error": True, "num_turns": turns + 1, "total_cost_usd": 0.01,
             "usage": {"cache_read_input_tokens": 100}, "errors": ["Reached maximum number of turns"]})
        sys.exit(1)
    turns += 1
    out({"type": "stream_event", "event": {"type": "message_start", "message": {"usage": {}}}})
    if "call" in st:
        calls += 1
        rid += 1
        out({"type": "assistant", "message": {"id": f"m{turns}", "content": [{"type": "tool_use", "id": f"t{turns}", "name": "mcp__dsl__dsl",
                                                                               "input": {"code": st["call"]}}]}})
        r = rpc(rid, "tools/call", {"name": "dsl", "arguments": {"code": st["call"]}})
        out({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{turns}",
                                                       "content": r["result"]["content"]}]}})
    else:
        text = st["text"]
        for i in range(0, len(text), 40):
            out({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text[i:i + 40]}}})
            time.sleep(0.01)
        out({"type": "assistant", "message": {"id": f"m{turns}", "content": [{"type": "text", "text": text}]}})
        last_text = text
if srv:
    srv.stdin.close()
out({"type": "result", "subtype": "success", "is_error": False, "result": last_text, "num_turns": turns, "total_cost_usd": 0.02,
     "usage": {"input_tokens": 5, "output_tokens": 20, "cache_read_input_tokens": 1000 * turns, "cache_creation_input_tokens": 10}})
