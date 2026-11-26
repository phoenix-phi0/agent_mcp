"""编排过程的实时查看：起一个本地小服务，浏览器里看正在跑的流程走到哪一步；停在节点上时可以在页面里做决定。

    python -m tools.trace_server workflow_demo            # 工作目录（下面有 runs/）
    python -m tools.trace_server workflow_demo/runs --port 8765

然后打开 http://127.0.0.1:8765 。页面每 1.5 秒拉一次，跟随最新的一次运行。

读接口：
    GET /                 查看器页面（tools/trace_view.html）
    GET /api/runs         runs/*.json 列表，新的在前：name、status、started、updated、alive，
                          以及列表页用的 workflow、current（所在步）、seconds、cost_spent、goal 等
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
    GET  /api/entries     工作目录下能启动的入口脚本（调「编排执行」的 .zs）：文件名、说明、流程、节点名、角色；
                          另带 agents/ 下的角色卡。只给能写的查看服务
    POST /api/start       {entry, mode?, confirm_before?, confirm_after?, max_attempts?, models?, roles?}
                          启动一次受控运行（会真的调模型），回 {ok, name, status}
    POST /api/configure   {name, confirm_before?, confirm_after?, max_attempts?, models?, roles?}
                          改整次运行的规则和按角色的长期覆盖（只影响还没跑的节点）；不给的键不改，给 []/{} 清空
    POST /api/pause       {name}
  带 Origin 头的请求，Origin 要和 Host 一致；没有 --token 时 Host 还得是本机名（127.0.0.1 / ::1 / localhost），否则 403。
  成功：200 {ok: true, status: workflow_ctl.status 的摘要}
  失败：400 {ok: false, error: 原样的出错信息, errors?: ["字段: 原因", …]}（格式不合格时带逐条字段错误）
  往下跑一律交给后台进程（workflow_ctl 自己起），接口立刻返回，页面靠轮询看进度。

带 --token（TRACE_TOKEN）时要登录：<base>/login 输入口令，发一个签名 cookie（HttpOnly、SameSite=Lax，7 天，
TRACE_SESSION_TTL 可改；经 https 代理时带 Secure），之后的地址 <base>/、<base>/meeting/、<base>/api/… 都不带口令。
没登录：页面跳登录页，接口回 401（页面里加的脚本据此跳登录页）。<base>/logout 退出。换了 TRACE_TOKEN 旧 cookie 全部失效。
老地址 <base>/<口令>/… 照旧能用（过渡）：页面顺手发 cookie，浏览器里确认 cookie 能用后把地址栏换成不带口令的。

alive：记录里是 running 时，按记录里的 pid 查进程还在不在（同一台机器才准）。
进程被杀、机器重启，记录会一直停在 running，靠它区分「还在跑」和「已经没了」。

只监听 127.0.0.1；日志写 devnull，不接管道（每秒的轮询会把管道写满）。
"""
import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

VIEW = Path(__file__).resolve().with_name("trace_view.html")
_NAME = re.compile(r"^[\w.-]+\.json$")
_CARD = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_WRITE_OPS = ("submit", "execute", "resume", "abort", "approve", "reject", "edit_plan", "pause", "submit_files",
              "configure", "start")
_CONFIG_KEYS = ("confirm_before", "confirm_after", "max_attempts", "models", "roles")
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


_ENTRY = re.compile(r"^[\w.\-]+\.zs$")
_RUN_WF = re.compile(r"^\s*编排执行\s+(\S+\.wf)\s*$", re.M)
_ROLE_LINE = re.compile(r"^\s+角色\s+(?:([A-Z][A-Z0-9_]*)|\{\w+\s+或\s+([A-Z][A-Z0-9_]*)\})\s*$", re.M)
_ROSTER_VAR = re.compile(r"^\s*设\s+(?:roles|attendees|moderator)\s*=\s*(.+)$", re.M)   # 角色清单、参会名单、主持人
_NOT_NODE = ("如果", "遍历", "跳转", "存储", "清空", "标记", "角色清单", "成本合计", "#")
_FIELDS = ("任务 ", "角色 ", "文本 ", "格式 ", "记录 ")


