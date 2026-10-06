# -*- coding: utf-8 -*-
"""代理 CLI 的工作目录：默认空临时目录、跑完删；拒绝 ~、/、家目录。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_zcode_workdir.py

不真的调 zcode / claude：zcode_tool 里的 subprocess.run / Popen 换成假的，
记下 cwd 和那一刻目录里有什么。HOME 换成临时目录里的假家目录（放一个
.ssh），不碰真家目录。只有 WSL 那段 mktemp 脚本是真用 bash 跑的，跑的是
sh -c 'pwd; ls -A'，不是 zcode。
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="zcode_workdir_test_"))
HOME = TMP / "home"
(HOME / ".ssh").mkdir(parents=True)
(HOME / "proj").mkdir()
(HOME / "proj" / "a.py").write_text("x = 1\n", encoding="utf-8")
os.environ["HOME"] = str(HOME)
os.environ["CBATCH_HOME"] = str(TMP / "jobs")
os.environ["CBATCH_CLAUDE"] = "/bin/true"

from tools import cbatch, zbatch, zcode_tool    # noqa: E402
from tools.zcode_tool import (UnsafeWorkdirError, ZCodeTool,    # noqa: E402
                              check_workdir, check_wsl_workdir)

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"：{extra}" if extra else ""))


def raises(fn, *a, exc=UnsafeWorkdirError, **k):
    try:
        fn(*a, **k)
    except exc as e:
        return str(e) or type(e).__name__
    return None


# ----------------------------------------------------------------------
# 假的 subprocess：记下 cwd、当时目录在不在、里面有什么

SEEN = []
REPLY = json.dumps({"result": "print(1)"})


def fake_run(args, **kw):
    cwd = kw.get("cwd")
    SEEN.append({"args": args, "cwd": cwd,
                 "exists": bool(cwd) and os.path.isdir(cwd),
                 "entries": sorted(os.listdir(cwd)) if cwd and os.path.isdir(cwd) else None})
    return subprocess.CompletedProcess(args, 0, REPLY, "")


class FakePopen:
    def __init__(self, args, **kw):
        fake_run(args, **kw)
        self.stdout = io.StringIO("一行\n两行\n")
        self.stdin = None

    def poll(self):
        return 0

    def wait(self):
        return 0


# 只换 zcode_tool 看到的那份：直接改 subprocess 模块会连下面真跑 bash 的也换掉
fake_subprocess = types.ModuleType("fake_subprocess")
fake_subprocess.__dict__.update(subprocess.__dict__)
fake_subprocess.run = fake_run
fake_subprocess.Popen = FakePopen
zcode_tool.subprocess = fake_subprocess


def last():
    return SEEN[-1]


def main():
    tmp_root = os.path.realpath(tempfile.gettempdir())

    print("check_workdir：拒绝的")
    for bad, why in [("~", "~"), ("~/proj", "~ 开头"), ("/", "根目录"),
                     (str(HOME), "家目录"), (str(HOME.parent), "家目录的上级"),
                     ("/home/somebody-else", "别人的家目录形状"),
                     (str(HOME / ".ssh"), ".ssh 里面"), ("", "空串"),
                     (str(TMP / "nope"), "不存在")]:
        check(raises(check_workdir, bad), f"拒绝 {why}（{bad!r}）")
    leaky = TMP / "leaky"
    leaky.mkdir()
    (leaky / ".git-credentials").write_text("", encoding="utf-8")
    msg = raises(check_workdir, leaky)
    check(msg and ".git-credentials" in msg, "拒绝含 .git-credentials 的父目录，报出是哪个", msg)
    check(issubclass(UnsafeWorkdirError, ValueError), "是 ValueError，老的 except ValueError 照样接得住")

    print("check_workdir：允许的")
    check(check_workdir(HOME / "proj") == str((HOME / "proj").resolve()), "允许家目录下的项目子目录")
    check(check_workdir(ROOT) == str(ROOT), "允许本项目目录", ROOT)
    proj_claude = TMP / "with_claude_settings"
    (proj_claude / ".claude").mkdir(parents=True)
    check(check_workdir(proj_claude), "项目自己的 .claude/ 设置目录不算凭证")

    print("check_wsl_workdir")
    for bad in ["~", "~/x", "/", "/home", "/home/ysc", "/home/ysc/", "/root",
                "/home/ysc/mcp/../", "/home/ysc/.ssh/x", "relative/path", ""]:
        check(raises(check_wsl_workdir, bad), f"拒绝 {bad!r}")
    check(check_wsl_workdir("/home/ysc/mcp") == "/home/ysc/mcp", "允许 /home/ysc/mcp")

    print("run：默认在空临时目录里跑，跑完删")
    tool = ZCodeTool(command=["zcode"])
    tool.run("hi")
    s = last()
    check(s["cwd"] and os.path.realpath(s["cwd"]).startswith(tmp_root + os.sep)
          and os.path.basename(s["cwd"]).startswith("zcode_"),
          "cwd 是临时目录 zcode_xxx", s["cwd"])
    check(s["exists"] and s["entries"] == [], "调用时目录存在且是空的", s)
    check(not os.path.exists(s["cwd"]), "调用后已删")
    tool.run("again")
    check(last()["cwd"] != s["cwd"], "每次新建一个")
    check(s["cwd"] != str(HOME) and s["cwd"] != "/", "不是家目录也不是 /")

    print("stream：同样")
    lines = list(tool.stream("hi"))
    s = last()
    check(lines == ["一行\n", "两行\n"], "输出照常", lines)
    check(s["exists"] and s["entries"] == [] and not os.path.exists(s["cwd"]),
          "临时目录、空、跑完删", s)

    print("run_json / generate_code_text：默认临时目录")
    code = tool.generate_code_text("写个 print")
    s = last()
    check(code == "print(1)", "拿到代码", code)
    check(os.path.basename(s["cwd"]).startswith("zcode_") and not os.path.exists(s["cwd"]),
          "临时目录且已删", s["cwd"])

    print("显式 cwd")
    n = len(SEEN)
    check(raises(tool.run, "x", cwd="/"), "run(cwd='/') 拒绝")
    check(raises(tool.run, "x", cwd=str(HOME)), "run(cwd=家目录) 拒绝")
    check(raises(tool.generate_code_text, "x", cwd="~"), "generate_code_text(cwd='~') 拒绝")
    check(len(SEEN) == n, "拒绝时根本没起进程")
    check(raises(ZCodeTool, command=["zcode"], cwd=str(HOME)), "构造时给家目录就拒绝")
    check(raises(tool.write_code_json, "改点东西", cwd="/"), "write_code_json(cwd='/') 拒绝")
    tool.run("x", cwd=HOME / "proj")
    s = last()
    check(s["cwd"] == str((HOME / "proj").resolve()) and s["entries"] == ["a.py"],
          "允许项目子目录，就在那儿跑", s)
    check((HOME / "proj" / "a.py").exists(), "显式目录跑完不删")
    t2 = ZCodeTool(command=["zcode"], cwd=HOME / "proj")
    t2.run("x")
    check(last()["cwd"] == str((HOME / "proj").resolve()), "构造时给的默认目录生效")

    print("generate_code_text_wsl：命令行")
    tool.generate_code_text_wsl("写个 print")
    a = last()["args"]
    i = a.index("--cd")
    check(a[i + 1] == "/tmp", "不给 wsl_cwd 时 --cd /tmp，不是 ~", a[:8])
    script = a[a.index("-ic") + 1]
    check("mktemp -d" in script and "rm -rf" in script and "exec" not in script,
          "用 mktemp 临时目录、trap 删除、不 exec", script)
    check("~" not in a, "命令行里没有 ~")
    check(a[a.index("-ic") + 2:a.index("-ic") + 4] == ["zcode", "zcode"],
          "$0 和 zcode 命令照旧", a)
    check("\\" not in script and all(ord(c) < 128 for c in script),
          "脚本纯 ASCII 无反斜杠（Windows 命令行转义安全）")
    tool.generate_code_text_wsl("x", wsl_cwd="/home/ysc/mcp")
    a = last()["args"]
    check(a[a.index("--cd") + 1] == "/home/ysc/mcp" and a[a.index("-ic") + 1] == 'exec "$@"',
          "给了项目目录就 --cd 过去", a[:8])
    for bad in ["~", "/", "/home/ysc", "  "]:
        check(raises(tool.generate_code_text_wsl, "x", wsl_cwd=bad), f"wsl_cwd={bad!r} 拒绝")

    print("WSL 那段脚本真跑一遍（bash，不是 zcode）")
    wtmp = TMP / "wsltmp"
    wtmp.mkdir()
    p = subprocess.run(["bash", "-c", zcode_tool._WSL_TMP_SCRIPT, "zcode",
                        "sh", "-c", 'pwd; ls -A; echo "$1"', "sh", "参数 原样"],
                       capture_output=True, text=True, cwd="/tmp",
                       env={**os.environ, "TMPDIR": str(wtmp)})
    out = p.stdout.splitlines()
    check(p.returncode == 0 and out and out[0].startswith(str(wtmp) + "/zcode_"),
          "在 mktemp 出来的目录里跑", (p.returncode, p.stdout, p.stderr))
    check(out[1:] == ["参数 原样"], "目录是空的，参数原样传过去", out)
    check(list(wtmp.iterdir()) == [], "跑完目录删了", list(wtmp.iterdir()))
    p = subprocess.run(["bash", "-c", zcode_tool._WSL_TMP_SCRIPT, "zcode", "sh", "-c", "exit 7"],
                       capture_output=True, text=True, env={**os.environ, "TMPDIR": str(wtmp)})
    check(p.returncode == 7 and list(wtmp.iterdir()) == [], "退出码透传，出错也删目录", p.returncode)

    print("zbatch.submit")
    posted = []
    zbatch._base_url = lambda: "http://fake"

    def fake_post(url, payload, timeout=zbatch.TIMEOUT):
        posted.append(payload)
        if payload["name"] == "BOOM":
            raise OSError("连不上")
        return {"job_id": f"j{len(posted)}", "status": "running", "tasks": len(payload["tasks"])}

    zbatch._post = fake_post
    r = zbatch.submit(["一"], name="默认")
    cwd = posted[-1]["cwd"]
    check(os.path.basename(cwd).startswith("zbatch_") and os.path.realpath(cwd).startswith(tmp_root),
          "默认 cwd 是这一批的临时目录", cwd)
    check(os.path.isdir(cwd) and os.listdir(cwd) == [], "提交后目录在、是空的（任务还要用）")
    zbatch.status = lambda job_id, full=False: {"id": job_id, "status": "done"}
    zbatch.wait(r["job_id"], timeout=1, every=0)
    check(not os.path.exists(cwd), "wait 看到跑完就删")
    check(raises(zbatch.submit, ["x"], name="BOOM", exc=OSError), "提交失败照样报错")
    check(not os.path.exists(posted[-1]["cwd"]), "提交失败也删临时目录")
    old = Path(tempfile.mkdtemp(prefix=zbatch.WORKDIR_PREFIX))
    os.utime(old, (time.time() - zbatch.WORKDIR_TTL - 60,) * 2)
    fresh = Path(tempfile.mkdtemp(prefix=zbatch.WORKDIR_PREFIX))
    zbatch.submit(["x"], name="清理")
    check(not old.exists() and fresh.exists(), "下次提交清掉过期的，不动新的")
    for d in [fresh, Path(posted[-1]["cwd"])]:
        d.rmdir()
    n = len(posted)
    for bad in ["~", "/", str(HOME), "/home/ysc"]:
        check(raises(zbatch.submit, ["x"], cwd=bad), f"cwd={bad!r} 拒绝")
    check(len(posted) == n, "拒绝时没提交")
    zbatch.submit(["x"], cwd=str(ROOT))
    check(posted[-1]["cwd"] == str(ROOT), "允许项目目录")

    print("cbatch.submit（claude）")
    for bad in ["/", str(HOME)]:
        msg = raises(cbatch.submit, ["x"], cwd=bad, exc=cbatch.CBatchError)
        check(msg and "cwd" in msg, f"cwd={bad!r} 拒绝", msg)
    here = os.getcwd()
    os.chdir(HOME)
    try:
        check(raises(cbatch.submit, ["x"], exc=cbatch.CBatchError),
              "不传 cwd、当前目录是家目录时也拒绝")
    finally:
        os.chdir(here)
    check(not (TMP / "jobs").exists() or not any((TMP / "jobs").iterdir()), "拒绝时没建任务")

    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
