# -*- coding: utf-8 -*-
"""用 .zs 定义 HTTP 接口（Flask）。

    服务 8091-8099

    接口 POST /chat 动作 send
      用包 http
      消息 老师 收到了
    结束

    接口 POST /api/user
      如果 {id} 为空
        返回 {"code":400,"msg":"缺少 id"} 400
      结束
      返回 {"code":0,"data":{"id":"{id}"}}
    结束

跑起来：

    pip install flask
    py -m tools.dsl_http --list        只看有哪些接口
    py -m tools.dsl_http --mock        用假客户端跑，不消耗额度
    py -m tools.dsl_http --port 9000   精确指定，不做自动查找

## 两种返回方式

**返回**（通用）—— 像 Flask 的 return：给 JSON 就返回 JSON，给文本就
返回文本，末尾三位数是状态码。立即结束这个接口，所以早返回成立。

**消息 / 状态 / 响应**（配套 .ui 前端）—— 往固定的五个字段里塞内容，
塞完接着跑。字段是 messages / state / rows / stream / overlay。

同一个块里混用的话「返回」赢——它一出现脚本就结束了。

## 动作声明

接口行末尾可以加「动作 <名字>」，说明这个接口服务于 `.ui` 里的哪个
动作。`app2/build.py` 扫 routes/ 时把这些导出成端点表，加个接口前端
自动知道地址。

**为什么不靠约定自动推**：动作名和路径没有可靠对应，`send` 对的是
`/chat`。靠「动作名等于路径最后一段」的话现有路由全要改名，而路径是
给人看的 URL，不该迁就界面里的变量名。

没声明动作的接口是纯后端接口（给别的程序调的），界面不需要知道它们。

## 端口

脚本顶层声明：

    服务 8091          就用这一个，被占了报错
    服务 8091-8099     从 8091 往上找第一个空的

**范围写明而不是写「自动」**：部署时「这个服务可能占哪几个端口」是运维
要知道的信息，藏在实现里的默认范围没人看得见。

找到之后**必须大声打印实际用的端口**。不打印的话，前端连不上时人会
以为服务器没起来，而它其实在隔壁端口好好跑着。

命令行 `--port` 优先，**给了就不找**：命令行是精确指令，不该被自动
逻辑改写。被占了直接报错并给出查进程的命令——多数时候真正的问题是上次
的进程没退干净。

主机不在 DSL 里：同一份路由在本地和在服务器上绑的地址不一样，那是
部署环境的事。用 `--host`。

## 三层各管什么

    dsl.py            解析和执行脚本。不知道 HTTP 存在
    tools/http_ctx.py 请求上下文（threading.local），两边共用
    verbs/http/       消息 / 状态 / 响应 / 消息流 / 浮层，标准动词包
    这个文件          切接口块、注册 Flask 路由、注入请求参数和会话

引擎一行没动过 HTTP 的东西。`接口`、`服务`、`动作` 都不是 DSL 语句——
路由器切块时把那些行剥掉了，引擎收到的是块内的普通脚本。只有 `返回`
是真的引擎语句：它是控制流，跟 HTTP 无关。

## 为什么用 Flask 而不是 starlette

starlette 是 mcp 自带的——但它是 async，而 **DSL 引擎从头到尾同步
阻塞**。一次「问」要等模型几秒，在 async handler 里跑同步代码会卡住
整个事件循环，第二个请求只能干等。Flask 开发服务器默认多线程，跟同步
引擎是天然的搭配。生产环境该换 gunicorn 或 waitress。

## 状态

请求字段注入成变量：POST body 里的 `answer` 在脚本里就是 `{answer}`。
GET 的查询参数也注入。

会话状态注入成 `{会话.xxx}`，脚本跑完自动存回文件，按 `learner` 字段
分文件。脚本里不写读写语句——不然十个接口各写一遍。

**并发只做了一半**。锁保护读会话和写会话这两个瞬间，中间跑脚本的那
几秒没锁——同一个学习者的两个请求仍然会后写覆盖先写。单人本地用无
所谓；真要给别人用，得按会话 ID 加锁并持有整个请求周期。
"""

