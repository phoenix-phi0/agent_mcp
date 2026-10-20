"""存修改计划：把通过检查的修改计划文本存成 plan/changes/<序号>.zs，序号接着上一份往后编。返回存盘的相对路径。
例如 设 w = 存修改计划 {plan}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 存修改计划(计划: str) -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import change_plan as CP
    c = X.ctx()
    rel = CP.save(c.project, 计划)
    c.log("修改计划", 事件="存", 路径=rel)
    return rel
