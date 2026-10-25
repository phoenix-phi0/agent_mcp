# -*- coding: utf-8 -*-
"""tools/gsb_tools_mcp.py：gsbatch 给 goose 挂的 stdio MCP 扩展。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_gsb_tools_mcp.py

真起一个服务器进程，按 goose 的方式走 JSON-RPC（一行一条）：initialize、tools/list、
read_files（多文件 / 行号范围 / 缺失 / 目录 / 二进制 / 截断 / glob）、multi_edit（原子成功 / 中途失败不落盘 / count 不符 / 多文件 / 超上限）、run_wait（正常 /
非零 / 超时杀进程组 / 单次阻塞上限后 still_running）、wait_pid（自己起的 / 外部进程）、
凭证变量不进命令环境。不联网、不花钱。

list / check / write_iface_template：假目录（GSB_IFACE_DIR）下列、校验、写入；校验失败不落盘；
overwrite；路径穿越 / 非法英文名拒绝。不改 iftpl 引擎。

review / review_wait 同样用假 codex：默认不出现、GSB_REVIEW=1 才有；参数校验、默认审工作区
diff、base、报告草稿、提示里有任务书路径和必查项、强制只读、开头的初步审查提示和「无出处」标记、
still_running 后 review_wait。
probe / probe_wait 用 PATH 上的假 codex（不联网）：默认不出现、GSB_PROBE=1 才有；
正常 / 失败 / 超时杀进程组 / still_running 后 probe_wait / 并行 wait=false + 一次等多个 /
超长截断 / 满载自动重试 / 参数校验；每次都带 -s read-only、默认 -m gpt-6-luna、
不带 --dangerously*，凭证变量进不了 codex。默认还给 codex 挂 gsb_read_files MCP
（GSB_TOOLS_ONLY=read_files）；GSB_PROBE_READ_FILES=0 可关。
GSB_PROBE_BACKEND=claude 时改走假 claude（经 probe_claude_run.py）：plan 模式、
strict-mcp-config、只挂 gsb_read_files、关 connectors；review 仍走 codex。
verify / verify_wait（GSB_VERIFY=1）：假 codex 交回 JSON / 非 JSON / 往被验项目写文件，
验开关、参数校验、workspace-write + 临时目录 argv、JSON 解析成功 / 失败、违规改动
（git 与非 git）、still_running + verify_wait、超时杀进程组；说明里提 verify。
GSB_TOOLS_ONLY=read_files 时 tools/list 只有 read_files。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "gsb_tools_mcp.py"
TMP = Path(tempfile.mkdtemp(prefix="gsbtools_"))
SECRET = "sk-test-SECRET-0123456789abcdef"

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"：{str(extra)[:800]}" if extra != "" else ""))


class Server:
    def __init__(self, max_block=4, **extra):
        env = dict(os.environ, GSB_MAX_BLOCK=str(max_block), GSB_LOG_DIR=str(TMP / "logs"),
                   ZAI_CODING_PLAN_API_KEY=SECRET, GH_TOKEN="ghp_fakefakefakefake",
                   MY_SECRET="x" + SECRET, HARMLESS_VAR="ok", OPENAI_API_KEY="sk-openai-" + SECRET,
                   # 模拟 Cursor 沙箱：把凭证嵌进“ innocuous ”变量值里
                   __CURSOR_SANDBOX_ENV_RESTORE=(
                       "builtin export GH_TOKEN='ghp_embedded_in_restore'; "
                       "builtin export ZHIPU_API_KEY='sk-embedded-in-restore'"
                   ))
        env.pop("GSB_PROBE", None)
        env.pop("GSB_PROBE_BACKEND", None)
        env.pop("GSB_PROBE_MODEL", None)
        env.pop("GSB_TOOLS_ONLY", None)
        env["GSB_PROBE_BACKEND"] = "codex"  # 大部分用例用假 codex；默认 claude 另测
        env.update(extra)
        env = {k: v for k, v in env.items() if v is not None}
        self.p = subprocess.Popen([sys.executable, str(SCRIPT)], cwd=str(TMP), env=env,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                  bufsize=1)
        self.n = 0
        self.got = {}
        self.cv = threading.Condition()
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for line in self.p.stdout:
            m = json.loads(line)
            with self.cv:
                self.got[m.get("id")] = m
                self.cv.notify_all()

    def send(self, obj):
        self.p.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.p.stdin.flush()

    def req(self, method, params=None, timeout=30):
        self.n += 1
        mid = self.n
        self.send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
        end = time.time() + timeout
        with self.cv:
            while mid not in self.got:
                left = end - time.time()
                if left <= 0:
                    raise TimeoutError(method)
                self.cv.wait(left)
            return self.got.pop(mid)

    def call(self, name, args, timeout=30):
        r = self.req("tools/call", {"name": name, "arguments": args}, timeout)
        if "error" in r:
            return None, r["error"]
        return r["result"]["content"][0]["text"], r["result"].get("isError")

    def close(self):
        try:
            self.p.stdin.close()
        except OSError:
            pass
        try:
            self.p.wait(5)
        except subprocess.TimeoutExpired:
            self.p.kill()


def alive(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            s = f.read()
        return s[s.rindex(")") + 2] != "Z"
    except OSError:
        return False


def field(text, k):
    m = re.search(rf"^{k}：(\S+)", text, re.M)
    return m.group(1) if m else None


FAKE_CODEX = '#!/usr/bin/env python3\n# 假 codex：记下 argv / 环境，按提示词里的关键字表演\nimport json, os, subprocess, sys, time\nargv = sys.argv[1:]\nprompt = sys.stdin.read()\nrec = os.environ["FAKE_CODEX_REC"]\nwith open(rec, "a") as f:\n    f.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "prompt": prompt,\n                        "env_keys": sorted(os.environ),\n                        "secret_seen": any("SECRET-0123" in v or v.startswith("ghp_")\n                                           for v in os.environ.values())}) + "\\n")\nout = argv[argv.index("-o") + 1]\ntask = prompt.split("任务：")[-1]\nprint("OpenAI Codex (fake)\\nuser\\n" + prompt, flush=True)\ndef done(text, tok="1,234"):\n    open(out, "w").write(text)\n    print("codex\\n" + text + "\\ntokens used\\n" + tok, flush=True)\n    sys.exit(0)\nif "你是代码审查员" in prompt:\n    if "REVIEWSLOW" in prompt:\n        time.sleep(6)\n    done("结论：有问题\\n问题清单：\\n- [阻断] calc.py:2 — 负数没处理。依据：读了文件\\n"\n         "- [应修] README 也要更新。依据：任务书\\n- [建议] calc.py:1 — 可以加类型注解\\n"\n         "必查项：\\n(a) 漏了负数要求\\n(b) 无\\n(c) 无\\n(d) 无报告草稿\\n(e) 无", "4,321")\nif "FAIL" in task:\n    print("ERROR: something broke badly", flush=True); sys.exit(2)\nif "HANG" in task:\n    c = subprocess.Popen(["sleep", "300"])\n    open(os.environ["FAKE_CODEX_REC"] + ".child", "w").write(str(c.pid))\n    time.sleep(300)\nif "CAP" in task:\n    cnt = rec + ".cap"\n    n = int(open(cnt).read()) if os.path.exists(cnt) else 0\n    open(cnt, "w").write(str(n + 1))\n    if n == 0:\n        print("ERROR: Selected model is at capacity. Please try a different model.\\ntokens used\\n100", flush=True)\n        sys.exit(1)\n    done("capacity ok")\nif "BIG" in task:\n    done("B" * 40000)\nif "\u4f60\u662f\u9a8c\u8bc1 agent" in prompt:\n    tgt = os.environ.get("FAKE_VERIFY_TARGET")\n    if tgt and "WRITE" in task:\n        open(tgt, "a").write("bad\\n")\n    for w in task.split():\n        if w.startswith("SLOW"):\n            time.sleep(float(w[4:]))\n    if "VERIFYBAD" in task:\n        done("\u8fd9\u4e0d\u662f JSON\uff1a\u624b\u5de5\u5199\u7684\u7ed3\u8bba\u3002")\n    if "ENVOKEY" in task:\n        proj = [l.split("\uff1a", 1)[1] for l in prompt.splitlines() if l.startswith("\u88ab\u9a8c\u9879\u76ee\uff1a")][0]\n        done(\'{"\u72b6\u6001": "\u6210\u529f", "\u7ed3\u679c": {"\u7ed3\u8bba": "\u901a\u8fc7", "\u73af\u5883": {"python": "\' + proj + \'/.venv/bin/python", "\u5f15\u64ce": "\' + proj + \'/gen/__init__.py \' + proj + \'/tools/__init__.py", "\u8d77\u6cd5": "make_app(real=False, login=True)"}, "\u68c0\u67e5": [{"\u9879": "smoke", "\u901a\u8fc7": true, "\u8bc1\u636e": "200"}], "\u53d1\u73b0": [], "\u8bf4\u660e": "env ok"}}\', "7,777")\n    if "ENVWRONG" in task and "ENVWRONGENG" not in task:\n        done(\'{"\u72b6\u6001": "\u6210\u529f", "\u7ed3\u679c": {"\u7ed3\u8bba": "\u4e0d\u901a\u8fc7", "\u73af\u5883": {"python": "/usr/bin/python3", "\u5f15\u64ce": "/workspace/dslagent_exp/luna_roles/code/gen/__init__.py", "\u8d77\u6cd5": "PYTHONPATH=/elsewhere python3 -m gen run"}, "\u68c0\u67e5": [{"\u9879": "smoke", "\u901a\u8fc7": false, "\u8bc1\u636e": "500"}], "\u53d1\u73b0": [], "\u8bf4\u660e": "old snapshot"}}\', "6,666")\n    if "ENVWRONGENG" in task:\n        proj = [l.split("\uff1a", 1)[1] for l in prompt.splitlines() if l.startswith("\u88ab\u9a8c\u9879\u76ee\uff1a")][0]\n        done(\'{"\u72b6\u6001": "\u6210\u529f", "\u7ed3\u679c": {"\u7ed3\u8bba": "\u4e0d\u901a\u8fc7", "\u73af\u5883": {"python": "\' + proj + \'/.venv/bin/python", "\u5f15\u64ce": "/workspace/dslagent_exp/luna_roles/code/tools/__init__.py", "\u8d77\u6cd5": "PYTHONPATH=/elsewhere .venv/bin/python -m gen run"}, "\u68c0\u67e5": [{"\u9879": "smoke", "\u901a\u8fc7": false, "\u8bc1\u636e": "500"}], "\u53d1\u73b0": [], "\u8bf4\u660e": "old engine only"}}\', "6,667")\n    done(\'{"\u72b6\u6001": "\u6210\u529f", "\u7ed3\u679c": {"\u7ed3\u8bba": "\u901a\u8fc7", "\u68c0\u67e5": [{"\u9879": "\u5168\u91cf\u56de\u5f52", "\u901a\u8fc7": true, "\u8bc1\u636e": "run.sh: 27 passed"}, {"\u9879": "auth_login \u8fd4\u56de\u952e", "\u901a\u8fc7": false, "\u8bc1\u636e": "\u7f3a ret"}], "\u53d1\u73b0": ["README \u8fc7\u671f"], "\u8bf4\u660e": "ok"}}\', "8,888")\nfor w in task.split():\n    if w.startswith("SLOW"):\n        time.sleep(float(w[4:]))\ndone("结论：" + task.strip() + "（a.txt:2）")\n'


FAKE_CLAUDE = """#!/usr/bin/env python3
# 假 claude：记下 argv / 环境，按提示词关键字表演；stdout 打一份 --output-format json
import json, os, subprocess, sys, time
argv = sys.argv[1:]
prompt = ""
if "--" in argv:
    i = argv.index("--")
    prompt = argv[i + 1] if i + 1 < len(argv) else ""
rec = os.environ["FAKE_CLAUDE_REC"]
with open(rec, "a") as f:
    f.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "prompt": prompt,
                        "env_keys": sorted(os.environ),
                        "enable_mcp": os.environ.get("ENABLE_CLAUDEAI_MCP_SERVERS"),
                        "secret_seen": any("SECRET-0123" in v or v.startswith("ghp_")
                                           for v in os.environ.values())}) + "\\n")
