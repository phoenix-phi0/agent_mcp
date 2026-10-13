# -*- coding: utf-8 -*-
"""tools/dslagent 的任务路径（开局测试全过）：写文件 / 删文件 / 改模块名 三个动词（越界、测试文件、安全约束）、
列文件 全部、计划白名单、规划提示的动词速查，以及用假 claude（回一份固定计划）把任务路径从头跑到尾。不调模型。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_task.py
"""

import importlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_task_"))
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
os.environ["DSLAGENT_TMP"] = str(TMP / "tmp")
os.environ["CBATCH_CLAUDE"] = "/bin/true"

from tools.dslagent import plan as P          # noqa: E402
from tools.dslagent.legacy import prompts as PR      # noqa: E402
from tools.dslagent import reason as RS       # noqa: E402
from tools.dslagent import runner as R        # noqa: E402

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
    return getattr(m, name)


def project(name, files):
    d = TMP / name
    for rel, text in files.items():
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return d


TEST_OK = ("import unittest\nfrom pkg.calc import total\n\n\nclass CalcTest(unittest.TestCase):\n"
           "    def test_total(self):\n        self.assertEqual(total([1, 2]), 3)\n")
BASE = {"pkg/__init__.py": "", "pkg/calc.py": "def total(xs):\n    return sum(xs)\n",
        "pkg/textutil.py": "def norm(s):\n    return s.strip()\n",
        "pkg/use.py": "from pkg import textutil\nfrom pkg.textutil import norm\n\n\ndef go(s):\n    return textutil.norm(norm(s))\n",
        "pkg/data/rates.json": '{"a": 1}\n', "pkg/data/old.csv": "id,name\n1,x\n2,y\n",
        "pkg/loader.py": "PATH = 'data/old.csv'\n", "README.md": "# demo\n",
        "tests/__init__.py": "", "tests/test_calc.py": TEST_OK}


