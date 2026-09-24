"""从 JSON 文本里取字段，路径用点号分隔。例如 取字段 {进度} hiragana.current_day

引擎本身已经支持 {变量.路径} 直接取值，这个动词是给「JSON 存在字符串里」
的场合用的——比如动词返回的 JSON 文本、或者拼接出来的内容。
从文件读的话用「读JSON」更直接，那样拿到的就是结构。
"""

import json


def 取字段(内容: str, 路径: str) -> str:
    try:
        cur = json.loads(内容)
    except json.JSONDecodeError:
        return "[不是合法 JSON]"
    for key in 路径.split("."):
        key = key.strip()
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        elif isinstance(cur, list) and key.lstrip("-").isdigit():
            i = int(key)
            if not -len(cur) <= i < len(cur):
                return f"[下标越界] {路径}"
            cur = cur[i]
        else:
            return f"[没有字段] {路径}"
    # 取到的还是结构就转回 JSON，这样能接着传给下一个动词
    if isinstance(cur, (dict, list)):
        return json.dumps(cur, ensure_ascii=False)
    return "" if cur is None else str(cur)
