# -*- coding: utf-8 -*-
"""K36：放宽 change2 修改代理（modify_module）的模型调用次数。

--max-turns（缺省 8）→ run_entry(module_calls=N) → 派代理(v2_calls=N) → v2 子进程
--budget-calls N → 计划「预算 调用 N」只放宽不收紧（v2.bump_budget）。
覆盖：bump_budget 各情形、CLI 缺省值与传参、v2_calls 透传（假 backend + 桩子进程）、
agents.jsonl 记 v2_calls、cost-cap 仍提前截停。全离线假模型，不调真模型。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_k36.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_k36_"))

from tools.dslagent import ledger as LG                          # noqa: E402
from tools.dslagent import roles as R                            # noqa: E402
from tools.dslagent import v2 as V2                              # noqa: E402
from tools.dslagent.v3 import core                               # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


def fresh(name):
    p = TMP / name
    p.mkdir(parents=True, exist_ok=True)
    return p


# ------------------------------------------------------------------ bump_budget（只放宽不收紧）


def test_bump_budget():
    print("bump_budget：计划里「预算 调用 N」提到下限，只放宽不收紧")
    check(V2.bump_budget("预算 调用 2 秒 600\n", 8) == "预算 调用 8 秒 600\n", "N=2 提到 8，秒数、行尾换行保留", repr(V2.bump_budget("预算 调用 2 秒 600\n", 8)))
    check(V2.bump_budget("预算 调用 2 秒 600\n终止 成功\n", 8) == "预算 调用 8 秒 600\n终止 成功\n", "替换后下一行不粘连")
    check(V2.bump_budget("预算 调用 12 秒 600\n", 8) == "预算 调用 12 秒 600\n", "N=12 大于 8 不收紧，行尾换行也原样")
    check(V2.bump_budget("预算 调用 8\n", 8) == "预算 调用 8\n", "没有秒数部分也行（换行保留）")
    check(V2.bump_budget("用包 common\n终止 成功\n", 8) == "用包 common\n终止 成功\n", "没有预算行原样")
    check(V2.bump_budget("预算 调用 {n} 秒 600\n", 8) == "预算 调用 {n} 秒 600\n", "N 是变量不碰")
    check(V2.bump_budget("预算 调用 2 秒 600\n", 0) == "预算 调用 2 秒 600\n" and V2.bump_budget("预算 调用 2 秒 600\n", None) == "预算 调用 2 秒 600\n",
          "min_calls 0 / None = 不干预")
    check(V2.bump_budget("预算 调用 2 秒 600\n预算 调用 3\n", 8).count("预算 调用 8") == 1, "只改第一处（count=1）", V2.bump_budget("预算 调用 2 秒 600\n预算 调用 3\n", 8))


# ------------------------------------------------------------------ CLI 参数


def test_cli():
    print("CLI：--max-turns 缺省 8、可传参、只对 change2 生效")
    cp = subprocess.run([sys.executable, "-m", "tools.dslagent", "v3", "change2", "-h"], cwd=ROOT, capture_output=True, text=True)
    check("--max-turns" in cp.stdout and "缺省 8" in cp.stdout, "change2 -h 有 --max-turns 且写明缺省 8", cp.stdout + cp.stderr)
    cp = subprocess.run([sys.executable, "-m", "tools.dslagent", "v3", "audit2", "-h"], cwd=ROOT, capture_output=True, text=True)
    check("（change2）" in cp.stdout and "--max-turns" in cp.stdout, "audit2 -h 里 --max-turns 标明（change2）专用", cp.stdout)

    from tools.dslagent import __main__ as M
    import argparse
    src = (ROOT / "tools" / "dslagent" / "__main__.py").read_text(encoding="utf-8")
    check('v.add_argument("--max-turns", type=int, default=8' in src, "参数缺省值写在 __main__.py：default=8")
    check('a.action == "change2"' in src and "module_calls" in src, "module_calls 只在 change2 时传给 run_entry")


# ------------------------------------------------------------------ v2_calls 透传（假 backend / 桩子进程）


def test_dispatch_v2_calls():
    print("派代理 v2_calls：透传到 v2 子进程 --budget-calls，账本记 v2_calls")
    stub = TMP / "v2stub.py"
    stub.write_text("""import sys, os, json
