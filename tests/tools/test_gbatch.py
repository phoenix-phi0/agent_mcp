# -*- coding: utf-8 -*-
"""tools/gbatch.py：提交、跑完、share 续接会话、回合被中断、失败和超时、取消。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_gbatch.py

执行端换成一个假的 grok（下面的 FAKE），不联网、不花钱。输出的 JSON
照真 grok -p --output-format json 的样子（text / stopReason / sessionId）。
"""

import json
import os
import signal
import stat
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="gbatch_"))
LOG = TMP / "calls.jsonl"

FAKE = f"""#!{sys.executable}
import json, os, sys, time, uuid
a = sys.argv[1:]
prompt = a[a.index("-p") + 1]
resume = a[a.index("-r") + 1] if "-r" in a else None
with open({str(LOG)!r}, "a", encoding="utf-8") as f:
    f.write(json.dumps({{"prompt": prompt, "resume": resume, "argv": a,
                         "cwd": os.getcwd(),
                         "leak": sorted(k for k in os.environ
                                        if k == "CLAUDECODE" or k.startswith("CLAUDE_CODE_"))}},
                       ensure_ascii=False) + "\\n")
if "SLEEP" in prompt:
    time.sleep(30)
if "BADJSON" in prompt:
    print("Error: not logged in"); sys.exit(1)
stop = "cancelled" if "ASK" in prompt else "max_tokens" if "CUT" in prompt else "end_turn"
print(json.dumps({{"text": ("我来做：" if stop == "cancelled" else "答：") + prompt
                           + ("|接着" + resume if resume else ""),
                  "stopReason": stop,
                  "sessionId": resume or "s-" + uuid.uuid4().hex[:6],
                  "num_turns": 1, "total_cost_usd": 0.01}}, indent=2))
"""

fake = TMP / "grok"
fake.write_text(FAKE, encoding="utf-8")
fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

os.environ["GBATCH_HOME"] = str(TMP / "jobs")
os.environ["GBATCH_GROK"] = str(fake)
os.environ["GROK_HOME"] = str(TMP / "grok_home")     # 不去读真的会话记录
os.environ["CLAUDECODE"] = "1"
os.environ["CLAUDE_CODE_SESSION_ID"] = "parent"

from tools import gbatch    # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"：{extra}" if extra else ""))


def calls():
    return [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines()] \
        if LOG.exists() else []


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except gbatch.GBatchError as e:
        return str(e)
    return None


def arg(c, k):
    return c["argv"][c["argv"].index(k) + 1] if k in c["argv"] else None


