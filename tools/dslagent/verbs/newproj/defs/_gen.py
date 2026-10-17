"""newproj 动词共用（下划线开头，scan_verbs 不注册它）：参数解析、沙箱路径、空跑判断、gen 调用（进程内或 .venv 子进程）。"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
PROMPTS = REPO / "tools" / "dslagent" / "packs" / "newproj" / "prompts"
PACK_PREFIX = "pack:"
CORE = Path(__file__).with_name("_gencore.py")
TIMEOUT = 120


def sandbox_resolve(root, rel):
    """rel 解析到 root 下；越界返回 (None, 错误说明)。同 code 包的 _sandbox.resolve。"""
    root = Path(root).resolve()
    rel = str(rel or "").strip().strip("'\"")
    if not rel:
        return None, "没给文件名"
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        return None, f"[路径越界] {rel} 不在沙箱里"
    return p, ""


def parse_obj(x):
    """动词参数：dict 原样，JSON 文本解析。返回 (dict, 错误)。"""
    if isinstance(x, dict):
        return x, ""
    try:
        o = json.loads(x) if str(x or "").strip() else {}
    except (TypeError, json.JSONDecodeError) as e:
        return None, f"参数不是 JSON 对象：{e}"
    return (o, "") if isinstance(o, dict) else (None, "参数要是 JSON 对象")


def project_root(workspace, d):
    p, err = sandbox_resolve(workspace, d or ".")
    if err:
        return None, err
    return p, ""


def is_dry():
    from tools.dsl import current_engine
    eng = current_engine()
    return bool(getattr(eng, "dry_run", False))


def have_deps():
    if os.environ.get("NEWPROJ_FORCE_SUBPROCESS"):
        return False
    try:
        import flask  # noqa: F401
        import jinja2  # noqa: F401
    except ImportError:
        return False
    return True


def venv_python():
    p = REPO / ".venv" / "bin" / "python"
    return str(p) if p.is_file() else sys.executable


def run_op(op, args):
    """调 _gencore.OPS[op](**args)，返回 dict。有 jinja2/flask 就进程内，否则 .venv python 子进程（-I，自己把仓库根放进 path）。"""
    if have_deps():
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        sys.path.insert(0, str(CORE.parent))
        try:
            import _gencore
            return _gencore.call(op, args)
        finally:
            sys.path.remove(str(CORE.parent))
    try:
        p = subprocess.run([venv_python(), "-I", str(CORE), str(REPO)], input=json.dumps({"op": op, "args": args}, ensure_ascii=False),
                           capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": "否", "msg": f"超过 {TIMEOUT} 秒没跑完"}
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"ok": "否", "msg": ("子进程没给出结果：" + (p.stderr or p.stdout))[-800:]}
