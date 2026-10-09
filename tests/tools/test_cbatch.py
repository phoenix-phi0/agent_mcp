# -*- coding: utf-8 -*-
"""tools/cbatch.py：提交、跑完、share 续接会话、失败和超时、取消。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_cbatch.py

执行端换成一个假的 claude（下面的 FAKE），不联网、不花钱。它按提示词
里的暗号决定怎么表现，并把收到的参数和环境记进日志，测试再对着日志查。
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

TMP = Path(tempfile.mkdtemp(prefix="cbatch_"))
LOG = TMP / "calls.jsonl"

FAKE = f"""#!{sys.executable}
import json, os, sys, time, uuid
a = sys.argv[1:]
prompt = a[a.index("-p") + 1]
resume = a[a.index("--resume") + 1] if "--resume" in a else None
with open({str(LOG)!r}, "a", encoding="utf-8") as f:
    f.write(json.dumps({{"prompt": prompt, "resume": resume, "argv": a,
                         "cwd": os.getcwd(),
                         "leak": sorted(k for k in os.environ
                                        if k == "CLAUDECODE" or k.startswith("CLAUDE_CODE_"))}},
                       ensure_ascii=False) + "\\n")
if "--system-prompt" in a and "分流" in a[a.index("--system-prompt") + 1]:
    # engine=auto 的短分类：按任务里的暗号给 route。RT_JUNK 输出不是 JSON，RT_SLEEP 睡到超时
    task = prompt.split("【任务】")[-1]
    if "RT_SLEEP" in task:
        time.sleep(30)
    if "RT_JUNK" in task:
        out = "这个嘛，看情况"
    else:
        route = "dsl_task" if "RT_TASK" in task or "RT_NEEDS" in task else "dsl_bugfix" if "RT_BUG" in task else "claude"
        out = json.dumps({{"route": route, "needs": ["要装 openpyxl"] if "RT_NEEDS" in task else [],
                          "reason": "因为" + route}}, ensure_ascii=False)
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": False,
                      "result": out, "session_id": "route", "total_cost_usd": 0.001}}))
    sys.exit(0)
if "NAP" in prompt:
    t0 = time.time(); time.sleep(1)
    with open({str(TMP / "nap.jsonl")!r}, "a") as f:
        f.write(json.dumps({{"who": "claude", "p": prompt[:20], "t0": t0, "t1": time.time()}}) + "\\n")
if "--tools" in a:
    # 难度评估：按每条任务里的暗号分模型。JUNK 让输出不是 JSON，GAP 让那条缺席
    if "JUNK" in prompt:
        out = "我觉得都挺难的"
    else:
        picks = []
        for i, sec in enumerate(prompt.split("### 任务 ")[1:], 1):
            if "GAP" in sec:
                continue
            m = "hard" if "HARD" in sec else "easy" if "EASY" in sec else "normal"
            picks.append({{"i": i, "tier": m, "reason": "因为" + m}})
        out = "```json\\n" + json.dumps(picks) + "\\n```"
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": False,
                      "result": out, "session_id": "judge", "total_cost_usd": 0.002}}))
    sys.exit(0)
if "SLEEP" in prompt:
    time.sleep(30)
if "BADJSON" in prompt:
    print("Error: not logged in"); sys.exit(1)
err = "FAIL" in prompt
print(json.dumps({{"type": "result", "subtype": "error_during_execution" if err else "success",
                  "is_error": err, "result": "答：" + prompt + ("|接着" + resume if resume else ""),
                  "session_id": "s-" + uuid.uuid4().hex[:6], "total_cost_usd": 0.01,
                  "num_turns": 1,
                  "permission_denials": [{{"tool_name": "Write"}}] if "DENY" in prompt else []}}))
"""

fake = TMP / "claude"
fake.write_text(FAKE, encoding="utf-8")
fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

# 假的 dsl 执行器（engine=dsl/auto 时 cbatch 起它，代替 python -m tools.dslagent）：
# 按任务文本里的暗号写 result.json——DSLOK 修好，DSLNO 没修好（带交接说明），DSLCRASH 什么都不写就退出。
DSL_LOG = TMP / "dsl_calls.jsonl"
FAKE_DSL = f"""import json, os, sys
from pathlib import Path
a = sys.argv[1:]
arg = lambda k: a[a.index(k) + 1] if k in a else None
task = Path(arg("--task-file")).read_text(encoding="utf-8")
with open({str(DSL_LOG)!r}, "a", encoding="utf-8") as f:
    f.write(json.dumps({{"argv": a, "task": task, "planner": os.environ.get("DSLAGENT_PLANNER"),
                       "plan_model": os.environ.get("DSLAGENT_PLAN_MODEL")}},
                       ensure_ascii=False) + "\\n")
if "DSLCRASH" in task:
    print("炸了"); sys.exit(3)
if "DSLNAP" in task:
    import time
    t0 = time.time(); time.sleep(1.2)
    with open({str(TMP / "nap.jsonl")!r}, "a") as f:
        f.write(json.dumps({{"who": "dsl", "p": arg("--project"), "t0": t0, "t1": time.time()}}) + "\\n")
