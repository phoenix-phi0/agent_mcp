"""记验收：把一轮验收（加载检查 + 比对约定 + 跑用例）的结果记进记录。通过 填 是|否，说明写失败原因（会截断）。
例如 记验收 graph 否 {失败}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 记验收(模块: str, 通过: str, 说明: str = "") -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    X.ctx().log("验收", 模块=模块.strip(), 通过=(通过.strip() == "是"), 说明=(说明 or "")[:1500])
    return ""
