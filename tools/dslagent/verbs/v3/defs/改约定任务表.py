"""改约定任务表：一层的模块（逗号分隔）+「写约定目标」（{模块: 条目文本或空}，应用修改计划 的返回）→
并行执行 用的任务列表；只挑这一层里在目标表里的模块。条目非空（改约定）走 规划一份 的强制问题通道（带上一版 +
条目重写，只跑程序检查）；条目是空串（新增模块，还没约定过）走 规划一份 的正常写约定全流程（含复核）。
例如 设 jobs = 改约定任务表 {group} {r.写约定目标} {需求} {模型}
"""
import re
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 改约定任务表(组: str, 目标: dict, 需求: str = "", 模型: str = "sonnet") -> list:
    names = [x for x in re.split(r"[,，\s]+", 组 or "") if x]
    items = 目标 if isinstance(目标, dict) else {}
    jobs = []
    for m in names:
        if m not in items:
            continue
        args = {"种类": "约定", "模块": m, "需求": 需求 or "", "最多": "3", "模型": 模型 or "sonnet"}
        entry = items.get(m) or ""
        if entry:
            args["强制问题"] = entry
        jobs.append({"脚本": "规划一份", "参数": args})
    return jobs