import argparse
import json
import re
import socket
import threading
import traceback
from pathlib import Path

from .dsl import DSLEngine, DSLError
from .http_ctx import set_bucket, take_bucket
from . import packs

# 接口 POST /chat 动作 send  ——  方法和动作都可省
API_RE = re.compile(
    r"^接口\s+(?:(GET|POST|PUT|DELETE)\s+)?(/\S*)"
    r"(?:\s+动作\s+(\S+))?\s*$", re.I)
# 服务 8091  或  服务 8091-8099
SERVICE_RE = re.compile(r"^服务\s+(\d{2,5})(?:\s*-\s*(\d{2,5}))?\s*$")

# 块内这些关键字会开一层，它们的「结束」不能被当成接口的收尾
INNER_OPENERS = {"如果", "若", "if", "遍历", "循环", "每个",
                 "逐项", "逐个", "each", "foreach", "事务", "tx"}
CLOSERS = {"结束", "end"}

# 接口脚本默认能用的包。脚本自己写「用包」会在这个基础上追加。
DEFAULT_PACKS = ["common", "http"]
DEFAULT_PORT = 8090

# 请求体上限，32MB。这是**整个请求**的上限，不是单个文件——多文件字段
# 加起来超了也会被拒。
#
# 界面上那个「最大 5MB」只管文件选择器，绕过前端直接发请求就没了，
# 真正的把关在这儿。
MAX_UPLOAD = 32 * 1024 * 1024


class Endpoint:
    """一个接口：方法、路径、服务的动作，以及块内那几行脚本。"""

    def __init__(self, method: str, path: str, body: list,
                 src: Path, line: int, action: str = ""):
        self.method = method.upper()
        self.path = path
        self.body = body
        self.src = src
        self.line = line
        self.action = action

    @property
    def script(self) -> str:
        return "\n".join(self.body)

    def __repr__(self) -> str:
        tail = f" 动作 {self.action}" if self.action else ""
        return f"<{self.method} {self.path}{tail} @{self.src.name}:{self.line}>"


def split_endpoints(text: str, src: Path):
    """切出接口块，顺带读走顶层的「服务」声明。

    返回 (接口列表, 端口范围)，端口范围是 (起, 止) 或 None。
    """
    lines = text.splitlines()
    out = []
    ports = None
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        sm = SERVICE_RE.match(stripped)
        if sm:
            if ports is None:
                lo = int(sm.group(1))
                hi = int(sm.group(2)) if sm.group(2) else lo
                if hi < lo:
                    raise DSLError(
                        f"{src.name} 第 {i + 1} 行：端口范围反了（{lo}-{hi}）")
                ports = (lo, hi)
            i += 1
            continue

        m = API_RE.match(stripped)
        if not m:
            i += 1
            continue

        depth, body, j = 1, [], i + 1
        while j < len(lines):
            head = lines[j].strip().split(" ")[0]
            if head in INNER_OPENERS:
                depth += 1
            elif head in CLOSERS:
                depth -= 1
                if depth == 0:
                    break
            body.append(lines[j])
            j += 1
        else:
            raise DSLError(f"{src.name} 第 {i + 1} 行的「接口」没有对应的「结束」")

        out.append(Endpoint(m.group(1) or "POST", m.group(2), body,
                            src, i + 1, action=m.group(3) or ""))
        i = j + 1
    return out, ports


def scan_routes(root: Path):
    """扫描目录下所有 .zs。返回 (接口表, 端口范围, 警告)。"""
    table = {}
    ports = None
    port_src = ""
    warns = []
    if not root.is_dir():
        return table, ports, warns

    for f in sorted(root.rglob("*.zs")):
        eps, p = split_endpoints(f.read_text(encoding="utf-8"), f)
        if p is not None:
            if ports is None:
                ports, port_src = p, f.name
            elif p != ports:
                # 取第一个并说出来。静默忽略的话，「为什么端口不是我写的
                # 那个」会变成一件要翻文件才知道的事。
                warns.append(f"{f.name} 也声明了端口 {p[0]}-{p[1]}，"
                             f"已按 {port_src} 的 {ports[0]}-{ports[1]} 为准")
        for ep in eps:
            key = (ep.method, ep.path)
            if key in table:
                old = table[key]
                raise DSLError(
                    f"接口重复：{ep.method} {ep.path} 同时出现在 "
                    f"{old.src.name}:{old.line} 和 {ep.src.name}:{ep.line}")
            table[key] = ep
    return table, ports, warns


