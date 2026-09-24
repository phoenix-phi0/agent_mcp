"""两数相加，支持负数和小数。例如 相加 3 1 → 4"""


def 相加(甲: str, 乙: str) -> str:
    try:
        s = float(甲) + float(乙)
    except ValueError:
        return "[参数不是数字]"
    # 整数结果不带小数点：3+1 要出 4 而不是 4.0，
    # 后者拿去跟别的数字比较或者拼进文本都难看
    return str(int(s)) if s == int(s) else str(s)
