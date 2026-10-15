# -*- coding: utf-8 -*-
"""tools/cxbatch.py：提交、沙箱参数、续接、并发、超时被杀、取消、输出截断、cwd 校验。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_cxbatch.py

执行端换成假的 codex（下面的 FAKE，路径走 CXBATCH_CODEX），不联网、不花钱。
输出照 codex exec --json 的事件流（thread.started / item.completed / turn.completed）。
"""

import atexit
import json
import os
import shutil
import signal
import stat
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="cxbatch_"))
LOG = TMP / "calls.jsonl"

FAKE = f"""#!{sys.executable}
import json, os, sys, time, uuid
a = sys.argv[1:]
prompt = sys.stdin.read()
resume = a[a.index("resume") + 1] if "resume" in a else None
# resume 后面先是选项时，会话 id 是 `-` 前面那个不是选项的参数
if resume is not None:
    if resume.startswith("-"):
        dash = len(a) - 1 - a[::-1].index("-")
        resume = a[dash - 1]
t0 = time.time()
cfgs = [a[i + 1] for i, x in enumerate(a) if x == "-c" and i + 1 < len(a)]
with open({str(LOG)!r}, "a", encoding="utf-8") as f:
    f.write(json.dumps({{"prompt": prompt, "resume": resume, "argv": a, "cwd": os.getcwd(),
                         "cfgs": cfgs,
                         "leak": sorted(k for k in os.environ
                                        if k in ("CLAUDECODE", "CODEX_SANDBOX", "CODEX_THREAD_ID")
                                        or k.startswith("CLAUDE_CODE_")),
                         "t0": t0}}, ensure_ascii=False) + "\\n")
if "SLEEP2" in prompt:
    time.sleep(2)
elif "SLEEP" in prompt:
    time.sleep(30)
sid = resume or str(uuid.uuid4())
def emit(obj):
    print(json.dumps(obj, ensure_ascii=False), flush=True)
emit({{"type": "thread.started", "thread_id": sid}})
emit({{"type": "turn.started"}})
if "ERR" in prompt:
    emit({{"type": "turn.failed", "error": {{"message": "模型不可用"}}}})
    sys.exit(0)
if "RC3" in prompt:
    sys.stderr.write("boom")
    sys.exit(3)
text = "X" * 150000 if "BIG" in prompt else "答：" + prompt
emit({{"type": "item.completed", "item": {{"id": "item_1", "type": "agent_message", "text": text}}}})
emit({{"type": "turn.completed", "usage": {{"input_tokens": 10, "cached_input_tokens": 4,
      "output_tokens": 5, "reasoning_output_tokens": 1}}}})
"""

fake = TMP / "codex"
fake.write_text(FAKE, encoding="utf-8")
fake.chmod(fake.stat().st_mode | stat.S_IXUSR)


def _cleanup():
    """假 codex 在自己的进程组里，执行器被杀掉时它还在睡。先杀掉再删临时目录。"""
    for p in Path("/proc").iterdir():
        if p.name.isdigit() and _cmd_has(p, str(fake)):
            try:
                os.kill(int(p.name), signal.SIGKILL)
            except OSError:
                pass
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)

os.environ["CXBATCH_HOME"] = str(TMP / "jobs")
os.environ["CXBATCH_CODEX"] = str(fake)
os.environ["CLAUDECODE"] = "1"
os.environ["CLAUDE_CODE_SESSION_ID"] = "parent"
os.environ["CODEX_SANDBOX"] = "seatbelt"
os.environ["CODEX_THREAD_ID"] = "parent-thread"

from tools import cxbatch    # noqa: E402

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
    except cxbatch.CXBatchError as e:
        return str(e)
    return None


def arg(c, k):
    return c["argv"][c["argv"].index(k) + 1] if k in c["argv"] else None


def cfg(c, prefix):
    return next((x for x in c["cfgs"] if x.startswith(prefix)), "")


def run(tasks, **k):
    LOG.unlink(missing_ok=True)
    j = cxbatch.submit(tasks, cwd=str(TMP), **k)
    d = cxbatch.wait(j["job_id"], timeout=40, every=0.2)
    return d, calls()


