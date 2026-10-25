# -*- coding: utf-8 -*-
"""DSL 的词法常量、值处理和条件求值——不碰引擎状态的那部分。

从 dsl.py 拆出来的第一块。判据是「要不要 self」：这里全是纯函数和
常量，给定输入就有确定输出，能单独测、能被别的模块直接用。

拆分本身是被逼的：dsl.py 涨到一千四百行之后，改一行要整个重写，
而这条链路上每次全文件写入都有把 MCP 服务器压垮的风险——实际崩过两次。
拆完之后改条件求值只碰这个文件，两百多行。

`tools/dsl.py` 会把这里的东西重新导出，所以 `from tools.dsl import
to_text, DSLError` 这类老写法不受影响。
"""

import json
import re

from .db_errors import ClientError

# 中文关键字 -> 内部指令名
KEYWORDS = {
    "用包": "use", "依赖": "use",
    "模型": "model", "系统": "system", "温度": "temp",
    "设": "set", "设置": "set", "变量": "set",
    "问": "ask", "提问": "ask",
    "问JSON": "ask_json", "提问JSON": "ask_json",
    "流式": "stream", "对话": "chat",
    "重置": "reset", "清空": "reset",
    "读历史": "load_history", "载入历史": "load_history",
    "存历史": "save_history", "保存历史": "save_history",
    "修剪历史": "trim_history",
    "打印": "print", "输出": "print",
    "保存": "save", "写入": "save",
    "追加": "append", "续写": "append",
    "读取": "load", "载入": "load",
    "读JSON": "load_json", "载入JSON": "load_json",
    "读JSONL": "load_jsonl", "载入JSONL": "load_jsonl",
    "遍历": "each", "循环": "each", "每个": "each",
    "逐项": "foreach", "逐个": "foreach",
    "如果": "if", "若": "if", "否则": "else", "结束": "end",
    "否则如果": "elif", "否则若": "elif",
    "计算": "compute",
    "事务": "tx",
    "执行": "call", "调用": "call",
    "后台执行": "call_bg",
    "判定": "verdict",
    "返回": "ret",
    "当": "while", "重复": "repeat",
    "跳出": "break", "继续": "continue",
    "终止": "halt",
    "预算": "budget",
}

# 动词不能用这些名字
RESERVED = set(KEYWORDS) | set(KEYWORDS.values())

# 「事务」块在三个时刻调的动词。引擎只认这三个名字，不认数据库——
# 语义由 db 包提供，换个存储就换个包。
TX_BEGIN, TX_COMMIT, TX_ROLLBACK = "事务开始", "事务提交", "事务回滚"

# 循环分隔词。长的排前面：否则「属于」会被「于」抢先匹配，
# 变量名里会多出一个「属」字。
IN_WORDS = ("属于", "于", "在", "in")

CONDITION_OPS = [
    ("不包含", "not_contains"), ("包含", "contains"),
    ("不等于", "ne"), ("等于", "eq"),
    ("不为空", "not_empty"), ("为空", "empty"),
    ("不小于", "ge"), ("不大于", "le"),
    ("大于", "gt"), ("小于", "lt"),
    ("开头是", "startswith"), ("结尾是", "endswith"),
]
# 符号写法是中文运算符的别名，语义完全一样。长的排前面（>= 先于 >），
# 紧贴写法按子串找时才不会把 >= 切成 > 加 =。中文仍是规范写法。
SYMBOL_OPS = [
    (">=", "ge"), ("<=", "le"), ("==", "eq"), ("!=", "ne"),
    ("＝＝", "eq"), ("≥", "ge"), ("≤", "le"), ("≠", "ne"),
    (">", "gt"), ("<", "lt"), ("＞", "gt"), ("＜", "lt"),
]
CONDITION_OPS += SYMBOL_OPS
UNARY_OPS = {"empty", "not_empty"}
OP_BY_WORD = dict(CONDITION_OPS)

# 「为空」要认的几种形态：空串，以及结构转文本后的空数组、空对象
EMPTY_FORMS = ("", "[]", "{}")

