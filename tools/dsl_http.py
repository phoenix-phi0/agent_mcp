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

会话状态注入成 `{session.xxx}`，脚本跑完自动存回文件，按 `learner` 字段
分文件。脚本里不写读写语句——不然十个接口各写一遍。

**并发只做了一半**。锁保护读会话和写会话这两个瞬间，中间跑脚本的那
几秒没锁——同一个学习者的两个请求仍然会后写覆盖先写。单人本地用无
所谓；真要给别人用，得按会话 ID 加锁并持有整个请求周期。

## 认证

路由目录里任何一个 .zs 的顶层（接口块外面）写这些行，对整个项目生效：

    认证 必须                     一直要登录，只有标了「公开」的接口例外
    认证 可选                     默认不要登录（跟没写一样）；启动时开了登录
                                  （Router(login=True)、gen run --登录、
                                  dsl_http --登录）才等同「认证 必须」
    认证 核对 app.db user_auth    每个请求认出 cookie 里的人之后，再用这条查询
                                  （queries/user_auth.sql，参数 :username）查一次：
                                  查不到（停用了、删了）就当没登录——令牌本身
                                  无状态，靠这一步让停用立即生效。查到的行里
                                  role 列注入成 {current_role}
    认证 身份 learner 默认 me     注入「这个请求是谁的数据」：开着登录时是
                                  {current_user}，请求体里同名的字段一律盖掉
                                  （{learner} 和 {request.learner} 都是），前端
                                  伪造无效；没开登录时是请求体里的 learner，
                                  没给或空串就是 me（单人用，跟以前每个接口开头
                                  「{learner 或} 空了补 me」那段一样）
    认证 角色 teacher 教师        角色的中文名，拒绝时说「需要教师权限」
    认证 角色 student 学生 拒绝 教师账号不参与学习，请用学生账号
                                  「拒绝」后面是别人调「只许 学生」的接口时
                                  403 的说明（整句，可以有空格）；不写是
                                  「需要学生权限」

接口行上的「角色 teacher」或「只许 教师」（两种写法一样，后者用中文名，按上面
的「认证 角色」对回 teacher）：开着登录时只许 {current_role} 是这个角色的人调，
别人回 403。没开登录时不查（单人用，管理侧照常可用）。

    接口 POST /import/home 动作 import_home 角色 teacher
    接口 POST /report/home 动作 report_home 只许 教师
    接口 POST /quiz/answer 动作 quiz_answer 只许 学生

写了没声明的中文角色名（「只许 校长」）启动时记一条警告：开着登录时谁都 403。

注入的变量（都放在请求字段之后，请求体里的同名字段盖不掉）：

    current_user   登录的用户名；没开登录或没登录是空串
    current_role   核对查询返回的 role；没有是空串
    auth_mode      on（这次启动要求登录）/ off

