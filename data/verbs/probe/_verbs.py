"""probe 包：临时排查用的小动词，查完可删。"""

from pathlib import Path

from tools.verbs import scan_verbs

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def register(reg, workspace):
    scan_verbs(reg, PACK_DIR / "defs", workspace, pack_dir=PACK_DIR)