BLOCK_OPENERS = {"each", "if", "foreach", "tx", "while", "repeat"}
# 「跳出」「继续」认的循环：最内层的这几种块
LOOP_HEADS = {"each", "foreach", "while", "repeat"}
# 「当」「重复」的全局硬上限。「当」必须自己写上限（最多 N 次），N 也不能超过它：
# 条件写错时宁可停在一千轮，不能把一个请求挂死
LOOP_MAX = 1000
# 「当 条件 最多 N 次」的尾巴；N 是整数或一个 {变量}。「次」可以贴着写
WHILE_LIMIT_RE = re.compile(r"(?:^|\s+)最多\s+(\{[^{}]+\}|\S+?)\s*次\s*$")
# 「重复 N 次 [计数 i]」
REPEAT_RE = re.compile(r"^(\{[^{}]+\}|\S+?)\s*次(?:\s+计数\s+(\S+))?\s*$")

CJK = re.compile(r"[\u4e00-\u9fff]")
KEYWORDS_BY_LEN = sorted(KEYWORDS, key=len, reverse=True)

VAR_RE = re.compile(r"\{([^{}]+)\}")
# 插值实际用的：{{内容}} 是字面的 {内容}，不展开（正则的 \d{{4}}、
# 恰好跟变量同名的 {n}）；其余同 VAR_RE。只认成对的 {{…}}，单个 }} 不动——
# JSON 字面量 {"a":{x}} 的结尾就是 }}。
ESC_OR_VAR_RE = re.compile(r"\{\{([^{}]*)\}\}|\{([^{}]+)\}")
# 条件、计算在展开之前的原文上分词：{变量}、{{字面}} 整块算一个词，
# 里面的空格和「或」（{x 或 默认}）不切
BRACE_RE = re.compile(r"\{\{[^{}]*\}\}|\{[^{}]+\}")
# 整个值就是一个没展开的 {变量}。未定义变量会原样保留成这个样子，
# 判空时要当成「没有值」。
# 开头不能是引号：{"id":1} 这种只有一层的 JSON 对象不是没展开的变量（否则「如果 {p} 为空」
# 对一个有内容的扁平结构也成立）
UNEXPANDED_RE = re.compile(r'^\{(?!\s*")[^{}]+\}$')
RETRY_RE = re.compile(r"\s+重试\s+(\d+)\s*次?\s+直到\s+(.+)$")
# 返回值末尾的三位数当状态码。三位而不是任意数字：返回一个纯数字
# （比如「返回 200」当内容）的情况得能区分，三位数几乎只会是状态码。
RET_STATUS_RE = re.compile(r"\s+([1-5]\d\d)\s*$")
# 后缀不进 KEYWORDS：它们只在语句尾巴上出现，进了关键字表会让
# 「附录 xxx」这种普通文本行被当成语句
ATTACH_RE = re.compile(r"\s+附\s+(\S+)$")
TOOLS_RE = re.compile(r"\s+带工具\s+(\S+)(?:\s+最多\s+(\d+)\s*轮?)?$")
# 「问 … 用 快」：只管这一次的模型。「用」在提示词里太常见，所以只认
# 最末尾的「 用 名字」，名字还得是别名表里的、像模型真名的（ASCII，
# 如 glm-4-flash）或一个 {变量}，见 ModelMixin._split_model
MODEL_RE = re.compile(r"\s+用\s+(\S+)$")
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/\-]*$")
BRANCH_RE = re.compile(r"(\S+?)\s*(?:→|->)\s*(\S+)")
CALL_PARAM_RE = re.compile(r"(\S+?)\s*=\s*(.*?)(?=\s+\S+?\s*=|$)")
PACK_SEP_RE = re.compile(r"[,，\s]+")
# 修剪历史的参数：纯数字是条数，带「字」后缀是字符数
TRIM_CHARS_RE = re.compile(r"^(\d+)\s*(?:字符?|chars?)$", re.I)
# 用来判断「这行看着像不像动词调用」
VERB_LIKE_RE = re.compile(r"^[^\s{}=/\\:：]+$")

