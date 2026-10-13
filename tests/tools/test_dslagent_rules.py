# -*- coding: utf-8 -*-
"""tools/dslagent 执行中的逻辑规则（reason.py + rules/*.dl + 动词 推理/留底/撤回），不调模型：
测试变化四种情况与同错两次、读改测.zs 用假模型跑「失败变多→撤回」「同错两次→升级」、
完成核对的抽取与检查（含假成功样例）、安全约束（删仍被引用/未等价迁移的数据、覆盖没点名的数据、测试文件、越界、
退回规划前回滚）、runner 里完成核对补做一轮、开关 DSLAGENT_RULES=0。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_rules.py
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_rules_"))
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
os.environ["DSLAGENT_TMP"] = str(TMP / "tmp")
os.environ["CBATCH_CLAUDE"] = "/bin/true"
os.environ.pop("DSLAGENT_RULES", None)
(TMP / "state").mkdir()

from tools.dslagent import reason as R          # noqa: E402
from tools.dslagent.legacy import reason_rules as RR   # noqa: E402
from tools.dslagent.legacy import run as LR            # noqa: E402
from tools.dslagent import runner as RN         # noqa: E402
from tools.dslagent.legacy.engine import LegacyEngine as AgentEngine   # noqa: E402
from tools.mock import MockClient               # noqa: E402

PY = sys.executable
PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {msg}")
    else:
        FAIL += 1
        print(f"  ✗ {msg}  {str(extra)[:300]}")


def project(name, files):
    d = TMP / name
    for rel, text in files.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text, encoding="utf-8")
    return d


def verb(name, ws):
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"_t_{name}", RN.DEFS / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.WORKSPACE = ws
    return m


LIB = {
    "lib/__init__.py": "",
    "lib/storage.py": 'import csv, os\n\nD = os.path.join(os.path.dirname(__file__), "data")\n\n\n'
                      'def load_members():\n    with open(os.path.join(D, "members.csv"), encoding="utf-8") as f:\n'
                      '        return list(csv.DictReader(f))\n',
    "lib/data/members.csv": "mid,name\n1,甲\n2,乙\n3,丙\n",
    "lib/data/books.csv": "bid,title\n1,书一\n",
    "tests/__init__.py": "",
    "tests/test_storage.py": "import unittest\nfrom lib.storage import load_members\n\n\nclass T(unittest.TestCase):\n"
                             "    def test_n(self):\n        self.assertEqual(len(load_members()), 3)\n",
}
TASK = ("读者名单要从 CSV 换成 JSON。新建 lib/data/members.json，结构：{\"version\": 1, \"members\": [{\"mid\": …, \"name\": …}]}。"
        "迁完删掉 lib/data/members.csv，storage.load_members() 改为读新文件。books.csv 不要动。")


def test_test_delta():
    print("【测试变化】")
    S = lambda *ns: "\n".join(f"FAIL: {n} (m.T.{n})\n  AssertionError: {n}" for n in ns) + f"\nFAILED (failures={len(ns)})"
    for name, b, a, want in (("失败变多 → undo_reask", S("a"), S("a", "b"), "undo_reask"),
                             ("失败变少 → keep", S("a", "b"), S("a"), "keep"),
                             ("集合换了 → reask", S("a"), S("b"), "reask"),
                             ("全过 → done", S("a"), {"passed": "是", "summary": "全部通过：Ran 3 tests"}, "done")):
        f, _ = RR.test_facts(b, a, "")
        check(R.infer("测试变化", f)["action"] == want, name, f)
    f, x = RR.test_facts(S("a"), S("a"), "")
    f2, _ = RR.test_facts(S("a"), S("a"), x["sigs"])
    check(R.infer("测试变化", f)["action"] == "reask" and R.infer("测试变化", f2)["action"] == "escalate",
          "同一错误第 1 次 reask，连续第 2 次 escalate")


def test_read_edit_test():
    print("【读改测.zs：失败变多撤回、同错两次升级】")
    mini = project("mini", {"calc.py": "def add(a, b):\n    return a - b\n\n\ndef mul(a, b):\n    return a * b\n",
                            "tests/test_calc.py": "import unittest\nfrom calc import add, mul\n\n\nclass T(unittest.TestCase):\n"
                                                  "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n\n"
                                                  "    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n"})
    replies = iter([{"file": "calc.py", "old": "return a * b", "new": "return a + b"},
                    {"file": "calc.py", "old": "return a - b", "new": "return a - b + 0"},
                    {"file": "calc.py", "old": "return a - b + 0", "new": "return a - b + 0 * 1"}])
    seen = []

    def handler(prompt, *a, **k):
        seen.append(prompt)
        return json.dumps({"action": "改", "reason": "试", "edits": [next(replies)]})

    os.environ["DSLAGENT_TEST_CMD"] = f"{PY} -m unittest discover -s tests"
    eng = AgentEngine(client=MockClient(handler=handler, offline=True), workdir=mini, verbose=False, verbs_root=RN.VERBS,
                      scripts={n: LR.LIB / n for n in ("读改测.zs", "定位.zs")})
    eng.vars.update(task="修 add", segs="calc.py:1-6", rounds="3")
    eng.run("用包 common text code\n设 o = 调用 读改测.zs task={task} segs={segs} rounds={rounds}\n打印 {o.outcome}｜{o.log}")
    out = "\n".join(eng.output)
    check("失败变多 → 撤回" in out and "return a * b" in (mini / "calc.py").read_text(), "第 1 轮改坏 mul → 撤回", out[-300:])
    check(len(seen) >= 2 and "已撤回" in seen[1] and "test_mul" in seen[1], "第 2 轮提示带「已撤回」和新失败")
    check("升级交回" in out and len(seen) == 3 and out.startswith("没修好"), "同错两次 → 升级交回（outcome 没修好）", out[:200])
    os.environ.pop("DSLAGENT_TEST_CMD")


def test_done_check():
    print("【完成核对：抽取 + 检查 + 假成功】")
    t1 = ("把模块 lib/dates.py 里的 days_overdue 改叫 late_days；lib/ 下的 .py 文件里不能再出现 days_overdue。"
          "新建 lib/errors.py，里面定义 LibError，让 from lib import LibError 也能用。给 Book 加个类方法 Book.from_text(text)。"
          "report.py 一个字都不许改。挪完以后 catalog.py 里不能再留数据，整个文件控制在 80 行以内。"
          "在 lib/ 下新建 stock.py，提供 build_report(config=None)，最后在仓库根目录写一个 STOCK.md。raise ValueError(...) 保持原样。")
    files = {"lib/dates.py": b"", "lib/report.py": b"x", "lib/catalog.py": b""}
    got = {(i["kind"], i.get("path") or i.get("name")) for i in R.done_items(t1, files)}
    want = {("def", "late_days"), ("forbid", "days_overdue"), ("exists", "lib/errors.py"), ("def", "LibError"),
            ("import", "LibError"), ("def", "from_text"), ("unchanged", "lib/report.py"), ("lines", "lib/catalog.py"),
            ("exists", "lib/stock.py"), ("def", "build_report"), ("exists", "STOCK.md")}
    check(want <= got, "点名产物都抽到", sorted(want - got))
    check(not any(k == "def" and n in ("ValueError", "days_overdue") for k, n in got), "内建名/要删掉的旧名不当成要有的定义", got)
    check(R.done_items("修一下 tests.test_x.T.test_y 挂掉的问题，tests/ 别动。", {}) == [], "修 bug 描述不抽东西")
    p = project("u8", LIB)
    snap = R.all_files(p)
    items = R.done_items(TASK, snap)
    kinds = {(i["kind"], i.get("path")) for i in items}
    check({("exists", "lib/data/members.json"), ("absent", "lib/data/members.csv"), ("unchanged", "lib/data/books.csv"),
           ("keys", "lib/data/members.json")} <= kinds, "迁移任务：新建/删除/不许动/顶层键", kinds)
    check(len(RR.done_unmet(p, items, snap)) >= 3, "开局：新建/删除/键 都未满足")
    (p / "lib/data/members.json").write_text(json.dumps([{"mid": "1"}]), encoding="utf-8")
    un = RR.done_unmet(p, items, snap)
    check(len(un) == 2, "假成功：CSV 还在、JSON 不是对象 → 2 项未满足", un)
    f = lambda tp, u, redo, conf: R.infer("完成核对", RR.done_facts(tp, u, redo, conf))["action"]
    check((f(True, un, True, True), f(True, un, False, True), f(True, un, False, False), f(False, [], True, True), f(True, [], True, True))
          == ("redo", "confirm", "not_done", "not_done", "done"), "redo → confirm → not_done；测试没过 not_done；全满足 done")
    (p / "lib/data/books.csv").write_text("x\n", encoding="utf-8")
    check(any("books.csv" in x for x in RR.done_unmet(p, items, snap)), "点名不许动的文件被改 → 未满足")
    shutil.rmtree(p)


def test_safety():
    print("【安全约束（推理 安全.dl）】")
    p = project("safe", LIB)
    snap = R.all_files(p)
    R.setup(p, snap, TASK)
    check("依赖" in R.check("删除", p, "lib/data/members.csv"), "删仍被代码引用的源数据 → 拦")
    C = verb("改文件", p)
    r = C.改文件({"file": "lib/data/books.csv", "old": "书一", "new": "书二"})
    check(r["ok"] == "否" and (p / "lib/data/books.csv").read_bytes() == snap["lib/data/books.csv"], "改任务说不要动的 books.csv → 拦", r["msg"])
    r = C.改文件({"file": "lib/storage.py", "old": '"members.csv"', "new": '"members.json"'})
    check(r["ok"] == "是", "改源码放行", r["msg"])
    check("tests/" in R.check("改写", p, "tests/test_storage.py", "x"), "改测试文件 → 拦")
    check("出了项目" in R.check("删除", p, "/etc/hosts"), "越界 → 拦")
    (p / "lib/data/members.json").write_text(json.dumps({"version": 1, "members": [{"mid": "1"}]}), encoding="utf-8")
    check("等价" in R.check("删除", p, "lib/data/members.csv"), "新 JSON 记录数 1≠3 → 删源数据拦")
    (p / "lib/data/members.json").write_text(json.dumps({"version": 1, "members": [{"mid": str(i)} for i in (1, 2, 3)]}),
                                             encoding="utf-8")
    check(R.check("删除", p, "lib/data/members.csv") == "", "记录数一致、不再引用 → 删除放行")
    cmd = f"{PY} -m unittest discover -s tests"
    d = RR.replan_check(set(), RN.test_state(p, cmd)["summary"], R.all_files(p) != snap)
    check(d["action"] == "rollback" and d["regress"], "退回规划前回归已坏且有改动 → rollback", d)
    R.restore(p, snap)
    check(R.all_files(p) == snap, "回滚后与开局快照逐字节一致")
    check(RR.replan_check(set(), RN.test_state(p, cmd)["summary"], False)["action"] == "allow", "回归没坏 → 不回滚")
    os.environ["DSLAGENT_RULES"] = "0"
    check(R.check("改写", p, "lib/data/books.csv", "y") == "" and R.check("改写", p, "tests/x.py", "y") != "",
          "DSLAGENT_RULES=0：只留越界/测试文件检查")
    os.environ.pop("DSLAGENT_RULES")
    shutil.rmtree(p)


def test_verbs_in_dsl():
    print("【动词 推理 / 留底 / 撤回】")
    p = project("dsl", LIB)
    R.setup(p, R.all_files(p), TASK)
    os.environ["DSLAGENT_TEST_CMD"] = f"{PY} -m unittest discover -s tests"
    eng = AgentEngine(client=MockClient(handler=lambda *a, **k: "", offline=True), workdir=p, verbose=False, verbs_root=RN.VERBS)
    eng.run("用包 common text code\n设 t0 = 跑测试\n设 d = 推理 规则=测试变化.dl {t0} {t0} 无\n打印 {d.action}/{d.delta}\n"
            "设 c = 推理 规则=完成核对.dl 无 是 是\n打印 {c.action}\n"
            "设 bk = 留底\n打印 {bk.id}")
    st = p / "lib/storage.py"
    st.write_text(st.read_text().replace("members.csv", "x.csv"), encoding="utf-8")
    (p / "lib/new.py").write_text("x = 1\n", encoding="utf-8")
    eng.run(f"用包 common text code\n设 u = 撤回 {eng.output[2].strip()}\n打印 {{u.ok}}")
    check(eng.output[0].strip() == "done/same", "推理 测试变化（开局全过）→ done", eng.output)
    check(eng.output[1].strip() == "redo", "推理 完成核对（迁移没做）→ redo", eng.output)
    check(eng.output[-1].strip() == "是" and "members.csv" in st.read_text() and not (p / "lib/new.py").exists(),
          "留底 → 改/新建 → 撤回 恢复原样（新建的删掉）", eng.output)
    os.environ.pop("DSLAGENT_TEST_CMD")
    shutil.rmtree(p)


def test_runner_done_check():
    print("【runner：测试修好但点名的函数没加 → 补做一轮】")
    p = project("rn", {"m.py": "def f():\n    return 1\n",
                       "tests/test_m.py": "import unittest\nfrom m import f\n\n\nclass T(unittest.TestCase):\n"
                                          "    def test_f(self):\n        self.assertEqual(f(), 2)\n"})
    task = "tests.test_m.T.test_f 挂了，修好它；另外在 m.py 里新增函数 g_total(x)，返回 x。"
    calls = []

    def reply(prompt):
        if "【定位】" in prompt or "【读改测】" in prompt:
            return json.dumps({"action": "改", "reason": "f 应返回 2",
                               "edits": [{"file": "m.py", "old": "return 1", "new": "return 2"}]})
        if "补加函数" in prompt:
            return json.dumps({"edits": [{"file": "m.py", "old": "return 2\n", "new": "return 2\n\n\ndef g_total(x):\n    return x\n"}]})
        return "用包 common text code\n问JSON r = 补加函数 g_total 格式 edits:列表\n设 res = 改文件 {r}\n打印 结论：修好"

    class FakePool:
        def __init__(self, *a, **k):
            pass

        def prewarm(self, *a, **k):
            pass

        def run_local(self, cmd, timeout):
            from types import SimpleNamespace
            calls.append(cmd[2])
            return SimpleNamespace(returncode=0, stdout=json.dumps({"result": reply(cmd[2]), "total_cost_usd": 0}), stderr="")

        def close(self):
            pass

    import tools.dslagent.legacy.pool as PL
    old = PL.Pool
    PL.Pool = FakePool
    try:
        res = RN.run(p, task, TMP / "rn_out", test_cmd=f"{PY} -m unittest discover -s tests", infer=False)
    except Exception as e:
        res = {"error": repr(e)}
    finally:
        PL.Pool = old
    log = res.get("done_check", {}).get("log", [])
    check([x.get("action") for x in log] == ["redo", "done"], "模板修好 → 核对出 g_total 没加 → redo → 补做后 done", res.get("error") or log)
    check(res.get("fixed") and "def g_total" in (p / "m.py").read_text(), "最终 fixed 且函数已加", res.get("stop"))
    check(any("【完成核对】" in c for c in calls), "补做那一版的规划提示里带了未满足项", len(calls))


def main():
    test_test_delta()
    test_read_edit_test()
    test_done_check()
    test_safety()
    test_verbs_in_dsl()
    test_runner_done_check()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