def _wf_nodes(text):
    """流程里的节点名：下一行缩进更深、而且是任务块字段（任务 / 角色 …）的那一行。"""
    lines = [l for l in text.splitlines() if l.strip()]
    out = []
    for i, line in enumerate(lines[:-1]):
        head, nxt = line.strip(), lines[i + 1]
        ind = len(line) - len(line.lstrip())
        if (len(nxt) - len(nxt.lstrip()) > ind and nxt.strip().startswith(_FIELDS)
                and not head.startswith(_NOT_NODE) and head not in out):
            out.append(head)
    return out


def list_entries(workdir):
    """工作目录下调「编排执行」的入口脚本，带上流程里的节点名和角色（页面上做确认规则、换卡的候选）。"""
    out = []
    for f in sorted(workdir.glob("*.zs")):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        m = _RUN_WF.search(text)
        if not m or not _ENTRY.fullmatch(f.name):
            continue
        first = next((l for l in text.splitlines() if l.strip()), "")
        title = first.lstrip("#").strip() if first.startswith("#") else ""
        try:
            wf = (workdir / m[1]).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            wf = ""
        roles = []
        for a, b in _ROLE_LINE.findall(wf):
            if (a or b) not in roles:
                roles.append(a or b)
        for m2 in _ROSTER_VAR.finditer(text):
            for r in re.split(r"[,\s，]+", m2[1].strip()):
                if _CARD.fullmatch(r) and r not in roles:
                    roles.append(r)
        out.append({"entry": f.name, "title": title, "workflow": m[1][:-3], "nodes": _wf_nodes(wf), "roles": roles,
                    "params": _entry_params(text)})
    return out


def _entry_params(text):
    """入口脚本开头「# 参数：」声明的参数（启动时由 vars 传）：[{name, required, default}]。没声明是空列表。
    可选参数（`名?`）的默认值写在脚本里 `设 名 = {名 或 默认}` 的，default 报那个默认值（页面预填用）。"""
    from tools.verbs import parse_param_specs
    specs, strict, _ = parse_param_specs(text)
    out = []
    for sp in specs:
        default = sp.default
        if default in (None, "") and not (sp.required and strict):
            m = re.search(r"^[ \t]*设[ \t]+" + re.escape(sp.name) + r"[ \t]*=[ \t]*\{" + re.escape(sp.name)
                          + r"[ \t　]+或[ \t　]+(.+)\}[ \t]*$", text, re.M)
            if m:
                default = m.group(1).strip()
        out.append({"name": sp.name, "required": bool(sp.required and strict), "default": default})
    return out


def _check_roles_exist(roles, agents):
    known = {a["name"] for a in agents}
    missing = sorted({v for v in (roles or {}).values() if v not in known})
    if missing:
        from tools.workflow_ctl import ControlError
        raise ControlError(f"没有这张角色卡：{'、'.join(map(str, missing))}")


def _config_args(wc, body):
    args = {k: body[k] for k in _CONFIG_KEYS if body.get(k) is not None}
    for key in ("models", "roles"):
        if key in args and not isinstance(args[key], dict):
            raise wc.ControlError(f"{key} 要是对象（角色 → 模型 / 卡）")
    for key in ("confirm_before", "confirm_after"):
        if key in args and not isinstance(args[key], list):
            raise wc.ControlError(f"{key} 要是列表")
    return args


def start_run(runs, body):
    """页面上启动一次受控运行。工作目录是 runs 的上一层；入口必须是那里调「编排执行」的 .zs。"""
    wc = _ctl()
    workdir = runs.resolve().parent
    try:
        entry = body.get("entry")
        if not isinstance(entry, str) or not _ENTRY.fullmatch(entry):
            raise wc.ControlError("entry 要是工作目录下的 .zs 文件名")
        if entry not in {e["entry"] for e in list_entries(workdir)}:
            raise wc.ControlError(f"{entry} 不是能启动的入口脚本（工作目录里没有，或没调「编排执行」）")
        mode = body.get("mode") or "auto"
        args = _config_args(wc, body)
        if body.get("vars") is not None:
            args["vars"] = body["vars"]
        if args.get("roles"):
            _check_roles_exist(args["roles"], read_agents({"workdir": str(workdir)}))
        with _LOCK:
            st = wc.start(workdir, entry=entry, mode=mode, wait=False, actor="viewer", **args)
    except wc.ControlError as e:
        return 400, {"ok": False, "error": str(e)}
    except (TypeError, ValueError) as e:
        return 400, {"ok": False, "error": f"参数不对：{e}"}
    except Exception as e:      # 不让一次失败的操作把服务带倒
        return 500, {"ok": False, "error": f"{type(e).__name__}: {e}"}
    name = Path(st["run"]).name
    if (runs / name).resolve().parent != runs.resolve():
        return 500, {"ok": False, "error": f"运行记录没有写到 {runs}：{st['run']}"}
    return 200, {"ok": True, "name": name, "status": st}


