# -*- coding: utf-8 -*-
"""中文关键字的小型 DSL 引擎。

完整语法见 Notion「MCP 服务器」页，或 dsl_help 工具。这里只列速查表。

    用包 common quiz           声明动词包，同时开启严格模式
    模型/系统/温度             配置。「模型 快」只管本脚本（含它调起的子脚本），
                               不改共用的客户端；名字可以是档位（快/平衡/强）、
                               别名或模型真名，见下面「模型档位」
    设 name = 值               变量（右侧是纯变量引用时保留结构）
    设 card.title = 值         往结构里写，中间层不存在会自动建
    问 reply = 提示词          调模型
    问JSON data = 提示词       要 JSON，直接得到结构
    流式 reply = 提示词        边生成边打印
    对话 reply = 提示词        多轮，保留历史
    重置 / 读历史 文件 / 存历史 文件
    修剪历史 20 8000字         条数和字数两个上限，谁先触发听谁的
    打印 / 保存 / 追加
    读取 text = 文件           纯文本
    读JSON data = 文件         对象或列表
    读JSONL rows = 文件        对象列表
    遍历 word 于 甲，乙 … 结束  列表变量可直接遍历
    遍历 item 于 {rows} 序号 i  序号从 1 开始，循环里用 {i}
    {name 或 默认}             取不到或为空就用默认；{name 或} 取空
    逐项 word 于 列表 … 结束    自动加标题和输出
    如果 条件 … 否则 … 结束
    事务 库 … 结束             块内的写入要么全成要么全败
    执行 sub.zs key=值          独立作用域，key 在子脚本里就是 {key}
    判定 verdict_of = 提示词 键→输出 … 否则→输出
    返回 值 [状态码]           结束脚本并交出一个值

命名约定：变量名、脚本参数（「执行 x.zs key=值」的 key）、SQL 参数
（.sql 里的 :limit）用英文 snake_case；关键字（设、如果、遍历、问…）、动词名、
动词参数名（拆选项 的 题干/题型——传给中文动词的参数字典，键是中文）、
界面名、显示文本用中文。引擎照样认中文变量名（标识符按 Python 的
isidentifier 判，中英文、下划线、数字都行），约定只管仓库里的脚本，
tests/dsl/test_naming.py 会查。英文变量名别用关键字的英文别名（set、if、
end、reset、verdict… 见 dsl_core.KEYWORDS）和 in。

HTTP 接口里路由器注入的变量（英文名，放在请求字段之后，请求体伪造不了）：

    {request}        整个请求体（字典），写库表这类动词收它
    {current_user}   登录的用户名，没登录是空串
    {session.xxx}    会话状态，改了自动存回
    {run_mode}       real / mock，当前是不是假客户端

请求的表单字段、地址参数直接就是变量（{learner}、{lesson}）。局部变量跟
它们同名时含义要一样（设 learner = {learner 或} 补默认值可以），别用一个
同名的局部变量盖掉后面还要读的请求字段。

三个后缀（挂在 问/问JSON/流式/对话/系统 末尾）：

    附 a.md,b.md               挂载文件，内容拼在提示词前面
    带工具 挑题,题目数 最多 3 轮  让模型自己调动词
    重试 3 次 直到 包含 答案     结果不满足就重来

还有一个只管这一次的模型后缀（问/问JSON/流式/对话，必须写在最末尾）：

    问 答 = 提示词 用 快        「快」得是档位、别名、ASCII 的模型名
                               （glm-4-flash、api:zhipu/glm-5.3）、带通道
                               前缀的名字或 {变量}；别的词（如「用 中文」）
                               不认，留在提示词里

模型名的规范写法是「通道:提供方/模型」：

    api:zhipu/glm-5.3          智谱 HTTP API
    api:anthropic/<模型>        预留，还没接入（调用时报「api:anthropic 还没接入」）
    cli:claude/haiku           本机 Claude Code（claude -p，haiku/sonnet/opus）；
                               cli:claude 不带模型 = 它自己的默认
    cli:zcode                  本机 ZCode（zcode -p）；不能选模型，
                               写 cli:zcode/xx 报错

    兼容：裸名 glm-5.3 = api:zhipu/glm-5.3；旧写法 claude:sonnet =
    cli:claude/sonnet，zcode / zcode:xx = cli:zcode（后半忽略）。照旧能用，
    python -m tools.config 会标「旧写法，建议改成 …」。

API 和 CLI 的差别（能力表在 config.BACKENDS）：

    能力      api（智谱）   cli（claude / zcode）
    带工具    支持          不支持：报错，说出规范名和能力
    流式      真流式        降级：等整段生成完一次性返回，不报错
    温度      支持          忽略
    对话历史  原样发        拼成一段文字发过去

    CLI 每次起一个进程，慢（claude 十秒上下）；吃 Claude 订阅 / Z.AI 账号
    的额度；在空的临时目录里纯问答，读不到项目文件。同时最多跑 2 个进程
    （DSL_CLAUDE_MAX_PROCS / DSL_ZCODE_MAX_PROCS），单次超时 180 秒
    （DSL_CLAUDE_TIMEOUT / DSL_ZCODE_TIMEOUT）。

    Windows 上的 Python：本机没装 claude / zcode 时自动经 wsl.exe 调 WSL
    里装的（cli_via_wsl，默认 "auto"；true 强制走 WSL，false 不走）。
    提示词、系统提示词经标准输入 base64 传过去，不怕中文、换行、引号、
    $ % ^ & 之类。发行版 wsl_distro、WSL 里的路径 wsl_claude_bin /
    wsl_zcode_bin 可选；环境变量 DSL_CLI_VIA_WSL / DSL_WSL_DISTRO /
    DSL_WSL_CLAUDE_BIN / DSL_WSL_ZCODE_BIN 优先于 config.json。
    python -m tools.config 显示现在是本机调还是经 WSL 调。细节见 llm_router。

模型档位（项目根的 models.json，不含密钥，可以提交 git）：

    {"default": "平衡",
     "tiers":   {"快": "api:zhipu/glm-5.3-flashx", "平衡": "api:zhipu/glm-5.3-flash",
                 "强": "api:zhipu/glm-5.3"},
     "aliases": {"克": "cli:claude/sonnet", "z": "cli:zcode"}}

    模型 快                    之后的问/对话都用「快」档
    问 答 = 提示词 用 强        只这一次用「强」档
    问 答 = 提示词 用 克        只这一次走本机 claude -p --model sonnet
    模型 cli:claude/sonnet     名字直接写规范名也行
    Agent(model="平衡")         Python 里一样写档位名
    别名可以指向档位（{"大": "强"}），只解析一层；档位和别名不能重名。
    config.json 旧的 models 别名表照样认，跟 models.json 重名时 models.json 优先。
    不写模型：环境变量 ZHIPU_MODEL > config.json 的 model > default 档位 > 内置默认。
    查看当前的档位表和别名表：python -m tools.config

档位的备用模型（fallback，写了才生效）：

    "tiers": {"强": {"model": "cli:claude/opus", "fallback": "api:zhipu/glm-5.3"}}

    「用 强」平时走 claude；这一句需要主模型没有的能力（带工具）时改用
    fallback，并记一条 warning 日志（档位、原模型、改用模型、原因）。
    没写 fallback 就直接报错；fallback 自己也没有那个能力也报错。
    fallback 要写模型名，不能写档位/别名。别名只能是字符串，不支持
    fallback，但别名指向档位时继承档位的 fallback。

## 文件是怎么拆的

    dsl_core.py      常量、值处理、条件求值。全是纯函数，不碰状态
    dsl_model.py     ModelMixin：问/问JSON/流式/对话/判定/挂载/带工具
    dsl_history.py   HistoryMixin：读存修剪对话历史
    dsl.py（本文件） 解析、执行、动词调用、事务、单条语句

拆之前是一千四百行，改一行要整个重写，而这条链路上每次全文件写入都
有把 MCP 服务器压垮的风险——实际崩过两次。

mixin 而不是独立的类，是因为那些方法离不开引擎状态（client、history、
verbs、_emit……）。做成独立类就要把七八样东西传来传去，或者反过来持有
引擎引用，那跟 mixin 是同一件事，只是多绕一道。代价是隐式依赖：mixin
里用到的 self.xxx 定义在这里，改属性名要记得搜那两个文件。

dsl_core 的东西在这里重新导出，所以 `from tools.dsl import to_text,
DSLError, RESERVED` 这类老写法不受影响。
"""