MAX_CALL_DEPTH = 5
# 「报错 404 文字」：业务错误（4xx 码 + 文字）。「报错」本身还是 common 包的动词
# （报错 文字 → 500），只有第一个词是 400–499 的三位码才当业务错误，见 dsl.py _exec_block
BIZ_ERR_RE = re.compile(r"^(4\d\d)(?:\s+(.*))?$", re.S)
DEFAULT_TOOL_ROUNDS = 3
DEFAULT_TRIM_KEEP = 20


class DSLError(Exception):
    """脚本语法或运行错误。"""


class BizError(ClientError):
    """「报错 <码> <文字>」抛出的业务错误（码是 4xx）：沿调用链往上传，到接口层回
    {"error": 文字} + 该码。

    是 db_errors.ClientError 的子类——路由器在错误链上找 ClientError，找到就回
    {"error": 文字} + 该码（见 db_errors.find_client_error）。引擎的逐行兜底不把它包成
    DSLError（其他异常会被包），所以业务函数调业务函数，错误原样往上走。
    """


class ModelOutputError(DSLError):
    """模型返回的内容不合格（JSON 解析失败、缺字段、类型不对）：是模型输出的问题，
    不是脚本写错。问JSON 这类「问模型要结构」的语句在解析 / 校验失败时抛它。

    继承 DSLError：没被接住时和普通脚本错误待遇一样（往上抛、接口层照旧），
    引擎的逐行兜底也不会再把它包一层。带 status / message 是给业务层的
    「出错时」用的——分类时认出它就当业务错误接住（tools/dsl_service.py 的
    _do_service_call），{e.code} {e.error} 跟 报错 4xx 的一个待遇。码用 502：
    模型是上游服务，它回的货不合格，不是脚本写错了。
    """

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.message = message
        self.status = status


class ModelCallError(ModelOutputError):
    """模型服务调用本身失败（超时、限流、服务不可用、网络断、后端起不来）：
    不是模型回的内容不合格（那是 ModelOutputError），也不是脚本写错。模型调用
    语句（问 / 问JSON / 对话 / 流式）在客户端抛服务失败（RuntimeError /
    OSError，含 requests 的网络异常）时包成它，消息保留原文、加「模型调用失败」
    前缀。

    继承 ModelOutputError：现有分类逻辑（find_model_output_error）认整个
    ModelOutputError 族，`调用 … 出错时` 和 `问JSON … 出错时` 就都能接住。
    码用 503：上游服务临时不可用（超时、限流、满载），区别于 502「回了货但
    货不合格」。没被接住时异常仍带 model_call 标记（dsl_model 打的），接口层
    待遇不变（照旧 502 + 一句人话，不是 500）。
    """

    def __init__(self, message: str, status: int = 503):
        super().__init__(message, status)


def find_model_output_error(exc):
    """顺着错误链找 ModelOutputError（跟 db_errors.find_client_error 一个找法：
    引擎和业务层会一层层包，原来的异常挂在 __cause__ / __context__ 上）。
    没有就回 None。"""
    seen = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, ModelOutputError):
            return exc
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return None


class ScriptReturn(Exception):
    """「返回」抛出来的，不是错误——run() 接住它当正常结束。

    用异常而不是层层传标志位：返回可能发生在任意深度的嵌套块里，靠返回
    值往上传要每一层都判断一次，漏一处就成了「返回之后还接着跑」。
    """

    def __init__(self, value, status: int = 200):
        super().__init__("script returned")
        self.value = value
        self.status = status


class LoopControl(Exception):
    """「跳出」「继续」抛出来的，由最内层的循环接住。不是错误。

    跟 ScriptReturn 一样用异常：语句可能在循环里任意深度的「如果」「事务」
    里面。循环外写「跳出」在运行之前的检查（DSLEngine._check_loops）就报了，
    所以正常情况下它出不了循环。
    """


class LoopBreak(LoopControl):
    pass


class LoopContinue(LoopControl):
    pass


# 「终止 状态 原因」的状态只能是这三个
HALT_STATES = ("成功", "失败", "超出预期")


