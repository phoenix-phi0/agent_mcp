"""dslproj 包（dslagent 私有）：做 DSL 项目里一个模块用的三个动词——加载检查、比对约定、跑用例。

动词只是壳：逻辑在 packs/dslproj/（project.py 比对 / 加载检查，cases.py 跑用例）。沙箱根 = 引擎工作目录（要做模块的项目）。
空跑（计划检查时）不碰项目，给结构合法的假结果。读 / 搜 / 改 / 写文件用 code 包的动词。
"""

from pathlib import Path

from tools.verbs import scan_verbs

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def register(reg, workspace):
    scan_verbs(reg, PACK_DIR / "defs", workspace, pack_dir=PACK_DIR)
