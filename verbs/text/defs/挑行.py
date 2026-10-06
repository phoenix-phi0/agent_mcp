"""把文本按行分成两拨：匹配正则的行、其余的行。返回 {hits, rest}。例如 设 parts = 挑行 {题干} ^([A-D])\\.\\s*(.*)$

hits  匹配上的行，按出现顺序，每行是一个列表：[整行匹配, 第1组, 第2组, …]
      （没有的组是空串），脚本里 {h.1} {h.2} 取
rest  没匹配上的行，用换行连起来（原样，不去首尾空白）

按行用 str.splitlines 切（\\r\\n、\\r 都算换行），每行用 re.match（从行首匹配）。

为什么要这样一个动词：DSL 里没法往列表里加字符串、也写不出换行，「把选项行
挑出来、剩下的拼回题面」这件事拆成单步写不出来。
"""

import re


def 挑行(文本: str = "", 正则: str = "") -> dict:
    if not 正则:
        raise ValueError("挑行：没给正则")
    try:
        pat = re.compile(正则)
    except re.error as e:
        raise ValueError(f"挑行：正则写错了（{e}）：{正则}")
    hits, rest = [], []
    for line in str(文本 or "").splitlines():
        m = pat.match(line)
        if m:
            hits.append([m.group(0)] + [g if g is not None else "" for g in m.groups()])
        else:
            rest.append(line)
    return {"hits": hits, "rest": "\n".join(rest)}
