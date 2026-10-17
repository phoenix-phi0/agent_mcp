# -*- coding: utf-8 -*-
"""tools/obatch.py：提交、并发、超时被杀、取消、输出截断、模型名校验、lean 参数拼装、cwd 校验。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_obatch.py

执行端换成假的 opencode（下面的 FAKE，路径走 OBATCH_OPENCODE），不联网、不花钱。
输出照真 opencode run --format json 的事件流（step_start / text / step_finish）。
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

TMP = Path(tempfile.mkdtemp(prefix="obatch_"))
LOG = TMP / "calls.jsonl"

FAKE = f"""#!{sys.executable}
import json, os, sys, time, uuid
a = sys.argv[1:]
prompt = a[a.index("--") + 1]
resume = a[a.index("-s") + 1] if "-s" in a else None
t0 = time.time()
with open({str(LOG)!r}, "a", encoding="utf-8") as f:
    f.write(json.dumps({{"prompt": prompt, "resume": resume, "argv": a, "cwd": os.getcwd(),
                         "cfg": os.environ.get("OPENCODE_CONFIG_CONTENT"),
                         "pwd": os.environ.get("PWD"), "stdin": sys.stdin.read(),
                         "env": {{k: os.environ.get(k) for k in
                                 ("OPENCODE_DISABLE_CLAUDE_CODE", "OPENCODE_DISABLE_AUTOUPDATE")}},
                         "leak": sorted(k for k in os.environ
                                        if k == "CLAUDECODE" or k.startswith("CLAUDE_CODE_")),
                         "t0": t0}}, ensure_ascii=False) + "\\n")
if "SLEEP2" in prompt:
    time.sleep(2)
elif "SLEEP" in prompt:
    time.sleep(30)
sid = resume or "ses_" + uuid.uuid4().hex[:6]
def ev(typ, **part):
    print(json.dumps({{"type": typ, "timestamp": int(time.time() * 1000), "sessionID": sid,
                      "part": part}}, ensure_ascii=False), flush=True)
ev("step_start", type="step-start")
if "ERR" in prompt:
    print(json.dumps({{"type": "error", "sessionID": sid,
                      "error": {{"name": "APIError", "data": {{"message": "模型不可用"}}}}}}))
    sys.exit(0)
if "RC3" in prompt:
    sys.stderr.write("boom"); sys.exit(3)
text = "X" * 150000 if "BIG" in prompt else "答：" + prompt + ("|接着" + resume if resume else "")
ev("text", type="text", text=text)
ev("step_finish", type="step-finish", reason="stop",
   tokens={{"total": 30, "input": 10, "output": 5, "reasoning": 15, "cache": {{"write": 0, "read": 0}}}},
   cost=0.002)