import json
from pathlib import Path

from .config import resolve_model
from .zhipu import ZhipuClient
from .llm_router import wrap as wrap_client
from .verbs import VerbRegistry, VerbError
from .dsl_history import HistoryMixin
from .dsl_model import ModelMixin

# 重新导出，保持 `from tools.dsl import X` 的老写法能用
from .dsl_core import (  # noqa: F401
    BLOCK_OPENERS, CALL_PARAM_RE, DSLError, EMPTY_FORMS, IN_WORDS,
    KEYWORDS, MAX_CALL_DEPTH, PACK_SEP_RE, RESERVED, RET_STATUS_RE,
    ScriptReturn, TX_BEGIN, TX_COMMIT, TX_ROLLBACK, VAR_RE, VERB_LIKE_RE,
    as_number, check_name, dig, eval_parts, is_empty, iter_items, msg_size,
    normalize, parse_condition, put, split_condition_tail, split_head,
    split_items, to_text,
)

import re
import threading

# 「用包」加载动词包时持有。动词表可能被多个线程共用（见 _do_use）。
# 只在真加载时才会等：包加载过一次之后，后面的「用包」查一下就跳过了。
_USE_LOCK = threading.RLock()


class DSLEngine(ModelMixin, HistoryMixin):
    def __init__(self, client: ZhipuClient | None = None,
                 workdir: Path | None = None, verbose: bool = True,
                 verbs: VerbRegistry | None = None,
                 verbs_root: Path | str | None = None,
                 _depth: int = 0):
        # 套一层按模型通道分派的（cli:claude/… / cli:zcode 走本机 CLI），见 llm_router
        self.client = wrap_client(client or ZhipuClient())
        self.workdir = (Path(workdir) if workdir else Path.cwd()).resolve()
        self.verbose = verbose
        self.verbs = verbs
        self.verbs_root = Path(verbs_root) if verbs_root else None
        # 「用包」之后转严格模式：不认识的动词名报错，不当文本
        self.strict_verbs = False
        self._depth = _depth

        # 值可以是 str，也可以是读文件或动词返回的 dict / list
        self.vars: dict = {}
        self.system: str | None = None
        self.temperature: float = 0.7
        # 「模型 X」设在引擎上，不改 client.model：客户端是子脚本、HTTP
        # 并发请求、agent 共用的，改它会串到别人那里。None = 客户端默认
        self.model: str | None = None
        self.history: list = []
        self.output: list = []
        # 「返回」交出来的东西：(值, 状态码)。没返回过就是 None——
        # 调用方靠这个区分「脚本主动返回了」和「跑完了什么也没说」
        self.returned: tuple | None = None
        # 逐项块的自动输出用它。必须是实例属性——类属性会让父子引擎
        # 共享初值，嵌套调用时读到上一轮的残留。
        self._last_result: str = ""

    # ------------------------------------------------------------------
    # 变量
    # ------------------------------------------------------------------

    def lookup(self, expr: str):
        """按变量名或点号路径取原始值。先查完整名再拆点号——
        变量名本身含点号时不会被误拆。"""
        expr = expr.strip()
        if expr in self.vars:
            return self.vars[expr]
        if "." in expr:
            head, _, path = expr.partition(".")
            if head.strip() in self.vars:
                return dig(self.vars[head.strip()], path)
        return None

    def store(self, name: str, value) -> None:
        """给变量赋值，支持点号路径。

        头部变量不存在或者不是结构时，建一个空字典再往里写——这样
        「设 session.code = x」在会话还没有任何内容时也能用。
        """
        name = name.strip()
        if "." not in name:
            self.vars[name] = value
            return
        head, _, path = name.partition(".")
        head = head.strip()
        if not isinstance(self.vars.get(head), (dict, list)):
            self.vars[head] = {}
        if not put(self.vars[head], path, value):
            raise DSLError(
                f"写不进去：{name}。中间某一层不是字典或列表，或者下标越界")

    def expand(self, text: str) -> str:
        """{变量名} 替换成值，未定义的原样保留——为了拼写错时看得见。

        **{名字 或 默认值}**：取不到就用默认值，取到空值也用。

        原样保留是有意的：`{项.标题}` 写成 `{项.标提}` 时，库里会写进
        「{项.标提}」这串字，看一眼就知道哪儿错了；换成空字符串反而查不出。

        但导入这类场景要的正相反——可选字段本来就常常没有，每个字段都先
        判空太啰嗦。所以给一个显式的写法，而不是改掉默认行为：想要「缺了
        当空」就写 `{项.after 或 }`，什么都不写默认值就是空。
        """
        def repl(m):
            body = m.group(1)
            # 「或」两边要有空格，否则「甲或乙」这种普通变量名会被误切
            head, sep, alt = body.partition(" 或 ")
            if not sep:
                head, sep, alt = body.partition(" 或")   # {名 或} 取空
            got = self.lookup(head.strip())
            if sep:
                # 取不到（None）、空串、空列表、空字典都算「没有」，用默认值。
                # 不走 is_empty：那个函数是给字符串用的，拿到 None 会炸。
                blank = got is None or (hasattr(got, "__len__") and not len(got))
                return alt.strip() if blank else to_text(got)
            return m.group(0) if got is None else to_text(got)
        return VAR_RE.sub(repl, text)

    def _resolve_items(self, raw: str):
        """整个就是一个变量引用时取原始值，否则展开成文本。

        这是结构化变量能用于循环的关键：展开成文本的话列表变成 JSON
        字符串，列表身份丢失，只能按逗号硬拆——而 JSON 里本来就有逗号，
        拆出来全是碎片。
        """
        raw = raw.strip()
        m = VAR_RE.fullmatch(raw)
        if m:
            body = m.group(1)
            # 「或 默认值」这里也要认，不然 `设 后 = {项.after 或}` 走不通：
            # lookup 拿整串「项.after 或」去查，查不到，变量没建起来，
            # 后面再引用只会看到 {后} 原样保留。
            head, sep, alt = body.partition(" 或 ")
            if not sep:
                head, sep, alt = body.partition(" 或")
            got = self.lookup(head.strip())
            if sep:
                blank = got is None or (hasattr(got, "__len__") and not len(got))
                return alt.strip() if blank else got
            if got is not None:
                return got
        return self.expand(raw)

    # ------------------------------------------------------------------
    # 输出与路径
    # ------------------------------------------------------------------

    def _emit(self, text: str) -> None:
        self.output.append(text)
        if self.verbose:
            print(text)

    def _safe_path(self, name: str) -> Path:
        p = (self.workdir / name).resolve()
        if p != self.workdir and self.workdir not in p.parents:
            raise DSLError(f"路径越界，只能读写工作目录内的文件：{name}")
        return p

    def _rel(self, p: Path) -> str:
        try:
            return p.relative_to(self.workdir).as_posix()
        except ValueError:
            return str(p)

    def _read_file(self, rest: str, kw: str):
        name, fname = self._split_assign(rest, kw)
        path = self._safe_path(self.expand(fname))
        if not path.is_file():
            raise DSLError(f"文件不存在：{self._rel(path)}")
        return name, path

    def _split_file_arg(self, rest: str, kw: str):
        fname, _, content = rest.partition(" ")
        if not fname:
            raise DSLError(f"「{kw}」的语法应为：{kw} 文件名 内容")
        path = self._safe_path(self.expand(fname))
        return path, self.expand(content.strip()).replace("\\n", "\n")

    def _split_assign(self, rest: str, kw: str):
        name, sep, value = rest.partition("=")
        if not sep:
            raise DSLError(f"「{kw}」的语法应为：{kw} 变量名 = 内容")
        return check_name(name.strip()), value.strip()

    def _sub_engine(self) -> "DSLEngine":
        """共享客户端与动词表的子引擎。

        history 不继承——子脚本独立作用域，要接着聊就自己「读历史」。
        """
        sub = DSLEngine(client=self.client, workdir=self.workdir,
                        verbose=False, verbs=self.verbs,
                        verbs_root=self.verbs_root, _depth=self._depth + 1)
        sub.system = self.system
        sub.temperature = self.temperature
        sub.model = self.model
        sub.strict_verbs = self.strict_verbs
        return sub

    def _is_verb(self, head: str) -> bool:
        return (self.verbs is not None and head not in RESERVED
                and self.verbs.has(head))

    # ------------------------------------------------------------------
    # 条件
    # ------------------------------------------------------------------

    def _eval_condition(self, cond: str, lineno: int) -> bool:
        left, op, right = parse_condition(self.expand(cond), lineno)
        return eval_parts(left, op, right)

    def _eval_against(self, value: str, cond: str, lineno: int) -> bool:
        """条件省略左值时，拿 value 当左值。"""
        cond = self.expand(cond).strip()
        tail = split_condition_tail(cond)
        if tail is not None:
            return eval_parts(value, tail[0], tail[1])
        left, op, right = parse_condition(cond, lineno)
        return eval_parts(left, op, right)

    # ------------------------------------------------------------------
    # 解析与执行
    # ------------------------------------------------------------------

    def run(self, script: str) -> str:
        lines = [normalize(ln).rstrip() for ln in script.splitlines()]
        try:
            self._exec_block(lines, 0, len(lines))
        except ScriptReturn as r:
            # 不是错误，是脚本主动收尾。调用方读 self.returned。
            self.returned = (r.value, r.status)
        return "\n".join(self.output)

    def run_file(self, path) -> str:
        p = Path(path)
        if not p.is_absolute():
            p = self.workdir / p
        return self.run(p.read_text(encoding="utf-8"))

    def _find_block(self, lines: list, start: int, stop: int):
        depth = 0
        else_at = None
        for i in range(start, stop):
            head, _ = split_head(lines[i].strip())
            if head in BLOCK_OPENERS:
                depth += 1
            elif head == "end":
                depth -= 1
                if depth == 0:
                    return else_at, i
            elif head == "else" and depth == 1:
                if else_at is not None:
                    raise DSLError(f"第 {i + 1} 行：同一个分支里有多个「否则」")
                else_at = i
        raise DSLError(f"第 {start + 1} 行的块没有对应的「结束」")

    def _exec_block(self, lines: list, start: int, stop: int) -> None:
        i = start
        while i < stop:
            line = lines[i].strip()
            if not line or line.startswith("#"):
                i += 1
                continue

            head, rest = split_head(line)

            if head in ("each", "foreach"):
                name, items, seq = self._parse_each(rest, i)
                else_at, end = self._find_block(lines, i, stop)
                if else_at is not None:
                    raise DSLError(f"第 {else_at + 1} 行：循环里不能直接写「否则」")
                for n, item in enumerate(iter_items(items), 1):
                    self.vars[name] = item
                    if seq:
                        self.vars[seq] = n
                    if head == "foreach":
                        self._emit(f"── {to_text(item)} ──")
                        mark = len(self.output)
                        self._last_result = ""
                        self._exec_block(lines, i + 1, end)
                        # 块内没打印任何东西时，自动输出最后一次生成结果
                        if len(self.output) == mark and self._last_result:
                            self._emit(self._last_result)
                    else:
                        self._exec_block(lines, i + 1, end)
                i = end + 1
                continue

            if head == "tx":
                else_at, end = self._find_block(lines, i, stop)
                if else_at is not None:
                    raise DSLError(f"第 {else_at + 1} 行：事务里不能写「否则」")
                self._run_tx(lines, i + 1, end, self.expand(rest).strip(), i)
                i = end + 1
                continue

            if head == "if":
                if not rest:
                    raise DSLError(f"第 {i + 1} 行：「如果」后面要跟条件")
                else_at, end = self._find_block(lines, i, stop)
                if self._eval_condition(rest, i):
                    self._exec_block(lines, i + 1, else_at if else_at else end)
                elif else_at is not None:
                    self._exec_block(lines, else_at + 1, end)
                i = end + 1
                continue

            if head == "else":
                raise DSLError(f"第 {i + 1} 行：「否则」没有对应的「如果」")
            if head == "end":
                raise DSLError(f"第 {i + 1} 行：多余的「结束」")

            if self._is_verb(head):
                try:
                    self._do_verb(head, rest, i)
                except VerbError as e:
                    raise DSLError(f"第 {i + 1} 行：{e}") from e
                i += 1
                continue

            try:
                self._exec_stmt(head, rest, i)
            except (DSLError, ScriptReturn):
                # ScriptReturn 要穿透出去，不能被下面那个兜底 except 包成
                # DSLError——那样「返回」就成报错了
                raise
            except Exception as e:
                raise DSLError(f"第 {i + 1} 行执行失败：{e}") from e
            i += 1

    def _parse_each(self, rest: str, lineno: int):
        """循环头。返回 (变量名, 要遍历的东西, 序号变量名或空)。

        「遍历 项 于 {表} 序号 i」：序号从 1 开始，循环里用 {i}。

        为什么要显式写而不是自动给一个 {序号}：自动的话，嵌套循环里内层
        会悄悄盖掉外层的，而且脚本里读到 {序号} 也看不出它从哪来。显式
        写出来，名字是自己起的，嵌套时各叫各的。

        序号解决的是「逐条报错要说第几条」——导入器早先只能用 Python 写，
        就是因为这个：几百行的文件里，不说第几行等于没报。
        """
        seq = ""
        m = re.search(r"\s+序号\s+(\S+)\s*$", rest)
        if m:
            seq = check_name(m.group(1), lineno)
            rest = rest[:m.start()]
        if "=" in rest:
            name, _, items = rest.partition("=")
            return (check_name(name.strip(), lineno),
                    self._resolve_items(items), seq)
        for word in IN_WORDS:
            m = re.match(rf"^(.+?)\s*{re.escape(word)}\s+(.+)$", rest)
            if m:
                return (check_name(m.group(1).strip(), lineno),
                        self._resolve_items(m.group(2)), seq)
        raise DSLError(f"第 {lineno + 1} 行：循环语法应为"
                       f"「遍历 名 于 甲，乙，丙」，可选「序号 i」")

    # ------------------------------------------------------------------
    # 事务
    # ------------------------------------------------------------------

    def _call_tx_verb(self, name: str, target: str) -> None:
        """调事务的三个动词之一。

        只有「事务开始」要知道库名，「事务提交」和「事务回滚」用的是
        已经挂在连接上的那个——所以按动词自己声明的参数个数决定传不传，
        而不是一律传一个。先前一律传库名，零参数的「事务提交」会报
        「最多接受 0 个参数」。
        """
        args = [target] if (target and self.verbs.params_of(name)) else []
        params = self.verbs.bind(name, args)
        kind, impl = self.verbs.resolve(name)
        if kind != "python":
            raise DSLError(f"「{name}」必须是 Python 动词")
        result = to_text(impl(**params))
        if result.startswith("["):
            # 动词用 [出错] 这种前缀报问题。事务的三个时刻出错都要让脚本
            # 停下——继续跑下去写入会落在没有事务的连接上。
            raise DSLError(f"{name} 失败：{result}")

    def _run_tx(self, lines: list, start: int, end: int,
                target: str, lineno: int) -> None:
        """跑一个事务块。

        引擎不认识数据库——只在三个时刻调三个约定好的动词。语义由 db 包
        提供，换个存储就换个包，引擎不用改。

        「返回」在事务里算成功：脚本主动收尾不是错误，已经做的写入该留下。
        """
        for name in (TX_BEGIN, TX_COMMIT, TX_ROLLBACK):
            if not self._is_verb(name):
                raise DSLError(
                    f"第 {lineno + 1} 行：「事务」需要动词「{name}」，"
                    f"块外先写「用包 db」")

        self._call_tx_verb(TX_BEGIN, target)
        try:
            self._exec_block(lines, start, end)
        except ScriptReturn:
            self._call_tx_verb(TX_COMMIT, target)
            raise
        except Exception:
            # 回滚失败不能盖掉原始错误——那才是人要看的东西
            try:
                self._call_tx_verb(TX_ROLLBACK, target)
            except Exception as e2:
                self._emit(f"[回滚也失败了] {type(e2).__name__}: {e2}")
            raise
        self._call_tx_verb(TX_COMMIT, target)

    # ------------------------------------------------------------------
    # 动词包
    # ------------------------------------------------------------------

    def _do_use(self, rest: str, lineno: int) -> None:
        """用包 common quiz —— 声明依赖，同时开启严格模式。"""
        names = [x for x in PACK_SEP_RE.split(rest.strip()) if x]
        if not names:
            raise DSLError(f"第 {lineno + 1} 行：「用包」后面要跟包名")

        root = self.verbs_root or (self.workdir / "verbs")
        if not root.is_dir():
            raise DSLError(f"第 {lineno + 1} 行：找不到动词包目录 {root}。"
                           f"创建引擎时传 verbs_root，或在工作目录下建 verbs/")

        if self.verbs is None:
            self.verbs = VerbRegistry(reserved=RESERVED)

        for name in names:
            pack = root / name
            if not pack.is_dir():
                有哪些 = ", ".join(sorted(p.name for p in root.iterdir()
                                          if p.is_dir())) or "无"
                raise DSLError(f"第 {lineno + 1} 行：没有动词包「{name}」。"
                               f"{root} 下有：{有哪些}")
            # 「查过没加载」和「加载」要在一把锁里：HTTP 接口的动词表是按包
            # 组合缓存、所有请求共用的（packs.registry），两个请求同时跑到
            # 「用包 db」，都看到 db 还没加载，就各加载一遍——第二遍每个动词
            # 报一条「被重复注册」，这些警告进了脚本输出，又被路由器兜底塞进
            # messages，出现在做题页的消息流里。端到端测试撞上的，时有时无。
            #
            # 警告也在锁里取走、只报自己这次加载出来的：警告列表同样是共用的，
            # 不这样的话别的请求会把这次的警告当成自己的打印出来。
            with _USE_LOCK:
                # 已加载过就跳过——父子脚本各声明一次同一个包很常见
                if name in self.verbs.packs:
                    continue
                self.verbs.load_pack(pack, workspace=self.workdir)
                mine = list(self.verbs.warnings)
                self.verbs.warnings.clear()
            for w in mine:
                self._emit(f"[动词包] {w}")

        self.strict_verbs = True

        # 加载警告不能吞：包里的 _verbs.py 出错时动词会静悄悄少几个，
        # 后面报「没有这个动词」时根本想不到是加载阶段就失败了。上面每加载
        # 一个包就报它自己的；这里报的是加载之前就攒着的（建动词表时的）
        with _USE_LOCK:
            early = list(self.verbs.warnings)
            self.verbs.warnings.clear()
        for w in early:
            self._emit(f"[动词包] {w}")

    def _check_unknown_verb(self, head: str, rest: str, lineno: int) -> None:
        """严格模式下，右侧长得像动词调用但查不到时报错。

        判据是「有参数 + 名字不含空格标点」。会误判「设 甲 = 明天 下午」
        这类中文文本——先用宽判据是有意的，静默错误的代价比误报大。
        """
        if not rest.strip() or not VERB_LIKE_RE.match(head):
            return
        if head in RESERVED or as_number(head) is not None:
            return
        known = self.verbs.names() if self.verbs else []
        近似 = [n for n in known if head in n or n in head]
        提示 = f"，是不是想写「{'」「'.join(近似[:3])}」" if 近似 else ""
        raise DSLError(
            f"第 {lineno + 1} 行：没有名为「{head}」的动词{提示}。"
            f"这行如果本来就是一段文本，改成不以词+空格开头的写法；"
            f"严格模式由「用包」开启，去掉那行即可回到宽松模式。")

    def _do_verb(self, name: str, rest: str, lineno: int,
                 assign_to: str | None = None) -> None:
        """执行一个动词。参数转文本，但返回值保留结构。"""
        args = [self.expand(a) for a in rest.split()] if rest.strip() else []
        params = self.verbs.bind(name, args)
        kind, impl = self.verbs.resolve(name)

        if kind == "python":
            result = impl(**params)
            # 结构原样留着——str() 一个 dict 会得到 Python 字面量
            # （单引号、True 而不是 true），拿去 json.loads 都解析不了
            if result is None:
                result = ""
            elif not isinstance(result, (str, dict, list, int, float, bool)):
                result = str(result)
        else:
            if self._depth >= MAX_CALL_DEPTH:
                raise DSLError(f"动词调用层数超过 {MAX_CALL_DEPTH}，"
                               f"可能存在循环调用")
            sub = self._sub_engine()
            sub.vars.update(params)
            text = sub.run(Path(impl).read_text(encoding="utf-8"))
            result = sub.returned[0] if sub.returned else text

        self._deliver(result, assign_to)

    def _deliver(self, result, assign_to: str | None) -> None:
        """存进变量或逐行输出。存变量时保留原始类型——动词返回的列表
        要还能拿去遍历；输出时才转文本，因为 output 是字符串列表。"""
        text = to_text(result)
        self._last_result = text
        if assign_to:
            self.store(assign_to, result)
        elif text:
            for line in text.splitlines():
                self._emit(line)

    # ------------------------------------------------------------------
    # 返回与子脚本
    # ------------------------------------------------------------------

    def _do_return(self, rest: str, lineno: int) -> None:
        """返回 值 [状态码] —— 结束脚本并交出一个值。

        值是合法 JSON 就当结构交出去，否则当文本。末尾的三位数当状态码，
        用三位而不是任意数字是为了让「返回 200」这种把数字当内容的写法
        还能成立。
        """
        text = rest.strip()
        status = 200
        m = RET_STATUS_RE.search(text)
        if m:
            status = int(m.group(1))
            text = text[:m.start()].strip()

        value = self._resolve_items(text)
        if isinstance(value, str):
            s = value.strip()
            if s.startswith(("{", "[")):
                try:
                    value = json.loads(s)
                except json.JSONDecodeError:
                    # 解析不了就当文本，不报错——返回一段以 { 开头的普通
                    # 文字是合法的，为这个中断请求没道理
                    pass
        raise ScriptReturn(value, status)

    def _do_call(self, rest: str, lineno: int,
                 assign_to: str | None = None) -> None:
        """执行 子脚本.zs 键=值 ...

        子脚本里的「返回」只结束子脚本。返回的值优先于输出：显式返回了
        什么就把什么交给父脚本。
        """
        if self._depth >= MAX_CALL_DEPTH:
            raise DSLError(f"脚本调用层数超过 {MAX_CALL_DEPTH}，可能存在循环调用")

        parts = rest.split(None, 1)
        if not parts:
            raise DSLError(f"第 {lineno + 1} 行：「执行」后面要跟脚本名")
        name = parts[0]
        tail = parts[1] if len(parts) > 1 else ""

        # 参数值整个是变量引用时传原始值，子脚本里还能当结构用
        params = {}
        for m in CALL_PARAM_RE.finditer(tail):
            params[m.group(1).strip()] = self._resolve_items(m.group(2).strip())

        fname = name if name.endswith(".zs") else f"{name}.zs"
        path = self._safe_path(self.expand(fname))
        if not path.is_file():
            raise DSLError(f"找不到脚本：{self._rel(path)}")

        sub = self._sub_engine()
        sub.vars.update(params)
        text = sub.run(path.read_text(encoding="utf-8"))
        self._deliver(sub.returned[0] if sub.returned else text, assign_to)

    # ------------------------------------------------------------------
    # 单条语句
    # ------------------------------------------------------------------

    def _exec_stmt(self, head: str, rest: str, lineno: int = -1) -> None:
        if head == "use":
            self._do_use(rest, lineno)

        elif head == "ret":
            self._do_return(rest, lineno)

        elif head == "model":
            self.model = resolve_model(self.expand(rest))

        elif head == "system":
            rest, files = self._split_attach(rest)
            self.system = self._attach(self.expand(rest), files)

        elif head == "temp":
            self.temperature = float(rest)

        elif head == "reset":
            self.history = []

        elif head == "load_history":
            self._do_load_history(rest)

        elif head == "save_history":
            self._do_save_history(rest)

        elif head == "trim_history":
            self._do_trim_history(rest, lineno)

        elif head == "set":
            name, value = self._split_assign(rest, "设")
            sub_head, sub_rest = split_head(value)
            if sub_head == "call":
                self._do_call(sub_rest, lineno, assign_to=name)
            elif self._is_verb(sub_head):
                try:
                    self._do_verb(sub_head, sub_rest, lineno, assign_to=name)
                except VerbError as e:
                    raise DSLError(f"第 {lineno + 1} 行：{e}") from e
            else:
                # 文本赋值。打错的动词名正好也落在这里，严格模式下先确认
                if self.strict_verbs:
                    self._check_unknown_verb(sub_head, sub_rest, lineno)
                self.store(name, self._resolve_items(value))

        elif head == "ask":
            self._do_ask(rest, lineno)

        elif head == "ask_json":
            self._do_ask_json(rest, lineno)

        elif head == "stream":
            self._do_stream(rest)

        elif head == "chat":
            self._do_chat(rest)

        elif head == "verdict":
            self._do_verdict(rest, lineno)

        elif head == "call":
            self._do_call(rest, lineno)

        elif head == "print":
            self._emit(self.expand(rest))

        elif head == "save":
            path, text = self._split_file_arg(rest, "保存")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            self._emit(f"[已保存 {self._rel(path)}]")

        elif head == "append":
            path, text = self._split_file_arg(rest, "追加")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(text.rstrip("\n") + "\n")
            self._emit(f"[已追加 {self._rel(path)}]")

        elif head == "load":
            name, path = self._read_file(rest, "读取")
            self.store(name, path.read_text(encoding="utf-8"))

        elif head == "load_json":
            name, path = self._read_file(rest, "读JSON")
            try:
                self.store(name, json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError as e:
                raise DSLError(f"{self._rel(path)} 不是合法 JSON："
                               f"第 {e.lineno} 行 {e.msg}") from e

        elif head == "load_jsonl":
            name, path = self._read_file(rest, "读JSONL")
            rows, bad = [], 0
            for i, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    # 坏行跳过而不是中断：几百行里坏一行就整个跑不了代价
                    # 太大。但一定要提示——静默丢数据比报错更糟。
                    bad += 1
                    if bad == 1:
                        self._emit(f"[{self._rel(path)} 第 {i} 行不是合法 "
                                   f"JSON，已跳过]")
            if bad > 1:
                self._emit(f"[共跳过 {bad} 行无法解析的内容]")
            self.store(name, rows)

        else:
            raise DSLError(f"未知语句：{head}")


def make_verbs(verbs_dir=None) -> VerbRegistry:
    """建一个带保留字检查的动词表，可选地立即扫描一个目录。"""
    reg = VerbRegistry(reserved=RESERVED)
    if verbs_dir:
        reg.load_dir(Path(verbs_dir))
    return reg


def _no_model(prompt, system=None):
    raise DSLError("从 Python 直接调的动词里不能问模型：调用方没给模型客户端（invoke_verb 的 client）")


def invoke_verb(verbs: VerbRegistry, name: str, *args, workdir=None,
                verbs_root=None, client=None):
    """从 Python 调一个动词，.py 写的和 .zs 写的都行，返回值跟脚本里拿到的一样。

    参数照 DSL 的规矩转成文本（结构转 JSON），按位置绑。.zs 动词在一个新引擎
    里跑：跟「设 x = 动词 …」走的是同一套（独立作用域、返回值优先于输出）。

    client 不给时，.zs 动词里「问」模型直接报错——判题这类规则动词用不到模型，
    真用到了说明调用方该显式给一个，而不是悄悄去花额度。
    """
    params = verbs.bind(name, [to_text(a) for a in args])
    kind, impl = verbs.resolve(name)
    if kind == "python":
        return impl(**params)
    from .mock import MockClient
    eng = DSLEngine(client=client or MockClient(handler=_no_model, offline=True),
                    workdir=workdir, verbose=False, verbs=verbs, verbs_root=verbs_root,
                    _depth=1)
    eng.vars.update(params)
    text = eng.run(Path(impl).read_text(encoding="utf-8"))
    return eng.returned[0] if eng.returned else text


def run_script(path, verbs: VerbRegistry | None = None, **kwargs) -> str:
    p = Path(path)
    return DSLEngine(workdir=p.parent, verbs=verbs, **kwargs).run_file(p)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python -m tools.dsl 脚本.zs")
        sys.exit(1)
    run_script(sys.argv[1])
