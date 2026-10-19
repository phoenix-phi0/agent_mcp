# -*- coding: utf-8 -*-
"""条件符号运算符、当前时间、相加 / 算比例收口。

    .venv/bin/python tests/dsl/test_cond_symbols_time.py

  一、符号运算符：> < >= <= == != 与全角 ＞ ＜ ≥ ≤ ＝＝ ≠ 同中文语义（数值 / 文本比较）；
      与 且 / 或 / 非 / 括号组合；变量值含符号不影响；单个 = 报错
  二、当前时间：默认 / 日期 / 时间戳、DSL_NOW、mock 模式、非法格式
  三、相加 / 算比例：旧写法仍可用（kg 在用），但不再列进能力清单
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import packs                                # noqa: E402
from tools.dsl import DSLEngine, DSLError, invoke_verb  # noqa: E402
from tools.mock import MockClient                      # noqa: E402
from tools.dslagent import loadcheck as LC             # noqa: E402
from tools.dslagent import modbuild as MB              # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


REG = packs.registry(["common", "text"], ROOT, cache=False)


def run(script, **vars_):
    e = DSLEngine(client=MockClient(offline=True), workdir=ROOT, verbose=False,
                  verbs=REG, verbs_root=packs.verbs_root())
    e.vars.update(vars_)
    e.run(script)
    return e


def cond(text, **vars_):
    return "\n".join(run(f"如果 {text}\n打印 Y\n否则\n打印 N\n结束", **vars_).output)


def error_of(script, **vars_):
    try:
        run(script, **vars_)
    except DSLError as e:
        return str(e)
    return ""


def verb(name, *args):
    return invoke_verb(REG, name, *args, workdir=ROOT, verbs_root=packs.verbs_root())


def main():
    print("\n[一、符号运算符]")
    table = [  # (符号, 中文, 真的一组, 假的一组)
        (">", "大于", ("5", "3"), ("3", "5")), ("<", "小于", ("3", "5"), ("5", "3")),
        (">=", "不小于", ("5", "5"), ("3", "5")), ("<=", "不大于", ("5", "5"), ("5", "3")),
        ("==", "等于", ("5", "5"), ("5", "3")), ("!=", "不等于", ("5", "3"), ("5", "5")),
        ("＞", "大于", ("5", "3"), ("3", "5")), ("＜", "小于", ("3", "5"), ("5", "3")),
        ("≥", "不小于", ("5", "5"), ("3", "5")), ("≤", "不大于", ("5", "5"), ("5", "3")),
        ("＝＝", "等于", ("5", "5"), ("5", "3")), ("≠", "不等于", ("5", "3"), ("5", "5")),
    ]
    for sym, zh, yes, no in table:
        check(cond(f"{{a}} {sym} {{b}}", a=yes[0], b=yes[1]) == "Y"
              and cond(f"{{a}} {sym} {{b}}", a=no[0], b=no[1]) == "N", f"{sym} 同 {zh}（真 / 假各一组）")
    check(cond("{a}>=5", a="5") == "Y" and cond("{a}!=5", a="5") == "N" and cond("{a}<10", a="9") == "Y",
          "紧贴写法 {a}>=5 / {a}!=5 / {a}<10")
    check(cond("{a} > {b}", a="10", b="9") == "Y" and cond("{a} > {b}", a="a", b="b") == "N"
          and cond("{a} < {b}", a="10", b="9") == "N",
          "数值比较（10 > 9）与文本比较（a > b）规则同中文")
    check(cond("{a} == {b}", a=" 1 ", b="1") == "Y" and cond("{a} 等于 {b}", a=" 1 ", b="1") == "Y", "== 同 等于：两边去空白")
    check(cond("{a} > 1 且 {a} < 10", a="5") == "Y" and cond("{a} > 1 且 {a} < 10", a="50") == "N", "与 且 组合")
    check(cond("{a} < 1 或 {a} >= 10", a="50") == "Y" and cond("{a} < 1 或 {a} >= 10", a="5") == "N", "与 或 组合")
    check(cond("非 {a} == 1", a="2") == "Y" and cond("非 {a} == 1", a="1") == "N", "与 非 组合")
    check(cond("({a} == 1 或 {a} == 2) 且 {b} != 0", a="2", b="1") == "Y"
          and cond("（{a} ＝＝ 1 或 {a} ＝＝ 2）且 {b} ≠ 0", a="2", b="0") == "N", "与括号组合（半角 / 全角）")
    check(cond("{a} == 1", a="1 == 2") == "N" and cond("{a} == {b}", a="x > y", b="x > y") == "Y"
          and cond("{a} 包含 >", a="a > b") == "Y",
          "变量值里含 > == 不影响结构")
    check(cond("{a} == a>b", a="a>b") == "Y" and cond("{a} == a>b", a="a") == "N",
          "{…} 外的字面值含符号：整词运算符先到先得（== 之后的 a>b 是右值），同中文")
    check(cond("{a} 等于 a>b", a="a>b") == "Y", "对照：中文运算符同样处理")
    msg = error_of("如果 {a} = 1\n打印 x\n结束", a="1")
    check("比较用 等于 或 ==" in msg and "看不懂的条件" in msg, f"单个 = 报错并提示：{msg[:60]}")
    check("比较用 等于 或 ==" in error_of("如果 {a}=1\n打印 x\n结束", a="1"), "紧贴的 {a}=1 同样报错")
    check("比较用" not in error_of("如果 {a} 神秘 b\n打印 x\n结束", a="1"), "别的看不懂的条件不带这条提示")
    check(cond("{a} 等于 x=1", a="x=1") == "Y", "已有运算符时右值里的 = 不报错")
    check(LC.parse_script("如果 {a} == 1 且 {b} ≥ 2\n打印 x\n结束\n") is None, "loadcheck：符号不判成看不懂的条件")
    e = LC.parse_script("如果 {a} = 1\n打印 x\n结束\n")
    check(e is not None and "比较用 等于 或 ==" in e, "loadcheck：单个 = 报错带提示")

    print("\n[二、当前时间]")
    saved = os.environ.pop("DSL_NOW", None)
    try:
        import re
        now = verb("当前时间")
        check(re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", str(now)) is not None, f"默认格式 YYYY-MM-DD HH:MM:SS（{now}）")
        check(re.fullmatch(r"\d{4}-\d\d-\d\d", str(verb("当前时间", "日期"))) is not None, "日期")
        ts = str(verb("当前时间", "时间戳"))
        check(ts.isdigit() and abs(int(ts) - __import__("time").time()) < 5, f"时间戳是整数秒（{ts}）")
        os.environ["DSL_NOW"] = "2026-10-19 12:00:00"
        check(verb("当前时间") == "2026-10-19 12:00:00" and verb("当前时间", "日期") == "2026-10-19", "DSL_NOW 固定默认 / 日期")
        from datetime import datetime
        check(verb("当前时间", "时间戳") == str(int(datetime(2026, 10, 19, 12).timestamp())), "DSL_NOW 固定时间戳")
        check("\n".join(run("设 t = 当前时间 日期\n打印 {t}").output) == "2026-10-19", "脚本里 设 t = 当前时间 日期")
        check(run("设 t = 当前时间\n打印 {t}").output == ["2026-10-19 12:00:00"], "MockClient（离线 mock 引擎）下 DSL_NOW 同样生效")
        os.environ["DSL_NOW"] = "2026-10-19"
        check(verb("当前时间") == "2026-10-19 00:00:00", "DSL_NOW 只给日期 → 00:00:00")
        os.environ["DSL_NOW"] = "乱写"
        try:
            verb("当前时间")
            check(False, "DSL_NOW 格式错应报错")
        except (ValueError, DSLError):
            check(True, "DSL_NOW 格式错 → 报错")
        os.environ["DSL_NOW"] = "2026-10-19 12:00:00"
        try:
            verb("当前时间", "星期")
            check(False, "不认识的格式应报错")
        except (ValueError, DSLError):
            check(True, "不认识的格式 → 报错")
    finally:
        os.environ.pop("DSL_NOW", None)
        if saved is not None:
            os.environ["DSL_NOW"] = saved

    print("\n[三、相加 / 算比例收口]")
    check(verb("相加", "3", "1") == "4" and verb("算比例", "8", "10") == "80", "旧动词仍可调（kg 在用）")
    caps = MB.capabilities()
    names = {v["名"] for vs in caps.values() for v in vs}
    check("相加" not in names and "算比例" not in names, "能力清单不再列 相加 / 算比例")
    check("当前时间" in names, "能力清单列了 当前时间")
    check("\n".join(run("设 r = 计算 四舍五入(8 * 100 / 10)\n打印 {r}").output) == "80", "计算 四舍五入(分子 * 100 / 分母) 等价算比例")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