"""

fake = TMP / "opencode"
fake.write_text(FAKE, encoding="utf-8")
fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

os.environ["OBATCH_HOME"] = str(TMP / "jobs")
os.environ["OBATCH_OPENCODE"] = str(fake)
os.environ["CLAUDECODE"] = "1"
os.environ["CLAUDE_CODE_SESSION_ID"] = "parent"

from tools import obatch    # noqa: E402

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
    except obatch.OBatchError as e:
        return str(e)
    return None


def arg(c, k):
    return c["argv"][c["argv"].index(k) + 1] if k in c["argv"] else None


def run(tasks, **k):
    LOG.unlink(missing_ok=True)
    j = obatch.submit(tasks, cwd=str(TMP), **k)
    d = obatch.wait(j["job_id"], timeout=40, every=0.2)
    return d, calls()


def main():
    print("参数检查")
    check(raises(obatch.submit, []), "空列表报错")
    check(raises(obatch.submit, ["x"] * 11), "超过 MAX_TASKS 报错")
    check(raises(obatch.submit, ["x"], mode="both"), "mode 不对报错")
    check(raises(obatch.submit, [{"no": 1}]), "字典缺 prompt 报错")
    check(raises(obatch.submit, ["x"], concurrency=9), "并发超上限报错")
    check(raises(obatch.submit, ["x"], permission_mode="all"), "permission_mode 不对报错")
    check(raises(obatch.status, "nope"), "查不存在的任务报错")

    print("模型名校验")
    for bad in ("glm-5.3", "zhipuai-coding-plan/nope", "a b/c"):
        e = raises(obatch.submit, ["x"], model=bad, cwd=str(TMP))
        check(e and "zhipuai-coding-plan/glm-5.3-flash" in e, f"{bad!r} 报错并列出可用模型", e)
    check(raises(obatch.submit, [{"prompt": "x", "model": "bad"}], cwd=str(TMP)), "单条 model 写错也报错")

    print("百炼模型白名单 / PWD / stdin")
    for m in ("bailian-cli/qwen3.8-max", "bailian-cli/qwen3.8-flash"):
        check(raises(obatch.submit, ["no-run"], model=m, cwd=str(TMP)) is None, f"{m} 放行")
    time.sleep(1.5)      # 放行的提交会真起一个假 opencode，等它写完日志再开始
    check(raises(obatch.submit, ["x"], model="bailian-cli/qwen9", cwd=str(TMP)), "未登记的百炼模型拒绝")
    d, cs = run(["PWDCHK"], model="bailian-cli/qwen3.8-flash")
    cs = [c for c in cs if c["prompt"] == "PWDCHK"]
    check(d["status"] == "done" and cs and cs[0]["pwd"] == str(TMP) and cs[0]["stdin"] == "",
          "obatch：env PWD=cwd 且 stdin 即刻 EOF", cs[:1])
    check(arg(cs[0], "-m") == "bailian-cli/qwen3.8-flash", "-m 传百炼模型")
    # v2 引擎 call_opencode：PWD、stdin 喂完即关
    from tools.dslagent import engines
    fake2 = TMP / "opencode_v2"
    fake2.write_text(f"""#!{sys.executable}
import json, os, sys
u = sys.stdin.read()
open({str(LOG)!r}, "a").write(json.dumps({{"pwd": os.environ.get("PWD"), "cwd": os.getcwd(), "user": u,
    "home": os.environ.get("HOME"), "argv": sys.argv[1:]}}) + "\\n")
