"""跑这个模块在约定里写的验收用例（contracts/<模块>.md 的「## 用例」）：每个用例在空库上单独跑（按本模块和上游模块的 entities 建表），时间固定。
例如 设 t = 跑用例 graph      返回 {all_passed: 是|否, failures: 文本（每个失败用例一行：用例 名：原因）, total}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 跑用例(模块: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _ctx as X
    if X.dry():
        return {"all_passed": "是", "failures": "", "total": 1}
    _, K, _, _ = X.load(WORKSPACE, 模块)
    r = K.run(Path(WORKSPACE), 模块.strip())
    return {"all_passed": "是" if r["全过"] else "否", "failures": r["原因"], "total": r["总数"]}
