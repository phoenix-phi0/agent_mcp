"""逻辑核查：对全部已有约定的模块并行跑角色 logic_check（找伪代码逻辑漏洞），按约定内容 hash 缓存（hash 没变不重调模型）。
返回 {count, items:[{issue, modules, basis, type}], summary}；疑点的 basis 写「logic_check(疑点)」，type=contract；没有 plan/top.zs 时 count=0。
例如 设 e = 逻辑核查
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 逻辑核查() -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import issues as IS, planning as PL
    c = X.ctx()
    try:
        top = PL.current_top(c)
    except ValueError:
        return {"count": 0, "items": [], "summary": "还没有 plan/top.zs，跳过"}
    items = IS.run_logic_checks(c, top)
    c.log("核查", 事件="逻辑核查", 疑点条数=len(items))
    return {"count": len(items), "items": items, "summary": f"{len(items)} 条疑点" if items else "没有疑点"}