def endpoints_of(routes_dir) -> dict:
    """扫路由目录，返回 {动作名: 路径}。给前端生成器用。

    只收声明了「动作」的接口——没声明的是纯后端接口，界面不需要知道。

    同一个动作名被两个接口声明时报错而不是取一个：那种情况下界面到底
    发到哪儿完全看扫描顺序，静默选一个会让人调半天。
    """
    table, _, _ = scan_routes(Path(routes_dir))
    out = {}
    seen = {}
    for (method, path), ep in sorted(table.items()):
        if not ep.action:
            continue
        if ep.action in out:
            raise DSLError(
                f"动作「{ep.action}」被两个接口声明：{out[ep.action]}"
                f"（{seen[ep.action]}）和 {path}"
                f"（{ep.src.name}:{ep.line}）")
        out[ep.action] = path
        seen[ep.action] = f"{ep.src.name}:{ep.line}"
    return out


def port_free(host: str, port: int) -> bool:
    """试着绑一下看端口空不空。

    绑完立刻关，中间有极小的窗口可能被别人抢走——真起服务时仍然可能撞。
    但这个探测的用途是给出像样的错误信息，不是保证，所以够用。
    """
    with socket.socket() as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def pick_port(host: str, lo: int, hi: int):
    """从 lo 到 hi 找第一个空端口。返回 (端口, 跳过了几个)。

    全占了返回 (None, 试过的个数)——调用方据此报错，而不是在这里抛：
    报错信息要带上排查命令，那是 main 的事。
    """
    for i, port in enumerate(range(lo, hi + 1)):
        if port_free(host, port):
            return port, i
    return None, hi - lo + 1


