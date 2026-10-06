"""文本归一化：NFKC（全角字母数字、半角片假名统一）、去掉所有空白。去标点 给「是」时连句号逗号（。.、,）也去掉。例如 归一化 {作答} 是

返回字符串。比较两段作答「是不是一样」之前两边都先过一遍：
「Ｃ」「c 」「Ｃ　」归一化后一样（大小写不动，要的话再「转大写」）。

去标点只去句号和逗号（NFKC 之后全角的 ．，已经是半角）：作答末尾多写一个
句号很常见，不该算错；别的标点（「」？！）是内容的一部分，不去。
"""

import re
import unicodedata

_PUNCT = re.compile(r"[。.、,]+")
# 「去标点」认的写法：是 / 1 / true / 去
_YES = {"是", "1", "true", "去", "yes"}


def 归一化(文本: str = "", 去标点: str = "") -> str:
    s = unicodedata.normalize("NFKC", str(文本 or ""))
    s = "".join(s.split())
    if str(去标点 or "").strip().lower() in _YES:
        s = _PUNCT.sub("", s)
    return s