class ScriptHalt(ScriptReturn):
    """「终止 成功|失败|超出预期 原因」抛出来的：结束整个流程，带状态和原因。

    做成 ScriptReturn 的子类，是要它在别处的待遇跟「返回」完全一样：穿透循环、
    事务里算正常结束（提交）、run() 接住不当错误。值是 {status, reason, at}——
    子脚本里终止时，调用方「设 r = 执行 子.zs」拿到的就是这个字典，由调用方决定
    接着走还是自己也终止。顶层脚本终止时引擎的 halted 记着它。
    """

    def __init__(self, state: str, reason: str, where: str):
        super().__init__({"status": state, "reason": reason, "at": where})


# ----------------------------------------------------------------------
# 文本与值
# ----------------------------------------------------------------------


def normalize(line: str) -> str:
    """全角符号转半角，全角空格除外。逗号和冒号保持原样——正文里它们是标点。

    U+3000 曾经也在这里被换成半角空格，整行（连字面量值一起）遭殃：
    「设 head = 《{t}》　{l}　第{n}课」运行出来分隔全成了半角。现在值里的
    全角空格原样保留；语句结构上的分隔照旧认它——str.split() 本来就把
    U+3000 当空白，靠 partition(" ") 切头的地方换成 split_ws_once。
    """
    return (line.replace("＝", "=").replace("＃", "#")
                .replace("｛", "{").replace("｝", "}"))


WS_SEP_RE = re.compile(r"[ \u3000]")


def split_ws_once(line: str) -> tuple:
    """在第一个空格（半角/全角）处把一行切成（头，余下）；没有空格就（原文，''）。

    全角空格当分隔符是历史行为：引擎曾把整行的 U+3000 先换成半角再切。
    修复「值里的 U+3000 被归一」后，分隔仍认它，写法不因修复而变：
    「打印　甲」照旧等价于「打印 甲」。
    """
    m = WS_SEP_RE.search(line)
    if not m:
        return line, ""
    return line[:m.start()], line[m.end():]


def split_alt(body: str) -> tuple:
    """「{名 或 默认}」按「或」切成（名，默认值）；没有「或」返回（原文，None）。

    「或」两边要有空白（半角全角都行），否则「甲或乙」这种普通变量名会
    被误切。先认两边都有、再认只在前头（{名 或} 取空）——这套先后顺序
    就是历史行为，早先靠行级归一顺便得到，现在写明。
    """
    for sep in (" 或 ", " 或", "　或　", "　或"):
        head, found, alt = body.partition(sep)
        if found:
            return head, alt
    return body, None


def split_items(text: str) -> list:
    """拆分列表，半角和全角逗号都算分隔符。"""
    return [x.strip() for x in re.split(r"[,，]", text) if x.strip()]


def is_empty(value: str) -> bool:
    """判空。空串、空列表、空对象，以及没展开的 {变量} 都算空。

    最后一条是关键：未定义变量原样保留成 {名} 这个字面量，那在语义上
    就是「没有值」。不这么算的话，「如果 {session.code} 为空」在字段还
    不存在时会判成「不为空」，一路走进处理已有值的分支。
    """
    s = value.strip()
    return s in EMPTY_FORMS or bool(UNEXPANDED_RE.fullmatch(s))


def to_text(value) -> str:
    """结构化值转文本。插值、写文件、条件比较都走这里，统一一处转换。

    紧凑 JSON 而不是缩进：插进一行文本里不该炸成多行。
    布尔转「是/否」——脚本里写「如果 {标志} 等于 是」比 True 自然。
    """
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def as_number(s):
    try:
        return float(s.strip())
    except (ValueError, AttributeError):
        return None


# ----------------------------------------------------------------------
# 结构化变量：按路径读写
# ----------------------------------------------------------------------


def index_of(key: str, seq: list):
    """把一段路径当数组下标解析，越界或不是数字返回 None。"""
    if not key.lstrip("-").isdigit():
        return None
    i = int(key)
    return i if -len(seq) <= i < len(seq) else None


def dig(obj, path: str):
    """按点号路径取值，取不到返回 None。数字段当下标，支持负数。"""
    cur = obj
    for key in path.split("."):
        key = key.strip()
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        elif isinstance(cur, list):
            i = index_of(key, cur)
            if i is None:
                return None
            cur = cur[i]
        else:
            return None
    return cur