out = Path(arg("--out"))
ok = "DSLOK" in task or "DSLNAP" in task
kind = "task" if "DSLTASK" in task else "bugfix"
eu = "plan_task" if kind == "task" else "template" if ok else "plan"
json.dump({{"fixed": ok, "kind": kind, "engine_used": eu, "versions": 1 if ok else 3,
           "calls": 2 if ok else 9, "cost": 0.03, "seconds": 5, "stop": "" if ok else "3 版都没修好",
           "handoff": "HANDOFF-NOTE 定位到 a.py", "report": "DSL 报告" + ("修好" if ok else "没修好"),
           "calls_log": str(out / "calls.json"), "dir": str(out), "test_cmd": arg("--test-cmd") or "python3 -m unittest",
           "early_exit": "计划自报缺能力：要装 openpyxl" if "DSLEARLY" in task else None}},
          open(out / "result.json", "w"), ensure_ascii=False)
"""
fake_dsl = TMP / "fake_dsl.py"
fake_dsl.write_text(FAKE_DSL, encoding="utf-8")

os.environ["CBATCH_HOME"] = str(TMP / "jobs")
os.environ["CBATCH_CLAUDE"] = str(fake)
# 模拟在 Claude Code 会话里调用：这些不该漏给子进程
os.environ["CLAUDECODE"] = "1"
os.environ["CLAUDE_CODE_SESSION_ID"] = "parent"

from tools import cbatch    # noqa: E402

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


def tools_of(c):
    """--allowed-tools 后面跟的那一串（到下一个 -- 参数为止）。"""
    a = c["argv"]
    if "--allowed-tools" not in a:
        return []
    out = []
    for x in a[a.index("--allowed-tools") + 1:]:
        if x.startswith("--"):
            break
        out.append(x)
    return out


def default_tools_ok(ts, test_cmd=None):
    """默认放行：能读写、能跑 python/测试和只读命令；没有任意 Bash、装包、联网、删除、git 提交推送。"""
    need = {"Read", "Edit", "Write", "Grep", "Glob", "Bash(python3:*)", "Bash(python:*)", "Bash(pytest:*)",
            "Bash(python3 -m pytest:*)", "Bash(python3 -m unittest:*)", "Bash(ls:*)", "Bash(cat:*)",
            "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(diff:*)", "Bash(git diff:*)", "Bash(git status:*)"}
    if test_cmd:
        need.add(f"Bash({test_cmd}*)")
    bad = [x for x in ts if x in ("Bash", "Bash(*)", "Bash(:*)", "*")
           or any(w in x for w in ("pip", "npm", "curl", "wget", "rm ", "rm:", "git push", "git commit",
                                   "systemctl", "sudo"))]
    return need <= set(ts) and not bad


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except cbatch.CBatchError as e:
        return str(e)
    return None


def main():
    print("参数检查")
    check(raises(cbatch.submit, []), "空列表报错")
    check(raises(cbatch.submit, ["x"] * 11), "超过 MAX_TASKS 报错")
    check(raises(cbatch.submit, ["x"], mode="both"), "mode 不对报错")
    check(raises(cbatch.submit, [{"no": 1}]), "字典缺 prompt 报错")
    check(raises(cbatch.status, "nope"), "查不存在的任务报错")
    check(raises(cbatch.submit, ["x"], permission_mode="bypassPermissions"),
          "不收 bypassPermissions")

    print("isolated：逐条跑完")
    j = cbatch.submit(["一", "二", {"prompt": "三", "outfile": "out/三.txt"}],
                      name="基本", cwd=str(TMP), model="sonnet")
    d = cbatch.wait(j["job_id"], timeout=30, every=0.2)
    check(d["status"] == "done", "整批 done", d["status"])
    check([t["output"] for t in d["tasks"]] == ["答：一", "答：二", "答：三"],
          "输出按顺序", [t["output"] for t in d["tasks"]])
    check(d["progress"] == "3/3", "progress 3/3", d.get("progress"))
    check((TMP / "out" / "三.txt").read_text(encoding="utf-8") == "答：三", "outfile 写到 cwd 下")
    cs = calls()
    check(all(c["resume"] is None for c in cs), "isolated 不续接会话")
    check(all(c["cwd"] == str(TMP) for c in cs), "在指定 cwd 里跑")
    check(all("--model" in c["argv"] and "--append-system-prompt" in c["argv"] for c in cs),
          "带上 --model 和环境交代")
    pre = cs[0]["argv"][cs[0]["argv"].index("--append-system-prompt") + 1]
    check("前台跑完" in pre and "不得放到后台" in pre and "轮询" in pre, "交代里有「前台跑完、不得放后台、前台轮询」", pre)
    check(all("--permission-mode" not in c["argv"] for c in cs), "默认不放开权限")
    check(all(not c["leak"] for c in cs), "CLAUDECODE / CLAUDE_CODE_* 没漏给子进程",
          cs[0]["leak"])

    print("share：后一条接前一条的会话，失败后断开")
    LOG.unlink()
    j = cbatch.submit(["甲", "乙 FAIL", "丙", "丁 DENY"], mode="share", cwd=str(TMP),
                      permission_mode="acceptEdits", preamble=False)
    d = cbatch.wait(j["job_id"], timeout=30, every=0.2)
    cs = calls()
    t = d["tasks"]
    check(cs[0]["resume"] is None and cs[1]["resume"] == t[0]["session_id"],
          "第二条 --resume 第一条的会话")
    check(cs[2]["resume"] is None, "前一条失败，下一条开新会话", cs[2]["resume"])
    check(cs[3]["resume"] == t[2]["session_id"], "之后接着续")
    check(t[1]["status"] == "error" and "error_during_execution" in t[1]["error"],
          "is_error 记成 error", t[1])
    check(t[3].get("denied") == ["Write"], "被拒的工具记在 denied", t[3])
    check(all(c["argv"][c["argv"].index("--model") + 1] == "sonnet" for c in cs),
          "不传 model 默认用 sonnet")
    check(d["status"] == "partial", "有成有败是 partial", d["status"])
    check(all(c["argv"][c["argv"].index("--permission-mode") + 1] == "acceptEdits"
              and "--append-system-prompt" not in c["argv"] for c in cs),
          "permission_mode 传下去，preamble=False 不加交代")

    print("输出不是 JSON、超时")
    j = cbatch.submit(["BADJSON", "SLEEP", "后面照跑"], cwd=str(TMP), timeout=1, model=None)
    d = cbatch.wait(j["job_id"], timeout=30, every=0.2)
    t = d["tasks"]
    check(t[0]["status"] == "error" and "not logged in" in t[0]["output"],
          "非 JSON 输出原样留着", t[0])
    check(t[1]["status"] == "timeout", "超时的那条记 timeout", t[1]["status"])
    check(t[2]["status"] == "done", "超时之后接着跑下一条", t[2]["status"])
    check(all("--model" not in c["argv"] for c in calls()[-3:]),
          "model=None 不带 --model")

    print("取消")
    j = cbatch.submit(["SLEEP 一", "SLEEP 二"], cwd=str(TMP))
    for _ in range(50):
        if cbatch.status(j["job_id"])["tasks"][0]["status"] == "running":
            break
        time.sleep(0.1)
    pid = cbatch.status(j["job_id"])["pid"]
    r = cbatch.cancel(j["job_id"])
    d = cbatch.status(j["job_id"])
    check(r["status"] == "cancelled" and d["status"] == "cancelled", "状态是 cancelled", d["status"])
    check({t["status"] for t in d["tasks"]} == {"cancelled"}, "没跑完的都标 cancelled")
    alive = True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        alive = False
    check(not alive, "执行器进程已经没了")
    time.sleep(1)
    check(cbatch.status(j["job_id"])["status"] == "cancelled", "执行器没有回头把状态盖掉")

    print("执行器死掉")
    j = cbatch.submit(["SLEEP"], cwd=str(TMP))
    for _ in range(50):
        if cbatch.status(j["job_id"]).get("pid"):
            break
        time.sleep(0.1)
    import signal
    os.killpg(cbatch.status(j["job_id"])["pid"], signal.SIGKILL)
    time.sleep(0.3)
    check(cbatch.status(j["job_id"])["status"] == "died", "进程没了就是 died，wait 不会空等")

    print("model=auto：sonnet 低 effort 评估后分档")
    LOG.unlink()
    j = cbatch.submit(["EASY 跑命令", "HARD 重构", "普通活"], cwd=str(TMP), model="auto")
    d = cbatch.wait(j["job_id"], timeout=30, every=0.2)
    cs = calls()
    judge = [c for c in cs if "--tools" in c["argv"]]
    runs = [c for c in cs if "--tools" not in c["argv"]]
    arg = lambda c, k: c["argv"][c["argv"].index(k) + 1] if k in c["argv"] else None  # noqa: E731
    check(len(judge) == 1 and arg(judge[0], "--model") == "sonnet"
          and arg(judge[0], "--effort") == "low",
          "整批只评估一次，用 sonnet 低 effort", judge[0]["argv"] if judge else len(judge))
    check(arg(judge[0], "--tools") == "" and "--strict-mcp-config" in judge[0]["argv"],
          "评估时不开工具、不连 MCP")
    check(judge[0]["cwd"] != str(TMP), "评估不在任务 cwd 里跑", judge[0]["cwd"])
    check([(arg(c, "--model"), arg(c, "--effort")) for c in runs]
          == [("sonnet", "low"), ("opus", None), ("sonnet", None)],
          "easy→sonnet+low、hard→opus、normal→sonnet 不带 effort",
          [(arg(c, "--model"), arg(c, "--effort")) for c in runs])
    check([(t["model"], t["effort"]) for t in d["tasks"]]
          == [("sonnet", "low"), ("opus", None), ("sonnet", None)]
          and d["tasks"][1]["model_reason"] == "hard：因为hard", "档和理由记在任务里",
          [(t["model"], t["effort"], t["model_reason"]) for t in d["tasks"]])
    check(d["auto"]["ok"] and d["auto"]["cost_usd"] == 0.002, "评估结果记在 auto 里", d["auto"])
    check(d["status"] == "done", "整批 done", d["status"])

    LOG.unlink()
    j = cbatch.submit(["HARD", "GAP"], cwd=str(TMP), model="auto")
    d = cbatch.wait(j["job_id"], timeout=30, every=0.2)
    check([t["model"] for t in d["tasks"]] == ["opus", "sonnet"]
          and not d["auto"]["ok"] and "2" in d["auto"]["error"],
          "缺的那条退回 sonnet，并记下原因", (d["tasks"], d["auto"]))

    LOG.unlink()
    j = cbatch.submit(["HARD JUNK", "EASY"], cwd=str(TMP), model="auto")
    d = cbatch.wait(j["job_id"], timeout=30, every=0.2)
    check({t["model"] for t in d["tasks"]} == {"sonnet"} and "解析不了" in d["auto"]["error"],
          "评估输出坏了整批退回 sonnet", d["auto"])
    check(d["status"] == "done", "评估失败不影响任务照跑", d["status"])

    print("列表和概况")
    js = cbatch.jobs()
    check(len(js) == 8 and js[0]["id"] == j["job_id"], "jobs 新的在前", [x["id"] for x in js])
    check("最近 5 个任务" in cbatch.describe(), "describe 能用")

    print("engine：参数检查")
    proj = TMP / "proj"
    (proj / "tests").mkdir(parents=True)
    (proj / "calc.py").write_text("def total(xs):\n    return sum(xs) - 1\n", encoding="utf-8")
    (proj / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "tests" / "test_calc.py").write_text(
        "import unittest\nfrom calc import total\n\n\nclass T(unittest.TestCase):\n"
        "    def test_total(self):\n        self.assertEqual(total([1, 2]), 3)\n", encoding="utf-8")
    check(raises(cbatch.submit, ["x"], engine="grok"), "engine 不认识报错")
    check(raises(cbatch.submit, [{"prompt": "x", "engine": "fast"}]), "单条 engine 不认识报错")
    check("project" in (raises(cbatch.submit, ["x"], engine="dsl") or ""), "dsl 缺 project 报错")
    check("project" in (raises(cbatch.submit, [{"prompt": "x", "engine": "dsl"}]) or ""), "单条 dsl 缺 project 报错")
    check(raises(cbatch.submit, ["x"], engine="dsl", project=str(Path.home())), "project 是家目录报错")
    check(raises(cbatch.submit, ["x"], engine="dsl", project=str(TMP / "nope")), "project 不存在报错")

    print("engine：dsl 修好 / 没修好交 claude 兜底 / 不兜底 / 执行器崩了；claude 任务不受影响")
    os.environ["CBATCH_DSL"] = f"{sys.executable} {fake_dsl}"
    LOG.unlink()
    j = cbatch.submit([{"prompt": "DSLOK 修 total", "engine": "dsl", "project": str(proj)},
                       {"prompt": "DSLNO 修 total", "engine": "dsl", "project": str(proj),
                        "test_cmd": "python3 -m unittest discover -s tests"},
                       {"prompt": "DSLNO 不兜底", "engine": "dsl", "project": str(proj), "fallback": False},
                       {"prompt": "DSLCRASH", "engine": "dsl", "project": str(proj)},
                       "普通 claude 任务"], cwd=str(TMP), model="sonnet")
    d = cbatch.wait(j["job_id"], timeout=60, every=0.2)
    t = d["tasks"]
    cs = calls()
    check(t[0]["status"] == "done" and t[0]["engine_used"] == "template" and t[0]["versions"] == 1
          and t[0]["calls"] == 2 and t[0]["cost_usd"] == 0.03 and t[0]["calls_log"].endswith("task_1/calls.json")
          and t[0]["output"] == "DSL 报告修好", "dsl 修好：engine_used/versions/calls/cost/calls_log 都记下", t[0])
    fb = [c for c in cs if "DSLNO 修 total" in c["prompt"]]
    check(len(fb) == 1 and "HANDOFF-NOTE" in fb[0]["prompt"] and "python3 -m unittest discover -s tests" in fb[0]["prompt"],
          "没修好交 claude：提示词带上 dsl 的交接说明和测试命令", fb[0]["prompt"][-300:] if fb else cs)
    arg = lambda c, k: c["argv"][c["argv"].index(k) + 1] if k in c["argv"] else None  # noqa: E731
    check(fb and fb[0]["cwd"] == str(proj) and arg(fb[0], "--permission-mode") == "acceptEdits"
          and "Bash(python3 -m unittest discover -s tests*)" in fb[0]["argv"],
          "兜底在 project 里跑，默认 acceptEdits + 测试命令", fb[0]["argv"] if fb else "")
    check(fb and default_tools_ok(tools_of(fb[0]), "python3 -m unittest discover -s tests"),
          "兜底默认放行：python/pytest/unittest、只读命令；不含任意 Bash/pip/curl/git push", tools_of(fb[0]) if fb else "")
    check(fb and "可以运行项目里的 Python" in fb[0]["prompt"] and "不要改项目以外的文件" in fb[0]["prompt"],
          "兜底提示词说明可跑 Python 验证、不改项目外文件", fb[0]["prompt"][-400:] if fb else "")
    check(t[1]["engine_used"] == "claude_fallback" and t[1]["status"] == "done" and t[1]["cost_usd"] == 0.04
          and t[1]["versions"] == 3 and "DSL 报告没修好" in t[1]["output"],
          "兜底的那条：engine_used=claude_fallback，费用合计，输出附上 dsl 的报告", t[1])
    check(t[2]["status"] == "error" and t[2]["engine_used"] == "plan" and "3 版都没修好" in t[2]["error"]
          and not [c for c in cs if "不兜底" in c["prompt"]], "fallback=false：不调 claude，记 error", t[2])
    check(t[3]["engine_used"] == "claude_fallback" and [c for c in cs if c["prompt"].startswith("DSLCRASH")]
          and "没写出结果" in t[3]["output"], "执行器崩了照样兜底，原因进输出", t[3])
    check(t[4]["engine"] == "claude" and t[4]["engine_used"] == "claude" and t[4]["output"] == "答：普通 claude 任务"
          and "project" not in t[4], "claude 任务照旧，不带 dsl 字段", t[4])
    dl = [json.loads(x) for x in DSL_LOG.read_text(encoding="utf-8").splitlines()]
    check([x["argv"][x["argv"].index("--project") + 1] for x in dl] == [str(proj)] * 4
          and "--test-cmd" in dl[1]["argv"] and "--test-cmd" not in dl[0]["argv"],
          "dsl 执行器拿到 project、给了才传 test_cmd", [x["argv"] for x in dl])
    check(d["options"]["engine"] == "claude", "job 级 engine 记在 options 里", d["options"])
    check(all(x["planner"] is None for x in dl) and d["options"]["dsl_planner"] is None,
          "没设 DSLAGENT_PLANNER：dsl 进程拿不到它（走缺省路径）", [x["planner"] for x in dl])

    print("engine=dsl：DSLAGENT_PLANNER / dsl_options.planner 透传给 dsl 进程")
    DSL_LOG.unlink()
    os.environ["DSLAGENT_PLANNER"] = "v2"
    try:
        j = cbatch.submit([{"prompt": "DSLOK 规划 v2", "engine": "dsl", "project": str(proj)}], cwd=str(TMP))
    finally:
        del os.environ["DSLAGENT_PLANNER"]
    d = cbatch.wait(j["job_id"], timeout=60, every=0.2)
    j = cbatch.submit([{"prompt": "DSLOK 逐条 v2", "engine": "dsl", "project": str(proj),
                        "dsl_options": {"planner": "v2"}}], cwd=str(TMP))
    d2 = cbatch.wait(j["job_id"], timeout=60, every=0.2)
    dl = [json.loads(x) for x in DSL_LOG.read_text(encoding="utf-8").splitlines()]
    check([x["planner"] for x in dl] == ["v2", "v2"] and d["options"]["dsl_planner"] == "v2"
          and d["tasks"][0]["dsl_planner"] == "v2" and d2["tasks"][0]["dsl_planner"] == "v2",
          "提交时的环境变量 / 单条 dsl_options.planner 都传到 dsl 进程", ([x["planner"] for x in dl], d["options"]))

    print("engine=dsl：提交时的 model 透传成 DSLAGENT_PLAN_MODEL")
    DSL_LOG.unlink()
    j = cbatch.submit([{"prompt": "DSLOK 带 model", "engine": "dsl", "project": str(proj)}], cwd=str(TMP), model="opus")
    cbatch.wait(j["job_id"], timeout=60, every=0.2)
    j = cbatch.submit([{"prompt": "DSLOK 没给 model", "engine": "dsl", "project": str(proj)}], cwd=str(TMP),
                      model=None)
    cbatch.wait(j["job_id"], timeout=60, every=0.2)
    dl = [json.loads(x) for x in DSL_LOG.read_text(encoding="utf-8").splitlines()]
    check([x["plan_model"] for x in dl] == ["opus", None],
          "给了 model → dsl 进程有 DSLAGENT_PLAN_MODEL；没给就没有", [x["plan_model"] for x in dl])

    print("engine：显式给了权限就照用户的，不套默认放行")
    LOG.unlink()
    j = cbatch.submit([{"prompt": "DSLNO 显式工具", "engine": "dsl", "project": str(proj)}],
                      cwd=str(TMP), allowed_tools=["Read", "Bash(make test)"])
    cbatch.wait(j["job_id"], timeout=60, every=0.2)
    j = cbatch.submit([{"prompt": "DSLNO 显式模式", "engine": "dsl", "project": str(proj)}],
                      cwd=str(TMP), permission_mode="plan")
    cbatch.wait(j["job_id"], timeout=60, every=0.2)
    c1 = [c for c in calls() if c["prompt"].startswith("DSLNO 显式工具")]
    c2 = [c for c in calls() if c["prompt"].startswith("DSLNO 显式模式")]
    check(c1 and tools_of(c1[0]) == ["Read", "Bash(make test)"], "显式 allowed_tools：原样照用，不追加默认",
          tools_of(c1[0]) if c1 else calls())
    check(c2 and arg(c2[0], "--permission-mode") == "plan" and not tools_of(c2[0]),
          "显式 permission_mode：照用，不追加默认工具", c2[0]["argv"] if c2 else calls())
    o = {"permission_mode": None, "allowed_tools": [], "model": None}
    dd = cbatch._in_project({"options": o, "cwd": "/x"}, {"project": str(proj)}, "pytest -q")
    check(dd["cwd"] == str(proj) and dd["options"]["permission_mode"] == "acceptEdits"
          and default_tools_ok(dd["options"]["allowed_tools"], "pytest -q") and o["allowed_tools"] == [],
          "_in_project 默认：acceptEdits + 默认清单 + 测试命令，不改原 options", dd["options"])
    dd = cbatch._in_project({"options": dict(o, allowed_tools=["Read"]), "cwd": "/x"}, {"project": str(proj)}, "pytest")
    check(dd["options"]["allowed_tools"] == ["Read"], "_in_project 显式 allowed_tools 不被覆盖", dd["options"])

    print("engine=auto：按规则分到 dsl / claude，理由记下")
    LOG.unlink()
    DSL_LOG.unlink()
    j = cbatch.submit([{"prompt": "DSLOK 测试 test_total 失败了：AssertionError", "project": str(proj)},
                       {"prompt": "DSLOK 给 calc 加个注释", "project": str(proj)},
                       {"prompt": "DSLOK Traceback (most recent call last):"}],
                      engine="auto", cwd=str(TMP))
    d = cbatch.wait(j["job_id"], timeout=60, every=0.2)
    t = d["tasks"]
    check(t[0]["engine_used"] == "template" and t[0]["engine_reason"].startswith("auto → dsl")
          and "unittest" in (t[0]["test_cmd"] or ""), "有失败测试的说法 + 能跑 + 初始失败 → dsl", t[0])
    check(t[1]["engine_used"] == "claude" and "auto → claude" in t[1]["engine_reason"], "没有信号 → claude", t[1])
    check(t[2]["engine_used"] == "claude" and "没给 project" in t[2]["engine_reason"], "没给 project → claude", t[2])
    check(len(DSL_LOG.read_text(encoding="utf-8").splitlines()) == 1, "只有分到 dsl 的那条起了 dsl 执行器")

    print("engine=dsl / auto：开局全过的任务路径（plan_task），兜底同样生效")
    ok = TMP / "proj_ok"
    (ok / "tests").mkdir(parents=True)
    (ok / "calc.py").write_text("def total(xs):\n    return sum(xs)\n", encoding="utf-8")
    (ok / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (ok / "tests" / "test_calc.py").write_text((proj / "tests" / "test_calc.py").read_text(encoding="utf-8"),
                                               encoding="utf-8")
    bare = TMP / "proj_bare"
    bare.mkdir()
    (bare / "calc.py").write_text("x = 1\n", encoding="utf-8")
    LOG.unlink()
    DSL_LOG.unlink()
    j = cbatch.submit([{"prompt": "DSLTASK DSLOK 新建 data/out.json", "engine": "dsl", "project": str(ok)},
                       {"prompt": "DSLTASK DSLNO 新建 data/out.json", "engine": "dsl", "project": str(ok)},
                       {"prompt": "DSLTASK DSLOK 新建 data/report.json，放汇总", "project": str(ok)},
                       {"prompt": "DSLOK 把代码整理得好看一点", "project": str(ok)},
                       {"prompt": "DSLOK 新建 data/report.json", "project": str(bare)},
                       {"prompt": "DSLOK 新建 data/report.json，Traceback (most recent call last):", "project": str(ok)}],
                      engine="auto", cwd=str(TMP))
    j_dsl = j
    d = cbatch.wait(j["job_id"], timeout=60, every=0.2)
    t = d["tasks"]
    check(t[0]["engine"] == "dsl" and t[0]["engine_used"] == "plan_task" and t[0]["status"] == "done"
          and t[0]["dsl_kind"] == "task", "engine=dsl 开局全过 → 任务路径，engine_used=plan_task", t[0])
    fb = [c for c in calls() if c["prompt"].startswith("DSLTASK DSLNO")]
    check(t[1]["engine_used"] == "claude_fallback" and len(fb) == 1 and "没能完成" in fb[0]["prompt"]
          and "HANDOFF-NOTE" in fb[0]["prompt"], "任务路径没完成 → claude 兜底，提示词说没完成、带交接说明",
          fb[0]["prompt"][-300:] if fb else t[1])
    check(t[2]["engine_used"] == "plan_task" and t[2]["engine_reason"].startswith("auto → dsl（task）")
          and "data/report.json" in t[2]["engine_reason"], "auto：全过 + 抽到产物 → dsl 任务路径，理由列出产物", t[2])
    check(t[3]["engine_used"] == "claude" and "抽不出明确产物" in t[3]["engine_reason"], "auto：全过、没有产物 → claude", t[3])
    check(t[4]["engine_used"] == "claude" and "探测不到测试" in t[4]["engine_reason"], "auto：测试跑不起来 → claude", t[4])
    check(t[5]["engine_used"] == "claude" and "初始测试全过" in t[5]["engine_reason"],
          "auto：说有 Traceback 但测试全过 → claude", t[5])
    check(len(DSL_LOG.read_text(encoding="utf-8").splitlines()) == 3, "只有 3 条起了 dsl 执行器", j_dsl)

    print("engine=auto：规则拿不准时短分类（假模型），能力检查")
    LOG.unlink()
    dec = lambda p, pj: cbatch.decide(p, str(pj))   # noqa: E731
    r = dec("RT_TASK 把代码整理一下", ok)
    check(r["engine"] == "dsl" and r["kind"] == "task" and r["source"] == "短分类" and r["classify"]["ok"]
          and "拿不准" in r["reason"] and "dsl_task" in r["reason"] and "s：" in r["reason"],
          "全过 + 抽不出产物 → 短分类 dsl_task → dsl 任务路径，理由带分类耗时", r)
    r = dec("RT_BUG 让它对", proj)
    check(r["engine"] == "dsl" and r["kind"] == "bugfix", "有失败没说法 → 短分类 dsl_bugfix → dsl 修 bug", r["reason"])
    r = dec("RT_BUG 让它对", ok)
    check(r["engine"] == "claude" and "没有失败测试" in r["reason"], "分类说修 bug 但测试全过 → claude", r["reason"])
    r = dec("RT_TASK 加个功能", proj)
    check(r["engine"] == "claude" and "修 bug 路径" in r["reason"], "分类说任务但测试有失败 → claude", r["reason"])
    r = dec("随便看看", ok)
    check(r["engine"] == "claude" and r["classify"]["route"] == "claude", "分类给 claude → claude", r["reason"])
    r = dec("RT_NEEDS 导出", ok)
    check(r["engine"] == "claude" and r["needs"] == ["要装 openpyxl"] and "做不到" in r["reason"],
          "分类 needs 非空 → claude（能力检查）", r["reason"])
    r = dec("RT_JUNK 弄一下", ok)
    check(r["engine"] == "claude" and not r["classify"]["ok"] and "解析不了" in r["reason"], "分类输出不是 JSON → 回落 claude", r["reason"])
    old_to = cbatch.ROUTE_TIMEOUT
    cbatch.ROUTE_TIMEOUT = 1
    r = dec("RT_SLEEP 弄一下", ok)
    cbatch.ROUTE_TIMEOUT = old_to
    check(r["engine"] == "claude" and "超过 1 秒" in r["reason"], "分类超时 → 回落 claude", r["reason"])
    n_before = len(calls())
    r = dec("RT_TASK 先 pip install openpyxl，再新建 data/out.xlsx", ok)
    check(r["engine"] == "claude" and r["source"] == "能力检查" and len(calls()) == n_before,
          "能力检查命中 → claude，不跑分类", r)
    r = dec("新建 data/report.json", ok)
    check(r["engine"] == "dsl" and r["source"] == "规则" and r["classify"] is None, "规则确定的不调分类", r)
    r = cbatch.decide("RT_TASK 整理", str(ok), classify=False)
    check(r["engine"] == "claude", "classify=False：拿不准照规则给 claude", r)

    print("submit：auto 走短分类、engine=dsl 能力警告、早退回兜底、分流日志")
    LOG.unlink()
    DSL_LOG.unlink()
    rl = Path(os.environ["CBATCH_HOME"]).parent / "routing.jsonl"
    rl.unlink(missing_ok=True)
    j = cbatch.submit([{"prompt": "DSLTASK DSLOK RT_TASK 把代码整理一下", "project": str(ok)},
                       {"prompt": "DSLOK RT_JUNK 弄一下", "project": str(ok)},
                       {"prompt": "DSLTASK DSLOK 先 pip install x，再新建 data/out.json", "project": str(ok), "engine": "dsl"},
                       {"prompt": "DSLTASK DSLEARLY 新建 data/out.xlsx", "project": str(ok), "engine": "dsl"},
                       "普通"], engine="auto", cwd=str(TMP))
    d = cbatch.wait(j["job_id"], timeout=60, every=0.2)
    t = d["tasks"]
    check(t[0]["engine_used"] == "plan_task" and "［短分类］" in t[0]["engine_reason"]
          and t[0]["route"]["classify"]["route"] == "dsl_task" and t[0]["cost_usd"] == 0.031,
          "auto 拿不准 → 短分类 → dsl；route 记分类细节，费用含分类", t[0])
    check(t[1]["engine_used"] == "claude" and "回落 claude" in t[1]["engine_reason"], "分类坏了回落 claude", t[1]["engine_reason"])
    c1 = [c for c in calls() if c["prompt"] == "DSLOK RT_JUNK 弄一下"]
    check(c1 and c1[0]["cwd"] == str(ok) and "acceptEdits" in c1[0]["argv"],
          "auto 判给 claude 且有 project：在 project 里跑，权限同兜底", c1[0]["argv"] if c1 else calls())
    check(c1 and default_tools_ok(tools_of(c1[0])), "auto→claude 也用默认放行清单（含 python）",
          tools_of(c1[0]) if c1 else "")
    check(t[2]["engine_used"] == "plan_task" and "pip install" in t[2].get("engine_warning", ""),
          "engine=dsl 命中能力检查：只记警告，照跑 dsl", t[2])
    fb = [c for c in calls() if "DSLEARLY" in c["prompt"]]
    check(t[3]["engine_used"] == "claude_fallback" and "缺能力" in t[3].get("dsl_early_exit", "") and len(fb) == 1,
          "dsl 早退回 → 直接兜底 claude，记原因", t[3])
    rows = [json.loads(x) for x in rl.read_text(encoding="utf-8").splitlines()]
    check(len(rows) == 5 and {r["i"] for r in rows} == {1, 2, 3, 4, 5}
          and all(len(r["hash"]) == 12 and "prompt" not in r for r in rows), "每条结束写一行分流日志（只记哈希）", rows[:1])
    r1 = [r for r in rows if r["i"] == 1][0]
    check(r1["decision"] == "dsl/task" and r1["source"] == "短分类" and r1["classify_route"] == "dsl_task"
          and r1["ok"] and r1["engine_used"] == "plan_task" and r1["cost_usd"] == 0.031 and r1["classify_sec"] is not None,
          "日志字段：判定、来源、分类、engine_used、成功、费用", r1)
    check([r for r in rows if r["i"] == 3][0]["warning"] and [r for r in rows if r["i"] == 4][0]["early_exit"],
          "日志里记警告和早退回")
    st = cbatch.routing_stats()
    check(st["total"]["n"] == 5 and st["classify"]["n"] == 2 and st["classify"]["failed"] == 1
          and st["early_exit"] == 1 and st["warnings"] == 1
          and st["by_engine_used"]["plan_task"]["n"] == 2 and st["by_engine_used"]["plan_task"]["rate"] == 1.0,
          "routing_stats 汇总：条数、成功率、分类次数、早退回、警告", st)
    check(cbatch.routing_stats(since="2999")["total"]["n"] == 0, "routing_stats since 过滤")

    print("并发：dsl 道默认 3、可覆盖，claude 道单独计，同一 project 互斥")
    check(raises(cbatch.submit, ["x"], dsl_concurrency=0) and raises(cbatch.submit, ["x"], concurrency=9),
          "并发参数越界报错")
    nap = TMP / "nap.jsonl"
    projs = []
    for k in range(5):
        pk = TMP / f"pnap{k}"
        pk.mkdir(exist_ok=True)
        projs.append(str(pk))

    def overlap(rows):
        ev = sorted([(r["t0"], 1) for r in rows] + [(r["t1"], -1) for r in rows])
        cur = best = 0
        for _, x in ev:
            cur += x
            best = max(best, cur)
        return best

    def run_nap(tasks, **kw):
        nap.unlink(missing_ok=True)
        j = cbatch.submit(tasks, engine="dsl", cwd=str(TMP), **kw)
        d = cbatch.wait(j["job_id"], timeout=60, every=0.2)
        rows = [json.loads(x) for x in nap.read_text().splitlines()]
        return d, [r for r in rows if r["who"] == "dsl"], [r for r in rows if r["who"] == "claude"]

    d, dr, _ = run_nap([{"prompt": "DSLNAP", "project": p} for p in projs])
    check(d["status"] == "done" and len(dr) == 5 and overlap(dr) == 3, "5 条 dsl 默认最多同时 3 条", overlap(dr))
    d, dr, _ = run_nap([{"prompt": "DSLNAP", "project": p} for p in projs[:4]], dsl_concurrency=2)
    check(overlap(dr) == 2, "dsl_concurrency=2 覆盖", overlap(dr))
    d, dr, cr = run_nap([{"prompt": "DSLNAP", "project": projs[0]}, {"prompt": "DSLNAP", "project": projs[0]},
                         {"prompt": "NAP 一", "engine": "claude"}, {"prompt": "NAP 二", "engine": "claude"}])
    allr = dr + cr
    check(overlap(dr) == 1 and overlap(cr) == 1 and overlap(allr) == 2 and [r["p"] for r in cr] == ["NAP 一", "NAP 二"],
          "同一 project 的 dsl 不并发；claude 道并发 1 按顺序，和 dsl 道同时跑", (overlap(dr), overlap(cr), overlap(allr)))
    d, _, cr = run_nap([{"prompt": "NAP 一", "engine": "claude"}, {"prompt": "NAP 二", "engine": "claude"}], concurrency=2)
    check(overlap(cr) == 2, "concurrency=2 时 claude 道两条同时跑", overlap(cr))
    del os.environ["CBATCH_DSL"]

    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