def test_verbs():
    pj = project("verbs", BASE)
    RS.setup(pj, RS.all_files(pj), "给 pkg 加一个报告文件 pkg/report.md")

    print("写文件：新建（父目录自动建）/ 覆盖 / 越界 / 测试文件 / 安全约束")
    w = verb("写文件", pj)
    r = w({"file": "pkg/out/report.md", "content": "# 报告\n"})
    check(r["ok"] == "是" and (pj / "pkg/out/report.md").read_text(encoding="utf-8") == "# 报告\n", "新建文件、父目录自动建", r)
    r = w({"files": [{"file": "pkg/a.py", "content": "A = 1\n"}, {"file": "pkg/b.json", "content": {"k": 1}}]})
    check(r["ok"] == "是" and r["n"] == 2 and json.loads((pj / "pkg/b.json").read_text(encoding="utf-8")) == {"k": 1},
          "files 列表一次写多个，content 是结构就转 JSON", r)
    r = w({"file": "../evil.py", "content": "x"})
    check(r["ok"] == "否" and "越界" in r["msg"] and not (TMP / "evil.py").exists(), "越出项目被拒", r)
    r = w({"file": "tests/test_new.py", "content": "x"})
    check(r["ok"] == "否" and "测试文件" in r["msg"], "不许写测试文件", r)
    r = w({"files": [{"file": "pkg/c.py", "content": "C = 1\n"}, {"file": "pkg/data/rates.json", "content": "{}\n"}]})
    check(r["ok"] == "否" and r.get("blocked") == "是" and "安全约束" in r["msg"] and not (pj / "pkg/c.py").exists(),
          "覆盖任务没点名、开局就有的数据文件 → 安全约束拦下，整体没写", r)
    r = w({"file": "pkg/data/rates.json", "content": '{"a": 1}\n'})
    check(r["ok"] == "是", "写回与开局快照一致的内容放行", r)
    r = w({"file": "pkg/x.py"})
    check(r["ok"] == "否" and "content" in r["msg"], "缺 content 报错", r)

    print("删文件：项目内非测试文件 / 越界 / 测试文件 / 仍被引用拦截")
    d = verb("删文件", pj)
    r = d("pkg/a.py")
    check(r["ok"] == "是" and not (pj / "pkg/a.py").exists(), "删掉没人引用的文件", r)
    r = d("pkg/nothere.txt")
    check(r["ok"] == "是" and "本来就不存在" in r["msg"], "不存在也算成功", r)
    r = d("../other/x.py")
    check(r["ok"] == "否" and "越界" in r["msg"], "相对路径出项目被拒", r)
    r = d("/etc/hostname")
    check(r["ok"] == "否" and "越界" in r["msg"], "绝对路径出项目被拒", r)
    r = d("tests/test_calc.py")
    check(r["ok"] == "否" and (pj / "tests/test_calc.py").exists(), "不许删测试文件", r)
    r = d("pkg/data/old.csv")
    check(r["ok"] == "否" and r.get("blocked") == "是" and "loader.py" in r["msg"] and (pj / "pkg/data/old.csv").exists(),
          "仍被代码引用的数据文件 → 安全约束拦下", r)

    print("改模块名：更新 import、兼容层、测试文件/越界被拒")
    m = verb("改模块名", pj)
    r = m("pkg/textutil.py", "pkg/textnorm.py", "是", "norm")
    use = (pj / "pkg/use.py").read_text(encoding="utf-8")
    compat = (pj / "pkg/textutil.py").read_text(encoding="utf-8")
    check(r["ok"] == "是" and (pj / "pkg/textnorm.py").is_file() and "from pkg import textnorm" in use
          and "from pkg.textnorm import norm" in use and "textnorm.norm(" in use, "改名 + 引用方 import / 调用都换掉", (r, use))
    check("from .textnorm import norm" in compat and "def " not in compat, "兼容模块只重新导出", compat)
    r = m("pkg/calc.py", "tests/calc.py")
    check(r["ok"] == "否" and (pj / "pkg/calc.py").exists(), "不许挪进测试目录", r)
    r = m("pkg/calc.py", "../calc.py")
    check(r["ok"] == "否" and "越界" in r["msg"], "越出项目被拒", r)
    r = m("pkg/none.py", "pkg/none2.py")
    check(r["ok"] == "否" and "不存在" in r["msg"], "旧模块不存在报错", r)
    os.environ["DSLAGENT_RULES"] = "0"
    try:
        r = verb("删文件", pj)("pkg/data/old.csv")
        check(r["ok"] == "是", "DSLAGENT_RULES=0：只剩越界/测试文件检查，引用不再拦", r)
    finally:
        del os.environ["DSLAGENT_RULES"]
    blocks = [b["code"] for b in RS.STATE["log"]]
    check("overwrite_data" in blocks and "still_referenced" in blocks, "拦截都记进 reason.STATE['log']", blocks)

    print("列文件：缺省只列 .py；全部 另列数据/文档文件")
    ls = verb("列文件", pj)
    a, b = ls(), ls("全部")
    check("pkg/calc.py" in a and "rates.json" not in a and "README.md" not in a, "缺省只列 .py", a)
    check("pkg/data/rates.json（1 行）" in b and "README.md" in b and "pkg/calc.py" in b, "全部：.json/.md 也列出", b)


def test_whitelist_prompts():
    print("计划白名单、规划提示")
    sc = ("用包 common text code\n设 f = 列文件 全部\n设 r = 写文件 {e}\n设 d = 删文件 pkg/old.csv\n"
          "设 m = 改模块名 pkg/a.py pkg/b.py 是 x\n打印 结论：修好")
    check(not P.whitelist_check(sc, {}), "写文件/删文件/改模块名/列文件 全部 过白名单", P.whitelist_check(sc, {}))
    check({"写文件", "删文件", "改模块名"} <= P.ALLOWED_VERBS, "三个动词在 ALLOWED_VERBS")
    for v in ("写文件 {e}", "删文件 路径", "改模块名 旧路径 新路径", "列文件 [全部]", "安全约束"):
        check(v in PR.SYSTEM, f"规划系统提示的动词速查里有「{v}」")
    check(importlib.reload(PR).SYSTEM == PR.SYSTEM and not re.search(r"/home|\d{4}-\d\d", PR.SYSTEM),
          "规划系统提示逐字稳定、不含路径/日期")
    t = PR.task_first_prompt("做 X", "a.py", "全部通过", 15, 13, 1, "python3 -m unittest")
    check("不是修 bug" in t and "【任务】\n做 X" in t and "结论：修好" in t, "任务路径首版提示：不是修 bug、要结论", t[:200])
    t = PR.task_replan_prompt("做 X", "a.py", "全部通过", 9, 7, 0, 1, "S", "O", "E", "T", "D", "cmd", note="NOTE")
    check(t.index("NOTE") < t.index("【任务】") and "【上一版的报错】\nE" in t and "D" in t, "任务路径重规划提示带上一版和说明")


