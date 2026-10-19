"""规划任务表：一层的模块（逗号分隔）→ 给 并行执行 用的任务列表，每个模块一项（脚本 规划一份，种类=约定）。
例如 设 jobs = 规划任务表 vocab,progress {需求} 3 sonnet
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 规划任务表(模块组: str, 需求: str = "", 最多: str = "3", 模型: str = "sonnet") -> list:
    sys.path.insert(0, str(Path(__file__).parent))
    from tools.dslagent.v3 import planning as PL
    return PL.tasks(模块组, 需求, 最多, 模型 or "sonnet")