class Router:
    def __init__(self, routes: Path, workspace: Path, sessions: Path,
                 real: bool = True, verbose: bool = False):
        self.routes_dir = Path(routes)
        self.workspace = Path(workspace)
        self.sessions_dir = Path(sessions)
        self.real = real
        self.verbose = verbose
        self.table, self.ports, self.warnings = scan_routes(self.routes_dir)
        self._lock = threading.Lock()

    # ---- 会话 ----

    def _session_path(self, who: str) -> Path:
        # 只留安全字符：会话 ID 来自请求体，直接当文件名等于开放路径注入
        safe = re.sub(r"[^\w\-.\u4e00-\u9fff]", "_", who or "默认") or "默认"
        return self.sessions_dir / f"{safe}.json"

    def load_session(self, who: str) -> dict:
        p = self._session_path(who)
        if not p.is_file():
            return {}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # 坏了就当空的重来——会话状态不值得为它中断请求
            return {}
        return data if isinstance(data, dict) else {}

    def save_session(self, who: str, data: dict) -> None:
        p = self._session_path(who)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                     encoding="utf-8")

    # ---- 执行 ----

    def _client(self):
        if not self.real:
            from .mock import MockClient
            return MockClient()
        from .zhipu import ZhipuClient
        return ZhipuClient()

    def handle(self, ep: Endpoint, form: dict, uploads: dict = None):
        """跑一个接口，返回 (响应体, 状态码)。

        uploads 是这次请求带的文件。它们不进 form——脚本要用就调「存文件」
        动词，那时才决定存哪儿、怎么命名。
        """
        who = str(form.get("learner") or form.get("会话") or "默认")
        with self._lock:
            session = self.load_session(who)

        set_bucket({}, uploads)
        text = ""
        returned = None
        try:
            engine = DSLEngine(
                self._client(),
                workdir=self.workspace,
                verbose=self.verbose,
                verbs=packs.registry(DEFAULT_PACKS, self.workspace),
                verbs_root=packs.verbs_root(),
            )
            # 请求字段直接当变量：{answer}、{learner} 在脚本里可用
            engine.vars.update(form)
            engine.vars["会话"] = session

            text = engine.run(ep.script)
            returned = engine.returned

            # 脚本改了会话就存回去。「返回」提前结束的情况下也要存——
            # 早返回之前做的状态变更同样有效。
            after = engine.vars.get("会话")
            if isinstance(after, dict):
                with self._lock:
                    self.save_session(who, after)
        finally:
            # 异常路径也要清，否则线程复用时下个请求读到残留
            bucket = take_bucket()

        # 「返回」赢：它一出现脚本就结束了，消息那套没意义
        if returned is not None:
            return returned[0], returned[1]

        out = dict(bucket)
        # 脚本里的「打印」没进响应字段，但调试时有用，兜底塞进 messages
        if text.strip() and not out.get("messages"):
            out["messages"] = [{"who": "", "text": text}]
        return out, 200

    def _read_request(self):
        """读请求体，返回 (字段表, 上传的文件表)。

        两种 Content-Type：

        **application/json** —— 老路子。`.ui` 生成的前端把字段包在 `form`
        里，所以要摊平一层。

        **multipart/form-data** —— 界面上有文件字段时前端改发这个。文本
        字段在 request.form 里（同样包在 `form` 里，只是变成了 JSON 字符
        串），文件在 request.files 里。

        文件**不进字段表**：字段表的值全是字符串，脚本里 `{头像}` 取到的
        得是能插进 SQL 的东西。所以这里只把文件对象单独收着，交给动词去
        决定存哪儿、怎么命名——那是策略，不该写死在路由器里。

        脚本不管它们的话，文件对象随请求结束一起丢掉，什么也没留下。
        """
        from flask import request

        uploads = {}

        if request.content_type and "multipart" in request.content_type:
            form = dict(request.form)
            # 前端把字段包在 form 里，multipart 下那是个 JSON 字符串
            inner = form.pop("form", None)
            if inner:
                try:
                    parsed = json.loads(inner)
                    if isinstance(parsed, dict):
                        form.update(parsed)
                except json.JSONDecodeError:
                    # 不是 JSON 就当普通字段留着——总比整个丢掉强
                    form["form"] = inner
            uploads = dict(request.files)
            return form, uploads

        form = request.get_json(silent=True) or {}
        if not isinstance(form, dict):
            form = {}
        # 兼容 .ui 生成的前端：它把字段包在 form 里
        inner = form.get("form")
        if isinstance(inner, dict):
            form = {**form, **inner}
        return form, uploads

    def dispatch(self):
        from flask import request, jsonify

        key = (request.method.upper(), request.path)
        ep = self.table.get(key)
        if ep is None:
            return jsonify({"messages": [
                {"who": "出错", "text": f"没有这个接口：{key[0]} {key[1]}",
                 "kind": "no"}]}), 404

        form, uploads = self._read_request()
        # GET 的查询参数也注入，跟 body 字段并列
        for k, v in request.args.items():
            form.setdefault(k, v)

        try:
            body, status = self.handle(ep, form, uploads)
            # 纯文本返回不包 JSON——「返回 ok」就该是 ok
            if isinstance(body, str):
                return body, status
            return jsonify(body), status
        except DSLError as e:
            return jsonify({"messages": [
                {"who": "脚本出错", "text": f"{ep.src.name}: {e}",
                 "kind": "no"}]}), 500
        except Exception:
            return jsonify({"messages": [
                {"who": "出错", "text": traceback.format_exc(limit=3),
                 "kind": "no"}]}), 500

    # ---- 启动 ----

    def app(self):
        from flask import Flask

        app = Flask(__name__)
        # 中文不转义成 \uXXXX，调试时看得懂
        app.json.ensure_ascii = False
        # 请求体上限。不设的话传个 1GB 的文件会整个读进内存——而且是在
        # 脚本跑起来之前，动词里的检查根本来不及。超了 Flask 直接回 413。
        app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD

        # 同一路径可能有多个方法，按路径合并注册一次
        by_path = {}
        for method, path in self.table:
            by_path.setdefault(path, set()).add(method)
        for path, methods in by_path.items():
            app.add_url_rule(path, endpoint=path, view_func=self.dispatch,
                             methods=sorted(methods))
        return app

    def describe(self) -> str:
        if not self.table:
            return f"{self.routes_dir} 下没有找到任何「接口」块"
        lines = [f"路由目录 {self.routes_dir}",
                 f"工作目录 {self.workspace}",
                 f"会话目录 {self.sessions_dir}"]
        if self.ports:
            lo, hi = self.ports
            lines.append(f"脚本端口 {lo}" + (f"-{hi}" if hi != lo else ""))
        lines.append("")
        for (m, p), ep in sorted(self.table.items()):
            动作 = f"  动作 {ep.action}" if ep.action else ""
            lines.append(f"  {m:6} {p:24} {ep.src.name}:{ep.line}{动作}")
        for w in self.warnings:
            lines.append(f"\n  [警告] {w}")
        return "\n".join(lines)


