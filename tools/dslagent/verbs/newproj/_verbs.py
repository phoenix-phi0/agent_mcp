"""newproj 包（dslagent 私有）：「新建项目」固定模板用的动词——读提示词原文、校验实体、拆分隔块、
调 gen 生成增删改查、预编译 sql、项目摘要、检查项目。

沙箱根就是引擎的工作目录（WORKSPACE，即要新建的项目）。所有路径都经沙箱 resolve 限在根下，
越界 / 失败一律返回 {ok: 否, msg} 而不是抛异常，让模板脚本能把报错带回给模型重写。
gen 需要 jinja2 / flask：当前解释器没有就转 .venv 的 python 子进程（见 defs/_gen.py）。
"""

from pathlib import Path

from tools.verbs import scan_verbs

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def register(reg, workspace):
    scan_verbs(reg, PACK_DIR / "defs", workspace, pack_dir=PACK_DIR)