task = prompt.split("任务：")[-1] if "任务：" in prompt else prompt

def emit(result, tok_in=1200, is_error=False, rc=0, err=None):
    d = {"type": "result", "result": result, "is_error": is_error,
         "modelUsage": {"claude-haiku-5-5": {"inputTokens": tok_in, "outputTokens": 40,
                                            "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0}}}
    if err:
        print(err, file=sys.stderr, flush=True)
    print(json.dumps(d, ensure_ascii=False), flush=True)
    sys.exit(rc)

if "FAIL" in task:
    emit("", is_error=True, rc=1, err="ERROR: something broke badly")
if "HANG" in task:
    c = subprocess.Popen(["sleep", "300"])
    open(os.environ["FAKE_CLAUDE_REC"] + ".child", "w").write(str(c.pid))
    time.sleep(300)
if "CAP" in task:
    cnt = rec + ".cap"
    n = int(open(cnt).read()) if os.path.exists(cnt) else 0
    open(cnt, "w").write(str(n + 1))
    if n == 0:
        print("ERROR: API Error: 529 overloaded_error", file=sys.stderr, flush=True)
        emit("", is_error=True, rc=1)
    emit("capacity ok")
if "BIG" in task:
    emit("B" * 40000)
for w in task.split():
    if w.startswith("SLOW"):
        time.sleep(float(w[4:]))
emit("结论：" + task.strip() + "（a.txt:2）")
"""


def pid_of(text):
    m = re.search(r"probe_id：([\w-]+)", text)
    return m.group(1) if m else None


def recs(path):
    try:
        return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    except OSError:
        return []


def tools_only_tests():
    print("GSB_TOOLS_ONLY=read_files")
    s = Server(GSB_TOOLS_ONLY="read_files")
    try:
        init = s.req("initialize", {"protocolVersion": "2025-03-26"})
        info = init["result"]["serverInfo"]
        check(info["name"] == "gsb_read_files", "server 名变成 gsb_read_files", info)
        names = [t["name"] for t in s.req("tools/list")["result"]["tools"]]
        check(names == ["read_files"], "tools/list 只有 read_files", names)
        t, e = s.call("read_files", {"files": ["a.txt"]})
        check(not e and "line1" in t, "read_files 仍可用", t)
        r = s.req("tools/call", {"name": "multi_edit", "arguments": {"edits": []}})
        check("error" in r, "multi_edit 不可用", r)
    finally:
        s.close()
    s = Server(GSB_TOOLS_ONLY="wait_pid")
    try:
        init = s.req("initialize", {})
        instr = init["result"].get("instructions") or ""
        check("wait_pid" in instr and "run_wait" not in instr and "read_files" not in instr
              and "multi_edit" not in instr and "工具用法" in instr and "sleep" in instr,
              "子集只提暴露了的工具（GSB_TOOLS_ONLY=wait_pid 不提 run_wait/read_files）", instr)
        t, e = s.call("wait_pid", {"pid": 1})
        check("pid 不是整数" in t or "不存在" in t or e, "子集里的工具仍可用", t)
    finally:
        s.close()

    print("GSB_PROBE_READ_FILES=0 不挂 MCP")
    bindir = TMP / "bin_noread"
    bindir.mkdir(exist_ok=True)
    (bindir / "codex").write_text(FAKE_CODEX)
    (bindir / "codex").chmod(0o755)
    rec = TMP / "codex_calls_noread.jsonl"
    env = {"PATH": f"{bindir}:{os.environ.get('PATH', '')}", "FAKE_CODEX_REC": str(rec),
           "GSB_PROBE_RETRY_WAITS": "1,1", "GSB_PROBE_READ_FILES": "0"}
    s = Server(max_block=4, GSB_PROBE="1", **env)
    try:
        t, e = s.call("probe", {"instructions": "OK noread"})
        a = recs(rec)[-1]["argv"]
        check(not any("mcp_servers.gsb_read_files" in x for x in a),
              "GSB_PROBE_READ_FILES=0 时 argv 无 gsb_read_files", a)
        check("优先用 read_files" in recs(rec)[-1]["prompt"], "开场说明仍提示 read_files", recs(rec)[-1]["prompt"][:200])
    finally:
        s.close()


def probe_tests():
    bindir = TMP / "fakebin"
    bindir.mkdir(exist_ok=True)
    (bindir / "codex").write_text(FAKE_CODEX)
    (bindir / "codex").chmod(0o755)
    rec = TMP / "codex_calls.jsonl"
    env = {"PATH": f"{bindir}:{os.environ.get('PATH', '')}", "FAKE_CODEX_REC": str(rec),
           "GSB_PROBE_RETRY_WAITS": "1,1"}

    print("probe 默认不开")
    s0 = Server(**{k: v for k, v in env.items()})
    try:
        names = [t["name"] for t in s0.req("tools/list")["result"]["tools"]]
        check("probe" not in names and "probe_wait" not in names, "没 GSB_PROBE=1 时 tools/list 没有 probe", names)
        r = s0.req("tools/call", {"name": "probe", "arguments": {"instructions": "x"}})
        check("error" in r, "调 probe 报没有这个工具", r)
    finally:
        s0.close()

    s = Server(max_block=4, GSB_PROBE="1", **env)
    try:
        tools = {t["name"]: t for t in s.req("tools/list")["result"]["tools"]}
        check({"probe", "probe_wait"} <= set(tools)
              and {"read_files", "multi_edit", "run_wait", "wait_pid"} <= set(tools),
              "GSB_PROBE=1 时多出 probe / probe_wait，原来的基础工具还在", list(tools))
        sch = tools["probe"]["inputSchema"]
        check(sch["required"] == ["instructions"]
              and sch["properties"]["effort"]["enum"] == ["low", "medium", "high"]
              and "read-only" in tools["probe"]["description"], "probe 的 schema", sch)

        print("probe 正常")
        t0 = time.time()
        t, e = s.call("probe", {"instructions": "OK 看看第二行"})
        c = recs(rec)[-1]
        a = c["argv"]
        check(not e and "状态：done" in t and "结论：OK 看看第二行（a.txt:2）" in t
              and "tokens used：1,234" in t and re.search(r"用时：[\d.]+ 秒", t), "done + 最终回复全文 + tokens + 用时", t)
        check(a[0] == "exec" and a[a.index("-s") + 1] == "read-only" and a[a.index("-m") + 1] == "gpt-6-luna"
              and "model_reasoning_effort=medium" in a and a[-1] == "-"
              and not any("dangerous" in x or "bypass" in x or "full-auto" in x for x in a)
              and "workspace-write" not in a and "danger-full-access" not in a,
              "argv：exec -m gpt-6-luna -s read-only，默认 medium，stdin 读提示词，没有 --dangerously*", a)
        check(any("mcp_servers.gsb_read_files.command=" in x for x in a)
              and any("mcp_servers.gsb_read_files.args=" in x for x in a)
              and any('GSB_TOOLS_ONLY="read_files"' in x or "GSB_TOOLS_ONLY=read_files" in x for x in a),
              "默认挂 gsb_read_files MCP（仅 read_files）", a)
        check(a[a.index("-C") + 1] == str(TMP) and c["cwd"] == str(TMP), "默认工作目录是服务器 cwd", c["cwd"])
        check(c["prompt"].startswith("你是一个只读探针") and "只读" in c["prompt"] and "path:line" in c["prompt"]
              and c["prompt"].rstrip().endswith("OK 看看第二行"), "固定只读前言 + 任务", c["prompt"][:200])
        check(not c["secret_seen"] and "HOME" in c["env_keys"] and "PATH" in c["env_keys"]
              and not any(k in c["env_keys"] for k in ("GH_TOKEN", "ZAI_CODING_PLAN_API_KEY", "MY_SECRET",
                                                      "OPENAI_API_KEY"))
              and "HARMLESS_VAR" in c["env_keys"], "凭证变量进不了 codex，HOME/PATH 保留", c["env_keys"])

        sub = TMP / "sub"
        t, e = s.call("probe", {"instructions": "OK2", "effort": "HIGH", "cwd": "sub", "model": "gpt-other"})
        a = recs(rec)[-1]["argv"]
        check("状态：done" in t and "model_reasoning_effort=high" in a and a[a.index("-C") + 1] == str(sub)
              and a[a.index("-m") + 1] == "gpt-other" and a[a.index("-s") + 1] == "read-only",
              "effort / cwd（相对路径）/ model 照传，仍然 -s read-only", a)

        print("probe 失败")
        t, e = s.call("probe", {"instructions": "FAIL 一下", "effort": "low"})
        check("状态：failed（退出码 2）" in t and "something broke badly" in t and "log 末尾" in t,
              "failed + 退出码 + log 末尾", t)

        print("probe 超时：杀掉整个进程组")
        t, e = s.call("probe", {"instructions": "HANG", "timeout_secs": 2}, timeout=20)
        child = int(Path(str(rec) + ".child").read_text())
        time.sleep(0.3)
        check("状态：timeout（超过 2 秒，已杀掉进程组）" in t, "timeout 状态", t)
        check(not alive(child), "codex 起的子进程也被杀", child)

        print("still_running 后 probe_wait 接着等")
        t0 = time.time()
        t, e = s.call("probe", {"instructions": "SLOW6 慢活"}, timeout=20)
        pid = pid_of(t)
        check("状态：still_running" in t and 3.5 < time.time() - t0 < 6 and pid
              and "probe_wait" in t, "单次阻塞到上限返回 still_running + probe_id", t)
        t, e = s.call("probe_wait", {"probe_ids": [pid]}, timeout=20)
        check("状态：done" in t and "SLOW6 慢活" in t, "probe_wait 拿到结果", t)
        t, e = s.call("probe_wait", {"probe_ids": [pid]})
        check("状态：done" in t and "前面已经返回过" in t and "SLOW6 慢活" not in t, "再等一次只给简短提示", t)

        print("并行：wait=false 派三个，probe_wait 一起等")
        t0 = time.time()
        ids = []
        for i in range(3):
            t, e = s.call("probe", {"instructions": f"SLOW3 第{i}块", "wait": False})
            ids.append(pid_of(t))
            check("状态：started" in t, f"第 {i} 个立即返回 started", t)
        check(time.time() - t0 < 1.5 and len(set(ids)) == 3 and all(ids), "三个立即返回且 id 各不相同", ids)
        t, e = s.call("probe_wait", {"probe_ids": ",".join(ids) + ",nope-1"}, timeout=20)
        el = time.time() - t0
        check(t.count("状态：done") == 3 and all(f"第{i}块" in t for i in range(3)) and el < 5.5,
              f"三个都 done，总共 {el:.1f} 秒（串行要 9 秒）", t)
        check("nope-1" in t and "没有这个 id" in t, "不认识的 id 报出来", t)
        t, e = s.call("probe", {"instructions": "SLOW8 a", "wait": False})
        i1 = pid_of(t)
        t, e = s.call("probe", {"instructions": "OK b", "wait": False})
        i2 = pid_of(t)
        t, e = s.call("probe_wait", {"probe_ids": [i1, i2], "timeout_secs": 2}, timeout=20)
        check("still_running" in t and "状态：done" in t and f'probe_wait(probe_ids=["{i1}"])' in t,
              "一个完一个没完：完的给结果，没完的列出来叫再等", t)
        t, e = s.call("probe_wait", {"probe_ids": [i1]}, timeout=20)
        check("still_running" in t, "单次最多阻塞 GSB_MAX_BLOCK", t)
        t, e = s.call("probe_wait", {"probe_ids": [i1]}, timeout=20)
        check("状态：done" in t, "最后等到", t)

        print("超长截断 / 满载重试 / 参数校验")
        t, e = s.call("probe", {"instructions": "BIG"})
        check("状态：done" in t and "截断，共 40000 字" in t and ".reply.txt" in t and t.count("B") < 30100,
              "超过 30000 字截断，给全文路径", len(t))
        t, e = s.call("probe", {"instructions": "CAP"}, timeout=20)
        check("状态：done" in t and "capacity ok" in t and "自动重试了 1 次" in t
              and "tokens used：1,334（2 次运行合计）" in t, "模型满载自动重试一次后成功，tokens 两次合计", t)
        for bad, why in (({"instructions": "  "}, "空 instructions"),
                         ({"instructions": "x", "effort": "xhigh"}, "effort 不在 low/medium/high"),
                         ({"instructions": "x", "timeout_secs": 1801}, "timeout_secs 超过 1800"),
                         ({"instructions": "x", "cwd": "nope_dir"}, "cwd 不存在"),
                         ({"instructions": "x", "model": "a b;rm"}, "model 不合法")):
            n = len(recs(rec))
            t, e = s.call("probe", bad)
            check(e and "出错" in t and len(recs(rec)) == n, f"拒绝：{why}（没启动 codex）", t)
        argvs = [r["argv"] for r in recs(rec)]
        check(all(a[a.index("-s") + 1] == "read-only" for a in argvs)
              and not any("dangerous" in x for a in argvs for x in a),
              f"全部 {len(argvs)} 次调用都是 -s read-only、没有 --dangerously*")
        check(not any(r["secret_seen"] for r in recs(rec)), "全部调用都没见到凭证")

        print("stdin 关闭时杀掉还在跑的探针")
        t, e = s.call("probe", {"instructions": "HANG2 HANG", "wait": False})
        time.sleep(1)
        child = int(Path(str(rec) + ".child").read_text())
        s.close()
        time.sleep(0.5)
        check(not alive(child), "服务器退出，探针进程组被杀", child)
    finally:
        s.close()


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                           "-c", "commit.gpgsign=false", *a], check=True, capture_output=True, text=True).stdout



def probe_claude_tests():
    bindir = TMP / "fakebin_claude"
    bindir.mkdir(exist_ok=True)
    (bindir / "claude").write_text(FAKE_CLAUDE)
    (bindir / "claude").chmod(0o755)
    rec = TMP / "claude_calls.jsonl"
    env = {"PATH": f"{bindir}:{os.environ.get('PATH', '')}", "FAKE_CLAUDE_REC": str(rec),
           "GSB_PROBE_RETRY_WAITS": "1,1", "GSB_PROBE_BACKEND": "claude"}

    print("没设 GSB_PROBE_BACKEND：默认 claude")
    s = Server(max_block=4, GSB_PROBE="1", **dict(env, GSB_PROBE_BACKEND=None))
    try:
        tools = {t["name"]: t for t in s.req("tools/list")["result"]["tools"]}
        check("Claude CLI" in tools["probe"]["description"], "默认后端 claude", tools["probe"]["description"][:120])
    finally:
        s.close()

    print("Claude 后端：正常 + 参数")
    s = Server(max_block=4, GSB_PROBE="1", **env)
    try:
        tools = {t["name"]: t for t in s.req("tools/list")["result"]["tools"]}
        check("probe" in tools and "Claude CLI" in tools["probe"]["description"]
              and "claude-haiku-5-5" in tools["probe"]["description"],
              "tools/list 描述写 Claude / haiku", tools["probe"]["description"][:160])
        t, e = s.call("probe", {"instructions": "OK 看看第二行"})
        c = recs(rec)[-1]
        a = c["argv"]
        check(not e and "状态：done" in t and "结论：OK 看看第二行（a.txt:2）" in t
              and "claude" in t,
              "done + 最终回复 + 后端标记", t)
        check(a[0] == "-p" and a[a.index("--model") + 1] == "claude-haiku-5-5"
              and a[a.index("--permission-mode") + 1] == "plan"
              and a[a.index("--effort") + 1] == "medium"
              and "--strict-mcp-config" in a
              and a[a.index("--output-format") + 1] == "json"
              and a[a.index("--tools") + 1] == "Read,Glob,Grep,Bash",
              "argv：-p plan haiku strict-mcp tools", a)
        mcp = a[a.index("--mcp-config") + 1]
        settings = a[a.index("--settings") + 1]
        check(mcp.endswith("probe_claude_mcp.json") and Path(mcp).is_file()
              and settings.endswith("probe_claude_settings.json"),
              "挂了 tools/ 下的 mcp + settings", (mcp, settings))
        check(c["enable_mcp"] == "0" and not c["secret_seen"]
              and "HOME" in c["env_keys"] and "PATH" in c["env_keys"]
              and not any(k in c["env_keys"] for k in ("GH_TOKEN", "ZAI_CODING_PLAN_API_KEY",
                                                      "MY_SECRET", "OPENAI_API_KEY")),
              "ENABLE_CLAUDEAI_MCP_SERVERS=0，凭证进不了 claude", c["env_keys"][:20])
        check(c["prompt"].startswith("你是一个只读探针") and c["prompt"].rstrip().endswith("OK 看看第二行"),
              "固定只读前言 + 任务", c["prompt"][:120])

        t, e = s.call("probe", {"instructions": "OK2", "effort": "HIGH", "model": "claude-haiku-5-5"})
        a = recs(rec)[-1]["argv"]
        check(a[a.index("--effort") + 1] == "high" and a[a.index("--model") + 1] == "claude-haiku-5-5",
              "effort / model 照传", a)

        print("Claude：失败 / 超时 / 满载重试 / 并行")
        t, e = s.call("probe", {"instructions": "FAIL 一下", "effort": "low"})
        check("状态：failed" in t and "log 末尾" in t, "failed + log", t)
        t, e = s.call("probe", {"instructions": "HANG", "timeout_secs": 2}, timeout=20)
        child = int(Path(str(rec) + ".child").read_text())
        time.sleep(0.3)
        check("状态：timeout" in t and not alive(child), "timeout 杀进程组", (t, child))
        t, e = s.call("probe", {"instructions": "CAP"}, timeout=20)
        check("状态：done" in t and "capacity ok" in t and "自动重试了 1 次" in t, "满载自动重试", t)
        ids = []
        for i in range(2):
            t, e = s.call("probe", {"instructions": f"SLOW2 第{i}块", "wait": False})
            ids.append(pid_of(t))
            check("后端 claude" in t and "状态：started" in t, f"started #{i}", t)
        t, e = s.call("probe_wait", {"probe_ids": ids}, timeout=20)
        check(t.count("状态：done") == 2, "并行两个 done", t)
    finally:
        s.close()

    print("Claude 后端时 review 仍走 codex")
    (bindir / "codex").write_text(FAKE_CODEX)
    (bindir / "codex").chmod(0o755)
    crec = TMP / "codex_calls_with_claude_probe.jsonl"
    env2 = {**env, "FAKE_CODEX_REC": str(crec), "PATH": f"{bindir}:{os.environ.get('PATH', '')}"}
    repo = TMP / "repo_claude_probe"
    repo.mkdir(exist_ok=True)
    if not (repo / ".git").exists():
        git(repo, "init", "-q", "-b", "main")
        (repo / "calc.py").write_text("def f(x):\n    return x\n")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "i")
    s = Server(max_block=4, GSB_PROBE="1", GSB_REVIEW="1", **env2)
    try:
        t, e = s.call("review", {"instructions": "看一下", "cwd": str(repo)})
        check("状态：done" in t and "初步审查" in t, "review 在 claude probe 后端下仍可用", t)
        cr = recs(crec)
        check(cr and cr[-1]["argv"][0] == "exec"
              and cr[-1]["argv"][cr[-1]["argv"].index("-m") + 1] == "gpt-6-luna",
              "review 仍调 codex gpt-6-luna", cr[-1]["argv"] if cr else None)
        n_claude = len(recs(rec))
        n_codex = len(cr)
        t, e = s.call("probe", {"instructions": "OK review-isolation"})
        check(len(recs(rec)) == n_claude + 1 and len(recs(crec)) == n_codex,
              "probe 走 claude、不碰 codex", (len(recs(rec)), len(recs(crec))))
    finally:
        s.close()


def review_tests():
    bindir = TMP / "fakebin"
    rec = TMP / "codex_calls.jsonl"
    env = {"PATH": f"{bindir}:{os.environ.get('PATH', '')}", "FAKE_CODEX_REC": str(rec),
           "GSB_PROBE_RETRY_WAITS": "1,1"}
    repo = TMP / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "calc.py").write_text("def f(x):\n    return x\n")
    (repo / "README.md").write_text("readme\n")
    (repo / "task.md").write_text("把 f 改成返回 x*2；负数返回 0；不能改 README。\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    (repo / "calc.py").write_text("def f(x):\n    return x * 2\n")
    git(repo, "commit", "-q", "-am", "double")
    (repo / "calc.py").write_text("def f(x):\n    return x * 2  # wip\n")
    (repo / "staged.py").write_text("y = 1\n")
    git(repo, "add", "staged.py")
    (repo / "report.md").write_text("改了 1 个文件\n")
    plain = TMP / "plain"
    plain.mkdir()

    print("review 默认不开 / 只开 review")
    s0 = Server(GSB_PROBE="1", **env)
    try:
        names = [t["name"] for t in s0.req("tools/list")["result"]["tools"]]
        check("review" not in names and "review_wait" not in names and "probe" in names,
              "只有 GSB_PROBE=1 时没有 review", names)
    finally:
        s0.close()
    s = Server(max_block=4, GSB_REVIEW="1", **env)
    try:
        tools = {t["name"]: t for t in s.req("tools/list")["result"]["tools"]}
        check({"review", "review_wait"} <= set(tools) and "probe" not in tools,
              "GSB_REVIEW=1 时有 review / review_wait（probe 没开就没有）", list(tools))
        d = tools["review"]["description"]
        props = tools["review"]["inputSchema"]["properties"]
        check({"task_file", "instructions", "cwd", "base", "report_file", "effort", "timeout_secs", "wait"}
              <= set(props) and "初步审查" in d and "不是定论" in d and "误报" in d and "漏报" in d
              and "read-only" in d, "schema 参数齐全，描述写明初步审查、只是线索", d)
        check("不论采纳还是驳回" not in d and "重新 read_files" not in d and "命令重数" not in d
              and "存疑" not in d, "描述里没有后加的核实规则", d)

        print("review 参数校验（不启动 codex）")
        for bad, why in (({"cwd": str(repo)}, "task_file 和 instructions 都没给"),
                         ({"task_file": "nope.md", "cwd": str(repo)}, "task_file 不存在"),
                         ({"task_file": "task.md", "report_file": "nope.md", "cwd": str(repo)}, "report_file 不存在"),
                         ({"task_file": "task.md", "base": "HEAD~1..HEAD", "cwd": str(repo)}, "base 写成范围"),
                         ({"task_file": "task.md", "base": "--output=/tmp/x", "cwd": str(repo)}, "base 像选项"),
                         ({"task_file": "task.md", "base": "nosuchbranch", "cwd": str(repo)}, "base 不存在"),
                         ({"instructions": "x", "base": "HEAD", "cwd": str(plain)}, "非 git 目录给 base"),
                         ({"task_file": "task.md", "effort": "max", "cwd": str(repo)}, "effort 不对"),
                         ({"task_file": "task.md", "timeout_secs": 5000, "cwd": str(repo)}, "timeout 超上限"),
                         ({"task_file": "task.md", "cwd": str(TMP / "nodir")}, "cwd 不存在")):
            n = len(recs(rec))
            t, e = s.call("review", bad)
            check(e and "出错" in t and len(recs(rec)) == n, f"拒绝：{why}", t)

        print("review 默认：审工作区相对 HEAD 的未提交改动 + 暂存区")
        t, e = s.call("review", {"task_file": "task.md", "cwd": str(repo), "instructions": "改了 calc.py"})
        c = recs(rec)[-1]
        a, pr = c["argv"], c["prompt"]
        check(t.startswith("以下为初步审查意见，请逐条自行核实后再处理。\n===== review_id：r"),
              "返回开头是初步审查提示，再是 review_id", t[:120])
        check("状态：done" in t and "初步审查结论：有问题（阻断 1 条，应修 1 条，其中 1 条无出处、低可信）——只是线索，不是定论" in t
              and "tokens used：4,321" in t, "解析出结论和条数，标明只是线索", t)
        check("处理要求" not in t, "返回里没有「处理要求」行", t)
        check("README 也要更新。依据：任务书　【无出处，低可信】" in t and "calc.py:2 — 负数没处理。依据：读了文件\n" in t
              and t.count("【无出处，低可信】") == 1, "没有 文件:行号 的意见标「无出处，低可信」，有出处的不标", t)
        check(a[a.index("-s") + 1] == "read-only" and a[a.index("-m") + 1] == "gpt-6-luna"
              and a[a.index("-C") + 1] == str(repo) and "model_reasoning_effort=medium" in a
              and not any("danger" in x or "bypass" in x or "full-auto" in x for x in a),
              "强制 -s read-only、默认 gpt-6-luna、-C 仓库、没有 --dangerously*", a)
        check(f"任务书：{repo / 'task.md'}" in pr and "git diff HEAD" in pr and "git status --porcelain" in pr
              and "..HEAD" not in pr and "报告草稿：无" in pr and "补充说明" in pr and "改了 calc.py" in pr,
              "提示：任务书绝对路径、默认范围 git diff HEAD + 未跟踪、无报告草稿、补充说明", pr)
        check(all(k in pr for k in ("(a) 任务书里的每个要求有没有做到", "(b) 有没有违反任务书的规则",
                                     "(c) git status 里有没有不属于本任务的改动", "(d) 有报告草稿时",
                                     "计数用命令实际数", "(e) 明显的 bug", "结论：通过 / 有问题（二选一",
                                     "[阻断 / 应修 / 建议] 文件:行号", "不提风格类小问题")),
              "提示里有必查项 (a)~(e) 和交回格式", pr)
        check("只读" in pr and "不创建、修改、删除任何文件" in pr and "git status --short --branch" in pr
              and "M calc.py" in pr and "A  staged.py" in pr and "?? report.md" in pr,
              "提示里写明只读，并附上派审查时的 git status", pr)
        check(not c["secret_seen"], "审查员见不到凭证")

        print("review base + 报告草稿")
        t, e = s.call("review", {"task_file": str(repo / "task.md"), "cwd": str(repo), "base": "HEAD~1",
                                 "report_file": "report.md", "effort": "high"})
        pr, a = recs(rec)[-1]["prompt"], recs(rec)[-1]["argv"]
        check("状态：done" in t and "HEAD~1..HEAD" in pr and "git diff HEAD" in pr
              and f"报告草稿：{repo / 'report.md'}" in pr and "model_reasoning_effort=high" in a
              and a[a.index("-s") + 1] == "read-only", "base 审 base..HEAD + 未提交改动，带报告草稿", pr)

        print("review 非 git 目录，只给 instructions")
        t, e = s.call("review", {"instructions": "检查 a.txt 有 10 行", "cwd": str(plain)})
        pr = recs(rec)[-1]["prompt"]
        check("状态：done" in t and "cwd 不是 git 仓库" in pr and "任务书：无" in pr and "检查 a.txt 有 10 行" in pr,
              "非 git 目录按文件审", pr)

        print("review still_running 后 review_wait 接着等")
        t0 = time.time()
        t, e = s.call("review", {"instructions": "REVIEWSLOW 慢审", "cwd": str(repo)}, timeout=20)
        rid = re.search(r"review_id：([\w-]+)", t).group(1)
        check("状态：still_running" in t and 3.5 < time.time() - t0 < 6 and rid.startswith("r")
              and f'review_wait(review_ids=["{rid}"])' in t, "到单次上限返回 still_running，提示调 review_wait", t)
        t, e = s.call("review_wait", {"review_ids": [rid]}, timeout=20)
        check("状态：done" in t and t.startswith("以下为初步审查意见") and "初步审查结论：有问题" in t,
              "review_wait 拿到结论", t)
        t, e = s.call("review", {"task_file": "task.md", "cwd": str(repo), "wait": False})
        rid = re.search(r"review_id：([\w-]+)", t).group(1)
        check("状态：started" in t and "review_wait" in t, "wait=false 立即返回 review_id", t)
        t, e = s.call("review_wait", {"review_ids": [rid]}, timeout=20)
        check("状态：done" in t, "review_wait 等到", t)
        argvs = [r["argv"] for r in recs(rec) if "你是代码审查员" in r["prompt"]]
        check(len(argvs) == 5 and all(a[a.index("-s") + 1] == "read-only" for a in argvs),
              f"全部 {len(argvs)} 次审查都是 -s read-only")
        check(git(repo, "status", "--short") == " M calc.py\nA  staged.py\n?? report.md\n",
              "审查前后仓库状态没变", git(repo, "status", "--short"))
    finally:
        s.close()


def iface_tests():
    """假目录下 list / check / write；校验失败不落盘；overwrite；路径穿越拒绝。"""
    print("iface 模板工具")
    idir = TMP / "iface_tpl"
    idir.mkdir(parents=True, exist_ok=True)
    # 先放一个合法模板
    (idir / "demo.zs").write_text(
        "# c\n模板 演示\n用途 单测用\n参数 键 必填 snake 数据键\n例子 POST /x -> 动 作 a 模板 演示 键=k\n"
        "主体\n  表格 <<键>> {r}\n", encoding="utf-8")
    s = Server(GSB_IFACE_DIR=str(idir))
    try:
        tools = {t["name"] for t in s.req("tools/list")["result"]["tools"]}
        check({"list_iface_templates", "check_iface_template", "write_iface_template"} <= tools,
              "tools/list 始终有 iface 三工具", sorted(tools))

        t, e = s.call("list_iface_templates", {})
        check(not e and "demo.zs" in t and "模板 演示" in t and "键 必填 snake" in t,
              "list 列出文件名、中文名、参数", t)

        t, e = s.call("check_iface_template", {"file": "demo"})
        check(not e and "校验通过" in t and "模板 演示" in t, "check 已有文件通过", t)

        bad = "模板 坏的名\n用途 x\n主体\n  表格 <<没有>> {r}\n"
        t, e = s.call("check_iface_template", {"content": bad})
        check(not e and "校验失败" in t and ("占位符" in t or "不是声明" in t or "空格" in t),
              "check content 失败返回问题", t)

        # 非法英文名 / 穿越
        t, e = s.call("write_iface_template", {
            "name": "../escape", "title": "逃逸", "purpose": "坏",
            "body": {"lines": ["表格 k {r}"]}})
        check(e and ("英文文件名" in t or "只能是" in t), "拒绝 ../ 英文名", t)
        t, e = s.call("write_iface_template", {
            "name": "Foo", "title": "大写", "purpose": "坏",
            "body": {"lines": ["表格 k {r}"]}})
        check(e and "英文文件名" in t, "拒绝大写英文名", t)
        t, e = s.call("check_iface_template", {"file": str(TMP / "a.txt")})
        check(e and "只允许" in t, "check 拒绝目录外路径", t)

        # 校验失败不落盘
        before = set(idir.glob("*.zs"))
        t, e = s.call("write_iface_template", {
            "name": "badone", "title": "坏模板", "purpose": "缺主体占位",
            "params": [{"name": "键", "required": True, "constraint": "snake", "meaning": "k"}],
            "body": {"lines": ["表格 <<没有>> {r}"]}})
        check(not e and "写入取消" in t and "未落盘" in t, "校验失败不落盘（文本提示）", t)
        check(not (idir / "badone.zs").exists() and set(idir.glob("*.zs")) == before,
              "校验失败确实没有新文件", list(idir.glob("*.zs")))

        # 正常写入
        t, e = s.call("write_iface_template", {
            "name": "ping", "title": "轻响", "purpose": "冒烟回一条消息",
            "params": ["消息 必填 free 提示文字"],
            "example": "POST /ping -> 轻响一下 动作 ping 模板 轻响 消息=pong",
            "body": {"lines": ["设 _msg = <<消息>>", "消息 系统 {_msg} ok"]}})
        check(not e and "已写入" in t and (idir / "ping.zs").is_file(), "write 校验通过后落盘", t)
        text = (idir / "ping.zs").read_text(encoding="utf-8")
        check("模板 轻响" in text and "参数 消息 必填 free" in text and "<<消息>>" in text,
              "写入内容含中文名/参数/主体", text)

        # overwrite 默认拒绝
        t, e = s.call("write_iface_template", {
            "name": "ping", "title": "轻响", "purpose": "再写",
            "body": {"lines": ["消息 系统 ok ok"]}})
        check(e and "已存在" in t and "overwrite" in t, "默认 overwrite=false 拒绝覆盖", t)
        old = (idir / "ping.zs").read_text(encoding="utf-8")
        t, e = s.call("write_iface_template", {
            "name": "ping", "title": "轻响二", "purpose": "覆盖版",
            "params": ["消息 必填 free 提示"],
            "body": {"lines": ["设 _msg = <<消息>>", "消息 系统 {_msg} ok"]},
            "overwrite": True})
        check(not e and "已写入" in t and "已覆盖" in t, "overwrite=true 可覆盖", t)
        check("轻响二" in (idir / "ping.zs").read_text(encoding="utf-8") and old != (idir / "ping.zs").read_text(encoding="utf-8"),
              "覆盖后内容变了")

        # 中文名冲突
        t, e = s.call("write_iface_template", {
            "name": "ping2", "title": "演示", "purpose": "撞名",
            "body": {"lines": ["表格 k {r}"]}})
        check(not e and "写入取消" in t and "冲突" in t and not (idir / "ping2.zs").exists(),
              "中文名与已有文件冲突则不落盘", t)

        # text 直写 + list 闭环
        raw = ("模板 直写\n用途 用 text 写入\n参数 键 必填 snake k\n"
               "主体\n  表格 <<键>> {r}\n")
        t, e = s.call("write_iface_template", {"name": "direct", "text": raw})
        check(not e and (idir / "direct.zs").is_file(), "text 模式写入", t)
        t, e = s.call("list_iface_templates", {})
        check("direct.zs" in t and "模板 直写" in t and "ping.zs" in t, "write→list 闭环", t)
        t, e = s.call("check_iface_template", {"file": "direct.zs"})
        check("校验通过" in t, "write→check 闭环", t)
    finally:
        s.close()



def multi_edit_tests():
    """原子成功 / 中途失败不落盘 / count 不符 / 多文件 / 超上限；同文件多刀。"""
    print("multi_edit")
    root = TMP / "medit"
    root.mkdir()
    (root / "a.py").write_text("def f():\n    return 1\n\ndef g():\n    return 2\n", encoding="utf-8")
    (root / "b.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    (root / "config.json").write_text('{"k": 1}\n', encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (root / "many.py").write_text("\n".join(f"v{i} = {i}" for i in range(16)) + "\n", encoding="utf-8")

    s = Server()
    try:
        tools = {t["name"]: t for t in s.req("tools/list")["result"]["tools"]}
        check("multi_edit" in tools and tools["multi_edit"]["inputSchema"]["required"] == ["edits"],
              "tools/list 有 multi_edit，required=edits", tools["multi_edit"]["inputSchema"])

        # 原子成功：同文件两刀 + 另一文件一刀
        a0 = (root / "a.py").read_text(encoding="utf-8")
        b0 = (root / "b.py").read_text(encoding="utf-8")
        t, e = s.call("multi_edit", {"cwd": str(root), "edits": [
            {"path": "a.py", "before": "return 1", "after": "return 10"},
            {"path": "a.py", "before": "return 2", "after": "return 20"},
            {"path": "b.py", "before": "x = 1", "after": "x = 11"},
        ]})
        check(not e and "已改 3 处" in t and "原子提交" in t and "涉及 2 个文件" in t
              and "edits[0]" in t and "edits[2]" in t and "@@" in t, "原子成功：摘要+短 diff", t)
        check((root / "a.py").read_text(encoding="utf-8") == "def f():\n    return 10\n\ndef g():\n    return 20\n"
              and (root / "b.py").read_text(encoding="utf-8") == "x = 11\ny = 2\n",
              "两文件内容都对")

        # 中途失败：第二刀对不上 → 整批不落盘（先恢复原样测）
        (root / "a.py").write_text(a0, encoding="utf-8")
        (root / "b.py").write_text(b0, encoding="utf-8")
        t, e = s.call("multi_edit", {"cwd": str(root), "edits": [
            {"path": "a.py", "before": "return 1", "after": "return 99"},
            {"path": "a.py", "before": "return NOPE", "after": "return 0"},
            {"path": "b.py", "before": "x = 1", "after": "x = 9"},
        ]})
        check(e and "edits[1] 失败" in t and "未落盘" in t and "找不到" in t,
              "第二刀失败报 edits[1]、未落盘", t)
        check((root / "a.py").read_text(encoding="utf-8") == a0
              and (root / "b.py").read_text(encoding="utf-8") == b0,
              "原子失败：磁盘内容未变")

        # count 不符
        t, e = s.call("multi_edit", {"cwd": str(root), "edits": [
            {"path": "b.py", "before": "=", "after": ":=", "count": 1},
        ]})
        check(e and "出现了 2 次" in t and "count=1" in t and "未落盘" in t, "count 不符", t)
        check((root / "b.py").read_text(encoding="utf-8") == b0, "count 不符不写盘")

        # 同文件多刀顺序：后刀看到前刀结果（K28a 风格精简）
        t, e = s.call("multi_edit", {"cwd": str(root), "edits": [
            {"path": "many.py", "before": f"v{i} = {i}", "after": f"v{i} = {i * 10}"}
            for i in range(16)
        ]})
        check(not e and "已改 16 处" in t and "涉及 1 个文件" in t, "同文件 16 刀一次提交", t)
        body = (root / "many.py").read_text(encoding="utf-8")
        check(all(f"v{i} = {i * 10}" in body for i in range(16)), "16 处都改对", body)

        # 超上限
        t, e = s.call("multi_edit", {"cwd": str(root), "edits": [
            {"path": "b.py", "before": "y = 2", "after": "y = 3"}
        ] + [{"path": "b.py", "before": "y = 3", "after": "y = 3"}] * 20})
        check(e and "一次最多 20" in t, "超过 20 处拒绝", t)

        # 拒绝 config.json / .git / 越界
        t, e = s.call("multi_edit", {"cwd": str(root), "edits": [
            {"path": "config.json", "before": '"k": 1', "after": '"k": 2'}]})
        check(e and "受保护" in t, "拒绝 config.json", t)
        t, e = s.call("multi_edit", {"cwd": str(root), "edits": [
            {"path": ".git/HEAD", "before": "ref:", "after": "REF:"}]})
        check(e and ".git" in t, "拒绝 .git", t)
        t, e = s.call("multi_edit", {"cwd": str(root), "edits": [
            {"path": "../a.txt", "before": "line1", "after": "LINE1"}]})
        check(e and "越界" in t, "拒绝 cwd 外路径", t)
        check((root / "config.json").read_text(encoding="utf-8") == '{"k": 1}\n', "保护文件未改")
    finally:
        s.close()



def k32_tests():
    """K32 追加：CRLF 保留与提示、模板缩进检查与 _body_block 拆块、read_files 拦凭证、
    备份目录按进程分开且多次保留、用量上限不重试 / 瞬时限流重试。"""
    print("K32：multi_edit CRLF 保留")
    root = TMP / "k32"
    root.mkdir()
    crlf = root / "crlf.txt"
    crlf.write_bytes(b"alpha = 1\r\nbeta = 2\r\ngamma = 3\r\n")
    mixed = root / "mixed.txt"
    mixed.write_bytes(b"a = 1\r\nb = 2\nc = 3\r\n")
    s = Server()
    try:
        t, e = s.call("multi_edit", {"cwd": str(root), "edits": [
            {"path": "crlf.txt", "before": "beta = 2\r\n", "after": "beta = 20\r\n"}]})
        check(not e and "已改 1 处" in t, "CRLF 文件能改", t)
        check(crlf.read_bytes() == b"alpha = 1\r\nbeta = 20\r\ngamma = 3\r\n", "CRLF 行尾保留",
              crlf.read_bytes())
        t, e = s.call("multi_edit", {"cwd": str(root), "edits": [
            {"path": "mixed.txt", "before": "a = 1\r\n", "after": "a = 10\r\n"},
            {"path": "mixed.txt", "before": "c = 3\r\n", "after": "c = 30\r\n"}]})
        check(not e and mixed.read_bytes() == b"a = 10\r\nb = 2\nc = 30\r\n",
              "混合行尾原样保留", mixed.read_bytes())
        t, e = s.call("multi_edit", {"cwd": str(root), "edits": [
            {"path": "crlf.txt", "before": "gamma = 3\n", "after": "gamma = 33\n"}]})
        check(e and "CRLF" in t and "\\r\\n" in t, "before 用 \n 在 CRLF 文件匹配不到，提示写 \\r\\n", t)
        check(crlf.read_bytes() == b"alpha = 1\r\nbeta = 20\r\ngamma = 3\r\n", "提示那刀未落盘")

        print("K32：备份目录按进程分开、多次修改各留一份")
        t, e = s.call("multi_edit", {"cwd": str(root), "edits": [
            {"path": "crlf.txt", "before": "beta = 20", "after": "beta = 21"}]})
        t, e = s.call("multi_edit", {"cwd": str(root), "edits": [
            {"path": "crlf.txt", "before": "beta = 21", "after": "beta = 22"}]})
        check(not e, "后续两次修改成功", t)
        eb = TMP / "logs" / "edit_backup"
        pdirs = [d for d in eb.iterdir() if d.is_dir() and re.fullmatch(r"\d+_\d{8}-\d{6}", d.name)]
        check(len(pdirs) >= 2, "每个服务进程有独立备份目录（pid_启动时间）", [d.name for d in pdirs])
        cdirs = [d for d in pdirs if any(p.name.startswith("crlf.txt") for p in d.iterdir())]
        check(len(cdirs) == 1, "同一文件的备份集中在自己进程的目录里", [d.name for d in cdirs])
        vers = sorted(p.name for p in cdirs[0].iterdir() if p.name.startswith("crlf.txt"))
        check(vers == ["crlf.txt", "crlf.txt.1", "crlf.txt.2"], "同文件三次修改各留一份", vers)
    finally:
        s.close()

    print("K32：模板缩进检查与 _body_block 拆块")
    idir = TMP / "k32_iface"
    idir.mkdir()
    bad_indent = ("模板 缩进坏\n用途 测试\n参数 键 必填 snake k\n"
                  "主体\n  表格 <<键>> {r}\n    主体 当 x = 1\n      表格 y {r}\n")
    s2 = Server(GSB_IFACE_DIR=str(idir))
    try:
        t, e = s2.call("check_iface_template", {"content": bad_indent})
        check(not e and "校验失败" in t and "第 6 行" in t and "顶格" in t,
              "缩进的「主体 当」被拒并指行号", t)
        (idir / "indent_bad.zs").write_text(bad_indent, encoding="utf-8")
        (idir / "ok.zs").write_text(
            "模板 正常\n用途 测试\n参数 键 必填 snake k\n主体\n  表格 <<键>> {r}\n",
            encoding="utf-8")
        t, e = s2.call("check_iface_template", {"file": "indent_bad"})
        check("校验失败" in t and "顶格" in t, "check file 也走缩进检查", t)
        t, e = s2.call("list_iface_templates", {})
        check("indent_bad.zs" in t and "有问题" in t and "顶格" in t and "ok.zs" in t
              and "模板 正常" in t, "list 把缩进问题标为有问题，正常文件照列", t)
        body_str = ("主体\n  表格 <<键>> {r}\n"
                    "    主体 当 x\n      表格 y {r}\n"
                    "主体 当 x\n  表格 z {r}\n")
        t, e = s2.call("write_iface_template", {
            "name": "split", "title": "拆块", "purpose": "字符串主体自动拆块",
            "params": ["键 必填 snake k", "x 可选 go 条件参数"], "body": body_str})
        check(not e and "已写入" in t, "字符串主体含多个「主体」能写入", t)
        txt = (idir / "split.zs").read_text(encoding="utf-8")
        check("\n主体\n  表格 <<键>> {r}\n主体 当 x\n  表格 y {r}\n"
              "主体 当 x\n  表格 z {r}\n" in txt,
              "「主体…」行顶格、正文缩进两格", txt)
        t, e = s2.call("check_iface_template", {"file": "split"})
        check("校验通过" in t, "拆块后校验通过", t)
    finally:
        s2.close()

    print("K32：read_files 拦凭证文件")
    sec = TMP / "k32sec"
    sec.mkdir()
    for n in ("auth.json", ".env", "srv.pem", "db.key", "id_rsa_test", "my_credentials.txt",
              "prod_secret.conf", ".netrc", ".git-credentials", "normal.txt"):
        (sec / n).write_text("x = 1\n", encoding="utf-8")
    (sec / ".ssh").mkdir()
    (sec / ".ssh" / "known_hosts").write_text("h\n", encoding="utf-8")
    (sec / ".codex").mkdir()
    (sec / ".codex" / "auth.json").write_text("{}\n", encoding="utf-8")
    (sec / ".codex" / "history.log").write_text("log\n", encoding="utf-8")
    s3 = Server()
    try:
        t, e = s3.call("read_files", {"files": [
            str(sec / "normal.txt"), str(sec / "auth.json"), str(sec / ".env"),
            str(sec / "srv.pem"), str(sec / "id_rsa_test"), str(sec / "my_credentials.txt"),
            str(sec / ".ssh" / "known_hosts"), str(sec / ".codex" / "history.log")]})
        check(not e and "normal.txt（第 1-1 行" in t, "普通文件照读", t)
        check(t.count("拒绝读取（疑似凭证文件）") == 6, "auth.json/.env/*.pem/id_rsa*/credential/.ssh 都被拦", t)
        check("拒绝读取 6 个" in t, "汇总里写明拒绝数", t[-200:])
        check("history.log（第 1-1 行" in t, ".codex 普通日志放行（取舍：只拦凭证类）", t)
        t, e = s3.call("read_files", {"files": [str(sec / "*")]})
        check("normal.txt（第 1-1 行" in t and "auth.json：拒绝读取" in t
              and "srv.pem：拒绝读取" in t, "glob 展开后同样过滤", t)
    finally:
        s3.close()

    print("K32：限流分类（正则）")
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("gsb_tools_mcp_k32", SCRIPT)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    check(mod._CAPACITY_RE.search("model is at capacity, try later")
          and mod._CAPACITY_RE.search("HTTP 429 Too Many Requests")
          and mod._CAPACITY_RE.search("temporarily unavailable")
          and mod._CAPACITY_RE.search("529 overloaded_error"), "瞬时限流 / 满载能被识别")
    check(mod._USAGE_LIMIT_RE.search("usage limit reached for gpt-6-luna on your 4-hour window")
          and mod._USAGE_LIMIT_RE.search("credit balance is too low"), "用量上限能被识别")
    check(not mod._CAPACITY_RE.search("usage limit reached for gpt-6-luna"),
          "用量上限不再当瞬时限流去重试")
    check(not mod._USAGE_LIMIT_RE.search("model is at capacity"), "瞬时限流不当成用量上限")

    print("K32：用量上限不重试 / 瞬时限流重试（假 codex）")
    limit_bin = TMP / "k32bin_limit"
    limit_bin.mkdir()
    (limit_bin / "codex").write_text(
        "#!/usr/bin/env python3\n"
        "import sys\nargv = sys.argv[1:]\n"
        "sys.stdin.read()\n"
        "print(\"ERROR: usage limit reached for gpt-6-luna on your 4h window\", flush=True)\n"
        "sys.exit(1)\n")
    (limit_bin / "codex").chmod(0o755)
    cap_bin = TMP / "k32bin_cap"
    cap_bin.mkdir()
    (cap_bin / "codex").write_text(FAKE_CODEX)
    (cap_bin / "codex").chmod(0o755)
    sl = Server(max_block=4, GSB_PROBE="1",
                PATH=f"{limit_bin}:{os.environ.get('PATH', '')}",
                FAKE_CODEX_REC=str(TMP / "k32_codex_limit.jsonl"), GSB_PROBE_RETRY_WAITS="1,1")
    try:
        t, e = sl.call("probe", {"instructions": "LIMIT 顶到用量上限"}, timeout=20)
        check("用量上限" in t and "failed" in t and "自动重试了" not in t,
              "用量上限：不重试，按失败返回并写明", t)
    finally:
        sl.close()
    sc = Server(max_block=4, GSB_PROBE="1",
                PATH=f"{cap_bin}:{os.environ.get('PATH', '')}",
                FAKE_CODEX_REC=str(TMP / "k32_codex_cap.jsonl"), GSB_PROBE_RETRY_WAITS="1,1")
    try:
        t, e = sc.call("probe", {"instructions": "CAP 临时满载"}, timeout=20)
        check("状态：done" in t and "自动重试了 1 次" in t, "瞬时限流：仍自动重试", t)
    finally:
        sc.close()


def k34_tests():
    """K34 追加：verify / verify_wait —— 开关、参数校验、workspace-write + 临时目录、
    违规改动检测（git / 非 git）、JSON 解析成功 / 失败、still_running + verify_wait、
    超时杀进程组、说明里提 verify。"""
    bindir = TMP / "fakebin34"
    bindir.mkdir(exist_ok=True)
    (bindir / "codex").write_text(FAKE_CODEX)
    (bindir / "codex").chmod(0o755)
    rec = TMP / "codex_calls34.jsonl"
    env = {"PATH": f"{bindir}:{os.environ.get('PATH', '')}", "FAKE_CODEX_REC": str(rec),
           "GSB_PROBE_RETRY_WAITS": "1,1"}
    proj = TMP / "k34proj"
    proj.mkdir(exist_ok=True)
    if not (proj / ".git").exists():
        git(proj, "init", "-q", "-b", "main")
        (proj / "app.py").write_text("print('hi')\n")
        git(proj, "add", "-A")
        git(proj, "commit", "-q", "-m", "i")
    plain = TMP / "k34plain"
    plain.mkdir(exist_ok=True)
    (plain / "a.txt").write_text("x\n", encoding="utf-8")

    print("verify 默认不开")
    s0 = Server(GSB_PROBE="1", GSB_REVIEW="1", **env)
    try:
        names = [t["name"] for t in s0.req("tools/list")["result"]["tools"]]
        check("verify" not in names and "verify_wait" not in names and "review" in names,
              "没 GSB_VERIFY=1 时没有 verify（probe/review 照旧）", names)
        ins = s0.req("initialize", {"protocolVersion": "2025-03-26"})["result"]["instructions"]
        check("verify" not in ins, "没开 verify 时说明里不提 verify", ins)
    finally:
        s0.close()

    s = Server(max_block=4, GSB_VERIFY="1", **env)
    try:
        print("verify 开关 / schema")
        tools = {t["name"]: t for t in s.req("tools/list")["result"]["tools"]}
        check({"verify", "verify_wait"} <= set(tools) and "probe" not in tools
              and "review" not in tools, "GSB_VERIFY=1 时有 verify / verify_wait", list(tools))
        d = tools["verify"]["description"]
        props = tools["verify"]["inputSchema"]["properties"]
        check({"instructions", "cwd", "project", "base", "effort", "timeout_secs", "wait", "model"}
              <= set(props) and "workspace-write" in d and "JSON" in d and "违规改动" in d
              and "临时目录" in d, "schema 参数齐全，描述写明沙箱 / JSON / 违规改动", d[:200])
        ins = s.req("initialize", {"protocolVersion": "2025-03-26"})["result"]["instructions"]
        check("verify" in ins and "回归" in ins, "说明里提 verify（回归交给 verify）", ins)

        print("verify 参数校验（不启动 codex）")
        for bad, why in (({"cwd": str(proj)}, "instructions 没给"),
                         ({"instructions": "x", "effort": "max", "cwd": str(proj)}, "effort 不对"),
                         ({"instructions": "x", "timeout_secs": 5000, "cwd": str(proj)}, "timeout 超上限"),
                         ({"instructions": "x", "cwd": str(TMP / "nodir")}, "cwd 不存在"),
                         ({"instructions": "x", "project": str(TMP / "noproj"), "cwd": str(proj)}, "project 不存在"),
                         ({"instructions": "x", "base": "HEAD~1..HEAD", "cwd": str(proj)}, "base 写成范围"),
                         ({"instructions": "x", "base": "--cfg=x", "cwd": str(proj)}, "base 像选项"),
                         ({"instructions": "x", "base": "nosuchref", "cwd": str(proj)}, "base 不存在"),
                         ({"instructions": "x", "base": "HEAD", "cwd": str(plain)}, "非 git project 给 base"),
                         ({"instructions": "x", "model": "bad model", "cwd": str(proj)}, "model 不对")):
            n = len(recs(rec))
            t, e = s.call("verify", bad)
            check(e and "出错" in t and len(recs(rec)) == n, f"拒绝：{why}", t)

        print("verify 正常：JSON 解析 + workspace-write 参数 + 前言")
        t, e = s.call("verify", {"instructions": "VERIFYOK 跑全量回归", "cwd": str(proj)}, timeout=30)
        c = recs(rec)[-1]
        a, pr = c["argv"], c["prompt"]
        check(not e and "状态：done" in t and "验证 JSON：已解析" in t and "结论=通过" in t
              and "检查 2 项（通过 1，不通过 1）" in t and "发现 1 条" in t,
              "done + 解析出 JSON 摘要（状态/结论/检查/发现）", t)
        check("违规改动" not in t, "没违规时不标违规改动", t)
        check(a[a.index("-s") + 1] == "workspace-write" and a[a.index("-m") + 1] == "gpt-6-luna"
              and "sandbox_workspace_write.network_access=true" in a
              and not any("danger" in x or "bypass" in x or "full-auto" in x for x in a),
              "-s workspace-write + 放行本地网络，无 --dangerously*", a)
        cwd_arg = a[a.index("-C") + 1]
        check(cwd_arg.startswith("/tmp/verify_") and os.path.isdir(cwd_arg) and c["cwd"] == cwd_arg,
              "-C 锁在自己的临时目录（已建好）", (cwd_arg, c["cwd"]))
        check("你是验证 agent" in pr and "只做验证不修东西" in pr and "优先用项目已有入口" in pr
              and "成功|失败" in pr and "通过|不通过|无法验证" in pr
              and "VERIFYOK 跑全量回归" in pr and str(proj) in pr and cwd_arg in pr
              and "不要用 pkill" in pr,
              "前言：只验证不修 / 临时目录 / 优先已有入口 / 严格 JSON / 项目与临时目录路径", pr)
        check(not c["secret_seen"] and "GH_TOKEN" not in c["env_keys"], "验证员见不到凭证")
        check(re.search(r"verify_id：v\d+-", t) is not None, "verify_id 前缀 v", t[:120])

        print("verify base / project")
        t, e = s.call("verify", {"instructions": "VERIFYOK 基线对比", "cwd": str(proj), "base": "HEAD"},
                      timeout=30)
        pr = recs(rec)[-1]["prompt"]
        check("状态：done" in t and "基线（对比用，只读）：git 提交 HEAD" in pr and "拷一份仓库" in pr,
              "base 进提示，写明只许在自己的目录里切", pr)

        print("verify JSON 解析失败：按原文返回")
        t, e = s.call("verify", {"instructions": "VERIFYBAD 不按格式", "cwd": str(proj)}, timeout=30)
        check("状态：done" in t and "解析失败" in t and "这不是 JSON" in t,
              "解析失败标明并按原文返回", t)

        print("verify still_running 后 verify_wait 接着等；wait=false")
        t0 = time.time()
        t, e = s.call("verify", {"instructions": "VERIFYOK SLOW6 慢验", "cwd": str(proj)}, timeout=20)
        vid = re.search(r"verify_id：(v[\w-]+)", t).group(1)
        check("状态：still_running" in t and 3.5 < time.time() - t0 < 6
              and 'verify_wait(verify_ids=["' in t, "到单次上限返回 still_running，提示调 verify_wait", t)
        t, e = s.call("verify_wait", {"verify_ids": [vid]}, timeout=20)
        check("状态：done" in t and "验证 JSON：已解析" in t, "verify_wait 拿到结果并解析", t)
        t, e = s.call("verify", {"instructions": "VERIFYOK no-wait", "cwd": str(proj), "wait": False})
        vid2 = re.search(r"verify_id：(v[\w-]+)", t).group(1)
        check("状态：started" in t and "verify_wait" in t and str(proj) in t,
              "wait=false 立即返回 verify_id + 工作目录说明", t)
        t, e = s.call("verify_wait", {"verify_ids": [vid2]}, timeout=20)
        check("状态：done" in t and "验证 JSON：已解析" in t, "verify_wait 等到", t)

        print("verify 超时：杀掉整个进程组")
        t, e = s.call("verify", {"instructions": "HANG 起服务不停", "timeout_secs": 2, "cwd": str(proj)},
                      timeout=20)
        child = int(Path(str(rec) + ".child").read_text())
        time.sleep(0.3)
        check("状态：timeout" in t and not alive(child), "timeout 杀进程组（验证员起的服务也停）", (t, child))
    finally:
        s.close()

    print("verify 违规改动检测（git / 非 git）")
    s2 = Server(max_block=4, GSB_VERIFY="1",
                **dict(env, FAKE_VERIFY_TARGET=str(proj / "badfile.txt")))
    try:
        t, e = s2.call("verify", {"instructions": "VERIFYOK WRITE", "cwd": str(proj)}, timeout=30)
        check("状态：done" in t and "违规改动" in t and "badfile.txt" in t
              and "验证 JSON：已解析" in t, "git 项目被写 → 标违规改动，JSON 照常解析", t)
    finally:
        s2.close()
    (proj / "badfile.txt").unlink(missing_ok=True)
    check(git(proj, "status", "--short") == "", "核对后测试现场清理干净", git(proj, "status", "--short"))
    s3 = Server(max_block=4, GSB_VERIFY="1",
                **dict(env, FAKE_VERIFY_TARGET=str(plain / "extra.txt")))
    try:
        t, e = s3.call("verify", {"instructions": "VERIFYOK WRITE", "cwd": str(plain)}, timeout=30)
        check("状态：done" in t and "违规改动" in t and "extra.txt" in t,
              "非 git 项目文件清单变化 → 标违规改动", t)
    finally:
        s3.close()
    (plain / "extra.txt").unlink(missing_ok=True)


def k38_tests():
    """K38 追加：verify 前言交代运行环境（.venv / PYTHONPATH / 「环境」JSON 字段 /
    make_app 起法）；结论 JSON 的「环境」合规 → 正常；引擎不在被验仓库下 / 缺「环境」
    → 摘要标 ⚠ 环境不符，按「无法验证」对待；推不出仓库根时前言交代先找。"""
    bindir = TMP / "fakebin38"
    bindir.mkdir(exist_ok=True)
    (bindir / "codex").write_text(FAKE_CODEX)
    (bindir / "codex").chmod(0o755)
    rec = TMP / "codex_calls38.jsonl"
    env = {"PATH": f"{bindir}:{os.environ.get('PATH', '')}", "FAKE_CODEX_REC": str(rec),
           "GSB_PROBE_RETRY_WAITS": "1,1"}
    proj = TMP / "k34proj"
    proj.mkdir(exist_ok=True)
    if not (proj / ".git").exists():
        git(proj, "init", "-q", "-b", "main")
        (proj / "app.py").write_text("print('hi')\n")
        git(proj, "add", "-A")
        git(proj, "commit", "-q", "-m", "i")
    plain = TMP / "k38plain"
    plain.mkdir(exist_ok=True)
    (plain / "a.txt").write_text("x\n", encoding="utf-8")

    s = Server(max_block=4, GSB_VERIFY="1", **env)
    try:
        print("K38 前言交代运行环境")
        t, e = s.call("verify", {"instructions": "VERIFYOK 跑全量回归", "cwd": str(proj)},
                      timeout=30)
        pr = recs(rec)[-1]["prompt"]
        check("状态：done" in t and "验证 JSON：已解析" in t, "K38: verify 正常跑完", t)
        check(".venv/bin/python" in pr and "PYTHONPATH=" in pr
              and "import gen,tools;print(gen.__file__,tools.__file__)" in pr
              and "「环境」" in pr and "make_app(real=False, login=…)" in pr
              and "引擎代码不拷" in pr and "不要用系统 python3" in pr,
              "K38 前言：.venv 解释器 / PYTHONPATH 引擎 / 环境 JSON 字段 / make_app 起法 / 不拷引擎",
              pr)
        check(f"PYTHONPATH={proj}" in pr and f"{proj}/.venv/bin/python" in pr,
              "K38 前言：能推出仓库根时写具体路径", pr)

        print("K38 环境合规：不标 ⚠")
        t, e = s.call("verify", {"instructions": "VERIFYOK ENVOKEY 环境合规", "cwd": str(proj)},
                      timeout=30)
        check("状态：done" in t and "验证 JSON：已解析" in t and "结论=通过" in t
              and "发现 0 条" in t and "环境不符" not in t,
              "K38 合规环境：正常解析，无 ⚠ 环境不符", t)

        print("K38 引擎不在被验仓库下 → ⚠ 且按无法验证")
        t, e = s.call("verify", {"instructions": "VERIFYOK ENVWRONG 旧快照", "cwd": str(proj)},
                      timeout=30)
        check("状态：done" in t and "⚠ 环境不符" in t and "解释器不是被验仓库的 .venv" in t
              and "/usr/bin/python3" in t and "按「无法验证」对待" in t
              and "结论=不通过" in t and "这不是 JSON" not in t,
              "K38 旧解释器：标 ⚠ 环境不符（模型原文照录，结论=不通过 保留）", t)

        print("K38 引擎不在被验仓库下 → ⚠ 且按无法验证")
        t, e = s.call("verify", {"instructions": "VERIFYOK ENVWRONGENG 旧引擎", "cwd": str(proj)},
                      timeout=30)
        check("状态：done" in t and "⚠ 环境不符" in t and "引擎不在被验仓库根下" in t
              and "luna_roles" in t and "按「无法验证」对待" in t,
              "K38 旧引擎快照：标 ⚠ 环境不符，按无法验证", t)

        print("K38 缺「环境」字段 → ⚠")
        t, e = s.call("verify", {"instructions": "VERIFYOK 缺环境字段", "cwd": str(proj)},
                      timeout=30)
        check("状态：done" in t and "⚠ 环境不符" in t and "缺「环境」字段" in t
              and "按「无法验证」对待" in t, "K38 缺环境：标 ⚠，按无法验证", t)

        print("K38 非 git 项目推不出仓库根：前言交代先找")
        t, e = s.call("verify", {"instructions": "VERIFYOK plain", "cwd": str(plain)},
                      timeout=30)
        pr = recs(rec)[-1]["prompt"]
        check("先找被验仓库的 .venv/bin/python" in pr and "向上找仓库根" in pr,
              "K38 推不出仓库根：前言交代先找 .venv / 向上找仓库根", pr)
    finally:
        s.close()
    shutil.rmtree(plain, ignore_errors=True)


FAKE_CODEX47 = '''#!/usr/bin/env python3
# 假 codex（K47）：记 argv / 提示词；「环境」JSON 的路径可由 FAKE_ENGINE_REPO 指到别的仓库
import json, os, sys
argv = sys.argv[1:]
prompt = sys.stdin.read()
rec = os.environ["FAKE_CODEX_REC"]
with open(rec, "a") as f:
    f.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "prompt": prompt}) + "\\n")
out = argv[argv.index("-o") + 1]
task = prompt.split("任务：")[-1]
print("OpenAI Codex (fake)\\nuser\\n" + prompt, flush=True)


def done(text, tok="1,234"):
    open(out, "w").write(text)
    print("codex\\n" + text + "\\ntokens used\\n" + tok, flush=True)
    sys.exit(0)


if "你是验证 agent" in prompt:
    tgt = os.environ.get("FAKE_VERIFY_TARGET")
    if tgt and "WRITE" in task:
        open(tgt, "a").write("bad\\n")
    if "ENGOKEY" in task:
        eng = os.environ.get("FAKE_ENGINE_REPO") or "/noeng"
        done(json.dumps({"状态": "成功", "结果": {"结论": "通过", "环境": {
            "python": eng + "/.venv/bin/python",
            "引擎": eng + "/gen/__init__.py " + eng + "/tools/__init__.py",
            "起法": "PYTHONPATH=" + eng + " .venv/bin/python serve.py"},
            "检查": [{"项": "smoke", "通过": True, "证据": "200"}],
            "发现": [], "说明": "engine env"}}, ensure_ascii=False), "7,778")
    if "ENVWRONG" in task:
        done(json.dumps({"状态": "成功", "结果": {"结论": "不通过", "环境": {
            "python": "/usr/bin/python3",
            "引擎": "/workspace/dslagent_exp/luna_roles/code/gen/__init__.py",
            "起法": "PYTHONPATH=/elsewhere python3 -m gen run"},
            "检查": [{"项": "smoke", "通过": False, "证据": "500"}],
            "发现": [], "说明": "old snapshot"}}, ensure_ascii=False), "6,666")
    done(json.dumps({"状态": "成功", "结果": {"结论": "通过", "检查": [
        {"项": "x", "通过": True, "证据": "e"}], "发现": [], "说明": "ok"}},
        ensure_ascii=False))
done("结论：" + task.strip())
'''


def k47_tests():
    """K47 追加：verify 加 engine_repo（引擎仓库）。显式参数生效；项目在仓库外、cwd 在
    仓库内 → 用 cwd 的仓库；都推不出 → 「先找」；engine_repo 不是带 gen/ + tools/ 的仓库根
    要拒；引擎仓库与被验项目分离时「环境」核对按引擎仓库判；被验仓库和引擎仓库两边快照都
    比对（写哪边都标违规改动）。已有 K34/K38 用例一字不改。"""
    bindir = TMP / "fakebin47"
    bindir.mkdir(exist_ok=True)
    (bindir / "codex").write_text(FAKE_CODEX47)
    (bindir / "codex").chmod(0o755)
    rec = TMP / "codex_calls47.jsonl"
    proj = TMP / "k47proj"           # 被验项目：仓库外普通目录（非 git）
    proj.mkdir(exist_ok=True)
    (proj / "a.txt").write_text("x\\n", encoding="utf-8")
    eng = TMP / "k47eng"             # 引擎仓库：带 gen/ + tools/ + .venv/bin/python（非 git）
    (eng / "gen").mkdir(parents=True, exist_ok=True)
    (eng / "tools").mkdir(exist_ok=True)
    (eng / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    # 真实 venv 的 python 是指向系统 python3 的符号链接：核对不能用 realpath 跳出 .venv
    _vpy = eng / ".venv" / "bin" / "python"
    if not _vpy.is_symlink():
        _vpy.unlink(missing_ok=True)
        _vpy.symlink_to("/bin/sh")
    engd = TMP / "k47eng"           # Path 版本，后面拼 FAKE_VERIFY_TARGET 用
    eng = os.path.realpath(str(eng))
    env = {"PATH": f"{bindir}:{os.environ.get('PATH', '')}", "FAKE_CODEX_REC": str(rec),
           "GSB_PROBE_RETRY_WAITS": "1,1", "FAKE_ENGINE_REPO": eng}

    s = Server(max_block=4, GSB_VERIFY="1", **env)
    try:
        print("K47 schema / 说明")
        tools = {t["name"]: t for t in s.req("tools/list")["result"]["tools"]}
        d = tools["verify"]["description"]
        props = tools["verify"]["inputSchema"]["properties"]
        check("engine_repo" in props and "engine_repo" in d and "cwd 在引擎仓库" in d,
              "K47: schema 有 engine_repo，描述写明被验项目不在引擎仓库下时传它 / 保证 cwd", d[:260])
        ins = s.req("initialize", {"protocolVersion": "2025-03-26"})["result"]["instructions"]
        check("engine_repo" in ins, "K47: initialize 说明提 engine_repo", ins)

        print("K47 参数校验（不启动 codex）")
        for bad, why in (({"instructions": "x", "cwd": str(proj), "engine_repo": str(proj)},
                          "engine_repo 没有 gen/ + tools/"),
                         ({"instructions": "x", "cwd": str(proj),
                           "engine_repo": str(TMP / "nodir47")}, "engine_repo 不是目录")):
            n = len(recs(rec))
            t, e = s.call("verify", bad)
            check(e and "出错" in t and len(recs(rec)) == n, f"K47 拒绝：{why}", t)

        print("K47 显式 engine_repo 生效")
        t, e = s.call("verify", {"instructions": "VERIFYOK plain", "cwd": str(proj),
                                 "engine_repo": str(eng)}, timeout=30)
        pr = recs(rec)[-1]["prompt"]
        check("状态：done" in t and f"PYTHONPATH={eng}" in pr
              and f"{eng}/.venv/bin/python" in pr and "引擎仓库" in pr and "也不许" in pr,
              "K47: 显式参数 → 前言的 .venv / PYTHONPATH 都指引擎仓库，且写明引擎仓库不许改",
              pr[-300:])

        print("K47 项目在仓库外、cwd 在仓库内 → 用 cwd 的仓库")
        t, e = s.call("verify", {"instructions": "VERIFYOK plain", "cwd": eng,
                                 "project": str(proj)}, timeout=30)
        pr = recs(rec)[-1]["prompt"]
        check("状态：done" in t and f"PYTHONPATH={eng}" in pr,
              "K47: cwd 向上探测到带 gen/ + tools/ 的仓库根", pr[-300:])

        print("K47 都推不出 → 前言交代先找")
        t, e = s.call("verify", {"instructions": "VERIFYOK plain", "cwd": str(proj)}, timeout=30)
        pr = recs(rec)[-1]["prompt"]
        check("先找被验仓库的 .venv/bin/python" in pr and "向上找仓库根" in pr
              and "当前工作目录" in pr,
              "K47: 推不出引擎仓库 → 先找 / 被验项目推不出再从 cwd 向上找", pr[-300:])

        print("K47 显式 engine_repo 缺 .venv → 前言禁用别处解释器，环境核对按无法验证")
        eng2 = TMP / "k47eng_novenv"
        (eng2 / "gen").mkdir(parents=True, exist_ok=True)
        (eng2 / "tools").mkdir(exist_ok=True)
        eng2 = os.path.realpath(str(eng2))
        t, e = s.call("verify", {"instructions": "VERIFYOK plain", "cwd": str(proj),
                                 "engine_repo": eng2}, timeout=30)
        pr = recs(rec)[-1]["prompt"]
        check("状态：done" in t and f"{eng2}/.venv/bin/python" in pr and "下没有" in pr
              and "不要改用系统 python" in pr and f"PYTHONPATH={eng2}" in pr
              and "先找引擎仓库的 .venv" not in pr,
              "K47: 显式引擎仓库缺 .venv → 前言写明没有、不许改用别处解释器、结论无法验证", pr[-400:])
        t, e = s.call("verify", {"instructions": "VERIFYOK ENGOKEY 别处venv", "cwd": str(proj),
                                 "engine_repo": eng2}, timeout=30)
        check("状态：done" in t and "⚠ 环境不符" in t and "按「无法验证」对待" in t,
              "K47: 缺 .venv 的引擎仓库 + 验证员用了别处 .venv → ⚠ 环境不符", t)

        print("K47 分离时「环境」核对按引擎仓库判")
        t, e = s.call("verify", {"instructions": "VERIFYOK ENGOKEY 分离合规", "cwd": str(proj),
                                 "engine_repo": eng}, timeout=30)
        check("状态：done" in t and "验证 JSON：已解析" in t and "结论=通过" in t
              and "环境不符" not in t,
              "K47: 环境=引擎仓库（分离于被验项目）→ 不标 ⚠", t)
        t, e = s.call("verify", {"instructions": "VERIFYOK ENVWRONG 旧快照", "cwd": str(proj),
                                 "engine_repo": eng}, timeout=30)
        check("状态：done" in t and "⚠ 环境不符" in t and "解释器不是被验仓库的 .venv" in t
              and "按「无法验证」对待" in t,
              "K47: 环境指向别的仓库 → 按引擎仓库判 ⚠ 环境不符", t)
    finally:
        s.close()

    print("K47 两边快照都比对（被验仓库 + 引擎仓库）")
    s2 = Server(max_block=4, GSB_VERIFY="1",
                **dict(env, FAKE_VERIFY_TARGET=str(proj / "bad.txt")))
    try:
        t, e = s2.call("verify", {"instructions": "VERIFYOK WRITE", "cwd": str(proj),
                                  "engine_repo": eng}, timeout=30)
        check("状态：done" in t and "违规改动" in t and str(proj) in t,
              "K47: 写被验项目 → 标违规改动", t)
    finally:
        s2.close()
    (proj / "bad.txt").unlink(missing_ok=True)
    s3 = Server(max_block=4, GSB_VERIFY="1",
                **dict(env, FAKE_VERIFY_TARGET=str(engd / "bad.txt")))
    try:
        t, e = s3.call("verify", {"instructions": "VERIFYOK WRITE", "cwd": str(proj),
                                  "engine_repo": eng}, timeout=30)
        check("状态：done" in t and "违规改动" in t and eng in t,
              "K47: 写引擎仓库 → 也标违规改动（两边都拍快照）", t)
    finally:
        s3.close()
    (engd / "bad.txt").unlink(missing_ok=True)


def main():
    (TMP / "a.txt").write_text("".join(f"line{i}\n" for i in range(1, 11)), encoding="utf-8")
    (TMP / "b.py").write_text("print('b')\r\nx = 1\r\n", encoding="utf-8")
    (TMP / "sub").mkdir()
    (TMP / "sub" / "c.py").write_text("c1\nc2\n", encoding="utf-8")
    (TMP / "bin.dat").write_bytes(b"\x00\x01\x02abc")
    (TMP / "big.txt").write_text("".join(f"{'x' * 90}{i}\n" for i in range(1, 2001)), encoding="utf-8")
    (TMP / "empty.txt").write_text("", encoding="utf-8")

    s = Server()
    try:
        print("协议")
        r = s.req("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "t", "version": "0"}})
        check(r["result"]["protocolVersion"] == "2025-06-18"
              and "tools" in r["result"]["capabilities"], "initialize 回协议版本和 tools 能力", r)
        k33i = r["result"].get("instructions") or ""
        check("工具用法" in k33i and "read_files" in k33i and "cat" in k33i
              and "run_wait" in k33i and "sleep" in k33i and "multi_edit" in k33i
              and "write_iface_template" in k33i and "iftpl.py" in k33i
              and "probe" not in k33i and "review" not in k33i,
              "initialize instructions：工具用法按实际暴露的工具生成（默认没 probe/review）", k33i)
        s.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        r = s.req("tools/list")
        names = [t["name"] for t in r["result"]["tools"]]
        check(names == ["read_files", "multi_edit", "run_wait", "wait_pid",
                        "list_iface_templates", "check_iface_template", "write_iface_template"]
              and all(t["inputSchema"]["type"] == "object" for t in r["result"]["tools"]),
              "tools/list 有基础工具 + multi_edit + iface 模板三工具和 schema", names)
        d0 = {t["name"]: t for t in r["result"]["tools"]}
        check(all(d0[n]["description"].startswith("优先用本工具")
                  for n in ("read_files", "multi_edit", "run_wait", "wait_pid")),
              "read_files/multi_edit/run_wait/wait_pid 的 description 开头都写了优先用本工具",
              {n: d0[n]["description"][:40] for n in ("read_files", "multi_edit", "run_wait", "wait_pid")})
        check(s.req("ping")["result"] == {}, "ping")
        _, err = s.call("nope", {})
        check(isinstance(err, dict) and err["code"] == -32602, "不认识的工具回 JSON-RPC 错误", err)
        r = s.req("foo/bar")
        check(r.get("error", {}).get("code") == -32601, "不支持的方法回 -32601", r)

        print("read_files")
        t, e = s.call("read_files", {"files": ["a.txt", {"path": "a.txt", "start": 3, "end": 5},
                                               {"path": str(TMP / "b.py")}, "sub/c.py"]})
        check(not e and "a.txt（第 1-10 行，共 10 行）" in t and "10\tline10" in t,
              "整个文件带行号、注明总行数", t)
        check("a.txt（第 3-5 行，共 10 行） =====\n3\tline3\n4\tline4\n5\tline5\n\n" in t,
              "行号范围含首尾", t)
        check("1\tprint('b')\n2\tx = 1\n" in t and "\r" not in t, "绝对路径 / CRLF 去掉 \\r", t)
        check("c.py（第 1-2 行" in t and t.rstrip().endswith("[读了 4 个，出错 0 个，共 " + t.rsplit("共 ", 1)[1]),
              "相对路径按服务器 cwd，末尾有汇总", t[-200:])
        t, e = s.call("read_files", {"files": ["nope.txt", "sub", "bin.dat", "a.txt", "empty.txt",
                                               {"path": "a.txt", "start": 50},
                                               {"path": "a.txt", "start": 5, "end": 2}]})
        check(not e and "nope.txt：错误：不存在" in t and "sub：错误：是目录" in t
              and "bin.dat：错误：二进制文件" in t, "缺失 / 目录 / 二进制各给错误条目", t)
        check("10\tline10" in t and "empty.txt（空文件）" in t and "start=50 超出文件末尾" in t
              and "行号范围不对" in t, "出错不影响别的文件；空文件、越界、反向范围有说明", t)
        check("出错 4 个" in t, "汇总里数出错数", t[-80:])
        t, e = s.call("read_files", {"files": ["big.txt"], "max_chars_per_file": 1000})
        body = t.split("=====\n", 1)[1]
        check("超出单文件上限 1000 字" in t and "start=11" in t and "10\t" in t and "11\t" not in body.split("…")[0],
              "单文件超上限截断并说明从哪接着读", t[:300])
        t, e = s.call("read_files", {"files": ["big.txt", "a.txt", "sub/c.py"],
                                     "max_chars_per_file": 100000, "max_total_chars": 5000})
        check("big.txt（第 1-" in t and "超出总上限 5000 字" in t and "a.txt" in t.split("没读：")[1],
              "总上限用完后后面的文件列为没读", t[-300:])
        t, e = s.call("read_files", {"files": ["**/*.py", "zz*.none"]})
        check("b.py（" in t and "c.py（" in t and "zz*.none：错误：glob 没匹配到文件" in t,
              "glob 展开（含 **），没匹配给错误", t)
        t, e = s.call("read_files", {"files": "a.txt"})
        check(not e and "line1" in t, "files 给单个字符串也行")
        t, e = s.call("read_files", {"files": []})
        check(e is True and "非空列表" in t, "空列表是工具错误（isError），不是协议错误", t)

        print("run_wait")
        t, e = s.call("run_wait", {"command": "echo hello; echo err >&2; pwd"})
        check(not e and "状态：finished" in t and "退出码：0" in t and "hello" in t and "err" in t
              and str(TMP) in t, "正常退出：退出码 0、stdout+stderr、在服务器 cwd 跑", t)
        log = field(t, "log_path")
        check(log and Path(log).is_file() and "hello" in Path(log).read_text(), "完整输出写到 log", log)
        t, e = s.call("run_wait", {"command": "for i in $(seq 1 200); do echo n$i; done; exit 3",
                                   "tail_lines": 5, "cwd": str(TMP / "sub"),
                                   "log_path": str(TMP / "mylog" / "x.log")})
        check("退出码：3" in t and "n200" in t and "n195" not in t and "n196" in t
              and "下面是末尾 5 行" in t, "非零退出码、只回末尾 N 行", t)
        check((TMP / "mylog" / "x.log").read_text().count("\n") == 200, "指定 log_path 存全量")
        t, e = s.call("run_wait", {"command": "pwd", "cwd": str(TMP / "sub")})
        check(str(TMP / "sub") in t, "cwd 参数生效", t)
        t, e = s.call("run_wait", {"command": "env"})
        check("HARMLESS_VAR=ok" in t and SECRET not in t and "ZAI_CODING_PLAN_API_KEY" not in t
              and "GH_TOKEN" not in t and "MY_SECRET" not in t
              and "__CURSOR_SANDBOX_ENV_RESTORE" not in t
              and "ghp_embedded_in_restore" not in t
              and "sk-embedded-in-restore" not in t,
              "名字像凭证的变量、以及内嵌凭证的 SANDBOX_ENV_RESTORE 不进命令环境", "")
        t, e = s.call("run_wait", {"command": "x", "timeout_secs": 99999})
        check(e is True and "timeout_secs" in t, "timeout_secs 超上限报错", t)
        t, e = s.call("run_wait", {"command": "  "})
        check(e is True, "空命令报错", t)

        print("超时杀进程组")
        mark = TMP / "child.pid"
        t0 = time.time()
        t, e = s.call("run_wait", {"command": f"sleep 300 & echo $! > {mark}; echo started; wait",
                                   "timeout_secs": 2})
        child = int(mark.read_text().strip())
        time.sleep(0.3)
        check("状态：timeout" in t and "已杀掉整个进程组" in t and time.time() - t0 < 6,
              "超时返回 timeout 并说明", t)
        check(not alive(child), "后台子进程（同进程组）也被杀", child)

        print("单次阻塞上限 → still_running → wait_pid")
        t0 = time.time()
        t, e = s.call("run_wait", {"command": "echo a; sleep 7; echo finished-ok", "timeout_secs": 60})
        pid = int(field(t, "pid"))
        log = field(t, "log_path")
        check("still_running" in t and 3.5 < time.time() - t0 < 6 and f"wait_pid(pid={pid}" in t,
              "超过单次上限（4 秒）返回 still_running 和接着等的办法", t)
        check(alive(pid), "命令还在跑，没被杀")
        t, e = s.call("wait_pid", {"pid": pid, "log_path": log})
        check("状态：finished" in t and "退出码：0" in t and "finished-ok" in t,
              "wait_pid 等自己起的进程：拿到退出码和输出", t)
        t, e = s.call("run_wait", {"command": "sleep 30", "timeout_secs": 6})
        pid = int(field(t, "pid"))
        check("still_running" in t, "命令超时比单次上限长时先返回 still_running", t)
        t, e = s.call("wait_pid", {"pid": pid})
        check("状态：timeout" in t and not alive(pid), "到 timeout_secs 后台看门狗杀掉，wait_pid 报 timeout", t)

        print("wait_pid：外部进程")
        lf = TMP / "ext.log"
        ext = subprocess.Popen(["bash", "-c", f"echo ext-start; sleep 2; echo ext-done"],
                               stdout=open(lf, "w"), stderr=subprocess.STDOUT)
        t0 = time.time()
        t, e = s.call("wait_pid", {"pid": ext.pid, "log_path": str(lf), "tail_lines": 10})
        ext.wait()
        check("状态：finished" in t and "拿不到退出码" in t and "ext-done" in t and time.time() - t0 < 4,
              "外部进程结束（含僵尸）就返回，带 log 末尾", t)
        ext = subprocess.Popen(["sleep", "30"])
        t, e = s.call("wait_pid", {"pid": ext.pid, "timeout_secs": 1})
        check("still_running" in t, "外部进程还在跑：timeout_secs 内返回 still_running", t)
        ext.kill()
        ext.wait()
        t, e = s.call("wait_pid", {"pid": 999999})
        check("不存在" in t, "pid 不存在", t)
        t, e = s.call("wait_pid", {"pid": "abc"})
        check(e is True, "pid 不是整数报错", t)

        print("并发与取消")
        res = {}

        def bg():
            res["t"] = s.call("run_wait", {"command": "sleep 2; echo par"}, timeout=20)
        th = threading.Thread(target=bg)
        th.start()
        time.sleep(0.3)
        t0 = time.time()
        t, e = s.call("read_files", {"files": ["a.txt"]})
        check(time.time() - t0 < 1 and "line1" in t, "run_wait 阻塞时别的调用照样回（不排队）")
        th.join()
        check("par" in res["t"][0], "并行的 run_wait 也正常结束", res)
        s.n += 1
        mid = s.n
        s.send({"jsonrpc": "2.0", "id": mid, "method": "tools/call",
                "params": {"name": "run_wait", "arguments": {"command": "sleep 3"}}})
        time.sleep(0.3)
        s.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": mid}})
        time.sleep(1)
        with s.cv:
            check(mid not in s.got, "被客户端取消的调用不再回结果")

        print("stdin 关闭时杀掉还在跑的命令")
        t, e = s.call("run_wait", {"command": "sleep 60", "timeout_secs": 120})
        pid = int(field(t, "pid"))
        s.close()
        time.sleep(0.5)
        check(s.p.returncode is not None and not alive(pid), "服务器退出，命令被杀", pid)
        multi_edit_tests()
        tools_only_tests()
        probe_tests()
        probe_claude_tests()
        review_tests()
        iface_tests()
        k32_tests()
        k34_tests()
        k38_tests()
        k47_tests()
    finally:
        s.close()
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