令牌是无状态的签名串（tools/auth.py）：退出只删 cookie，偷走的令牌过期前
都有效。「认证 核对」挡住的是停用和删号；改密码不会让旧令牌失效。
"""

import argparse
import json
import os
import re
import socket
import sys
import threading
import traceback
from pathlib import Path

from .dsl import DSLEngine, DSLError
from .http_ctx import set_bucket, take_auth, take_bucket
from . import packs

# 接口 POST /chat 动作 send 公开  ——  方法、动作、公开、角色都可省
# 接口 POST /import/home 动作 import_home 角色 teacher
# 接口 POST /quiz/answer 动作 quiz_answer 只许 学生   —— 「只许」跟「角色」一样，
#                                    写中文名，按「认证 角色」对回角色代号
API_RE = re.compile(
    r"^接口\s+(?:(GET|POST|PUT|DELETE)\s+)?(/\S*)"
    r"(?:\s+动作\s+(\S+))?(\s+公开)?(?:\s+(?:角色|只许)\s+(\S+))?\s*$", re.I)
# 服务 8091  或  服务 8091-8099
SERVICE_RE = re.compile(r"^服务\s+(\d{2,5})(?:\s*-\s*(\d{2,5}))?\s*$")
# 认证 必须 —— 路由目录里任何一个文件写了这行，所有接口都要求登录，
# 只有标了「公开」的例外。不写这行的项目行为完全不变。
AUTH_RE = re.compile(r"^认证\s+必须\s*$")
# 认证 可选 —— 平时不要登录，启动时开了登录（--登录）才等同「认证 必须」。
# 单人本机用和多人用同一份路由，不用两套文件。见文件开头「认证」一节
AUTH_OPTIONAL_RE = re.compile(r"^认证\s+可选\s*$")
# 认证 核对 app.db user_auth —— 每个请求按用户名再查一次（停用立即生效、拿角色）
AUTH_CHECK_RE = re.compile(r"^认证\s+核对\s+(\S+)\s+(\S+)\s*$")
# 认证 身份 learner 默认 me —— 注入「这是谁的数据」
AUTH_IDENTITY_RE = re.compile(r"^认证\s+身份\s+([A-Za-z_]\w*)\s+默认\s+(\S+)\s*$")
# 认证 角色 teacher 教师 —— 角色的中文名，403 的说明里用
# 认证 角色 student 学生 拒绝 教师账号不参与学习，请用学生账号 —— 别人调「只许
# 学生」的接口时 403 说这句（整句，到行尾）
AUTH_ROLE_RE = re.compile(r"^认证\s+角色\s+(\S+)\s+(\S+)(?:\s+拒绝\s+(.+?))?\s*$")
# 开了登录、监听的又不是本机时，cookie 走明文 http 会被同网段的人截走
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")

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
    """一个接口：方法、路径、服务的动作，以及块内那几行脚本。

    public 为真表示标了「公开」：项目开了「认证 必须」时，只有这种接口
    不登录也能调（登录、注册本身）。

    role 是「角色 teacher」：开着登录时只许这个角色调，别人 403。
    """

    def __init__(self, method: str, path: str, body: list,
                 src: Path, line: int, action: str = "", public: bool = False,
                 role: str = ""):
        self.method = method.upper()
        self.path = path
        self.body = body
        self.src = src
        self.line = line
        self.action = action
        self.public = public
        self.role = role

    @property
    def script(self) -> str:
        return "\n".join(self.body)

    def __repr__(self) -> str:
        tail = f" 动作 {self.action}" if self.action else ""
        tail += " 公开" if self.public else ""
        tail += f" 角色 {self.role}" if self.role else ""
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
                            src, i + 1, action=m.group(3) or "",
                            public=bool(m.group(4)), role=m.group(5) or ""))
        i = j + 1
    return out, ports


def auth_required(root: Path) -> bool:
    """路由目录里有没有哪个文件写了「认证 必须」（顶层，接口块外面）。

    一个文件写了就对整个项目生效：认证是项目级的开关，不是某个文件的
    事——不然新加一个路由文件忘了写这行，里面的接口就全是公开的。
    """
    return top_level_flag(root, AUTH_RE)


def top_level_flag(root: Path, pattern) -> bool:
    """路由目录里有没有哪个 .zs 在顶层（接口块外面）写了匹配 pattern 的一行。

    项目级开关都这么写：「认证 必须」，「迁移 只加」（见 tools/migrate.py）。
    接口块里的同样一行不算——那是脚本内容，不是声明。
    """
    return bool(top_level_matches(root, pattern))


def top_level_matches(root: Path, pattern) -> list:
    """顶层匹配 pattern 的行，返回 match 对象的列表（按文件名、行号）。"""
    out = []
    if not Path(root).is_dir():
        return out
    for f in sorted(Path(root).rglob("*.zs")):
        depth = 0
        for line in f.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if API_RE.match(s):
                depth = 1
                continue
            head = s.split(" ")[0] if s else ""
            if depth:
                if head in INNER_OPENERS:
                    depth += 1
                elif head in CLOSERS:
                    depth -= 1
                continue
            m = pattern.match(s)
            if m:
                out.append(m)
    return out


def auth_config(root: Path) -> dict:
    """读路由目录里的认证声明。见文件开头「认证」一节。

    返回 {"mandatory", "optional", "check": (库, 查询名) 或 None,
          "identity": (变量名, 单人默认值) 或 None, "roles": {角色: 中文名}}
    同一种声明写了两次不一样的，报错——哪个算数全看扫描顺序的话，查起来很难。
    """
    def one(pattern, what):
        ms = top_level_matches(root, pattern)
        vals = {m.groups() for m in ms}
        if len(vals) > 1:
            raise DSLError(f"「认证 {what}」写了不一样的几行：{sorted(vals)}")
        return ms[0].groups() if ms else None

    return {
        "mandatory": top_level_flag(root, AUTH_RE),
        "optional": top_level_flag(root, AUTH_OPTIONAL_RE),
        "check": one(AUTH_CHECK_RE, "核对"),
        "identity": one(AUTH_IDENTITY_RE, "身份"),
        "roles": {m.group(1): m.group(2) for m in top_level_matches(root, AUTH_ROLE_RE)},
        "deny": {m.group(1): m.group(3) for m in top_level_matches(root, AUTH_ROLE_RE)
                 if m.group(3)},
    }


def listen_warning(host: str, login: bool) -> str:
    """监听的不是本机时，启动日志里醒目地提醒一句。返回空串表示不用提醒。"""
    if host in LOCAL_HOSTS:
        return ""
    bar = "!" * 64
    lines = [bar, f"!! 监听 {host}：同一网络里的其他机器都能连上来。"]
    if login:
        lines += ["!! 开着登录：这是明文 http，密码和登录 cookie 可能被同网段的人截走。",
                  "!! 对外请放在 https 反向代理后面，并加 --安全cookie（cookie 只走 https）。"]
    else:
        lines += ["!! 没开登录：谁连上来都能用，管理页也一样。多人用请加 --登录。"]
    lines.append(bar)
    return "\n".join(lines)


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

    **探测要跟真起服务用同样的选项**：Flask（werkzeug）起服务时设了
    SO_REUSEADDR，所以刚停掉的服务留下的 TIME_WAIT 挡不住它。探测不设的
    话会比真实情况更悲观——停掉服务马上重启，报「端口被占用」，而其实
    完全能绑上。并发测试连跑两遍时撞上的。

    Windows 上不设：那边 SO_REUSEADDR 的意思是「可以抢别人正在监听的
    端口」，设了探测就永远说空闲。
    """
    with socket.socket() as s:
        if os.name != "nt":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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


