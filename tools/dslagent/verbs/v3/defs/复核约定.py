"""复核约定：约定通过程序检查后，调一次模型对照本轮需求复核（默认 sonnet）。
入参只给本轮需求全文 + 该模块约定；模型逐条找约定与需求不一致的地方（需求要的行为被删改或替换、编造了需求没有的功能、超出本轮范围、
本轮范围内该有却没有的函数 / 接口）。返回 {ok: 是|否, problems: 文本（一行一条，带序号）, summary: 前 3 条一行, count, status: 已复核|未复核}。
例如 设 v = 复核约定 graph {文本} 需求={req}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 复核约定(模块: str, 文本: str, 需求: str = "", 模型: str = "sonnet") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import planning as PL
    c = X.ctx()
    try:
        r = PL.review(c, 模块, 文本, 需求, 模型 or "sonnet")
    except ValueError as e:
        X.fail(e)
    return {"ok": "是" if r["passed"] else "否", "problems": X.numbered(r["issues"]), "summary": "；".join(r["issues"][:3]),
            "count": len(r["issues"]), "status": r["状态"]}
