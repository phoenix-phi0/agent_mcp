"""写修改计划：调一次模型，把问题清单写成一份 .zs 修改计划（改需求 / 新增模块 / 删除模块 / 改约定 四种动词 +
固定收尾动词 落实修改），自己存盘到 plan/changes/<序号>.zs（不检查格式，检查交给 检查修改计划）。返回存盘的相对路径。
问题 入参可以是渲染好的文本、读问题清单 的返回（{"items":…}）、或 items 列表，都会规整成干净的编号文本。
例如 设 plan = 写修改计划 问题={issues} 需求={需求} 任务={任务} 上次问题={problems} 模型={模型}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 写修改计划(问题, 需求: str = "", 任务: str = "", 上次问题: str = "", 模型: str = "sonnet") -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import change_plan as CP
    c = X.ctx()
    issues_text = CP.as_issues_text(问题)
    c.issues_items = (问题.get("items") if isinstance(问题, dict) else 问题) if isinstance(问题, (dict, list)) else c.issues_items
    c.task = 任务 or ""
    prev = CP.as_issues_text(上次问题) if (上次问题 or "") else ""
    if prev.strip():
        issues_text = f"{issues_text}\n\n【检查发现的问题（上一版计划没通过，逐条改掉）】\n{prev.strip()}"
    try:
        text = CP.write(c, issues_text, 任务, 模型 or "sonnet")
    except ValueError as e:
        X.fail(e)
    rel = CP.save(c.project, text)
    c.log("修改计划", 事件="写", 路径=rel)
    return rel
