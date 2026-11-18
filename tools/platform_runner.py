"""platform_agent.py 的子进程：用 anthropic SDK 跑一次托管 agent 会话，结果以一行 JSON 打到 stdout。

由 /opt/platform_venv/bin/python 运行（装了 anthropic SDK），引擎进程不加载 SDK。
stdin：{card, model, effort, system, prompt, project, timeout}
stdout 最后一行：{text, session, seconds, tool_calls, usage} 或 {error, ...}

- API 密钥从 /root/.config/agent_mcp/platform_api_key 读，显式传给 SDK，不放进环境变量
  （放进 ANTHROPIC_API_KEY 会让本机的 claude -p 全部改成按 API 计费）。
- 同一张卡（名字、模型、effort、系统提示都相同）只建一次 agent，ID 记在 /var/lib/wfplat/agents.json。
- 会话该在哪个项目目录执行，登记在 /var/lib/wfplat/sessions/<会话 ID>，worker 的 on_work.sh 照它进目录。
- 会话每发一次工具调用都会以 requires_action 停一下等结果，只有 end_turn 才算做完。
"""
import fcntl
import hashlib
import json
import re
import sys
import time

CFG = "/root/.config/agent_mcp"
STATE = "/var/lib/wfplat"
_PROJECT = re.compile(r"[A-Za-z0-9_-]+")
_READ_TOOLS = {"read", "grep", "glob"}
# bash 一条命令常把装依赖、跑测试、看文件拼在一起（实测：pip install; pytest; cat -n a.py b.py），
# 所以按 ; && || 换行切成几段，每段管道的第一个命令是这些的，算一次读代码
_READ_CMDS = {"cat", "sed", "grep", "rg", "head", "tail", "nl", "awk", "less", "more", "egrep"}
_SEG = re.compile(r"\s*(?:;|&&|\|\||\n)\s*")


def _bash_reads(cmd):
    n = 0
    for seg in _SEG.split(cmd):
        words = seg.split("|")[0].split()
        while words and (words[0] in ("cd", "sudo", "time") or "=" in words[0]):
            words = [] if words[0] == "cd" else words[1:]
        if words and words[0].rsplit("/", 1)[-1] in _READ_CMDS:
            n += 1
    return n


def _out(**kw):
    print(json.dumps(kw, ensure_ascii=False), flush=True)


def _agent_id(client, req):
    key = hashlib.sha256(json.dumps([req["card"], req["model"], req.get("effort"), req["system"]],
                                    ensure_ascii=False).encode()).hexdigest()[:16]
    path = f"{STATE}/agents.json"
    with open(f"{STATE}/agents.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            known = json.load(open(path))
        except (OSError, ValueError):
            known = {}
        if key in known:
            return known[key]
        tools = [{"type": "agent_toolset_20260401",
                  "configs": [{"name": "web_search", "enabled": False}, {"name": "web_fetch", "enabled": False}]}]
        import anthropic
        try:
            model = {"id": req["model"], "effort": req["effort"]} if req.get("effort") else req["model"]
            agent = client.beta.agents.create(name=f"wf-{req['card']}-{key[:8]}", model=model,
                                              system=req["system"], tools=tools)
        except anthropic.BadRequestError:
            if not req.get("effort"):
                raise
            # 不收 effort 的写法：去掉 effort 再建，用模型默认的思考强度
            agent = client.beta.agents.create(name=f"wf-{req['card']}-{key[:8]}", model=req["model"],
                                              system=req["system"], tools=tools)
        known[key] = agent.id
        with open(path + ".tmp", "w") as f:
            json.dump(known, f)
        import os
        os.replace(path + ".tmp", path)
        return agent.id


def _usage(ev):
    """session.usage 事件里的 usage（累计值）：token 数、缓存、平台报的标价费用。"""
    u = getattr(ev, "usage", None)
    try:
        data = u.model_dump()
    except AttributeError:
        return {}
    out = {k: data.get(k) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "active_seconds")
           if data.get(k) is not None}
    cc = data.get("cache_creation") or {}
    out["cache_creation_input_tokens"] = sum(v for v in cc.values() if isinstance(v, (int, float)))
    if data.get("list_cost"):
        out["list_cost"] = data["list_cost"]
    return out


def main():
    req = json.load(sys.stdin)
    if not _PROJECT.fullmatch(req.get("project", "")):
        return _out(error=f"项目名不合法：{req.get('project')!r}")
    import anthropic
    client = anthropic.Anthropic(api_key=open(f"{CFG}/platform_api_key").read().strip())
    env_id = dict(l.split("=", 1) for l in open(f"{CFG}/platform_env").read().splitlines()
                  if "=" in l)["ANTHROPIC_ENVIRONMENT_ID"]
    agent_id = _agent_id(client, req)
    session = client.beta.sessions.create(agent=agent_id, environment_id=env_id, title=f"{req['card']} @ {req['project']}")
    with open(f"{STATE}/sessions/{session.id}", "w") as f:
        f.write(req["project"] + "\n")
    t0, deadline = time.time(), time.time() + int(req.get("timeout") or 600)
    texts, tools, names, usage, stop, reads = [], 0, {}, {}, None, 0
    with client.beta.sessions.events.stream(session.id) as stream:
        client.beta.sessions.events.send(session.id, events=[
            {"type": "user.message", "content": [{"type": "text", "text": req["prompt"]}]}])
        for ev in stream:
            if ev.type == "agent.message":
                texts.append("".join(b.text for b in ev.content if getattr(b, "type", "") == "text"))
            elif ev.type == "agent.tool_use":
                tools += 1
                name = getattr(ev, "name", "?")
                names[name] = names.get(name, 0) + 1
                inp = getattr(ev, "input", None) or {}
                if not isinstance(inp, dict):
                    inp = getattr(inp, "model_dump", lambda: {})()
                cmd = str(inp.get("command", "")) if name == "bash" else ""
                reads += 1 if name in _READ_TOOLS else _bash_reads(cmd)
            elif ev.type == "session.usage":
                usage = _usage(ev) or usage
            elif ev.type == "session.status_idle":
                stop = getattr(getattr(ev, "stop_reason", None), "type", None)
                if stop != "requires_action":
                    break
            elif ev.type == "session.error":
                stop = "error"
                texts.append(f"[会话出错] {getattr(ev, 'error', '')}")
            if time.time() > deadline:
                stop = "timeout"
                break
    usage["tools"] = names   # 各工具调了几次：验收不读代码只跑测试，这里一眼能看出来
    usage["reads"] = reads   # 读代码的次数：read/grep/glob 各算一次，bash 里每段 cat/sed/grep… 算一次
    res = dict(session=session.id, seconds=round(time.time() - t0, 1), tool_calls=tools, usage=usage, stop=stop)
    if stop != "end_turn":
        return _out(error=f"会话没有正常结束（{stop}）", text=texts[-1] if texts else "", **res)
    _out(text=texts[-1] if texts else "", **res)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 让引擎拿到原因，而不是一段看不懂的 traceback
        _out(error=f"{type(e).__name__}: {e}")
