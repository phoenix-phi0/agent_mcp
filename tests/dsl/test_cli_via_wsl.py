# -*- coding: utf-8 -*-
"""Windows 上经 WSL 调 claude / zcode（llm_router 的 cli_via_wsl）。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_cli_via_wsl.py

在 Linux 上测：替换 llm_router.is_windows 假装是 Windows；临时目录里放一个
假的 wsl.exe（DSL_WSL_EXE 指过去），它记下收到的参数和标准输入，然后像真
wsl.exe 一样把 --exec 后面的命令跑起来（真的 bash -lc 那段脚本），HOME 换成
一个假的「WSL 家目录」，里面 ~/.local/bin 放假 claude / zcode。假程序记下
参数、标准输入、cwd，输出跟真的同格式的 JSON。

假家目录的 .profile 往 stdout 打一行噪声：真 WSL 的登录 shell 也可能这样，
得被丢掉。配置用临时的 config.json（ZHIPU_CONFIG 指过去），不读真配置。
"""

import base64
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="cli_via_wsl_"))
LOG = TMP / "calls"
LOG.mkdir()
WSL_LOG = TMP / "wsl_calls"
WSL_LOG.mkdir()
HOME = TMP / "wsl_home"
(HOME / ".local" / "bin").mkdir(parents=True)
(HOME / ".profile").write_text("echo profile-noise-on-stdout\n", encoding="utf-8")
CFG = TMP / "config.json"


def write_cfg(**kw):
    CFG.write_text(json.dumps({"api_key": "test-not-real",
                               "model": "glm-default", **kw},
                              ensure_ascii=False), encoding="utf-8")


write_cfg()
os.environ["ZHIPU_CONFIG"] = str(CFG)
os.environ["ZHIPU_MODELS"] = str(TMP / "no_models.json")
for k in ("ZHIPU_MODEL", "ZHIPU_API_KEY", "ZHIPU_BASE_URL",
          "DSL_CLAUDE_MAX_PROCS", "DSL_ZCODE_MAX_PROCS",
          "DSL_CLAUDE_TIMEOUT", "DSL_ZCODE_TIMEOUT", "DSL_CLI_VIA_WSL",
          "DSL_WSL_DISTRO", "DSL_WSL_CLAUDE_BIN", "DSL_WSL_ZCODE_BIN"):
    os.environ.pop(k, None)

FAKE = r'''#!{py}
import json, os, sys, time, uuid
kind = {kind!r}
t0 = time.time()
args = sys.argv[1:]
stdin = sys.stdin.read()
if os.environ.get("FAKE_SLEEP"):
    time.sleep(float(os.environ["FAKE_SLEEP"]))
rec = {{"kind": kind, "args": args, "cwd": os.getcwd(),
       "cwd_files": sorted(os.listdir(".")), "stdin": stdin,
       "has_api_key": "ANTHROPIC_API_KEY" in os.environ,
       "start": t0}}
with open(os.path.join({log!r}, uuid.uuid4().hex + ".json"), "w") as f:
    json.dump(rec, f, ensure_ascii=False)
if os.environ.get("FAKE_EXIT"):
    sys.stderr.write("第一行错误\n第二行错误\n")
    sys.exit(int(os.environ["FAKE_EXIT"]))
model = args[args.index("--model") + 1] if "--model" in args else ""
if os.environ.get("FAKE_ECHO"):
    reply = stdin if kind.endswith("claude") else args[args.index("-p") + 1]
else:
    reply = kind + "[" + model + "]"
if kind.endswith("claude"):
    print(json.dumps({{"type": "result", "subtype": "success",
                      "is_error": bool(os.environ.get("FAKE_IS_ERROR")),
                      "result": reply}}, ensure_ascii=False))
else:
    print(json.dumps({{"ok": True, "result": reply}}, ensure_ascii=False))
'''

