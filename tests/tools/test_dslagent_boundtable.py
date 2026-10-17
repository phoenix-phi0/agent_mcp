# -*- coding: utf-8 -*-
"""tools/dslagent 边界复核的期望表路径（verify/bound_table.py、verify/asserts.py、verify/code.py 的 boundary / table_stage、v2 切表）。
用假模型，不调真模型。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_boundtable.py

  一、断言判定：词表里 11 种断言各至少 1 过 1 不过，另测预处理、异常、同改前遇异常、非法参数
  二、期望表切分：有表 / 无表 / 坏表 / 不是数组 / 空表；切出后 .zs 与没有表时一致；plan_fix 重写时保留原表 / 换新表
  三、覆盖检查与补表：规则覆盖率、每函数条数、专用夹具登记、补表触发（成功 / 回复解析不出 / 补完仍不达标）
  四、表校验：函数名 / 参数名 / 必填参数 / 断言词表不对的丢弃并计数
  五、boundary 表路径：全过 → 成功（0 次边界调用）；失败 → 判表错 → 成功；失败 → 代码错 → bfix → 重跑通过；判表错引擎出错 / 回复不合格 → 超出预期；
      补改弄坏测试撤回；无表 / 表不达标 / 表执行器出错 → 旧路径；同改前
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_bt_"))
os.environ["DSLAGENT_TMP"] = str(TMP / "tmp")
os.environ["CBATCH_CLAUDE"] = "/bin/true"
os.environ["DSLAGENT_DATASET"] = str(TMP / "dataset")
os.environ.pop("DSLAGENT_PLANNER", None)
os.environ.pop("DSLAGENT_PLAN_MODEL", None)

from tools.dslagent import agents as AG          # noqa: E402
from tools.dslagent import engines               # noqa: E402
from tools.dslagent import v2 as V               # noqa: E402
from tools.dslagent.verify import asserts as A   # noqa: E402
from tools.dslagent.verify import bound_table as BT   # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


# ------------------------------------------------------------------ 一、断言


def ok(a, v, **k):
    return A.check(a, v, **k)[0]


def t_asserts():
    print("一、断言判定")
    check(A.to_items("a\n\nb\n") == ["a", "b"] and A.to_items({"x": 1}) == [{"x": 1}] and A.to_items([1]) == [1], "预处理：字符串按行 / 字典单元素 / 列表照用")
    check(ok([{"条数": {"≤": 3}}], "a\nb\nc") and not ok([{"条数": {"≤": 2}}], "a\nb\nc"), "条数 ≤ 过 / 不过")
    check(ok([{"条数": {"=": 2}}], ["x", "y"]) and not ok([{"条数": {"=": 2}}], ["x"]), "条数 = 过 / 不过")
    check(ok([{"条数": {"≥": 1}}], {"a": 1}) and not ok([{"条数": {"≥": 1}}], ""), "条数 ≥ 过 / 不过")
    check(not ok([{"条数": {"<": 1}}], "a"), "条数 非法运算符判失败")
    check(ok([{"都不含": ["venv/"]}], "a.py\nb.py") and not ok([{"都不含": ["venv/"]}], "a.py\nvenv/x.py"), "都不含 过 / 不过")
    check(ok([{"都不含": {"字段": "id", "值": ["k"]}}], [{"id": "a"}]) and not ok([{"都不含": {"字段": "id", "值": ["k"]}}], [{"id": "k1"}]),
          "都不含 带字段 过 / 不过")
    check(ok([{"都含": ".py"}], "a.py\nb.py") and not ok([{"都含": ".py"}], "a.py\nb.txt"), "都含 过 / 不过")
    check(ok([{"有含": ["a", "b"]}], "xa\nyb") and not ok([{"有含": ["a", "c"]}], "xa\nyb"), "有含 过 / 不过")
    check(ok([{"都匹配": r"\d+\| line\d+"}], "1| line1\n2| line2") and not ok([{"都匹配": r"\d+\| line\d+"}], "1| line1\nxx")
          and not ok([{"都匹配": r"\d+"}], "12ab"), "都匹配 过 / 不过（完整匹配）")
    f = {"字段都在": {"字段": "status", "取值": ["done"]}}
    check(ok([f], [{"status": "done"}]) and not ok([f], [{"status": "done"}, {"status": "failed"}]) and not ok([f], [{"id": 1}]),
          "字段都在 过 / 不过 / 缺字段")
    o = {"有序": {"字段": "id", "方向": "降"}}
    check(ok([o], [{"id": "k3"}, {"id": "k2"}]) and not ok([o], [{"id": "k2"}, {"id": "k3"}])
          and ok([{"有序": {"字段": "行", "方向": "升"}}], "a\nb") and not ok([{"有序": {"字段": "行", "方向": "升"}}], "b\na"), "有序 降 / 升（行）过 / 不过")
    check(ok([{"行号连续": {"从": 5}}], "5| a\n6| b") and not ok([{"行号连续": {"从": 5}}], "5| a\n7| b") and not ok([{"行号连续": {"从": 1}}], "x\n2| b"),
          "行号连续 过 / 不过")
    check(ok([{"不抛异常": True}], "x", exc=None) and not ok([{"不抛异常": True}], None, exc="ValueError: x") and ok([{"不抛异常": False}], None, exc="E"),
          "不抛异常 过 / 不过 / 要求抛")
    check(ok([{"同改前": True}], "abc", before="abc") and not ok([{"同改前": True}], "abc", before="abd") and not ok([{"同改前": True}], "abc"),
          "同改前 过 / 不过 / 无改前结果")
    check(ok([{"同改前": True}], "EXC:E", before="EXC:E", exc="E") and not ok([{"同改前": True}], "EXC:E", before="x", exc="E"), "同改前 遇异常：改前改后同样异常算相同")
    check(ok([{"类型": "str"}], "x") and not ok([{"类型": "list"}], "x") and ok([{"类型": "int"}], 3) and not ok([{"类型": "int"}], True), "类型 过 / 不过（bool 不算 int）")
    check(ok([{"条数": {"≤": 3}}, {"都含": "a"}], "a\na") and not ok([{"条数": {"≤": 1}}, {"都含": "a"}], "a\na"), "多条断言全部满足才过")
    check(not ok([{"随便": 1}], "a") and not ok([], "a") and not ok("x", "a"), "未知断言 / 空列表 / 非列表判失败")
    check(not ok([{"条数": {"≥": 0}}], None, exc="E"), "调用抛异常时其余断言判失败")


# ------------------------------------------------------------------ 二、切表

ROWS = [{"规则": "把 pkg/util.py 里的 double 改成用加法实现（x + x），对外行为不变", "函数": "pkg/util.py::double", "参数": {"x": 3}, "期望": 6},
        {"规则": "把 pkg/util.py 里的 double 改成用加法实现（x + x），对外行为不变", "函数": "double", "参数": {"x": -2}, "断言": [{"类型": "int"}]},
        {"规则": "对外行为不变", "函数": "pkg/util.py::clamp", "参数": {"x": 5, "lo": 0, "hi": 3}, "断言": [{"同改前": True}]}]


def table_text(rows):
    return "\n#期望表\n```json\n" + json.dumps(rows, ensure_ascii=False) + "\n```\n"


def t_split():
    print("二、期望表切分")
    plan = "用包 common text code\n预算 调用 4 秒 300\n终止 成功 ok\n"
    rest, rows, note = BT.split_table(plan + table_text(ROWS))
    check(rows == ROWS and note == "" and rest == plan, "有表：切出表，前面的 .zs 原样", (note, rest))
    rest, rows, note = BT.split_table(plan)
    check(rows is None and note == "无表" and rest == plan, "无表")
    rest, rows, note = BT.split_table(plan + "#期望表\n[{坏的")
    check(rows is None and note == "表解析失败" and rest == plan, "坏表（JSON 解析失败）", note)
    rest, rows, note = BT.split_table(plan + '#期望表\n{"a": [1]}')
    check(rows is None and note in ("表不是数组", "表解析失败") and rest == plan, "表不是数组", note)
    rest, rows, note = BT.split_table(plan + "#期望表\n[]")
    check(rows is None and note == "表为空" and rest == plan, "空表", note)
    rest, rows, note = BT.split_table(plan + "#期望表\n没有数组")
    check(rows is None and note == "表解析失败", "标题后没有数组", note)
    rest, rows, note = BT.split_table("```\n" + plan + "```\n" + table_text(ROWS))
    check(rows == ROWS and rest.endswith("```\n"), "计划带围栏、表在围栏外", rest)


# ------------------------------------------------------------------ 三、覆盖 / 补表 / 夹具


def t_cover():
    print("三、覆盖检查、补表、夹具登记")
    task = "把 pkg/util.py 里的 double 改成用加法实现（x + x），对外行为不变。测试文件不要改。"
    cl = {"items": [["改", "pkg/util.py", "double"], ["改", "pkg/util.py", "12-30"], ["新建", "pkg/new.py", ""], ["改", "tests/test_a.py", "t"], ["删", "pkg/o.py", ""]]}
    units = BT.planned_units(cl)
    check([u["label"] for u in units] == ["pkg/util.py:double", "pkg/new.py"], "改动函数取清单里的 改 函数名 / 新建；行号范围、测试、删除不算", units)
    check(BT.unit_matches(units[0], "double") and BT.unit_matches(units[0], "pkg/util.py::double") and not BT.unit_matches(units[0], "other.py::double")
          and BT.unit_matches(units[1], "pkg/new.py::f") and not BT.unit_matches(units[1], "pkg/util.py::f"), "表项函数名与改动函数的对应")
    c = BT.table_check(task, ROWS, units[:1])
    check(c["达标"] and c["覆盖率"] >= 0.7 and c["各函数条数"] == {"pkg/util.py:double": 2}, "覆盖率够、每函数 ≥2 条 → 达标", c)
    c = BT.table_check(task, ROWS[:1], units[:1])
    check(not c["达标"] and "条数不够" in c["原因"], "某函数只有 1 条 → 不达标", c)
    c = BT.table_check(task, [dict(r, 规则="毫不相干的话") for r in ROWS], units[:1])
    check(not c["达标"] and "覆盖率" in c["原因"] and c["未覆盖"], "规则字段没引到任务原文 → 覆盖率不达标，列出未覆盖", c)
    check(BT.table_check("很短", ROWS, [])["覆盖率"] == 1.0, "任务里切不出规则候选就不卡覆盖率")
    bad = [{"函数": "f"}, {"函数": "f", "期望": 1, "期望包含": "x"}, {"函数": "f", "断言": [{"乱写": 1}]}, "不是对象", {"函数": "f", "断言": []}]
    check(all(BT.row_shape_problem(r) for r in bad) and BT.row_shape_problem(ROWS[1]) is None, "表项结构问题：缺断言 / 双期望 / 词表外断言 / 非对象 / 空断言")
    check("CBATCH_HOME" in BT.fixture_notes("要改 tools/cbatch.py 的 jobs") and "GBATCH_HOME" not in BT.fixture_notes("tools/cbatch.py")
          and BT.fixture_notes("pkg/util.py") == "", "专用夹具按涉及的模块登记，没涉及就不追加")
    reg = BT.registry()
    check(set(reg) == {"tools/cbatch.py", "tools/gbatch.py"} and all("构造" in v and "说明" in v for v in reg.values()), "夹具登记表：模块路径 → 构造 + 说明")
    sysp = AG.PLAN.system_text()
    check("批量执行器夹具" not in sysp and "CBATCH_HOME" not in sysp and "#期望表" in sysp and "同改前" in sysp
          and "任务要求改变行为的函数不要写同改前" in sysp, "规划 system 里没有写死 jobs 夹具；有期望表要求和「同改前」限制")
    check(AG.of_tag("bound_judge").step == "bound" and AG.of_tag("bound_judge_reask") is AG.BOUND_JUDGE and AG.of_tag("table_fill").step == "plan"
          and engines.step_of("bound_judge") == "bound" and engines.step_of("table_fill") == "plan", "tag 归步骤：bound_judge → bound；table_fill → plan")
    check(AG.BOUND_JUDGE.retry.times == 2 and AG.BOUND_JUDGE.tools == "无" and AG.TABLE_FILL.retry.times == 1, "bound_judge 最多 2 次，补表 1 次")
    check("条目序号" in AG.BOUND_JUDGE.system_text() and "不写 .zs" in AG.TABLE_FILL.system_text() and "断言词表" in AG.TABLE_FILL.system_text(),
          "bound_judge system = judge_prompt；补表 system 带表项格式")


# ------------------------------------------------------------------ 四、校验 / 判定


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
    return p


def t_validate():
    print("四、表校验与判定")
    p = make_proj("val")
    after = UTIL.replace("return x * 2", "return x + x")
    base = {"pkg/util.py": UTIL, "pkg/other.py": OTHER}
    cur = {"pkg/util.py": after, "pkg/other.py": OTHER}
    ch = BT.changed_callables(p, base, cur)
    check([t["key"] for t in ch] == ["pkg/util.py::double"] and ch[0]["params"] == [("x", True)], "改动函数：只有 double 被改，签名取自改后代码", ch)
    (p / "pkg" / "util.py").write_text(after, encoding="utf-8")
    rows = ROWS + [
        {"规则": "r", "函数": "nope", "参数": {}, "期望": 1},
        {"规则": "r", "函数": "double", "参数": {"y": 1}, "期望": 1},
        {"规则": "r", "函数": "double", "参数": {}, "期望": 1},
        {"规则": "r", "函数": "double", "参数": {"x": 1}, "断言": [{"乱写": 1}]},
        {"规则": "r", "函数": "动词 double(x)", "参数": {"x": 1}, "期望": 2},
        {"规则": "r", "函数": "pkg/util.py::clamp", "参数": {"x": 1, "lo": 0}, "期望": 1},
        {"规则": "r", "函数": "pkg/other.py::twice", "参数": {"x": 2}, "期望": 4}]
    kept, dropped = BT.validate(rows, p, ch)
    check(len(kept) == 5 and len(dropped) == 5, "合格 5 条（3 条原表 + 带「动词 」前缀的写法 + 未改动的 twice），丢弃 5 条", ([d["why"] for d in dropped], len(kept)))
    whys = " ".join(d["why"] for d in dropped)
    check("函数名不在" in whys and "多 ['y']" in whys and "缺 ['x']" in whys and "断言词表" in whys and "缺 ['hi']" in whys,
          "丢弃原因：函数名 / 多余参数 / 缺必填参数 / 词表外断言 / 缺必填（未改动函数也按真实签名校验）", whys)
    work = TMP / "val_run"
    res, fatals, sec = BT.run_cases(kept, p, sys.executable, work / "a")
    check(not fatals and all(r is not None for r in res.values()) and res[0]["rep"] == "6", "子进程执行：double(3) = 6", (fatals, res.get(0)))
    bef, bf, _ = BT.run_before(kept, base, sys.executable, work / "b")
    js = BT.judge_all(kept, res, bef)
    check(all(j["ok"] for j in js), "期望 / 断言 / 同改前（改前副本 clamp 结果一致）全过", js)
    k = dict(kept[0], exp=7)
    ok1, actual, why = BT.judge_one(k, res[0])
    check(not ok1 and why == ["期望不符"] and actual == "6", "期望不符 → 失败，实际值带回")
    kx = dict(kept[0], exp_kind="期望异常", exp="ValueError")
    check(not BT.judge_one(kx, res[0])[0], "期望异常但没抛 → 失败")
    kc = dict(kept[0], exp_kind="期望包含", exp="6")
    check(BT.judge_one(kc, res[0])[0], "期望包含（返回值是数字时取 JSON 文本）")
    check(not BT.judge_one(kept[0], None)[0], "没有结果（子进程失败 / 超时）→ 失败")
    big = {"x": 1}
    (p / "pkg" / "big.py").write_text("def big(n):\n    return 'a' * n\n\n\ndef slow(n):\n    import time\n    time.sleep(n)\n    return 1\n", encoding="utf-8")
    cases = [{"key": "pkg/big.py::big", "t": BT.resolve(p, "pkg/big.py::big"), "args": {"n": 150000}, "files": {}},
             {"key": "pkg/big.py::slow", "t": BT.resolve(p, "pkg/big.py::slow"), "args": {"n": 8}, "files": {}}]
    r2, f2, _ = BT.run_cases(cases, p, sys.executable, work / "c")
    check(len(json.loads(r2[0]["rep"])) == 150000, "结果上限 200000 字符（15 万字符不被截断）")
    check(r2[1] is not None and "CallTimeout" in (r2[1]["exc"] or ""), "单次调用 5 秒超时被打断", r2[1])
    jp = BT.parse_judge('[{"条目序号": 1, "判定": "期望写错", "依据": "x"}, {"条目序号": 2, "判定": "代码错", "依据": "y"}]')
    check(not jp["problems"] and jp["value"] == {1: ("期望写错", "x"), 2: ("代码错", "y")}, "bound_judge 回复解析")
    check(BT.parse_judge("没有数组")["problems"] and BT.parse_judge('[{"条目序号": 1, "判定": "随便"}]')["problems"] and BT.parse_judge("[]")["problems"],
          "bound_judge 回复不合格：无数组 / 判定不对 / 空数组")


# ------------------------------------------------------------------ 五、全流程


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
PLAN_BODY = '''
设 res = 改文件 {e1}
如果 {res.ok} 不等于 是
  终止 失败 没套上：{res.msg}
结束
终止 成功 double 改成加法
'''


def plan(table=None, head="用包 common text code\n预算 调用 4 秒 300\n", cl="改 pkg/util.py:double"):
    return head + PLAN_BODY.strip("\n") + "\n\n" + EDIT_DOUBLE + "\n#清单\n" + cl + "\n" + (table_text(table) if table is not None else "")


BOUND_OK = "import unittest\n\nfrom pkg.util import double\n\n\nclass B(unittest.TestCase):\n    def test_zero(self):\n        \"\"\"0 的两倍还是 0\"\"\"\n        self.assertEqual(double(0), 0)\n"
FIX_CLAMP = {"结果": {"edits": [{"file": "pkg/util.py", "old": "def clamp(x, lo, hi):\n",
                                "new": "def clamp(x, lo, hi):\n    if lo > hi:\n        raise ValueError(\"区间不对\")\n"}],
                     "说明": "加区间检查"}, "状态": "成功", "原因": ""}
RULE = "把 pkg/util.py 里的 double 改成用加法实现（x + x），对外行为不变"
GOOD = [{"规则": RULE, "函数": "pkg/util.py::double", "参数": {"x": 3}, "期望": 6},
        {"规则": RULE, "函数": "double", "参数": {"x": -2}, "断言": [{"类型": "int"}, {"同改前": True}]},
        {"规则": "对外行为不变", "函数": "pkg/util.py::clamp", "参数": {"x": 5, "lo": 0, "hi": 3}, "断言": [{"同改前": True}]}]
WRONG = {"规则": RULE, "函数": "pkg/util.py::double", "参数": {"x": 4}, "期望": 9}                       # 期望写错
CLAMP_EXC = {"规则": "区间反了要报错", "函数": "pkg/util.py::clamp", "参数": {"x": 5, "lo": 3, "hi": 1}, "期望异常": "ValueError"}


def verdict(*pairs):
    return json.dumps([{"条目序号": i, "判定": v, "依据": "依据"} for i, v in pairs], ensure_ascii=False)


class Fake:
    """按 tag 前缀回复；值可以是文本、dict（转 JSON）、callable(user) → 文本、列表（依次回复）。记下每次的 (tag, system, user)。"""

    def __init__(self, **replies):
        self.replies = {"plan": plan(GOOD), "bound": BOUND_OK}
        self.replies.update(replies)
        self.log = []

    def __call__(self, system, user, tag, timeout, model=None, **kw):
        self.log.append((tag, system, user))
        key = next((k for k in sorted(self.replies, key=len, reverse=True) if tag.startswith(k)), None)
        r = self.replies.get(key)
        if callable(r):
            r = r(user)
        if isinstance(r, list):
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


def t_flow():
    print("五、boundary 表路径（假模型）")
    # 全过
    f = Fake()
    r, p, out = go("t_ok", f)
    b = r["v2"]["边界复核"]
    check(r["reply"]["状态"] == "成功" and f.tags() == ["plan"] and r["calls"] == 1, "表全过 → 成功，边界复核 0 次模型调用", (f.tags(), r["reply"]))
    check(b["方式"] == "表" and b["表条数"] == 3 and b["丢弃条数"] == 0 and b["失败条数"] == 0 and b["判表错条数"] == 0 and "跑表" in b["各段秒数"]
          and "全过" in b["结论"], "bound 记录：方式 / 表条数 / 丢弃 / 失败 / 判表错 / 各段秒数", b)
    et = json.loads((out / "expect_table.json").read_text(encoding="utf-8"))
    check(et["rows"] == GOOD and et["达标"] and r["v2"]["期望表"]["表条数"] == 3 and "rows" not in r["v2"]["期望表"], "out/expect_table.json 存表；result 里记检查不重复存表")
    check(not (out / "boundary" / "test_boundary_v2.py").exists() and (out / "boundary" / "table_run1.json").is_file(), "表路径不写 unittest 用例，写 table_run1.json")
    # 切出后 .zs 与无表时一致
    f2 = Fake(plan=plan(None))
    r2, _, out2 = go("t_nt", f2)
    check((out / "plan.zs").read_text(encoding="utf-8") == (out2 / "plan.zs").read_text(encoding="utf-8")
          and r2["v2"]["边界复核"]["方式"] == "模型" and r2["v2"]["边界复核"]["表回退原因"] == "无表" and f2.tags() == ["plan", "bound"] and "期望表" in r2["v2"],
          "切出表后的 .zs 与没有表时完全一致；无表 → 旧路径（模型写 unittest）", (r2["v2"]["边界复核"], f2.tags()))
    check(not (out2 / "expect_table.json").exists(), "无表不写 expect_table.json")
    # 失败 → 判表错 → 成功
    f = Fake(plan=plan(GOOD + [WRONG]), bound_judge=verdict((1, "期望写错")))
    r, p, out = go("t_wrong", f)
    b = r["v2"]["边界复核"]
    ju = next(u for t, _, u in f.log if t == "bound_judge")
    check(r["reply"]["状态"] == "成功" and f.tags() == ["plan", "bound_judge"] and b["失败条数"] == 1 and b["判表错条数"] == 1 and "丢弃" in b["结论"],
          "表有 1 条写错 → 判表错（1 次调用）→ 丢弃 → 成功", (f.tags(), b))
    check("【任务原文】" in ju and "规则原文：" + RULE in ju and "期望：" in ju and "def double" in ju and "实际：8" in ju,
          "判表错入参：任务原文、改动函数当前代码、失败条目（规则 / 函数 / 输入 / 期望 / 实际）", ju)
    check(b["判表错"][0]["函数"] == "pkg/util.py::double" and "秒" not in b and "判表错" in b["各段秒数"], "记录判表错条目和耗时")
    # 失败 → 代码错 → bfix → 重跑通过
    f = Fake(plan=plan(GOOD + [CLAMP_EXC]), bound_judge=verdict((1, "代码错")), bfix=FIX_CLAMP)
    r, p, out = go("t_fix", f)
    b = r["v2"]["边界复核"]
    bu = next(u for t, _, u in f.log if t == "bfix")
    check(r["reply"]["状态"] == "成功" and f.tags() == ["plan", "bound_judge", "bfix"] and "raise ValueError" in util(p) and b["第2次"]["失败条数"] == 0
          and b["失败条数"] == 1 and "补改" in b["结论"], "失败 → 判代码错 → bfix 改代码 → 同一张表重跑通过 → 成功", (f.tags(), b))
    check("期望表里没过的条目" in bu and "规则原文：区间反了要报错" in bu and "不允许改用例" in bu and "def clamp" in bu, "bfix 入参是失败清单，说明不许改用例，带函数全文", bu)
    # bfix 想改用例 → 忽略
    f = Fake(plan=plan(GOOD + [CLAMP_EXC]), bound_judge=verdict((1, "代码错")),
             bfix=dict(FIX_CLAMP, 结果=dict(FIX_CLAMP["结果"], 用例代码="import unittest\n")))
    r, p, out = go("t_case", f)
    check(r["reply"]["状态"] == "成功" and r["v2"]["边界复核"]["补改"]["忽略用例代码"] is True and not (out / "boundary" / "test_boundary_v2.py").exists(),
          "表模式下 bfix 给的「用例代码」被忽略，不写用例文件")
    # 补改后仍不过
    f = Fake(plan=plan(GOOD + [CLAMP_EXC]), bound_judge=verdict((1, "代码错")),
             bfix={"结果": {"edits": [{"file": "pkg/util.py", "old": "    return x\n", "new": "    return x  # 看过了\n"}]}, "状态": "成功", "原因": ""})
    r, p, _ = go("t_still", f)
    check(r["reply"]["状态"] == "超出预期" and "仍没过" in r["reply"]["原因"] and "clamp" in r["reply"]["原因"], "补改后表项仍没过 → 超出预期", r["reply"])
    # 补改没改代码
    f = Fake(plan=plan(GOOD + [CLAMP_EXC]), bound_judge=verdict((1, "代码错")), bfix={"结果": {"edits": []}, "状态": "超出预期", "原因": "任务没要求"})
    r, p, _ = go("t_noedit", f)
    check(r["reply"]["状态"] == "超出预期" and "补改没有改代码" in r["reply"]["原因"], "bfix 没改代码 → 超出预期", r["reply"])
    # 补改弄坏测试
    f = Fake(plan=plan(GOOD + [CLAMP_EXC]), bound_judge=verdict((1, "代码错")),
             bfix={"结果": {"edits": [{"file": "pkg/util.py", "old": "        return hi\n", "new": "        return lo\n"}]}, "状态": "成功", "原因": ""})
    r, p, _ = go("t_break", f)
    check(r["reply"]["状态"] == "超出预期" and "撤回" in r["reply"]["原因"] and "return hi" in util(p) and "x + x" in util(p), "补改弄坏现有测试 → 撤回，超出预期", r["reply"])
    # 判表错引擎出错 / 回复不合格
    def boom(user):
        raise RuntimeError("额度用完")
    f = Fake(plan=plan(GOOD + [WRONG]), bound_judge=boom)
    r, p, _ = go("t_jerr", f)
    b = r["v2"]["边界复核"]
    check(r["reply"]["状态"] == "超出预期" and b.get("未复核") is True and "判表错没做成" in b["结论"] and "额度用完" in r["reply"]["原因"] and "bfix" not in f.tags()
          and "x + x" in util(p), "判表错引擎出错 → 未复核，超出预期，不放行也不回滚", (r["reply"], b))
    f = Fake(plan=plan(GOOD + [WRONG]), bound_judge="没有数组")
    r, p, _ = go("t_jbad", f)
    check(r["reply"]["状态"] == "超出预期" and r["v2"]["边界复核"].get("未复核") is True and f.tags().count("bound_judge") + f.tags().count("bound_judge_reask") == 2,
          "判表错回复不合格 → 重问 1 次 → 仍不合格 → 未复核，超出预期", f.tags())
    f = Fake(plan=plan(GOOD + [WRONG]), bound_judge=["没有数组", verdict((1, "期望写错"))])
    r, p, _ = go("t_jre", f)
    check(r["reply"]["状态"] == "成功" and "bound_judge_reask" in f.tags(), "判表错第一次回复不合格、重问后合格 → 照常", f.tags())
    f = Fake(plan=plan(GOOD + [WRONG]), bound_judge=verdict((7, "期望写错")))
    r, p, _ = go("t_jmiss", f)
    check(r["reply"]["状态"] == "超出预期" and "bfix" in f.tags(), "回复里缺的条目按代码错处理 → 进 bfix", f.tags())
    # 丢弃计数
    f = Fake(plan=plan(GOOD + [{"规则": "r", "函数": "nope", "参数": {}, "期望": 1}]))
    r, p, _ = go("t_drop", f)
    b = r["v2"]["边界复核"]
    check(r["reply"]["状态"] == "成功" and b["丢弃条数"] == 1 and "函数名不在" in b["丢弃原因"][0] and f.tags() == ["plan"], "校验丢弃的条目计数，不影响结果", b)
    # 表执行器出错 → 旧路径
    old = BT.CHILD
    BT.CHILD = Path("/nonexistent/child.py")
    try:
        f = Fake()
        r, p, _ = go("t_exec", f)
    finally:
        BT.CHILD = old
    b = r["v2"]["边界复核"]
    check(r["reply"]["状态"] == "成功" and b["方式"] == "模型" and "表执行器出错" in b["表回退原因"] and f.tags() == ["plan", "bound"], "表执行器本身出错 → 旧路径（模型写 unittest）", (b, f.tags()))
    # 校验后可执行的表项太少 → 旧路径
    f = Fake(plan=plan(GOOD[:1] + [{"规则": RULE, "函数": "nope", "参数": {}, "期望": 1}] * 2, cl="改 pkg/util.py:double"))
    r, p, _ = go("t_few", f)
    check(r["v2"]["边界复核"]["方式"] == "模型" and "表不达标" in r["v2"]["期望表"]["说明"], "结构合格但函数条数不够 → 补表后仍不达标时走旧路径", (r["v2"]["期望表"], f.tags()))
    # 同改前：改变了行为的函数写了同改前 → 失败 → 判表错
    f = Fake(plan=plan(GOOD + [{"规则": RULE, "函数": "double", "参数": {"x": 1}, "期望": 2, "断言": [{"同改前": True}]}]),
             bound_judge=verdict((1, "期望写错")))
    r, p, _ = go("t_before", f)
    check(r["reply"]["状态"] == "成功" and f.tags() == ["plan"], "同改前 对没变行为的 double 一致 → 过（改前副本 x*2 与改后 x+x 同值）", f.tags())
    BEFORE_BAD = {"规则": "double 现在是加法", "函数": "pkg/util.py::double", "参数": {"x": 2}, "断言": [{"同改前": True}, {"类型": "str"}]}
    f = Fake(plan=plan(GOOD + [BEFORE_BAD]), bound_judge=verdict((1, "期望写错")))
    r, p, _ = go("t_before2", f)
    check(r["reply"]["状态"] == "成功" and f.tags() == ["plan", "bound_judge"] and r["v2"]["边界复核"]["失败条数"] == 1, "同改前 + 断言不满足 → 失败 → 判表错", (f.tags(), r["v2"]["边界复核"]))


def t_plan_table():
    print("六、规划：表不达标补表；plan_fix 保留 / 换表")
    thin = GOOD[:1]
    fill = json.dumps(GOOD[1:], ensure_ascii=False)
    f = Fake(plan=plan(thin), table_fill=fill)
    r, p, out = go("p_fill", f)
    e = r["v2"]["期望表"]
    check(f.tags() == ["plan", "table_fill"] and e["补表"] and e["达标"] and e["补表条数"] == 2 and r["v2"]["边界复核"]["方式"] == "表" and r["reply"]["状态"] == "成功",
          "表只有 1 条 → 补表 1 次 → 达标 → 走表路径", (f.tags(), e))
    fu = next(u for t, _, u in f.log if t == "table_fill")
    fs = next(s for t, s, _ in f.log if t == "table_fill")
    check("【还没被引到的任务原文规则】" in fu and "pkg/util.py:double" in fu and "断言词表" in fs, "补表入参：之前的表、要改的函数、条数不够的函数；system 带表格式")
    et = json.loads((out / "expect_table.json").read_text(encoding="utf-8"))
    check(len(et["rows"]) == 3 and et["补表"], "expect_table.json 存补表后的表")
    f = Fake(plan=plan(thin), table_fill="补不了")
    r, p, _ = go("p_fill_bad", f)
    check(f.tags() == ["plan", "table_fill", "bound"] and r["v2"]["期望表"]["补表错误"] and r["v2"]["边界复核"]["方式"] == "模型" and r["reply"]["状态"] == "成功",
          "补表回复解析不出数组 → 当没补，表仍不达标 → 旧路径", (f.tags(), r["v2"]["期望表"]))

    def boom(user):
        raise RuntimeError("引擎挂了")
    f = Fake(plan=plan(thin), table_fill=boom)
    r, p, _ = go("p_fill_err", f)
    check(r["reply"]["状态"] == "成功" and r["v2"]["边界复核"]["方式"] == "模型" and "引擎挂了" in r["v2"]["期望表"]["补表错误"], "补表引擎出错不影响计划，走旧路径", r["v2"]["期望表"])
    f = Fake(plan=plan(thin), table_fill="[]")
    r, p, _ = go("p_fill_still", f)
    check(r["v2"]["期望表"]["达标"] is False and "表不达标" in r["v2"]["期望表"]["说明"] and f.tags().count("table_fill") == 1 and r["v2"]["边界复核"]["方式"] == "模型",
          "补完仍不达标 → 记「表不达标」，只补 1 次，走旧路径", r["v2"]["期望表"])
    # 坏表 / 空表 → 无表，不影响计划
    for nm, txt in (("p_bad", plan(None) + "#期望表\n[{坏"), ("p_empty", plan(None) + "#期望表\n[]"), ("p_obj", plan(None) + '#期望表\n{"a": 1}')):
        f = Fake(plan=txt)
        r, p, _ = go(nm, f)
        check(r["reply"]["状态"] == "成功" and f.tags() == ["plan", "bound"] and r["v2"]["期望表"]["说明"] in ("表解析失败", "表为空", "表不是数组"),
              f"{nm}：表坏 / 空 / 不是数组 → 记无表，计划照常通过，走旧路径", (r["v2"]["期望表"], f.tags()))
    # plan_fix：第一次计划没过检查（缺 预算），带表；重写的回复没有表 → 保留原表
    bad_head = plan(GOOD, head="用包 common text code\n")
    f = Fake(plan=[bad_head], plan_fix=plan(None))
    f.replies["plan"] = bad_head
    f.replies["plan_fix"] = plan(None)
    r, p, out = go("p_keep", f)
    et = json.loads((out / "expect_table.json").read_text(encoding="utf-8"))
    check(r["v2"]["重写"] is True and f.tags() == ["plan", "plan_fix"] and et["rows"] == GOOD and r["v2"]["边界复核"]["方式"] == "表" and r["reply"]["状态"] == "成功",
          "plan_fix 重写的回复没有表 → 保留原表，边界复核照走表路径", (f.tags(), r["v2"]["期望表"]))
    fu = next(u for t, _, u in f.log if t == "plan_fix")
    check("#期望表" not in fu, "plan_fix 的 user 里没有表（表已切出，.zs 以外的内容不进重写入参）")
    # plan_fix 回复里有新表 → 用新表
    new_rows = GOOD + [WRONG]
    f = Fake()
    f.replies["plan"] = plan(GOOD[:2], head="用包 common text code\n")
    f.replies["plan_fix"] = plan(new_rows)
    f.replies["bound_judge"] = verdict((1, "期望写错"))
    r, p, out = go("p_new", f)
    et = json.loads((out / "expect_table.json").read_text(encoding="utf-8"))
    check(et["rows"] == new_rows and r["reply"]["状态"] == "成功", "plan_fix 回复里有新表 → 用新表", (f.tags(), len(et["rows"])))
    # 计划过检查，表只用于边界；强制 .zs 里不含表
    check("期望表" not in (out / "plan.zs").read_text(encoding="utf-8") and "期望表" not in (out / "plan_v1.zs").read_text(encoding="utf-8"), "plan*.zs 里没有表")
    check("期望表" in (out / "plan_v1.raw.txt").read_text(encoding="utf-8"), "plan_vN.raw.txt 留着模型原始回复（含表）")


def main():
    try:
        t_asserts()
        t_split()
        t_cover()
        t_validate()
        t_flow()
        t_plan_table()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
