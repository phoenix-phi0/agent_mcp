"""列出项目里所有 .py 文件（相对路径，带行数；跳过隐藏目录、虚拟环境等）。例如 设 r = 列文件"""

import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
MAX_FILES = 300


def 列文件() -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    from _sandbox import py_files
    root = Path(WORKSPACE).resolve()
    files = py_files(root)
    out = []
    for rel in files[:MAX_FILES]:
        try:
            n = len((root / rel).read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError):
            n = "?"
        out.append(f"{rel}（{n} 行）")
    if len(files) > MAX_FILES:
        out.append(f"…（共 {len(files)} 个 .py 文件，只列了前 {MAX_FILES} 个，其余用 搜索代码 找）")
    return "\n".join(out) or "（没有 .py 文件）"
