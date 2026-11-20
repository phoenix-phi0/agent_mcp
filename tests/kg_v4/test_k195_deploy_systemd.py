#!/usr/bin/env python3
"""K195：deploy.sh 的 systemd 模式（打包模板 scripts/build_bundle.sh 里的 deploy.sh；本机正式服务的
kg_v4_run/deploy.sh 存在时一并测）。

不碰真的 systemd：PATH 前面放假的 systemctl / journalctl（状态记在临时目录），假服务是监听随机端口的
<当前解释器> -m http.server（GET / 200）。覆盖：
  1 pid 模式（没设 KG_SYSTEMD_UNIT）：新旧脚本在同样的夹具上 --dry-run 和真跑，输出（去掉数字和临时路径后）逐行一致
  2 pid 模式自动探测：端口被假 unit 的 MainPID 占着、server.pid 不存在 → 退出码 2、提示设变量、不停服不备份
  3 systemd 模式 --dry-run：认出 unit/MainPID，不调 stop/start，不备份
  4 systemd 模式真跑：systemctl stop → 备份 → 同步 → systemctl start → MainPID 换新且就是监听进程、GET / 200；
    不建 server.pid、不起看门狗
  5 systemd 模式同步失败：从备份还原约定目录、拉回服务，退出码 1
  6 systemd 模式新版本没就绪：停 unit、从备份还原、再拉起，退出码 1
  7 systemd 模式端口被别的进程占着 / unit 不存在 / 看门狗在跑：未停服就退出
用法：python tests/kg_v4/test_k195_deploy_systemd.py
"""
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_COMMIT = "2391527"   # K195 之前的 build_bundle.sh（pid 模式逐行对照的基线）
LOCAL_DEPLOY = Path(os.environ.get("KG_LOCAL_DEPLOY", "/workspace/dslagent_exp/kg_v4_run/deploy.sh"))
LOCAL_BASE = Path(str(LOCAL_DEPLOY) + ".bak-K195")
UNIT = "fake-kg.service"
DIRS = "contracts entities queries routes scripts services ui setup i18n".split()

ok = fail = 0


def check(name, cond, info=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name} {info}")


FAKE_SYSTEMCTL = r'''#!/usr/bin/env bash
# 假 systemctl：只认 $FAKE_UNIT；服务 = $FAKE_PY -m http.server $FAKE_PORT。调用记在 $FAKE_SD/calls
S=$FAKE_SD; U=$FAKE_UNIT
alive(){ local p; p=$(cat "$S/main.pid" 2>/dev/null); [ -n "$p" ] && kill -0 "$p" 2>/dev/null; }
cmd=$1; shift
case $cmd in
  show)
    prop=; unit=
    while [ $# -gt 0 ]; do case $1 in -p) prop=$2; shift 2;; --value) shift;; *) unit=$1; shift;; esac; done
    if [ "$unit" != "$U" ]; then [ "$prop" = LoadState ] && echo not-found || echo 0; exit 0; fi
    case $prop in
      LoadState) echo loaded;;
      MainPID) if alive; then cat "$S/main.pid"; else echo 0; fi;;
    esac;;
  is-active) [ "$1" = "$U" ] && alive && { echo active; exit 0; }; echo inactive; exit 3;;
  status)
    p=$(cat "$S/main.pid" 2>/dev/null)
    if [ "$1" = "$p" ] && alive; then echo "● $U - fake kg"; echo "     Loaded: loaded"; exit 0; fi
    echo "Failed to get unit for PID $1"; exit 4;;
  stop)
    echo stop >> "$S/calls"
    if alive; then p=$(cat "$S/main.pid"); kill -TERM "$p"; for i in $(seq 1 40); do kill -0 "$p" 2>/dev/null || break; sleep 0.1; done; fi
    rm -f "$S/main.pid";;
  start)
    echo start >> "$S/calls"
    alive && exit 0
    if [ -e "$S/broken_once" ]; then rm -f "$S/broken_once"
      setsid sleep 300 > /dev/null 2>&1 < /dev/null & echo $! > "$S/main.pid"   # 起来了但不监听
    else
      setsid "$FAKE_PY" -m http.server "$FAKE_PORT" --bind 127.0.0.1 --directory "$S/www" > /dev/null 2>&1 < /dev/null &
      echo $! > "$S/main.pid"
    fi;;
  *) echo "fake systemctl: 不支持 $cmd" >&2; exit 1;;
esac
'''

