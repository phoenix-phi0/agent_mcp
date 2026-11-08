# -*- coding: utf-8 -*-
"""编排节点的「提交」工具：一个只有 submit 一个工具的 stdio MCP 服务。

编排器调 claude / goose 时挂上它（见 tools/wf_submit.py）。submit 的参数格式就是这一步
的格式（JSON Schema），模型只能通过它交结果：

- 格式对：结果原子写进 WF_OUT，回「已提交」。编排器看到 WF_OUT 出现就结束那个进程，
  不等模型再说话。
- 格式不对：把 jsonschema 报的每处错误回给模型（isError），让它改了再交；错误也记进 WF_LOG。
  交错 WF_MAX_TRIES 次后不再接受，回「次数用完」，编排器判这一步失败。

环境变量：WF_SCHEMA（格式文件路径）、WF_OUT（结果文件）、WF_LOG（错误记录，一行一个 JSON）、
WF_MAX_TRIES（默认 3）。协议：每行一条 JSON-RPC 消息（MCP stdio）。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.wf_submit import validate  # noqa: E402

SCHEMA = json.loads(Path(os.environ["WF_SCHEMA"]).read_text(encoding="utf-8"))
OUT = Path(os.environ["WF_OUT"])
LOG = Path(os.environ.get("WF_LOG") or str(OUT) + ".log")
MAX_TRIES = int(os.environ.get("WF_MAX_TRIES") or 3)
TRIES = [0]

TOOL = {
    "name": "submit",
    "description": ("提交这一步的结果。结果只能通过这个工具交，参数必须符合格式；"
                    "格式不对会返回具体错误，改了再交。提交成功后任务就结束了，不要再输出别的。"),
    # 有的模型接口不收顶层的 if/then/allOf 之类（工具参数要求是普通对象 schema）：
    # 声明给模型的去掉这些，校验仍按完整格式来，条件规则不满足时照样回错误
    "inputSchema": {k: v for k, v in SCHEMA.items()
                    if k not in ("if", "then", "else", "allOf", "anyOf", "oneOf", "not")},
}


def _send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _log(entry):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _text(mid, text, error=False):
    _send({"jsonrpc": "2.0", "id": mid,
           "result": {"content": [{"type": "text", "text": text}], "isError": error}})


def _call(mid, params):
    if params.get("name") != "submit":
        _text(mid, f"没有工具 {params.get('name')}，只有 submit", True)
        return
    if OUT.exists():
        _text(mid, "已经提交过了，任务结束。")
        return
    if TRIES[0] >= MAX_TRIES:
        _text(mid, f"交错 {MAX_TRIES} 次，不再接受提交。", True)
        return
    args = params.get("arguments")
    errors = validate(SCHEMA, args)
    if errors:
        TRIES[0] += 1
        _log({"try": TRIES[0], "errors": errors, "arguments": args})
        left = MAX_TRIES - TRIES[0]
        _text(mid, "格式不对，没有提交：\n- " + "\n- ".join(errors)
              + (f"\n改正后再调用 submit（还能再交 {left} 次）。" if left else "\n次数用完，这一步失败。"), True)
        return
    tmp = OUT.with_name(OUT.name + ".tmp")
    tmp.write_text(json.dumps(args, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, OUT)
    _text(mid, "已提交，任务结束。不要再输出任何内容。")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            _send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if mid is None:          # 通知（notifications/initialized 等）不回
            continue
        if method == "initialize":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": params.get("protocolVersion") or "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "wf_submit", "version": "1"}}})
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [TOOL]}})
        elif method == "tools/call":
            try:
                _call(mid, params)
            except Exception as e:      # 工具自己出错也回给模型，不让服务挂掉
                _text(mid, f"提交工具出错：{type(e).__name__}: {e}", True)
        else:
            _send({"jsonrpc": "2.0", "id": mid,
                   "error": {"code": -32601, "message": f"不支持 {method}"}})


if __name__ == "__main__":
    main()
