"""沙箱路径检查、状态目录、源码清单，几个动词共用（下划线开头，scan_verbs 不注册它）。"""

import os
import tempfile
from pathlib import Path

# 搜索/列文件时跳过的目录：真实项目里有 .git、虚拟环境、node_modules，整个扫一遍又慢又没用
SKIP_DIRS = {"__pycache__", "node_modules", "venv", "env", "site-packages", "build", "dist"}


def resolve(root, rel):
    """rel 解析到 root 下的绝对路径；越界返回 (None, 错误说明)。"""
    root = Path(root).resolve()
    rel = str(rel or "").strip().strip("'\"")
    if not rel:
        return None, "没给文件名"
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        return None, f"[路径越界] {rel} 不在沙箱里"
    return p, ""


def is_test_rel(rel):
    """测试文件：路径里有 tests/ 或 test/ 目录，或文件名是 test_*.py / *_test.py / conftest.py。"""
    parts = Path(str(rel)).parts
    if any(p in ("tests", "test") for p in parts[:-1]):
        return True
    name = parts[-1] if parts else ""
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def is_test_path(root, p):
    return is_test_rel(Path(p).resolve().relative_to(Path(root).resolve()))


def skipped(rel_parts):
    return any(p.startswith(".") or p in SKIP_DIRS for p in rel_parts[:-1])


def py_files(root):
    root = Path(root).resolve()
    out = []
    for f in root.rglob("*.py"):
        rel = f.relative_to(root)
        if not skipped(rel.parts):
            out.append(str(rel))
    return sorted(out)


def state_dir(root):
    """状态/日志目录：DSLAGENT_STATE（runner 设成任务目录下的 state/）；没设就放临时目录，绝不写进项目。"""
    d = os.environ.get("DSLAGENT_STATE")
    if not d:
        d = Path(tempfile.gettempdir()) / "dslagent_state" / Path(root).resolve().name
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    return d
