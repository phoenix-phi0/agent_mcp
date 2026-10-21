"""全量回归：所有模块（含已完成、约定 hash 没变的）重新跑一次「加载检查 + 比对约定 + 跑用例」；
不过的标未完成、记回归原因，按依赖分层交 做一个模块 重做（第一轮任务就带这个原因），最多 2 轮，仍不过 终止 失败。
build.zs 末尾按依赖分层做完各模块组之后调。
例如 全量回归
方式=修改（修改流程收尾用）：失败模块只调 改模块（修改式重做，带失败原文），不调 做一个模块。
方式=核查（核查.zs 用）：只对有代码的模块报告，不重做、不改 state；返回 {count, items:[{issue,modules,basis,type}], summary}，没有代码时 count=0、summary 写「还没有代码，跳过」。
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 全量回归(方式: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dsl import current_engine
    from tools.dslagent.v3 import planning as PL, regress as RG
    c = X.ctx()
    try:
        top = PL.current_top(c)
    except ValueError as e:
        if 方式 == "核查":
            return {"count": 0, "items": [], "summary": "还没有 plan/top.zs，跳过"}
        X.fail(e)
    if 方式 == "核查":
        return RG.audit_regression(c, top)
    r = RG.full_regression(c, current_engine(), top, modify=(方式 == "修改"))
    return {"status": r["状态"], **({"rounds": r["轮数"]} if "轮数" in r else {}), **({"files": r["结果文件"]} if "结果文件" in r else {})}
