# -*- coding: utf-8 -*-
"""中文关键字的小型 DSL 引擎。

完整语法见 Notion「MCP 服务器」页，或 dsl_help 工具。这里只列速查表。

    用包 common quiz           声明动词包，同时开启严格模式
    模型/系统/温度             配置。「模型 快」只管本脚本（含它调起的子脚本），
                               不改共用的客户端；名字可以是档位（快/平衡/强）、
                               别名或模型真名，见下面「模型档位」
    动词 参数 键=值            位置参数在前，可混用 键=值（键须是动词声明的参数名）。
                               .zs 动词头 `# 参数：甲 乙? 丙=默认`：乙可选（空串）、丙默认值，
                               甲必填；声明里没有 ? 和 = 的旧文件少传不报错
    设 name = 值               变量（右侧是纯变量引用时保留结构）
    设 card.title = 值         往结构里写，中间层不存在会自动建
    问 reply = 提示词          调模型
    问JSON data = 提示词       要 JSON，直接得到结构
    问JSON r = 提示词 格式 字段:类型 …  [重问 N 次]
                               类型 文本 数字 是否 列表 A|B|C，字段名后加 ? 可选。
                               自动附格式说明，不对就带着问题重问（默认 2 次，
                               N 0–5），用完报错停脚本。顺序：附 → 格式 → 用
        问JSON r = 判断 {answer} 格式 action:合格|重做 reason:文本 score?:数字 用 快
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
    {{内容}}                   字面的 {内容}，不展开（正则里找「{name}」这种）。
                               \\d{4}、{2,3} 这类量词不用转义：没定义的 {…} 原样留
    逐项 word 于 列表 … 结束    自动加标题和输出
    当 条件 最多 N 次 … 结束    条件成立就跑一轮，每轮开头重新求值（条件写法同「如果」）。
                               必须写上限：N 是 1–1000 的整数或 {变量}，不写报错。
                               跑满 N 轮条件仍成立：不报错，接着往下执行，
                               {loop_full} 设成「是」（正常结束是「否」），trace 记一条
        当 {done} 不等于 是 且 {n} 小于 5 最多 6 次
    重复 N 次 … 结束           固定 N 轮（0–1000，可以是 {变量}，0 就一轮不跑）
    重复 N 次 计数 i           i 从 1 开始
    跳出 / 继续                结束最内层循环 / 跳到它的下一轮。当、重复、遍历、逐项
                               都认；嵌套时只管最内层；写在循环外（含子脚本里没套
                               循环）运行前就报错。在事务里跳出算正常结束（提交）；
                               「返回」在循环里照样结束整个脚本
                               每轮迭代、跳出、跑满记在 engine.trace（不进输出），
                               命令行 python -m tools.dsl x.zs --trace 打到 stderr
    如果 条件 … 否则如果 条件 … 否则 … 结束
                               只跑第一个成立的分支，「否则如果」可以多个，
                               「否则」可选；「否则 如果」「否则若」同义
    条件：甲 运算符 乙，组合用 且 / 或 / 非 / 括号（半角全角都行）
        如果 {a} 等于 1 且 ( {b} 包含 x 或 非 {c} 为空 )
                               优先级 非 > 且 > 或，短路。结构在展开之前的原文上
                               认，{变量} 的值里有「等于」「或」「(」都不影响；
                               且/或/非 要单独成词，{…} 外面的括号一律是分组——
                               要比的字面值带这些字，先「设」进变量。运算符：包含
                               不包含 等于 不等于 为空 不为空 大于 小于 不小于
                               不大于 开头是 结尾是（中文是规范写法）；大于 / 小于 这四个两边都能
                               转数字时按数值比，否则按文本。符号也可用：> < >= <=
                               == !=（全角 ＞ ＜ ≥ ≤ ＝＝ ≠ 也认），语义同中文；单个 =
                               不是运算符（报错：比较用 等于 或 ==）
    设 t = 当前时间 [日期|时间戳]
                               本地时间 YYYY-MM-DD HH:MM:SS；日期 YYYY-MM-DD；时间戳 整数秒
                               （common 包；环境变量 DSL_NOW 可固定返回值，测试用）
    设 total = 计算 {a} * 2 + 1
                               + - * / // %、括号、负数、小数；函数 取整（向下）
                               四舍五入(x, 位数) 最大 最小 绝对值。整数出整数，
                               除数是 0 报错。{变量} 的值只当一个数，转不了就报错
                               （不拼进算式里重新解析）。单独一行「计算 …」打印结果
    事务 库 … 结束             块内的写入要么全成要么全败
    执行 sub.zs key=值          独立作用域，key 在子脚本里就是 {key}。找脚本：先在
                               正在跑的这个脚本文件所在目录（同级）里找，同名时同级优先，
                               再按工作目录找；字符串脚本没有同级目录；同级只认该目录内
                               的文件（.. 跳出去的不算）。子脚本里再「执行」，同级 = 子脚本自己的目录
    调用 模块.函数 键=值 [出错时 e]
                               业务层（services/<模块>.zs，见 dsl_service）：调公开函数；
                               报错 404 文字 抛业务错误，接口层回 {"error": 文字} + 码
    后台执行 sub.zs key=值 on_error=fail.zs
                               放到后台线程跑，马上往下走（见 _do_call_bg）
    判定 verdict_of = 提示词 键→输出 … 否则→输出
    返回 值 [状态码]           结束脚本并交出一个值
    终止 成功|失败|超出预期 原因
                               结束整个流程（多深的循环、如果、事务里都行，事务算提交），
                               带状态和原因。顶层：脚本正常结束，engine.halted =
                               {status, reason, at}，输出末尾一行「[终止] 状态：原因」；
                               子脚本里：只结束子脚本，「设 r = 执行 子.zs」拿到的
                               就是 {status, reason, at}（at = 「子.zs 第 N 行」），
                               调用方决定接着走还是 终止 {r.status} {r.reason}。
                               脚本动词（.zs 动词）里的 终止：调用方没写 设 r = … 接结果时
                               接着往外传，结束调用方；接了结果的拿到同样的 {status, reason, at}。
                               状态可以是 {变量}，展开后不是这三个之一就报错
    预算 调用 N 秒 M           整个流程最多调 N 次模型、跑 M 秒墙钟（可只写其一，
                               N、M 是正整数或 {变量}）。从顶层脚本开始累计，含
                               派任务 / 并行派任务、子脚本、重问；超出按「终止 超出预期
                               预算用完：…」结束（第 N+1 次调用不发出去；秒数在每条
                               语句开头和每次调模型前查）。再写一次覆盖。见 dsl_budget
    #改法 名 … / #清单 …       脚本末尾的多行段（见 dsl_sections）：
                                   #改法 e1
                                   @@ 改 pkg/a.py
                                   <<<<<<< 原文
                                   …原文…
                                   =======
                                   …新文…
                                   >>>>>>> 新文
                                   @@ 新建 pkg/b.py
                                   <<<<<<< 内容
                                   …整份内容…
                                   >>>>>>> 新文
                               运行前拿出来：{e1} = {edits:[{file,old,new}…],
                               files:[{file,content}…]}，交给 改文件 {e1}；#清单 的
                               {items, hint} 放在 engine.checklist。段写错运行前就报

命名约定：变量名、脚本参数（「执行 x.zs key=值」的 key）、SQL 参数
（.sql 里的 :limit）用英文 snake_case；关键字（设、如果、遍历、问…）、动词名、
动词参数名（拆选项 的 题干/题型——传给中文动词的参数字典，键是中文）、
界面名、显示文本用中文。引擎照样认中文变量名（标识符按 Python 的
isidentifier 判，中英文、下划线、数字都行），约定只管仓库里的脚本，
tests/dsl/test_naming.py 会查。英文变量名别用关键字的英文别名（set、if、
end、reset、verdict… 见 dsl_core.KEYWORDS）和 in。

HTTP 接口里路由器注入的变量（英文名，放在请求字段之后，请求体伪造不了）：

    {request}        整个请求体（字典），写库表这类动词收它
    {current_user}   登录的用户名，没登录（或没开登录）是空串
    {current_role}   「认证 核对」查出的角色（teacher / student…），没有是空串
    {auth_mode}      on / off：这次启动要不要登录
    {session.xxx}    会话状态，改了自动存回
    {run_mode}       real / mock，当前是不是假客户端

请求的表单字段、地址参数直接就是变量（{learner}、{lesson}）。局部变量跟
它们同名时含义要一样，别用一个同名的局部变量盖掉后面还要读的请求字段。

认证（路由文件顶层的声明，详见 tools/dsl_http.py 的「认证」一节）：

    认证 必须                     一直要登录，标「公开」的接口例外
    认证 可选                     平时不要登录；启动时 --登录（gen run / dsl_http，
                                  Router(login=True)）才等同「认证 必须」。
                                  不开时跟没写这行完全一样
    认证 核对 app.db user_auth    每个请求按用户名再查一次：查不到（停用）当没登录，
                                  查到的 role 注入成 {current_role}
    认证 身份 learner 默认 me     注入「这是谁的数据」：开着登录时是登录的人，请求体
                                  里的 learner（含 {request.learner}）盖掉；没开时
                                  是请求体的 learner，没给是 me。接口里不用再写
                                  「{learner 或} 空了补 me」
    认证 角色 teacher 教师        角色的中文名（403 说明「需要教师权限」）
    接口 POST /x 动作 y 角色 teacher   开着登录时只许这个角色，别人 403；
                                  没开登录时不查

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
    dsl_calc.py      「计算」的算式解析（不用 eval）
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
from .verbs import VerbRegistry, VerbError, bind_top_params, KW_TOKEN_RE
from . import db_tx
from .dsl_history import HistoryMixin
from .dsl_budget import CountingClient, Usage
from .dsl_sections import split_sections
from .dsl_model import ModelMixin
from .dsl_service import ServiceMixin, biz_error_from, parse_call_text

# 重新导出，保持 `from tools.dsl import X` 的老写法能用
from .dsl_core import (  # noqa: F401
    BLOCK_OPENERS, CALL_PARAM_RE, DSLError, EMPTY_FORMS, ESC_OR_VAR_RE,
    HALT_STATES, ScriptHalt, IN_WORDS, KEYWORDS, LOOP_HEADS, LOOP_MAX, LoopBreak, LoopContinue,
    LoopControl, MAX_CALL_DEPTH, REPEAT_RE, WHILE_LIMIT_RE, PACK_SEP_RE, RESERVED, RET_STATUS_RE,
    BizError, ScriptReturn, TX_BEGIN, TX_COMMIT, TX_ROLLBACK, VAR_RE, VERB_LIKE_RE,
    as_number, check_name, dig, eval_cond_expr, eval_parts, is_empty,
    iter_items, msg_size, normalize, parse_cond_expr, parse_condition, put,
    split_condition_tail, split_head, split_items, to_text,
)
from .dsl_calc import calculate

import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

# engine.trace 最多记这么多条，再多只记一条「省略」：一千轮的循环套一千轮的
# 循环不能把内存吃光
TRACE_MAX = 2000

# 「用包」加载动词包时持有。动词表可能被多个线程共用（见 _do_use）。
# 只在真加载时才会等：包加载过一次之后，后面的「用包」查一下就跳过了。
_USE_LOCK = threading.RLock()

# 正在调 Python 动词的引擎（按线程）。动词是普通函数，拿不到引擎；要调模型的
# 动词（派任务）用 current_engine() 取，沿用这个引擎的客户端、系统提示和模型
_CURRENT = threading.local()


def current_engine():
    """当前线程里正在调 Python 动词的那个引擎；不在动词里返回 None。"""
    return getattr(_CURRENT, "engine", None)


# 「后台执行」的线程池：全进程一个，懒建。见 DSLEngine._do_call_bg
_BG_LOCK = threading.Lock()
_BG_POOL = None
_BG_PENDING = set()


def _submit_background(fn) -> None:
    global _BG_POOL
    with _BG_LOCK:
        if _BG_POOL is None:
            try:
                n = max(int(os.environ.get("DSL_BG_WORKERS", "2")), 1)
            except ValueError:
                n = 2
            _BG_POOL = ThreadPoolExecutor(max_workers=n, thread_name_prefix="zs-bg")
        fut = _BG_POOL.submit(fn)
        _BG_PENDING.add(fut)
    fut.add_done_callback(lambda f: _BG_PENDING.discard(f))


def wait_background(timeout: float = 60) -> bool:
    """等后台执行的活都跑完（测试用）。超时回 False。"""
    import time
    end = time.time() + timeout
    while time.time() < end:
        with _BG_LOCK:
            busy = [f for f in _BG_PENDING if not f.done()]
        if not busy:
            return True
        time.sleep(0.05)
    return False


def background_reason(exc) -> str:
    """后台出错的一句人话：模型的错（dsl_model 打了 model_call 标记）说「模型
    没有回应：第一行」，别的取最里面那层错误的第一行。最长 200 字。"""
    seen, cur, model, last = set(), exc, None, exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if getattr(cur, "model_call", False) and model is None:
            model = cur
        last = cur
        # 「raise … from None」压掉的上下文不往里找：json 解析失败的最里层是
        # StopIteration(0)，取它的第一行就成了一个「0」
        cur = cur.__cause__ or (None if cur.__suppress_context__ else cur.__context__)
    if model is not None:
        first = (str(model).strip().splitlines() or [type(model).__name__])[0]
        return f"模型没有回应：{first}"[:200]
    first = (str(last).strip().splitlines() or [type(last).__name__])[0]
    return first[:200]


class DSLEngine(ModelMixin, HistoryMixin, ServiceMixin):
    def __init__(self, client: ZhipuClient | None = None,
                 workdir: Path | None = None, verbose: bool = True,
                 verbs: VerbRegistry | None = None,
                 verbs_root: Path | str | None = None,
                 _depth: int = 0):
        # 套一层按模型通道分派的（cli:claude/… / cli:zcode 走本机 CLI），见 llm_router；
        # 外面再套一层计数的（「预算」）。拿父引擎的客户端建的（子引擎）共用父引擎的用量
        if isinstance(client, CountingClient):
            self.client, self.usage = client, client.usage
        else:
            self.usage = Usage()
            self.client = CountingClient(wrap_client(client or ZhipuClient()), self.usage)
        self.workdir = (Path(workdir) if workdir else Path.cwd()).resolve()
        self.verbose = verbose
        self.verbs = verbs
        self.verbs_root = Path(verbs_root) if verbs_root else None
        # 「用包」之后转严格模式：不认识的动词名报错，不当文本
        self.strict_verbs = False
        self._depth = _depth
        # 正在跑的脚本文件所在目录（run_file / 「执行」子脚本时设；字符串脚本为 None）：
        # 「执行」先在这里找同级脚本，见 _find_sibling
        self.script_dir: Path | None = None

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
        # 「终止」交出来的 {状态, 原因, 停在}；没终止过是 None
        self.halted: dict | None = None
        # 「#清单」段：{items: [[改|新建|删, 路径, 位置]], hint}；没写是 None
        self.checklist: dict | None = None
        # 正在跑的语句的行号（0 起）。预算在调模型时拦下，「停在」由它补
        self._at = 0
        # 空跑（dslagent 规划检查）：派任务这类要调模型的动词直接给假结果
        self.dry_run = False
        # 逐项块的自动输出用它。必须是实例属性——类属性会让父子引擎
        # 共享初值，嵌套调用时读到上一轮的残留。
        self._last_result: str = ""
        # 循环的执行记录（每轮迭代、跳出、继续、跑满上限），不进 output——
        # 输出是脚本的结果，接口会把它当消息给人看。子脚本共用父脚本这份
        self.trace: list = []
        # 业务层（services/*.zs，见 dsl_service）。services：Services 对象，None 表示第一次
        # 调业务函数时按工作目录下的 services/ 加载；svc_module：调用方所在的业务模块
        # （接口按文件名判定，业务函数里是它自己的模块，未知是 None）；in_func：本引擎正在跑
        # 业务函数体；svc_depth / svc_chain：业务函数调用深度和调用链。子脚本沿用
        self.services = None
        self.svc_module: str | None = None
        self.in_func = False
        self.svc_depth = 0
        self.svc_chain: tuple = ()

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
                base = self.vars[head.strip()]
                if isinstance(base, str) and base.lstrip()[:1] in ("{", "["):
                    # 变量里存的是 JSON 文本（取字段 / 读文件 / 模型回复都给文本）：点号路径钻进去，
                    # 不然 {r.结果} 取不到，原样留成 {r.结果} 这串字再被当 JSON 解析（kg_v2plan：写文件 {r1.结果}）
                    try:
                        base = json.loads(base)
                    except ValueError:
                        pass
                return dig(base, path)
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

        **{{内容}}** 是字面的 {内容}，不展开。正则的量词 \\d{4}、{2,3} 本来
        就原样留着（{4} 不是变量），要转义的是花括号里恰好是个已定义变量名
        的时候：正则要找文本里的「{name}」而 name 又是变量，写 {{name}}。
        只认成对的 {{…}}，JSON 结尾的 }} 不受影响。
        """
        def repl(m):
            if m.group(1) is not None:
                return "{" + m.group(1) + "}"
            body = m.group(2)
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
        return ESC_OR_VAR_RE.sub(repl, text)

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

    def _trace(self, text: str) -> None:
        if len(self.trace) < TRACE_MAX:
            self.trace.append("  " * self._depth + text)
        elif len(self.trace) == TRACE_MAX:
            self.trace.append(f"…trace 超过 {TRACE_MAX} 条，后面的不记了")

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
        sub.dry_run = self.dry_run
        sub.trace = self.trace
        sub.services = self.services
        sub.svc_module = self.svc_module
        sub.svc_depth = self.svc_depth
        sub.svc_chain = self.svc_chain
        return sub

    def _is_verb(self, head: str) -> bool:
        return (self.verbs is not None and head not in RESERVED
                and self.verbs.has(head))

    # ------------------------------------------------------------------
    # 条件
    # ------------------------------------------------------------------

    def _eval_condition(self, cond: str, lineno: int) -> bool:
        """先在原文上认结构（且 / 或 / 非 / 括号 / 运算符），再分别展开
        比较的两边。见 dsl_core.parse_cond_expr。"""
        return eval_cond_expr(parse_cond_expr(cond, lineno), self.expand, lineno)

    def _eval_against(self, value: str, cond: str, lineno: int) -> bool:
        """条件省略左值时，拿 value 当左值。组合条件里每个比较都可以省。"""
        return eval_cond_expr(parse_cond_expr(cond, lineno), self.expand,
                              lineno, value=to_text(value))

    # ------------------------------------------------------------------
    # 解析与执行
    # ------------------------------------------------------------------

    def run(self, script: str, params: dict | None = None) -> str:
        if params is not None:
            self.vars.update(bind_top_params(script, list(params.items())))
        script = self._take_sections(script)
        lines = [normalize(ln).rstrip() for ln in script.splitlines()]
        self._check_loops(lines)
        if self._depth == 0:
            self.usage.reset()
        try:
            self._exec_block(lines, 0, len(lines))
        except ScriptReturn as r:
            # 不是错误，是脚本主动收尾。调用方读 self.returned。
            self.returned = (r.value, r.status)
            if isinstance(r, ScriptHalt):
                if not r.value["at"]:      # 预算在调模型时拦下的，不知道行号
                    r.value["at"] = f"第 {self._at + 1} 行"
                self.halted = r.value
                if self._depth == 0:
                    self._emit(f"[终止] {r.value['status']}：{r.value['reason']}"
                               f"（停在 {r.value['at']}）")
        except LoopControl as e:   # _check_loops 挡过，到这里是引擎的 bug
            raise DSLError(f"「跳出 / 继续」跑到了循环外面：{e}") from None
        return "\n".join(self.output)

    def _take_sections(self, script: str) -> str:
        """「#改法 名」段放进同名变量、「#清单」段放进 self.checklist，原位置换成空行（行号不变）。"""
        rest, edits, checklist, probs = split_sections(script)
        if probs:
            raise DSLError("；".join(probs[:5]) + (f"；还有 {len(probs) - 5} 处" if len(probs) > 5 else ""))
        for name, obj in edits.items():
            self.vars[check_name(name)] = obj
        if checklist is not None:
            self.checklist = checklist
        return rest

    def _check_loops(self, lines: list) -> None:
        """运行之前过一遍：「跳出」「继续」要在循环里，「当」「重复」的头要写对。

        只认这几样，块配不配对还是跑到那里再报（老脚本的行为不变）。放在运行
        之前，是为了不走到的分支里写错了也能在空跑、语法检查时就看到。
        """
        stack = []
        for i, raw in enumerate(lines):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            head, rest = split_head(line)
            if head in BLOCK_OPENERS:
                stack.append(head)
                if head == "while":
                    self._parse_while(rest, i)
                elif head == "repeat":
                    self._parse_repeat(rest, i)
            elif head == "end":
                if stack:
                    stack.pop()
            elif head in ("break", "continue"):
                word = "跳出" if head == "break" else "继续"
                if rest:
                    raise DSLError(f"第 {i + 1} 行：「{word}」后面不能跟别的（「{rest}」）")
                if not any(h in LOOP_HEADS for h in stack):
                    raise DSLError(f"第 {i + 1} 行：「{word}」只能写在循环"
                                   f"（当 / 重复 / 遍历 / 逐项）里面")
            elif head == "halt":
                self._parse_halt(rest, i)
            elif head == "budget":
                self._parse_budget(rest, i)

    @staticmethod
    def _parse_budget(rest: str, lineno: int) -> dict:
        """「预算 调用 N 秒 M」→ {"调用": N 原文, "秒": M 原文}，至少一项，顺序随意。"""
        words = rest.split()
        how = f"第 {lineno + 1} 行：「预算」的写法：预算 调用 N 秒 M（可只写其一，N、M 是正整数或 {{变量}}）"
        if not words or len(words) % 2 or len(words) > 4:
            raise DSLError(how)
        got = {}
        for k, v in zip(words[::2], words[1::2]):
            if k not in ("调用", "秒") or k in got:
                raise DSLError(how)
            if not (v.isdigit() and int(v) > 0) and not VAR_RE.fullmatch(v):
                raise DSLError(f"{how}，「{k}」后面是「{v}」")
            got[k] = v
        return got

    @staticmethod
    def _parse_halt(rest: str, lineno: int):
        """「终止 状态 原因」→ (状态原文, 原因原文)。状态是 {变量} 的留到运行时查。"""
        state, _, reason = rest.strip().partition(" ")
        if not state:
            raise DSLError(f"第 {lineno + 1} 行：「终止」的写法：终止 成功|失败|超出预期 原因")
        if state not in HALT_STATES and not VAR_RE.fullmatch(state):
            raise DSLError(f"第 {lineno + 1} 行：「终止」的状态只能是 "
                           f"{' / '.join(HALT_STATES)}，现在是「{state}」")
        return state, reason.strip()

    @staticmethod
    def _parse_while(rest: str, lineno: int):
        """「当 条件 最多 N 次」→ (条件原文, N 的原文)。"""
        m = WHILE_LIMIT_RE.search(rest)
        if not m:
            raise DSLError(f"第 {lineno + 1} 行：「当」必须写上限，写法：当 条件 最多 N 次"
                           f"（N 是 1–{LOOP_MAX} 的整数或 {{变量}}）")
        cond = rest[:m.start()].strip()
        if not cond:
            raise DSLError(f"第 {lineno + 1} 行：「当」后面要跟条件")
        return cond, m.group(1)

    @staticmethod
    def _parse_repeat(rest: str, lineno: int):
        """「重复 N 次 [计数 i]」→ (N 的原文, 计数变量名或空)。"""
        m = REPEAT_RE.match(rest)
        if not m:
            raise DSLError(f"第 {lineno + 1} 行：「重复」的写法：重复 N 次，"
                           f"可选「计数 i」（N 是 0–{LOOP_MAX} 的整数或 {{变量}}）")
        return m.group(1), (check_name(m.group(2), lineno) if m.group(2) else "")

    def _loop_limit(self, raw: str, word: str, low: int, lineno: int) -> int:
        """展开上限、查是不是 low–LOOP_MAX 的整数。"""
        text = to_text(self._resolve_items(raw)).strip()
        if not text.isdigit() or not low <= int(text) <= LOOP_MAX:
            shown = text if raw == text else f"{raw} → {text}"
            raise DSLError(f"第 {lineno + 1} 行：「{word}」的次数要是 {low}–{LOOP_MAX} "
                           f"的整数，现在是「{shown}」")
        return int(text)

    def _loop_body(self, lines: list, start: int, end: int) -> bool:
        """跑一轮循环体。「继续」在这里接住；「跳出」接住并回 True。"""
        try:
            self._exec_block(lines, start, end)
        except LoopContinue:
            pass
        except LoopBreak:
            return True
        return False

    def run_file(self, path, params: dict | None = None) -> str:
        p = Path(path)
        if not p.is_absolute():
            p = self.workdir / p
        self.script_dir = p.resolve().parent
        return self.run(p.read_text(encoding="utf-8"), params=params)

    @staticmethod
    def _branch_of(line: str):
        """这行是不是分支的分界：("elif", 条件原文) / ("else", "") / None。

        「否则 如果 …」（中间有空格）也当「否则如果」——不然会被当成「否则」，
        后面那半句悄悄丢掉，分支就全走歪了。「否则」后面跟别的字报错，
        理由一样；跟 # 注释可以。
        """
        head, rest = split_head(line.strip())
        if head == "elif":
            return "elif", rest
        if head != "else":
            return None
        sub_head, sub_rest = split_head(rest)
        if sub_head == "if":
            return "elif", sub_rest
        if rest and not rest.startswith("#"):
            return "else?", rest
        return "else", ""

    def _scan_block(self, lines: list, start: int, stop: int):
        """找块的「结束」，顺带记下这一层的「否则如果」「否则」。
        返回 ([(类别, 行号, 条件原文)…], 结束的行号)。"""
        depth = 0
        marks = []
        for i in range(start, stop):
            head, _ = split_head(lines[i].strip())
            if head in BLOCK_OPENERS:
                depth += 1
            elif head == "end":
                depth -= 1
                if depth == 0:
                    return marks, i
            elif head in ("else", "elif") and depth == 1:
                kind, cond = self._branch_of(lines[i])
                if kind == "else?":
                    raise DSLError(f"第 {i + 1} 行：「否则」后面不能跟「{cond}」。"
                                   f"要再判断一个条件写「否则如果 条件」")
                if kind == "elif" and not cond:
                    raise DSLError(f"第 {i + 1} 行：「否则如果」后面要跟条件")
                if marks and marks[-1][0] == "else":
                    raise DSLError(
                        f"第 {i + 1} 行：同一个分支里有多个「否则」" if kind == "else"
                        else f"第 {i + 1} 行：「否则如果」要写在「否则」前面")
                marks.append((kind, i, cond))
        raise DSLError(f"第 {start + 1} 行的块没有对应的「结束」")

    def _find_block(self, lines: list, start: int, stop: int):
        """循环、事务用：返回 (第一个「否则 / 否则如果」的行号或 None, 结束的行号)。"""
        marks, end = self._scan_block(lines, start, stop)
        return (marks[0][1] if marks else None), end

    def _exec_block(self, lines: list, start: int, stop: int) -> None:
        i = start
        while i < stop:
            line = lines[i].strip()
            if not line or line.startswith("#"):
                i += 1
                continue

            self._at = i
            if self.usage.limited:
                spent = self.usage.over()
                if spent:
                    raise ScriptHalt("超出预期", f"预算用完：{spent}", f"第 {i + 1} 行")

            head, rest = split_head(line)

            if head in ("each", "foreach"):
                name, items, seq = self._parse_each(rest, i)
                else_at, end = self._find_block(lines, i, stop)
                if else_at is not None:
                    raise DSLError(f"第 {else_at + 1} 行：循环里不能直接写「否则」")
                word = "遍历" if head == "each" else "逐项"
                for n, item in enumerate(iter_items(items), 1):
                    self.vars[name] = item
                    if seq:
                        self.vars[seq] = n
                    self._trace(f"第 {i + 1} 行：{word} 第 {n} 轮 {name}={to_text(item)[:40]}")
                    if head == "foreach":
                        self._emit(f"── {to_text(item)} ──")
                        mark = len(self.output)
                        self._last_result = ""
                        if self._loop_body(lines, i + 1, end):
                            break
                        # 块内没打印任何东西时，自动输出最后一次生成结果
                        if len(self.output) == mark and self._last_result:
                            self._emit(self._last_result)
                    elif self._loop_body(lines, i + 1, end):
                        break
                i = end + 1
                continue

            if head in ("while", "repeat"):
                i = self._run_loop(head, rest, lines, i, stop) + 1
                continue

            if head in ("break", "continue"):
                # 位置和写法在 _check_loops 里查过了
                self._trace(f"第 {i + 1} 行：{'跳出' if head == 'break' else '继续'}")
                raise (LoopBreak if head == "break" else LoopContinue)(f"第 {i + 1} 行")

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
                marks, end = self._scan_block(lines, i, stop)
                # 分支：(类别, 起始行, 条件)，每段到下一个分界或「结束」为止。
                # 只跑第一个成立的；后面的条件不求值
                branches = [("if", i, rest)] + marks
                for n, (kind, at, cond) in enumerate(branches):
                    stop_at = branches[n + 1][1] if n + 1 < len(branches) else end
                    if kind == "else" or self._eval_condition(cond, at):
                        self._exec_block(lines, at + 1, stop_at)
                        break
                i = end + 1
                continue

            if head == "else":
                raise DSLError(f"第 {i + 1} 行：「否则」没有对应的「如果」")
            if head == "elif":
                raise DSLError(f"第 {i + 1} 行：「否则如果」没有对应的「如果」")
            if head == "end":
                raise DSLError(f"第 {i + 1} 行：多余的「结束」")

            if head == "报错":
                # 「报错 404 文字」是业务错误（沿调用链往上，接口回 {"error": 文字} + 该码）；
                # 第一个词不是 4xx 码的还是 common 包的报错动词
                err = biz_error_from(rest, self.expand)
                if err is not None:
                    raise err

            if self._is_verb(head):
                try:
                    self._do_verb(head, rest, i)
                except VerbError as e:
                    raise DSLError(f"第 {i + 1} 行：{e}") from e
                i += 1
                continue

            try:
                self._exec_stmt(head, rest, i)
            except (DSLError, ScriptReturn, BizError):
                # BizError（业务错误）原样往上走，状态码和文字才不丢。
                # ScriptReturn 要穿透出去，不能被下面那个兜底 except 包成
                # DSLError——那样「返回」就成报错了
                raise
            except Exception as e:
                raise DSLError(f"第 {i + 1} 行执行失败：{e}") from e
            i += 1

    def _run_loop(self, head: str, rest: str, lines: list, i: int, stop: int) -> int:
        """「当 条件 最多 N 次」「重复 N 次 [计数 i]」。返回「结束」的行号。"""
        word = "当" if head == "while" else "重复"
        else_at, end = self._find_block(lines, i, stop)
        if else_at is not None:
            raise DSLError(f"第 {else_at + 1} 行：循环里不能直接写「否则」")

        if head == "repeat":
            raw, counter = self._parse_repeat(rest, i)
            limit = self._loop_limit(raw, word, 0, i)
            for n in range(1, limit + 1):
                if counter:
                    self.vars[counter] = n
                self._trace(f"第 {i + 1} 行：重复 第 {n}/{limit} 轮")
                if self._loop_body(lines, i + 1, end):
                    break
            return end

        cond, raw = self._parse_while(rest, i)
        limit = self._loop_limit(raw, word, 1, i)
        # 结构只认一次，每轮重新展开、求值
        tree = parse_cond_expr(cond, i)
        n, full, why = 0, False, "条件不成立"
        while eval_cond_expr(tree, self.expand, i):
            if n >= limit:
                full = True
                break
            n += 1
            self._trace(f"第 {i + 1} 行：当 第 {n} 轮")
            if self._loop_body(lines, i + 1, end):
                why = "跳出"
                break
        self.vars["loop_full"] = full
        if full:
            self._trace(f"第 {i + 1} 行：当 跑满 {limit} 轮上限，条件仍成立，"
                        f"接着往下执行（{{loop_full}}=是）")
        else:
            self._trace(f"第 {i + 1} 行：当 结束（{why}，跑了 {n} 轮）")
        return end

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

        if self.in_func and getattr(db_tx.TX, "con", None) is not None:
            # 业务函数在外层事务里被调用：并入外层事务，不另开（db 包不支持嵌套）。
            # 出错一路抛到外层的「事务」块，由它回滚；这里不提交也不回滚
            self._trace(f"第 {lineno + 1} 行：事务 并入外层事务")
            self._exec_block(lines, start, end)
            return

        self._call_tx_verb(TX_BEGIN, target)
        try:
            self._exec_block(lines, start, end)
        except (ScriptReturn, LoopControl):
            # 跳出 / 继续 也是正常的流程控制，不是出错：块里已经做的写入留下
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
        pos, kws, late = self.verbs.split_call(name, rest.split()) if rest.strip() else ([], [], [])
        args = [self.expand(a) for a in pos]
        # 键=值 的值整个是变量引用时保留结构（列表 / 对象）
        params = self.verbs.bind(name, args, [(k, self._resolve_items(v)) for k, v in kws],
                                 [self.expand(a) for a in late])
        kind, impl = self.verbs.resolve(name)

        if kind == "python":
            prev = current_engine()
            _CURRENT.engine = self
            try:
                result = impl(**params)
            finally:
                _CURRENT.engine = prev
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
            if sub.halted is not None and assign_to is None:
                # 脚本动词里「终止」了、调用方又没接结果（没写 设 r = …）：终止接着往外传，结束调用方；
                # 接了结果（设 r = 动词 …）的拿到 {status, reason, at}，自己决定接着走还是终止
                h = sub.halted
                raise ScriptHalt(h["status"], h["reason"], f"{name} {h['at']}".strip())
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
    # 计算
    # ------------------------------------------------------------------

    def _do_compute(self, expr: str, lineno: int):
        """计算 表达式 —— 见 dsl_calc。{变量} 在原文里认，取到的值只能当一个
        数，不拼回表达式里再解析（值来自用户输入时，拼进去就能改写算式）。"""
        def value_of(token: str):
            m = VAR_RE.fullmatch(token)
            body = m.group(1)
            head, sep, alt = body.partition(" 或 ")
            if not sep:
                head, sep, alt = body.partition(" 或")
            got = self.lookup(head.strip())
            if sep and (got is None or (hasattr(got, "__len__") and not len(got))):
                return alt.strip()
            return got
        try:
            return calculate(expr, value_of)
        except DSLError as e:
            raise DSLError(f"第 {lineno + 1} 行：{e}") from None

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
        # 「调用 模块.函数 键=值」是业务函数，不是脚本（见 dsl_service）
        target, tail, on_err = parse_call_text(rest)
        hit = self._service_target(target)
        if hit is not None:
            self._do_service_call(hit[0], hit[1], tail, on_err, lineno, assign_to)
            return

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

        expanded_name = self.expand(name)
        fname = expanded_name if expanded_name.endswith(".zs") else f"{expanded_name}.zs"
        path = self._find_sibling(fname)
        if path is None:
            path = self._safe_path(fname)
            if not path.is_file():
                raise DSLError(f"找不到脚本：{self._rel(path)}")

        sub = self._sub_engine()
        sub.script_dir = path.parent
        sub.vars.update(params)
        text = sub.run(path.read_text(encoding="utf-8"))
        if sub.halted is not None:
            # 子脚本「终止」了：交给调用方的是 {status, reason, at}，at 带上脚本名（照「执行」里写的）
            sub.halted["at"] = f"{self.expand(fname)} {sub.halted['at']}"
        self._deliver(sub.returned[0] if sub.returned else text, assign_to)

    def _find_sibling(self, fname: str) -> Path | None:
        """「执行」先找正在跑的脚本文件所在目录（同级）下的脚本，只读、只认该目录内的文件。

        字符串脚本没有同级目录；写到目录外（..）的不算同级，交给 workdir 查找去报错。
        """
        if self.script_dir is None:
            return None
        p = (self.script_dir / fname).resolve()
        if self.script_dir not in p.parents or not p.is_file():
            return None
        return p

    def _do_halt(self, rest: str, lineno: int) -> None:
        """终止 成功|失败|超出预期 原因 —— 见 dsl_core.ScriptHalt。"""
        raw_state, raw_reason = self._parse_halt(rest, lineno)
        state = to_text(self._resolve_items(raw_state)).strip()
        if state not in HALT_STATES:
            raise DSLError(f"第 {lineno + 1} 行：「终止」的状态只能是 "
                           f"{' / '.join(HALT_STATES)}，{raw_state} 展开后是「{state}」")
        reason = self.expand(raw_reason).strip()
        self._trace(f"第 {lineno + 1} 行：终止 {state} {reason[:40]}")
        raise ScriptHalt(state, reason, f"第 {lineno + 1} 行")

    def _do_budget(self, rest: str, lineno: int) -> None:
        """预算 调用 N 秒 M —— 见 dsl_budget。"""
        got = {}
        for k, raw in self._parse_budget(rest, lineno).items():
            v = to_text(self._resolve_items(raw)).strip()
            if not (v.isdigit() and int(v) > 0):
                raise DSLError(f"第 {lineno + 1} 行：「预算」的{k}要是正整数，{raw} 展开后是「{v}」")
            got[k] = int(v)
        self.usage.set_limits(got.get("调用"), got.get("秒"))
        self._trace(f"第 {lineno + 1} 行：预算 调用 {self.usage.max_calls} 秒 {self.usage.max_secs}"
                    f"（已用 {self.usage.calls} 次、{self.usage.elapsed():.1f} 秒）")

    def _do_call_bg(self, rest: str, lineno: int) -> None:
        """后台执行 子脚本.zs 键=值 ... [on_error=出错时.zs]

        跟「执行」一样起一个独立作用域的子引擎（同一个模型客户端、同一套
        动词），只是放到后台线程池里跑，这一行马上返回，接口照常回响应。
        给调模型的慢活用：上传教材后逐块抽取，一块十几秒，不能让页面干等。

        **结果怎么拿**：子脚本自己写库（进度、结果、出错），页面轮询那张表
        （.ui 动作的「每隔」）。后台没有请求上下文，「响应」「消息」这类
        动词在里面不起作用。

        **出错**：子脚本抛了错（模型超时、SQL 出错……），这一行早就返回了，
        没人接得住。所以可以给 on_error=另一个.zs：出错时用同样的参数再加
        一个 error（一句人话：模型的错是「模型没有回应：…」，别的是错误的
        第一行）跑它，把「这一块失败了、为什么」记进库里，页面上能看到、
        能重试。不给 on_error 就只打一行日志到 stderr。

        **并发**：全进程共用一个线程池，同时最多跑 DSL_BG_WORKERS 个（默认
        2，跟 llm_router 里 claude -p 默认 2 个进程对齐），多出来的排队，
        不会一下子起几十个线程去抢模型——排在 CLI 的信号量上超过 30 秒会被
        当成「排队太久」改走 fallback。

        参数值在交出去之前深拷贝一份：后台跑的时候请求那边的变量可能已经变了。
        """
        import copy
        if self._depth >= MAX_CALL_DEPTH:
            raise DSLError(f"脚本调用层数超过 {MAX_CALL_DEPTH}，可能存在循环调用")
        parts = rest.split(None, 1)
        if not parts:
            raise DSLError(f"第 {lineno + 1} 行：「后台执行」后面要跟脚本名")
        name = parts[0]
        tail = parts[1] if len(parts) > 1 else ""
        params = {}
        for m in CALL_PARAM_RE.finditer(tail):
            params[m.group(1).strip()] = self._resolve_items(m.group(2).strip())
        params = copy.deepcopy(params)

        def script_of(n):
            n = str(n)
            fname = n if n.endswith(".zs") else f"{n}.zs"
            path = self._safe_path(self.expand(fname))
            if not path.is_file():
                raise DSLError(f"第 {lineno + 1} 行：找不到脚本：{self._rel(path)}")
            return path

        path = script_of(name)
        on_error = params.pop("on_error", None)
        fail_path = script_of(on_error) if on_error else None
        main = self._sub_engine()
        fail = self._sub_engine() if fail_path else None
        # 后台跑的时候请求早就结束了，不往请求那份 trace 里记
        main.trace = []
        if fail is not None:
            fail.trace = []
        text = path.read_text(encoding="utf-8")

        def job():
            try:
                main.vars.update(copy.deepcopy(params))
                main.run(text)
            except Exception as e:  # 后台没人接，记下来交给 on_error
                why = background_reason(e)
                print(f"[后台执行出错] {path.name}: {why}", file=sys.stderr, flush=True)
                if fail is None:
                    return
                try:
                    fail.vars.update(copy.deepcopy(params))
                    fail.vars["error"] = why
                    fail.run(fail_path.read_text(encoding="utf-8"))
                except Exception as e2:
                    print(f"[后台执行出错] {fail_path.name}（处理出错的脚本自己也出错了）: "
                          f"{background_reason(e2)}", file=sys.stderr, flush=True)

        _submit_background(job)

    # ------------------------------------------------------------------
    # 单条语句
    # ------------------------------------------------------------------

    def _exec_stmt(self, head: str, rest: str, lineno: int = -1) -> None:
        if head == "use":
            self._do_use(rest, lineno)

        elif head == "ret":
            self._do_return(rest, lineno)

        elif head == "halt":
            self._do_halt(rest, lineno)

        elif head == "budget":
            self._do_budget(rest, lineno)

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
            elif sub_head == "compute":
                self.store(name, self._do_compute(sub_rest, lineno))
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

        elif head == "call_bg":
            self._do_call_bg(rest, lineno)

        elif head == "print":
            self._emit(self.expand(rest))

        elif head == "compute":
            value = self._do_compute(rest, lineno)
            self._deliver(value, None)

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


def run_script(path, verbs: VerbRegistry | None = None, params: dict | None = None, **kwargs) -> str:
    p = Path(path)
    return DSLEngine(workdir=p.parent, verbs=verbs, **kwargs).run_file(p, params=params)


if __name__ == "__main__":
    import sys

    raw = [a for a in sys.argv[1:] if a != "--trace"]
    if not raw:
        print("用法: python -m tools.dsl 脚本.zs [键=值 …] [--trace]")
        sys.exit(1)
    p = Path(raw[0])
    pairs = []
    for tok in raw[1:]:
        m = KW_TOKEN_RE.match(tok)
        if not m:
            print(f"参数「{tok}」不是 键=值 的形式", file=sys.stderr)
            sys.exit(1)
        pairs.append((m.group(1), m.group(2)))
    eng = DSLEngine(workdir=p.parent)
    try:
        script = p.read_text(encoding="utf-8")
        eng.run(script, params=dict(pairs))
    finally:
        if "--trace" in sys.argv[1:]:
            for t in eng.trace:
                print(f"[trace] {t}", file=sys.stderr)
