"""按正则找第一处匹配，返回 {matched, all, groups, named}。例如 设 m = 匹配 {作答} (\\d+)年(\\d+)月

matched  是 / 否（配「如果 {m.matched} 等于 是」）
all      整个匹配；没匹配上是空串
groups   [第1组, 第2组, …]，没参与匹配的组是空串，脚本里 {m.groups.0} 取第一组
named    命名组 (?P<名字>…) 的 {名字: 值}

用 re.search：在文本里任何位置找，不要求从开头匹配（要从开头就写 ^）。
没匹配上时 matched 是「否」，all 是空串，groups、named 是空的。

正则的写法同「替换」：参数按空格切，正则里要空格写 \\s；花括号量词
\\d{4} 原样能用，字面的 {变量名} 写 {{变量名}}。正则写错了直接抛。
"""

import re


def 匹配(文本: str = "", 正则: str = "") -> dict:
    if not 正则:
        raise ValueError("匹配：没给正则")
    try:
        m = re.search(正则, str(文本 or ""))
    except re.error as e:
        raise ValueError(f"匹配：正则写错了（{e}）：{正则}")
    if not m:
        return {"matched": "否", "all": "", "groups": [], "named": {}}
    return {"matched": "是", "all": m.group(0),
            "groups": [g if g is not None else "" for g in m.groups()],
            "named": {k: (v if v is not None else "") for k, v in m.groupdict().items()}}