def main():
    print("参数检查")
    check(raises(gbatch.submit, []), "空列表报错")
    check(raises(gbatch.submit, ["x"] * 11), "超过 MAX_TASKS 报错")
    check(raises(gbatch.submit, ["x"], mode="both"), "mode 不对报错")
    check(raises(gbatch.submit, [{"no": 1}]), "字典缺 prompt 报错")
    check(raises(gbatch.status, "nope"), "查不存在的任务报错")
    check(raises(gbatch.submit, ["x"], permission_mode="bypassPermissions"),
          "不收 bypassPermissions")
    check(raises(gbatch.submit, ["x"], cwd=str(Path.home())), "不收家目录当 cwd")

    print("isolated：逐条跑完")
    j = gbatch.submit(["一", "二", {"prompt": "三", "outfile": "out/三.txt"}],
                      name="基本", cwd=str(TMP))
    d = gbatch.wait(j["job_id"], timeout=30, every=0.2)
    check(d["status"] == "done", "整批 done", d["status"])
    check([t["output"] for t in d["tasks"]] == ["答：一", "答：二", "答：三"],
          "输出按顺序", [t["output"] for t in d["tasks"]])
    check(all(t["stop_reason"] == "end_turn" and t["session_id"] for t in d["tasks"]),
          "stop_reason 和 session_id 记下来")
    check((TMP / "out" / "三.txt").read_text(encoding="utf-8") == "答：三", "outfile 写到 cwd 下")
    cs = calls()
    check(all(c["resume"] is None for c in cs), "isolated 不续接会话")
    check(all(c["cwd"] == str(TMP) for c in cs), "在指定 cwd 里跑")
    check(all(arg(c, "--output-format") == "json" for c in cs), "要 JSON 输出")
    check(all(arg(c, "--rules") == gbatch.PREAMBLE for c in cs), "环境交代走 --rules")
    check("PYTHONPATH=" in gbatch.PREAMBLE and "sys.path.insert" in gbatch.PREAMBLE,
          "--rules 含「不要加环境变量前缀」")
    check(all("--model" not in c["argv"] and "--permission-mode" not in c["argv"]
              and "--allow" not in c["argv"] and "--always-approve" not in c["argv"]
              for c in cs), "默认不带模型、不放开权限")
    check(all(not c["leak"] for c in cs), "CLAUDECODE / CLAUDE_CODE_* 没漏给子进程")

    print("share：后一条接前一条的会话，失败后断开；参数传下去")
    LOG.unlink()
    j = gbatch.submit(["甲", "乙 ASK", "丙", "丁"], mode="share", cwd=str(TMP),
                      model="grok-4.7-build-fast", permission_mode="acceptEdits",
                      allowed_tools=["Bash(git *)", "Edit"], preamble=False)
    d = gbatch.wait(j["job_id"], timeout=30, every=0.2)
    cs = calls()
    t = d["tasks"]
    check(cs[0]["resume"] is None and cs[1]["resume"] == t[0]["session_id"],
          "第二条 -r 第一条的会话", [c["resume"] for c in cs])
    check(cs[2]["resume"] is None, "前一条失败，下一条开新会话", cs[2]["resume"])
    check(cs[3]["resume"] == t[2]["session_id"], "之后接着续")
    check(all(arg(c, "--model") == "grok-4.7-build-fast"
              and arg(c, "--permission-mode") == "acceptEdits" for c in cs),
          "model、permission_mode 传下去")
    argv = cs[0]["argv"]
    check([argv[i + 1] for i, x in enumerate(argv) if x == "--allow"] == ["Bash(git *)", "Edit"],
          "allowed_tools 每条一个 --allow", argv)
    check(all("--rules" not in c["argv"] for c in cs), "preamble=False 不加交代")
    check(d["status"] == "partial", "有成有败是 partial", d["status"])

    print("回合被中断：退出码 0 也算失败")
    j = gbatch.submit(["ASK 建文件", {"prompt": "CUT", "outfile": "cut.txt"}], cwd=str(TMP))
    d = gbatch.wait(j["job_id"], timeout=30, every=0.2)
    t = d["tasks"]
    check(t[0]["status"] == "error" and "批准" in t[0]["error"]
          and t[0]["stop_reason"] == "cancelled", "stopReason=cancelled 记 error，说明原因", t[0])
    check(t[0]["output"] == "我来做：ASK 建文件", "打算做的话留在 output 里", t[0]["output"])
    check(t[1]["status"] == "error" and "max_tokens" in t[1]["error"],
          "其他非 end_turn 也记 error", t[1])
    check(not (TMP / "cut.txt").exists(), "失败的那条不写 outfile")
    check(d["status"] == "failed", "全失败是 failed", d["status"])

    print("输出不是 JSON、超时")
    j = gbatch.submit(["BADJSON", "SLEEP", "后面照跑"], cwd=str(TMP), timeout=1)
    d = gbatch.wait(j["job_id"], timeout=30, every=0.2)
    t = d["tasks"]
    check(t[0]["status"] == "error" and "not logged in" in t[0]["output"],
          "非 JSON 输出原样留着", t[0])
    check(t[1]["status"] == "timeout", "超时的那条记 timeout", t[1]["status"])
    check(t[2]["status"] == "done", "超时之后接着跑下一条", t[2]["status"])

    print("取消")
    j = gbatch.submit(["SLEEP 一", "SLEEP 二"], cwd=str(TMP))
    for _ in range(50):
        if gbatch.status(j["job_id"])["tasks"][0]["status"] == "running":
            break
        time.sleep(0.1)
    pid = gbatch.status(j["job_id"])["pid"]
    r = gbatch.cancel(j["job_id"])
    d = gbatch.status(j["job_id"])
    check(r["status"] == "cancelled" and d["status"] == "cancelled", "状态是 cancelled", d["status"])
    check({t["status"] for t in d["tasks"]} == {"cancelled"}, "没跑完的都标 cancelled")
    alive = True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        alive = False
    check(not alive, "执行器进程已经没了")
    time.sleep(1)
    check(gbatch.status(j["job_id"])["status"] == "cancelled", "执行器没有回头把状态盖掉")

    print("执行器死掉")
    j = gbatch.submit(["SLEEP"], cwd=str(TMP))
    for _ in range(50):
        if gbatch.status(j["job_id"]).get("pid"):
            break
        time.sleep(0.1)
    os.killpg(gbatch.status(j["job_id"])["pid"], signal.SIGKILL)
    time.sleep(0.3)
    check(gbatch.status(j["job_id"])["status"] == "died", "进程没了就是 died，wait 不会空等")

    print("推理强度 effort")
    def run(tasks, **k):
        LOG.unlink(missing_ok=True)
        j = gbatch.submit(tasks, cwd=str(TMP), **k)
        d = gbatch.wait(j["job_id"], timeout=30, every=0.2)
        return d, calls()
    d, cs = run(["e1"])
    check(arg(cs[0], "--reasoning-effort") == "medium", "默认 medium 进命令行")
    check(d["options"]["effort"] == "medium" and "medium" in d["tasks"][0]["cmd"],
          "options 和 task cmd 记录 effort")
    for zh, en in (("低", "low"), ("中", "medium"), ("高", "high"), ("极高", "xhigh")):
        d, cs = run(["e2"], effort=zh)
        check(arg(cs[0], "--reasoning-effort") == en, f"中文别名 {zh} → {en}")
    d, cs = run(["e3"], effort="HIGH")
    check(arg(cs[0], "--reasoning-effort") == "high", "大小写不敏感")
    for none in (None, ""):
        d, cs = run(["e4"], effort=none)
        check("--reasoning-effort" not in cs[0]["argv"] and "--reasoning-effort" not in d["tasks"][0]["cmd"]
              and d["options"]["effort"] is None, f"effort={none!r} 不传参数")
    e = raises(gbatch.submit, ["x"], cwd=str(TMP), effort="super")
    check(e and "low" in e and "xhigh" in e, "非法值报错并列出可选值", e)
    e = raises(gbatch.submit, ["x"], cwd=str(TMP), effort="xhigh", model="grok-4.5-build")
    check(e and "xhigh" in e, "grok-4.5 + xhigh 报错", e)
    e = raises(gbatch.submit, [{"prompt": "x", "effort": "xhigh"}], cwd=str(TMP), model="grok-4.5")
    check(e, "任务级 xhigh 也受 4.5 限制")
    check(gbatch._norm_effort("high", "grok-4.5-build") == "high", "grok-4.5 + high 可以")
    check(raises(gbatch.submit, [{"prompt": "x", "effort": "bad"}], cwd=str(TMP)),
          "任务级非法值报错")
    d, cs = run(["j1", {"prompt": "j2", "effort": "low"}, {"prompt": "j3", "effort": None},
                 {"prompt": "j4"}], effort="high")
    got = {c["prompt"]: arg(c, "--reasoning-effort") for c in cs}
    check(got == {"j1": "high", "j2": "low", "j3": None, "j4": "high"},
          "任务级覆盖优先于 job 级", got)
    check(arg(cs[1], "--reasoning-effort") == "low" and "low" in d["tasks"][1]["cmd"],
          "覆盖后的值记在该任务 cmd")
    check("effort" in gbatch.describe() and "low" in gbatch.describe(), "describe 有 effort 说明")
    j = {"job_id": d["id"]}          # 下面「jobs 新的在前」要用最新一个

    print("列表和概况")
    js = gbatch.jobs()
    check(len(js) >= 6 and js[0]["id"] == j["job_id"], "jobs 新的在前", [x["id"] for x in js])
    check("最近 5 个任务" in gbatch.describe(), "describe 能用")

    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