def main():
    print("参数检查")
    check(raises(cxbatch.submit, []), "空列表报错")
    check(raises(cxbatch.submit, ["x"] * 11), "超过 MAX_TASKS 报错")
    check(raises(cxbatch.submit, ["x"], mode="both"), "mode 不对报错")
    check(raises(cxbatch.submit, [{"no": 1}]), "字典缺 prompt 报错")
    check(raises(cxbatch.submit, ["x"], concurrency=9), "并发超上限报错")
    check(raises(cxbatch.submit, ["x"], permission_mode="all"), "permission_mode 不对报错")
    check(raises(cxbatch.submit, ["x"], permission_mode="danger-full-access"),
          "不收 danger-full-access")
    check(raises(cxbatch.submit, ["x"], permission_mode="bypassPermissions"),
          "不收 bypassPermissions")
    check(raises(cxbatch.submit, ["x"], effort="turbo"), "effort 不对报错")
    check(raises(cxbatch.status, "nope"), "查不存在的任务报错")

    print("模型名")
    check(raises(cxbatch.submit, ["x"], model="a b", cwd=str(TMP)), "模型名有空格报错")
    check(raises(cxbatch.submit, [{"prompt": "x", "model": "bad/name"}], cwd=str(TMP)),
          "单条 model 写错也报错")

    print("cwd 校验")
    check(raises(cxbatch.submit, ["x"], cwd=str(Path.home())), "不收家目录")
    check(raises(cxbatch.submit, ["x"], cwd="/"), "不收 /")
    check(raises(cxbatch.submit, ["x"], cwd="~/x"), "不收 ~")
    check(raises(cxbatch.submit, ["x"], cwd=str(TMP / "不存在")), "不收不存在的目录")

    print("提交、跑完、只读沙箱")
    d, cs = run(["一", "二"], name="基本", model="gpt-5.6-luna", effort="低")
    check(d["status"] == "done", "整批 done", d["status"])
    check([t["output"] for t in d["tasks"]] == ["答：一", "答：二"], "输出按顺序")
    t = d["tasks"][0]
    check(t["tokens"] == {"input": 10, "cached_input": 4, "output": 5, "reasoning": 1}
          and t["cost_usd"] is None and t["rc"] == 0 and t["session_id"],
          "tokens / 不估算费用 / rc / thread_id", t)
    check(t["seconds"] is not None, "记了秒数")
    c = cs[0]
    check(c["argv"][:3] == ["exec", "--json", "--color"] and arg(c, "--color") == "never"
          and arg(c, "-s") == "read-only" and arg(c, "-C") == str(TMP)
          and arg(c, "-m") == "gpt-5.6-luna" and c["argv"][-1] == "-",
          "exec --json --color never -s read-only，提示词走 stdin", c["argv"])
    check(c["prompt"] == "一", "stdin 是提示词本身，不拼 preamble")
    check('approval_policy="never"' in c["cfgs"]
          and cfg(c, "model_reasoning_effort=") == 'model_reasoning_effort="low"'
          and cfg(c, "developer_instructions=").split("\n", 1)[-1].startswith(cxbatch.PREAMBLE[:8]),
          "approval=never、effort、preamble 进 -c")
    check("--skip-git-repo-check" in c["argv"] and "--ignore-rules" in c["argv"],
          "非 git 目录跳过仓库检查，并且不吃 execpolicy")
    check(c["cwd"] == str(TMP), "在指定 cwd 里跑", c["cwd"])
    check(not c["leak"], "CLAUDECODE / CODEX_SANDBOX / CODEX_THREAD_ID 没漏给子进程", c["leak"])
    check("key" not in cxbatch.PREAMBLE.lower() and "sk-" not in cxbatch.PREAMBLE, "preamble 不含 key")
    warned = cxbatch.submit(["创建一个文件"], cwd=str(TMP))
    cxbatch.wait(warned["job_id"], timeout=20, every=0.2)
    check(warned["sandbox"] == "read-only" and any("acceptEdits" in w for w in warned["warnings"]),
          "看着要写文件就警告，仍是只读", warned["warnings"])

    print("acceptEdits / 关 preamble / 不传模型")
    d, cs = run(["甲"], permission_mode="acceptEdits", preamble=False, effort=None, model=None)
    c = cs[0]
    check(arg(c, "-s") == "workspace-write" and "-m" not in c["argv"],
          "acceptEdits → workspace-write，不传 model 就不带 -m", c["argv"])
    check(not any(x.startswith("developer_instructions=") for x in c["cfgs"])
          and not any(x.startswith("model_reasoning_effort=") for x in c["cfgs"])
          and 'approval_policy="never"' in c["cfgs"],
          "preamble=False、effort=None 时不传这两项")

    print("git 仓库不加 --skip-git-repo-check")
    repo = TMP / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    LOG.unlink(missing_ok=True)
    j = cxbatch.submit(["在仓库里"], cwd=str(repo))
    cxbatch.wait(j["job_id"], timeout=20, every=0.2)
    c = calls()[0]
    check("--skip-git-repo-check" not in c["argv"] and arg(c, "-C") == str(repo),
          "有 .git 就不跳过检查", c["argv"])

    print("默认 cwd：任务目录下的空目录")
    LOG.unlink(missing_ok=True)
    j = cxbatch.submit(["x"])
    d = cxbatch.wait(j["job_id"], timeout=30, every=0.2)
    c = calls()[0]
    check(c["cwd"] == str(TMP / "jobs" / j["job_id"] / "work") and not any(Path(c["cwd"]).iterdir()),
          "不传 cwd 用空目录", c["cwd"])

    print("share：后一条 resume 接前一条的线程，失败后断开")
    d, cs = run(["甲", "乙 ERR", "丙", "丁"], mode="share")
    t = d["tasks"]
    check(cs[0]["resume"] is None and cs[1]["resume"] == t[0]["session_id"],
          "第二条 resume 第一条的 thread_id")
    check("resume" in cs[1]["argv"] and "--color" not in cs[1]["argv"] and "-s" not in cs[1]["argv"],
          "resume 不带 exec 才有的 -s / --color")
    check(t[1]["status"] == "error" and "模型不可用" in t[1]["error"], "turn.failed 记 error", t[1])
    check(cs[2]["resume"] is None, "前一条失败，下一条开新线程")
    check(cs[3]["resume"] == t[2]["session_id"], "之后接着续")
    check(d["status"] == "partial", "有成有败 partial", d["status"])

    print("退出码非 0")
    d, cs = run(["RC3"])
    t = d["tasks"][0]
    check(t["status"] == "error" and t["rc"] == 3 and "boom" in t["stderr"] and d["status"] == "failed",
          "记 rc 和 stderr 摘要", t)

    print("输出截断")
    d, cs = run(["BIG"])
    out = d["tasks"][0]["output"]
    check("还有" in out and len(out) < 700, "status 默认预览截断", len(out))
    full = cxbatch.status(d["id"], full=True)["tasks"][0]["output"]
    check(len(full) < 150000 and "已截断" in full and len(full) > cxbatch.MAX_OUTPUT,
          "full 返回存盘截断后的全文", len(full))

    print("并发")
    t0 = time.time()
    d, cs = run(["SLEEP2 a", "SLEEP2 b", "SLEEP2 c"], concurrency=3)
    el = time.time() - t0
    starts = sorted(c["t0"] for c in cs)
    check(d["status"] == "done" and starts[-1] - starts[0] < 1.5, "3 条几乎同时开始", starts[-1] - starts[0])
    check(el < 5.5, "总耗时远小于串行 6 秒", el)
    check([t["output"] for t in d["tasks"]] == ["答：SLEEP2 a", "答：SLEEP2 b", "答：SLEEP2 c"],
          "输出对应各自的提示词")
    d, cs = run(["SLEEP2 a", "SLEEP2 b"], concurrency=1)
    starts = sorted(c["t0"] for c in cs)
    check(starts[1] - starts[0] >= 1.9, "concurrency=1 顺序跑", starts[1] - starts[0])

    print("超时被杀")
    d, cs = run(["SLEEP", "后面照跑"], timeout=1)
    t = d["tasks"]
    check(t[0]["status"] == "timeout" and t[0]["seconds"] < 10, "超时那条记 timeout", t[0])
    check(t[1]["status"] == "done", "之后接着跑", t[1]["status"])
    time.sleep(0.3)
    check(not [p for p in Path("/proc").iterdir()
               if p.name.isdigit() and _cmd_has(p, str(fake)) and _cmd_has(p, "SLEEP")],
          "假 codex 进程已被杀掉")

    print("取消")
    j = cxbatch.submit(["SLEEP 一", "SLEEP 二"], cwd=str(TMP), concurrency=2)
    for _ in range(80):
        if cxbatch.status(j["job_id"])["tasks"][0]["status"] == "running" and len(calls()) >= 2:
            break
        time.sleep(0.1)
    pid = cxbatch.status(j["job_id"])["pid"]
    r = cxbatch.cancel(j["job_id"])
    d = cxbatch.status(j["job_id"])
    check(r["status"] == "cancelled" and d["status"] == "cancelled", "状态是 cancelled", d["status"])
    check({t["status"] for t in d["tasks"]} == {"cancelled"}, "没跑完的都标 cancelled",
          [t["status"] for t in d["tasks"]])
    try:
        os.kill(pid, 0)
        alive = True
    except ProcessLookupError:
        alive = False
    check(not alive, "执行器进程已经没了")
    time.sleep(0.5)
    check(not [p for p in Path("/proc").iterdir()
               if p.name.isdigit() and _cmd_has(p, str(fake)) and _cmd_has(p, "SLEEP")],
          "正在跑的 codex 子进程也被杀")
    check(cxbatch.status(j["job_id"])["status"] == "cancelled", "执行器没有回头把状态盖掉")
    check(cxbatch.cancel(j["job_id"]).get("note") == "已经结束了", "重复取消不报错")

    print("执行器死掉")
    j = cxbatch.submit(["SLEEP"], cwd=str(TMP))
    for _ in range(50):
        if cxbatch.status(j["job_id"]).get("pid"):
            break
        time.sleep(0.1)
    os.killpg(cxbatch.status(j["job_id"])["pid"], signal.SIGKILL)
    time.sleep(0.3)
    check(cxbatch.status(j["job_id"])["status"] == "died", "进程没了就是 died")
    check(any(x["id"] == j["job_id"] for x in cxbatch.jobs(50)), "jobs 列得到")
    text = cxbatch.describe()
    check("read-only" in text and "acceptEdits" in text and "medium" in text, "describe 有权限和 effort")

    _cleanup()
    check(not TMP.exists(), "临时目录已删")
    check(not [p for p in Path("/proc").iterdir()
               if p.name.isdigit() and _cmd_has(p, str(fake))],
          "假 codex 进程已清掉")

    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)


def _cmd_has(p, s):
    try:
        return s in (p / "cmdline").read_bytes().decode("utf-8", "replace")
    except OSError:
        return False


if __name__ == "__main__":
    main()
