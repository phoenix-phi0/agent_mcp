# -*- coding: utf-8 -*-
"""tools/dslagent 规划路径 v2（v2.py / v2pack.py）：用假模型把 1–7 各分支走一遍。不调真模型。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_v2.py

  一、数据包：候选模块、引用行、测试断言（import 了候选模块的测试）、超长时砍候选块；补查三类（查引用 / 查文本 / 读文件）
  二、test_gate：计划里的 跑测试 什么时候真跑
  三、全流程（假模型）：
      1–4 够了不补查 / 要补查并入数据包；计划没过检查重写 1 次；重写仍错判失败不执行；脚本 终止 失败回滚；
          计划内 跑测试 不影响走向时跳过、影响走向时真跑（验收复用、失败时派任务补救）
      5   残留（只搜计划声明的旧写法、限任务涉及的目录）→ 补改（入参给所在函数全文）；清单缺口补改不成 → 失败
      6   边界用例全过 / 失败补改后过 / 补改说用例不对 → 超出预期 / 补改后仍失败 → 超出预期 / 补改弄坏现有测试 → 撤回
          / 用例文件跑不起来不算代码的问题
      7   reply 的 结果/状态/原因、各步秒、调用次数、费用
  四、开关：DSLAGENT_PLANNER=v2 时 runner.run 转到 v2，缺省不转
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_v2_"))
os.environ["DSLAGENT_TMP"] = str(TMP / "tmp")
os.environ["CBATCH_CLAUDE"] = "/bin/true"
os.environ["DSLAGENT_DATASET"] = str(TMP / "dataset")      # 训练数据样本写临时目录，不进 ~/dslagent_data
os.environ.pop("DSLAGENT_PLANNER", None)
os.environ.pop("DSLAGENT_PLAN_MODE", None)

from tools.dslagent import runner as RN      # noqa: E402
from tools.dslagent import v2 as V            # noqa: E402
from tools.dslagent import guard as G                    # noqa: E402
from tools.dslagent import v2pack as K        # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


UTIL = '''def clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def double(x):
    return x * 2
'''
OTHER = '''from pkg.util import clamp


def norm(x):
    return clamp(x, 0, 10)


def twice(x):
    return x * 2
'''
TESTS = '''import unittest

from pkg.other import norm, twice
from pkg.util import clamp, double


class T(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(clamp(5, 0, 3), 3)

    def test_double(self):
        self.assertEqual(double(2), 4)

    def test_norm(self):
        self.assertEqual(norm(-1), 0)
        self.assertEqual(twice(3), 6)
'''
TEST_CMD = f"{sys.executable} -m unittest discover -s tests"
TASK = "把 pkg/util.py 里的 double 改成用加法实现（x + x），对外行为不变。测试文件不要改。"


def make_proj(name):
    p = TMP / name
    shutil.rmtree(p, ignore_errors=True)
    (p / "pkg").mkdir(parents=True)
    (p / "tests").mkdir()
    (p / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (p / "pkg" / "util.py").write_text(UTIL, encoding="utf-8")
    (p / "pkg" / "other.py").write_text(OTHER, encoding="utf-8")
    (p / "tests" / "test_util.py").write_text(TESTS, encoding="utf-8")
    (p / "docs").mkdir()
    (p / "docs" / "old.py").write_text("def legacy(x):\n    return x * 2\n", encoding="utf-8")
    return p


EDIT_DOUBLE = '''#改法 e1
@@ 改 pkg/util.py
<<<<<<< 原文
def double(x):
    return x * 2
=======
def double(x):
    return x + x
>>>>>>> 新文
'''


def plan(body, old_rx=None, checklist="改 pkg/util.py:double", edits=EDIT_DOUBLE):
    head = "用包 common text code\n预算 调用 4 秒 300\n" + (f"# 旧写法: {old_rx}\n" if old_rx else "")
    return head + body.strip("\n") + "\n\n" + edits + "\n#清单\n" + checklist + "\n"


PLAN_OK = plan('''
设 res = 改文件 {e1}
如果 {res.ok} 不等于 是
  终止 失败 没套上：{res.msg}
结束
设 t = 跑测试
如果 {t.passed} 不等于 是
  终止 失败 测试没过
结束
终止 成功 double 改成加法
''')

BOUND_OK = '''import unittest

from pkg.util import double


class B(unittest.TestCase):
    def test_zero(self):
        """0 的两倍还是 0"""
        self.assertEqual(double(0), 0)

    def test_neg(self):
        """负数照样翻倍"""
        self.assertEqual(double(-3), -6)
'''
BOUND_RAISE = '''```python
import unittest

from pkg.util import clamp


class B(unittest.TestCase):
    def test_bad_range(self):
        """lo 大于 hi 时抛 ValueError"""
        with self.assertRaises(ValueError):
            clamp(5, 3, 1)

    def test_mid(self):
        """区间内原样返回"""
        self.assertEqual(clamp(2, 1, 3), 2)
```'''
FIX_CLAMP = {"结果": {"edits": [{"file": "pkg/util.py", "old": "def clamp(x, lo, hi):\n",
                                "new": "def clamp(x, lo, hi):\n    if lo > hi:\n        raise ValueError(\"区间不对\")\n"}],
                     "说明": "加区间检查"}, "状态": "成功", "原因": ""}


class Fake:
    """按 tag 前缀回复；值可以是文本、dict（转 JSON）、或 callable(user) → 文本。记下每次的 (tag, system, user)。"""

    def __init__(self, **replies):
        self.replies = {"plan": PLAN_OK, "bound": BOUND_OK}
        self.replies.update(replies)
        self.log = []
        self.models = []

    def __call__(self, system, user, tag, timeout, model=None, **kw):
        self.log.append((tag, system, user))
        self.models.append((tag, model))
        key = next((k for k in sorted(self.replies, key=len, reverse=True) if tag.startswith(k)), None)
        r = self.replies.get(key)
        if callable(r):
            r = r(user)
        if isinstance(r, list):          # 依次回复
            r = r.pop(0) if len(r) > 1 else r[0]
        if isinstance(r, dict):
            r = json.dumps(r, ensure_ascii=False)
        return {"text": r or "", "cost": 0.01, "sec": 0.0}

    def tags(self):
        return [t for t, _, _ in self.log]


def go(name, fake, **kw):
    p = make_proj(name)
    out = TMP / f"out_{name}"
    shutil.rmtree(out, ignore_errors=True)
    r = V.run(p, kw.pop("task", TASK), out, test_cmd=TEST_CMD, model=fake, **kw)
    return r, p, out


def util(p):
    return (p / "pkg" / "util.py").read_text(encoding="utf-8")


# ------------------------------------------------------------------ 一、数据包


def t_pack():
    print("一、数据包（大纲 / 候选）")
    p = make_proj("pack")
    text, info = K.build(p, "把 pkg/util.py 里的 double 改成加法；clamp 不动")
    check("pkg/util.py" in info["cands"] and "def double" in text, "候选模块含点名文件、给了原文", info)
    check("tests/test_util.py" in info["test_files"] and "assertEqual(double(2), 4)" in text,
          "import 了候选模块的测试断言收进数据包", info["test_files"])
    check("## 被点名字的全部引用行" in text and "## 文件大纲" in text and "clamp:1-" in text, "引用行、文件大纲")
    check(not any(c.startswith("tests/") for c in info["cands"]), "测试文件不当候选")
    small, si = K.build(p, "把 pkg/util.py 里的 double 改成加法，pkg/other.py 的 twice 也一样", budget=1500)
    check(len(small) <= 1500 + 40 and len(si["cands"]) <= len(info["cands"]), "超长时砍候选块 / 截断", (len(small), si))


# ------------------------------------------------------------------ 二、test_gate


def t_gate():
    print("二、test_gate")
    g = V.test_gate
    check(g("设 t = 跑测试\n如果 {t.passed} 不等于 是\n  终止 失败 x {t.summary}\n结束\n终止 成功 好") == {0: False},
          "失败只 终止、后面也只 终止 → 不真跑")
    check(g("设 t = 跑测试\n如果 {t.passed} 等于 是\n  终止 成功 好\n否则\n  终止 失败 {t.summary}\n结束") == {0: False},
          "两个分支都只 终止 → 不真跑")
    check(g("设 t = 跑测试\n如果 {t.passed} 等于 是\n  终止 成功 好\n结束\n设 r = 派任务 修 {task}\n终止 失败 x") == {0: True},
          "没过时落到后面的补救 → 真跑")
    check(g("设 t = 跑测试\n如果 {t.passed} 不等于 是\n  设 r = 派任务 修 {t.summary}\n结束\n终止 成功 好") == {0: True},
          "失败分支里派任务 → 真跑")
    check(g("设 t = 跑测试\n设 last = {t.summary}\n终止 成功 好") == {0: True}, "结果带进别的变量 → 真跑")
    check(g("跑测试\n设 t = 跑测试\n打印 {t.summary}\n终止 成功 好") == {0: False, 1: False}, "不赋值 / 只打印 → 不真跑")
    ex = (V.LIB / "示例_分支规划.zs").read_text(encoding="utf-8")
    check(all(g(ex).values()) and len(g(ex)) == 2, "示例脚本里两处 跑测试 都影响走向", g(ex))


# ------------------------------------------------------------------ 三、全流程


def t_flow():
    print("三、全流程（假模型）")
    f = Fake()
    r, p, out = go("ok", f)
    rp = r["reply"]
    check(rp["状态"] == "成功" and r["fixed"] and "x + x" in util(p), "成功：改法套上、验收过、边界用例过", r.get("stop"))
    check(f.tags() == ["plan", "bound"] and r["calls"] == 2 and abs(r["cost"] - 0.02) < 1e-9,
          "没有补查；调用 2 次，费用累加", f.tags())
    v = r["v2"]
    check([x["mode"] for x in v["计划内测试"]] == ["skipped", "real"] and v["验收"]["测试"][0]["方式"] == "真跑",
          "计划里不影响走向的 跑测试 跳过，验收真跑一次", v["计划内测试"])
    check(set(v["步骤秒"]) == {"1大纲", "3规划", "4执行", "5验收", "6边界复核"}, "记下各步耗时", v["步骤秒"])
    check(set(rp) == {"结果", "状态", "原因"} and rp["结果"]["改动文件"] == ["pkg/util.py"] and rp["结果"]["调用"] == 2
          and "全过" in rp["结果"]["边界复核"], "reply 是 结果/状态/原因 结构", rp)
    check((out / "result.json").is_file() and (out / "calls.json").is_file() and (out / "boundary" / "test_boundary_v2.py").is_file()
          and not (p / "test_boundary_v2.py").exists(), "记录写进任务目录，用例文件不进项目")
    check("x + x" in r["diff"] and "DSL v2 成功" in r["report"], "diff / report")

    f = Fake()
    os.environ["DSLAGENT_PLAN_MODEL"] = "opus"
    try:
        r, p, out = go("planmodel", f)
    finally:
        del os.environ["DSLAGENT_PLAN_MODEL"]
    calls = json.loads((out / "calls.json").read_text(encoding="utf-8"))
    check(f.models == [("plan", "opus"), ("bound", None)] and r["plan_model"] == "opus"
          and r["v2"]["规划模型"] == "opus" and [c["model"] for c in calls] == ["opus", "sonnet"],
          "DSLAGENT_PLAN_MODEL：规划用指定模型，边界复核仍 sonnet，记录里写规划模型", (f.models, r.get("plan_model"), calls))
    f = Fake()
    r, p, out = go("planmodel0", f)
    check(f.models == [("plan", None), ("bound", None)] and r["plan_model"] == "sonnet",
          "没设 DSLAGENT_PLAN_MODEL：规划用 sonnet，backend 不多传 model", f.models)

    bad = "用包 common text code\n预算 调用 2 秒 60\n设 x = 转大写 ls\n终止 成功 好\n\n#清单\n改 pkg/util.py:double\n"
    f = Fake(plan=bad, plan_fix=PLAN_OK)
    r, p, _ = go("rewrite", f)
    fx = next(u for t, _, u in f.log if t == "plan_fix")
    check(r["reply"]["状态"] == "成功" and r["v2"]["重写"] and "转大写" in fx and "没通过检查" in fx,
          "计划没过检查 → 带着错误重写 1 次", r["v2"]["检查"])
    f = Fake(plan=bad, plan_fix=bad.replace("预算 调用 2 秒 60\n", ""))
    r, p, _ = go("rewrite2", f)
    check(r["reply"]["状态"] == "失败" and "重写 1 次仍没过检查" in r["reply"]["原因"] and util(p) == UTIL
          and f.tags() == ["plan", "plan_fix"], "重写仍错 → 失败、不执行", r["reply"])
    f = Fake(plan=plan("设 res = 改文件 {e1}\n终止 失败 故意失败"))
    r, p, _ = go("halt", f)
    check(r["reply"]["状态"] == "失败" and "故意失败" in r["reply"]["原因"] and util(p) == UTIL and r["changed_files"] == [],
          "脚本 终止 失败 → 回滚到开局", r["reply"])
    f = Fake(plan=plan("设 res = 改文件 {e1}\n终止 超出预期 前提不对"))
    r, p, _ = go("halt2", f)
    check(r["reply"]["状态"] == "超出预期" and util(p) == UTIL, "脚本 终止 超出预期 → 状态照报、回滚")

    # 计划内测试影响走向：真跑，验收复用
    pl = plan('''
设 res = 改文件 {e1}
设 t = 跑测试
如果 {t.passed} 不等于 是
  设 r = 派任务 修测试 {t.summary} 修好 edits:列表
  设 res = 改文件 {r.结果}
结束
终止 成功 好
''')
    f = Fake(plan=pl)
    r, p, _ = go("reuse", f)
    v = r["v2"]
    check(r["reply"]["状态"] == "成功" and [x["mode"] for x in v["计划内测试"]] == ["real"]
          and v["验收"]["测试"][0]["方式"] == "复用" and r["reply"]["结果"]["测试次数"]["复用"] == 1,
          "影响走向的 跑测试 真跑；代码没变，验收复用它", v["验收"].get("测试"))
    broke = EDIT_DOUBLE.replace("return x + x", "return x * 3")
    pl2 = plan(pl.split("预算 调用 4 秒 300\n", 1)[1].split("\n\n#改法")[0], edits=broke)
    f = Fake(plan=pl2, dsl={"结果": {"edits": [{"file": "pkg/util.py", "old": "return x * 3", "new": "return x + x"}]},
                            "状态": "成功", "原因": ""})
    r, p, _ = go("remedy", f)
    v = r["v2"]
    check(r["reply"]["状态"] == "成功" and "dsl01" in f.tags() and "x + x" in util(p)
          and v["验收"]["测试"][0]["方式"] == "真跑", "测试没过 → 计划里派任务补救，代码变了验收重跑", (f.tags(), v["验收"]))

    # 5 残留：只搜计划声明的旧写法、范围限任务涉及的目录（docs/old.py 不在范围里）
    fixrep = {"结果": {"edits": [{"file": "pkg/other.py", "old": "    return x * 2", "new": "    return x + x"}],
                       "说明": "twice 也改"}, "状态": "成功", "原因": ""}
    f = Fake(plan=PLAN_OK.replace("预算 调用 4 秒 300\n", "预算 调用 4 秒 300\n# 旧写法: return x \\* 2$\n"), fix=fixrep)
    r, p, _ = go("resid", f)
    a = r["v2"]["验收"]
    fu = next(u for t, _, u in f.log if t == "fix")
    check(a["残留"] == 1 and a["残留列表"][0]["文件"] == "pkg/other.py" and a["范围"] == ["pkg"],
          "残留只在任务涉及的目录里搜（docs/ 不算）", a)
    check("def twice(x):" in fu and "pkg/other.py:9" in fu and a["补改后残留"] == 0 and r["reply"]["状态"] == "成功",
          "补改入参给残留所在函数全文；补改后没残留 → 成功", fu[-600:])
    f = Fake(plan=PLAN_OK.replace("预算 调用 4 秒 300\n", "预算 调用 4 秒 300\n# 旧写法: return x \\* 2$\n"),
             fix={"结果": {"edits": []}, "状态": "失败", "原因": "不会"})
    r, p, _ = go("resid2", f)
    check(r["reply"]["状态"] == "失败" and "旧写法残留" in r["reply"]["原因"] and "bound" not in f.tags(),
          "补改后仍有残留 → 失败，不做边界复核", r["reply"])
    f = Fake(plan=plan(PLAN_OK.split("预算 调用 4 秒 300\n", 1)[1].split("\n\n#改法")[0],
                       checklist="改 pkg/util.py:double\n改 pkg/other.py:twice"),
             fix={"结果": {"edits": []}, "状态": "失败", "原因": "不会"})
    r, p, _ = go("cl", f)
    fu = next(u for t, _, u in f.log if t == "fix")
    check(r["reply"]["状态"] == "失败" and "清单没做到" in r["reply"]["原因"] and "def twice(x):" in fu,
          "清单里要改的文件没动 → 补改（给那个函数）→ 仍没动 → 失败", r["reply"])

    # 6 边界复核
    f = Fake(bound=BOUND_RAISE, bfix=FIX_CLAMP)
    r, p, out = go("b_fix", f)
    b = r["v2"]["边界复核"]
    bu = next(u for t, _, u in f.log if t == "bfix")
    check(r["reply"]["状态"] == "成功" and "raise ValueError" in util(p) and b["第1次"]["failed_desc"]
          and b["第2次"]["ok"] and "改了代码）后全过" in b["结论"], "边界用例没过 → 补改 → 再跑全过 → 成功", b)
    check("test_bad_range" in bu and "def double(x):" in bu and "【任务原文】" in bu, "边界补改入参：用例、失败输出、改动所在函数")
    f = Fake(bound=BOUND_RAISE, bfix={"结果": {"edits": []}, "状态": "超出预期", "原因": "任务没说要检查区间"})
    r, p, _ = go("b_disagree", f)
    check(r["reply"]["状态"] == "超出预期" and "test_bad_range" in r["reply"]["原因"] and not r["fixed"],
          "补改说用例不对、不改 → 超出预期（不报成功），原因写明用例", r["reply"])
    f = Fake(bound=BOUND_RAISE, bfix={"结果": {"edits": [{"file": "pkg/util.py", "old": "    return x\n",
                                                          "new": "    return x  # 看过了\n"}]}, "状态": "成功", "原因": ""})
    r, p, _ = go("b_still", f)
    check(r["reply"]["状态"] == "超出预期" and "仍没过" in r["reply"]["原因"] and "lo 大于 hi" in r["reply"]["原因"],
          "补改后仍失败 → 超出预期，原因带用例说明", r["reply"])
    f = Fake(bound=BOUND_RAISE, bfix={"结果": {"edits": [{"file": "pkg/util.py", "old": "        return hi\n",
                                                          "new": "        return lo\n"}]}, "状态": "成功", "原因": ""})
    r, p, _ = go("b_break", f)
    check(r["reply"]["状态"] == "超出预期" and "撤回" in r["reply"]["原因"] and "return hi" in util(p)
          and "x + x" in util(p), "补改弄坏现有测试 → 撤回补改，超出预期", r["reply"])
    harness = BOUND_OK.replace("class B(unittest.TestCase):\n", "class B(unittest.TestCase):\n    f = double\n\n") \
        .replace("double(0)", "self.f(0)")
    f = Fake(bound=harness, bfix={"结果": {"edits": [], "用例代码": "```python\n" + BOUND_OK + "```", "说明": "用例把函数存成类属性"},
                                  "状态": "成功", "原因": ""})
    r, p, out = go("b_case", f)
    b = r["v2"]["边界复核"]
    check(r["reply"]["状态"] == "成功" and "修了用例自身的错" in b["结论"] and b["补改"]["改了用例"]
          and (out / "boundary" / "test_boundary_v2.run1.py").is_file() and util(p).count("x + x") == 1,
          "用例自身的编程错误 → 补改给改好的用例文件 → 再跑全过（代码不动）", b)
    f = Fake(bound="import unittest\nclass B(unittest.TestCase:\n    def test_x(self):\n        pass\n")
    r, p, _ = go("b_broken", f)
    check(r["reply"]["状态"] == "成功" and "跑不起来" in r["v2"]["边界复核"]["结论"] and "bfix" not in f.tags(),
          "用例文件跑不起来 → 记下，不算代码的问题", r["v2"]["边界复核"])
    check(r["v2"]["边界复核"].get("未复核") is True, "用例文件跑不起来 → bound 记 未复核=True（判定不变）", r["v2"]["边界复核"])
    f = Fake()
    r, p, _ = go("calls_cap", f, max_calls=1)
    check(r["reply"]["状态"] == "超出预期" and "未复核" in r["v2"]["边界复核"]["结论"] and r["v2"]["边界复核"].get("未复核") is True
          and "边界复核没做成" in r["reply"]["原因"], "调用次数用完时边界复核没做成 → 超出预期，不当通过", (r["reply"], r["v2"]["边界复核"]))

    def boom(user):
        raise RuntimeError("额度用完")
    f = Fake(bound=boom)
    r, p, _ = go("b_raise", f)
    b = r["v2"]["边界复核"]
    check(r["reply"]["状态"] == "超出预期" and "未复核" in b["结论"] and b.get("未复核") is True and "额度用完" in r["reply"]["原因"]
          and "x + x" in util(p), "边界复核时引擎抛错 → 超出预期、结论含未复核（代码不回滚）", (r["reply"], b))
    for nm, rep in (("b_empty", ""), ("b_blank", "  \n\n ")):
        f = Fake(bound=rep)
        r, p, _ = go(nm, f)
        b = r["v2"]["边界复核"]
        check(r["reply"]["状态"] == "超出预期" and "未复核" in b["结论"] and b.get("未复核") is True and "边界复核没做成" in r["reply"]["原因"],
              f"边界复核回复为空（{nm}）→ 超出预期、结论含未复核", (r["reply"], b))
    f = Fake()
    r, p, _ = go("b_pass", f)
    check(r["reply"]["状态"] == "成功" and "全过" in r["v2"]["边界复核"]["结论"] and "未复核" not in r["v2"]["边界复核"],
          "正常用例全过 → 仍成功（防回归）", r["v2"]["边界复核"])


# ------------------------------------------------------------------ 四、开关


def t_switch():
    print("四、开关")
    check(not V.enabled(), "缺省不走 v2")
    fake = Fake()
    sysmap = {V.BOUND_SYS: "bound"}
    old = V.call_claude
    V.call_claude = lambda s, u, timeout=300, model=None, **kw: fake(s, u, sysmap.get(s, "plan"), timeout)
    os.environ["DSLAGENT_PLANNER"] = "v2"
    try:
        check(V.enabled(), "DSLAGENT_PLANNER=v2 → 走 v2")
        p = make_proj("switch")
        r = RN.run(p, TASK, TMP / "out_switch", test_cmd=TEST_CMD)
        check(r.get("planner") == "v2" and r["fixed"] and r["engine_used"] == "v2" and "x + x" in util(p),
              "runner.run 转到 v2，结果字段同 runner（fixed / engine_used / calls / cost）", r.get("reply"))
    finally:
        V.call_claude = old
        os.environ.pop("DSLAGENT_PLANNER", None)


FAKE_CLI = r'''#!/usr/bin/env python3
import json, os, sys, time
sys.stdin.read()
cnt = os.environ["FAKE_CNT"]
n = int(open(cnt).read()) + 1 if os.path.exists(cnt) else 1
open(cnt, "w").write(str(n))
mode = os.environ["FAKE_MODE"]
def ev(o):
    print(json.dumps(o), flush=True)
def delta(t):
    ev({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": t}}})
if mode == "silent":
    time.sleep(30)
if mode == "invoke_ok" and n == 1:
    delta("先说两句<inv")
    delta("oke name=x>")
    time.sleep(30)
if mode == "angle":
    delta("if a<b and c>d: <div>x</div> List<int> 1<2")
if mode == "empty" or (mode == "idle_ok" and n == 1) or mode == "idle_always":
    delta("半截")
    delta("内容")
    if mode == "empty":
        sys.exit(3)
    time.sleep(30)
delta("好")
ev({"type": "assistant", "message": {"content": [{"type": "text", "text": "好的回复"}]}})
ev({"type": "result", "total_cost_usd": 0.01, "usage": {}})
'''


def t_idle_retry():
    print("五、空闲超时 / 重试 / 流落盘（假 CLI 脚本）")
    cli = TMP / "fake_cli.py"
    cli.write_text(FAKE_CLI, encoding="utf-8")
    cli.chmod(0o755)
    old_env, old_idle = os.environ["CBATCH_CLAUDE"], G.IDLE_SEC
    os.environ["CBATCH_CLAUDE"] = str(cli)
    G.IDLE_SEC = 1.5

    def go(mode, name):
        cnt = TMP / f"cnt_{name}"
        os.environ.update(FAKE_MODE=mode, FAKE_CNT=str(cnt))
        out = TMP / f"out_{name}"
        M = V.Model(out)
        try:
            return M, M("sys", "user", "t"), None, out
        except RuntimeError as e:
            return M, None, str(e), out
    try:
        M, text, err, out = go("idle_ok", "a")
        check(text == "好的回复" and M.n == 2 and len(M.log) == 2, "空闲后被杀，重试 1 次成功（调用数 2）", (text, err, M.n))
        check(M.log[0].get("failed") == "空闲超时" and M.log[1].get("retry") == 1 and M.log[1].get("first_fail") == "空闲超时",
              "calls 记录 retry=1 和首次失败原因", M.log)
        check(M.log[0]["sec"] < 20 and abs(M.cost - 0.01) < 1e-9, "空闲杀得快（没等满 30 秒），费用只计有结果的", M.log[0]["sec"])
        r1 = (out / "calls" / "01_t.reply.txt").read_text(encoding="utf-8")
        check(r1.startswith("半截内容") and "空闲超时" in r1, "被杀那次已收到的内容保留在 reply 文件", r1)
        M, text, err, out = go("idle_always", "b")
        check(text is None and M.n == 2 and "空闲超时" in (err or "") and "首次失败" in err, "重试仍失败 → 报原因（含首次失败）", err)
        M, text, err, out = go("empty", "c")
        check(text is None and M.n == 2 and "rc=3" in (err or ""), "rc≠0 也重试，仍失败报错", err)
        # 止损：输出工具调用格式 / 普通尖括号不误杀
        M, text, err, out = go("invoke_ok", "e")
        check(text == "好的回复" and M.n == 2 and M.log[0].get("failed") == "输出工具调用格式"
              and M.log[1].get("retry") == 1 and M.log[1].get("first_fail") == "输出工具调用格式" and M.log[0]["sec"] < 20,
              "出现 <invoke（跨增量拼接）→ 立即被杀，重试 1 次成功，calls 记录 reason", (text, err, M.log))
        old_first, G.FIRST_CAP = G.FIRST_CAP, 1
        try:
            M, text, err, out = go("silent", "h")
        finally:
            G.FIRST_CAP = old_first
        check(text is None and M.n == 2 and M.log[0].get("failed") == G.R_FIRST and M.log[0]["sec"] < 20 and G.R_FIRST in (err or ""),
              "claude 首个事件前静默超过 FIRST_CAP → 被杀（首字前静默超时），重试仍静默则报错", (err, M.log))
        M, text, err, out = go("angle", "g")
        check(text == "好的回复" and M.n == 1 and not M.log[0].get("failed"), "普通尖括号（a<b、<div>、List<int>）不误杀", (text, err, M.log))
        # 增量落盘：流还没结束时文件里已经有内容
        cnt = TMP / "cnt_d"
        os.environ.update(FAKE_MODE="idle_always", FAKE_CNT=str(cnt))
        G.IDLE_SEC = 3
        rp = TMP / "inc.reply.txt"
        import threading
        res = []
        th = threading.Thread(target=lambda: res.append(V.call_claude("s", "u", 60, None, reply_path=rp)))
        th.start()
        import time as _t
        seen = ""
        for _ in range(20):
            _t.sleep(0.2)
            seen = rp.read_text(encoding="utf-8") if rp.exists() else ""
            if seen:
                break
        check(seen == "半截内容" and th.is_alive(), "增量落盘：调用未结束时文件已有已收到的文本", seen)
        th.join()
        check(res[0]["reason"] == "空闲超时" and res[0]["partial"] == "半截内容", "被杀返回 reason 和 partial", res[0])
    finally:
        os.environ["CBATCH_CLAUDE"] = old_env
        G.IDLE_SEC = old_idle


def t_fix_input():
    print("补改入参：缺口所在函数代码不为空")
    G = [{"说明": "全量测试没过（失败摘要见下）"}]
    HDR = "【缺口所在函数的完整当前代码】"

    def case(name, summary, extra=None):
        p = make_proj(name)
        before = V.snapshot(p)
        (p / "pkg" / "util.py").write_text(UTIL.replace("return x * 2", "return x + x"), encoding="utf-8")
        for rel, txt in (extra or {}).items():
            (p / rel).parent.mkdir(parents=True, exist_ok=True)
            (p / rel).write_text(txt, encoding="utf-8")
        after = V.snapshot(p)
        u = V._fix_user(p, TASK, G, before, after, summary)
        return u.split(HDR, 1)[1]

    sec = case("fx_src", "  pkg/util.py:10 double: return x + x\n  AssertionError: 4 != 5\n")
    check("def double" in sec and "x + x" in sec, "失败指向源码函数 → 给该函数完整当前代码", sec[:300])
    sec = case("fx_test", "  tests/acc/test_existing.py:18 test_existing: assert p.returncode == 0\n  AssertionError: 一、查引用\n")
    check(sec.strip() and "未能定位" not in sec and "x + x" in sec, "只指向测试文件 → 退到本次改动所在函数", sec[:300])
    zs = "\n".join(f"行{i}" for i in range(1, 100)) + "\n"
    sec = case("fx_zs", "  脚本报错 scripts/a.zs:50 变量未定义\n  AssertionError\n", {"scripts/a.zs": zs})
    check("行50" in sec and "行20" in sec and "行80" in sec and "行19\n" not in sec and "行82" not in sec,
          ".zs 文件 → 行号前后各 30 行", sec[:200])
    p = make_proj("fx_none")
    snap = V.snapshot(p)
    sec = V._fix_user(p, TASK, G, snap, snap, "  tests/acc/test_existing.py:18 x\n").split(HDR, 1)[1]
    check("未能定位，附 diff" in sec, "什么都定位不到 → 写明未能定位而不是空", sec[:200])
    sec = case("fx_txt", "FAILED something", {"notes.txt": "hello\n"})
    check("未能定位" not in sec and "x + x" in sec, "无栈信息 → 给改动函数", sec[:200])


def t_reply():
    print("回复解析统一：补括号 / 状态上提 / 通用校验 + edits 结构")
    from tools.dslagent.verify import code as VC
    p = make_proj("rp_fix")
    ok_edit = json.dumps({"file": "pkg/util.py", "old": "return x * 2", "new": "return x + x"}, ensure_ascii=False)

    class FakeM:
        def __init__(self, *replies):
            self.replies, self.tags = list(replies), []

        def __call__(self, system, user, tag):
            self.tags.append(tag)
            return self.replies.pop(0)
    # 缺末尾括号 → 补括号后能套用，记录标 repaired
    M = FakeM('{"结果": {"edits": [' + ok_edit + '], "说明": "改了"}, "状态": "成功", "原因": ""')
    rec = VC.dispatch_fix(M, p, "s", "u", "fix")
    check(rec.get("套用") is True and rec.get("repaired") == "补括号" and M.tags == ["fix"], "fix 回复缺末尾括号 → 补括号解析，记录标 repaired", rec)
    # 状态写进结果里 → 状态上提
    p = make_proj("rp_lift")
    M = FakeM('{"结果": {"edits": [' + ok_edit + '], "状态": "成功", "原因": ""}}')
    rec = VC.dispatch_fix(M, p, "s", "u", "fix")
    check(rec.get("套用") is True and rec.get("repaired") == "状态上提", "状态写在结果里 → 状态上提，标 repaired", rec)
    # edits 结构不对 → 带问题重问 1 次（tag fix_reask），仍不合格 → 回复不合格
    p = make_proj("rp_bad")
    M = FakeM('{"结果": {"edits": "没有"}, "状态": "成功", "原因": ""}', '{"结果": {"edits": []}, "状态": "成功", "原因": ""}')
    rec = VC.dispatch_fix(M, p, "s", "u", "bfix")
    check(M.tags == ["bfix", "bfix_reask"] and rec.get("状态") == "成功" and rec.get("edits") == 0, "edits 结构不对 → 重问 1 次（bfix_reask），空 edits 合格", (M.tags, rec))
    M = FakeM("不是 JSON", "还不是")
    rec = VC.dispatch_fix(M, p, "s", "u", "fix")
    check(rec.get("状态") == "回复不合格" and M.tags == ["fix", "fix_reask"], "不是 JSON → 重问 1 次仍不合格", rec)
    M = FakeM('{"结果": {"edits": []}, "状态": "失败", "原因": ""}', '{"结果": {"edits": []}, "状态": "失败", "原因": "做不到"}')
    rec = VC.dispatch_fix(M, p, "s", "u", "fix")
    check(M.tags == ["fix", "fix_reask"] and rec.get("原因") == "做不到", "通用校验：状态不是成功时原因不能空（同子任务）", (M.tags, rec))


def t_reason_setup():
    print("安全约束的开局快照：第一次写 / 改 / 删文件前才设")
    from tools.dslagent import reason as R
    from tools.mock import MockClient
    p = make_proj("rs_eng")
    (p / "config.json").write_text('{"a": 1}\n', encoding="utf-8")
    R.STATE.update(snap=None, root=None, task="", log=[], fires=[])
    eng = V._engine_cls()(client=MockClient(default="x", offline=True), workdir=p, verbose=False, verbs_root=V.VERBS)
    eng.vars["task"] = TASK
    eng.vars["e"] = {"file": "config.json", "content": '{"a": 2}\n'}
    eng.run("用包 common text code\n设 n = 列文件 全部\n")
    check(R.STATE.get("snap") is None, "没碰写类动词 → 不设快照（不白读整个项目）")
    eng.run("设 w = 写文件 {e}\n")
    w = eng.vars["w"]
    check(w["ok"] == "否" and "安全约束拦下" in w["msg"] and (p / "config.json").read_text(encoding="utf-8") == '{"a": 1}\n',
          "覆盖任务没点名、开局就有的数据文件 → 被安全约束拦下（有开局快照）", w)
    check("config.json" in R.STATE["snap"] and R.STATE["task"] == TASK, "快照里有开局的文件、带任务原文")
    eng.run("设 d = 删文件 config.json\n")
    check(eng.vars["d"]["ok"] == "否" and "安全约束拦下" in eng.vars["d"]["msg"], "删没有等价迁移的数据文件 → 拦下", eng.vars["d"])
    # 整个 v2.run：计划里 改文件 一执行，快照里就是开局的内容
    f = Fake()
    r, p2, out = go("rs_run", f)
    check(r["fixed"] and R.STATE.get("snap") is not None and R.STATE["snap"]["pkg/util.py"] == UTIL.encode("utf-8"),
          "v2.run：第一次 改文件 前设了开局快照（pkg/util.py 是开局内容）", r.get("stop"))
    go("rs_run2", Fake(plan=plan("设 x = 打印 没写文件\n终止 失败 故意失败")))
    check(R.STATE.get("snap") is None, "下一次 v2.run 开头清掉上次的快照；没写类动词就不设")


def t_isolation():
    print("v2 不 import legacy；planner≠v2 时 runner.run 才转 legacy")
    import subprocess
    code = ("import sys; sys.path.insert(0, %r); "
            "import tools.dslagent.runner, tools.dslagent.v2, tools.dslagent.auto, tools.dslagent.common, tools.dslagent.engines, "
            "tools.dslagent.verify.code, tools.dslagent.packs.code, tools.dslagent.toolsub, tools.dslagent.dslmcp, tools.dslagent.plan, "
            "tools.dslagent.reason, tools.dslagent.datalog; "
            "print([m for m in sys.modules if m.startswith('tools.dslagent.legacy')])" % str(ROOT))
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60)
    check(out.returncode == 0 and out.stdout.strip() == "[]", "import v2 / runner / auto / verify / packs / engines … 不会带进 legacy", (out.stdout, out.stderr[-300:]))
    p = make_proj("iso")
    f = Fake()
    r, p, _ = go("iso_v2", f)
    check(r["fixed"] and not [m for m in sys.modules if m.startswith("tools.dslagent.legacy")], "跑一次 v2.run 之后 legacy 也没被 import", r.get("stop"))


def main():
    try:
        t_pack()
        t_gate()
        t_flow()
        t_switch()
        t_idle_retry()
        t_fix_input()
        t_reply()
        t_reason_setup()
        t_isolation()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
