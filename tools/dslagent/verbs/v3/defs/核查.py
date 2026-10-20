"""核查：程序检查（全局检查 + 依赖与顶层不一致）+ 调一次模型找全局问题（职责重复、模块间缺口、跨模块调用对不上、
偏离需求、伪代码留白），两边的问题并成一份清单（不存盘，存盘由 存问题清单 做）。按各输入 hash 缓存，hash 没变不重调模型。
返回 {"count": n, "items": [{问题,涉及模块,依据}, …]}。
例如 设 g = 核查 需求={需求} 任务={任务} 模型={模型}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 核查(需求: str = "", 任务: str = "", 程序检查: str = "", 模型: str = "sonnet") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import issues as IS
    c = X.ctx()
    try:
        items = IS.run_audit(c, 任务, 模型 or "sonnet")
    except ValueError as e:
        X.fail(e)
    return {"count": len(items), "items": items}
