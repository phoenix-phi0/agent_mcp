# -*- coding: utf-8 -*-
"""动词参数里的 {名 或}、{名 或 默认} 整块算一个参数（K102）。

    .venv/bin/python tests/dsl/test_alt_args.py

背景：动词参数按空白切、切在展开之前。早先直接 rest.split()，
「替换 {prev_code 或} ^\\s+|\\s+$」被切成「{prev_code」「或}」「^\\s+|\\s+$」，
正则那一格拿到的是「或}」，运行时报「正则写错了（bad escape \\s）：或}」；
「{x 或 默认}」更是多出参数，报「最多接受 3 个参数」。设 / 打印 整行展开、
不切参数，所以那边一直正常。

  一、替换 / 截取 / 按正则切分 / 相等 / 匹配 带 {x 或}、{x 或 默认}，
      变量有值、为空、未定义三种
  二、键=值 的值写 {x 或 默认}
  三、原有写法不变：没有花括号的切分、{变量}（值里有空格）、{{字面}}、
      没有「或」的 {…}（正则量词）照旧按空白切
  四、加载检查（check_verb_calls）跟运行时切法一致：{x 或 默认} 不报参数过多
  五、split_args 本身：同 str.split，只多认带「或」的 {…}
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import packs                        # noqa: E402
from tools.dsl import DSLEngine, DSLError      # noqa: E402
from tools.dsl_core import split_args          # noqa: E402
from tools.dslagent import loadcheck as LC     # noqa: E402
from tools.mock import MockClient              # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


REG = packs.registry(["common", "text"], ROOT, cache=False)


def run(script: str, **vars_):
    e = DSLEngine(client=MockClient(offline=True), workdir=ROOT, verbose=False,
                  verbs=packs.registry(["common", "text"], ROOT, cache=False),
                  verbs_root=packs.verbs_root())
    e.vars.update(vars_)
    try:
        return e.run(script)
    except DSLError as ex:
        return f"ERR {ex}"


# 三种状态：有值 / 为空 / 未定义
STATES = [("有值", {"x": "  ab  "}), ("为空", {"x": ""}), ("未定义", {})]


def main():
    print("一、动词参数里的 {x 或} / {x 或 默认}")
    want = {"有值": "[ab]", "为空": "[]", "未定义": "[]"}
    for label, vs in STATES:
        out = run("设 r = 替换 {x 或} ^\\s+|\\s+$ \n打印 [{r}]", **vs)
        check(out == want[label], f"替换 {{x 或}}（{label}）：{out}")

    want = {"有值": "[__ab__]", "为空": "[默_认]", "未定义": "[默_认]"}
    for label, vs in STATES:
        out = run("设 r = 替换 {x 或 默 认} \\s _\n打印 [{r}]", **vs)
        check(out == want[label], f"替换 {{x 或 默认}}，默认里带空格（{label}）：{out}")

    want = {"有值": "[ab]", "为空": "[]", "未定义": "[]"}
    for label, vs in STATES:
        out = run("设 r = 截取 {x 或} 3 2\n打印 [{r}]", **vs)
        check(out == want[label], f"截取 {{x 或}}（{label}）：{out}")

    # 起 那一格写 {n 或 2}：没给 n 就从第 2 个字取
    out = run("设 r = 截取 ABCD {n 或 2} 2\n打印 [{r}]")
    check(out == "[BC]", f"截取 起={{n 或 2}}（未定义用默认）：{out}")
    out = run("设 r = 截取 ABCD {n 或 2} 2\n打印 [{r}]", n="3")
    check(out == "[CD]", f"截取 起={{n 或 2}}（有值）：{out}")

    # 文本为空时 re.split 本来就给 [""]（跟写「按正则切分 {s} ,」、s 为空一样）
    want = {"有值": '["a", "b"]', "为空": '[""]', "未定义": '[""]'}
    for label, _ in STATES:
        # 按正则切分：文本那一格是 {s 或}
        s = {"有值": "a,b", "为空": ""}.get(label)
        vars_ = {"s": s} if s is not None else {}
        out = run("设 r = 按正则切分 {s 或} ,\n打印 {r}", **vars_)
        check(out.replace(" ", "") == want[label].replace(" ", ""),
              f"按正则切分 {{s 或}}（{label}）：{out}")

    want = {"有值": "[否]", "为空": "[是]", "未定义": "[是]"}
    for label, vs in STATES:
        out = run("设 r = 相等 {x 或} {y 或}\n打印 [{r}]", **vs)
        check(out == want[label], f"相等 {{x 或}} {{y 或}}（{label}）：{out}")

    out = run("设 m = 匹配 {x 或 abc} b\n打印 {m}")
    lit = run("设 m = 匹配 abc b\n打印 {m}")
    check("ERR" not in out and out == lit, f"匹配 {{x 或 abc}}（未定义）跟写字面 abc 一样：{out}")

    print("二、键=值 的值写 {x 或 默认}")
    out = run("设 r = 替换 文本={x 或 a b} 正则=\\s 替换为=_\n打印 [{r}]")
    check(out == "[a_b]", f"键=值 {{x 或 a b}}（未定义）：{out}")
    out = run("设 r = 替换 文本={x 或 a b} 正则=\\s 替换为=_\n打印 [{r}]", x="c d e")
    check(out == "[c_d_e]", f"键=值 {{x 或 a b}}（有值）：{out}")

    print("三、原有写法不变")
    out = run("设 r = 替换 {x} ^\\s+|\\s+$ \n打印 [{r}]", x="  ab  ")
    check(out == "[ab]", f"替换 {{x}} 必填写法照常：{out}")
    out = run("设 r = 替换 {x} \\s _\n打印 [{r}]", x="你好 世界")
    check(out == "[你好_世界]", f"{{变量}} 值里有空格照常是一个参数：{out}")
    out = run("设 r = 替换 a-b-c - +\n打印 [{r}]")
    check(out == "[a+b+c]", f"没有花括号的字面量照常：{out}")
    out = run("设 r = 替换 a b c\n打印 [{r}]")
    check(out == "[a]", f"无花括号三参数照常按空白切（文本 a、正则 b、替换为 c）：{out}")
    out = run("设 r = 替换 aaab a{2} X\n打印 [{r}]")
    check(out == "[Xab]", f"正则量词 {{2}}（没有「或」）照常：{out}")
    out = run("设 r = 替换 a{x}b {{x}} Y\n打印 [{r}]")
    check(out == "[aYb]", f"{{{{字面}}}} 照常：{out}")
    out = run("设 r = 替换 x或y 或 Z\n打印 [{r}]")
    check(out == "[xZy]", f"花括号外的「或」照常是普通参数（正则那一格）：{out}")

    print("四、加载检查跟运行时一致")
    probs = LC.check_verb_calls(["设 r = 替换 {x 或 默 认} \\s _",
                                 "设 r = 替换 {x 或} ^\\s+|\\s+$"], REG, "x")
    check(not probs, f"{{x 或 默认}} 不报参数过多：{probs}")
    probs = LC.check_verb_calls(["设 r = 替换 a b c d"], REG, "")
    check(len(probs) == 1, f"真的多给参数照样报：{probs}")

    print("五、split_args")
    for s in ["a b  c", "  a\tb　c ", "{x} {y}", "{{a b}} c", "a{2, 3} b", '{"a": 1}', ""]:
        check(split_args(s) == s.split(), f"不带「或」的同 str.split：{s!r} → {split_args(s)}")
    check(split_args("替 {x 或} y") == ["替", "{x 或}", "y"], "{x 或} 整块")
    check(split_args("{x 或 默 认} y") == ["{x 或 默 认}", "y"], "{x 或 默认} 整块，默认里的空格不切")
    check(split_args("k={x　或} y") == ["k={x　或}", "y"], "全角空格的「或」也认，键=值 里也整块")
    check(split_args("前{x 或}后 z") == ["前{x 或}后", "z"], "夹在文字里也整块")
    check(split_args("{{x 或}} z") == ["{{x", "或}}", "z"], "{{x 或}} 是字面，照旧按空白切")
    check(split_args("{甲或乙} z") == ["{甲或乙}", "z"], "「或」两边没空白不算（同 split_alt）")

    print("----")
    if failed:
        print(f"通过 {passed}，失败 {failed}")
        sys.exit(1)
    print(f"通过 {passed}，失败 0")


if __name__ == "__main__":
    main()
