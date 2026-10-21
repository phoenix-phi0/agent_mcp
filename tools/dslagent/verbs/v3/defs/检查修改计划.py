"""检查修改计划：确定性检查一份修改计划（不调模型）。计划 入参可以是 plan/changes/<序号>.zs 的相对路径，也可以是
计划原文；问题清单和需求从 ctx 取（plan/issues/ 下最新一份、ctx.req），跟 修改.zs 里刚读的是同一份。
查：格式（四种动词 + 固定收尾动词 落实修改 开头，落实修改 必须是最后一行且只出现一次）、模块存在（删除模块/改约定
的模块要在 top.zs 里）、新增模块不重名且写了说明、新增模块的依赖不成环、问题清单里每个编号都被某行计划覆盖
（# 对应问题 N）、改需求的节号在需求文本里能找到。
返回 {ok: 是|否, problems: 文本（一行一条，带序号）, summary: 前 3 条一行, count}。
例如 设 c = 检查修改计划 {plan}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 检查修改计划(计划: str) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import change_plan as CP, issues as IS, planning as PL
    c = X.ctx()
    text = CP.resolve_plan_text(c.project, 计划)
    try:
        top = PL.current_top(c)
    except ValueError as e:
        X.fail(e)
    try:
        issues_list, _ = IS.load(c.project, "最新")
    except ValueError as e:
        X.fail(e)
    probs = CP.check_plan(text, issues_list, top, c.req)
    c.log("修改计划", 事件="检查", 通过=not probs, 条数=len(probs), 问题=probs[:6])
    return {"ok": "否" if probs else "是", "problems": X.numbered(probs), "summary": "；".join(probs[:3]), "count": len(probs)}
