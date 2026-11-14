"""编排过程的实时查看：起一个本地小服务，浏览器里看正在跑的流程走到哪一步；停在节点上时可以在页面里做决定。

    python -m tools.trace_server workflow_demo            # 工作目录（下面有 runs/）
    python -m tools.trace_server workflow_demo/runs --port 8765

然后打开 http://127.0.0.1:8765 。页面每 1.5 秒拉一次，跟随最新的一次运行。

读接口：
    GET /                 查看器页面（tools/trace_view.html）
    GET /api/runs         runs/*.json 列表，新的在前：name、status、started、updated、alive
    GET /api/run?name=…   一份过程记录，多几个字段：_alive；_control（受控编排的模式、覆盖、
                          最近操作，没有控制文件就是 null）；_formats（脚本里用到的格式定义）；
                          _agents（工作目录 agents/ 下的角色卡：名字、模型、说明，换卡执行时选）
    GET /api/plan?name=…&record=…  分配清单和逐项控制；record 可省

写接口（POST，JSON 体，Content-Type 必须是 application/json；直接调 tools/workflow_ctl.py，校验和出错
信息都是它的）。只在服务绑定本机地址（127.0.0.1 / ::1 / localhost）且没加 --readonly 时开放，否则 403；
带 --token（经隧道公开到外网）时默认也只读，要再加 --write 才开放：
    POST /api/submit      {name, result, step?}        交回停住那一步的结果（人扮演这个角色）
    POST /api/execute     {name, model?, role?, step?} 用内置执行器跑这一步，可换模型 / 换卡
    POST /api/resume      {name}                       改成自动，往下跑
    POST /api/abort       {name}                       中止
    POST /api/approve     {name, attempt, step?, result?, note?, item_controls?}
    POST /api/reject      {name, attempt, note, step?, role?, model?}
    POST /api/edit_plan   {name, tasks?, item_controls?, record?}
    POST /api/pause       {name}
  带 Origin 头的请求，Origin 要和 Host 一致；没有 --token 时 Host 还得是本机名（127.0.0.1 / ::1 / localhost），否则 403。
  成功：200 {ok: true, status: workflow_ctl.status 的摘要}
  失败：400 {ok: false, error: 原样的出错信息, errors?: ["字段: 原因", …]}（格式不合格时带逐条字段错误）
  往下跑一律交给后台进程（workflow_ctl 自己起），接口立刻返回，页面靠轮询看进度。

alive：记录里是 running 时，按记录里的 pid 查进程还在不在（同一台机器才准）。
进程被杀、机器重启，记录会一直停在 running，靠它区分「还在跑」和「已经没了」。

只监听 127.0.0.1；日志写 devnull，不接管道（每秒的轮询会把管道写满）。
"""
import argparse
import ipaddress
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

VIEW = Path(__file__).resolve().with_name("trace_view.html")
_NAME = re.compile(r"^[\w.-]+\.json$")
_CARD = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_WRITE_OPS = ("submit", "execute", "resume", "abort", "approve", "reject", "edit_plan", "pause")
_MAX_BODY = 4 * 1024 * 1024
_LOCK = threading.Lock()        # 写操作一次只做一个：控制文件只能有一个写的人


def writable(host):
    """写接口只在绑定本机地址时开放。"""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _hostname(host):
    """Host 头里的主机名：去掉端口和 IPv6 的方括号。"""
    if host.startswith("["):
        return host[1:].split("]", 1)[0]
    return host.rsplit(":", 1)[0] if ":" in host else host


def _ctl():
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    from tools import workflow_ctl
    return workflow_ctl


