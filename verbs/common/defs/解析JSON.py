"""把一段文字解析成 JSON 结构，解析不了就给空字典，不报错。例如
设 判 = 解析JSON {原文}

跟「问JSON」的分工：问JSON 解析失败直接报错（接口回 500），适合「坏了就该
停」的场合；模型的回复坏了也要接着走（按默认处理）的场合，先「问」拿原文，
再用这个解析，取字段时用 {判.intent 或} 兜底。

模型常在 JSON 外面包代码围栏或加一句「结果如下」，先抠出 {…} 再解析。
解析出来是数字、字符串这类不是结构的，也当解析不了。
"""

import json

from tools.zhipu import strip_json


def 解析JSON(内容: str = ""):
    if isinstance(内容, (dict, list)):
        return 内容
    try:
        v = json.loads(strip_json(str(内容 or "")))
    except (json.JSONDecodeError, ValueError):
        return {}
    return v if isinstance(v, (dict, list)) else {}
