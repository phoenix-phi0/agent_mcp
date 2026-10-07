"""v6：在沙箱里跑一小段 Python 看中间值。返回 {ran: 是/否, text}；ran=否 是没运行（空/超长/黑名单）。
例如 设 run = 运行代码 {r.arg}

限制（尽力而为，不是安全边界——黑名单很容易绕过，真正兜底的是下面的进程级限制和事后回滚）：
  · ≤ 30 行；含 subprocess / os.system / shutil / socket / eval / exec / 写文件 等写法的直接拒绝（简单黑名单）
  · python3 -I -B（隔离模式：不读 PYTHON* 环境变量、不加用户 site、不把 cwd/脚本目录加进 sys.path；不写 .pyc），
    sys.path 只额外加沙箱根，cwd = 沙箱根；环境变量只留 PATH/LANG/HOME（HOME 指向运行目录），代理设成无效地址
  · 不联网：unshare -rn（新的用户+网络命名空间，只有一个没启用的 lo）；包装脚本里再把 socket 换成直接报错的桩
  · 超时 10 秒；RLIMIT_CPU 10s、RLIMIT_AS 1GB、RLIMIT_FSIZE 1MB
  · 运行前给沙箱所有文件拍快照，运行后比对：测试文件被改→回滚并报错；其他文件被改/新增/删除→同样回滚并报错
    （「运行」只许读和打印，改代码要用「修改」）
  · 输出（stdout+stderr）截到 3000 字
包装脚本和用户代码写在状态目录的 runcode/ 下（DSLAGENT_STATE），不进被修的项目。
"""

import hashlib
import re
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
MAX_LINES = 30
MAX_OUT = 3000
TIMEOUT = 10

_BAD = [
    (r"\b(?:import|from)\s+(subprocess|socket|shutil|ctypes|multiprocessing|pty|urllib|http|requests|ftplib|"
     r"smtplib|telnetlib|asyncio|importlib|signal|threading|tempfile)\b", "导入了禁止的模块"),
    (r"\bos\.(system|popen|exec\w*|spawn\w*|fork\w*|kill\w*|remove|unlink|rmdir|removedirs|rename|replace|"
     r"chmod|chown|truncate|makedirs|mkdir|symlink|link|chdir|putenv|environ)\b", "调用了危险的 os 函数"),
    (r"\bshutil\.", "用了 shutil"),
    (r"__import__|\beval\s*\(|\bexec\s*\(|\bcompile\s*\(|\bglobals\s*\(\s*\)\s*\[|__builtins__|__subclasses__",
     "用了动态执行/反射"),
    (r"\bopen\s*\([^)]*,\s*(?:mode\s*=\s*)?['\"][rbt]*[wax+]|\.open\s*\(\s*(?:mode\s*=\s*)?['\"][rbt]*[wax+]",
     "以写模式打开文件"),
    (r"\.(write_text|write_bytes|unlink|rmdir|rename|replace|touch|mkdir|symlink_to|chmod)\s*\(", "写/删文件"),
]


def _unshare_ok():
    try:
        p = subprocess.run(["unshare", "-rn", "true"], capture_output=True, timeout=5)
        return p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _snapshot(root):
    """项目文件快照（跳过 .git、虚拟环境、node_modules 等，见 _sandbox.SKIP_DIRS；单个文件 >2MB 不拍）。"""
    from _sandbox import skipped
    out = {}
    for f in root.rglob("*"):
        rel = f.relative_to(root)
        if f.is_file() and not skipped(rel.parts) and f.stat().st_size <= 2 << 20:
            out[str(rel)] = f.read_bytes()
    return out


def _tree_hash(snap):
    from _sandbox import is_test_rel
    h = hashlib.sha256()
    for k in sorted(x for x in snap if is_test_rel(x)):
        h.update(k.encode()); h.update(snap[k])
    return h.hexdigest()


def _limits():
    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT, TIMEOUT))
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 20, 1 << 20))


