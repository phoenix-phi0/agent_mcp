"""全局重写任务表：全局检查 的「按模块」（{模块: 问题文本}）→ 给 并行执行 用的任务列表，每个带问题的模块一项
（脚本 规划一份，种类=约定，强制问题=该模块的问题，逼它重写——即使它自己原来的约定单独检查是过的）。
例如 设 jobs = 全局重写任务表 {g.by_module} {需求} {模型}
"""
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 全局重写任务表(按模块: dict, 需求: str = "", 模型: str = "sonnet") -> list:
    items = 按模块 if isinstance(按模块, dict) else {}
    return [{"脚本": "规划一份", "参数": {"种类": "约定", "模块": m, "需求": 需求, "最多": "2", "模型": 模型 or "sonnet", "强制问题": p}}
            for m, p in sorted(items.items())]
