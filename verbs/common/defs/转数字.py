"""把文本转成数字（整数或小数），转不了报错。例如 设 seed.sort = 转数字 {sort}

为什么要有：DSL 里的值一律是文本，「设 x.sort = 1」写进 JSON 文件就成了
"sort": "1"。文件要的是数字时（content/series.jsonl 的 sort），写之前先转。
整数给 int，有小数点的给 float。空串、不是数字的报错——悄悄写个 0 进去，
排序错了也看不出来。
"""


def 转数字(值: str = ""):
    s = str(值 if 值 is not None else "").strip()
    try:
        f = float(s)
    except ValueError:
        raise ValueError(f"转数字：「{s}」不是数字")
    return int(f) if f == int(f) and "." not in s and "e" not in s.lower() else f
