# -*- coding: utf-8 -*-
"""tools/dslagent：不调模型的部分——补读范围的区间覆盖、模板抽参、auto 判定、测试命令探测、
测试摘要、计划检查（白名单 / 去说明文字 / 补结束）、AgentEngine 的子脚本映射和语句白名单。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent.py

真模型的集成测试在 tests/tools/dslagent_live.py（手动跑，要花钱）。
"""

import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_"))
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
os.environ["DSLAGENT_TMP"] = str(TMP / "tmp")
# 执行器开头会预热常驻 claude 进程（不调 API）；单元测试里换成马上退出的程序，一个真 claude 都不起
os.environ["CBATCH_CLAUDE"] = "/bin/true"

from tools.dslagent import plan as P          # noqa: E402
from tools.dslagent import runner as R        # noqa: E402
from tools.dslagent import template as T      # noqa: E402

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
        (f"报错\n{tb}", ok, None, "claude", "初始测试全过"),
        (f"报错\n{tb}", empty, None, "claude", "探测不到测试"),
        ("x", empty, f"{R._python()} -m unittest discover -s tests", "claude", "测试命令没跑到测试"),
    ]
    for prompt, proj, cmd, want, why in cases:
        d = R.decide_auto(prompt, str(proj) if proj else None, cmd)
        check(d["engine"] == want and d["reason"], f"auto：{why} → {want}", d)

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
    from tools.dslagent.engine import AgentEngine
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

    print("执行器：开局全过 / 探测不到测试时不动手")
    r = R.run(ok, "x", TMP / "out_ok")
    check(not r["fixed"] and "全部通过" in r["stop"] and r["calls"] == 0, "开局全过 → 不调模型", r["stop"])
    r = R.run(empty, "x", TMP / "out_empty")
    check(not r["fixed"] and "探测不到测试" in r["stop"] and (TMP / "out_empty" / "result.json").is_file(),
          "探测不到测试 → 直接交回，照样写 result.json", r["stop"])

    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