# 假 wsl.exe：记下参数和标准输入，再把 --exec 后面的命令跑起来
FAKE_WSL = r'''#!{py}
import json, os, subprocess, sys, time, uuid
argv = sys.argv[1:]
data = sys.stdin.buffer.read()
with open(os.path.join({log!r}, uuid.uuid4().hex + ".json"), "w") as f:
    json.dump({{"argv": argv, "stdin": data.decode("latin-1"),
               "start": time.time()}}, f, ensure_ascii=False)
if os.environ.get("FAKE_WSL_HANG"):
    time.sleep(float(os.environ["FAKE_WSL_HANG"]))
    sys.exit(0)
if os.environ.get("FAKE_WSL_FAIL"):
    # 真 wsl.exe 自己的报错是 UTF-16LE
    sys.stderr.buffer.write("没有具有所提供名称的分发。".encode("utf-16-le"))
    sys.exit(4294967295 & 0xFF)
i, cd, rest = 0, None, None
while i < len(argv):
    a = argv[i]
    if a in ("-d", "--distribution", "-u", "--user"):
        i += 2
    elif a == "--cd":
        cd = argv[i + 1]
        i += 2
    elif a == "--exec":
        rest = argv[i + 1:]
        break
    else:
        sys.stderr.write("fake wsl: unexpected arg " + a + "\n")
        sys.exit(2)
home = {home!r}
env = {{k: v for k, v in os.environ.items() if k != "BASH_ENV"}}
env["HOME"] = home
cwd = home if cd == "~" else cd
p = subprocess.run(rest, input=data, cwd=cwd, env=env)
sys.exit(p.returncode)
'''


def make(path: Path, text: str):
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


for kind in ("claude", "zcode"):
    make(HOME / ".local" / "bin" / kind,
         FAKE.format(py=sys.executable, kind="wsl-" + kind, log=str(LOG)))
    make(TMP / f"local_{kind}",
         FAKE.format(py=sys.executable, kind="local-" + kind, log=str(LOG)))
make(TMP / "wsl.exe", FAKE_WSL.format(py=sys.executable, log=str(WSL_LOG),
                                      home=str(HOME)))
os.environ["DSL_WSL_EXE"] = str(TMP / "wsl.exe")
MISSING = str(TMP / "not_installed")
# 假的值，只看它有没有被传给 WSL 里的程序
os.environ["ANTHROPIC_API_KEY"] = "fake-for-test"

from tools import config, DSLEngine, MockClient, llm_router  # noqa: E402
from tools.llm_router import BackendError  # noqa: E402

config.load(reload=True)
REAL_IS_WINDOWS = llm_router.is_windows
CLAUDE = llm_router._BACKENDS["claude"]
ZCODE = llm_router._BACKENDS["zcode"]

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def take(d: Path):
    out = []
    for f in d.glob("*.json"):
        out.append(json.loads(f.read_text(encoding="utf-8")))
        f.unlink()
    return sorted(out, key=lambda r: r["start"])


def calls():
    return take(LOG)


def wsl_calls():
    return take(WSL_LOG)


def opt(rec, name):
    a = rec["args"]
    return a[a.index(name) + 1] if name in a else None


def windows(on: bool):
    llm_router.is_windows = (lambda: True) if on else REAL_IS_WINDOWS


def local(claude=True, zcode=True):
    """本机有没有 claude / zcode。"""
    os.environ["CBATCH_CLAUDE"] = str(TMP / "local_claude") if claude else MISSING
    os.environ["ZCODE_BIN"] = str(TMP / "local_zcode") if zcode else MISSING


def env(**kw):
    for k in ("FAKE_ECHO", "FAKE_IS_ERROR", "FAKE_EXIT", "FAKE_SLEEP",
              "FAKE_WSL_HANG", "FAKE_WSL_FAIL", "DSL_CLI_VIA_WSL",
              "DSL_CLAUDE_TIMEOUT", "DSL_WSL_DISTRO", "DSL_WSL_CLAUDE_BIN"):
        os.environ.pop(k, None)
    for k, v in kw.items():
        os.environ[k] = str(v)