FAKE_JOURNALCTL = '#!/usr/bin/env bash\necho "fake journal: app.db 已存在"\n'

# pid 模式的假 start/stop/watch（新旧脚本共用，所以对照公平）
FAKE_START = r'''#!/usr/bin/env bash
RUN=$FAKE_RUN
mkdir -p "$RUN"
p=$(cat "$RUN/server.pid" 2>/dev/null); [ -n "$p" ] && kill -0 "$p" 2>/dev/null && exit 0
setsid "$FAKE_PY" -m http.server "$FAKE_PORT" --bind 127.0.0.1 --directory "$FAKE_SD/www" >> "$RUN/server.log" 2>&1 < /dev/null 8>&- 9>&- &
echo $! > "$RUN/server.pid"
'''
FAKE_STOP = r'''#!/usr/bin/env bash
RUN=$FAKE_RUN
p=$(cat "$RUN/server.pid" 2>/dev/null)
[[ $p =~ ^[0-9]+$ ]] || { echo "没有有效 PID 文件"; exit 0; }
kill -0 "$p" 2>/dev/null || { echo "进程 $p 已不在"; rm -f "$RUN/server.pid"; exit 0; }
kill -TERM -- "-$p" 2>/dev/null || kill -TERM "$p"
for i in $(seq 1 40); do kill -0 "$p" 2>/dev/null || { echo "已停止 $p"; rm -f "$RUN/server.pid"; exit 0; }; sleep 0.1; done
echo "仍未退出 $p"; exit 1
'''
FAKE_WATCH = r'''#!/usr/bin/env bash
RUN=$FAKE_RUN
exec 8>"$RUN/watch.lock"; flock -n 8 || exit 0
while :; do sleep 1; done
'''


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def write_exec(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def holders_of(lock):
    """握着 lock 文件的进程（按 /proc/*/fd 找，不用 pgrep）。"""
    lock = os.path.realpath(lock)
    out = set()
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            for fd in (d / "fd").iterdir():
                if os.path.realpath(fd) == lock:
                    out.add(int(d.name))
                    break
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            continue
    return out


def kill_pid(p, group=False):
    try:
        if group:
            os.killpg(p, signal.SIGTERM)
        else:
            os.kill(p, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def port_pid(port):
    r = subprocess.run(["ss", "-ltnp", f"sport = :{port}"], capture_output=True, text=True)
    m = re.search(r"pid=(\d+)", r.stdout)
    return int(m.group(1)) if m else None


def http_code(port):
    r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"http://127.0.0.1:{port}/"],
                       capture_output=True, text=True)
    return r.stdout


