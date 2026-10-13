"""dslagent 的公共函数（v2、验收、引擎、旧路径都用，不依赖 legacy/）：目录、测试命令探测、动词模块加载、claude 子进程环境。"""
import os
import shutil
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent
ROOT = PKG.parents[1]
LIB = PKG / "lib"
VERBS = PKG / "verbs"
DEFS = VERBS / "code" / "defs"


def _defs():
    if str(DEFS) not in sys.path:
        sys.path.insert(0, str(DEFS))


def sandbox():
    """verbs/code/defs/_sandbox.py（py_files / is_test_rel 等）。"""
    _defs()
    import _sandbox
    return _sandbox


def src_files(repo):
    """项目里的非测试 .py（相对路径列表）。"""
    sb = sandbox()
    return [f for f in sb.py_files(repo) if not sb.is_test_rel(f)]


def _verb_module(name):
    """直接加载 code 包里的一个动词文件（跑测试、列文件、改文件的核对计划等不经引擎时用）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"_dslagent_{name}", DEFS / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def tmp_dir():
    """临时目录（claude 子进程的 TMPDIR、进程池的空工作目录）。DSLAGENT_TMP > ~/.cache/dslagent/tmp。
    默认不用 /tmp：WSL 上 /tmp 是 1.9G 的内存盘，满过两次，claude 写不了临时文件就 ENOSPC 秒退。"""
    d = Path(os.environ.get("DSLAGENT_TMP") or Path.home() / ".cache" / "dslagent" / "tmp")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _python():
    """PATH 上有 python3 就写 python3（不写绝对路径：兜底 claude 的 Bash(python3 …*) 放行规则才对得上）。"""
    return "python3" if shutil.which("python3") else sys.executable


def detect_test_cmd(project):
    """按项目探测测试命令：有 pytest 配置（pytest.ini / conftest.py / pyproject 的 [tool.pytest] / setup.cfg、tox.ini 的
    [pytest] 段）且 python3 装了 pytest → pytest（--tb=native 让摘要能认出调用位置）；否则有 tests/ → unittest discover -s tests；
    顶层有 test_*.py → unittest discover；都没有 → None。"""
    import subprocess
    p = Path(project)
    py = _python()
    cfg = (p / "pytest.ini").is_file() or (p / "conftest.py").is_file() or (p / "tests" / "conftest.py").is_file()
    for name, marks in (("pyproject.toml", ("[tool.pytest",)), ("setup.cfg", ("[tool:pytest]",)), ("tox.ini", ("[pytest]",))):
        f = p / name
        if f.is_file():
            try:
                txt = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                txt = ""
            cfg = cfg or any(m in txt for m in marks)
    if cfg:
        try:
            ok = subprocess.run([py, "-c", "import pytest"], capture_output=True, timeout=30).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        if ok:
            return f"{py} -m pytest -q --tb=native -p no:cacheprovider"
    if (p / "tests").is_dir():
        return f"{py} -m unittest discover -s tests"
    if any(p.glob("test_*.py")):
        return f"{py} -m unittest discover"
    return None


def child_env(tmp):
    """claude 子进程的环境：洗掉 CLAUDECODE / CLAUDE_CODE_*（cbatch 同款）和 ANTHROPIC_API_KEY（要走订阅登录），
    TMPDIR / CLAUDE_CODE_TMPDIR 指到可写的临时目录（/tmp 满了 claude 会 ENOSPC 秒退，plan7 撞上过）。"""
    from tools.cbatch import _child_env
    env = _child_env()
    env.pop("ANTHROPIC_API_KEY", None)
    env["TMPDIR"] = env["CLAUDE_CODE_TMPDIR"] = str(tmp)
    return env
