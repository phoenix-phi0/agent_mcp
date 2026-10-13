# -*- coding: utf-8 -*-
"""tools/dslagent：不调模型的部分——补读范围的区间覆盖、模板抽参、auto 判定、测试命令探测、
测试摘要、计划检查（白名单 / 去说明文字 / 补结束）、AgentEngine 的子脚本映射和语句白名单、
常驻进程池的首 token 对冲（假 claude 进程）。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent.py

真模型的集成测试在 tests/tools/dslagent_live.py（手动跑，要花钱）。
"""

import importlib.util
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_"))
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
os.environ["DSLAGENT_TMP"] = str(TMP / "tmp")
# 执行器开头会预热常驻 claude 进程（不调 API）；单元测试里换成马上退出的程序，一个真 claude 都不起
os.environ["CBATCH_CLAUDE"] = "/bin/true"

from tools.dslagent import plan as P          # noqa: E402
from tools.dslagent import runner as R        # noqa: E402
from tools.dslagent.legacy import run as LR     # noqa: E402
from tools.dslagent.legacy import template as T      # noqa: E402

DEFS = ROOT / "tools" / "dslagent" / "verbs" / "code" / "defs"
PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"：{extra}" if extra else ""))


def verb(name, ws):
    spec = importlib.util.spec_from_file_location(f"_t_{name}", DEFS / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.WORKSPACE = Path(ws)
    return getattr(m, name), m


def project(name, files):
    d = TMP / name
    for rel, text in files.items():
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return d


CALC = "def total(xs):\n    return sum(xs) - 1\n\n\ndef avg(xs):\n    return total(xs) / len(xs)\n"
TEST_FAIL = ("import unittest\nfrom pkg.calc import total\n\n\nclass CalcTest(unittest.TestCase):\n"
             "    def test_total(self):\n        self.assertEqual(total([1, 2]), 3)\n")
TEST_OK = TEST_FAIL.replace("3)", "2)")


# 假的常驻 claude（stream-json 进出）：第 i 个起的进程按 FAKE_PLAN[i] 行事——数字 = 多少秒后出首 token；
# {"start": a, "delay": b} = a 秒出 message_start（带 usage）、b 秒出首 token；dict 里再加 "stall": c = 出首 token 后
# 卡 c 秒才出结果（流卡住）、"boot": d = 进程起来先睡 d 秒才开始读 stdin（预热没完成）；
# "die" = 收到问题就退出；"err" = 马上回报错的 result；列表 = 这个进程的第几问逐个取。
# 每个进程把 pid 记进 FAKE_DIR/pids；回答里带 pid 和「上次 /clear 以来第几问」(hist)，用来查会话干不干净。
FAKE_CLAUDE = r"""#!/usr/bin/env python3
import json, os, sys, time
d = os.environ["FAKE_DIR"]
plan = json.load(open(os.path.join(d, "plan.json")))
i = 0
while True:
    try:
        os.close(os.open(os.path.join(d, f"idx_{i}"), os.O_CREAT | os.O_EXCL)); break
    except FileExistsError:
        i += 1
with open(os.path.join(d, "pids"), "a") as f:
    f.write(f"{os.getpid()}\n")
beh = plan[i] if i < len(plan) else 0.05
if isinstance(beh, dict) and beh.get("boot"):
    time.sleep(beh["boot"])
out = lambda o: (sys.stdout.write(json.dumps(o, ensure_ascii=False) + "\n"), sys.stdout.flush())
hist, nq, total = 0, 0, 0.0
for line in sys.stdin:
    msg = json.loads(line)["message"]["content"]
    if msg == "/clear":
        hist = 0
        out({"type": "result", "subtype": "success", "result": "", "total_cost_usd": total, "session_id": f"s{i}"})
        continue
    hist += 1
    if beh == "die":
        sys.exit(3)
    if beh == "err":
        out({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "API Error",
             "session_id": f"s{i}", "total_cost_usd": total})
        continue
    nq += 1
    b = beh[min(nq, len(beh)) - 1] if isinstance(beh, list) else beh
    start, delay = (b.get("start"), b.get("delay", 0.05)) if isinstance(b, dict) else (None, b)
    t0 = time.time()
    if start is not None:
        time.sleep(start)
        out({"type": "stream_event", "event": {"type": "message_start", "message": {"usage": {
            "input_tokens": 1000, "cache_read_input_tokens": 10000, "cache_creation_input_tokens": 0}}}})
    time.sleep(max(0, delay - (time.time() - t0)))
    out({"type": "stream_event", "event": {"type": "content_block_delta"}})
    time.sleep(b.get("stall", 0) if isinstance(b, dict) else 0)
    total += 0.01
    out({"type": "result", "subtype": "success", "is_error": False, "session_id": f"s{i}", "total_cost_usd": total,
         "result": f"答:{msg}|idx={i}|pid={os.getpid()}|hist={hist}"})
"""


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:        # 僵尸进程也算死
        return Path(f"/proc/{pid}/stat").read_text().split(")")[-1].split()[0] != "Z"
    except OSError:
        return False


def test_hedge():
    """常驻进程池的首 token 对冲：用假 claude 模拟慢/快/崩，不调模型。"""
    import json
    from tools.dslagent.legacy.pool import Pool
    print("常驻进程池：首 token 对冲重发")
    fake = TMP / "fake_claude.py"
    fake.write_text(FAKE_CLAUDE, encoding="utf-8")
    fake.chmod(0o755)
    n = [0]

    def setup(plan, hedge=0.4, stall=20):
        n[0] += 1
        d = TMP / f"fake_{n[0]}"
        d.mkdir()
        (d / "plan.json").write_text(json.dumps(plan))
        env = dict(os.environ, FAKE_DIR=str(d))
        return d, Pool(d, str(fake), env, hedge=hedge, stall=stall)

    def ask(pool, q, timeout=10):
        t0 = time.time()
        r = json.loads(pool.run_local(["claude", "-p", q, "--system-prompt", "S", "--model", "sonnet"], timeout).stdout)
        return r, r["_pool"], time.time() - t0

    def pids(d):
        return [int(x) for x in (d / "pids").read_text().split()] if (d / "pids").exists() else []

    def finish(d, pool):
        pool.close()
        time.sleep(0.2)
        return [p for p in pids(d) if _pid_alive(p)]

    d, pool = setup([0.05])
    r, m, sec = ask(pool, "q1")
    check(not m["hedged"] and m["winner"] is None and len(pids(d)) == 1 and r["result"].startswith("答:q1"),
          "首 token 正常 → 不对冲、只有一个进程", m)
    check(not finish(d, pool), "关池后不留进程")

    d, pool = setup([3, 0.05])
    r, m, sec = ask(pool, "q1")
    win_pid = int(re.search(r"pid=(\d+)", r["result"]).group(1))
    check(m["hedged"] and m["winner"] == "backup" and "idx=1" in r["result"] and sec < 2.0 and m["hedge_at_ms"] >= 400,
          "主路首 token 很慢 → 0.4 秒后备用重发，备用先出首 token 就用备用", (m, round(sec, 2)))
    time.sleep(0.1)
    check(not _pid_alive(pids(d)[0]), "败者（主路）被杀掉")
    r2, m2, _ = ask(pool, "q2")
    check("idx=1" in r2["result"] and "hist=1" in r2["result"] and not m2["hedged"] and not m2["spawn"],
          "下一问直接用赢的那个进程，会话是干净的（/clear 后第 1 问），不新起", r2["result"])
    check(r["total_cost_usd"] == 0.01 and m["extra_cost"] == 0, "败者没出 message_start → 额外费用记 0", m)
    check(not finish(d, pool), "关池后不留进程")

    d, pool = setup([[1.0, 0.05], 3])
    r, m, sec = ask(pool, "q1")
    check(m["hedged"] and m["winner"] == "primary" and "idx=0" in r["result"] and sec < 1.8,
          "对冲后主路先回来 → 用主路", (m, round(sec, 2)))
    time.sleep(0.1)
    check(len(pids(d)) == 2 and not _pid_alive(pids(d)[1]), "败者（备用）被杀掉")
    r2, m2, _ = ask(pool, "q2")
    check("idx=0" in r2["result"] and "hist=1" in r2["result"], "主路会话照常清空、继续用", r2["result"])
    check(not finish(d, pool), "关池后不留进程")

    d, pool = setup([5, 5])
    r, m, sec = ask(pool, "q1", timeout=1.5)
    time.sleep(0.2)
    check(r["is_error"] and "超过" in r["result"] and m["hedged"] and 1.4 < sec < 2.5,
          "备用也慢 → 总超时照样生效（从主路发出算）", (r["result"], round(sec, 2)))
    check(len(pids(d)) == 2 and not any(_pid_alive(p) for p in pids(d)), "最多对冲 1 次（只起了 1 个备用），超时后两路都杀掉",
          pids(d))
    r2, m2, _ = ask(pool, "q2")
    check("idx=2" in r2["result"] and m2["spawn"] and "hist=1" in r2["result"], "超时后下一问重起新进程", r2["result"])
    check(not finish(d, pool), "关池后不留进程")

    d, pool = setup([{"start": 0.1, "delay": 3}, 0.05])
    r, m, sec = ask(pool, "q1")
    check(m["winner"] == "backup" and m["extra_cost"] > 0 and m.get("extra_cost_est")
          and abs(r["total_cost_usd"] - (0.01 + m["extra_cost"])) < 1e-9,
          "败者已出 message_start → 按 usage 估费用，计入这次调用的费用", (m, r["total_cost_usd"]))
    check(not finish(d, pool), "关池后不留进程")

    d, pool = setup(["die", 3, 0.05])
    r, m, sec = ask(pool, "q1")
    check(not r["is_error"] and m.get("retried") and m["hedged"] and m["winner"] == "backup" and "idx=2" in r["result"],
          "主路崩了 → 照旧重起重问（重问那次仍可对冲）", (m, r["result"]))
    check(not finish(d, pool), "关池后不留进程")

    d, pool = setup([1.0, "err"])
    r, m, sec = ask(pool, "q1")
    check(not r["is_error"] and m["winner"] == "primary" and "idx=0" in r["result"] and m.get("leg_died") == ["backup"],
          "备用没出首 token 就报错 → 扔掉它，接着等主路", m)
    check(not finish(d, pool), "关池后不留进程")

    d, pool = setup([0.8], hedge=0)
    r, m, sec = ask(pool, "q1")
    check(not m["hedged"] and len(pids(d)) == 1 and "idx=0" in r["result"], "阈值 0 → 不对冲", m)
    check(not finish(d, pool), "关池后不留进程")

    # —— 以下是 plan15 B7 / plan16 B4「150 秒超时、hedged=False」排查补的情况 ——
    d, pool = setup([{"delay": 0.1, "stall": 30}, 0.05], stall=0.6)
    r, m, sec = ask(pool, "q1", timeout=8)
    check(not r["is_error"] and m["hedged"] and m["hedge_reason"] == "stall" and m["winner"] == "backup"
          and "idx=1" in r["result"] and sec < 3.5,
          "首 token 很快出了、之后流卡住 → 卡流对冲，备用先给出结果就用备用（修复前：干等到总超时）", (m, round(sec, 2)))
    check(m["ttft_ms"] is not None and m["legs"][0]["tok"] is not None and m["legs"][0]["end"] == "lost",
          "记录：首 token 时刻、每一路明细（卡住那路被杀）", m.get("legs"))
    check(not finish(d, pool), "关池后不留进程")

    d, pool = setup([{"delay": 0.1, "stall": 30}, {"delay": 0.1, "stall": 30}], stall=0.6)
    r, m, sec = ask(pool, "q1", timeout=2)
    check(r["is_error"] and "超过" in r["result"] and m["ttft_ms"] is not None and m["stall_ms"] >= 1000
          and m["hedge_reason"] == "stall" and m["first_out_ms"] is not None,
          "两路都卡 → 总超时照样生效；超时记录带 ttft / stall_ms / first_out_ms（修复前超时不带 ttft，像没出首 token）", m)
    check(not finish(d, pool), "关池后不留进程")

    d, pool = setup([{"boot": 1.5, "delay": 30}, 0.05], hedge=0.4)
    pool.prewarm("S", "sonnet")     # 预热：进程刚起、还没开始读 stdin
    r, m, sec = ask(pool, "x" * 400000)
    check(m["hedged"] and m["hedge_reason"] == "no_token" and m["winner"] == "backup" and 350 <= m["hedge_at_ms"] < 900,
          "预热没完成 + 大问题写满管道 → 照样从发出起 0.4 秒对冲（修复前 send 卡到进程开始读才开始计时）", m)
    check(not finish(d, pool), "关池后不留进程")

    d, pool = setup([{"boot": 60, "delay": 0.05}, {"boot": 60, "delay": 0.05}], hedge=0.3)
    r, m, sec = ask(pool, "x" * 400000, timeout=1.5)
    check(r["is_error"] and "超过" in r["result"] and sec < 3 and m["no_output_ms"] >= 1400 and m["first_out_ms"] is None
          and m["hedged"], "进程一直不读 stdin、一行输出都没有 → 对冲 + 总超时都生效（修复前永远卡在 send）；记 no_output_ms",
          (round(sec, 2), m))
    check(not finish(d, pool), "关池后不留进程")

    d, pool = setup([{"start": 0.05, "delay": 0.1, "stall": 30}, 0.05], stall=0)
    r, m, sec = ask(pool, "q1", timeout=1.5)
    check(r["is_error"] and not m["hedged"], "卡流阈值 0 → 不做卡流对冲", m)
    check(not finish(d, pool), "关池后不留进程")

    os.environ["DSLAGENT_HEDGE_SEC"] = "2.5"
    from tools.dslagent.legacy import pool as PL
    check(PL.Pool("/", "x", {}).hedge == 2.5 and PL.Pool("/", "x", {}, hedge=1).hedge == 1,
          "阈值可用 DSLAGENT_HEDGE_SEC / 参数配置")
    del os.environ["DSLAGENT_HEDGE_SEC"]
    check(PL.Pool("/", "x", {}).hedge == PL.HEDGE_SEC == 7.0, "默认阈值 7 秒")
    os.environ["DSLAGENT_STALL_SEC"] = "9"
    check(PL.Pool("/", "x", {}).stall == 9 and PL.Pool("/", "x", {}, stall=1).stall == 1, "卡流阈值可用 DSLAGENT_STALL_SEC / 参数配置")
    del os.environ["DSLAGENT_STALL_SEC"]
    check(PL.Pool("/", "x", {}).stall == PL.STALL_SEC == 20.0, "默认卡流阈值 20 秒")

    call = SimpleNamespace(stdout=json.dumps({"total_cost_usd": 0.02, "_pool": {"hedged": True, "winner": "backup",
                                                                                  "hedge_at_ms": 7000, "extra_cost": 0.01}}))
    cm = LR.call_meta(call)
    check(cm["hedged"] and cm["winner"] == "backup" and cm["extra_cost"] == 0.01 and cm["hedge_at_ms"] == 7000,
          "calls.json 记录带 hedged / winner / hedge_at_ms / extra_cost", cm)
    call = SimpleNamespace(stdout=json.dumps({"is_error": True, "_pool": {"hedged": False, "ttft_ms": 3000, "stall_ms": 147000,
                                                                          "no_output_ms": 900, "hedge_reason": None}}))
    cm = LR.call_meta(call)
    check(cm["ttft_ms"] == 3000 and cm["stall_ms"] == 147000 and cm["no_output_ms"] == 900 and "hedge_reason" in cm,
          "calls.json 记录带 ttft（超时也带）/ stall_ms / no_output_ms / hedge_reason", cm)


def main():
    print("补读范围：整个区间要被已读段覆盖，标识逐处命中判断")
    big = "".join(f"x{i} = {i}\n" for i in range(1, 201))
    big = big.replace("x20 = 20\n", "MAGIC_CONST_X = 20\n").replace("x180 = 180\n", "y = MAGIC_CONST_X\n")
    pj = project("bk", {"pkg/a.py": big, "tests/test_a.py": "MAGIC_CONST_X\n"})
    fn, _ = verb("补读范围", pj)
    r = fn("pkg/a.py:1-50,pkg/a.py:150-200", "pkg/a.py:40-160", "")
    # 旧版只看两端（40 在 1-50 里、160 在 150-200 里）就判「已覆盖」，这里补不到
    check(r["added"] == "pkg/a.py:40-160", "两端都在已读段里、中间没读 → 补读", r)
    check(r["segs"] == "pkg/a.py", "补读后三段连成整个文件", r["segs"])
    r = fn("pkg/a.py:1-50,pkg/a.py:51-120", "pkg/a.py:40-100", "")
    check(not r["added"], "几段拼起来连续覆盖 → 不重复补", r)
    r = fn("pkg/a.py:1-50", "MAGIC_CONST_X", "")
    # 旧版「有一处命中已覆盖就跳过」，这里补不到
    check(r["added"] == "pkg/a.py:155-200", "标识一处已读（20 行）、另一处没读（180 行）→ 补读没读的那处", r)
    check("tests/" not in r["added"], "测试文件里的命中不补读", r)
    r = fn("pkg/a.py:1-200", "MAGIC_CONST_X", "")
    check(not r["added"], "所有命中都读过了 → 不补", r)

    print("跑测试：unittest / pytest 摘要")
    _, tm = verb("跑测试", pj)
    native = (f'___ test_x ___\nTraceback (most recent call last):\n  File "{pj}/tests/test_a.py", line 7, in test_x\n'
              f'    assert total([1]) == 1\n  File "{pj}/pkg/a.py", line 2, in total\n    return sum(xs) - 1\n'
              "AssertionError\nFAILED tests/test_a.py::test_x - AssertionError\n1 failed, 3 passed in 0.02s\n")
    s = tm.summarize(pj, 1, native)
    check(s["passed"] == "否" and "tests/test_a.py:7 test_x: assert total([1]) == 1" in s["summary"]
          and "pkg/a.py:2 total" in s["summary"] and "FAILED tests/test_a.py::test_x" in s["summary"],
          "pytest --tb=native 的输出能抽出调用位置", s["summary"])
    s = tm.summarize(pj, 0, "4 passed in 0.01s\n")
    check(s["summary"] == "全部通过：4 passed in 0.01s", "pytest 全过的统计行", s)

    print("测试命令探测和 auto 判定")
    fail = project("fail", {"pkg/__init__.py": "", "pkg/calc.py": CALC, "tests/__init__.py": "",
                            "tests/test_calc.py": TEST_FAIL})
    ok = project("ok", {"pkg/__init__.py": "", "pkg/calc.py": CALC.replace(" - 1", ""), "tests/__init__.py": "",
                        "tests/test_calc.py": TEST_FAIL})
    empty = project("empty", {"pkg/calc.py": CALC})
    check("unittest discover -s tests" in (R.detect_test_cmd(fail) or ""), "有 tests/ → unittest", R.detect_test_cmd(fail))
    check(R.detect_test_cmd(empty) is None, "没有测试 → None")
    pyt = project("pyt", {"pytest.ini": "[pytest]\n", "test_x.py": "def test_x():\n    assert 1\n"})
    has_pytest = os.system(f"{R._python()} -c 'import pytest' 2>/dev/null") == 0
    want = "pytest" if has_pytest else "unittest discover"
    check(want in (R.detect_test_cmd(pyt) or ""), f"有 pytest.ini → {want}（python3 {'有' if has_pytest else '没有'} pytest）",
          R.detect_test_cmd(pyt))
    st = R.test_state(fail, R.detect_test_cmd(fail))
    check(st["runnable"] and st["failing"] and "tests/test_calc.py:7 test_total" in st["summary"],
          "test_state：能跑、有失败、摘要带调用位置", st)
    check(not list(fail.rglob("__pycache__")), "跑测试不往项目里写 __pycache__")
    tb = "Traceback (most recent call last):\n  File x\nAssertionError"
    cases = [
        ("修一下 total", None, None, "claude", "没给 project"),
        ("修一下 total", fail, None, "claude", "没有失败测试"),
        ("测试 test_total 失败了，修一下", fail, None, "dsl", "提示词有信号 + 初始失败"),
        (f"报错如下\n{tb}", fail, None, "dsl", "提示词有 Traceback + 初始失败"),
        ("加个功能", fail, R.detect_test_cmd(fail), "dsl", "给了 test_cmd + 初始失败"),
        (f"报错\n{tb}", ok, None, "claude", "有 Traceback 但初始测试全过"),
        ("新建 pkg/report.json，写进合计", ok, None, "dsl", "初始全过 + 抽到产物（新建路径）"),
        ("把 total 改叫 sum_all", ok, None, "dsl", "初始全过 + 抽到产物（标识符）"),
        ("把代码整理得好看一点", ok, None, "claude", "初始全过、抽不出产物"),
        (f"报错\n{tb}", empty, None, "claude", "探测不到测试"),
        ("新建 pkg/report.json", empty, None, "claude", "有产物但探测不到测试"),
        ("x", empty, f"{R._python()} -m unittest discover -s tests", "claude", "测试命令没跑到测试"),
    ]
    for prompt, proj, cmd, want, why in cases:
        d = R.decide_auto(prompt, str(proj) if proj else None, cmd)
        check(d["engine"] == want and d["reason"] and (want == "claude" or d["kind"] == ("task" if proj == ok else "bugfix")),
              f"auto：{why} → {want}", d)

    print("模板抽参")
    t = T.extract("用户报告：合计少算了。失败的测试：tests.test_calc.CalcTest.test_total", st["summary"], fail)
    check("total" in t["kw"].split("|"), "测试行里调用的函数进 kw", t)
    check("pkg/calc.py" in t["pre"].split(","), "test_calc.py → 预读 pkg/calc.py（不限 shopkit/）", t)
    check(any(x.startswith("tests/test_calc.py:") for x in t["pre"].split(",")), "预读失败测试附近", t)
    s, p = T.build("x", st["summary"], fail)
    main_, subs = P.split_subs(s)
    check(not P.whitelist_check(main_, subs), "模板脚本过白名单", P.whitelist_check(main_, subs))

    print("计划检查")
    raw = "好的，下面是脚本：\n```\n用包 common text code\n设 t = 跑测试\n如果 {t.passed} 等于 否\n  打印 结论：没修好\n```\n希望有帮助"
    sc, dropped = P.strip_prose(raw)
    check(sc.startswith("用包") and sc.endswith("结论：没修好") and dropped == 2, "去掉围栏和首尾说明", (sc, dropped))
    new, n, _ = P.autoclose(sc)
    check(n == 1 and new.endswith("结束"), "只差末尾的「结束」自动补上", new)
    probs = P.whitelist_check("用包 common db\n读文件 x = a.txt\n设 r = 执行 别的.zs\n问 a = hi 用 强", {})
    check(len(probs) == 4, "白名单：包、语句、执行目标、模型后缀都拦", probs)
    check(not P.whitelist_check("用包 common text code\n设 r = 执行 _plan/a.zs\n设 p = 执行 定位.zs task=x",
                                {"a.zs": "打印 hi"}), "白名单：_plan 子脚本和系统子脚本放行")

    print("AgentEngine：子脚本映射到项目外、语句白名单")
    from tools.dsl import DSLError
    from tools.dslagent.legacy.engine import LegacyEngine as AgentEngine
    from tools.mock import MockClient
    lib = TMP / "lib"
    lib.mkdir()
    (lib / "子.zs").write_text("返回 来自项目外", encoding="utf-8")
    seen = []
    eng = AgentEngine(client=MockClient(offline=True), workdir=fail, verbose=False, verbs_root=R.VERBS,
                      scripts={"定位.zs": lib / "子.zs"}, on_call=seen.append)
    eng.run("用包 common text code\n设 x = 执行 定位.zs task=a\n打印 {x}")
    check(eng.output == ["来自项目外"] and seen and seen[0]["name"] == "定位.zs", "执行 定位.zs 用的是映射的文件，调用有记录",
          (eng.output, seen))
    check(not (fail / "定位.zs").exists(), "项目里没放子脚本")
    try:
        AgentEngine(client=MockClient(offline=True), workdir=fail, verbose=False, verbs_root=R.VERBS).run(
            "读文件 x = pkg/calc.py")
        check(False, "白名单外的语句被拦")
    except DSLError as e:
        check("白名单" in str(e), "白名单外的语句被拦", e)
    eng = AgentEngine(client=MockClient(offline=True), workdir=fail, verbose=False, verbs_root=R.VERBS)
    eng.run("用包 common text code\n设 f = 列文件\n设 n = 列表长度 a,b\n打印 {f}")
    check("pkg/calc.py" in eng.output[0], "私有动词根：code 包 + 转发的 common/text 都能用", eng.output)
    check((TMP / "state").is_dir() and not (fail.parent / "notes_state.json").exists(),
          "状态写 DSLAGENT_STATE，不写项目上级目录")

    print("定位/读改测：固定说明在系统提示里，用户消息只放变化内容")
    import json
    from tools.dsl_model import _format_note, _split_format
    from tools.dslagent.legacy import prompts as PR
    lib_txt = {n: (LR.LIB / n).read_text(encoding="utf-8") for n in P.LIBS}
    check(f"格式 {PR.LOC_FORMAT}\n" in lib_txt["定位.zs"] and f"格式 {PR.RCT_FORMAT}\n" in lib_txt["读改测.zs"],
          "prompts 里的格式和 lib 脚本里 问JSON 的「格式」逐字一致")
    check(PR.LOC_TAIL == _format_note(_split_format("x 格式 " + PR.LOC_FORMAT, 0)[1]) and PR.LOC_TAIL in PR.LIB_SYSTEM
          and PR.RCT_TAIL in PR.LIB_SYSTEM, "两段格式说明都在系统提示里")
    check("包括已经看到原文的文件" in PR.LIB_SYSTEM and "segs" in PR.LIB_SYSTEM, "系统提示里有 segs 要包括已看到原文的文件的规则")
    import importlib
    check(importlib.reload(PR).LIB_SYSTEM == PR.LIB_SYSTEM and not re.search(r"/home|\d{4}-\d\d|\{\w+\}", PR.LIB_SYSTEM),
          "系统提示逐字稳定、不含路径/日期/未填变量")
    fixed = ("下一步四选一", "字段名固定为", "输出格式：", "如果上一轮改文件失败", "运行看看＝")
    check(not any(f in t for t in lib_txt.values() for f in fixed), "lib 脚本的 问JSON 不再带固定说明")
    seen2 = []

    def h(prompt, system=None):
        seen2.append((prompt, system))
        if prompt.startswith(PR.LOC_TAG):
            return json.dumps({"action": "读这些", "segs": "pkg/calc.py", "reason": "r"})
        if prompt.startswith(PR.RCT_TAG):
            return json.dumps({"action": "无需改", "reason": "r"})
        if len(seen2) == 3:
            return "不是 JSON"          # 第一次格式不对 → 带着问题重问
        return json.dumps({"action": "停"})
    for rep in (1, 2):
        mk = MockClient(handler=h, offline=True)
        eng = AgentEngine(client=mk, workdir=fail, verbose=False, verbs_root=R.VERBS,
                          scripts={n: LR.LIB / n for n in P.LIBS})
        eng.vars["task"] = f"修 total 第{rep}次"
        eng.run("用包 common text code\n设 p = 执行 定位.zs task={task} kw=def\\s+total rounds=1\n"
                "设 r = 执行 读改测.zs task={task} segs={p.segs} rounds=1\n打印 {p.outcome} {r.outcome}")
        if rep == 1:
            check(eng.output == ["找到 无需改"], "定位 → 读改测 用假模型跑通", eng.output)
    lib_calls = [c for c in seen2 if c[0].startswith((PR.LOC_TAG, PR.RCT_TAG))]
    check(len(lib_calls) == 4 and all(s == PR.LIB_SYSTEM for _, s in lib_calls), "定位/读改测两次运行都用同一份 LIB_SYSTEM",
          [s[:30] if s else s for _, s in lib_calls])
    check(not any(f in p for p, _ in lib_calls for f in fixed) and "第 1/1 轮" in lib_calls[0][0]
          and "修 total 第1次" in lib_calls[0][0], "用户消息不含固定说明、只有变化内容", lib_calls[0][0][:200])
    check(P.LOC_MARK in lib_calls[0][0] and P.RCT_MARK in lib_calls[1][0], "用户消息仍带 LOC_MARK / RCT_MARK（调用分类用）")
    # 问JSON 格式校验/重问仍生效：系统提示下回非法 JSON → 重问；重问用完报错
    seen2.clear()
    seen2.extend([None, None])
    mk = MockClient(handler=h, offline=True)
    eng = AgentEngine(client=mk, workdir=fail, verbose=False, verbs_root=R.VERBS)
    eng.run(f"用包 common text code\n问JSON d = {PR.RCT_TAG}x 格式 action:停|走 重问 1 次\n打印 {{d.action}}")
    check(eng.output == ["停"] and mk.calls[-1]["turns"] == 3 and "不符合要求" in mk.calls[-1]["messages"][-1]["content"],
          "格式不对 → 带着问题重问一次就好", (eng.output, len(mk.calls)))
    check(mk.calls[0]["messages"][0]["role"] == "user", "格式不是 LIB 那两种 → 不换系统提示、照旧附格式说明")
    bad = MockClient(handler=lambda p, s=None: json.dumps({"action": "改"}), offline=True)
    eng = AgentEngine(client=bad, workdir=fail, verbose=False, verbs_root=R.VERBS)
    try:
        eng.run(f"用包 common text code\n问JSON d = {PR.RCT_TAG}x 格式 {PR.RCT_FORMAT} 重问 1 次")
        check(False, "LIB 格式缺字段 → 重问用完报错")
    except DSLError as e:
        msgs = bad.calls[0]["messages"]
        check("格式不对" in str(e) and len(bad.calls) == 2 and msgs[0] == {"role": "system", "content": PR.LIB_SYSTEM}
              and msgs[1]["content"] == f"{PR.RCT_TAG}x", "LIB 格式：系统提示换上、用户消息剥掉格式说明，缺字段重问用完报错", e)

    test_hedge()

    print("执行器：开局全过走任务路径 / 有失败走修 bug / 探测不到测试时不动手")
    r = R.run(ok, "x", TMP / "out_ok", max_plan=0)
    check(r["kind"] == "task" and not r["fixed"] and "上限 0" in r["stop"] and r["calls"] == 0,
          "开局全过 → kind=task（规划 0 版就不调模型）", r)
    r = R.run(fail, "x", TMP / "out_fail0", max_plan=0, template=False)
    check(r["kind"] == "bugfix" and r["calls"] == 0, "开局有失败 → kind=bugfix", r)
    r = R.run(empty, "x", TMP / "out_empty")
    check(not r["fixed"] and "探测不到测试" in r["stop"] and (TMP / "out_empty" / "result.json").is_file(),
          "探测不到测试 → 直接交回，照样写 result.json", r["stop"])

    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
