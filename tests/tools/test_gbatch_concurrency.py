# -*- coding: utf-8 -*-
"""tools/gbatch.py：concurrency 并发、stall 卡死检测。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_gbatch_concurrency.py

假 grok：提示词里 SLEEP<n> 睡 n 秒再输出；HANG 一声不吭一直睡（模拟等批准）；
HANGSESS 先在 GROK_HOME/sessions 下写一份带被拒调用的 updates.jsonl 再挂住；
TICK 每秒往 stderr 写一点、睡 4 秒后正常结束（有动静就不该被当成卡死）。
"""

import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="gbatch_cc_"))
GH = TMP / "grok_home"

FAKE = f"""#!{sys.executable}
import json, os, re, sys, time, uuid
a = sys.argv[1:]
p = a[a.index("-p") + 1]
sid = "s-" + uuid.uuid4().hex[:6]
if "HANGSESS" in p:
    d = os.path.join({str(GH)!r}, "sessions", "proj", sid)
    os.makedirs(d)
    with open(os.path.join(d, "updates.jsonl"), "w") as f:
        for u in ({{"sessionUpdate": "tool_call", "toolCallId": "c1", "title": "write",
                    "rawInput": {{"file_path": "/tmp/x.py"}}}},
                  {{"sessionUpdate": "tool_call_update", "toolCallId": "c1",
                    "status": "failed", "content": "User cancelled the execution"}}):
            f.write(json.dumps({{"params": {{"update": u}}}}) + "\\n")
    time.sleep(120)
if "HANG" in p:
    time.sleep(120)
if "TICK" in p:
    for _ in range(4):
        sys.stderr.write("."); sys.stderr.flush(); time.sleep(1)
m = re.search(r"SLEEP(\\d+)", p)
if m:
    time.sleep(int(m.group(1)))
print(json.dumps({{"text": "ok " + p, "stopReason": "end_turn", "sessionId": sid,
                  "num_turns": 1, "total_cost_usd": 0}}))
"""
fake = TMP / "grok"
fake.write_text(FAKE, encoding="utf-8")
fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

os.environ["GBATCH_HOME"] = str(TMP / "jobs")
os.environ["GBATCH_GROK"] = str(fake)
os.environ["GROK_HOME"] = str(GH)
(GH / "sessions").mkdir(parents=True)

from tools import gbatch    # noqa: E402

PASS = FAIL = 0


def check(name, ok, extra=""):
    global PASS, FAIL
    PASS += bool(ok)
    FAIL += not ok
    print(("  ✓ " if ok else "  ✗ ") + name + ("" if ok else f"  {extra}"))


def run(tasks, **kw):
    t0 = time.time()
    j = gbatch.submit(tasks, cwd=str(TMP), preamble=False, **kw)
    d = gbatch.wait(j["job_id"], timeout=90, every=0.2)
    return d, time.time() - t0


print("参数")
for bad in (0, 11, "x"):
    try:
        gbatch.submit(["a"], cwd=str(TMP), concurrency=bad)
        check(f"concurrency={bad!r} 报错", False)
    except gbatch.GBatchError:
        check(f"concurrency={bad!r} 报错", True)
try:
    gbatch.submit(["a"], cwd=str(TMP), stall=-1)
    check("stall=-1 报错", False)
except gbatch.GBatchError:
    check("stall=-1 报错", True)
check("describe 里写了 concurrency 和 stall",
      "concurrency" in gbatch.describe() and "stall" in gbatch.describe())

print("并发")
d, s = run(["SLEEP2 a", "SLEEP2 b", "SLEEP2 c"], concurrency=3)
check("3 条都 done", [t["status"] for t in d["tasks"]] == ["done"] * 3, d["tasks"])
check(f"concurrency=3 约 2 秒跑完（{s:.1f}s）", s < 4.5, s)
check("options 里记了 concurrency", d["options"]["concurrency"] == 3)
d, s = run(["SLEEP2 a", "SLEEP2 b", "SLEEP2 c"])
check(f"默认 concurrency=1 顺序跑（{s:.1f}s）", s >= 6, s)
d, s = run(["SLEEP2 a", "SLEEP2 b", "SLEEP2 c"], mode="share", concurrency=3)
check(f"share 模式忽略 concurrency，顺序跑（{s:.1f}s）", s >= 6, s)
check("share 续接了会话", "-r" in d["tasks"][1]["cmd"], d["tasks"][1]["cmd"])

print("卡死检测")
d, s = run(["HANG"], stall=2, timeout=60)
t = d["tasks"][0]
check(f"静默挂住在 stall 时被杀，不等 timeout（{s:.1f}s）", t["status"] == "stalled" and s < 10,
      (t["status"], s))
check("error 说明多半在等批准", "批准" in t["error"], t["error"])
check("任务整体 failed", d["status"] == "failed", d["status"])

d, s = run(["HANGSESS"], stall=2, timeout=60)
t = d["tasks"][0]
check("stalled 时从会话记录报出卡住的调用",
      t["status"] == "stalled" and "Edit /tmp/x.py" in t["error"]
      and t.get("pending") and t["session_id"], t)

d, s = run(["TICK"], stall=2, timeout=60)
check("一直有输出就不算卡死", d["tasks"][0]["status"] == "done", d["tasks"][0])

d, s = run(["HANG"], stall=0, timeout=3)
check(f"stall=0 不检测，照旧走硬超时（{s:.1f}s）",
      d["tasks"][0]["status"] == "timeout" and 3 <= s < 10, (d["tasks"][0], s))

d, s = run(["HANG", "SLEEP1 b"], stall=2, timeout=60, concurrency=2)
check("并发时卡住一条不拖累另一条",
      [t["status"] for t in d["tasks"]] == ["stalled", "done"], d["tasks"])

print("取消（并发中）")
j = gbatch.submit(["HANG a", "HANG b", "HANG c"], cwd=str(TMP), preamble=False,
                  concurrency=3, stall=0, timeout=60)
for _ in range(50):
    d = gbatch.status(j["job_id"])
    if sum(t["status"] == "running" for t in d["tasks"]) == 3:
        break
    time.sleep(0.2)
time.sleep(0.5)
gbatch.cancel(j["job_id"])
time.sleep(1)
d = gbatch.status(j["job_id"])
check("取消后状态 cancelled", d["status"] == "cancelled"
      and all(t["status"] == "cancelled" for t in d["tasks"]), d["tasks"])
left = [l for l in os.popen("ps -eo args").read().splitlines()
        if l.startswith(sys.executable) and str(fake) in l]
check("假 grok 进程都被杀掉", not left, left)

print(f"通过 {PASS}，失败 {FAIL}")
sys.exit(1 if FAIL else 0)
