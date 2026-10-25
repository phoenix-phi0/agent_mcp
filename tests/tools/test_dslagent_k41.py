# -*- coding: utf-8 -*-
"""K41：modify_module（dslproj 包）的计划默认结构改成「改 → 检查 → 没过就接着改」循环。

改动只在提示词（packs/dslproj/prompts/ 的 notes.md / example.zs / edits.md）：
教规划把改动拆成小段 #改法、每段套上就查一轮，不过进「重复 K 次」的补改循环——
每轮只修当轮检查报出的问题、带上当轮三份报告原文；终止 = 全过（终止 成功）/
预算用完（引擎 ScriptHalt 超出预期）/ 连续两轮三项检查输出完全相同（没有进展）/
K 轮用完（终止 失败）。DSL 语句（重复 / 如果 / 等于）本来就有，引擎零改动。

覆盖：①第 1 次检查不过、补改后过 → 两轮后成功；②一直不过 → 预算用完时终止，
调用次数 = 上限；③两轮检查输出完全相同 → 提前终止；④cost-cap 截停仍有效；
⑤新 example.zs 过计划检查（白名单 / 改法 / 假模型空跑）。全离线假模型，不调真模型。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_k41.py
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_k41_"))
SOL = ROOT / "tests" / "tools" / "fixtures" / "dslproj_solution"
PROMPTS = ROOT / "tools" / "dslagent" / "packs" / "dslproj" / "prompts"

from tools.dslagent.engine import AgentEngine                      # noqa: E402
from tools.dslagent import v2 as V2                                # noqa: E402
from tools.dslagent.packs import dslproj as DP_PACK                # noqa: E402
from tools.dslagent.packs.dslproj import project as P              # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


GOOD = (SOL / "services" / "graph.zs").read_text(encoding="utf-8")
OLD_FN = "  公开 函数 取知识点 code\n    设 p = 查一行 app.db graph_point_by_code code={code}\n    返回 {p}\n  结束"
BAD = GOOD.replace(OLD_FN, "  公开 函数 取知识点 code\n    报错 501 未实现\n  结束", 1)
assert BAD != GOOD, "夹具构造失败：参考实现里找不到 取知识点 函数原文"

GRAPH_SKEL = """业务 graph
  用包 db

  公开 函数 取知识点 code
    报错 501 未实现
  结束

  公开 函数 加边 src dst
    报错 501 未实现
  结束
结束
"""

LOOP_PLAN = """用包 common text code dslproj
预算 调用 {budget} 秒 900
设 m = graph
设 c = 加载检查 {m}
设 d = 比对约定 {m}
设 t = 跑用例 {m}
如果 {c.ok} 等于 是 且 {d.consistent} 等于 是 且 {t.all_passed} 等于 是
  终止 成功 一次就过
结束
设 prev.c = 未跑
设 prev.d = 未跑
设 prev.t = 未跑
重复 {rounds} 次 计数 k
  如果 {c.problems} 等于 {prev.c} 且 {d.diffs} 等于 {prev.d} 且 {t.failures} 等于 {prev.t}
    终止 失败 连续两轮三项检查输出完全相同（补改没有进展）
  结束
  设 prev.c = {c.problems}
  设 prev.d = {d.diffs}
  设 prev.t = {t.failures}
  设 files = 读片段 services/graph.zs:全文
  设 inp.文件 = {files}
  设 inp.加载检查 = {c.problems}
  设 inp.比对约定 = {d.diffs}
  设 inp.跑用例 = {t.failures}
  设 logic = 只修入参报告里报出的问题
  设 r = 派任务 第{k}轮补改 {inp} {logic} edits:列表,note:文本
  如果 {r.status} 不等于 成功
    终止 失败 补改没成：{r.reason}
  结束
  设 res = 改文件 {r.result}
  如果 {res.ok} 不等于 是
    终止 失败 补改没套上：{res.msg}
  结束
  设 c = 加载检查 {m}
  设 d = 比对约定 {m}
  设 t = 跑用例 {m}
  如果 {c.ok} 等于 是 且 {d.consistent} 等于 是 且 {t.all_passed} 等于 是
    终止 成功 第 {k} 轮补改后三项检查全过
  结束
