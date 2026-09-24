"""japanese 包：日语教学专用动词。

拆法：互相独立的放 defs/ 一文件一个，共用数据表的留在这里。

取假名行 和 列假名行 都要读 五十音.json，拆开的话两个文件各写一遍读取
逻辑——那种重复正是 _verbs.py 该存在的理由。含日语、假名统计、假名进度
彼此无关，就拆出去了。
"""

import re
from pathlib import Path

from tools.verbs import load_data, scan_verbs

# 平假名、片假名、汉字
KANA_KANJI = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]")

# 加载时注入
WORKSPACE = Path(".")
PACK_DIR = Path(".")


def register(reg, workspace):
    scan_verbs(reg, PACK_DIR / "defs", workspace, pack_dir=PACK_DIR)

    pack = PACK_DIR

    def 五十音() -> list[dict]:
        # 每次都读文件：几 KB 的表无所谓，换来的是改数据不用重启
        return (load_data(pack, "五十音.json") or {}).get("行", [])

    @reg.verb("按行号取五十音图的一行假名。例如 取假名行 3 → さ行：さ、し、す、せ、そ")
    def 取假名行(行号: str) -> str:
        rows = 五十音()
        if not rows:
            return "[五十音.json 读不到]"
        try:
            i = int(行号)
        except ValueError:
            return f"[行号要是数字] {行号}"
        if not 1 <= i <= len(rows):
            return f"[超出范围] 五十音图共 {len(rows)} 行"
        row = rows[i - 1]
        return f"{row['名']}：{'、'.join(row['假名'])}"

    @reg.verb("列出五十音图所有行的名字，用于选择练习范围。")
    def 列假名行() -> str:
        return "，".join(f"{i}.{r['名']}" for i, r in enumerate(五十音(), 1))