def err(fn):
    try:
        fn()
        return ""
    except Exception as ex:  # noqa: BLE001
        return f"{type(ex).__name__}: {ex}"


def main():
    env()
    print("零、对照：Linux 上 auto 不走 WSL，行为不变")
    windows(False)
    local()
    r = CLAUDE.chat("你好", model="haiku")
    rs, ws = calls(), wsl_calls()
    check(r == "local-claude[haiku]" and not ws, f"本机 claude：{r!r}，wsl.exe 没被调")
    check(rs and rs[0]["args"][:2] == ["-p", "你好"], "本机照旧把提示词放在 -p 后面")
    env(DSL_CLI_VIA_WSL="true")
    r = CLAUDE.chat("你好")
    check(r == "local-claude[]" and not wsl_calls(),
          f"Linux 上 cli_via_wsl=true 也不走 WSL：{r!r}")
    calls()
    env()
    local(claude=False)
    e = err(lambda: CLAUDE.chat("你好"))
    check("找不到 claude" in e and not wsl_calls(), f"Linux 上找不到照旧报原来的错：{e[:60]}")

    print("\n一、Windows + 本机没有 → 走 WSL")
    windows(True)
    local(claude=False, zcode=False)
    r = CLAUDE.chat("你好", model="haiku")
    rs, ws = calls(), wsl_calls()
    check(r == "wsl-claude[haiku]", f"经 WSL 的 claude 回复：{r!r}（.profile 的噪声被丢掉）")
    check(len(ws) == 1, f"wsl.exe 调了一次：{len(ws)}")
    argv = ws[0]["argv"] if ws else []
    check(argv[:5] == ["--cd", "~", "--exec", "bash", "-lc"],
          f"wsl.exe 参数：{argv[:5]}")
    check(all("你好" not in a for a in argv) and "-d" not in argv,
          "提示词不在 wsl.exe 命令行上；没设发行版就不带 -d")
    check(argv and argv[5] == llm_router._WSL_SCRIPT and "\\" not in argv[5]
          and argv[5].isascii(), "命令行上只有固定的脚本（纯 ASCII、无反斜杠）")
    rec = rs[0] if rs else {}
    check(rec.get("kind") == "wsl-claude" and rec.get("stdin") == "你好"
          and rec["args"][0] == "-p" and "你好" not in rec["args"],
          "WSL 里 claude 从标准输入读到提示词，-p 后面不带提示词")
    check(rec.get("args", [])[1:7] == ["--output-format", "json", "--tools", "",
                                       "--strict-mcp-config", "--system-prompt"],
          f"纯问答参数照旧：{rec.get('args', [])[1:7]}")
    check(opt(rec, "--model") == "haiku", "模型参数传过去")
    check(not rec.get("has_api_key"), "WSL 侧 unset 了 ANTHROPIC_API_KEY")
    cwd = rec.get("cwd", "")
    check(Path(cwd).name.startswith("dsl_wsl_") and rec.get("cwd_files") == [".in"]
          and not Path(cwd).exists(),
          f"在 mktemp -d 的空目录里跑、跑完删了：{cwd}")
    r = CLAUDE.chat("你好")
    rs = calls()
    wsl_calls()
    check(r == "wsl-claude[]" and rs and "--model" not in rs[0]["args"],
          "不写模型就不带 --model")

    env(DSL_WSL_DISTRO="Ubuntu-26.04")
    CLAUDE.chat("你好")
    ws = wsl_calls()
    calls()
    check(ws and ws[0]["argv"][:2] == ["-d", "Ubuntu-26.04"], "wsl_distro → -d 发行版")
    env()
    write_cfg(wsl_distro="Cfg-Distro")
    config.load(reload=True)
    CLAUDE.chat("你好")
    ws = wsl_calls()
    calls()
    check(ws and ws[0]["argv"][:2] == ["-d", "Cfg-Distro"], "config.json 的 wsl_distro 也认")
    write_cfg()
    config.load(reload=True)

    print("\n二、Windows + 本机有：auto 用本机，true 强制 WSL")
    local()
    r = CLAUDE.chat("你好")
    check(r == "local-claude[]" and not wsl_calls(), f"auto 用本机：{r!r}")
    calls()
    env(DSL_CLI_VIA_WSL="true")
    r = CLAUDE.chat("你好")
    check(r == "wsl-claude[]" and len(wsl_calls()) == 1, f"环境变量 true 强制 WSL：{r!r}")
    calls()
    env()
    write_cfg(cli_via_wsl=True)
    config.load(reload=True)
    r = CLAUDE.chat("你好")
    check(r == "wsl-claude[]", f"config.json 的 cli_via_wsl: true 也认：{r!r}")
    env(DSL_CLI_VIA_WSL="false")
    r = CLAUDE.chat("你好")
    check(r == "local-claude[]", f"环境变量 false 优先于 config.json 的 true：{r!r}")
    calls()
    wsl_calls()
    write_cfg()
    config.load(reload=True)

    print("\n三、false：找不到报原来的错")
    env(DSL_CLI_VIA_WSL="false")
    local(claude=False, zcode=False)
    e = err(lambda: CLAUDE.chat("你好"))
    check("找不到 claude" in e and not wsl_calls(), f"claude：{e[:60]}")
    e = err(lambda: ZCODE.chat("你好"))
    check("找不到 zcode" in e and not wsl_calls(), f"zcode：{e[:60]}")
    env()

    print("\n四、刁钻提示词原样到达")
    nasty = [
        "中文，日本語のテキスト、カタカナ",
        "第一行\n第二行\r\n第三行\n\n",
        "\"双引号\" '单引号' “中文引号” 「かぎ」",
        "$HOME ${PATH} $(whoami) `id` \\ \\\\ \\\"",
        "%PATH% %% ^ ^^ & && | || < > ; ! !! #",
        "-p --model opus",
        "",
        "  前后空格  ",
        "末尾换行\n",
        "長" * 7000,  # 20KB 左右（UTF-8）
    ]
    for s in nasty:
        env(FAKE_ECHO=1)
        r = CLAUDE.chat(s)
        rs = calls()
        wsl_calls()
        tag = repr(s[:24]) + (f"…（{len(s.encode())} 字节）" if len(s) > 24 else "")
        check(rs and rs[0]["stdin"] == s and r == s, f"提示词 {tag}")
    sysp = "系统：\"引号\" $x `y` %z% ^ & 換行\n第二行\n"
    env(FAKE_ECHO=1)
    CLAUDE.chat("你好", system=sysp)
    rs = calls()
    wsl_calls()
    check(rs and opt(rs[0], "--system-prompt") == sysp, "系统提示词原样到达")
    CLAUDE.chat("你好")
    rs = calls()
    wsl_calls()
    check(rs and opt(rs[0], "--system-prompt") == llm_router.DEFAULT_SYSTEM,
          "没给系统提示词时用默认的那句")

    print("\n五、zcode 经 WSL")
    env()
    nz = "zcode 提示词 \"引号\" $HOME `x` %P% ^ & 日本語\n第二行"
    r = ZCODE.chat(nz, system="系统")
    rs = calls()
    ws = wsl_calls()
    check(r == "wsl-zcode[]" and len(ws) == 1, f"走 WSL：{r!r}")
    rec = rs[0] if rs else {"args": []}
    check(opt(rec, "-p") == "系统\n\n" + nz, "提示词（拼上系统提示词）原样进 argv")
    check("--disallowedTools" in rec["args"] and "--json" in rec["args"]
          and rec["args"][:2] == ["--mode", "build"], "zcode 纯问答参数照旧")
    check(rec.get("stdin") == "", "zcode 的标准输入是空的")
    env(FAKE_EXIT=5)
    e = err(lambda: ZCODE.chat("你好"))
    calls()
    wsl_calls()
    check("zcode（经 WSL）" in e and "退出码 5" in e, f"zcode 退出码非 0：{e[:60]}")

    print("\n六、出错")
    env(FAKE_IS_ERROR=1)
    e = err(lambda: CLAUDE.chat("你好"))
    calls()
    wsl_calls()
    check("BackendError" in e and "经 WSL" in e and "报错" in e, f"is_error：{e[:60]}")
    env(FAKE_EXIT=3)
    e = err(lambda: CLAUDE.chat("你好"))
    calls()
    wsl_calls()
    check("经 WSL" in e and "退出码 3" in e and "第一行错误" in e, f"退出码 3：{e[:80]!r}")
    env(DSL_WSL_CLAUDE_BIN="/no/such/claude")
    e = err(lambda: CLAUDE.chat("你好"))
    calls()
    wsl_calls()
    check("WSL 里找不到 claude" in e, f"WSL 里也没有：{e[:70]}")
    env(FAKE_WSL_FAIL=1)
    e = err(lambda: CLAUDE.chat("你好"))
    wsl_calls()
    check("wsl.exe 退出码" in e and "没有具有所提供名称的分发" in e,
          f"wsl.exe 自己报错（UTF-16）能读：{e[:70]}")
    env()
    os.environ["DSL_WSL_EXE"] = str(TMP / "no_wsl.exe")
    e = err(lambda: CLAUDE.chat("你好"))
    os.environ["DSL_WSL_EXE"] = str(TMP / "wsl.exe")
    check("找不到 wsl.exe" in e, f"没有 wsl.exe：{e[:60]}")
    env(DSL_WSL_CLAUDE_BIN="claude")
    r = CLAUDE.chat("你好")
    calls()
    wsl_calls()
    check(r == "wsl-claude[]", f"wsl_claude_bin 写名字也行（PATH 前面加了 ~/.local/bin）：{r!r}")

    print("\n七、超时")
    env(DSL_CLAUDE_TIMEOUT=1, FAKE_SLEEP=20)
    t0 = time.time()
    e = err(lambda: CLAUDE.chat("你好"))
    dt = time.time() - t0
    calls()
    wsl_calls()
    check("超过 1 秒" in e and "WSL 侧已杀掉" in e and dt < 10,
          f"WSL 侧 timeout 生效：{dt:.1f}s，{e[:60]}")
    env(DSL_CLAUDE_TIMEOUT=1, FAKE_WSL_HANG=30)
    grace = llm_router.WSL_GRACE
    llm_router.WSL_GRACE = 1
    t0 = time.time()
    e = err(lambda: CLAUDE.chat("你好"))
    dt = time.time() - t0
    llm_router.WSL_GRACE = grace
    wsl_calls()
    check("已杀掉 wsl.exe" in e and dt < 6, f"wsl.exe 卡住时这边杀掉它：{dt:.1f}s，{e[:50]}")
    env()

    print("\n八、python -m tools.config 的说明")
    d = CLAUDE.describe()
    check(d.startswith("经 WSL") and "command -v claude" in d, f"claude：{d[:50]}")
    windows(False)
    local()
    check(CLAUDE.describe().startswith("本机 "), f"Linux：{CLAUDE.describe()[:50]}")
    windows(True)
    local(claude=False, zcode=False)

    print("\n九、DSL 引擎：问 … 用 cli:claude/haiku")
    mock = MockClient()
    e = DSLEngine(mock, workdir=TMP, verbose=False)
    e.run("问 答 = 只回复：好 用 cli:claude/haiku")
    rs = calls()
    wsl_calls()
    check(e.vars.get("答") == "wsl-claude[haiku]" and not mock.calls,
          f"引擎经 WSL：{e.vars.get('答')!r}")
    check(rs and rs[0]["stdin"] == "只回复：好", "提示词经标准输入到达")

    windows(False)
    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
