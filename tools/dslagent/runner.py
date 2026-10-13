"""入口：runner.run(project, task, out_dir, …) 在 project 里直接改文件，记录写进 out_dir，返回结果字典（同 result.json）。

    from tools.dslagent import runner
    r = runner.run(project, task, out_dir)          # 在 project 里直接改文件
    r["fixed"], r["engine_used"], r["handoff"]       # handoff：没修好时给兜底 claude 的交接说明

DSLAGENT_PLANNER=v2：整条转到 v2.py 的规划路径（文件大纲 → .zs 计划 → 执行 → 验收 → 边界复核）；
别的（缺省）转到 legacy/run.py 的旧路径（固定模板 → 模型规划 → 交回兜底）。
公共函数（tmp_dir、detect_test_cmd、_verb_module 等）在 common.py，engine=auto 的判定（decide_auto、capability_gaps）在 auto.py；
这里还把它们 import 进来，旧的 runner.xxx 写法仍能用。

**要在独立进程里跑**（python -m tools.dslagent run …，cbatch 就是这么调的）：旧路径把 llm_router 的
ClaudeCLIClient._run_local 换成常驻进程池、设 DSLAGENT_STATE 等环境变量，都是进程级的。
"""
from .auto import capability_gaps, decide_auto, test_state  # noqa: F401
from .common import (DEFS, LIB, PKG, ROOT, VERBS, _defs, _python, _verb_module, detect_test_cmd, tmp_dir)  # noqa: F401

MAX_PLAN, MAX_CALLS, WALL = 2, 15, 500      # 旧路径的缺省（legacy/run.py 里同名）


def run(project, task, out_dir, test_cmd=None, max_plan=MAX_PLAN, template=True, wall=WALL, inject=None,
        max_calls=MAX_CALLS, infer=None):
    """跑一次。DSLAGENT_PLANNER=v2 → v2.run（只认 test_cmd / wall）；否则 legacy.run.run（max_plan / template / inject / infer 只对它有效）。"""
    from . import v2
    if v2.enabled():
        return v2.run(project, task, out_dir, test_cmd=test_cmd, wall=wall)
    from .legacy import run as legacy_run
    return legacy_run.run(project, task, out_dir, test_cmd=test_cmd, max_plan=max_plan, template=template, wall=wall,
                          inject=inject, max_calls=max_calls, infer=infer)
