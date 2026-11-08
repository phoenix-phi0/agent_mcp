# -*- coding: utf-8 -*-
"""把编排查看器经 Cloudflare 临时隧道公开到外网：只读，地址里带随机令牌。

    python -m tools.trace_public start workflow_demo [--port 8765]
    python -m tools.trace_public status
    python -m tools.trace_public stop

start 做三件事：
1. 起 trace_server（只监听 127.0.0.1，令牌经环境变量 TRACE_TOKEN 给，不出现在命令行里），
   只认 /<令牌>/ 下的地址，别的一律 404；
2. 起 cloudflared 临时隧道（trycloudflare.com，不用注册账号），把公网 https 转到本机端口；
3. 从外网地址实际拉一次 /<令牌>/api/runs，通了才打印完整地址。

cloudflared 没装就从 GitHub 官方发布下载到 ~/.local/bin/cloudflared（linux-amd64）。
状态、日志在 ~/.trace_public/（state.json 权限 600，里面有令牌）。
临时隧道的域名每次 start 都会变；机器重启后要重新 start。拿到地址的人都能看全部运行记录
（只读），不要把地址发到公开的地方。
"""
import argparse
import json
import os
import re
import secrets
import signal
import socket
import stat
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = Path(os.environ.get("TRACE_PUBLIC_HOME") or Path.home() / ".trace_public")
STATE = HOME / "state.json"
CF = Path(os.environ.get("CLOUDFLARED") or Path.home() / ".local/bin/cloudflared")
CF_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
_TRY = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def _alive(pid):
    try:
        st = Path(f"/proc/{pid}/stat").read_text()
    except (OSError, TypeError):
        return False
    return st.rsplit(")", 1)[-1].split()[0] != "Z"


def _kill(pid):
    if not pid or not _alive(pid):
        return
    try:
        os.killpg(pid, signal.SIGTERM)
        for _ in range(50):
            if not _alive(pid):
                return
            time.sleep(0.1)
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _free_port(want):
    for port in [want] + list(range(want + 1, want + 50)):
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit(f"{want} 往后 50 个端口都被占了")


def _get(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "trace-public-check"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def ensure_cloudflared():
    if CF.is_file() and os.access(CF, os.X_OK):
        return CF
    if os.uname().machine not in ("x86_64", "amd64"):
        raise SystemExit(f"没有现成的 cloudflared，这台机器是 {os.uname().machine}，请手动装")
    CF.parent.mkdir(parents=True, exist_ok=True)
    tmp = CF.with_name(CF.name + ".download")
    print(f"下载 cloudflared：{CF_URL}", flush=True)
    with urllib.request.urlopen(CF_URL, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    tmp.chmod(0o755)
    v = subprocess.run([str(tmp), "--version"], capture_output=True, text=True, timeout=30)
    if v.returncode != 0 or "cloudflared" not in (v.stdout + v.stderr):
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"下载的 cloudflared 跑不起来：{(v.stdout + v.stderr)[:300]}")
    os.replace(tmp, CF)
    print("  " + (v.stdout or v.stderr).strip().splitlines()[0], flush=True)
    return CF


def _spawn(cmd, log, env=None):
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"\n=== {time.strftime('%F %T')} {Path(cmd[0]).name}\n")
        f.flush()
        return subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=f,
                                stderr=subprocess.STDOUT, start_new_session=True).pid


