"""K190：变量的值恰好形如 {name} 时，判空和后续处理都按字面的值走。

早先判空只看展开后的形状（整个是 {…} 就算没展开），搜 {name} 被判成空、筛选被静默跳过。
真的取不到值（未定义、未定义再传一手）仍算空，这是对照，少了它「不为空」的断言可能白过。
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.dsl import DSLEngine  # noqa: E402
from tools.dsl_core import Unexpanded, is_empty  # noqa: E402

fails = []
total = 0


def check(name, got, want):
    global total
    total += 1
    if got == want:
        print(f"  ok  {name}")
    else:
        fails.append(name)
        print(f"  错  {name}: 实际 {got!r}，应为 {want!r}")


def run(script, **params):
    e = DSLEngine(verbose=False)
    e.vars.update(params)
    return e.run(script)


IF = "如果 {x} 不为空\n打印 有\n否则\n打印 无\n结束"
for v in ("{name}", "{student}", "{x}", "{a.b}", "{ name }", " {name} ", "{1}", "{中文}"):
    check(f"值 {v!r} 不为空", run(IF, x=v), "有")
    check(f"值 {v!r} 为空 不成立", run("如果 {x} 为空\n打印 空\n否则\n打印 非空\n结束", x=v), "非空")

# 对照：真的没值
check("未定义 为空", run(IF), "无")
check("未定义路径 为空", run("如果 {a.b} 不为空\n打印 有\n否则\n打印 无\n结束"), "无")
for v in ("", "  ", "[]", "{}", [], {}):
    check(f"值 {v!r} 为空", run(IF, x=v), "无")
check("有普通值", run(IF, x="abc"), "有")
check("{x 或} 取不到", run("如果 {x 或} 不为空\n打印 有\n否则\n打印 无\n结束"), "无")
check("{x 或} 取到花括号值", run("如果 {x 或} 不为空\n打印 有\n否则\n打印 无\n结束", x="{name}"), "有")
check("一层 JSON 对象不算没展开", run(IF, x='{"id":1}'), "有")

# 记号沿赋值、字典、函数参数往下传
check("设 a = {没定义} 后判空仍空", run("设 a = {没定义}\n如果 {a} 为空\n打印 空\n否则\n打印 非空\n结束"), "空")
check("连传两手仍空", run("设 a = {没定义}\n设 b = {a}\n如果 {b} 为空\n打印 空\n否则\n打印 非空\n结束"), "空")
check("{a 或} 接没展开的仍空", run("设 a = {没定义}\n如果 {a 或} 为空\n打印 空\n否则\n打印 非空\n结束"), "空")
check("进字典字段仍空", run("设 o.k = {没定义}\n如果 {o.k} 为空\n打印 空\n否则\n打印 非空\n结束"), "空")
check("设 a = {x} 带花括号值不空", run("设 a = {x}\n如果 {a} 为空\n打印 空\n否则\n打印 非空\n结束", x="{name}"), "非空")
check("进字典的花括号值不空", run("设 o.k = {x}\n如果 {o.k} 为空\n打印 空\n否则\n打印 非空\n结束", x="{name}"), "非空")
check("拼出来的花括号值不空", run("设 a = {{name}}\n如果 {a} 为空\n打印 空\n否则\n打印 非空\n结束"), "非空")

# 组合条件、循环条件走同一条路
check("且 组合", run("如果 {x} 不为空 且 {y} 不为空\n打印 有\n否则\n打印 无\n结束", x="{name}", y="{student}"), "有")
check("非 组合", run("如果 非 {x} 为空\n打印 有\n否则\n打印 无\n结束", x="{name}"), "有")
check("当 循环", run("设 n = 0\n当 {x} 不为空 且 {n} 小于 2 最多 5 次\n设 n = 计算 {n} + 1\n结束\n打印 {n}", x="{name}"), "2")

# 替换只扫一遍：值里的 {name} 不再解析成变量 name 的值
check("值不被二次展开", run("打印 {x}", x="{secret}", secret="不该出现"), "{secret}")
check("拼接时值不被二次展开", run("打印 前{x}后", x="{secret}", secret="不该出现"), "前{secret}后")
check("设 后不被二次展开", run("设 a = {x}\n打印 {a}", x="{secret}", secret="不该出现"), "{secret}")
check("字典字段不被二次展开", run("设 o.k = {x}\n打印 {o.k}", x="{secret}", secret="不该出现"), "{secret}")
check("等于 比较按字面", run("如果 {x} 等于 {{name}}\n打印 同\n否则\n打印 异\n结束", x="{name}", name="别的"), "同")

# 没定义的文字输出不变：拼写错了要看得见
check("未定义原样留着", run("打印 {项.标提}"), "{项.标提}")

# 记号只在整个结果是一个没展开的 {名} 时打
e = DSLEngine(verbose=False)
check("expand 未定义打记号", isinstance(e.expand("{nope}"), Unexpanded), True)
check("expand 拼接不打记号", isinstance(e.expand("a{nope}"), Unexpanded), False)
e.vars["x"] = "{name}"
check("expand 有值不打记号", isinstance(e.expand("{x}"), Unexpanded), False)
check("is_empty 记号", is_empty(Unexpanded("{a}")), True)
check("is_empty 普通 {a}", is_empty("{a}"), False)

# 记号是 str 子类，进 SQL、进 JSON 和普通字符串一样
c = sqlite3.connect(":memory:")
check("sqlite 绑定", c.execute("select ?", (Unexpanded("{a}"),)).fetchone()[0], "{a}")

# 业务函数：搜 {name}、{student} 走到函数里仍有值；不传的可选参数仍是空
with tempfile.TemporaryDirectory() as td:
    Path(td, "services").mkdir()
    Path(td, "services", "m.zs").write_text(
        "业务 m\n"
        "  公开 函数 f keyword?\n"
        "    如果 {keyword} 不为空\n"
        "      返回 有:{keyword}\n"
        "    结束\n"
        "    返回 无\n"
        "  结束\n"
        "  公开 函数 g keyword\n"
        "    设 r = 调用 f keyword={keyword}\n"
        "    返回 {r}\n"
        "  结束\n"
        "结束\n", encoding="utf-8")
    def svc(script, **params):
        e = DSLEngine(verbose=False, workdir=td)
        e.vars.update(params)
        return e.run(script)

    check("函数 传 {name}", svc("设 r = 调用 m.f keyword={x}\n打印 {r}", x="{name}"), "有:{name}")
    check("函数 传 {student} 再传一层", svc("设 r = 调用 m.g keyword={x}\n打印 {r}", x="{student}"), "有:{student}")
    check("函数 不传可选参数", svc("设 r = 调用 m.f\n打印 {r}"), "无")
    check("函数 传未定义变量", svc("设 r = 调用 m.f keyword={没定义}\n打印 {r}"), "无")

print(f"{total - len(fails)}/{total}")
sys.exit(1 if fails else 0)
