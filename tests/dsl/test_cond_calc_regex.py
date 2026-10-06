# -*- coding: utf-8 -*-
"""组合条件、否则如果、计算、正则动词、花括号转义。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_cond_calc_regex.py

  一、条件：结构在原文上认——变量值里有「等于」「且」「(」都不影响；
      优先级 非 > 且 > 或、括号（半角全角、贴着写）、短路；报错带行号和原因；
      「重试 … 直到」省略左值照旧
  二、否则如果：多分支只跑第一个成立的，后面的条件不求值；「否则 如果」同义；
      「否则」后面跟别的字、「否则如果」写在「否则」后面都报错
  三、计算：各运算、函数、整数出整数、除零、变量值注入不进算式
  四、正则动词：匹配、找全部、按正则切分；正则写错直接抛
  五、花括号：量词原样、{{…}} 是字面、JSON 结尾的 }} 不受影响
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import packs                                # noqa: E402
from tools.dsl import DSLEngine, DSLError, invoke_verb  # noqa: E402
from tools.mock import MockClient                      # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


REG = packs.registry(["common", "text"], ROOT, cache=False)


def engine(**vars_) -> DSLEngine:
    e = DSLEngine(client=MockClient(offline=True), workdir=ROOT, verbose=False,
                  verbs=REG, verbs_root=packs.verbs_root())
    e.vars.update(vars_)
    return e


def run(script: str, **vars_) -> DSLEngine:
    e = engine(**vars_)
    e.run(script)
    return e


def out(script: str, **vars_) -> str:
    return "\n".join(run(script, **vars_).output)


def cond(cond_text: str, **vars_) -> str:
    """一行条件真假：真回 Y，假回 N。"""
    return out(f"如果 {cond_text}\n打印 Y\n否则\n打印 N\n结束", **vars_)


def error_of(script: str, **vars_) -> str:
    try:
        run(script, **vars_)
    except DSLError as e:
        return str(e)
    return ""


def v(name, *args):
    return invoke_verb(REG, name, *args, workdir=ROOT, verbs_root=packs.verbs_root())


def raises(fn) -> bool:
    try:
        fn()
    except (ValueError, DSLError):
        return True
    return False


def main() -> int:
    print("\n[一、条件：结构在原文上认]")
    check(cond("{a} 等于 对", a="对 等于 对") == "N",
          "值里有「等于」：{a}=「对 等于 对」不等于「对」（早先会切成 对 等于 对 等于 对）")
    check(cond("{a} 等于 对 等于 对", a="对") == "N" and cond("{a} 包含 等于", a="x 等于 y") == "Y",
          "右值原文里的运算符词留在右值里，值里的照样能比")
    check(cond("{a} 等于 {b}", a="", b="") == "Y",
          "两边都是空值：早先报「看不懂的条件」，现在能比")
    check(cond("{a} 不等于 {b}", a="", b="x") == "Y", "一边空值也能比")
    check(cond("{a} 包含 x", a="或 ( 非 且 ）") == "N" and cond("{a} 包含 {b}", a="或 ( 非 且 ）", b="非 且") == "Y",
          "值里有 且 / 或 / 非 / 括号：不影响结构")
    check(cond("{a} 包含 {b}", a="甲 或 乙", b="或 乙") == "Y", "值里的「或」当普通字比")
    check(cond("{a} 为空", a="") == "Y" and cond("{nope} 为空") == "Y" and cond("{a} 为空", a="0") == "N",
          "为空：空串、没定义的 {变量} 算空，0 不算")
    check(cond("{x 或} 为空") == "Y" and cond("{x 或 默认} 等于 默认") == "Y",
          "{x 或 默认}：花括号里的空格和「或」不切")
    check(cond("{n} 大于 9", n="10") == "Y" and cond("{s} 大于 b", s="a") == "N",
          "数值 / 字符串比较规则不变（10 > 9 按数值，a > b 按字符串）")
    check(cond("{a}等于1", a="1") == "Y", "紧贴写法照旧（不在 {…} 里面找运算符）")
    check(cond("{等于x} 为空") == "Y", "变量名里带运算符字样也不切进去")

    print("\n[一、条件：且 / 或 / 非 / 括号]")
    check(cond("{a} 等于 1 且 ( {b} 包含 x 或 非 {c} 为空 )", a="1", b="zz", c="有") == "Y",
          "例子：a=1 且 (b 包含 x 或 非 c 为空)，c 不空 → 真")
    check(cond("{a} 等于 1 且 ( {b} 包含 x 或 非 {c} 为空 )", a="1", b="zz", c="") == "N",
          "同上，b 不含 x、c 空 → 假")
    check(cond("1 等于 1 或 1 等于 2 且 1 等于 2") == "Y", "且 比 或 先结合：真 或 (假 且 假) = 真")
    check(cond("( 1 等于 1 或 1 等于 2 ) 且 1 等于 2") == "N", "括号改变优先级：(真 或 假) 且 假 = 假")
    check(cond("非 1 等于 2 且 1 等于 1") == "Y", "非 只管紧跟的那个比较：(非 假) 且 真")
    check(cond("非 ( 1 等于 1 且 1 等于 2 )") == "Y", "非 管括号")
    check(cond("非 非 1 等于 1") == "Y", "非 非")
    check(cond("（1 等于 2 或 2 等于 2）且 3 等于 3") == "Y", "全角括号，贴着写")
    check(cond("({a} 等于 1 或 {a} 等于 2)", a="2") == "Y", "半角括号贴着写")
    check(cond("( ( 1 等于 1 ) )") == "Y", "多层括号")
    check(cond("{n} 等于 1 或 {n} 等于 2 或 {n} 等于 3", n="3") == "Y", "一串或")

    # 短路：后半边是个看不懂的条件，只在真去求值时才报错
    check(cond("1 等于 1 或 甲 神秘运算 乙") == "Y", "或 短路：前面真，后面不求值")
    check(cond("1 等于 2 且 甲 神秘运算 乙") == "N", "且 短路：前面假，后面不求值")
    check("看不懂的条件" in error_of("如果 1 等于 2 或 甲 神秘运算 乙\n打印 x\n结束"),
          "对照：不短路时那半边照样报「看不懂的条件」")

    print("\n[一、条件：报错]")
    cases = [
        ("如果 ( {a} 等于 1\n结束", "括号不配对", "缺右括号"),
        ("如果 {a} 等于 1 )\n结束", "多了一个「)」", "多右括号"),
        ("如果 {a} 等于 1 且\n结束", "「且」后面缺比较", "且 后面空"),
        ("如果 且 {a} 等于 1\n结束", "「且」前面缺比较", "且 前面空"),
        ("如果 {a} 等于 1 或 且 {a} 等于 2\n结束", "「或」后面缺比较", "或 且 连着"),
        ("如果 非\n结束", "「非」后面缺比较", "非 后面空"),
        ("如果 ( )\n结束", "括号里是空的", "空括号"),
        ("如果 {a} 等于 (A)\n结束", "括号", "字面值带括号：报错，不静默比错"),
        ("如果 {a} 等于 非\n结束", "「非」只能写在", "非 写在中间"),
    ]
    for script, want, label in cases:
        err = error_of("打印 前一行\n" + script, a="1")
        check(want in err and "第 2 行" in err, f"{label}：{err}")
    check(cond("{a} 等于 {p}", a="(A)", p="(A)") == "Y", "字面值带括号的正确写法：先设进变量")

    print("\n[一、重试 … 直到：省略左值]")
    e = engine()
    e.client = MockClient(replies=["没有", "答案在这", "多余"], offline=True)
    e.run("问 r = 问题 重试 3 次 直到 包含 答案")
    check(e.vars["r"] == "答案在这", f"直到 包含 X：第二次满足就停（{e.vars['r']}）")
    e = engine()
    e.client = MockClient(replies=["甲", "甲乙", "甲乙丙"], offline=True)
    e.run("问 r = 问题 重试 3 次 直到 包含 乙 且 包含 丙")
    check(e.vars["r"] == "甲乙丙", f"直到 里也能组合（{e.vars['r']}）")
    e = engine(want="等于 是")
    e.client = MockClient(replies=["等于 是"], offline=True)
    e.run("问 r = 问题 重试 2 次 直到 包含 {want}")
    check(e.vars["r"] == "等于 是" and not any("仍不满足" in x for x in e.output),
          "直到 的右值是变量、值里有运算符词也不切")

    print("\n[二、否则如果]")
    script = ("如果 {a} 等于 1\n打印 一\n否则如果 {a} 等于 2\n打印 二\n"
              "否则 如果 {a} 等于 3\n打印 三\n否则若 {a} 等于 4\n打印 四\n否则\n打印 别的\n结束")
    got = [out(script, a=str(n)) for n in (1, 2, 3, 4, 5)]
    check(got == ["一", "二", "三", "四", "别的"], f"五个分支各走各的：{got}")
    check(out("如果 1 等于 1\n打印 A\n否则如果 1 等于 1\n打印 B\n结束") == "A", "只跑第一个成立的")
    check(out("如果 1 等于 1\n打印 A\n否则如果 甲 神秘运算 乙\n打印 B\n结束") == "A",
          "前面成立了，后面的条件不求值")
    check(out("如果 1 等于 2\n打印 A\n否则如果 2 等于 3\n打印 B\n结束") == "", "没有否则、都不成立：什么也不跑")
    check(out("如果 1 等于 2\n打印 A\n否则如果 {x} 等于 1 且 {y} 为空\n打印 B\n结束", x="1") == "B",
          "否则如果 的条件也能组合")
    nested = ("如果 {a} 等于 1\n 如果 {b} 等于 1\n  打印 11\n 否则如果 {b} 等于 2\n  打印 12\n 结束\n"
              "否则如果 {a} 等于 2\n 打印 2\n结束")
    check([out(nested, a="1", b="2"), out(nested, a="2", b="2")] == ["12", "2"],
          "嵌套：内层的否则如果不被外层认领")
    check(out("遍历 n 于 1,2,3\n 如果 {n} 等于 1\n  打印 一\n 否则如果 {n} 等于 2\n  打印 二\n"
              " 否则\n  打印 {n}\n 结束\n结束") == "一\n二\n3", "循环里的多分支")
    err = error_of("如果 1 等于 2\n打印 A\n否则\n打印 B\n否则如果 1 等于 1\n打印 C\n结束")
    check("第 5 行" in err and "要写在「否则」前面" in err, f"否则如果 写在否则后面：{err}")
    err = error_of("如果 1 等于 2\n打印 A\n否则 1 等于 1\n打印 B\n结束")
    check("第 3 行" in err and "否则如果" in err, f"「否则」后面跟了别的字：报错，不悄悄丢掉（{err}）")
    check(out("如果 1 等于 2\n打印 A\n否则  # 别的情况\n打印 B\n结束") == "B", "「否则」后面跟注释可以")
    err = error_of("否则如果 1 等于 1\n打印 x\n结束")
    check("没有对应的「如果」" in err, f"孤立的否则如果：{err}")
    err = error_of("如果 1 等于 2\n打印 A\n否则如果\n打印 B\n结束")
    check("第 3 行" in err and "要跟条件" in err, f"否则如果 后面没条件：{err}")
    err = error_of("遍历 n 于 1\n打印 x\n否则如果 1 等于 1\n打印 y\n结束")
    check("循环里" in err, f"循环里写否则如果：{err}")
    from tools.dsl_http import split_endpoints
    eps, _ = split_endpoints("接口 POST /x\n  如果 {a} 等于 1\n    返回 1\n  否则如果 {a} 等于 2\n"
                             "    返回 2\n  结束\n  返回 3\n结束\n", Path("t.zs"))
    check(len(eps) == 1 and len(eps[0].body) == 6, "路由文件切接口块时认否则如果（不当成新的一层）")

    print("\n[三、计算]")
    def calc(expr, **vars_):
        return run(f"设 r = 计算 {expr}", **vars_).vars["r"]
    table = [
        ("1 + 2 * 3", 7), ("(1 + 2) * 3", 9), ("（1 + 2）* 3", 9), ("10 - 2 - 3", 5),
        ("7 / 2", 3.5), ("6 / 2", 3), ("7 // 2", 3), ("-7 // 2", -4), ("7 % 3", 1),
        ("-7 % 3", 2), ("-3 + 5", 2), ("2 * -3", -6), ("- (2 + 3)", -5), ("1.5 * 2", 3),
        ("0.1 + 0.2", 0.3), ("取整(3.7)", 3), ("取整(-3.2)", -4), ("四舍五入(2.5)", 3),
        ("四舍五入(3.14159, 2)", 3.14), ("四舍五入(-2.5)", -3), ("四舍五入(1.005, 2)", 1.01),
        ("最大(1, 5, 3)", 5), ("最小(4，2)", 2), ("绝对值(-4.5)", 4.5), ("最大(1)", 1),
        ("1+2*3", 7), ("2 * (3 + 最大(1, 2))", 10),
    ]
    for expr, want in table:
        got = calc(expr)
        check(got == want and type(got) is type(want), f"{expr} = {got!r}")
    check(calc("{a} * 2 + 1", a="5") == 11, "例子：设 total = 计算 {a} * 2 + 1（a=5 → 11）")
    check(calc("{a} + {b}", a=2, b=1.5) == 3.5, "变量是 int / float 也行")
    check(calc("{a 或 0} + 1") == 1, "{a 或 0}：没定义用默认")
    check(calc("{a} - 1", a="-3") == -4, "值是负数")
    check(calc("{a}", a=" 12 ") == 12, "值两头的空白不算")
    check(out("计算 1 + 1") == "2", "不赋值就打印")
    check(out("设 msg = 计算完成") == "" and run("设 msg = 计算完成").vars["msg"] == "计算完成",
          "「计算完成」这种连着汉字的不算关键字")
    for expr, vars_, want, label in [
        ("1 / 0", {}, "除数是 0", "除零"),
        ("5 // {z}", {"z": "0"}, "除数是 0", "整除零（变量）"),
        ("5 % 0", {}, "除数是 0", "取余零"),
        ("{a} + 1", {"a": "1) * 0 + (9"}, "不是数字", "注入：值里有运算符和括号"),
        ("{a} * 2", {"a": "2+3"}, "不是数字", "注入：2+3 不当算式"),
        ("{a} + 1", {"a": "abc"}, "不是数字", "值不是数字"),
        ("{a} + 1", {"a": "nan"}, "不是数字", "nan 不收"),
        ("{a} + 1", {"a": "1e5"}, "不是数字", "科学计数法不收"),
        ("{a} + 1", {"a": [1]}, "不是数字", "列表不收"),
        ("{a} + 1", {"a": True}, "不是数字", "布尔不收"),
        ("{nope} + 1", {}, "没有定义", "变量没定义"),
        ("(1 + 2", {}, "括号不配对", "括号缺右"),
        ("1 + 2)", {}, "多了「)」", "括号多右"),
        ("1 +", {}, "不完整", "末尾缺数"),
        ("1 2", {}, "缺运算符", "两个数挨着"),
        ("2 ** 3", {}, "前面缺一个数", "不支持 **"),
        ("__import__('os')", {}, "看不懂", "不是 eval：名字不认"),
        ("四舍五入(1.5, 1.5)", {}, "小数位", "小数位不是整数"),
        ("绝对值(1, 2)", {}, "1 个参数", "参数个数不对"),
        ("取整 3", {}, "后面要跟括号", "函数没括号"),
        ("", {}, "要跟算式", "空算式"),
    ]:
        err = error_of(f"打印 x\n设 r = 计算 {expr}", **vars_)
        check(want in err and "第 2 行" in err, f"{label}：{err}")

    print("\n[四、正则动词]")
    m = v("匹配", "生于 2024年5月", r"(\d+)年(?P<mon>\d+)月")
    check(m == {"matched": "是", "all": "2024年5月", "groups": ["2024", "5"], "named": {"mon": "5"}},
          f"匹配：{m}")
    m = v("匹配", "没有数字", r"\d+")
    check(m == {"matched": "否", "all": "", "groups": [], "named": {}}, f"没匹配上：{m}")
    m = v("匹配", "ab", r"(x)?b")
    check(m["groups"] == [""] and m["all"] == "b", "没参与匹配的组是空串")
    check(raises(lambda: v("匹配", "x", "(")) and raises(lambda: v("匹配", "x", "")), "匹配：正则写错 / 没给 直接抛")
    check(v("找全部", "a1b22c333", r"\d+") == ["1", "22", "333"], "找全部：没分组是匹配串")
    check(v("找全部", "a1 b2", r"([a-z])(\d)") == [["a1", "a", "1"], ["b2", "b", "2"]],
          "找全部：有分组是 [整个, 第1组, …]")
    check(v("找全部", "xyz", r"\d") == [], "找全部：没有是空列表")
    check(raises(lambda: v("找全部", "x", "[")), "找全部：正则写错直接抛")
    check(v("按正则切分", "a, b，c", r"[,，]\s*") == ["a", "b", "c"], "按正则切分")
    check(v("按正则切分", "a1b2c", r"(\d)") == ["a", "b", "c"], "按正则切分：分组不夹进结果")
    check(v("按正则切分", ",a,,b", ",") == ["", "a", "", "b"], "按正则切分：空段照留（同 re.split）")
    check(v("按正则切分", "abc", ",") == ["abc"], "按正则切分：没匹配是一项")
    check(raises(lambda: v("按正则切分", "x", "(")), "按正则切分：正则写错直接抛")
    e = run("设 m = 匹配 {t} (\\d{4})-(\\d{2,3})\n如果 {m.matched} 等于 是\n打印 {m.groups.0}/{m.groups.1}\n结束\n"
            "设 all = 找全部 {t} \\d+\n遍历 x 于 {all}\n打印 {x}\n结束", t="电话 2024-123 转 9")
    check(e.output == ["2024/123", "2024", "123", "9"], f"在脚本里用：量词 {{4}} {{2,3}} 原样，结果能遍历（{e.output}）")

    print("\n[五、花括号]")
    e = engine(n="3", t="见 {name} 和 x")
    check(e.expand(r"\d{4} {2,3} {nope}") == r"\d{4} {2,3} {nope}", "没定义的 {…} 原样保留（量词不受影响）")
    check(e.expand(r"\d{n}") == r"\d3", "对照：花括号里恰好是变量名就被展开了")
    check(e.expand(r"\d{{n}} {{name}} {{}}") == r"\d{n} {name} {}", "{{…}} 是字面的 {…}")
    check(e.expand('{"a":{"b":{n}}}') == '{"a":{"b":3}}', "JSON 结尾的 }} 不受影响")
    check(e.expand("{{n}}{n}") == "{n}3", "转义和变量挨着")
    e = run("设 name = 小明\n设 r = 替换 {t} {{name}} X", t="见 {name} 和 x")
    check(e.vars["r"] == "见 X 和 x", f"{{{{name}}}} 传给正则就是 {{name}}（{e.vars['r']}）")
    check(cond("{t} 包含 {{name}}", t="见 {name}", name="小明") == "Y", "条件里也能用 {{…}}")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
