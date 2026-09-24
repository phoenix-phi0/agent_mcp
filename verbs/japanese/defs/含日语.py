"""检查文本里有没有日语字符。返回「是」或「否」。

SOUL.md 里有一条「本次对话不含任何日语字符则跳过写入」，这个动词让那条
判断变成确定性的，不必让模型自己看。
"""

import re

# 平假名、片假名、汉字。汉字段也算——中日共用汉字，但对话里出现汉字
# 本来就说明在讨论日语内容
KANA_KANJI = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]")


def 含日语(文本: str) -> str:
    return "是" if KANA_KANJI.search(文本) else "否"
