"""旧写法，请用 计算（设 x = 计算 四舍五入({分子} * 100 / {分母})）。百分比取整，例如 算比例 8 10 → 80"""


def 算比例(分子: str, 分母: str) -> str:
    try:
        a, b = float(分子), float(分母)
    except ValueError:
        return "[参数不是数字]"
    # 分母为零返回 0 而不是报错：正确率这类场景下「还没答过题」是常态，
    # 一道题没答就抛异常会让整个流程中断
    return "0" if b == 0 else str(round(a / b * 100))