print(json.dumps({{"type": "text", "part": {{"type": "text", "text": "OK"}}}}), flush=True)
""", encoding="utf-8")
    fake2.chmod(0o755)
    LOG.unlink(missing_ok=True)
    old = engines.opencode_bin
    engines.opencode_bin = lambda: str(fake2)
    try:
        r = engines.call_opencode("sys", "用户内容", timeout=30, model="bailian-cli/qwen3.8-flash")
    finally:
        engines.opencode_bin = old
    c = calls()[0] if calls() else {}
    check(c.get("pwd") == c.get("cwd") and c.get("user") == "用户内容", "call_opencode：PWD==cwd，stdin 内容送达并 EOF", c)
    check(c.get("home") == os.environ.get("HOME") and "bailian-cli/qwen3.8-flash" in c.get("argv", []), "保留 HOME，-m 透传")
    check(r.get("text") == "OK" and r.get("rc") == 0, "call_opencode 返回文本", r)

    print("cwd 校验")
    check(raises(obatch.submit, ["x"], cwd=str(Path.home())), "不收家目录")
    check(raises(obatch.submit, ["x"], cwd="/"), "不收 /")
    check(raises(obatch.submit, ["x"], cwd="~/x"), "不收 ~")
    check(raises(obatch.submit, ["x"], cwd=str(TMP / "不存在")), "不收不存在的目录")

    print("提交、跑完、lean 参数拼装")
    d, cs = run(["一", "二"], name="基本",
                model="zhipuai-coding-plan/glm-5.3-flash")
    check(d["status"] == "done", "整批 done", d["status"])
    check([t["output"] for t in d["tasks"]] == ["答：一", "答：二"], "输出按顺序")
    t = d["tasks"][0]
    check(t["tokens"] == {"total": 30, "input": 10, "output": 5, "reasoning": 15}
          and t["cost"] == 0.002 and t["rc"] == 0 and t["session_id"], "tokens / 费用 / rc / session 记下来", t)
    check(t["seconds"] is not None and t["first_token_seconds"] is not None
          and t["first_token_seconds"] <= t["seconds"] + 0.5, "秒数和首字秒", t)
    c = cs[0]
    check(c["argv"][0] == "run" and arg(c, "--format") == "json"
          and arg(c, "-m") == "zhipuai-coding-plan/glm-5.3-flash", "run --format json -m 模型", c["argv"])
    check(arg(c, "--agent") == "obatch" and c["argv"][-2] == "--", "lean 走 obatch agent，提示词在 -- 之后")
    cfg = json.loads(c["cfg"])["agent"]["obatch"]
    check(cfg["tools"] == {"*": False} and cfg["steps"] == obatch.DEFAULT_STEPS
          and cfg["prompt"].startswith(obatch.LEAN_SYSTEM) and obatch.PREAMBLE in cfg["prompt"],
          "lean：短系统提示 + 关全部工具 + 限轮数 + preamble", cfg)
    check(c["env"]["OPENCODE_DISABLE_CLAUDE_CODE"] == "1" and c["env"]["OPENCODE_DISABLE_AUTOUPDATE"] == "1",
          "lean 关 Claude 配置读取")
    check(c["prompt"] == "一", "lean 时提示词不拼 preamble")
    check(c["cwd"] == str(TMP), "在指定 cwd 里跑", c["cwd"])
    check(not c["leak"], "CLAUDECODE / CLAUDE_CODE_* 没漏给子进程")
    check("key" not in obatch.PREAMBLE.lower() and "sk-" not in obatch.PREAMBLE, "preamble 不含 key")

    d, cs = run(["默认"], max_steps=2, preamble=False)
    cfg = json.loads(cs[0]["cfg"])["agent"]["obatch"]
    check(arg(cs[0], "-m") == obatch.DEFAULT_MODEL and cfg["steps"] == 2
          and cfg["prompt"] == obatch.LEAN_SYSTEM, "默认模型、max_steps、preamble=False")

    print("lean=False")
    d, cs = run(["甲"], lean=False)
    c = cs[0]
    check("--agent" not in c["argv"] and c["prompt"].startswith(obatch.PREAMBLE) and c["prompt"].endswith("甲"),
          "不指定 agent，preamble 拼在提示词前")
    check("agent" not in json.loads(c["cfg"]) and c["env"]["OPENCODE_DISABLE_CLAUDE_CODE"] is None,
          "不改工具和系统提示")
    d, cs = run(["乙"], lean=False, permission_mode="readonly", preamble=False)
    perm = json.loads(cs[0]["cfg"])["agent"]["obatch"]["permission"]
    check(arg(cs[0], "--agent") == "obatch" and perm == {"edit": "deny", "bash": "deny"}, "readonly", perm)
    d, cs = run(["丙"], lean=False, permission_mode="acceptEdits", preamble=False)
    perm = json.loads(cs[0]["cfg"])["agent"]["obatch"]["permission"]
    check(perm == {"edit": "allow", "bash": "deny"}, "acceptEdits", perm)

    print("默认 cwd：任务目录下的空目录")
    LOG.unlink(missing_ok=True)
    j = obatch.submit(["x"])
    d = obatch.wait(j["job_id"], timeout=30, every=0.2)
    c = calls()[0]
    check(c["cwd"] == str(TMP / "jobs" / j["job_id"] / "work") and not any(Path(c["cwd"]).iterdir()),
          "不传 cwd 用空目录", c["cwd"])

    print("share：后一条 -s 接前一条的会话，失败后断开")
    d, cs = run(["甲", "乙 ERR", "丙", "丁"], mode="share")
    t = d["tasks"]
    check(cs[0]["resume"] is None and cs[1]["resume"] == t[0]["session_id"], "第二条 -s 第一条的会话")
    check(t[1]["status"] == "error" and "模型不可用" in t[1]["error"], "error 事件记 error", t[1])
    check(cs[2]["resume"] is None, "前一条失败，下一条开新会话")
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
    check(len(out) == obatch.PREVIEW + len(f"…（还有 {150000 - obatch.PREVIEW} 字）")
          or "还有" in out and len(out) < 700, "status 默认预览截断", len(out))
    full = obatch.status(d["id"], full=True)["tasks"][0]["output"]
    check(len(full) < 150000 and "已截断" in full and len(full) > obatch.MAX_OUTPUT, "full 返回存盘截断后的全文", len(full))

    print("并发")
    t0 = time.time()
    d, cs = run(["SLEEP2 a", "SLEEP2 b", "SLEEP2 c"], concurrency=3)
    el = time.time() - t0
    starts = sorted(c["t0"] for c in cs)
    check(d["status"] == "done" and starts[-1] - starts[0] < 1.5, "3 条几乎同时开始", starts[-1] - starts[0])
    check(el < 5.5, "总耗时远小于串行 6 秒", el)
    check([t["output"] for t in d["tasks"]] == ["答：SLEEP2 a", "答：SLEEP2 b", "答：SLEEP2 c"], "输出对应各自的提示词")
    d, cs = run(["SLEEP2 a", "SLEEP2 b"], concurrency=1)
    starts = sorted(c["t0"] for c in cs)
    check(starts[1] - starts[0] >= 1.9, "concurrency=1 顺序跑", starts[1] - starts[0])

    print("超时被杀")
    d, cs = run(["SLEEP", "后面照跑"], timeout=1)
    t = d["tasks"]
    check(t[0]["status"] == "timeout" and t[0]["seconds"] < 10, "超时那条记 timeout", t[0])
    check(t[1]["status"] == "done", "之后接着跑", t[1]["status"])
    time.sleep(0.3)
    check(not [p for p in Path("/proc").iterdir() if p.name.isdigit() and _cmd_has(p, str(fake)) and _cmd_has(p, "SLEEP")],
          "假 opencode 进程已被杀掉")

    print("取消")
    j = obatch.submit(["SLEEP 一", "SLEEP 二"], cwd=str(TMP), concurrency=2)
    for _ in range(80):
        if obatch.status(j["job_id"])["tasks"][0]["status"] == "running" and len(calls()) >= 2:
            break
        time.sleep(0.1)
    pid = obatch.status(j["job_id"])["pid"]
    r = obatch.cancel(j["job_id"])
    d = obatch.status(j["job_id"])
    check(r["status"] == "cancelled" and d["status"] == "cancelled", "状态是 cancelled", d["status"])
    check({t["status"] for t in d["tasks"]} == {"cancelled"}, "没跑完的都标 cancelled")
    try:
        os.kill(pid, 0)
        alive = True
    except ProcessLookupError:
        alive = False
    check(not alive, "执行器进程已经没了")
    time.sleep(0.5)
    check(not [p for p in Path("/proc").iterdir() if p.name.isdigit() and _cmd_has(p, str(fake)) and _cmd_has(p, "SLEEP")],
          "正在跑的 opencode 子进程也被杀")
    check(obatch.status(j["job_id"])["status"] == "cancelled", "执行器没有回头把状态盖掉")
    check(obatch.cancel(j["job_id"]).get("note") == "已经结束了", "重复取消不报错")

    print("执行器死掉")
    j = obatch.submit(["SLEEP"], cwd=str(TMP))
    for _ in range(50):
        if obatch.status(j["job_id"]).get("pid"):
            break
        time.sleep(0.1)
    os.killpg(obatch.status(j["job_id"])["pid"], signal.SIGKILL)
    time.sleep(0.3)
    check(obatch.status(j["job_id"])["status"] == "died", "进程没了就是 died")
    check(any(x["id"] == j["job_id"] for x in obatch.jobs(50)), "jobs 列得到")

    # 清理遗留的假进程
    for p in Path("/proc").iterdir():
        if p.name.isdigit() and _cmd_has(p, str(fake)) and _cmd_has(p, "SLEEP"):
            try:
                os.kill(int(p.name), signal.SIGKILL)
            except OSError:
                pass

    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)


def _cmd_has(p, s):
    try:
        return s in (p / "cmdline").read_bytes().decode("utf-8", "replace")
    except OSError:
        return False


if __name__ == "__main__":
    main()