FAKE = r"""#!/usr/bin/env python3
import json, os, sys
plan = open(os.environ["FAKE_PLAN"], encoding="utf-8").read()
with open(os.environ["FAKE_PLAN"] + ".n", "a") as f:
    f.write("x")
out = lambda o: (sys.stdout.write(json.dumps(o, ensure_ascii=False) + "\n"), sys.stdout.flush())
for line in sys.stdin:
    msg = json.loads(line)["message"]["content"]
    if msg == "/clear":
        out({"type": "result", "subtype": "success", "result": "", "total_cost_usd": 0, "session_id": "s"})
        continue
    out({"type": "stream_event", "event": {"type": "content_block_delta"}})
    out({"type": "result", "subtype": "success", "is_error": False, "session_id": "s", "total_cost_usd": 0.01,
         "result": plan})
"""


def test_task_path():
    print("任务路径从头跑到尾（假 claude 回固定计划）")
    fake = TMP / "fake_claude.py"
    fake.write_text(FAKE, encoding="utf-8")
    fake.chmod(0o755)
    plan = TMP / "plan.zs"
    plan.write_text("用包 common text code\n设 d = 删文件 pkg/legacy_helper.py\n打印 {d.msg}\n打印 结论：修好 删了", encoding="utf-8")
    old = os.environ["CBATCH_CLAUDE"]
    os.environ.update(CBATCH_CLAUDE=str(fake), FAKE_PLAN=str(plan))
    try:
        pj = project("task1", dict(BASE, **{"pkg/legacy_helper.py": "OLD = 1\n"}))
        r = R.run(pj, "把 pkg/legacy_helper.py 删掉", TMP / "out_task1")
        res = json.loads((TMP / "out_task1" / "result.json").read_text(encoding="utf-8"))
        check(r["kind"] == "task" and r["fixed"] and r["engine_used"] == "plan_task" and res["engine_used"] == "plan_task"
              and res["kind"] == "task", "开局全过 → 任务路径完成，result.json 记 kind=task、engine_used=plan_task", r["stop"])
        check(not (pj / "pkg/legacy_helper.py").exists() and r["calls"] == 1 and r["versions"] == 1, "按计划删了文件，1 次规划调用", r)
        check(r["done_check"]["items"] == [{"kind": "absent", "path": "pkg/legacy_helper.py"}]
              and r["done_check"]["log"][0]["action"] == "done", "完成前核对：点名删除的文件已不在", r["done_check"])
        check("pkg/legacy_helper.py" in r["changed_files"] and "-OLD = 1" in r["diff"], "diff 记下删掉的文件", r["diff"][:200])
        check(r["report"].startswith("DSL 完成（任务路径规划第 1 版）"), "报告说完成", r["report"])

        # 计划自称修好但没做到点名产物 → 完成核对 redo 再规划一版 → 仍没做到 → 问模型确认（假模型回的不是 JSON → 算未完成）
        plan.write_text("用包 common text code\n打印 结论：修好 其实啥也没做", encoding="utf-8")
        pj = project("task2", dict(BASE, **{"pkg/legacy_helper.py": "OLD = 1\n"}))
        r = R.run(pj, "把 pkg/legacy_helper.py 删掉", TMP / "out_task2")
        acts = [x.get("action") for x in r["done_check"]["log"] if "action" in x]
        check(not r["fixed"] and acts[:2] == ["redo", "confirm"] and "完成核对" in r["stop"] and r["kind"] == "task"
              and r["engine_used"] == "plan_task", "假成功被完成核对拦下：redo → confirm → 没完成", (acts, r["stop"]))
        check("没完成" in r["handoff"] or "完成核对" in r["handoff"], "交接说明给兜底用", r["handoff"][:200])

        # 结论不是修好 → 再规划一版；两版都没完成
        plan.write_text("用包 common text code\n打印 结论：没修好 还差一步", encoding="utf-8")
        pj = project("task3", BASE)
        r = R.run(pj, "新建 pkg/report.md", TMP / "out_task3")
        check(not r["fixed"] and r["versions"] == 2 and "都没完成" in r["stop"], "结论不是修好 → 两版都没完成", r["stop"])

        # 改坏原本通过的测试 → 退回规划前回滚到开局快照
        plan.write_text("用包 common text code\n设 e = 解析JSON {\"file\":\"pkg/calc.py\",\"content\":\"total=0\"}\n"
                        "设 r = 写文件 {e}\n打印 {r.msg}\n打印 结论：修好", encoding="utf-8")
        pj = project("task4", BASE)
        r = R.run(pj, "新建 pkg/report.md", TMP / "out_task4")
        check(not r["fixed"] and r["rollbacks"] >= 1, "任务路径改坏测试 → 回滚", (r["stop"], r["rollbacks"], r["version_log"][0].get("error")))
    finally:
        os.environ["CBATCH_CLAUDE"] = old


