"""在列表末尾加一项，返回新列表（原列表不动）。例如 设 options = 列表加项 {options} {opt}

列表收 JSON 数组文本或真列表，空当空列表（开头写 设 options = 解析JSON [] 也行）。
项是 JSON 对象或数组的文本（{…} / […]，DSL 里结构传给动词就是这样）就按结构
加进去，否则当文本加。

为什么要有：DSL 的「设 x.0 = …」只能改已有的下标，不会往列表后面加，
拼一个对象列表（题卡上的选项）没有别的写法。
"""

import json

from tools.verbs import as_list


def 列表加项(列表="", 项="") -> list:
    items = as_list(列表)
    item = 项
    if isinstance(项, str) and 项.strip().startswith(("{", "[")):
        try:
            v = json.loads(项)
            if isinstance(v, (dict, list)):
                item = v
        except json.JSONDecodeError:
            pass
    items.append(item)
    return items
