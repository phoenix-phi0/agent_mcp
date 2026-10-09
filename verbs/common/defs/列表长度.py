"""统计列表里有多少项。例如 列表长度 甲,乙,丙 → 3；列表长度 {hits}（列表变量）→ 项数

列表变量传给动词时是 JSON 数组文本，按数组算（[] 是 0）；别的按逗号分隔数。
"""

import json
import re


def 列表长度(列表: str) -> str:
    s = str(列表).strip()
    # 列表变量到这里是 JSON 文本：按逗号数会把项里的逗号也算上，[] 还会数成 1
    if s.startswith("["):
        try:
            v = json.loads(s)
        except json.JSONDecodeError:
            v = None
        if isinstance(v, list):
            return str(len(v))
    # 半角和全角逗号都算分隔符——脚本里中文写法居多，
    # 只认半角的话「甲，乙，丙」会被数成 1 项
    return str(len([x for x in re.split(r"[,，]", s) if x.strip()]))
