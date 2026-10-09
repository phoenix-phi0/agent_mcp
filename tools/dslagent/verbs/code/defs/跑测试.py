"""在项目里跑测试命令（环境变量 DSLAGENT_TEST_CMD，缺省 python3 -m unittest discover -s tests），限时 DSLAGENT_TEST_TIMEOUT 秒（缺省 120）。

返回 {passed: 是/否, summary}。summary 只留失败摘要——每个失败的测试名、
项目内的调用位置（相对路径:行号 + 那一行）、最后的异常行，和统计行。
认 unittest 的输出，也认 pytest --tb=native 的输出（runner 探测到 pytest 时就这么跑）。
结果同时写进笔记状态的【当前测试】。.pyc 写到项目外的缓存目录（PYTHONPYCACHEPREFIX，缺省 ~/.cache/dslagent-pycache），不往项目里留 __pycache__。
例如 设 t = 跑测试
"""

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
MAX_LINES = 30


def 跑测试() -> dict:
    r = _run()
    sys.path.insert(0, str(Path(__file__).parent))
    import _notes
    st = _notes.load(WORKSPACE)
    st["test"] = r["summary"]
    _notes.save(WORKSPACE, st)
    return r


def default_cmd() -> str:
    py = "python3" if shutil.which("python3") else sys.executable
    return f"{py} -m unittest discover -s tests"


def test_env():
    """跑测试用的环境：.pyc 写到项目外的缓存目录（PYTHONPYCACHEPREFIX），
    项目里不留 __pycache__，又不用每次重新编译。已设了 PYTHONPYCACHEPREFIX 就沿用。"""
    env = dict(os.environ)
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env.setdefault("PYTHONPYCACHEPREFIX", os.environ.get("DSLAGENT_PYCACHE")
                   or str(Path.home() / ".cache" / "dslagent-pycache"))
    return env


def run_raw(root, cmd=None, timeout=None):
    """跑一次测试命令，返回 (退出码或 None=超时/起不来, 合并后的输出)。"""
    cmd = cmd or os.environ.get("DSLAGENT_TEST_CMD") or default_cmd()
    timeout = int(timeout or os.environ.get("DSLAGENT_TEST_TIMEOUT") or 120)
    env = test_env()
    try:
        p = subprocess.run(shlex.split(cmd), cwd=root, capture_output=True, text=True,
                           timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, f"测试超过 {timeout} 秒没跑完"
    except OSError as e:
        return None, f"测试命令起不来：{e}"
    return p.returncode, (p.stderr or "") + (p.stdout or "")


def summarize(root, rc, text) -> dict:
    lines = text.splitlines()
    if rc is None:
        return {"passed": "否", "summary": text}
    ran = next((l for l in lines if l.startswith("Ran ")), "") or \
        next((l.strip("= ") for l in reversed(lines) if re.search(r"\d+ (passed|failed)", l)), "")
    if rc == 0:
        return {"passed": "是", "summary": f"全部通过：{ran}"}
    keep, i = [], 0
    pre = str(Path(root).resolve()) + "/"
    while i < len(lines):
        l = lines[i]
        if l.startswith(("FAIL:", "ERROR:")):
            keep.append(l)
        elif l.startswith('  File "') and pre in l:
            m = re.match(r'  File "(.+?)", line (\d+), in (\S+)', l)
            code = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if m:
                keep.append(f"  {m.group(1).replace(pre, '')}:{m.group(2)} {m.group(3)}: {code}")
        elif re.match(r"^\w*(Error|Exception)\b", l):
            keep.append("  " + l)
        elif l.startswith("FAILED"):
            keep.append(l)
        i += 1
    if len(keep) > MAX_LINES:
        keep = keep[:MAX_LINES - 1] + [f"…（截掉 {len(keep) - MAX_LINES + 1} 行）"]
    return {"passed": "否", "summary": "\n".join(keep) or "\n".join(lines[-15:])}


def _run() -> dict:
    root = Path(WORKSPACE).resolve()
    rc, text = run_raw(root)
    return summarize(root, rc, text)