def _load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(st):
    HOME.mkdir(parents=True, exist_ok=True)
    os.chmod(HOME, stat.S_IRWXU)
    tmp = STATE.with_name("state.json.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATE)


def status():
    st = _load()
    if not st:
        print("没有在公开")
        return 1
    relay = st.get("mode") == "relay"
    srv = _alive(st["server_pid"])
    tun = True if relay else _alive(st["tunnel_pid"])
    print(f"查看服务：{'在跑' if srv else '不在了'}（pid {st['server_pid']}，端口 {st['port']}，看 {st['workdir']}）")
    print("转发：经 relay" if relay else f"隧道：{'在跑' if tun else '不在了'}（pid {st['tunnel_pid']}）")
    print(f"地址：{st['url']}/{st['token']}/")
    if srv and tun:
        try:
            code, _ = _get(f"{st['url']}/{st['token']}/api/runs")
            print(f"外网访问：HTTP {code}")
        except Exception as e:
            print(f"外网访问：失败（{e}）")
    return 0 if srv and tun else 1


def stop():
    st = _load()
    if not st:
        print("没有在公开")
        return 0
    _kill(st.get("tunnel_pid"))
    _kill(st.get("server_pid"))
    STATE.unlink(missing_ok=True)
    print("已停止（隧道和查看服务都关了，原来的地址失效）")
    return 0


def start_relay(workdir, port, relay, base):
    """经已有的 relay（/workspace/relay/agent.py 按路径前缀转发）公开：不起隧道，查看服务固定端口、
    挂在 base 子路径下。relay 那边要有一条 base=http://127.0.0.1:port 的路由。"""
    st = _load()
    if st and _alive(st["server_pid"]) and (st.get("mode") == "relay" or _alive(st.get("tunnel_pid"))):
        print("已经在公开了：")
        return status()
    if st:
        stop()
    wd = Path(workdir)
    if not wd.is_absolute():
        wd = ROOT / wd
    wd = wd.resolve()
    if not (wd / "runs").is_dir() and wd.name != "runs":
        raise SystemExit(f"{wd} 下面没有 runs/")
    if _free_port(port) != port:
        raise SystemExit(f"端口 {port} 被占了：relay 的路由指向它，不能换端口")
    base = "/" + base.strip("/")
    HOME.mkdir(parents=True, exist_ok=True)
    os.chmod(HOME, stat.S_IRWXU)
    token = secrets.token_urlsafe(24)
    env = dict(os.environ, TRACE_TOKEN=token, PYTHONPATH=str(ROOT))
    spid = _spawn([sys.executable, "-m", "tools.trace_server", str(wd), "--port", str(port), "--base", base],
                  HOME / "server.log", env)
    for _ in range(50):
        try:
            if _get(f"http://127.0.0.1:{port}{base}/{token}/api/runs", 2)[0] == 200:
                break
        except Exception:
            time.sleep(0.2)
    else:
        _kill(spid)
        raise SystemExit(f"查看服务没起来，看 {HOME / 'server.log'}")
    url = relay.rstrip("/") + base
    _save({"mode": "relay", "server_pid": spid, "tunnel_pid": None, "port": port, "workdir": str(wd),
           "url": url, "token": token, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    print(f"公开地址：{url}/{token}/")
    try:
        code, body = _get(f"{url}/{token}/api/runs")
        print("外网检查：通了" if code == 200 and b'"runs"' in body else f"外网检查：HTTP {code}，内容不对")
    except Exception as e:
        print(f"外网检查：还不通（{e}）。relay 里要有 {base}=http://127.0.0.1:{port} 这条路由，并重启过 relay")
    return 0


def start(workdir, port):
    st = _load()
    if st and _alive(st["server_pid"]) and _alive(st["tunnel_pid"]):
        print("已经在公开了：")
        return status()
    if st:
        stop()
    wd = Path(workdir)
    if not wd.is_absolute():
        wd = ROOT / wd
    wd = wd.resolve()
    if not (wd / "runs").is_dir() and wd.name != "runs":
        raise SystemExit(f"{wd} 下面没有 runs/")
    HOME.mkdir(parents=True, exist_ok=True)
    os.chmod(HOME, stat.S_IRWXU)
    cf = ensure_cloudflared()
    port = _free_port(port)
    token = secrets.token_urlsafe(24)
    env = dict(os.environ, TRACE_TOKEN=token, PYTHONPATH=str(ROOT))
    spid = _spawn([sys.executable, "-m", "tools.trace_server", str(wd), "--port", str(port)],
                  HOME / "server.log", env)
    for _ in range(50):
        try:
            if _get(f"http://127.0.0.1:{port}/{token}/api/runs", 2)[0] == 200:
                break
        except Exception:
            time.sleep(0.2)
    else:
        _kill(spid)
        raise SystemExit(f"查看服务没起来，看 {HOME / 'server.log'}")
    tlog = HOME / "tunnel.log"
    mark = tlog.stat().st_size if tlog.exists() else 0
    tpid = _spawn([str(cf), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"], tlog)
    url = None
    for _ in range(120):
        time.sleep(0.5)
        if not _alive(tpid):
            break
        m = _TRY.search(tlog.read_text(encoding="utf-8", errors="replace")[mark:])
        if m:
            url = m.group(0)
            break
    if not url:
        _kill(tpid)
        _kill(spid)
        raise SystemExit(f"隧道没拿到地址，看 {tlog}")
    _save({"server_pid": spid, "tunnel_pid": tpid, "port": port, "workdir": str(wd), "url": url,
           "token": token, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    # 新域名的 DNS 要几秒才生效：从外网实际拉一次，通了再报
    last = None
    for _ in range(30):
        try:
            code, body = _get(f"{url}/{token}/api/runs")
            if code == 200 and b'"runs"' in body:
                last = None
                break
        except Exception as e:
            last = e
        time.sleep(2)
    print(f"公开地址：{url}/{token}/")
    if last:
        print(f"（外网检查还没通：{last}；隧道刚建好时 DNS 可能要再等一会儿，稍后用 status 查）")
    else:
        print("外网检查：通了")
    print(f"关掉：python -m tools.trace_public stop")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="把编排查看器经 Cloudflare 临时隧道公开到外网")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("workdir", nargs="?", default="workflow_demo")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--relay", default=None,
                   help="经已有 relay 公开，给外网域名，如 https://demo.yscinternet.top（不起 cloudflared）")
    s.add_argument("--base", default="/trace", help="relay 模式下的子路径，默认 /trace")
    sub.add_parser("status")
    sub.add_parser("stop")
    a = ap.parse_args(argv)
    if a.cmd == "start":
        if a.relay:
            return start_relay(a.workdir, a.port, a.relay, a.base)
        return start(a.workdir, a.port)
    return status() if a.cmd == "status" else stop()


if __name__ == "__main__":
    sys.exit(main())