def _configure(wc, path, body):
    """页面改运行配置：键都可选，不给的不改。换卡的目标必须是工作目录 agents/ 下真有的卡
    （configure 本身只查名字格式，填错要等跑到那一步才炸）。"""
    args = _config_args(wc, body)
    if not args:
        raise wc.ControlError("没有要改的配置")
    if args.get("roles"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        _check_roles_exist(args["roles"], read_agents(data))
    return wc.configure(path, actor="viewer", **args)


def control(op, path, body):
    """做一次写操作，返回 (HTTP 状态码, 回给页面的 JSON)。path 是已经核对过的记录文件。"""
    wc = _ctl()
    step = body.get("step")
    try:
        if op == "submit_files":
            # 不占全局写锁：要跑测试，可能几分钟；同一份记录由 workflow_ctl 的记录锁互斥。
            # 测试命令只用这次流程自己的 test_cmd，请求里不能指定。
            st = wc.submit_files(path, body.get("files"), body.get("summary"),
                                 open_issues=body.get("open_issues"), status=body.get("status") or "完成",
                                 step=step, attempt=body.get("attempt"), allow_fail=bool(body.get("allow_fail")),
                                 note=body.get("note"), wait=False, actor="viewer")
            return 200, {"ok": True, "status": st}
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
            elif op == "configure":
                st = _configure(wc, path, body)
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
            "vars": c.get("vars") or {},          # 启动时传的入口参数（会议页靠它显示议题、参会名单）
            "worker": worker, "worker_alive": pid_alive(worker) if worker else None,
            # 交结果的进程里没有模型的 key，后台进程等服务接手（见 workflow_ctl.pick_up）：这几秒不算中断
            "handoff": c.get("handoff")}


def muse_state(path, data):
    """停在 Muse 的步骤上时（pending.reason=muse）：musebatch 里这一步的任务——queued 等认领、running 在做、
    failed 做不了。查不到（还没投、读不了队列）返回 None。"""
    pend = data.get("pending") if data.get("status") == "waiting" else None
    if not pend or pend.get("reason") != "muse":
        return None
    try:
        root = Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from tools import musebatch
        rel = path.resolve().relative_to(root).as_posix()
        return musebatch.job_for(rel, pend.get("step"), pend.get("attempt", 1))
    except Exception:
        return None


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
                        "cost": card.get("cost"), "category": card.get("category")})
    return out


