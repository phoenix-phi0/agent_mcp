# -*- coding: utf-8 -*-
"""tools/gsb_tools_mcp.py：gsbatch 给 goose 挂的 stdio MCP 扩展。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_gsb_tools_mcp.py

真起一个服务器进程，按 goose 的方式走 JSON-RPC（一行一条）：initialize、tools/list、
read_files（多文件 / 行号范围 / 缺失 / 目录 / 二进制 / 截断 / glob）、run_wait（正常 /
非零 / 超时杀进程组 / 单次阻塞上限后 still_running）、wait_pid（自己起的 / 外部进程）、
凭证变量不进命令环境。不联网、不花钱。

review / review_wait 同样用假 codex：默认不出现、GSB_REVIEW=1 才有；参数校验、默认审工作区
diff、base、报告草稿、提示里有任务书路径和必查项、强制只读、开头的初步审查提示和「无出处」标记、
still_running 后 review_wait。
probe / probe_wait 用 PATH 上的假 codex（不联网）：默认不出现、GSB_PROBE=1 才有；
正常 / 失败 / 超时杀进程组 / still_running 后 probe_wait / 并行 wait=false + 一次等多个 /
超长截断 / 满载自动重试 / 参数校验；每次都带 -s read-only、默认 -m gpt-6-luna、
不带 --dangerously*，凭证变量进不了 codex。
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
                   MY_SECRET="x" + SECRET, HARMLESS_VAR="ok", OPENAI_API_KEY="sk-openai-" + SECRET)
        env.pop("GSB_PROBE", None)
        env.update(extra)
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


FAKE_CODEX = '#!/usr/bin/env python3\n# 假 codex：记下 argv / 环境，按提示词里的关键字表演\nimport json, os, subprocess, sys, time\nargv = sys.argv[1:]\nprompt = sys.stdin.read()\nrec = os.environ["FAKE_CODEX_REC"]\nwith open(rec, "a") as f:\n    f.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "prompt": prompt,\n                        "env_keys": sorted(os.environ),\n                        "secret_seen": any("SECRET-0123" in v or v.startswith("ghp_")\n                                           for v in os.environ.values())}) + "\\n")\nout = argv[argv.index("-o") + 1]\ntask = prompt.split("任务：")[-1]\nprint("OpenAI Codex (fake)\\nuser\\n" + prompt, flush=True)\ndef done(text, tok="1,234"):\n    open(out, "w").write(text)\n    print("codex\\n" + text + "\\ntokens used\\n" + tok, flush=True)\n    sys.exit(0)\nif "你是代码审查员" in prompt:\n    if "REVIEWSLOW" in prompt:\n        time.sleep(6)\n    done("结论：有问题\\n问题清单：\\n- [阻断] calc.py:2 — 负数没处理。依据：读了文件\\n"\n         "- [应修] README 也要更新。依据：任务书\\n- [建议] calc.py:1 — 可以加类型注解\\n"\n         "必查项：\\n(a) 漏了负数要求\\n(b) 无\\n(c) 无\\n(d) 无报告草稿\\n(e) 无", "4,321")\nif "FAIL" in task:\n    print("ERROR: something broke badly", flush=True); sys.exit(2)\nif "HANG" in task:\n    c = subprocess.Popen(["sleep", "300"])\n    open(os.environ["FAKE_CODEX_REC"] + ".child", "w").write(str(c.pid))\n    time.sleep(300)\nif "CAP" in task:\n    cnt = rec + ".cap"\n    n = int(open(cnt).read()) if os.path.exists(cnt) else 0\n    open(cnt, "w").write(str(n + 1))\n    if n == 0:\n        print("ERROR: Selected model is at capacity. Please try a different model.\\ntokens used\\n100", flush=True)\n        sys.exit(1)\n    done("capacity ok")\nif "BIG" in task:\n    done("B" * 40000)\nfor w in task.split():\n    if w.startswith("SLOW"):\n        time.sleep(float(w[4:]))\ndone("结论：" + task.strip() + "（a.txt:2）")\n'


def pid_of(text):
    m = re.search(r"probe_id：([\w-]+)", text)
    return m.group(1) if m else None


def recs(path):
    try:
        return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    except OSError:
        return []


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
        check({"probe", "probe_wait"} <= set(tools) and {"read_files", "run_wait", "wait_pid"} <= set(tools),
              "GSB_PROBE=1 时多出 probe / probe_wait，原来三个还在", list(tools))
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
        s.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        r = s.req("tools/list")
        names = [t["name"] for t in r["result"]["tools"]]
        check(names == ["read_files", "run_wait", "wait_pid"]
              and all(t["inputSchema"]["type"] == "object" for t in r["result"]["tools"]),
              "tools/list 有三个工具和 schema", names)
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
              and "GH_TOKEN" not in t and "MY_SECRET" not in t, "名字像凭证的变量不进命令环境", "")
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
        probe_tests()
        review_tests()
    finally:
        s.close()
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
