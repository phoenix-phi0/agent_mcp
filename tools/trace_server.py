"""编排过程的实时查看：起一个只读的本地小服务，浏览器里看正在跑的流程走到哪一步。

    python -m tools.trace_server workflow_demo            # 工作目录（下面有 runs/）
    python -m tools.trace_server workflow_demo/runs --port 8765

然后打开 http://127.0.0.1:8765 。页面每 1.5 秒拉一次，跟随最新的一次运行。

接口（都只读）：
    GET /                 查看器页面（tools/trace_view.html）
    GET /api/runs         runs/*.json 列表，新的在前：name、status、started、updated、alive
    GET /api/run?name=…   一份过程记录，多几个字段：_alive；_control（受控编排的模式、覆盖、
                          最近操作，没有控制文件就是 null）；_formats（脚本里用到的格式定义）

alive：记录里是 running 时，按记录里的 pid 查进程还在不在（同一台机器才准）。
进程被杀、机器重启，记录会一直停在 running，靠它区分「还在跑」和「已经没了」。

只监听 127.0.0.1；日志写 devnull，不接管道（每秒的轮询会把管道写满）。
"""
import argparse
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

VIEW = Path(__file__).resolve().with_name("trace_view.html")
_NAME = re.compile(r"^[\w.-]+\.json$")


def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


_FMT = re.compile(r"^\s+格式\s+([A-Za-z][A-Za-z0-9_]*)\s*$", re.M)


def read_control(path):
    """受控编排的控制文件（runs/<id>.ctl，见 tools/workflow_ctl.py）：模式、覆盖、最近的操作。没有就 None。"""
    cf = path.with_name(path.name[:-len(".json")] + ".ctl")
    if not cf.is_file():
        return None
    try:
        c = json.loads(cf.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    worker = c.get("worker")
    return {"mode": c.get("mode"), "stop_roles": c.get("stop_roles") or [], "models": c.get("models") or {},
            "roles": c.get("roles") or {}, "history": (c.get("history") or [])[-30:],
            "worker": worker, "worker_alive": pid_alive(worker) if worker else None}


def read_formats(data):
    """脚本里「格式 名字」用到的格式定义，从记录里的工作目录 formats/ 读。读不到的跳过。"""
    out = {}
    wd = data.get("workdir")
    for name in sorted(set(_FMT.findall(data.get("script") or ""))):
        f = Path(wd or ".") / "formats" / f"{name}.json"
        try:
            out[name] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return out


def read_trace(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_alive"] = pid_alive(data.get("pid")) if data.get("status") == "running" else None
    data["_name"] = path.name
    data["_control"] = read_control(path)
    data["_formats"] = read_formats(data)
    return data


def list_runs(runs):
    out = []
    for p in sorted(runs.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = read_trace(p)
        except (OSError, ValueError):
            continue        # 正在被替换的瞬间读坏了，下次轮询再看
        tasks = [e for e in d.get("events", []) if e.get("type") == "task" and e.get("status") != "waiting"]
        pend = d.get("pending") if d.get("status") == "waiting" else None
        out.append({"name": p.name, "status": d.get("status"), "started": d.get("started"),
                    "updated": d.get("updated"), "alive": d["_alive"], "calls": len(tasks),
                    "controlled": d["_control"] is not None,
                    "waiting_step": pend.get("step") if pend else None})
    return out


def view_html():
    """查看器页面，加一个标记：页面靠它知道自己是由本服务提供的，进实时模式（经隧道访问时主机名不是 localhost）。"""
    return VIEW.read_bytes().replace(b"<head>", b'<head>\n<meta name="trace-live" content="1">', 1)


def make_handler(runs, token=None, base=""):
    """token：给了就只认 /<token>/ 下面的地址，别的一律 404（经隧道公开到外网时用）。
    base：挂在反向代理的子路径下（如 relay 把 /trace* 转过来），地址整体是 <base>/<token>/…"""
    base = "/" + base.strip("/") if base and base.strip("/") else ""
    prefix = base + (f"/{token}" if token else "")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype, extra=None):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            # 地址里有令牌：不让浏览器在请求字体等外部资源时把它当来源地址带出去
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def json(self, obj, code=200):
            self.send(code, json.dumps(obj, ensure_ascii=False, default=str), "application/json; charset=utf-8")

        def do_GET(self):
            u = urlparse(self.path)
            path = u.path
            if prefix:
                if path == prefix:
                    return self.send(301, b"", "text/plain", {"Location": prefix + "/"})
                if not path.startswith(prefix + "/"):
                    return self.json({"error": "没有这个地址"}, 404)
                path = path[len(prefix):]
            if path in ("/", "/index.html"):
                return self.send(200, view_html(), "text/html; charset=utf-8")
            if path == "/api/runs":
                return self.json({"dir": runs.name if token else str(runs), "runs": list_runs(runs)})
            if path == "/api/run":
                name = (parse_qs(u.query).get("name") or [""])[0]
                if not _NAME.fullmatch(name):
                    return self.json({"error": "文件名不对"}, 400)
                p = (runs / name).resolve()
                if p.parent != runs.resolve() or not p.is_file():
                    return self.json({"error": f"没有 {name}"}, 404)
                try:
                    return self.json(read_trace(p))
                except (OSError, ValueError) as e:
                    return self.json({"error": f"读不了 {name}：{e}"}, 503)
            return self.json({"error": "没有这个地址"}, 404)
    return H


def main(argv=None):
    ap = argparse.ArgumentParser(description="编排过程的实时查看")
    ap.add_argument("dir", help="工作目录（下面有 runs/）或 runs 目录本身")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--token", default=os.environ.get("TRACE_TOKEN") or None,
                    help="只认 /<token>/ 下的地址（也可用环境变量 TRACE_TOKEN）；经隧道公开到外网时一定要给")
    ap.add_argument("--base", default="", help="挂在反向代理的子路径下，如 /trace（relay 把 /trace* 转过来时）")
    a = ap.parse_args(argv)
    if a.token and not re.fullmatch(r"[A-Za-z0-9_-]{16,}", a.token):
        ap.error("--token 至少 16 位，只能是字母、数字、_、-")
    if a.base and not re.fullmatch(r"/?[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*/?", a.base):
        ap.error("--base 只能是 /xxx 这样的路径")
    d = Path(a.dir).resolve()
    runs = d if d.name == "runs" else d / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(runs, a.token, a.base))
    base = "/" + a.base.strip("/") if a.base.strip("/") else ""
    print(f"查看 {runs}：http://{a.host}:{a.port}{base}{'/' + a.token if a.token else ''}/  （Ctrl+C 停止）", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    sys.exit(main())
