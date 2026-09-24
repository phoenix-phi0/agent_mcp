"""统计文件的总行数（含空行和注释行）。"""

from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 行数(文件: str) -> str:
    root = Path(WORKSPACE).resolve()
    p = (root / 文件).resolve()
    if p != root and root not in p.parents:
        return f"[路径越界] {文件}"
    if not p.is_file():
        return "[文件不存在]"
    return str(len(p.read_text(encoding="utf-8").splitlines()))