def test_early_exit_and_caps():
    print("早退回：任务路径第 1 版计划自报缺能力 / 卡在白名单外动词 → 不写第 2 版；能力检查与 auto 拿不准标记")
    fake = TMP / "fake_claude.py"
    fake.write_text(FAKE, encoding="utf-8")
    fake.chmod(0o755)
    plan = TMP / "plan.zs"
    old = os.environ["CBATCH_CLAUDE"]
    os.environ.update(CBATCH_CLAUDE=str(fake), FAKE_PLAN=str(plan))
    try:
        plan.write_text("用包 common text code\n打印 结论：缺能力：要用 pip 装 openpyxl", encoding="utf-8")
        pj = project("early1", BASE)
        r = R.run(pj, "导出 xlsx：新建 pkg/export.py", TMP / "out_early1")
        check(not r["fixed"] and r["versions"] == 1 and r["calls"] == 1 and r["stop"].startswith("早退回")
              and "openpyxl" in r["early_exit"], "计划自报缺能力 → 1 版 1 次调用就交回，记 early_exit", (r["stop"], r["calls"]))
        plan.write_text("用包 common text code\n设 x = 撤回\n打印 结论：修好", encoding="utf-8")
        pj = project("early2", BASE)
        r = R.run(pj, "新建 pkg/report.md", TMP / "out_early2")
        check(not r["fixed"] and r["versions"] == 1 and "不在白名单里" in r.get("early_exit", "")
              and r["version_log"][0]["fix_rounds"] == 2, "白名单外动词重写 2 次仍不过 → 早退回，不写第 2 版",
              (r["stop"], r["versions"]))
        plan.write_text("用包 common text code\n打印 结论：没修好 还差一步", encoding="utf-8")
        pj = project("early3", BASE)
        r = R.run(pj, "新建 pkg/report.md", TMP / "out_early3")
        check(r["versions"] == 2 and not r.get("early_exit"), "普通没完成照旧写第 2 版", r["stop"])
    finally:
        os.environ["CBATCH_CLAUDE"] = old

    gaps = R.capability_gaps
    check(gaps("先 pip install openpyxl 再导出") and gaps("请到网上抓一下今天的汇率") and gaps("写个 deploy.sh 并执行")
          and gaps("把另一个仓库里的调用也改了") and gaps("在浏览器里点一下看看") and gaps("开调试器单步跟一下"),
          "能力检查：装依赖 / 联网 / shell / 仓库外 / 浏览器 / 交互式调试 都能认出")
    check(not gaps("新建 pkg/report.md，定义 build_report(cart)；测试要全部通过，tests/ 下别动")
          and not gaps("修复失败的测试：AssertionError in test_total"), "普通任务不误判")
    d = R.decide_auto("用 pip install requests 抓数据", None)
    check(d["engine"] == "claude" and d["needs"] and d["reason"].startswith("能力检查"), "decide_auto：能力检查先于一切", d)
    pj = project("auto_ok", BASE)
    d = R.decide_auto("把代码整理得好看一点", str(pj))
    check(d["engine"] == "claude" and d.get("uncertain") == "task", "全过、抽不出产物 → claude 并标 uncertain=task", d["reason"])
    d = R.decide_auto("新建 pkg/report.md", str(pj))
    check(d["engine"] == "dsl" and not d.get("uncertain"), "规则确定的不标 uncertain", d["reason"])


def main():
    test_verbs()
    test_whitelist_prompts()
    test_task_path()
    test_early_exit_and_caps()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
