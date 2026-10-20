"""核查：程序检查（全局检查 + 依赖与顶层不一致）+ 调一次模型找全局问题（职责重复、模块间缺口、跨模块调用对不上、
偏离需求、伪代码留白），两边的问题并成一份清单（不存盘，存盘由 存问题清单 做）。按各输入 hash 缓存，hash 没变不重调模型。
逻辑核查=是 时额外对全部已有约定的模块并行跑角色 logic_check（按约定内容 hash 缓存），疑点标「logic_check(疑点)」并入
问题清单，由修改规划决定采不采纳；缺省否（不开，跟原来行为一致）。
返回 {"count": n, "items": [{问题,涉及模块,依据}, …]}。
例如 设 g = 核查 需求={需求} 任务={任务} 模型={模型} 逻辑核查=是
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 核查(需求: str = "", 任务: str = "", 程序检查: str = "", 模型: str = "sonnet", 逻辑核查: str = "否") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import issues as IS
    c = X.ctx()
    try:
        items = IS.run_audit(c, 任务, 模型 or "sonnet", logic_check=(逻辑核查 == "是"))
    except ValueError as e:
        X.fail(e)
    return {"count": len(items), "items": items}
