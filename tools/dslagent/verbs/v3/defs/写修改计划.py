"""写修改计划：调一次模型，把问题清单（文本）写成一份 .zs 修改计划（改需求 / 新增模块 / 删除模块 / 改约定 四种动词）。
不存盘（存盘另有动词），不检查格式（检查交给 检查修改计划）。返回计划文本。
例如 设 plan = 写修改计划 问题={issues} 需求={需求} 任务={任务} 上次问题={problems} 模型={模型}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 写修改计划(问题: str, 需求: str = "", 任务: str = "", 上次问题: str = "", 模型: str = "sonnet") -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import change_plan as CP
    c = X.ctx()
    issues_text = 问题
    if (上次问题 or "").strip():
        issues_text = f"{问题}\n\n【检查发现的问题（上一版计划没通过，逐条改掉）】\n{上次问题.strip()}"
    try:
        return CP.write(c, issues_text, 任务, 模型 or "sonnet")
    except ValueError as e:
        X.fail(e)
