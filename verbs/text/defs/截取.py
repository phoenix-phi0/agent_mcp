"""按位置取一段：从第 起 个字开始（从 1 数，跟「遍历 … 序号 i」一样）取 长度 个字，长度不给就取到末尾。越界给空。例如 截取 ABCD {i} 1

起 是负数从末尾数（-1 是最后一个字）。
"""


def 截取(文本: str = "", 起: str = "1", 长度: str = "") -> str:
    s = str(文本 or "")
    try:
        start = int(str(起).strip() or "1")
        n = int(str(长度).strip()) if str(长度 or "").strip() else None
    except ValueError:
        raise ValueError(f"截取：起和长度要是整数，给的是「{起}」「{长度}」")
    if start == 0 or (n is not None and n < 0):
        raise ValueError(f"截取：起从 1 数（负数从末尾数），长度不能是负数：{起} {长度}")
    i = start - 1 if start > 0 else len(s) + start
    if i < 0 or i >= len(s):
        return ""
    return s[i:] if n is None else s[i:i + n]
