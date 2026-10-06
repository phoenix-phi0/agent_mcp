# -*- coding: utf-8 -*-
"""tools/gbatch.py 的权限部分：acceptEdits 补 Edit、工具名翻译、原始输出
落盘、被中断时说出卡在哪个调用、submit 的预检提示。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_gbatch_perm.py

执行端是假的 grok（FAKE），不联网。被中断的那种照真 grok 的样子：json
输出里只有 stopReason=cancelled，卡住的调用写在 $GROK_HOME/sessions/
<编码后的 cwd>/<sessionId>/updates.jsonl。
"""

import json
import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="gbatch_perm_"))
LOG = TMP / "calls.jsonl"
GHOME = TMP / "grok_home"

FAKE = f"""#!{sys.executable}
import json, os, sys, uuid, urllib.parse
a = sys.argv[1:]
prompt = a[a.index("-p") + 1]
with open({str(LOG)!r}, "a", encoding="utf-8") as f:
    f.write(json.dumps({{"prompt": prompt, "argv": a}}, ensure_ascii=False) + "\\n")
sid = "s-" + uuid.uuid4().hex[:8]
sys.stderr.write("stderr-line from fake grok\\n")
out = {{"text": "答：" + prompt, "stopReason": "end_turn", "sessionId": sid,
        "num_turns": 1, "total_cost_usd": 0.01}}
if "ASK" in prompt:
    out.update(text="我来写 /tmp/x.py 再跑它", stopReason="cancelled")
if "ASKSESSION" in prompt:
    d = os.path.join(os.environ["GROK_HOME"], "sessions",
                     urllib.parse.quote(os.getcwd(), safe=""), sid)
    os.makedirs(d)
    def upd(u):
        return json.dumps({{"method": "session/update",
                           "params": {{"sessionId": sid, "update": u}}}}, ensure_ascii=False)
    lines = [
        upd({{"sessionUpdate": "agent_message_chunk", "content": {{"type": "text", "text": "x"}}}}),
        upd({{"sessionUpdate": "tool_call", "toolCallId": "c0", "title": "write",
             "rawInput": {{"file_path": "/tmp/x.py", "content": "print('hi')"}}}}),
        upd({{"sessionUpdate": "tool_call", "toolCallId": "c1", "title": "run_terminal_command",
             "rawInput": {{"command": "python3 /tmp/x.py"}}}}),
        upd({{"sessionUpdate": "tool_call_update", "toolCallId": "c0", "status": "failed",
             "content": [{{"type": "content", "content": {{"type": "text",
                         "text": "User cancelled the execution for tool `write`"}}}}]}}),
        upd({{"sessionUpdate": "tool_call_update", "toolCallId": "c1", "status": "failed",
             "content": [{{"type": "content", "content": {{"type": "text",
                         "text": "Tool execution cancelled due to earlier user cancellation"}}}}]}}),
    ]
    if "SHELL" in prompt:
        lines = [
            upd({{"sessionUpdate": "tool_call", "toolCallId": "c0", "title": "run_terminal_command",
                 "rawInput": {{"command": "mkdir -p d && printf x > d/a.py && python3 d/a.py"}}}}),
            upd({{"sessionUpdate": "tool_call_update", "toolCallId": "c0", "status": "failed",
                 "content": [{{"type": "content", "content": {{"type": "text",
                             "text": "User cancelled the execution for tool `run_terminal_command`"}}}}]}}),
        ]
    open(os.path.join(d, "updates.jsonl"), "w", encoding="utf-8").write("\\n".join(lines) + "\\n")
if "ASKJSON" in prompt:
    out["permission_denials"] = [{{"tool_name": "search_replace",
                                   "tool_input": {{"file_path": "/tmp/y.py"}}}}]
print(json.dumps(out, ensure_ascii=False, indent=2))
"""

fake = TMP / "grok"
fake.write_text(FAKE, encoding="utf-8")
fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

os.environ["GBATCH_HOME"] = str(TMP / "jobs")
os.environ["GBATCH_GROK"] = str(fake)
os.environ["GROK_HOME"] = str(GHOME)

from tools import gbatch    # noqa: E402

PASS = FAIL = 0
WD = TMP / "wd"
WD.mkdir()


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"：{extra}" if extra else ""))


def calls():
    out = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines()] \
        if LOG.exists() else []
    if LOG.exists():
        LOG.unlink()
    return out


def allows(c):
    a = c["argv"]
    return [a[i + 1] for i, x in enumerate(a) if x == "--allow"]


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except gbatch.GBatchError as e:
        return str(e)
    return None


def run(tasks, **k):
    j = gbatch.submit(tasks, cwd=str(WD), **k)
    return j, gbatch.wait(j["job_id"], timeout=30, every=0.2)


