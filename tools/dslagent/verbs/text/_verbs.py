"""转发到仓库的 verbs/text：dslagent 用私有动词根（只多一个 code 包），
但引擎的「用包」要求每个包都在同一个根下，所以这里只转发，不复制动词。"""

from pathlib import Path

from tools.verbs import scan_verbs

WORKSPACE = Path(".")
PACK_DIR = Path(".")
SRC = Path(__file__).resolve().parents[4] / "verbs" / "text"


def register(reg, workspace):
    scan_verbs(reg, SRC / "defs", workspace, pack_dir=SRC)