def put(obj, path: str, value) -> bool:
    """按点号路径写值。中间层不存在就建成字典。成功返回 True。

    自动建中间层是为了让「从零开始记状态」能一行一行写，否则每次都得
    先拼一个完整的 JSON 出来，既难看又容易在引号上出错。

    列表只能按已有下标改，不会自动扩容——越界返回 False 让调用方报错，
    静默追加会让「写错下标」这种笔误变成看不见的数据错位。
    """
    parts = [p.strip() for p in path.split(".")]
    cur = obj
    for key in parts[:-1]:
        if isinstance(cur, list):
            idx = index_of(key, cur)
            if idx is None:
                return False
            cur = cur[idx]
        elif isinstance(cur, dict):
            if not isinstance(cur.get(key), (dict, list)):
                cur[key] = {}
            cur = cur[key]
        else:
            return False

    last = parts[-1]
    if isinstance(cur, list):
        idx = index_of(last, cur)
        if idx is None:
            return False
        cur[idx] = value
        return True
    if isinstance(cur, dict):
        cur[last] = value
        return True
    return False


def iter_items(value):
    """循环要遍历什么。列表直接遍历，字典遍历键，字符串按逗号拆。"""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.keys())
    return split_items(to_text(value))


def msg_size(msg: dict) -> int:
    """一条消息占多少字。

    算 content 加 tool_calls 的参数——带工具那轮的 assistant 消息 content
    可能是空的，重量全在 tool_calls 里，只数 content 会严重低估。
    """
    n = len(to_text(msg.get("content")))
    for c in msg.get("tool_calls") or []:
        fn = c.get("function", {}) if isinstance(c, dict) else {}
        n += len(to_text(fn.get("name"))) + len(to_text(fn.get("arguments")))
    return n


# ----------------------------------------------------------------------
# 条件
# ----------------------------------------------------------------------


SINGLE_EQ_RE = re.compile(r"(?<![=!<>＝≥≤≠])[=＝](?![=＝])")


def single_eq_hint(raw: str) -> str:
    """条件拆不出来、而且原文（{…} 外）有单个「=」时的提示，否则空串。
    单个 = 不当运算符——赋值和比较混用是常见笔误。"""
    if SINGLE_EQ_RE.search(_mask_braces(raw)):
        return "。单个「=」不是比较运算符，比较用 等于 或 =="
    return ""


def split_condition(cond: str):
    """拆成 (左值, 运算符, 右值)，拆不出返回 None。

    先按空格分词找整词匹配的运算符——这样左右值里出现「包含」「大于」
    这类字样不会被误切。分词找不到（紧贴写法）才退回子串匹配。
    """
    parts = cond.split()
    for i, word in enumerate(parts):
        op = OP_BY_WORD.get(word)
        if op is None:
            continue
        left = " ".join(parts[:i]).strip()
        right = " ".join(parts[i + 1:]).strip()
        if op in UNARY_OPS:
            if right:
                continue
            return left, op, ""
        if not left or not right:
            continue
        return left, op, right

    for zh, op in CONDITION_OPS:
        idx = cond.find(zh)
        if idx < 0:
            continue
        left, right = cond[:idx].strip(), cond[idx + len(zh):].strip()
        if op in UNARY_OPS:
            if right:
                continue
            return left, op, ""
        if not left or not right:
            continue
        return left, op, right
    return None


def split_condition_tail(cond: str):
    """条件省略左值时拆出 (运算符, 右值)。用于「重试 … 直到 包含 X」。"""
    parts = cond.split()
    if parts:
        op = OP_BY_WORD.get(parts[0])
        if op is not None:
            right = " ".join(parts[1:]).strip()
            if op in UNARY_OPS and right:
                return None
            return op, right
    for zh, op in CONDITION_OPS:
        if cond.startswith(zh):
            right = cond[len(zh):].strip()
            if op in UNARY_OPS and right:
                continue
            return op, right
    return None


