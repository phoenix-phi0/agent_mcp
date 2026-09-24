"""统计文本里的假名数量，格式为「平假名N 片假名M」。"""

import re

HIRAGANA = re.compile(r"[\u3040-\u309f]")
KATAKANA = re.compile(r"[\u30a0-\u30ff]")


def 假名统计(文本: str) -> str:
    return (f"平假名{len(HIRAGANA.findall(文本))} "
            f"片假名{len(KATAKANA.findall(文本))}")