class Fixture:
    """一套隔离环境：数据目录、新版源、运行目录、备份目录、假 systemd 状态。"""

    def __init__(self, flavor, script_text):
        self.flavor = flavor          # bundle | local
        self.root = Path(tempfile.mkdtemp(prefix=f"k195_{flavor}_"))
        self.port = free_port()
        self.sd = self.root / "sd"
        (self.sd / "www").mkdir(parents=True)
        (self.sd / "www" / "index.html").write_text("ok", encoding="utf-8")
        self.bin = self.root / "bin"
        write_exec(self.bin / "systemctl", FAKE_SYSTEMCTL)
        write_exec(self.bin / "journalctl", FAKE_JOURNALCTL)
        self.data = self.root / "data"
        self.backups = self.root / "backups"
        for d in DIRS:
            (self.data / d).mkdir(parents=True)
            (self.data / d / "a.txt").write_text(f"old {d}\n", encoding="utf-8")
        (self.data / "plan").mkdir()
        (self.data / "plan" / "top.zs").write_text("old top\n", encoding="utf-8")
        (self.data / "app.db").write_bytes(b"db-bytes")
        (self.data / "extra_only_in_data.txt").write_text("keep", encoding="utf-8")
        if flavor == "bundle":
            self.here = self.root / "bundle"
            self.run_dir = self.here / "run"
            scripts = self.here / "scripts"
            write_exec(scripts / "deploy.sh", script_text)
            write_exec(scripts / "start.sh", FAKE_START)
            write_exec(scripts / "stop.sh", FAKE_STOP)
            write_exec(scripts / "watch.sh", FAKE_WATCH)
            write_exec(self.here / ".venv" / "bin" / "python", "#!/bin/sh\nexit 0\n")
            self.src = self.root / "newproj"
            for d in DIRS:
                (self.src / d).mkdir(parents=True)
                (self.src / d / "a.txt").write_text(f"new {d}\n", encoding="utf-8")
            (self.src / "plan").mkdir()
            (self.src / "plan" / "top.zs").write_text("new top\n", encoding="utf-8")
            self.target = str(self.src)
            self.deploy = scripts / "deploy.sh"
        else:
            self.run_dir = self.root / "run"
            write_exec(self.run_dir / "deploy.sh", script_text)
            write_exec(self.run_dir / "start.sh", FAKE_START)
            write_exec(self.run_dir / "stop.sh", FAKE_STOP)
            write_exec(self.run_dir / "watch.sh", FAKE_WATCH)
            self.repo = self.root / "repo"
            k = self.repo / "kg_v4"
            for d in DIRS:
                (k / d).mkdir(parents=True)
                (k / d / "a.txt").write_text(f"new {d}\n", encoding="utf-8")
            (k / "plan").mkdir()
            (k / "plan" / "top.zs").write_text("new top\n", encoding="utf-8")
            g = ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t"]
            subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
            subprocess.run(g + ["add", "-A"], check=True)
            subprocess.run(g + ["commit", "-qm", "fixture"], check=True)
            self.target = subprocess.run(g + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
            self.deploy = self.run_dir / "deploy.sh"
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def env(self, unit=None):
        e = dict(os.environ)
        e.pop("KG_SYSTEMD_UNIT", None)
        e.update(PATH=f"{self.bin}:{e['PATH']}", FAKE_SD=str(self.sd), FAKE_UNIT=UNIT,
                 FAKE_PORT=str(self.port), FAKE_RUN=str(self.run_dir), FAKE_PY=sys.executable)
        if self.flavor == "bundle":
            e.update(DATA_DIR=str(self.data), RUN_DIR=str(self.run_dir), PORT=str(self.port), BACKUPS=str(self.backups))
        else:
            e.update(KG_RUN_DIR=str(self.run_dir), KG_DATA=str(self.data), KG_PORT=str(self.port),
                     KG_BACKUPS=str(self.backups), KG_REPO=str(self.repo))
        if unit:
            e["KG_SYSTEMD_UNIT"] = unit
            e["KG_READY_TRIES"] = "20"   # 等就绪 10 秒（默认 120 秒），只影响 systemd 模式
        return e

    def deploy_run(self, *args, unit=None, timeout=200):
        r = subprocess.run(["bash", str(self.deploy), *args, self.target, "T1"], env=self.env(unit),
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr

    def systemctl(self, *args):
        return subprocess.run(["systemctl", *args], env=self.env(), capture_output=True, text=True)

    def calls(self):
        f = self.sd / "calls"
        return f.read_text().split() if f.exists() else []

    def main_pid(self):
        out = self.systemctl("show", "-p", "MainPID", "--value", UNIT).stdout.strip()
        return int(out or 0)

    def wait_listen(self, secs=10):
        for _ in range(int(secs * 10)):
            if port_pid(self.port) and http_code(self.port) == "200":
                return True
            time.sleep(0.1)
        return False

    def pid_mode_start(self):
        subprocess.run(["bash", str(self.deploy.parent / "start.sh")], env=self.env(), check=True)
        subprocess.run(["setsid", "-f", "bash", str(self.deploy.parent / "watch.sh")], env=self.env(),
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        assert self.wait_listen(), "假服务没起来"
        for _ in range(30):
            if holders_of(self.run_dir / "watch.lock"):
                break
            time.sleep(0.1)

    def backups_list(self):
        return sorted(p.name for p in self.backups.iterdir() if p.is_dir()) if self.backups.exists() else []

    def data_text(self, d):
        p = self.data / d / "a.txt"
        return p.read_text() if p.is_file() else None

    def cleanup(self):
        self.systemctl("stop", UNIT)
        lock = self.run_dir / "watch.lock"
        if lock.exists():
            for p in holders_of(lock):
                try:
                    kill_pid(os.getpgid(p), group=True)
                except ProcessLookupError:
                    pass
        try:
            p = int((self.run_dir / "server.pid").read_text())
            kill_pid(p, group=True)
        except (FileNotFoundError, ValueError):
            pass
        time.sleep(0.3)
        shutil.rmtree(self.root, ignore_errors=True)


def normalize(text, fx):
    text = text.replace(str(fx.root), "<ROOT>")
    if fx.flavor == "local":   # 每个夹具自建 git 仓库，提交号不同
        text = text.replace(fx.target[:7], "<C>")
    text = re.sub(r"/tmp/kg_v4_deploy_\w+", "<TMP>", text)
    text = re.sub(r"\d+", "N", text)
    return text


def extract_template(src):
    m = re.search(r"cat > \"\$OUT/scripts/deploy\.sh\" <<'XEOF_DEPLOY'\n(.*?)\nXEOF_DEPLOY\n", src, re.S)
    assert m, "build_bundle.sh 里没找到 deploy.sh 模板"
    return m.group(1) + "\n"


def suite(flavor, new_text, old_text):
    print(f"== {flavor}：pid 模式新旧对照（--dry-run + 真跑）")

    def pid_run(text):
        fx = Fixture(flavor, text)
        try:
            fx.pid_mode_start()
            rc1, o1 = fx.deploy_run("--dry-run")
            rc2, o2 = fx.deploy_run()
            ready = fx.wait_listen() and port_pid(fx.port) == int((fx.run_dir / "server.pid").read_text())
            return (rc1, normalize(o1, fx), rc2, normalize(o2, fx), ready,
                    fx.data_text("services"), len(fx.backups_list()), bool(holders_of(fx.run_dir / "watch.lock")))
        finally:
            fx.cleanup()

    # pid 模式起看门狗后只等 3 秒看 watch.lock 被占（原脚本就这样，K195 没动）；机器忙（如 run_all 并发）时偶尔
    # 来不及，新旧脚本都会报「看门狗没起来」。这是原有的时序问题，碰上就整对重跑，最多 3 次
    for attempt in range(3):
        outs = {tag: pid_run(text) for tag, text in (("old", old_text), ("new", new_text))}
        if not any("看门狗没起来" in v[3] for v in outs.values()):
            break
        print(f"    （第 {attempt + 1} 次碰上原有的看门狗 3 秒时序，整对重跑）")
    o, n = outs["old"], outs["new"]
    check("旧脚本 pid 模式真跑成功（夹具有效）", o[0] == 0 and o[2] == 0 and o[4], f"{o[0]} {o[2]}\n{o[3]}")
    check("pid 模式 --dry-run 输出与旧脚本一致", (o[0], o[1]) == (n[0], n[1]), f"\n--旧--\n{o[1]}\n--新--\n{n[1]}")
    check("pid 模式真跑输出与旧脚本一致", (o[2], o[3]) == (n[2], n[3]), f"\n--旧--\n{o[3]}\n--新--\n{n[3]}")
    check("pid 模式结果一致（server.pid 就绪、同步、1 份备份、看门狗在跑）", o[4:] == n[4:] == (True, "new services\n", 1, True), f"{o[4:]} {n[4:]}")

    print(f"== {flavor}：pid 模式自动探测 systemd 托管")
    fx = Fixture(flavor, new_text)
    try:
        fx.systemctl("start", UNIT)
        fx.wait_listen()
        mp = fx.main_pid()
        for args in (("--dry-run",), ()):
            rc, out = fx.deploy_run(*args)
            check(f"{' '.join(args) or '真跑'}：退出码 2 并提示设 KG_SYSTEMD_UNIT={UNIT}",
                  rc == 2 and f"KG_SYSTEMD_UNIT={UNIT}" in out, f"rc={rc}\n{out}")
        check("没停服（只有最初那次 start）、MainPID 不变、没备份、没同步",
              fx.calls() == ["start"] and fx.main_pid() == mp and not fx.backups_list() and fx.data_text("services") == "old services\n",
              f"{fx.calls()} {fx.backups_list()}")
    finally:
        fx.cleanup()

    print(f"== {flavor}：systemd 模式 --dry-run 与真跑")
    fx = Fixture(flavor, new_text)
    try:
        fx.systemctl("start", UNIT)
        fx.wait_listen()
        mp = fx.main_pid()
        rc, out = fx.deploy_run("--dry-run", unit=UNIT)
        check("--dry-run 退出码 0，认出 unit 和 MainPID", rc == 0 and f"unit {UNIT}（active），MainPID {mp}" in out, f"rc={rc}\n{out}")
        check("--dry-run 不停起服、不备份、不同步",
              fx.calls() == ["start"] and not fx.backups_list() and fx.data_text("services") == "old services\n", f"{fx.calls()}")
        rc, out = fx.deploy_run(unit=UNIT)
        np_ = fx.main_pid()
        check("真跑退出码 0，GET / 200", rc == 0 and "GET / 200" in out, f"rc={rc}\n{out}")
        check("调用顺序 start(夹具) → stop → start", fx.calls() == ["start", "stop", "start"], f"{fx.calls()}")
        check("新 MainPID 换了、就是监听进程、GET / 200",
              np_ not in (0, mp) and port_pid(fx.port) == np_ and http_code(fx.port) == "200", f"{mp} {np_} {port_pid(fx.port)}")
        bks = fx.backups_list()
        check("备份 1 份且是旧内容；同步后是新内容；数据目录多出的文件保留",
              len(bks) == 1 and (fx.backups / bks[0] / "services" / "a.txt").read_text() == "old services\n"
              and fx.data_text("services") == "new services\n" and (fx.data / "plan" / "top.zs").read_text() == "new top\n"
              and (fx.data / "extra_only_in_data.txt").exists(), f"{bks}")
        lock = fx.run_dir / "watch.lock"
        check("不建 server.pid、不起看门狗",
              not (fx.run_dir / "server.pid").exists() and not (lock.exists() and holders_of(lock)), "")
        check("启动日志取自 journalctl", "Traceback 0" in out and "不起看门狗" in out, out)
    finally:
        fx.cleanup()

    print(f"== {flavor}：systemd 模式同步失败 → 还原")
    fx = Fixture(flavor, new_text)
    try:
        fx.systemctl("start", UNIT)
        fx.wait_listen()
        shutil.rmtree(fx.data / "services")
        (fx.data / "services").write_text("services 是个文件，cp 进去会失败\n", encoding="utf-8")
        rc, out = fx.deploy_run(unit=UNIT)
        check("退出码 1，报同步失败并从备份还原", rc == 1 and "同步 services 失败" in out and "从备份" in out, f"rc={rc}\n{out}")
        check("约定目录还原成旧样（services 仍是那个文件、contracts 是旧内容）",
              (fx.data / "services").is_file() and fx.data_text("contracts") == "old contracts\n"
              and (fx.data / "plan" / "top.zs").read_text() == "old top\n", "")
        check("服务已拉回：MainPID 是监听进程、GET / 200", fx.wait_listen() and port_pid(fx.port) == fx.main_pid(), "")
        check("恢复信息", "恢复：" in out and "GET / 200" in out, out)
    finally:
        fx.cleanup()

    print(f"== {flavor}：systemd 模式新版本没就绪 → 停 unit、还原、再拉起")
    fx = Fixture(flavor, new_text)
    try:
        fx.systemctl("start", UNIT)
        fx.wait_listen()
        (fx.sd / "broken_once").write_text("")
        t0 = time.time()
        rc, out = fx.deploy_run(unit=UNIT, timeout=300)
        check("退出码 1，报没就绪并从备份还原", rc == 1 and "没就绪" in out and "从备份" in out, f"rc={rc}\n{out}")
        check("约定目录还原成旧内容", fx.data_text("services") == "old services\n" and fx.data_text("i18n") == "old i18n\n", "")
        check("调用顺序 start → stop → start(坏) → stop → start(恢复)",
              fx.calls() == ["start", "stop", "start", "stop", "start"], f"{fx.calls()}")
        check("恢复后 MainPID 是监听进程、GET / 200", fx.wait_listen() and port_pid(fx.port) == fx.main_pid(), out)
        print(f"    （等就绪超时用了 {time.time() - t0:.0f} 秒，KG_READY_TRIES=20）")
    finally:
        fx.cleanup()

    print(f"== {flavor}：systemd 模式停服前拦截")
    fx = Fixture(flavor, new_text)
    try:
        # 端口被别的进程（不是 MainPID）占着
        other = subprocess.Popen([sys.executable, "-m", "http.server", str(fx.port), "--bind", "127.0.0.1",
                                  "--directory", str(fx.sd / "www")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
        try:
            fx.wait_listen()
            rc, out = fx.deploy_run(unit=UNIT)
            check("端口被非 MainPID 占着：退出码 1、未停服", rc == 1 and "不是" in out and "未停服" in out
                  and fx.calls() == [] and not fx.backups_list(), f"rc={rc} {fx.calls()}\n{out}")
        finally:
            other.terminate()
            other.wait()
        rc, out = fx.deploy_run(unit="nope.service")
        check("unit 不存在：退出码 1、未停服", rc == 1 and "LoadState=not-found" in out and fx.calls() == [], f"rc={rc}\n{out}")
        rc, out = fx.deploy_run(unit="bad unit;rm")
        check("unit 名不合法：退出码 2", rc == 2 and "不合法" in out, f"rc={rc}\n{out}")
        fx.systemctl("start", UNIT)
        fx.wait_listen()
        subprocess.run(["setsid", "-f", "bash", str(fx.deploy.parent / "watch.sh")], env=fx.env(),
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        for _ in range(30):
            if (fx.run_dir / "watch.lock").exists() and holders_of(fx.run_dir / "watch.lock"):
                break
            time.sleep(0.1)
        rc, out = fx.deploy_run(unit=UNIT)
        check("看门狗在跑：退出码 1、未停服", rc == 1 and "看门狗在跑" in out and fx.calls() == ["start"], f"rc={rc} {fx.calls()}\n{out}")
    finally:
        fx.cleanup()


def main():
    sys.stdout.reconfigure(line_buffering=True)
    for tool in ("ss", "curl", "flock", "setsid", "git"):
        if not shutil.which(tool):
            print(f"缺 {tool}，跳过")
            return 0
    new_bundle = extract_template((ROOT / "scripts" / "build_bundle.sh").read_text(encoding="utf-8"))
    old_src = subprocess.run(["git", "-C", str(ROOT), "show", f"{BASE_COMMIT}:scripts/build_bundle.sh"],
                             capture_output=True, text=True)
    if old_src.returncode != 0:
        print(f"取不到基线 {BASE_COMMIT}:scripts/build_bundle.sh：{old_src.stderr.strip()}")
        return 1
    suite("bundle", new_bundle, extract_template(old_src.stdout))
    if LOCAL_DEPLOY.is_file() and LOCAL_BASE.is_file():
        suite("local", LOCAL_DEPLOY.read_text(encoding="utf-8"), LOCAL_BASE.read_text(encoding="utf-8"))
    else:
        print(f"（本机 {LOCAL_DEPLOY} 或 {LOCAL_BASE.name} 不在，跳过 local）")
    print(f"\n通过 {ok}，失败 {fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
