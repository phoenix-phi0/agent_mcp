"""dslproj 动词共用：是否空跑、读约定、取项目根。"""
import sys
from pathlib import Path

from tools.dsl import DSLError, current_engine


def dry():
    return bool(getattr(current_engine(), "dry_run", False))


def pack():
    """packs/dslproj 的 project / cases 模块（动词文件按路径单独加载，仓库根已在 sys.path 里）。"""
    from tools.dslagent.packs.dslproj import cases, project
    return project, cases


def load(workspace, module):
    """→ (project 模块, cases 模块, 约定, 全部模块名)；模块名不对 / 约定有问题抛 DSLError。"""
    P, K = pack()
    name = str(module or "").strip()
    if not name:
        raise DSLError("要写模块名，如：跑用例 graph")
    try:
        c, _ = P.load_contract(Path(workspace), name)
    except P.ProjError as e:
        raise DSLError(str(e)) from None
    return P, K, c, P.all_modules(Path(workspace))
