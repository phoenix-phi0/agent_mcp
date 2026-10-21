"""做修改：改模块 的一轮。跟 做模块 一样起子进程跑一次 v2（在项目拷贝里做，只把本模块范围内的文件拷回项目），
区别只在任务文本：模块名 + 「## 这次是修改，不是新建」+ 修改需求 + 本模块计划条目与问题 + 新旧约定差异 + 范围规则（modify.mod_task），
上一轮失败原因也附在后面。补改（v2 的验收失败后补改）的入参里带着任务原文，所以同样带这些。
返回 {status, reason, cost, calls, round, model, log_dir, secs}（同 做模块）。
例如 设 r = 做修改 vocab {失败} 模型=opus
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 做修改(模块: str, 上次失败: str = "", 模型: str = "sonnet") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import modify as MD, modrun
    c = X.ctx()
    name = 模块.strip()
    r = modrun.run_module(c, name, 上次失败, 模型 or "sonnet", task_text_override=MD.mod_task(c.project, name, 上次失败))
    return {"status": r["状态"], "reason": r["原因"], "cost": r["花费"], "calls": r["调用"], "round": r["轮"],
            "model": r["模型"], "log_dir": r["记录目录"], "secs": r["秒"]}