def resolve_port(host: str, cli_port, ports):
    """定下用哪个端口。返回 (端口, 说明)，端口为 None 表示失败。

    命令行给了就用它，不做查找——命令行是精确指令，不该被自动逻辑改写。
    被占了直接报错：多数时候真正的问题是上次的进程没退干净，换个端口
    只是掩盖它。
    """
    if cli_port is not None:
        if port_free(host, cli_port):
            return cli_port, "命令行"
        return None, (
            f"{cli_port} 被占用了（命令行指定的端口不会自动换）。\n"
            f"  换一个：--port {cli_port + 1}\n"
            f"  或者找出占用它的进程：netstat -ano | findstr :{cli_port}")

    if ports is None:
        if port_free(host, DEFAULT_PORT):
            return DEFAULT_PORT, "默认"
        return None, (
            f"{DEFAULT_PORT} 被占用了，而且脚本里没有「服务」声明。\n"
            f"  加一行：服务 {DEFAULT_PORT}-{DEFAULT_PORT + 9}\n"
            f"  或者：--port 9000")

    lo, hi = ports
    port, skipped = pick_port(host, lo, hi)
    if port is None:
        return None, (
            f"{lo}-{hi} 全被占用了（试了 {skipped} 个）。\n"
            f"  把范围放宽，或者看看是不是上次的进程没退：\n"
            f"  netstat -ano | findstr :{lo}")
    if skipped:
        # 大声说出来：不说的话前端连不上时人会以为服务器没起来，
        # 而它其实在隔壁端口好好跑着
        return port, f"脚本 {lo}-{hi}，前 {skipped} 个被占"
    return port, f"脚本 {lo}" + (f"-{hi}" if hi != lo else "")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description="用 .zs 定义 HTTP 接口")
    p.add_argument("--routes", default=str(root / "routes"))
    p.add_argument("--workspace", default=str(packs.DATA_ROOT))
    p.add_argument("--sessions", default=None, help="默认是 workspace/sessions")
    p.add_argument("--host", default="127.0.0.1")
    # 默认 None 而不是数字：要能区分「用户显式给了 --port」和「没给」，
    # 才能让脚本里的「服务」声明在没给时生效
    p.add_argument("--port", type=int, default=None,
                   help="精确指定端口，不做自动查找")
    p.add_argument("--mock", action="store_true", help="用假客户端，不消耗额度")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--list", action="store_true", help="只列接口，不启动")
    args = p.parse_args()

    ws = Path(args.workspace)
    sessions = Path(args.sessions) if args.sessions else ws / "sessions"

    try:
        router = Router(Path(args.routes), ws, sessions,
                        real=not args.mock, verbose=args.verbose)
    except DSLError as e:
        print(f"路由加载失败：{e}")
        return 1

    print(router.describe())
    if args.list:
        return 0
    if not router.table:
        return 1

    try:
        app = router.app()
    except ImportError:
        print("\n缺 flask：pip install flask")
        return 1

    port, 来源 = resolve_port(args.host, args.port, router.ports)
    if port is None:
        print(f"\n{来源}")
        return 1

    print(f"\n监听 http://{args.host}:{port}（{来源}）"
          + ("" if not args.mock else "，假客户端"))
    # threaded=True 是重点：模型调用要等几秒，单线程的话第二个请求只能
    # 干等。debug 关掉——自动重载会把路由表读两遍。
    app.run(host=args.host, port=port, threaded=True, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