def read_trace(path, brief=False):
    """brief：只要状态和控制文件（列运行清单时用），不读格式定义和角色卡。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_alive"] = pid_alive(data.get("pid")) if data.get("status") == "running" else None
    data["_name"] = path.name
    data["_control"] = read_control(path)
    data["_muse"] = muse_state(path, data)
    if not brief:
        data["_formats"] = read_formats(data)
        data["_agents"] = read_agents(data)
    return data


MEETING_FORMATS = {"speech", "meeting_check", "meeting_decision"}


def list_runs(runs):
    out = []
    for p in sorted(runs.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = read_trace(p, brief=True)
        except (OSError, ValueError):
            continue        # 正在被替换的瞬间读坏了，下次轮询再看
        events = [e for e in d.get("events", []) if isinstance(e, dict)]
        tasks = [e for e in events if e.get("type") == "task" and e.get("status") != "waiting"]
        pend = d.get("pending") if d.get("status") == "waiting" else None
        # 列表页要的：现在在哪一步（跑着的那条，或者停住等外部的那一步）、需求摘要、花了多少
        running = next((e for e in reversed(tasks) if e.get("status") == "running"), None)
        here = running or pend
        inputs = d.get("inputs") if isinstance(d.get("inputs"), dict) else {}
        goal = next((str(inputs[k]) for k in ("goal", "content", "task") if inputs.get(k)), "")
        # 会议页要的：单独开的会，还是别的流程里有会议步骤（按格式认：发言、主持判断、会议结论）
        fmts = {e.get("format") for e in events if e.get("type") == "task"}
        if pend:
            fmts.add(pend.get("format"))
        meeting = ("standalone" if d.get("workflow") == "meeting_workflow"
                   else "embedded" if fmts & MEETING_FORMATS else None)
        handoff = (d["_control"] or {}).get("handoff")
        out.append({"name": p.name, "status": d.get("status"), "started": d.get("started"), "meeting": meeting,
                    "updated": d.get("updated"), "alive": None if handoff else d["_alive"], "calls": len(tasks),
                    "controlled": d["_control"] is not None, "handoff": handoff,
                    "waiting_step": pend.get("step") if pend else None,
                    # 停下的原因：human 轮到人、muse 交给 Muse（muse 带队列里的状态）、其余是等外部决定
                    "waiting_reason": pend.get("reason") if pend else None,
                    "waiting_card": pend.get("card") if pend else None, "muse": d["_muse"],
                    "workflow": d.get("workflow"), "finished": d.get("finished"), "seconds": d.get("seconds"),
                    "cost_spent": d.get("cost_spent"), "usd_spent": d.get("usd_spent"),
                    "errors": sum(1 for e in tasks if e.get("status") == "error"),
                    "current": ({"step": here.get("step"), "name": here.get("name"), "role": here.get("role")}
                                if here else None),
                    "error": str(d["error"])[:200] if d.get("error") else None,
                    "goal": goal[:160]})
    return out


def view_html(write=False, extra=b""):
    """查看器页面，加一个标记：页面靠它知道自己是由本服务提供的，进实时模式（经隧道访问时主机名不是 localhost）。
    write：再加一个标记，页面才显示「由我来做」和执行、继续、中止这些按钮。extra：登录模式加的脚本（见 _page_script）。"""
    meta = b'<head>\n<meta name="trace-live" content="1">'
    if write:
        meta += b'\n<meta name="trace-write" content="1">'
    return VIEW.read_bytes().replace(b"<head>", meta + extra, 1)


# ---- 登录（带 --token 时）----
# 访问口令就是 TRACE_TOKEN。登录后发一个签名 cookie（不是口令本身：HMAC(口令, 过期时间)），之后的地址不带口令：
#   <base>/            查看器          <base>/meeting/   会议页        <base>/api/…   接口
#   <base>/login       登录页（GET 表单，POST 验口令）     <base>/logout  退出
# 没登录：页面跳登录页，接口回 401。换了 TRACE_TOKEN，所有旧 cookie 立刻失效。
# 老地址 <base>/<口令>/… 照旧能用（过渡）：打开页面时顺手发 cookie，浏览器里确认 cookie 能用后把地址栏换成不带口令的。
SESSION_COOKIE = "trace_session"
SESSION_TTL = int(os.environ.get("TRACE_SESSION_TTL") or 7 * 86400)


def _sign(token, exp):
    return hmac.new(token.encode("utf-8"), f"trace-session:v1:{exp}".encode(), hashlib.sha256).hexdigest()


def make_session(token, now=None):
    exp = int(now if now is not None else time.time()) + SESSION_TTL
    return f"{exp}.{_sign(token, exp)}"


def check_session(token, value, now=None):
    try:
        exp_s, sig = (value or "").split(".", 1)
        exp = int(exp_s)
    except ValueError:
        return False
    if exp < (now if now is not None else time.time()):
        return False
    return hmac.compare_digest(sig.encode("ascii", "replace"), _sign(token, exp).encode())


def _cookie(headers, name):
    for part in (headers.get("cookie") or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return None


def _set_cookie(base, value, headers, max_age=None):
    secure = ((headers.get("x-forwarded-proto") or "").lower() == "https"
              or os.environ.get("TRACE_COOKIE_SECURE") == "1")
    return (f"{SESSION_COOKIE}={value}; Path={base or '/'}; Max-Age={SESSION_TTL if max_age is None else max_age}; "
            f"HttpOnly; SameSite=Lax" + ("; Secure" if secure else ""))


def _norm_base(base):
    return "/" + base.strip("/") if base and base.strip("/") else ""


def _auth(path, headers, token, base):
    """(去掉前缀后的路径, 方式)。方式：open（没设口令）、token（老地址）、cookie（已登录）、None（没登录）。
    路径不在 base 下：(None, None)。"""
    if not token:
        if base and not (path == base or path.startswith(base + "/")):
            return None, None
        return path[len(base):], "open"
    tp = base + "/" + token
    if path == tp or path.startswith(tp + "/"):
        return path[len(tp):], "token"
    if base and not (path == base or path.startswith(base + "/")):
        return None, None
    rel = path[len(base):]
    return rel, ("cookie" if check_session(token, _cookie(headers, SESSION_COOKIE)) else None)


def _safe_next(base, nxt):
    """登录后回到哪：只认本服务 base 下的路径（防跳到外站）。"""
    nxt = nxt or ""
    path = nxt.split("#", 1)[0].split("?", 1)[0]
    if (not nxt.startswith((base or "") + "/") or nxt.startswith("//") or "\\" in nxt or any(c in nxt for c in "\r\n")
            or "/../" in path + "/"):
        return (base or "") + "/"
    from urllib.parse import quote
    return quote(nxt, safe="/?&=#%:+,;@!$'()*~-._")       # 放进 Location 头：非 ASCII 要转义


def _page_script(base, rel, via):
    """登录模式下页面里加的脚本：接口回 401（登录过期）就跳登录页；老地址打开时，确认 cookie 能用就把地址栏换成不带口令的。"""
    login = json.dumps((base or "") + "/login")
    js = ("(function(){var L=" + login + ";var f=window.fetch;if(!f)return;"
          "window.fetch=function(){return f.apply(this,arguments).then(function(r){if(r.status===401)"
          "location.href=L+'?next='+encodeURIComponent(location.pathname+location.search+location.hash);return r;});};")
    if via == "token":
        clean = json.dumps((base or "") + rel)
        probe = json.dumps((base or "") + "/api/runs")
        js += ("f(" + probe + ",{credentials:'same-origin',cache:'no-store'}).then(function(r){if(r.ok)"
               "history.replaceState(null,'',(" + clean + ")+location.search+location.hash);}).catch(function(){});")
    js += "})();"
    return ("\n<script>" + js + "</script>").encode("utf-8")


LOGIN_HTML = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>登录 · 编排查看器</title>
<style>
body{font:15px/1.6 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f6f6f4;color:#222;
display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
form{background:#fff;border:1px solid #ddd;border-radius:10px;padding:28px 28px 22px;width:min(360px,90vw);box-shadow:0 2px 10px #0001}
h1{font-size:18px;margin:0 0 6px}p{margin:0 0 16px;color:#666;font-size:13px}
input[type=password]{width:100%;box-sizing:border-box;padding:9px 10px;border:1px solid #bbb;border-radius:6px;font-size:15px}
button{margin-top:14px;width:100%;padding:9px;border:0;border-radius:6px;background:#2d5be3;color:#fff;font-size:15px;cursor:pointer}
.err{color:#b3261e;font-size:13px;margin:10px 0 0}
</style></head><body>
<form method="post" action="login" autocomplete="off">
<h1>编排查看器</h1><p>输入访问口令。登录后 __DAYS__ 天内不用再输。</p>
<input type="password" name="key" placeholder="访问口令" autofocus required>
<input type="hidden" name="next" value="__NEXT__">
<button type="submit">登录</button>__ERR__
</form></body></html>"""


