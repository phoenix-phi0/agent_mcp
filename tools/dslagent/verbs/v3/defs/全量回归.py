"""全量回归：所有模块（含已完成、约定 hash 没变的）重新跑一次「加载检查 + 比对约定 + 跑用例」；
不过的标未完成、记回归原因，按依赖分层交 做一个模块 重做（第一轮任务就带这个原因），最多 2 轮，仍不过 终止 失败。
build.zs 末尾按依赖分层做完各模块组之后调。
例如 全量回归
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 全量回归() -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dsl import current_engine
    from tools.dslagent.v3 import planning as PL, regress as RG
    c = X.ctx()
    try:
        top = PL.current_top(c)
    except ValueError as e:
        X.fail(e)
    r = RG.full_regression(c, current_engine(), top)
    return {"status": r["状态"], **({"rounds": r["轮数"]} if "轮数" in r else {})}