结束
终止 失败 补改 {rounds} 轮仍不过
"""


def bad_project(name):
    """模块 graph 的夹具：约定 / 实体 / 查询 / 接口用参考实现，services/graph.zs 的 取知识点 函数体换成 报错 501。"""
    p = TMP / name
    shutil.rmtree(p, ignore_errors=True)
    shutil.copytree(SOL, p)
    (p / "services" / "graph.zs").write_text(BAD, encoding="utf-8")
    return p


def skeleton(name):
    """照 test_dslagent_dslproj.skeleton：只有 services/graph.zs 骨架，上游 progress 用参考实现（给 example.zs 的计划检查用）。"""
    p = TMP / name
    shutil.rmtree(p, ignore_errors=True)
    (p / "contracts").mkdir(parents=True)
    for f in (SOL / "contracts").glob("*.md"):
        shutil.copy(f, p / "contracts" / f.name)
    for g in P.scope_globs("progress"):
        for f in SOL.glob(g):
            dst = p / f.relative_to(SOL)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(f, dst)
    (p / "services").mkdir(exist_ok=True)
    (p / "services" / "graph.zs").write_text(GRAPH_SKEL, encoding="utf-8")
    return p


class FakeFixer:
    """假模型客户端（v2.Client 同款接口）：每次 派任务 回一份 edits，模式决定改什么。
    fix = 把 services/graph.zs 换回参考实现（第 2 轮检查就全过）；
    noprogress = 只在文件尾加注释（三项检查输出不变 → 没进展）；
    worsen = 把当前 取知识点<又…> 再多补一个「又」（每轮检查输出都不同 → 只能靠预算停）。"""

    offline = True

    def __init__(self, workdir, mode):
        self.workdir = Path(workdir)
        self.mode = mode
        self.calls = 0

    def _graph(self):
        return (self.workdir / "services" / "graph.zs").read_text(encoding="utf-8")

    def _reply(self, edits):
        return json.dumps({"result": {"edits": edits, "note": "假补改"}, "status": "成功", "reason": ""},
                          ensure_ascii=False)

    def chat_messages(self, messages, temperature=None, model=None, **kw):
        self.calls += 1
        cur = self._graph()
        if self.mode == "fix":
            return self._reply([{"file": "services/graph.zs", "old": cur, "new": GOOD}])
        if self.mode == "noprogress":
            return self._reply([{"file": "services/graph.zs", "old": cur, "new": cur + "\n# 这行注释不影响任何检查\n"}])
        name = "取知识点"
        while "公开 函数 " + name in cur:      # 当前已被改名的函数（取知识点 / 取知识点又 / …）
            name += "又"
        if name == "取知识点":
            name = "取知识点又"
        return self._reply([{"file": "services/graph.zs", "old": cur, "new": cur.replace("公开 函数 取知识点", "公开 函数 " + name, 1)}])

    def chat(self, prompt, system=None, temperature=None, model=None, **kw):
        return self.chat_messages([])


def run_plan(name, mode, budget, rounds):
    p = bad_project(name)
    fake = FakeFixer(p, mode)
    eng = AgentEngine(client=fake, workdir=p, verbose=False, verbs_root=ROOT / "tools" / "dslagent" / "verbs")
    eng.run(LOOP_PLAN.replace("{budget}", str(budget)).replace("{rounds}", str(rounds)))
    return eng, fake


# ------------------------------------------------------------------ ① 不过 → 补改 → 过


def test_fail_then_pass():
    print("①检查第 1 次不过、补改后过 → 循环两轮后成功（派 1 次补改）")
    eng, fake = run_plan("t1", "fix", budget=4, rounds=3)
    h = eng.halted
    check(h is not None and h.get("status") == "成功", "终止 成功", h)
    check("第 1 轮补改后" in str(h and h.get("reason")), "第 1 轮补改后通过", h and h.get("reason"))
    check(fake.calls == 1, "只派了 1 次补改（第一轮修好就不派）", fake.calls)
    check((eng.workdir / "services" / "graph.zs").read_text(encoding="utf-8") == GOOD, "坏文件被补改成参考实现")


# ------------------------------------------------------------------ ② 一直不过 → 预算用完


def test_budget_out():
    print("②一直不过 → 预算用完时终止，调用次数 = 上限（引擎 ScriptHalt 超出预期）")
    eng, fake = run_plan("t2", "worsen", budget=2, rounds=5)
    h = eng.halted
    check(h is not None and h.get("status") == "超出预期", "预算用完按 超出预期 终止（不用计划自己写）", h)
    check("预算用完" in str(h and h.get("reason")) and "上限 2 次" in str(h and h.get("reason")), "原因写明预算用满", h and h.get("reason"))
    check(fake.calls == 2, "实际模型调用 = 预算上限 2（第 3 次没发出）", fake.calls)
    check(eng.usage.calls == 2, "Usage 计到 2", eng.usage.calls)


# ------------------------------------------------------------------ ③ 两轮检查完全相同 → 提前终止


def test_no_progress():
    print("③补改后两轮检查输出完全相同 → 提前终止，不再空转派任务")
    eng, fake = run_plan("t3", "noprogress", budget=4, rounds=3)
    h = eng.halted
    check(h is not None and h.get("status") == "失败", "终止 失败", h)
    check("完全相同" in str(h and h.get("reason")), "原因写明没有进展", h and h.get("reason"))
    check(fake.calls == 1, "只派了 1 次补改就停（没把 3 轮烧完）", fake.calls)


# ------------------------------------------------------------------ ④ cost-cap 照旧先生效（v3 层，K36 同款）


class FakeB:
    def __init__(self, scripts=None):
        self.scripts = scripts or {}
        self.calls = []

    def __call__(self, system, user, tag, timeout, model=None, **kw):
        self.calls.append({"tag": tag, "user": user})
        return self.scripts.get(tag, "好的")


def test_cost_cap():
    print("④cost-cap 照旧先生效：花费到上限就截停，循环轮数没用完也停")
    from tools.dslagent import ledger as LG
    from tools.dslagent.v3 import core
    stub = TMP / "v2stub.py"
    stub.write_text("import sys, os, json\n"
                    "a = sys.argv\n"
                    "rec = a[a.index('--out') + 1]\n"
                    "os.makedirs(rec, exist_ok=True)\n"
                    "print(json.dumps({'fixed': False, 'calls': 6, 'cost': 5.0, 'stop': 'v2 验收没过'}))\n",
                    encoding="utf-8")
    p = TMP / "cap_proj"
    (p / "plan").mkdir(parents=True, exist_ok=True)
    (p / "plan" / "audit2.json").write_text(json.dumps(
        {"result": "module_issue", "issues": [{"module": "graph", "issue": "少接口", "basis": "contracts/graph.md"}]},
        ensure_ascii=False), encoding="utf-8")
    (p / "entities").mkdir(exist_ok=True)
    (p / "entities" / "graph.entity").write_text("实体", encoding="utf-8")
    fk = FakeB(scripts={"v3_agent_modify_module": {"reason": "v2 验收没过", "cost": 5.0}})
    out = TMP / "cap_out"
    res = core.run_entry("change2", p, out, "需求", backend=fk, module_cmd=[sys.executable, str(stub)],
                         module_calls=8, cost_cap=1.0)
    check(res["status"] == "超出预期" and "上限" in (res.get("reason") or ""), "花费超 1.0 以 超出预期 截停（module_calls=8 没用完也停）", res)
    rows = [r for r in LG.read_rows(out) if r.get("role") == "modify_module"]
    check(len(rows) == 1 and rows[0].get("v2_calls") == 8, "截停前那一笔照记 v2_calls=8", rows)


# ------------------------------------------------------------------ ⑤ 新 example.zs 过计划检查；提示词讲清循环


def test_example_and_prompts():
    print("⑤新 example.zs 过 白名单 / 改法 / 假模型空跑；notes / edits 讲清循环与终止")
    ex = (PROMPTS / "example.zs").read_text(encoding="utf-8")
    for lit in ("设 t = 跑用例 {m}", "{t.all_passed}", "{t.failures}", "重复 6 次 计数 k", "等于 {prev.c}"):
        check(lit in ex, f"example.zs 保留可替换字面量 / 循环要素：{lit}")
    p = skeleton("ex_skel")
    err, *_ = V2.check(p, TMP / "ex_work", ex, "模块 graph", pack=DP_PACK)
    check(err == "", "example.zs：白名单 / 改法 / 空跑都通过", err)

    bad = ex.replace("设 t = 跑用例 {m}", "设 t = 加载检查 {m}").replace("{t.all_passed}", "{t.ok}") \
            .replace("{t.failures}", "{t.problems}")
    err, *_ = V2.check(p, TMP / "ex_work2", bad, "模块 graph", pack=DP_PACK)
    check("跑用例" in err, "计划检查：把 跑用例 都换掉后报「没有 跑用例」", err)

    s = DP_PACK.PLAN_SYSTEM()
    for lit in ("重复 K 次", "预算 N − 1", "完全相同", "超出预期 终止"):
        check(lit in s, f"notes.md（进了 PLAN_SYSTEM）讲清：{lit}")
    ed = (PROMPTS / "edits.md").read_text(encoding="utf-8")
    check("同一文件的全部改动放同一段" in ed, "edits.md：多段拆分的同文件规则", ed)


if __name__ == "__main__":
    test_fail_then_pass()
    test_budget_out()
    test_no_progress()
    test_cost_cap()
    test_example_and_prompts()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
