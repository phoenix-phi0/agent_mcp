"""核查任务表：模块名（逗号分隔）→ 给 并行派任务 用的任务列表，每个模块一项 {任务, 入参, 逻辑, 格式}（顺序同模块列表）。
入参 = 需求里和本模块相关的节 + 约定全文（去用例）+ 上游公开函数头 + 本模块现有代码文件（每个「文件:1-400」引用，超过 400 行分段，
由 派任务 读出）；回复格式 found:是否,items:列表（items 每项 {issue, modules, basis, type}）。只读不改。
任务：可选，这一轮要完成的任务；已知问题：可选，程序检查 / 回归 / 冒烟的结果（核查类动词的返回，或它们装在一个对象里），
任务描述里列出本模块相关的，说明不用重复。
例如 设 jobs = 核查任务表 {mods} {task} 已知问题={known}
"""
import re
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 核查任务表(模块列表: str = "", 任务: str = "", 已知问题=None) -> list:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import audit as AU
    c = X.ctx()
    names = [x for x in re.split(r"[,，\s]+", 模块列表 if isinstance(模块列表, str) else ",".join(map(str, 模块列表 or []))) if x]
    return AU.tasks(c, names, 任务 or "", 已知问题)
