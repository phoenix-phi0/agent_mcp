# -*- coding: utf-8 -*-
"""K77：v3 audit2 的模块范围（--modules）、范围外问题不终止（skipped_issues）、--cost-cap 每次模型调用前检查。

覆盖（全离线：假模型 / 桩子进程，不调真模型）：
  ① 范围参数：只对点名模块派任务，audit2.json 只含点名模块的问题并带 scope；范围外模块的回归不过进 skipped_issues
  ② 范围外 contract_issue（核查员给 owner 指向范围外模块）被记下、不终止，后面的模块照审；范围内自己的 contract_issue 照旧
  ③ cost-cap：每次模型调用前检查——超了就以「超出预期」停、写明已花费，不再多调一次
  ④ 不传范围：行为同旧（派任务提示不带 owner、audit2.json 没有 scope / skipped_issues、旧 cost 行为）
  ⑤ change2 读带新增字段的 audit2.json 不受影响；fix2 把范围传给 audit2；CLI 校验 --modules

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_k77.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "tools"))

import test_dslagent_v3 as T                                       # noqa: E402  复用 v3 测试的假模型 / 参考项目（import 不会跑它的用例）
from tools.dslagent.v3 import core, scaffold as SF, top as VT      # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(("  ✓ " if cond else "  ✗ ") + msg + ("" if cond or extra == "" else f"\n      {str(extra)[:1500]}"))


class Costly(T.Fake):
    """每次调用花 per 美元的假模型。"""

    def __init__(self, per, scripts=None):
        super().__init__(scripts=scripts)
        self.per = per

    def __call__(self, system, user, tag, timeout, **kw):
        r = super().__call__(system, user, tag, timeout, **kw)
        r = dict(r) if isinstance(r, dict) else {"text": r}
        r["cost"] = self.per
        return r


def reply(result, issue="", basis="", owner=""):
    r = {"result": result}
    if issue:
        r.update(issue=issue, basis=basis)
    if owner:
        r["owner"] = owner
    return json.dumps({"result": r, "status": "成功", "reason": ""}, ensure_ascii=False)


ALLOK = {f"dsl0{k}": [reply("ok")] for k in (1, 2, 3)}


def project():
    p = T.full_project()
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "top.zs").write_text(T.TOP3, encoding="utf-8")
    return p


def audit(p, scripts, scope=None, backend=None, **kw):
    fk = backend or T.Fake(scripts=scripts)
    extra = {"llm": "sonnet"}
    if scope:
        extra.update(scope="|" + "|".join(scope) + "|", modules=",".join(scope))
    res = core.run_entry("audit2", p, T.fresh("k77_out"), "需求", extra_vars=extra, backend=fk, **kw)
    aj = p / "plan" / "audit2.json"
    return res, (json.loads(aj.read_text(encoding="utf-8")) if aj.is_file() else None), fk


def dsl_calls(fk):
    return [c for c in fk.calls if c["tag"].startswith("dsl")]


def test_scope_only_named():
    print("①范围参数：只审点名模块；范围外回归不过记进 skipped_issues")
    p = project()
    res, aj, fk = audit(p, {"dsl01": [reply("module_issue", "vocab 少接口", "services/vocab.zs")]}, scope=["vocab"])
    check(res["status"] == "成功" and len(dsl_calls(fk)) == 1, "只派 1 次派任务（点名 1 个模块，共 3 个有代码）", [c["tag"] for c in fk.calls])
    check("vocab" in dsl_calls(fk)[0]["user"].split("\n")[0] or "「vocab」" in dsl_calls(fk)[0]["user"], "派的就是 vocab", dsl_calls(fk)[0]["user"][:200])
    check(aj["result"] == "module_issue" and [i["module"] for i in aj["issues"]] == ["vocab"] and aj["scope"] == "vocab", "audit2.json：只含 vocab 的问题，带 scope", aj)
    check("skipped_issues" not in aj, "没有被跳过的问题时不写 skipped_issues", aj)

    broken = (p / "services" / "graph.zs").read_text(encoding="utf-8")
    (p / "services" / "graph.zs").write_text(broken.replace("报错 404 没有这个知识点", "报错 400 没有这个知识点", 1), encoding="utf-8")
    res, aj, fk = audit(p, {"dsl01": [reply("ok")]}, scope=["vocab"])
    sk = aj.get("skipped_issues") or []
    check(aj["result"] == "ok" and not aj.get("issues"), "graph 回归不过但在范围外：不影响 result（ok）", aj)
    check(len(sk) == 1 and sk[0]["module"] == "graph" and sk[0]["kind"] == "regression" and sk[0]["basis"] == "全量回归", "范围外的回归不过记进 skipped_issues", sk)
    res, aj, fk = audit(p, {}, scope=["graph", "vocab"])
    check(aj["result"] == "module_issue" and any(i["module"] == "graph" and i["basis"] == "全量回归" for i in aj["issues"]) and "skipped_issues" not in aj,
          "graph 在范围内：回归不过照旧算 module_issue", aj)
    (p / "services" / "graph.zs").write_text(broken, encoding="utf-8")


def test_scope_foreign_contract_issue():
    print("②范围外 contract_issue 记下不终止；范围内自己的 contract_issue 照旧")
    p = project()
    scripts = {"dsl01": [reply("contract_issue", "引用了 progress 里没有的函数", "contracts/progress.md", owner="progress")],
               "dsl02": [reply("module_issue", "少接口", "services/vocab.zs")]}
    res, aj, fk = audit(p, scripts, scope=["graph", "vocab"])
    sk = aj.get("skipped_issues") or []
    check(res["status"] == "成功" and len(dsl_calls(fk)) == 2, "范围外的 contract_issue 没终止：两个范围内模块都审了", [c["tag"] for c in fk.calls])
    check(aj["result"] == "module_issue" and [i["module"] for i in aj["issues"]] == ["vocab"], "result 只由范围内问题决定（module_issue，只含 vocab）", aj)
    check(len(sk) == 1 and sk[0]["owner"] == "progress" and sk[0]["kind"] == "contract_issue" and sk[0]["module"] == "graph"
          and sk[0]["issue"] and sk[0]["basis"] == "contracts/progress.md" and sk[0]["reason"], "skipped_issues 记了 module/owner/kind/issue/basis/reason", sk)
    check("问题出在哪个模块" in dsl_calls(fk)[0]["user"], "给了范围时派任务提示里要求写 owner")

    res, aj, fk = audit(p, {"dsl01": [reply("contract_issue", "约定自相矛盾", "contracts/graph.md")]}, scope=["graph", "vocab"])
    check(aj["result"] == "contract_issue" and [i["module"] for i in aj["issues"]] == ["graph"] and "skipped_issues" not in aj,
          "范围内自己的 contract_issue（没写 owner）：仍 result=contract_issue", aj)
    res, aj, fk = audit(p, {"dsl01": [reply("contract_issue", "约定自相矛盾", "contracts/graph.md", owner="graph 的约定")]}, scope=["graph", "vocab"])
    check(aj["result"] == "contract_issue" and "skipped_issues" not in aj, "owner 写成「graph 的约定」（含本模块名）：不当成范围外", aj)
    res, aj, fk = audit(p, {"dsl01": [reply("contract_issue", "依赖 vocab 的约定有错", "contracts/vocab.md", owner="vocab")]}, scope=["graph", "vocab"])
    check(aj["result"] == "contract_issue" and "skipped_issues" not in aj, "owner 指向范围内的别的模块：算范围内问题", aj)


def test_cost_cap_before_call():
    print("③cost-cap：每次模型调用前检查")
    p = project()
    fk = Costly(0.6, ALLOK)
    res, aj, _ = audit(p, None, backend=fk, cost_cap=1.0)
    check(res["status"] == "超出预期" and "已花费" in res["reason"] and "上限 $1.00" in res["reason"], "超 1.0 以 超出预期 停，原因写明已花费", res)
    check(len(dsl_calls(fk)) == 2 and abs(res["花费"] - 1.2) < 1e-6, "第 2 次后花费 1.2 ≥ 1.0，第 3 次调用没发出（共 2 次，不是 3 次）", (len(dsl_calls(fk)), res["花费"]))
    fk = Costly(0.6, ALLOK)
    res, aj, _ = audit(p, None, backend=fk, cost_cap=0.5)
    check(res["status"] == "超出预期" and len(dsl_calls(fk)) == 1, "上限 0.5：第 1 次后就停（模块之间之外，每次调用前都查）", (res["status"], len(dsl_calls(fk))))
    fk = Costly(0.6, ALLOK)
    res, aj, _ = audit(p, None, backend=fk, cost_cap=5.0)
    check(res["status"] == "成功" and len(dsl_calls(fk)) == 3 and aj["result"] == "ok", "上限够用：照常 3 次、ok", res)
    fk = Costly(0.6, ALLOK)
    res, aj, _ = audit(p, None, backend=fk)
    check(res["status"] == "成功" and len(dsl_calls(fk)) == 3, "不传 --cost-cap：不限", res)


def test_unscoped_same_as_old():
    print("④不传范围：行为同旧")
    p = project()
    res, aj, fk = audit(p, ALLOK)
    check(aj == {"result": "ok"} and len(dsl_calls(fk)) == 3, "全 ok：audit2.json == {result: ok}，3 次派任务", aj)
    check("问题出在哪个模块" not in dsl_calls(fk)[0]["user"], "派任务提示不带 owner")
    res, aj, fk = audit(p, dict(ALLOK, dsl01=[reply("contract_issue", "矛盾", "contracts/graph.md", owner="progress")]))
    check(aj["result"] == "contract_issue" and [i["module"] for i in aj["issues"]] == ["graph"] and set(aj) == {"result", "issues"}
          and len(dsl_calls(fk)) == 3, "owner 被忽略：contract_issue 照旧，字段只有 result/issues，其它模块照审", aj)


def test_change2_fix2_cli():
    print("⑤change2 兼容新字段；fix2 传范围；CLI 校验 --modules")
    p = T.project_with_contracts(("graph", "vocab", "progress"))
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "top.zs").write_text(T.TOP3, encoding="utf-8")
    SF.gen_skeleton(p, VT.load(T.TOP3))
    state = T.fresh("k77_st") / "state"
    T.stub_env(state)
    (p / "plan" / "audit2.json").write_text(json.dumps(
        {"result": "module_issue", "scope": "graph", "issues": [{"module": "graph", "issue": "少一个接口", "basis": "contracts/graph.md"}],
         "skipped_issues": [{"module": "vocab", "owner": "progress", "kind": "contract_issue", "issue": "x", "basis": "y", "reason": "范围外"}]},
        ensure_ascii=False), encoding="utf-8")
    fk = T.Fake(scripts={"v3_agent_modify_module": ["改好了"]})
    res = core.run_entry("change2", p, T.fresh("k77_c2"), "需求", backend=fk, module_cmd=T.CMD)
    ag = [c for c in fk.calls if c["tag"] == "v3_agent_modify_module"]
    r = res.get("returned") or {}
    check(res["status"] == "成功" and len(ag) == 1 and ag[0]["user"].split("\n")[0] == "模块 graph" and len(r.get("changed", [])) == 1,
          "change2：带 scope / skipped_issues 的 audit2.json 照常，只改 issues 里的 graph，不碰 skipped 的 vocab", (res, [c["tag"] for c in fk.calls]))

    p = project()
    fk = T.Fake(scripts={"dsl01": [reply("ok")]})
    res = core.run_entry("fix2", p, T.fresh("k77_f2"), "需求", extra_vars={"llm": "sonnet", "rounds": 2, "scope": "|vocab|", "modules": "vocab"}, backend=fk, module_cmd=T.CMD)
    check(res["status"] == "成功" and len(dsl_calls(fk)) == 1, "fix2：范围传给 audit2（只审 vocab 1 次，ok 即成功）", res)
    fk = T.Fake(scripts=ALLOK)
    res = core.run_entry("fix2", p, T.fresh("k77_f2"), "需求", extra_vars={"llm": "sonnet", "rounds": 2}, backend=fk, module_cmd=T.CMD)
    check(res["status"] == "成功" and len(dsl_calls(fk)) == 3, "fix2 不给范围：审 3 个模块（同旧）", res)

    cp = subprocess.run([sys.executable, "-m", "tools.dslagent", "v3", "-h"], cwd=ROOT, capture_output=True, text=True)
    check("--modules" in cp.stdout and "skipped_issues" in cp.stdout, "CLI v3 -h 列出 --modules 并说明 skipped_issues", cp.stdout[-300:])
    rq = T.fresh("k77_req") / "r.md"
    rq.write_text("需求", encoding="utf-8")
    base = [sys.executable, "-m", "tools.dslagent", "v3", "audit2", "--req", str(rq), "--out", str(T.fresh("k77_cli_o"))]
    cp = subprocess.run(base + ["--project", str(p), "--modules", "vocab,nope"], cwd=ROOT, capture_output=True, text=True)
    check(cp.returncode == 2 and "nope" in cp.stderr, "CLI：--modules 里有不存在的模块 → 退出码 2 并点名", cp.stderr[-300:])
    cp = subprocess.run(base + ["--project", str(T.fresh("k77_cli_p")), "--modules", " , "], cwd=ROOT, capture_output=True, text=True)
    check(cp.returncode == 2, "CLI：--modules 为空 → 退出码 2", cp.stderr[-200:])


if __name__ == "__main__":
    test_scope_only_named()
    test_scope_foreign_contract_issue()
    test_cost_cap_before_call()
    test_unscoped_same_as_old()
    test_change2_fix2_cli()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
