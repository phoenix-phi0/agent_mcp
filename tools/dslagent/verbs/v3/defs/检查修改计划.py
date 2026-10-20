"""检查修改计划：确定性检查一份修改计划文本（不调模型）。查：格式（只能是四种动词开头）、模块存在（删除模块/改约定
的模块要在 top.zs 里）、新增模块不重名且写了说明、新增模块的依赖不成环、问题清单里每个编号都被某行计划覆盖
（# 对应问题 N）、改需求的节号在需求文本里能找到。
返回 {ok: 是|否, problems: 文本（一行一条，带序号）, summary: 前 3 条一行, 条数}。
例如 设 c = 检查修改计划 {plan}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 检查修改计划(计划: str, 问题: str = "", 需求: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import change_plan as CP, issues as IS, planning as PL
    c = X.ctx()
    try:
        top = PL.current_top(c)
    except ValueError as e:
        X.fail(e)
    issues_list = IS.parse_issues(问题) if 问题 else []
    req_text = Path(需求).read_text(encoding="utf-8") if 需求 and Path(需求).is_file() else (需求 or c.req)
    probs = CP.check_plan(计划, issues_list, top, req_text)
    c.log("修改计划", 事件="检查", 通过=not probs, 条数=len(probs), 问题=probs[:6])
    return {"ok": "否" if probs else "是", "problems": X.numbered(probs), "summary": "；".join(probs[:3]), "条数": len(probs)}
