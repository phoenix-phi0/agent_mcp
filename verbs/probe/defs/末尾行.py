"""取文件末尾若干行，默认 10 行。"""

from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 末尾行(文件: str, 行数: str = "10") -> str:
    root = Path(WORKSPACE).resolve()
    p = (root / 文件).resolve()
    if p != root and root not in p.parents:
        return f"[路径越界] {文件}"
    if not p.is_file():
        return "[文件不存在]"
    lines = p.read_text(encoding="utf-8").splitlines()
    n = max(1, int(行数))
    return "\n".join(f"{len(lines) - n + 1 + i}| {ln}"
                     for i, ln in enumerate(lines[-n:]))
