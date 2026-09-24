"""统计逗号分隔列表里有多少项。例如 列表长度 甲,乙,丙 → 3"""

import re


def 列表长度(列表: str) -> str:
    # 半角和全角逗号都算分隔符——脚本里中文写法居多，
    # 只认半角的话「甲，乙，丙」会被数成 1 项
    return str(len([x for x in re.split(r"[,，]", 列表) if x.strip()]))
