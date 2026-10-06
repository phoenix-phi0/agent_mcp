# -*- coding: utf-8 -*-
"""「计算」：四则运算的小解析器。不用 eval。

    设 total = 计算 {a} * 2 + 1
    设 avg = 计算 四舍五入({sum} / {n}, 2)
    计算 最大({a}, {b}, 0)              不赋值就打印出来

运算：+ - * / // %、括号（半角全角都行）、负号、小数。函数：取整（向下）、
四舍五入（可带小数位，逢五进一，不是 Python round 的「银行家舍入」）、
最大、最小、绝对值；参数用逗号（半角全角）隔开。结果是整数就出整数（3，
不是 3.0）。

为什么是引擎关键字而不是 common 包里的动词：动词参数按空格切，「计算 {a}
* 2 + 1」会被切成五个参数；而且动词拿到的是展开过的文本，{a} 的值已经拼进
算式里了。值来自用户输入时（作答、表单里的数量），拼进去就能改写算式——
「1) * 0 + (9」。所以 {变量} 要在原文里认：每个 {变量} 取到的值只能当
**一个数**，转不了数字就报错，从来不拿值去重新解析。

内部用 Decimal 算：0.1 + 0.2 出 0.3，不出 0.30000000000000004。交出去的
时候转回 int / float。
"""

import re
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP, localcontext

from .dsl_core import BRACE_RE, DSLError, to_text

# 一个数：整数或小数，可带正负号（只在变量的值里认符号；表达式里的负号
# 是一元运算）。不认 nan / inf / 1e5——值是用户给的，越宽越容易出怪事。
NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")
LITERAL_RE = re.compile(r"\d+(?:\.\d*)?|\.\d+")

FUNCS = {"取整": (1, 1), "四舍五入": (1, 2), "最大": (1, None),
         "最小": (1, None), "绝对值": (1, 1)}
FUNCS_BY_LEN = sorted(FUNCS, key=len, reverse=True)
OPS = ("//", "+", "-", "*", "/", "%")
PUNCT = {"(": "(", "（": "(", ")": ")", "）": ")", ",": ",", "，": ","}

# 防止「999999999 位小数」或者巨大的数把进程拖住
MAX_DIGITS = 28
MAX_ROUND_PLACES = 20
MAX_MAGNITUDE = Decimal(10) ** 30


def _num(text: str, what: str) -> Decimal:
    s = text.strip()
    if not NUMBER_RE.fullmatch(s):
        raise DSLError(f"计算：{what}不是数字：「{s}」")
    return Decimal(s)


def format_number(d: Decimal):
    """Decimal → int（整数时）或 float。"""
    if d == d.to_integral_value():
        return int(d)
    return float(d)


def _tokens(expr: str, value_of):
    """→ [(类别, 值)]。类别：num / op / ( / ) / , / fn。{变量} 在这一步
    就换成数，后面的解析看不到值的原文。"""
    out, i = [], 0
    while i < len(expr):
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "{":
            m = BRACE_RE.match(expr, i)
            if not m or m.group(0).startswith("{{"):
                raise DSLError(f"计算：看不懂的花括号「{expr[i:i + 12]}」")
            tok = m.group(0)
            got = value_of(tok)
            if got is None:
                raise DSLError(f"计算：变量 {tok} 没有定义")
            if isinstance(got, bool) or not isinstance(got, (str, int, float)):
                raise DSLError(f"计算：{tok} 的值不是数字：「{to_text(got)[:40]}」")
            out.append(("num", _num(to_text(got), f"{tok} 的值")))
            i = m.end()
            continue
        m = LITERAL_RE.match(expr, i)
        if m:
            out.append(("num", Decimal(m.group(0))))
            i = m.end()
            continue
        op = next((o for o in OPS if expr.startswith(o, i)), None)
        if op:
            out.append(("op", op))
            i += len(op)
            continue
        if ch in PUNCT:
            out.append((PUNCT[ch], ch))
            i += 1
            continue
        fn = next((f for f in FUNCS_BY_LEN if expr.startswith(f, i)), None)
        if fn:
            out.append(("fn", fn))
            i += len(fn)
            continue
        raise DSLError(f"计算：看不懂「{expr[i:i + 12]}」。能用 + - * / // % 、括号、"
                       f"{'、'.join(FUNCS)}，变量写 {{x}}")
    return out