def login_page(base, nxt, error=""):
    import html as _html
    page = (LOGIN_HTML.replace("__NEXT__", _html.escape(_safe_next(base, nxt), quote=True))
            .replace("__DAYS__", str(max(1, SESSION_TTL // 86400)))
            .replace("__ERR__", f'<p class="err">{_html.escape(error)}</p>' if error else ""))
    return page.encode("utf-8")


MEETING_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".svg": "image/svg+xml", ".json": "application/json; charset=utf-8", ".png": "image/png"}


def meeting_dir():
    """会议页的静态文件目录：环境变量 TRACE_MEETING_DIR，默认 tools/meeting_web。"""
    return Path(os.environ.get("TRACE_MEETING_DIR") or Path(__file__).resolve().parent / "meeting_web")


def serve_meeting(rel, write=False, extra=b""):
    """<前缀>/meeting/ 下的静态页（人参加会议的界面）。和查看器同源同口令，接口用 ../api/…。
    html 和查看器页一样加上实时、可写的标记。"""
    root = meeting_dir().resolve()
    try:
        f = (root / (rel or "index.html")).resolve()
    except (OSError, ValueError):
        return respond_json({"error": "没有这个地址"}, 404)
    if root not in f.parents or not f.is_file() or f.suffix not in MEETING_TYPES:
        return respond_json({"error": "没有这个地址"}, 404)
    data = f.read_bytes()
    if f.suffix == ".html":
        meta = b'<head>\n<meta name="trace-live" content="1">'
        if write:
            meta += b'\n<meta name="trace-write" content="1">'
        data = data.replace(b"<head>", meta + extra, 1)
    return respond(200, data, MEETING_TYPES[f.suffix])


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
    base = _norm_base(base)
    normalized_headers = {}
    for key, value in headers.items():
        normalized_headers.setdefault(key.lower(), value)
    headers = normalized_headers
    rel, via = _auth(path, headers, token, base)
    if rel is None:
        return respond_json({"ok": False, "error": "没有这个地址"}, 404)
    host = (headers.get("host") or "").strip().lower()
    origin = (headers.get("origin") or "").strip().lower()
    if token and rel == "/login":
        # 登录表单：同源才收；表单编码；正文很小
        if origin and (origin == "null" or urlparse(origin).netloc != host):
            return respond_json({"ok": False, "error": "不接受别的网页发来的登录"}, 403)
        if (headers.get("content-type") or "").split(";")[0].strip().lower() != "application/x-www-form-urlencoded":
            return respond_json({"ok": False, "error": "Content-Type 要是 application/x-www-form-urlencoded"}, 415)
        try:
            size = int(headers.get("content-length") or 0)
        except ValueError:
            size = -1
        if size < 0 or size > 4096:
            return respond_json({"ok": False, "error": "请求体太大或没有长度"}, 413)
        return size
    if via is None:
        return respond_json({"ok": False, "error": "要先登录", "login": base + "/login"}, 401)
    path = rel
    op = path[len("/api/"):] if path.startswith("/api/") else ""
    if op not in _WRITE_OPS:
        return respond_json({"ok": False, "error": "没有这个地址"}, 404)
    if not write:
        return respond_json({"ok": False, "error": "这个查看服务是只读的（没有绑定本机地址、加了 --readonly，或带 --token 而没加 --write），不能在页面上操作"}, 403)
    # 别的网页不能借浏览器往这里发写请求：带 Origin 的要和 Host 是同一个；没有 --token 时 Host 还得是本机名
    # （防 DNS 重绑定：外面的域名解析到 127.0.0.1）。带 --token 时要登录（或老地址带口令），Host 可能是隧道的域名
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
    base = _norm_base(base)
    normalized_headers = {}
    for key, value in headers.items():
        normalized_headers.setdefault(key.lower(), value)  # HTTPMessage.get 取第一个同名头
    headers = normalized_headers
    rel, via = _auth(path, headers, token, base)
    if rel is None:
        return respond_json({"ok": False, "error": "没有这个地址"} if method == "POST" else {"error": "没有这个地址"}, 404)
    prefix = base + ("/" + token if via == "token" else "")       # 页面内跳转保持原来的地址形式

    if method == "GET":
        if rel == "":
            return respond(301, b"", "text/plain", {"Location": prefix + "/"})
        if token and rel == "/login":
            if via == "cookie":
                return respond(303, b"", "text/plain", {"Location": _safe_next(base, (parse_qs(query).get("next") or [""])[0])})
            return respond(200, login_page(base, (parse_qs(query).get("next") or [""])[0]), "text/html; charset=utf-8")
        if token and rel == "/logout":
            return respond(303, b"", "text/plain", {"Location": base + "/login",
                                                    "Set-Cookie": _set_cookie(base, "", headers, max_age=0)})
        if via is None:
            # 没登录：接口回 401（页面里的脚本据此跳登录页），页面直接跳登录页，登录后回来
            if rel.startswith("/api/"):
                return respond_json({"error": "要先登录", "login": base + "/login"}, 401)
            nxt = base + rel + ("?" + query if query else "")
            return respond(302, b"", "text/plain", {"Location": base + "/login?" + urlencode({"next": nxt})})
        page_extra, page_head = b"", {}
        if via in ("token", "cookie"):
            page_extra = _page_script(base, rel, via)
            if via == "token":           # 老地址打开页面：顺手发 cookie，脚本确认能用后把地址栏换成不带口令的
                page_head = {"Set-Cookie": _set_cookie(base, make_session(token), headers)}
        path = rel
        if path in ("/", "/index.html"):
            return respond(200, view_html(write, page_extra), "text/html; charset=utf-8", page_head)
        if path == "/meeting":
            return respond(301, b"", "text/plain", {"Location": prefix + "/meeting/"})
        if path.startswith("/meeting/"):
            code, head, data = serve_meeting(path[len("/meeting/"):], write, page_extra)
            if head.get("Content-Type", "").startswith("text/html"):
                head.update(page_head)
            return code, head, data
        if path == "/api/runs":
            return respond_json({"dir": runs.name if token else str(runs), "runs": list_runs(runs)})
        if path == "/api/entries":
            if not write:
                return respond_json({"error": "这个查看服务是只读的，不能启动运行"}, 403)
            wd = runs.resolve().parent
            return respond_json({"entries": list_entries(wd), "agents": read_agents({"workdir": str(wd)})})
        if path in ("/api/run", "/api/plan", "/api/workfiles"):
            name = (parse_qs(query).get("name") or [""])[0]
            if not _NAME.fullmatch(name):
                return respond_json({"error": "文件名不对"}, 400)
            p = (runs / name).resolve()
            if p.parent != runs.resolve() or not p.is_file():
                return respond_json({"error": f"没有 {name}"}, 400 if path == "/api/plan" else 404)
            if path == "/api/workfiles":
                # 工作目录的源码只给能写的查看服务（本机，或带 token 加 --write）：和交代码同一道门
                if not write:
                    return respond_json({"error": "这个查看服务是只读的，不能拉取工作目录"}, 403)
                wc = _ctl()
                try:
                    return respond_json(wc.workfiles(p))
                except wc.ControlError as e:
                    return respond_json({"error": str(e)}, 400)
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
        path = rel
        op = path[len("/api/"):]
        # HTTP handler 延迟读取：拒绝地址、权限和头部时不能等待客户端正文。
        if callable(body):
            body = body(size)
        if token and path == "/login":
            form = parse_qs(body[:size].decode("utf-8", "replace"))
            key = (form.get("key") or [""])[0]
            nxt = _safe_next(base, (form.get("next") or [""])[0])
            if not hmac.compare_digest(key.encode("utf-8", "replace"), token.encode("utf-8")):
                return respond(401, login_page(base, nxt, "口令不对"), "text/html; charset=utf-8")
            return respond(303, b"", "text/plain", {"Location": nxt,
                                                    "Set-Cookie": _set_cookie(base, make_session(token), headers)})
        try:
            body = json.loads(body[:size].decode("utf-8") or "null")
        except ValueError as e:
            return respond_json({"ok": False, "error": f"请求体不是 JSON：{e}"}, 400)
        if not isinstance(body, dict):
            return respond_json({"ok": False, "error": "请求体要是 JSON 对象"}, 400)
        if op == "start":
            code, out = start_run(runs, body)
            return respond_json(out, code)
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
    _ctl().pick_up_loop([runs.parent])      # 别的环境交结果时交给本服务起后台进程（见 workflow_ctl.pick_up）
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
