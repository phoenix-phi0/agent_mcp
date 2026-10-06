"""从一段作答里抓第一个选项字母（A–D，全角、小写都认），返回大写的半角字母；没有就空。例如 取字母 选ｃ → C

学生会写「C」「c」「选C」「C.」「答案是C」「（Ｃ）」，都只要那个字母。
先 NFKC（全角转半角）再找，只认 A–D：选择题最多四个选项。
"""

import re
import unicodedata

_LETTER = re.compile(r"[A-Da-d]")


def 取字母(文本: str = "") -> str:
    m = _LETTER.search(unicodedata.normalize("NFKC", str(文本 or "")))
    return m.group().upper() if m else ""
