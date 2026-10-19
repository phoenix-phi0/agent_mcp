"""检查规划：确定性检查一份规划文本，不调模型。返回 {ok: 是|否, 问题: 文本（一行一条，带序号）, 摘要: 前 3 条一行, 条数}。
种类=顶层：只有 项目 / 模块 [依赖]，名英文 snake、依赖存在、无环。
种类=约定：dslproj 的约定检查（格式、跨模块调用是依赖且上游有该公开函数、接口指向公开函数、每个公开函数有用例）
+ 约定里的 模块 / 依赖 与 top.zs 一致、表名以 模块名_ 开头。
例如 设 c = 检查规划 约定 {文本} graph
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 检查规划(种类: str, 文本: str, 模块: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import planning as PL
    c = X.ctx()
    try:
        probs = PL.check(c, 种类, 文本, 模块)
    except ValueError as e:
        X.fail(e)
    key = (种类, 模块)
    c.log("规划", 种类=种类, 模块=模块, 次=c.attempts.get(key, 0), 事件="检查", 通过=not probs, 条数=len(probs), 问题=probs[:6])
    return {"ok": "否" if probs else "是", "问题": X.numbered(probs), "摘要": "；".join(probs[:3]), "条数": len(probs)}