def _model_failure(exc):
    """顺着错误链找模型调用抛的那个异常（dsl_model 打了 model_call 标记）。
    跟 db_errors.find_client_error 一个找法。"""
    seen = set()
    while exc is not None and id(exc) not in seen:
        if getattr(exc, "model_call", False):
            return exc
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return None


class Router:
    def __init__(self, routes: Path, workspace: Path, sessions: Path,
                 real: bool = True, verbose: bool = False, login: bool = False,
                 secure_cookie: bool = False):
        self.routes_dir = Path(routes)
        self.workspace = Path(workspace)
        self.sessions_dir = Path(sessions)
        self.real = real
        self.verbose = verbose
        self.table, self.ports, self.warnings = scan_routes(self.routes_dir)
        # 「认证 必须」一直开；「认证 可选」看启动时给没给 login。两样都没写的
        # 项目给了 login 是报错而不是悄悄不认人——以为开了登录、其实谁都能进
        cfg = auth_config(self.routes_dir)
        if login and not (cfg["mandatory"] or cfg["optional"]):
            raise DSLError("开登录要路由里有「认证 可选」或「认证 必须」这一行"
                           "（这个项目没有登录功能，先 py -m gen auth 项目/）")
        self.auth_required = cfg["mandatory"] or (cfg["optional"] and bool(login))
        self.auth_check = cfg["check"]
        self.identity = cfg["identity"]
        self.role_labels = cfg["roles"]
        self.role_deny = cfg["deny"]
        # 「只许 学生」写的是中文名：对回角色代号（student），之后一律按代号比。
        # 对不上的（没声明的名字）原样留着，记一条警告——开着登录时谁都 403
        by_label = {label: code for code, label in self.role_labels.items()}
        for ep in self.table.values():
            if ep.role in by_label:
                ep.role = by_label[ep.role]
            elif ep.role and self.role_labels and ep.role not in self.role_labels:
                self.warnings.append(f"{ep.src.name}:{ep.line} 接口 {ep.path} 的角色「{ep.role}」"
                                     f"没有用「认证 角色」声明（开着登录时谁都 403）")
        # cookie 只走 https。本机 http 不能开（浏览器就不发了），对外部署到
        # https 后面时开
        self.secure_cookie = bool(secure_cookie)
        self._key = None
        self._lock = threading.Lock()
        self.client_factory = None

    def _secret(self) -> bytes:
        """签名密钥，第一次用到时才读或生成（在 workspace/.auth_secret）。
        没开认证的项目永远不会碰到这里，不会凭空多出一个密钥文件。"""
        if self._key is None:
            from .auth import secret_for
            self._key = secret_for(self.workspace)
        return self._key

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

    @property
    def mode(self) -> str:
        """real 用真模型客户端，其余（--mock、没传 --real）是 mock。"""
        return "real" if self.real else "mock"

    def _client(self):
        # 测试把它换成自己的工厂，拿到每次请求用的客户端（看发了什么提示词、
        # 用的哪一档模型）
        if self.client_factory:
            return self.client_factory()
        if not self.real:
            # 离线：「用 快」这类写法也不会真去调 claude -p。环境变量
            # DSL_MOCK_SCRIPT 指向规则文件时按它回（浏览器测试用）
            from .mock import MockClient
            return MockClient.from_env(offline=True)
        from .zhipu import ZhipuClient
        return ZhipuClient()

    def handle(self, ep: Endpoint, form: dict, uploads: dict = None,
               user: str = ""):
        """跑一个接口，返回 (响应体, 状态码)。要登录/退出要求的用 run。"""
        body, status, _ = self.run(ep, form, uploads, user)
        return body, status

    def run(self, ep: Endpoint, form: dict, uploads: dict = None,
            user: str = "", info: dict = None, remote: str = ""):
        """跑一个接口，返回 (响应体, 状态码, 登录/退出要求)。

        uploads 是这次请求带的文件。它们不进 form——脚本要用就调「存文件」
        动词，那时才决定存哪儿、怎么命名。

        user 是路由器从 cookie 认出来的当前用户，没登录是空串。它以
        {current_user} 交给脚本，并且**强制覆盖** {request} 里的同名字段——
        请求体是前端给的，前端塞一个「current_user: 别人」进来，不能让
        「写库表 … {request}」把它绑进 SQL。

        路由器注入的变量都是英文名（跟脚本变量的命名约定一致）：
          request       整个请求体（字典）
          current_user  登录的用户名，没登录是空串
          session       会话状态（字典），改了自动存回
          run_mode      real / mock，当前是不是假客户端
          current_role  「认证 核对」查出的 role，没有是空串
          auth_mode     on / off，这次启动要不要登录
          以及「认证 身份」声明的那个变量（kg 是 learner）
        它们放在请求字段之后，请求体里伪造的同名字段盖不掉。

        info 是「认证 核对」查出的那一行（字典），没有是 None。
        """
        # 会话按谁分：登录了按用户名——那是服务器认出来的。没登录才退回
        # 请求里的 learner 字段；开了认证的项目里，没登录能走到这儿的只有
        # 公开接口，统一放进一个匿名会话，不让请求体挑会话文件。
        if user:
            who = user
        elif self.auth_required:
            who = "_匿名"
        else:
            who = str(form.get("learner") or form.get("session") or "默认")

        # 会话只在用得到时才读、变了才写。
        #
        # 早先每个请求都读一次、写一次——增删改查的接口一处会话都不用，
        # 也照样往 sessions/ 里写一个 默认.json，白做一次磁盘写入。
        #
        # 「用得到」看脚本文本里有没有「session」。「执行」的子脚本不用另算：
        # 子脚本是独立作用域，看不到父脚本的变量，要用会话只能由父脚本显式
        # 传 `执行 子.zs session={session}`——那一行里本来就有「session」。
        # 文本里碰巧出现这个词（比如字典键）只是多读一次，不影响对错。
        needs_session = "session" in ep.script
        session = {}
        if needs_session:
            with self._lock:
                session = self.load_session(who)
        before = json.dumps(session, ensure_ascii=False, sort_keys=True)

        set_bucket({}, uploads, user, remote)
        text = ""
        returned = None
        auth = None
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
            # 请求体整个给一份，写库表这类动词收字典时用
            engine.vars["request"] = dict(form)
            # 当前用户放在请求字段之后，盖掉请求体里可能伪造的同名字段
            engine.vars["current_user"] = user
            engine.vars["request"]["current_user"] = user
            role = str((info or {}).get("role") or "") if user else ""
            engine.vars["current_role"] = role
            engine.vars["request"]["current_role"] = role
            auth_mode = "on" if self.auth_required else "off"
            engine.vars["auth_mode"] = auth_mode
            engine.vars["request"]["auth_mode"] = auth_mode
            # 「认证 身份 learner 默认 me」：开着登录时就是登录的人，请求体里
            # 的 learner 连 {request} 里的一起盖掉——前端塞别人的名字进来，
            # 读写的仍是自己的数据。没开登录是单人用：照旧认请求体，没给
            # 是 me（那时没什么要防的，测试也靠它分开不同的学习者）
            if self.identity:
                var, default = self.identity
                if self.auth_required:
                    engine.vars[var] = user
                    engine.vars["request"][var] = user
                else:
                    engine.vars[var] = str(form.get(var) or "") or default
            engine.vars["session"] = session
            # 当前是不是假客户端：mock / real。只读，放在最后盖掉请求体里的同名字段
            engine.vars["run_mode"] = self.mode
            engine.vars["request"]["run_mode"] = self.mode

            text = engine.run(ep.script)
            returned = engine.returned

            # 脚本改了会话就存回去。「返回」提前结束的情况下也要存——
            # 早返回之前做的状态变更同样有效。
            #
            # 跟进来时比一下，没变就不写：只读会话的接口（查题号、看进度）
            # 不该每次都重写一遍文件。
            after = engine.vars.get("session")
            if isinstance(after, dict) and json.dumps(
                    after, ensure_ascii=False, sort_keys=True, default=str) != before:
                with self._lock:
                    self.save_session(who, after)
        finally:
            # 异常路径也要清，否则线程复用时下个请求读到残留
            bucket = take_bucket()
            auth = take_auth()

        # 「返回」赢：它一出现脚本就结束了，消息那套没意义
        if returned is not None:
            return returned[0], returned[1], auth

        out = dict(bucket)
        # 脚本里的「打印」没进响应字段，但调试时有用，兜底塞进 messages
        if text.strip() and not out.get("messages"):
            out["messages"] = [{"who": "", "text": text}]
        return out, 200, auth

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
            # .ui 生成的前端（app.js.j2 的 postTo）把整个请求体 {action, form}
            # 塞成一个 JSON 字符串放在 payload 里。早先这里只认 form 键，前端
            # 发的 payload 原样留成一个字段，表单里的字段脚本一个都拿不到——
            # 文件存下了，系列编号、显示名全是空的，而且不报错
            payload = form.pop("payload", None)
            if payload:
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    body = parsed.get("form")
                    if isinstance(body, dict):
                        form.update(body)
                    if parsed.get("action") and "action" not in form:
                        form["action"] = parsed["action"]
                else:
                    form["payload"] = payload
            # 手拼 multipart 的调用方（dsl/test_upload.py）把字段包在 form 里，
            # 那是个 JSON 字符串
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

    def _identify(self, request) -> str:
        """从 cookie 认出当前用户，认不出是空串。

        没开认证的项目不认人：{current_user} 一律是空串，也不会去读或生成
        签名密钥。
        """
        if not self.auth_required:
            return ""
        from .auth import COOKIE, read_token
        return read_token(request.cookies.get(COOKIE), self._secret())

    def check_user(self, user: str):
        """「认证 核对」：按用户名查一次，返回那一行（字典），查不到 None。

        令牌只证明「签发时这个人登录过」。停用、删号要立刻生效，就得每个
        请求回库里看一眼——一条按唯一键的查询，代价很小。没写「核对」的
        项目照旧只认令牌。
        """
        if not user:
            return None
        if not self.auth_check:
            return {}
        import sqlite3
        db, name = self.auth_check
        ws = self.workspace.resolve()
        qdir = ws / "queries"
        if not qdir.is_dir():
            qdir = Path(__file__).resolve().parent.parent / "queries"
        f = (qdir / f"{name}.sql").resolve()
        dbp = (ws / db).resolve()
        if qdir.resolve() not in f.parents or ws not in dbp.parents:
            raise DSLError(f"「认证 核对」的库或查询越界：{db} {name}")
        if not f.is_file():
            raise DSLError(f"「认证 核对」的查询不在：{f}")
        con = sqlite3.connect(dbp)
        con.row_factory = sqlite3.Row
        try:
            row = con.execute(f.read_text(encoding="utf-8"), {"username": user}).fetchone()
        finally:
            con.close()
        return dict(row) if row is not None else None

    def _apply_auth(self, resp, auth) -> None:
        """按动词的要求设或删登录 cookie。

        HttpOnly：页面上的 JS 读不到它，被注入了脚本也偷不走。
        SameSite=Lax：别的网站发来的跨站 POST 不带它，挡住大部分 CSRF。
        没设 Secure：本机跑的是 http，设了浏览器就不发了。部署到 https
        时要加上。
        """
        if not auth:
            return
        from .auth import COOKIE, TTL, make_token
        if auth.get("login"):
            resp.set_cookie(COOKIE, make_token(auth["login"], self._secret()),
                            max_age=TTL, httponly=True, samesite="Lax", path="/",
                            secure=self.secure_cookie)
        elif auth.get("logout"):
            resp.delete_cookie(COOKIE, path="/", samesite="Lax",
                               secure=self.secure_cookie)

    def dispatch(self):
        from flask import jsonify, make_response, request

        key = (request.method.upper(), request.path)
        ep = self.table.get(key)
        if ep is None:
            return jsonify({"messages": [
                {"who": "出错", "text": f"没有这个接口：{key[0]} {key[1]}",
                 "kind": "no"}]}), 404

        user = self._identify(request)
        info = None
        stale = False
        if user:
            info = self.check_user(user)
            if info is None:
                # 令牌是真的，但人停用了或删了：当没登录，顺手把 cookie 删掉
                user, stale = "", True
        # 默认拒绝：开了认证的项目，没标「公开」的接口一律要登录。检查在
        # 路由器里而不是在每个接口的脚本里——手写的接口忘了写那一行，就是
        # 一个不设防的口子，而且不报错。
        if self.auth_required and not ep.public and not user:
            resp = make_response(jsonify({"error": "请先登录"}), 401)
            if stale:
                self._apply_auth(resp, {"logout": True})
            return resp
        # 「角色 teacher」：开着登录时查角色。没开登录是单人用，不查
        if self.auth_required and ep.role and str((info or {}).get("role") or "") != ep.role:
            label = self.role_labels.get(ep.role, ep.role)
            return jsonify({"error": self.role_deny.get(ep.role) or f"需要{label}权限"}), 403

        form, uploads = self._read_request()
        # GET 的查询参数也注入，跟 body 字段并列
        for k, v in request.args.items():
            form.setdefault(k, v)

        try:
            body, status, auth = self.run(ep, form, uploads, user, info,
                                          request.remote_addr or "")
            # 纯文本返回不包 JSON——「返回 ok」就该是 ok
            resp = make_response(body if isinstance(body, str) else jsonify(body),
                                 status)
            self._apply_auth(resp, auth or ({"logout": True} if stale else None))
            return resp
        except DSLError as e:
            # 用户造成的错（重名、必填为空……）：引擎一层层包成 DSLError，
            # 原来那个挂在错误链上。找到了就回它的状态码和人话，不当成
            # 服务器故障回 500。
            from .db_errors import find_client_error
            ce = find_client_error(e)
            if ce is not None:
                return jsonify({"error": ce.message}), ce.status
            # 模型那头出错（dsl_model 的「问」打的标记）：不是脚本写错了，
            # 回 502 和一句人话放在 error 里——没有消息流的界面弹提示条，
            # 有流的进流。原文进日志
            mc = _model_failure(e)
            if mc is not None:
                print(f"[模型出错] {ep.src.name}: {mc}", file=sys.stderr, flush=True)
                why = (str(mc).strip().splitlines() or [type(mc).__name__])[0][:120]
                return jsonify({"error": f"模型这次没有回应（{why}），过一会儿再试。"}), 502
            print(f"[接口出错] {ep.src.name}: {e}", file=sys.stderr, flush=True)
            return jsonify({"messages": [
                {"who": "脚本出错", "text": f"{ep.src.name}: {e}",
                 "kind": "no"}]}), 500
        except Exception as e:
            from .db_errors import find_client_error
            ce = find_client_error(e)
            if ce is not None:
                return jsonify({"error": ce.message}), ce.status
            mc = _model_failure(e)
            if mc is not None:
                print(f"[模型出错] {ep.src.name}: {mc}", file=sys.stderr, flush=True)
                why = (str(mc).strip().splitlines() or [type(mc).__name__])[0][:120]
                return jsonify({"error": f"模型这次没有回应（{why}），过一会儿再试。"}), 502
            print(f"[接口出错] {ep.src.name}:\n{traceback.format_exc(limit=3)}",
                  file=sys.stderr, flush=True)
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
        if self.auth_required:
            lines.append("登录     要求登录（多人模式）"
                         + ("，cookie 只走 https" if self.secure_cookie else ""))
        if self.ports:
            lo, hi = self.ports
            lines.append(f"脚本端口 {lo}" + (f"-{hi}" if hi != lo else ""))
        lines.append("")
        for (m, p), ep in sorted(self.table.items()):
            动作 = f"  动作 {ep.action}" if ep.action else ""
            动作 += f"  角色 {ep.role}" if ep.role else ""
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
    p.add_argument("--登录", dest="login", action="store_true",
                   help="路由写了「认证 可选」的项目：这次启动要求登录")
    p.add_argument("--安全cookie", dest="secure_cookie", action="store_true",
                   help="登录 cookie 只走 https（放在 https 反向代理后面时开）")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--list", action="store_true", help="只列接口，不启动")
    args = p.parse_args()

    ws = Path(args.workspace)
    sessions = Path(args.sessions) if args.sessions else ws / "sessions"

    try:
        router = Router(Path(args.routes), ws, sessions,
                        real=not args.mock, verbose=args.verbose,
                        login=args.login, secure_cookie=args.secure_cookie)
    except DSLError as e:
        print(f"路由加载失败：{e}")
        return 1

    print(router.describe())
    if args.list:
        return 0

    # 路由里写了「迁移 只加」：起服务前给工作区的 app.db 补上实体后加的表和列
    # （tools/migrate.py）。没写的项目这一步什么都不做
    from .migrate import migrate_project
    for line in migrate_project(ws, Path(args.routes)):
        print(line)
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
    warn = listen_warning(args.host, router.auth_required)
    if warn:
        print(warn, flush=True)
    # threaded=True 是重点：模型调用要等几秒，单线程的话第二个请求只能
    # 干等。debug 关掉——自动重载会把路由表读两遍。
    app.run(host=args.host, port=port, threaded=True, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
