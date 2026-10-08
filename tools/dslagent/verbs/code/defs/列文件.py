"""列出项目里所有 .py 文件（相对路径，带行数；跳过隐藏目录、虚拟环境等）。例如 设 r = 列文件
可选参数 全部：另外列出数据/文档文件（.json .csv .tsv .md .txt .yaml .yml .toml .ini .cfg）。例如 设 r = 列文件 全部"""

import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
MAX_FILES = 300
OTHER_EXT = (".json", ".csv", ".tsv", ".md", ".txt", ".yaml", ".yml", ".toml", ".ini", ".cfg")


def _other_files(root, skipped):
    out = []
    for f in root.rglob("*"):
        rel = f.relative_to(root)
        if f.suffix.lower() in OTHER_EXT and f.is_file() and not skipped(rel.parts) \
                and not rel.parts[-1].startswith("."):
            out.append(str(rel))
    return sorted(out)


def 列文件(范围: str = "") -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    from _sandbox import py_files, skipped
    root = Path(WORKSPACE).resolve()
    files = py_files(root)
    every = str(范围 or "").strip() in ("全部", "all", "*")
    if every:
        files = sorted(files + _other_files(root, skipped))
    out = []
    for rel in files[:MAX_FILES]:
        try:
            n = len((root / rel).read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError):
            n = "?"
        out.append(f"{rel}（{n} 行）")
    what = "文件" if every else ".py 文件"
    if len(files) > MAX_FILES:
        out.append(f"…（共 {len(files)} 个{what}，只列了前 {MAX_FILES} 个，其余用 搜索代码 找）")
    return "\n".join(out) or f"（没有{what}）"
