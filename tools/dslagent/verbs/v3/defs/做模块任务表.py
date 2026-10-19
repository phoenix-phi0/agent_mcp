"""做模块任务表：模块（逗号 / 空白分隔）→ 给 并行执行 用的任务列表，每个模块一项（脚本 做一个模块）。
例如 设 jobs = 做模块任务表 vocab,progress 3 opus
"""
import re
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 做模块任务表(模块: str, 最多: str = "3", 末次模型: str = "opus") -> list:
    names = [x for x in re.split(r"[,，、\s]+", 模块 or "") if x]
    return [{"脚本": "做一个模块", "参数": {"模块": n, "最多": str(最多), "末次模型": 末次模型}} for n in names]
