"""查未受影响用例 <模块>：改模块 的验收之一。修改前（改约定 登记时）通过的用例，只要它调的函数没出现在新旧约定差异里、用例本身没改，
修改后必须仍通过。没有修改记录 / 修改前没有可比的用例 → 通过。
返回 {ok: 是|否, problems: 文本（每个变红的用例一行）, checked: 比较了几个用例}。
例如 设 u = 查未受影响用例 vocab
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 查未受影响用例(模块: str) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import modify as MD
    r = MD.unaffected_check(X.ctx().project, 模块.strip())
    return {"ok": "是" if r["ok"] else "否", "problems": "\n".join(r["problems"]), "checked": r["checked"]}