def eval_parts(left: str, op: str, right: str) -> bool:
    """按运算符比较两个值。两侧都能转数字时按数值比较。"""
    if op == "empty":
        return is_empty(left)
    if op == "not_empty":
        return not is_empty(left)
    if op == "contains":
        return right in left
    if op == "not_contains":
        return right not in left
    if op == "eq":
        return left.strip() == right.strip()
    if op == "ne":
        return left.strip() != right.strip()
    if op == "startswith":
        return left.strip().startswith(right.strip())
    if op == "endswith":
        return left.strip().endswith(right.strip())
    a, b = as_number(left), as_number(right)
    if a is None or b is None:
        a, b = left.strip(), right.strip()
    return {"gt": a > b, "lt": a < b, "ge": a >= b, "le": a <= b}[op]


def parse_condition(cond: str, lineno: int):
    """拆条件，拆不出就报错并列出可用的运算符。"""
    parsed = split_condition(cond)
    if parsed is None:
        raise DSLError(
            f"第 {lineno + 1} 行：看不懂的条件「{cond}」。可用："
            f"包含 / 不包含 / 等于 / 不等于 / 为空 / 不为空 / "
            f"大于 / 小于 / 不小于 / 不大于 / 开头是 / 结尾是（符号 > < >= <= == != 也可以）"
            + single_eq_hint(cond))
    return parsed


# ----------------------------------------------------------------------
# 组合条件：且 / 或 / 非 / 括号
#
# 结构在**展开之前的原文**上认，展开只发生在比较的两侧。早先是先把整行
# 展开再按空格找运算符，学生作答里有「等于」「包含」，条件就被切错了——
# 变量值来自用户输入，不能让它决定条件的结构。
#
# 优先级 非 > 且 > 或，短路求值。且 / 或 / 非 要单独成词（空格或括号隔开）；
# 括号半角全角都行，{…} 外面的括号一律是分组，贴着写也算（「({a} 等于 1」）。
# 所以条件里要比的字面值本身带这几样（「等于 (A)」「等于 或」），先「设」进
# 变量再 {变量}——变量的值不参与分词。
# ----------------------------------------------------------------------

COND_AND, COND_OR, COND_NOT = "且", "或", "非"
OPEN_PARENS, CLOSE_PARENS = "(（", ")）"
_COND_STRUCT = {COND_AND: "and", COND_OR: "or", COND_NOT: "not"}


def raw_words(text: str) -> list:
    """按空格切原文，{…} 整块不切（里面的空格、「或」原样留在词里）。"""
    words, cur, i = [], [], 0
    while i < len(text):
        m = BRACE_RE.match(text, i)
        if m:
            cur.append(m.group(0))
            i = m.end()
            continue
        if text[i].isspace():
            if cur:
                words.append("".join(cur))
                cur = []
        else:
            cur.append(text[i])
        i += 1
    if cur:
        words.append("".join(cur))
    return words


def cond_tokens(cond: str) -> list:
    """原文分词，返回 [(类别, 文本)]。类别是 word / and / or / not / ( / )。

    {…} 外面的括号一律单独成一个记号，不管有没有空格隔开（「（甲 等于 1）且」
    里的「且」照样认得出）；{…} 里面的不算。
    """
    out = []

    def word(w):
        if w:
            out.append((_COND_STRUCT[w], w) if w in _COND_STRUCT else ("word", w))

    for w in raw_words(cond):
        cur, i = [], 0
        while i < len(w):
            m = BRACE_RE.match(w, i)
            if m:
                cur.append(m.group(0))
                i = m.end()
                continue
            ch = w[i]
            if ch in OPEN_PARENS or ch in CLOSE_PARENS:
                word("".join(cur))
                cur = []
                out.append(("(" if ch in OPEN_PARENS else ")", ch))
            else:
                cur.append(ch)
            i += 1
        word("".join(cur))
    return out


