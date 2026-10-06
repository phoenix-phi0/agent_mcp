"""英文字母转大写，别的字不动。例如 转大写 abc → ABC"""


def 转大写(文本: str = "") -> str:
    return str(文本 or "").upper()