def calculate(expr: str, value_of):
    """算表达式原文。value_of(「{x}」) 返回变量的原始值（None = 没定义）。"""
    if not expr.strip():
        raise DSLError("计算：后面要跟算式")
    toks = _tokens(expr, value_of)
    pos = 0

    def peek(k=0):
        return toks[pos + k] if pos + k < len(toks) else (None, None)

    def take(kind, what):
        nonlocal pos
        if peek()[0] != kind:
            got = peek()[1]
            raise DSLError(f"计算：{what}" + (f"，这里是「{got}」" if got is not None else "，算式就结束了"))
        pos += 1
        return toks[pos - 1]

    def check(d: Decimal) -> Decimal:
        if not d.is_finite() or abs(d) > MAX_MAGNITUDE:
            raise DSLError(f"计算：结果太大了（{expr.strip()}）")
        return d

    def p_expr():
        nonlocal pos
        val = p_term()
        while peek() in (("op", "+"), ("op", "-")):
            op = toks[pos][1]
            pos += 1
            rhs = p_term()
            val = check(val + rhs if op == "+" else val - rhs)
        return val

    def p_term():
        nonlocal pos
        val = p_unary()
        while peek()[0] == "op" and peek()[1] in ("*", "/", "//", "%"):
            op = toks[pos][1]
            pos += 1
            rhs = p_unary()
            if op == "*":
                val = check(val * rhs)
                continue
            if rhs == 0:
                raise DSLError(f"计算：除数是 0（{expr.strip()}）")
            if op == "/":
                val = check(val / rhs)
            elif op == "//":
                val = (val / rhs).to_integral_value(rounding=ROUND_FLOOR)
            else:
                # 跟 Python 一样，余数的符号跟除数走：-7 % 3 = 2
                val = val - rhs * (val / rhs).to_integral_value(rounding=ROUND_FLOOR)
        return val

    def p_unary():
        nonlocal pos
        if peek() in (("op", "-"), ("op", "+")):
            neg = toks[pos][1] == "-"
            pos += 1
            v = p_unary()
            return -v if neg else v
        return p_atom()

    def p_atom():
        nonlocal pos
        kind, val = peek()
        if kind == "num":
            pos += 1
            return val
        if kind == "(":
            pos += 1
            v = p_expr()
            take(")", "括号不配对，少了「)」")
            return v
        if kind == "fn":
            pos += 1
            take("(", f"「{val}」后面要跟括号：{val}(…)")
            args = [p_expr()]
            while peek()[0] == ",":
                pos += 1
                args.append(p_expr())
            take(")", f"「{val}」的括号没有收尾")
            return call(val, args)
        if kind is None:
            raise DSLError("计算：算式不完整，末尾缺一个数")
        raise DSLError(f"计算：「{val}」前面缺一个数")

    def call(fn, args):
        lo, hi = FUNCS[fn]
        if len(args) < lo or (hi is not None and len(args) > hi):
            want = f"{lo}" if lo == hi else (f"{lo} 到 {hi}" if hi else f"至少 {lo}")
            raise DSLError(f"计算：「{fn}」要 {want} 个参数，给了 {len(args)} 个")
        if fn == "取整":
            return args[0].to_integral_value(rounding=ROUND_FLOOR)
        if fn == "绝对值":
            return abs(args[0])
        if fn == "最大":
            return max(args)
        if fn == "最小":
            return min(args)
        places = args[1] if len(args) > 1 else Decimal(0)
        if places != places.to_integral_value() or not 0 <= places <= MAX_ROUND_PLACES:
            raise DSLError(f"计算：四舍五入的小数位要是 0 到 {MAX_ROUND_PLACES} 的整数，"
                           f"给的是 {format_number(places)}")
        return args[0].quantize(Decimal(1).scaleb(-int(places)), rounding=ROUND_HALF_UP)

    with localcontext() as ctx:
        ctx.prec = MAX_DIGITS
        try:
            result = p_expr()
        except InvalidOperation as e:
            raise DSLError(f"计算：算不了（{expr.strip()}）") from e
    if pos < len(toks):
        kind, val = toks[pos]
        if kind == ")":
            raise DSLError("计算：括号不配对，多了「)」")
        raise DSLError(f"计算：「{val}」前面缺运算符")
    return format_number(result)