a = sys.argv
proj = a[a.index('--project') + 1]
rec = a[a.index('--out') + 1]
os.makedirs(rec, exist_ok=True)
open(os.path.join(rec, 'argv.json'), 'w').write(json.dumps({'argv': a}))
print(json.dumps({'fixed': True, 'calls': 6, 'cost': 0.4, 'stop': ''}))
""", encoding="utf-8")
    proj = fresh("proj")
    (proj / "services").mkdir(exist_ok=True)
    cmd = [sys.executable, str(stub)]
    o = fresh("o1")
    r = R.dispatch_agent("modify_module", "t", {"模块": "graph"}, out_dir=o, project=proj, module_cmd=cmd, v2_calls=8)
    check(r["status"] == "ok", "modify_module 跑通（桩）", r)
    info = json.loads(next((o / "agents" / "modify_module").glob("*/v2/argv.json")).read_text(encoding="utf-8"))
    a = info["argv"]
    check("--budget-calls" in a and a[a.index("--budget-calls") + 1] == "8", "子进程 argv 带 --budget-calls 8", a)
    row = LG.read_rows(o)[0]
    check(row.get("v2_calls") == 8 and row.get("num_turns") == 6, "agents.jsonl 记 v2_calls=8（上限）、num_turns=6（实际）", row)

    # 不传 v2_calls：子进程不带 --budget-calls，账本不记 v2_calls
    o2 = fresh("o2")
    R.dispatch_agent("modify_module", "t", {"模块": "graph"}, out_dir=o2, project=proj, module_cmd=cmd)
    info = json.loads(next((o2 / "agents" / "modify_module").glob("*/v2/argv.json")).read_text(encoding="utf-8"))
    check("--budget-calls" not in info["argv"], "不传时子进程不带 --budget-calls（不干预）")
    check(LG.read_rows(o2)[0].get("v2_calls") is None, "不传时账本不记 v2_calls")


# ------------------------------------------------------------------ change2 端到端（假模型）


class Fake:
    """假模型：记录调用；scripts 按 tag 给回复（用完用最后一个）。"""

    def __init__(self, scripts=None):
        self.scripts = scripts or {}
        self.calls = []

    def __call__(self, system, user, tag, timeout, model=None, **kw):
        self.calls.append({"tag": tag, "user": user})
        reps = self.scripts.get(tag, ["好的"])
        rep = reps[-1] if len(reps) == 1 else (reps.pop(0) if self.calls.count(tag) <= len(reps) else reps[-1])
        return rep


def setup_change2(name):
    p = fresh(name)
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "audit2.json").write_text(json.dumps(
        {"result": "module_issue", "issues": [{"module": "graph", "issue": "少一个接口", "basis": "contracts/graph.md"}]}, ensure_ascii=False), encoding="utf-8")
    (p / "entities").mkdir(exist_ok=True)
    (p / "entities" / "graph.entity").write_text("知识点", encoding="utf-8")
    return p


def test_change2_module_calls():
    print("change2 端到端：--max-turns 透传到每个 modify_module；不传时 None")
    fk = Fake(scripts={"v3_agent_modify_module": ["改好了"]})
    p = setup_change2("c2a")
    res = core.run_entry("change2", p, fresh("c2a_out"), "需求", backend=fk, module_cmd=["stub"])
    rows = [r for r in LG.read_rows(fresh("c2a_out")) if r.get("role") == "modify_module"]
    check(res["status"] == "成功" and len(rows) == 1 and rows[0].get("v2_calls") is None, "不传 --max-turns：v2_calls 不记（None = 不干预）", rows)

    fk = Fake(scripts={"v3_agent_modify_module": ["改好了"]})
    p = setup_change2("c2b")
    res = core.run_entry("change2", p, fresh("c2b_out"), "需求", backend=fk, module_cmd=["stub"], module_calls=8)
    rows = [r for r in LG.read_rows(fresh("c2b_out")) if r.get("role") == "modify_module"]
    check(res["status"] == "成功" and len(rows) == 1 and rows[0].get("v2_calls") == 8 and rows[0].get("num_turns") == 1,
          "module_calls=8：agents.jsonl 记 v2_calls=8（上限）+ num_turns（实际）", rows)

    # 传 0 = 不干预
    fk = Fake(scripts={"v3_agent_modify_module": ["改好了"]})
    p = setup_change2("c2c")
    res = core.run_entry("change2", p, fresh("c2c_out"), "需求", backend=fk, module_cmd=["stub"], module_calls=0)
    rows = [r for r in LG.read_rows(fresh("c2c_out")) if r.get("role") == "modify_module"]
    check(res["status"] == "成功" and rows[0].get("v2_calls") in (None, 0), "module_calls=0：不干预（子进程不带 --budget-calls）", rows)


def test_change2_cost_cap():
    print("cost-cap 照旧先生效：超花费上限提前截停，轮数没用完也停")
    fk = Fake(scripts={"v3_agent_modify_module": [{"reason": "v2 验收没过", "cost": 5.0}]})
    p = setup_change2("c2d")
    res = core.run_entry("change2", p, fresh("c2d_out"), "需求", backend=fk, module_cmd=["stub"],
                         module_calls=8, cost_cap=1.0)
    check(res["status"] == "超出预期" and "上限" in (res.get("reason") or ""), "花费超 1.0 以「超出预期」截停（即使 module_calls=8）", res)
    rows = [r for r in LG.read_rows(fresh("c2d_out")) if r.get("role") == "modify_module"]
    check(len(rows) == 1 and rows[0].get("v2_calls") == 8, "截停前那一笔照记 v2_calls=8", rows)


if __name__ == "__main__":
    test_bump_budget()
    test_cli()
    test_dispatch_v2_calls()
    test_change2_module_calls()
    test_change2_cost_cap()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
