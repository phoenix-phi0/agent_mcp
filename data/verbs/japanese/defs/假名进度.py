"""按当前进度天数决定该学第几行假名。例如 假名进度 3 → さ行"""

from pathlib import Path

from tools.verbs import load_data

# 加载时注入
WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 假名进度(天数: str) -> str:
    rows = (load_data(PACK_DIR, "五十音.json") or {}).get("行", [])
    if not rows:
        return "[五十音.json 读不到]"
    try:
        d = int(天数)
    except ValueError:
        # 天数传错时退回第一行，而不是报错——这个动词常被拼进提示词，
        # 中断整个流程不如给个合理的默认值
        return rows[0]["名"]
    return rows[min(max(d, 1), len(rows)) - 1]["名"]