def main():
    print("acceptEdits 自动补 --allow Edit")
    j, d = run(["只读一下"], permission_mode="acceptEdits")
    c = calls()[0]
    check(allows(c) == ["Edit"], "单传 acceptEdits 也带 --allow Edit", allows(c))
    check(c["argv"][c["argv"].index("--permission-mode") + 1] == "acceptEdits",
          "permission_mode 照样传下去")
    check(j["allow"] == ["Edit"] and d["options"]["allow"] == ["Edit"],
          "返回值和 job.json 里有最终规则", j["allow"])
    run(["x"], permission_mode="acceptEdits", allowed_tools=["Write", "Bash"])
    check(allows(calls()[0]) == ["Edit", "Bash"], "已有 Edit（Write 翻过来的）不重复补")
    run(["x"], permission_mode="dontAsk")
    check(allows(calls()[0]) == [], "dontAsk 不补规则")

    print("工具名翻译、去重、认不出的记 warning")
    j, d = run(["x"], allowed_tools=["Glob", "Write", "MultiEdit", "NotebookEdit", "LS",
                                     "Read", "Bash(git *)", "Bash(git *)", "grep",
                                     "mcp__srv__t", "Edit(src/**)", "Task", "Agent(x)"])
    want = ["Grep", "Edit", "Read", "Bash(git *)", "mcp__srv__t", "Edit(src/**)"]
    got = allows(calls()[0])
    check(got == want, "Glob→Grep、Write/MultiEdit/NotebookEdit→Edit、LS→Read，"
          "带括号原样、去重", got)
    w = j["warnings"]
    check(any("'Task'" in x for x in w) and any("'Agent(x)'" in x for x in w),
          "Task、Agent(x) 进 warnings", w)
    check(d["warnings"] == w, "warnings 也写进 job.json")
    check(raises(gbatch.submit, ["x"], cwd=str(WD), allowed_tools=["*"]), "不收 \"*\"")
    check(raises(gbatch.submit, ["x"], cwd=str(WD), permission_mode="yolo"),
          "不认识的 permission_mode 报错")
    check(raises(gbatch.submit, ["x"], cwd=str(WD), permission_mode="bypassPermissions"),
          "照样不收 bypassPermissions")

    print("原始输出落盘、命令行记录、不漏密钥")
    secret = "xai-" + "A1b2C3d4E5f6G7h8"
    j, d = run([f"用 api_key=SUPERSECRET42 和 {secret} 调一下"], allowed_tools=["Read"])
    jd = Path(j["dir"])
    raw = (jd / "task_1.raw.json").read_text(encoding="utf-8")
    check(json.loads(raw)["stopReason"] == "end_turn", "task_1.raw.json 是 grok 的原始 json")
    check("stderr-line" in (jd / "task_1.stderr.log").read_text(encoding="utf-8"),
          "task_1.stderr.log 存了 stderr")
    t = d["tasks"][0]
    check(t["cmd"] and t["cmd"][0] == str(fake) and "--allow" in t["cmd"],
          "tasks[0].cmd 是实际的 argv", t["cmd"])
    check(d["cmd"] and "<提示词>" in d["cmd"], "job.json 顶层 cmd 有命令样子", d["cmd"])
    # prompt / output 字段本来就是调用方给的原文，这里只管命令行
    text = json.dumps([d["cmd"], t["cmd"]], ensure_ascii=False)
    check("SUPERSECRET42" not in text and secret not in text and "xai-***" in text,
          "cmd 里密钥打了码", text[:300])
    rules = t["cmd"][t["cmd"].index("--rules") + 1]
    check(len(rules) < 100 and "共" in rules, "--rules 的长文本截短", rules)

    print("被中断：说出卡在哪个调用，hint 给参数")
    j, d = run(["ASKSESSION 写 /tmp/x.py 并运行"], allowed_tools=["Read"])
    t = d["tasks"][0]
    check(t["status"] == "error" and "需要批准：Edit /tmp/x.py" in t["error"],
          "error 里有被拒的工具和参数", t["error"])
    check("Bash python3 /tmp/x.py" in t["error"], "连带没执行的也列出", t["error"])
    check([c["tool"] for c in t.get("pending", [])] == ["Edit", "Bash"], "pending 字段",
          t.get("pending"))
    check("hint" in d and "'Edit'" in d["hint"] and "'Bash'" in d["hint"]
          and "'Read'" in d["hint"], "status/wait 的 hint 给出建议的 allowed_tools",
          d.get("hint"))
    check("hint" in gbatch.status(j["job_id"]), "status 也带 hint")

    j, d = run(["ASKSESSION SHELL 建 a.py 跑一下"], permission_mode="acceptEdits",
               allowed_tools=["Bash"])
    check("需要批准：Bash mkdir -p d" in d["tasks"][0]["error"], "被拦的命令写进 error",
          d["tasks"][0]["error"])
    check("重定向" in d.get("hint", ""), "规则都给了还被拦：hint 说是重定向/串联的问题",
          d.get("hint"))

    j, d = run(["ASKJSON 改 y.py"])
    t = d["tasks"][0]
    check("需要批准：Edit /tmp/y.py" in t["error"], "json 里给了被拒列表也能用", t["error"])

    j, d = run(["ASK 改个文件"])
    t = d["tasks"][0]
    check("拿不到" in t["error"] and "批准" in t["error"], "没有记录时说明拿不到", t["error"])
    check("['Edit', 'Bash']" in d.get("hint", ""), "不知道卡在哪时 hint 给常见的", d.get("hint"))

    j, d = run(["只读一下"])
    check("hint" not in d, "成功的任务没有 hint")

    print("submit 预检")
    j, _ = run(["创建 hello.py 并运行它，汇报输出"])
    w = j["warnings"]
    check(any("写文件" in x for x in w) and any("跑命令" in x for x in w),
          "要写要跑、没放行：两条 warning", w)
    j, _ = run(["写 a.py 然后 run pytest"], permission_mode="acceptEdits",
               allowed_tools=["Bash(pytest *)"])
    check(j["warnings"] == [], "放行了就不提示", j["warnings"])
    j, _ = run(["读 tools/gbatch.py，总结它做什么，写清楚结论"])
    check(j["warnings"] == [], "只读的不误报", j["warnings"])
    j, _ = run(["modify a.py"], allowed_tools=["Bash"])
    check(any("写文件" in x for x in j["warnings"]), "只给 Bash 不算放行编辑（会用 write 工具）",
          j["warnings"])

    print("describe")
    s = gbatch.describe()
    check("acceptEdits" in s and "Glob" in s and "→ Grep" in s and "LS" in s,
          "列出权限用法和工具名映射", s[-400:])

    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
