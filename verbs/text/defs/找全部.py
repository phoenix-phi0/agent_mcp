"""按正则找出所有匹配，返回列表。例如 设 nums = 找全部 {题干} \\d+

正则里没有分组：每项是匹配到的那段文本，["12", "345"]
有分组：每项是 [整个匹配, 第1组, 第2组, …]（没参与匹配的组是空串），
跟「挑行」的 hits 一样，遍历时 {h.1} 取第一组

用 re.finditer，从左到右不重叠。没有匹配是空列表。正则写错了直接抛。
"""

import re


def 找全部(文本: str = "", 正则: str = "") -> list:
    if not 正则:
        raise ValueError("找全部：没给正则")
    try:
        pat = re.compile(正则)
    except re.error as e:
        raise ValueError(f"找全部：正则写错了（{e}）：{正则}")
    text = str(文本 or "")
    if not pat.groups:
        return [m.group(0) for m in pat.finditer(text)]
    return [[m.group(0)] + [g if g is not None else "" for g in m.groups()]
            for m in pat.finditer(text)]
