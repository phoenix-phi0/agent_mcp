"""写规划：按种类（顶层 / 约定）调一次模型写规划文本，返回文本。走 v2 的 Model（计数、记账、预算）。
例如 设 文本 = 写规划 约定 需求={req} 模块=graph 上次问题={问题}
入参 种类=顶层|约定；需求 缺省用流程的需求；模块（种类=约定必填）；上次问题 非空时按「上次的内容 + 问题」重写；模型 缺省 sonnet。
提示词在 tools/dslagent/v3/prompts/<种类>.md；输入 = 需求 + 顶层规划 + 上游已通过的约定。
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 写规划(种类: str, 需求: str = "", 模块: str = "", 上次问题: str = "", 模型: str = "sonnet") -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import planning as PL
    try:
        return PL.write(X.ctx(), 种类, 需求, 模块, 上次问题, 模型 or "sonnet")
    except ValueError as e:
        X.fail(e)