def parse_cond_expr(cond: str, lineno: int):
    """原文 → 条件树：("or"|"and", [子树…]) / ("not", 子树) / ("cmp", 原文)。

    只管结构，比较本身（哪个运算符、两边是什么）留到求值时再拆——那时
    才知道是不是「直到 包含 X」这种省略左值的写法。
    """
    where = f"第 {lineno + 1} 行："
    toks = cond_tokens(cond)
    pos = 0

    def peek():
        return toks[pos][0] if pos < len(toks) else None

    def missing(after: str):
        nxt = peek()
        if nxt is None:
            return f"{where}「{after}」后面缺比较"
        if nxt == ")":
            return f"{where}「{after}」后面缺比较，紧跟着就是「{toks[pos][1]}」"
        return f"{where}「{after}」后面缺比较，紧跟着又是「{toks[pos][1]}」"

    def p_or():
        nonlocal pos
        items = [p_and()]
        while peek() == "or":
            pos += 1
            if peek() in (None, ")", "and", "or"):
                raise DSLError(missing(COND_OR))
            items.append(p_and())
        return items[0] if len(items) == 1 else ("or", items)

    def p_and():
        nonlocal pos
        items = [p_not()]
        while peek() == "and":
            pos += 1
            if peek() in (None, ")", "and", "or"):
                raise DSLError(missing(COND_AND))
            items.append(p_not())
        return items[0] if len(items) == 1 else ("and", items)

    def p_not():
        nonlocal pos
        kind = peek()
        if kind == "not":
            pos += 1
            if peek() in (None, ")", "and", "or"):
                raise DSLError(missing(COND_NOT))
            return ("not", p_not())
        if kind == "(":
            opened = toks[pos][1]
            pos += 1
            if peek() == ")":
                raise DSLError(f"{where}括号里是空的：「{opened}{toks[pos][1]}」")
            inner = p_or()
            if peek() != ")":
                raise DSLError(f"{where}括号不配对：「{opened}」没有对应的右括号")
            pos += 1
            return inner
        if kind in ("and", "or"):
            raise DSLError(f"{where}「{toks[pos][1]}」前面缺比较")
        if kind == ")":
            raise DSLError(f"{where}括号不配对：多了一个「{toks[pos][1]}」")
        words = []
        while peek() == "word":
            words.append(toks[pos][1])
            pos += 1
        if peek() == "(":
            raise DSLError(f"{where}「{' '.join(words)}」后面直接跟了括号，"
                           f"中间缺「且」或「或」（要比的值带括号的话先「设」进变量）")
        if peek() == "not":
            raise DSLError(f"{where}「非」只能写在一个比较的最前面："
                           f"「{' '.join(words)} 非 …」看不懂")
        return ("cmp", " ".join(words))

    if not toks:
        raise DSLError(f"{where}条件是空的")
    tree = p_or()
    if pos < len(toks):
        # 能走到这里的只有多出来的右括号：别的情况在 p_* 里已经报了
        raise DSLError(f"{where}括号不配对：多了一个「{toks[pos][1]}」")
    return tree


def _mask_braces(text: str) -> str:
    """{…} 整块换成等长的占位，找紧贴写法的运算符时不会找进变量名里。"""
    return BRACE_RE.sub(lambda m: "\0" * len(m.group(0)), text)


def split_raw_tail(raw: str):
    """原文版的 split_condition_tail：省略左值时拆出 (运算符, 右值原文)。"""
    parts = raw_words(raw)
    if parts:
        op = OP_BY_WORD.get(parts[0])
        if op is not None:
            right = " ".join(parts[1:])
            if op in UNARY_OPS and right:
                return None
            return op, right
    masked = _mask_braces(raw)
    for zh, op in CONDITION_OPS:
        if masked.startswith(zh):
            right = raw[len(zh):].strip()
            if op in UNARY_OPS and right:
                continue
            return op, right
    return None


def split_raw_cmp(raw: str):
    """原文版的 split_condition：拆成 (左值原文, 运算符, 右值原文)。

    规则跟 split_condition 一样（先整词、再紧贴写法，一元的右边要空、
    二元的两边都不能空），只是拆的是没展开的原文，所以 {变量} 展开成
    空串、或者值里有「等于」「包含」都不影响。紧贴写法不会在 {…} 里面找。
    """
    parts = raw_words(raw)
    for i, word in enumerate(parts):
        op = OP_BY_WORD.get(word)
        if op is None:
            continue
        left = " ".join(parts[:i])
        right = " ".join(parts[i + 1:])
        if op in UNARY_OPS:
            if right:
                continue
            return left, op, ""
        if not left or not right:
            continue
        return left, op, right

    masked = _mask_braces(raw)
    for zh, op in CONDITION_OPS:
        idx = masked.find(zh)
        if idx < 0:
            continue
        left, right = raw[:idx].strip(), raw[idx + len(zh):].strip()
        if op in UNARY_OPS:
            if right:
                continue
            return left, op, ""
        if not left or not right:
            continue
        return left, op, right
    return None