def control(op, path, body):
    """做一次写操作，返回 (HTTP 状态码, 回给页面的 JSON)。path 是已经核对过的记录文件。"""
    wc = _ctl()
    step = body.get("step")
    try:
        with _LOCK:
            if op in ("approve", "reject") and body.get("attempt") is None:
                raise wc.ControlError("缺少 attempt")
            if op == "submit":
                if "result" not in body:
                    raise wc.ControlError("缺少 result")
                st = wc.submit(path, body["result"], step=step, wait=False)
            elif op == "execute":
                st = wc.execute(path, model=body.get("model") or None, role=body.get("role") or None,
                                step=step, wait=False)
            elif op == "resume":
                st = wc.resume(path, wait=False)
            elif op == "approve":
                st = wc.approve(path, attempt=body["attempt"], step=step,
                                result=body.get("result"), note=body.get("note"),
                                item_controls=body.get("item_controls"), wait=False)
            elif op == "reject":
                st = wc.reject(path, attempt=body["attempt"], note=body.get("note"),
                               step=step, role=body.get("role"), model=body.get("model"), wait=False)
            elif op == "edit_plan":
                st = wc.edit_plan(path, tasks=body.get("tasks"),
                                  item_controls=body.get("item_controls"), record=body.get("record"))
            elif op == "pause":
                st = wc.pause(path)
            else:
                st = wc.abort(path)
    except wc.ControlError as e:
        out = {"ok": False, "error": str(e)}
        if op in ("submit", "approve") and str(e).startswith("结果不符合格式"):     # 别的错（步号不对、后台还在跑）不带字段错误
            bad = _field_errors(path, body.get("result"))
            if bad:
                out["errors"] = bad
        return 400, out
    except (TypeError, ValueError) as e:
        return 400, {"ok": False, "error": f"参数不对：{e}"}
    except Exception as e:      # 不让一次失败的操作把服务带倒
        return 500, {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return 200, {"ok": True, "status": st}


def _field_errors(path, result):
    """结果不合格式时逐条的字段错误：和 workflow_ctl.submit 用的是同一个校验（tools/wf_submit.validate）。"""
    try:
        pend = json.loads(path.read_text(encoding="utf-8")).get("pending") or {}
        if isinstance(result, str):
            result = json.loads(result)
        if not pend.get("schema") or not isinstance(result, dict):
            return []
        from tools.wf_submit import validate
        return validate(pend["schema"], result)
    except Exception:
        return []


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
            "confirm_before": c.get("confirm_before") or [],
            "confirm_after": c.get("confirm_after") or [], "max_attempts": c.get("max_attempts"),
            "notes": {step: rows[-10:] for step, rows in (c.get("notes") or {}).items()},
            "revisions": {step: [{key: row.get(key) for key in
                                   ("rev", "kind", "attempt", "actor", "at", "note")}
                                  for row in rows]
                          for step, rows in (c.get("revisions") or {}).items()},
            "item_controls": c.get("item_controls") or {},
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


def read_agents(data):
    """工作目录 agents/ 下的角色卡（换卡执行时选）：只带名字、模型、说明、成本。"""
    out = []
    root = Path(data.get("workdir") or ".") / "agents"
    try:
        dirs = sorted(p for p in root.iterdir() if p.is_dir() and _CARD.fullmatch(p.name))
    except OSError:
        return out
    for d in dirs:
        try:
            card = json.loads((d / "agent.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(card, dict):
            out.append({"name": d.name, "model": card.get("model"), "description": card.get("description"),
                        "cost": card.get("cost")})
    return out


def read_trace(path, brief=False):
    """brief：只要状态和控制文件（列运行清单时用），不读格式定义和角色卡。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_alive"] = pid_alive(data.get("pid")) if data.get("status") == "running" else None
    data["_name"] = path.name
    data["_control"] = read_control(path)
    if not brief:
        data["_formats"] = read_formats(data)
        data["_agents"] = read_agents(data)
    return data


def list_runs(runs):
    out = []
    for p in sorted(runs.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = read_trace(p, brief=True)
        except (OSError, ValueError):
            continue        # 正在被替换的瞬间读坏了，下次轮询再看
        tasks = [e for e in d.get("events", []) if e.get("type") == "task" and e.get("status") != "waiting"]
        pend = d.get("pending") if d.get("status") == "waiting" else None
        out.append({"name": p.name, "status": d.get("status"), "started": d.get("started"),
                    "updated": d.get("updated"), "alive": d["_alive"], "calls": len(tasks),
                    "controlled": d["_control"] is not None,
                    "waiting_step": pend.get("step") if pend else None})
    return out


def view_html(write=False):
    """查看器页面，加一个标记：页面靠它知道自己是由本服务提供的，进实时模式（经隧道访问时主机名不是 localhost）。
    write：再加一个标记，页面才显示「由我来做」和执行、继续、中止这些按钮。"""
    meta = b'<head>\n<meta name="trace-live" content="1">'
    if write:
        meta += b'\n<meta name="trace-write" content="1">'
    return VIEW.read_bytes().replace(b"<head>", meta, 1)


def respond(code, body, ctype, extra=None):
    data = body if isinstance(body, bytes) else body.encode("utf-8")
    head = {"Content-Type": ctype, "Cache-Control": "no-store",
            # 地址里有令牌，不能作为来源地址带给外部资源。
            "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"}
    head.update(extra or {})
    head["Content-Length"] = str(len(data))
    return code, head, data


def respond_json(obj, code=200):
    # 校验错误可能原样引用孤立代理字符，JSON 转义后仍能安全返回。
    return respond(code, json.dumps(obj, ensure_ascii=True, default=str),
                   "application/json; charset=utf-8")


def validate_post_request(path, headers, token=None, base="", write=False):
    """正文读取前的共用检查：返回允许的长度，或完整的拒绝响应。"""
    base = "/" + base.strip("/") if base and base.strip("/") else ""
    prefix = base + (f"/{token}" if token else "")
    normalized_headers = {}
    for key, value in headers.items():
        normalized_headers.setdefault(key.lower(), value)
    headers = normalized_headers
    if prefix:
        if not path.startswith(prefix + "/"):
            return respond_json({"ok": False, "error": "没有这个地址"}, 404)
        path = path[len(prefix):]
    op = path[len("/api/"):] if path.startswith("/api/") else ""
    if op not in _WRITE_OPS:
        return respond_json({"ok": False, "error": "没有这个地址"}, 404)
    if not write:
        return respond_json({"ok": False, "error": "这个查看服务是只读的（没有绑定本机地址、加了 --readonly，或带 --token 而没加 --write），不能在页面上操作"}, 403)
    # 别的网页不能借浏览器往这里发写请求：带 Origin 的要和 Host 是同一个；没有 --token 时 Host 还得是本机名
    # （防 DNS 重绑定：外面的域名解析到 127.0.0.1）。带 --token 时地址本身就是口令，Host 可能是隧道的域名
    host = (headers.get("host") or "").strip().lower()
    origin = (headers.get("origin") or "").strip().lower()
    if origin and origin != "null" and urlparse(origin).netloc != host:
        return respond_json({"ok": False, "error": "不接受别的网页发来的写请求（Origin 和 Host 不一致）"}, 403)
    if origin == "null" or (not token and not writable(_hostname(host))):
        return respond_json({"ok": False, "error": "写接口只接受从本机地址打开的页面"}, 403)
    # 只收 application/json：别的网页想跨站往本机发这种请求，浏览器会先预检，而这里不回预检
    if (headers.get("content-type") or "").split(";")[0].strip().lower() != "application/json":
        return respond_json({"ok": False, "error": "Content-Type 要是 application/json"}, 415)
    try:
        size = int(headers.get("content-length") or 0)
    except ValueError:
        size = -1
    if size < 0 or size > _MAX_BODY:
        return respond_json({"ok": False, "error": "请求体太大或没有长度"}, 413)
    return size


def route(runs, method, path, query, headers, body, token=None, base="", write=False):
    """与 HTTP 服务器无关的路由，返回 (状态码, 响应头字典, 正文 bytes)。

    runs 是 runs 目录的 Path；path 不含 query，query 是原始查询字符串（不含 ?）。
    headers 接受普通 dict 或 HTTPMessage，按大小写不敏感的方式读取；body 是原始 bytes，
    或接收长度并返回 bytes 的读取函数（仅在 POST 头部检查通过后调用）。
    token / base 与 make_handler 相同；write 是调用方按绑定地址和开关算好的写权限。
    文件读取和 control 写操作沿用原有实现，本函数不读写网络连接。
    """
    base = "/" + base.strip("/") if base and base.strip("/") else ""
    prefix = base + (f"/{token}" if token else "")
    normalized_headers = {}
    for key, value in headers.items():
        normalized_headers.setdefault(key.lower(), value)  # HTTPMessage.get 取第一个同名头
    headers = normalized_headers

    if method == "GET":
        if prefix:
            if path == prefix:
                return respond(301, b"", "text/plain", {"Location": prefix + "/"})
            if not path.startswith(prefix + "/"):
                return respond_json({"error": "没有这个地址"}, 404)
            path = path[len(prefix):]
        if path in ("/", "/index.html"):
            return respond(200, view_html(write), "text/html; charset=utf-8")
        if path == "/api/runs":
            return respond_json({"dir": runs.name if token else str(runs), "runs": list_runs(runs)})
        if path in ("/api/run", "/api/plan"):
            name = (parse_qs(query).get("name") or [""])[0]
            if not _NAME.fullmatch(name):
                return respond_json({"error": "文件名不对"}, 400)
            p = (runs / name).resolve()
            if p.parent != runs.resolve() or not p.is_file():
                return respond_json({"error": f"没有 {name}"}, 400 if path == "/api/plan" else 404)
            if path == "/api/plan":
                wc = _ctl()
                record = (parse_qs(query).get("record") or [None])[0]
                try:
                    return respond_json(wc.plan(p, record=record))
                except wc.ControlError as e:
                    return respond_json({"error": str(e)}, 400)
            try:
                return respond_json(read_trace(p))
            except (OSError, ValueError) as e:
                return respond_json({"error": f"读不了 {name}：{e}"}, 503)
        return respond_json({"error": "没有这个地址"}, 404)

    if method == "POST":
        size = validate_post_request(path, headers, token, base, write)
        if not isinstance(size, int):
            return size
        if prefix:
            path = path[len(prefix):]
        op = path[len("/api/"):]
        # HTTP handler 延迟读取：拒绝地址、权限和头部时不能等待客户端正文。
        if callable(body):
            body = body(size)
        try:
            body = json.loads(body[:size].decode("utf-8") or "null")
        except ValueError as e:
            return respond_json({"ok": False, "error": f"请求体不是 JSON：{e}"}, 400)
        if not isinstance(body, dict):
            return respond_json({"ok": False, "error": "请求体要是 JSON 对象"}, 400)
        name = body.get("name")
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            return respond_json({"ok": False, "error": "文件名不对"}, 400)
        p = (runs / name).resolve()
        if p.parent != runs.resolve() or not p.is_file():
            return respond_json({"ok": False, "error": f"没有 {name}"}, 404)
        code, out = control(op, p, body)
        return respond_json(out, code)
    return respond_json({"error": "没有这个地址"}, 404)


def make_handler(runs, token=None, base="", write=False):
    """token / base：地址整体是 <base>/<token>/…；write 由调用方按绑定地址算好。"""
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _dispatch(self, method):
            u = urlparse(self.path)
            body = self.rfile.read if method == "POST" else b""
            code, headers, data = route(runs, method, u.path, u.query, self.headers,
                                        body, token, base, write)
            self.send_response(code)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")
    return H


def main(argv=None):
    ap = argparse.ArgumentParser(description="编排过程的实时查看")
    ap.add_argument("dir", help="工作目录（下面有 runs/）或 runs 目录本身")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--token", default=os.environ.get("TRACE_TOKEN") or None,
                    help="只认 /<token>/ 下的地址（也可用环境变量 TRACE_TOKEN）；经隧道公开到外网时一定要给")
    ap.add_argument("--base", default="", help="挂在反向代理的子路径下，如 /trace（relay 把 /trace* 转过来时）")
    ap.add_argument("--readonly", action="store_true", help="不开放写接口（页面上不出现提交、执行、继续、中止）")
    ap.add_argument("--write", action="store_true",
                    help="给了 --token（经隧道公开）时默认只读；加这个才开放写接口：拿到地址的人都能提交、执行、中止")
    a = ap.parse_args(argv)
    if a.token and not re.fullmatch(r"[A-Za-z0-9_-]{16,}", a.token):
        ap.error("--token 至少 16 位，只能是字母、数字、_、-")
    if a.base and not re.fullmatch(r"/?[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*/?", a.base):
        ap.error("--base 只能是 /xxx 这样的路径")
    d = Path(a.dir).resolve()
    runs = d if d.name == "runs" else d / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    # 写接口：绑定本机地址才开放；带 --token 多半是经隧道公开给外面看，默认仍只读，要明说 --write
    write = writable(a.host) and not a.readonly and (not a.token or a.write)
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(runs, a.token, a.base, write))
    base = "/" + a.base.strip("/") if a.base.strip("/") else ""
    print(f"查看 {runs}：http://{a.host}:{a.port}{base}{'/' + a.token if a.token else ''}/  "
          f"（{'可在页面上提交、执行、继续、中止' if write else '只读'}；Ctrl+C 停止）", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    sys.exit(main())