_WRAP = '''import sys
sys.path.insert(0, {root!r})
import socket as _s
def _no_net(*a, **k):
    raise OSError("运行：沙箱禁止联网")
_s.socket = _no_net; _s.create_connection = _no_net; _s.getaddrinfo = _no_net; _s.socketpair = _no_net
del _s
_code = open({user!r}, encoding="utf-8").read()
exec(compile(_code, "<运行>", "exec"), {{"__name__": "__main__"}})
'''


def 运行代码(代码: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _notes
    code = str(代码 or "")
    m = re.match(r"^\s*```(?:python|py)?\s*\n(.*?)\n?```\s*$", code, re.S)
    if m:
        code = m.group(1)
    code = code.strip("\n")
    st = _notes.load(WORKSPACE)
    rec = {"step": int(st.get("step", 0)) + 1, "lines": len(code.splitlines()), "chars": len(code)}

    def done(msg, **kw):
        rec.update(kw)
        rec["out_head"] = msg[:300]
        st["stats"]["runs"].append(rec)
        _notes.save(WORKSPACE, st)
        ran = kw.get("status") not in ("空", "超长", "黑名单")
        return {"ran": "是" if ran else "否", "text": msg}

    if not code.strip():
        return done("[运行] 没给代码", status="空")
    if rec["lines"] > MAX_LINES:
        return done(f"[运行] 代码 {rec['lines']} 行，超过 {MAX_LINES} 行上限，没运行。只写打印中间值的几行。", status="超长")
    for rx, why in _BAD:
        hit = re.search(rx, code)
        if hit:
            return done(f"[运行] 拒绝：{why}（{hit.group(0)}）。「运行」只用来调用项目函数、打印中间值；"
                        "改代码用「修改」。", status="黑名单", bad=hit.group(0))
    root = Path(WORKSPACE).resolve()
    from _sandbox import state_dir
    rdir = state_dir(root) / "runcode"
    rdir.mkdir(exist_ok=True)
    n = len(st["stats"]["runs"]) + 1
    user, wrap = rdir / f"run_{n}.py", rdir / f"wrap_{n}.py"
    user.write_text(code, encoding="utf-8")
    wrap.write_text(_WRAP.format(root=str(root), user=str(user)), encoding="utf-8")
    before = _snapshot(root)
    iso = _unshare_ok()
    cmd = (["unshare", "-rn"] if iso else []) + [sys.executable, "-I", "-B", str(wrap)]
    env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": str(rdir),
           "http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9",
           "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9"}
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True,
                           timeout=TIMEOUT, preexec_fn=_limits, stdin=subprocess.DEVNULL)
        rc, out = p.returncode, (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr.strip() else "")
    except subprocess.TimeoutExpired as e:
        rc = "超时"
        so = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        out = so + f"\n[运行] 超过 {TIMEOUT} 秒，被杀"
    sec = round(time.time() - t0, 2)
    out = re.sub(r'  File "[^"]*/wrap_\d+\.py", line \d+, in <module>\n(?:    .*\n)*', "", out)
    after = _snapshot(root)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    tests_hit = _tree_hash(before) != _tree_hash(after)
    note = ""
    if changed:
        for k in changed:
            f = root / k
            if k in before:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(before[k])
            elif f.exists():
                f.unlink()
        for d in sorted({(root / k).parent for k in changed if k not in before}, reverse=True):
            if d != root and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        note = (f"\n[运行] 错误：代码改动了{'测试' if tests_hit else ''}文件 {', '.join(changed[:5])}，已全部回滚。"
                "「运行」只许读和打印，改代码请用「修改」。")
    if len(out) > MAX_OUT:
        out = out[:MAX_OUT] + f"\n…（输出截掉 {len(out) - MAX_OUT} 字）"
    msg = f"[运行] 退出码 {rc}，{sec} 秒{'' if iso else '（unshare 不可用，没有网络隔离，只靠 socket 桩）'}：\n{out.strip() or '（没有输出）'}{note}"
    return done(msg, status="ok" if rc == 0 and not changed else ("回滚" if changed else f"rc={rc}"),
                rc=rc, sec=sec, iso=iso, rolled_back=changed, tests_touched=tests_hit)