def eval_cond_expr(tree, expand, lineno: int, value=None) -> bool:
    """求值条件树。expand 把原文展开成文本；value 不是 None 时允许省略
    左值（「重试 … 直到 包含 X」），拿它当左值。且 / 或 短路。"""
    kind = tree[0]
    if kind == "or":
        return any(eval_cond_expr(t, expand, lineno, value) for t in tree[1])
    if kind == "and":
        return all(eval_cond_expr(t, expand, lineno, value) for t in tree[1])
    if kind == "not":
        return not eval_cond_expr(tree[1], expand, lineno, value)

    raw = tree[1]
    if value is not None:
        tail = split_raw_tail(raw)
        if tail is not None:
            op, right = tail
            return eval_parts(value, op, expand(right).strip())
    parsed = split_raw_cmp(raw)
    if parsed is None:
        raise DSLError(
            f"第 {lineno + 1} 行：看不懂的条件「{raw}」。可用："
            f"包含 / 不包含 / 等于 / 不等于 / 为空 / 不为空 / "
            f"大于 / 小于 / 不小于 / 不大于 / 开头是 / 结尾是"
            f"（符号 > < >= <= == != 也可以），"
            f"组合用 且 / 或 / 非 / 括号" + single_eq_hint(raw))
    left, op, right = parsed
    # 右值去首尾空白：早先整行展开后按空格切再拼，右值天然是去过空白的，
    # 「包含」这种不 strip 的比较要保持一样
    return eval_parts(expand(left), op, expand(right).strip())


def split_head(line: str):
    """拆出指令名和剩余部分。

    关键字后紧跟汉字时不算关键字：「打印机 状态」的 head 是「打印机」。
    """
    head, rest = split_ws_once(line)
    if head in KEYWORDS:
        return KEYWORDS[head], rest.strip()
    if head in KEYWORDS.values():
        return head, rest.strip()

    for zh in KEYWORDS_BY_LEN:
        if line.startswith(zh):
            tail = line[len(zh):]
            if tail and CJK.match(tail):
                continue
            return KEYWORDS[zh], tail.strip()
    return head, rest.strip()


def check_name(name: str, lineno: int = -1) -> str:
    """校验变量名。允许点号路径：每一段是标识符或者数字下标。"""
    ok = bool(name) and all(
        seg.isidentifier() or seg.lstrip("-").isdigit()
        for seg in name.split("."))
    if not ok:
        where = f"第 {lineno + 1} 行：" if lineno >= 0 else ""
        raise DSLError(f"{where}非法变量名：{name}")
    return name


def parse_trim_spec(spec: str, lineno: int):
    """解析「修剪历史」的参数，返回 (条数上限, 字数上限)。

    纯数字是条数，带「字」后缀是字符数，两个都写就两个上限都生效。

    两种单位并存是因为各有盲区：条数挡不住「一条挂了整课课文」，
    字数挡不住「几十条短消息」——多轮工具调用正是后者。
    """
    keep_n = None
    keep_chars = None

    for tok in spec.split():
        tok = tok.strip()
        if not tok:
            continue
        m = TRIM_CHARS_RE.match(tok)
        if m:
            keep_chars = int(m.group(1))
            continue
        if tok.isdigit():
            keep_n = int(tok)
            continue
        raise DSLError(
            f"第 {lineno + 1} 行：看不懂的修剪参数「{tok}」。"
            f"写法：修剪历史 20 / 修剪历史 8000字 / 修剪历史 20 8000字")

    if keep_n is None and keep_chars is None:
        keep_n = DEFAULT_TRIM_KEEP
    return keep_n, keep_chars
