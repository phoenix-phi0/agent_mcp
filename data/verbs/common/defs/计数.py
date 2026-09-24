"""统计文件的非空行数。用于查看已收集多少条数据。"""

from pathlib import Path

# 加载时注入
WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 计数(文件: str) -> str:
    # 路径限制在工作目录内。动词是被脚本调用的，脚本内容可能来自模型，
    # 不做这层检查就等于把整个磁盘暴露给生成出来的路径
    root = Path(WORKSPACE).resolve()
    p = (root / 文件).resolve()
    if p != root and root not in p.parents:
        return f"[路径越界] {文件}"
    if not p.is_file():
        return "0"
    return str(sum(1 for ln in p.read_text(encoding="utf-8").splitlines()
                   if ln.strip()))
