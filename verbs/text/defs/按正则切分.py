"""按正则把文本切成几段，返回列表。例如 设 parts = 按正则切分 {作答} [,，、\\s]+

跟 re.split 一样切，只有一处不同：正则里有分组时，re.split 会把分组匹配
到的分隔符也夹进结果里（"a1b" 按 (\\d) 切成 ["a", "1", "b"]），这里不夹——
结果只有被切开的那几段（["a", "b"]），有没有分组都一样。

空段照留：开头、结尾就是分隔符，或者两个分隔符挨着，会切出空串
（",a,,b" 按 , 切是 ["", "a", "", "b"]），要去掉就把正则写成 [,]+ 并先
去首尾。没有匹配时是只有一项（整段文本）的列表。正则写错了直接抛。
"""

import re


def 按正则切分(文本: str = "", 正则: str = "") -> list:
    if not 正则:
        raise ValueError("按正则切分：没给正则")
    try:
        pat = re.compile(正则)
    except re.error as e:
        raise ValueError(f"按正则切分：正则写错了（{e}）：{正则}")
    text = str(文本 or "")
    out, last = [], 0
    for m in pat.finditer(text):
        out.append(text[last:m.start()])
        last = m.end()
    out.append(text[last:])
    return out
