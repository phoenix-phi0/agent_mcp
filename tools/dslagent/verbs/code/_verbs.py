"""code 包（dslagent 私有）：在项目目录里读、搜、改代码和跑测试，给 DSL 修 bug 流程用。

沙箱根就是引擎的工作目录（WORKSPACE，即要修的项目）。所有路径都在根下解析，越界的、
指向测试文件的修改一律返回错误说明而不是抛异常——让模型下一步能看到、自己改正。
状态/日志（notes_state.json、verb_log.jsonl、edit_log.jsonl、runcode/）写在
环境变量 DSLAGENT_STATE 指的目录，不写进项目，也不写项目的上级目录。
"""

from pathlib import Path

from tools.verbs import scan_verbs

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def register(reg, workspace):
    scan_verbs(reg, PACK_DIR / "defs", workspace, pack_dir=PACK_DIR)
