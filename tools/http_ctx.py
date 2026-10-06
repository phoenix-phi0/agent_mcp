# -*- coding: utf-8 -*-
"""HTTP 请求上下文：路由器和 http 动词包之间的桥。

放在 `tools/` 而不是包里，是因为两边都要 import 它：

    tools/dsl_http.py     每次请求前 set_bucket()，跑完 take_bucket()
    verbs/http/_verbs.py  动词往 current() 返回的字典里塞东西

动词包是用 spec_from_file_location 加载的，不走 sys.path——路由器
import 不到包里的东西，所以共享状态只能放在这种正经模块里。

用 threading.local 是因为 Flask 是多线程模型，每个请求一个线程。
**换成 async 框架就不对了**，那时要改成 contextvars。

## 响应只传数据，不传命令

四个字段，前三个是数据、第四个是归属：

    messages  追加到消息流的消息
    state     合并进跨界面状态（同名键覆盖）
    lists     表格数据，{数据键: 行表}，按键填对应的表格
    form      填进当前界面的表单（「载入」按地址参数拉回记录时用）
    stream    这批 messages 进哪条消息流；不给就进当前界面那条

**先前还有个 overlay，用来让后端控制模态框开关，已经删掉。**

理由是它跟另外几个不是一类东西：messages / state / lists 是后端算出来的
数据，stream 是数据的归属，而 overlay 是**命令**——让界面做一个动作。
把命令混进数据响应里，等于后端开始知道界面上有几个浮层、叫什么名字，
那跟 .ui 的定位（界面描述自己的行为，后端只提供数据）是冲突的。

浮层的显隐该由前端按状态自己判断：后端给 state，界面用「当 {字段}
不为空」这类条件决定显不显示。这样加一个浮层不用动后端。

顺带一提，删之前那条链本来就是断的：动词能塞 overlay，而前端生成的
applyResponse 根本不认这个字段，塞了也静默丢掉。两边各说各话没报错，
是因为前端对不认识的字段一律忽略。
"""

import threading

_ctx = threading.local()

# 响应里允许的字段。跟前端 applyResponse 认的那几个一致——
# 多一个就是塞了没人接的东西，前端会静默丢掉，不报错也不告警。
#
# form：填进当前界面的表单。「载入」按地址参数把记录拉回来时用
# （刷新编辑界面、打开别人发来的编辑链接）。
#
# lists：{数据键: 行表}。数据键默认是界面上那张表的名字，「绑」能另指
# 一个。早先还有个 rows（只能填一张表），已经去掉了——一个界面能有几张
# 表，哪张填哪组必须说清楚。
#
# go：换到哪个界面（界面名），地址参数随之清掉。前端早就认它（登录成功
# 回来处用的是「返回 {"go":…}」），但「返回」会作废之前「响应」攒的东西；
# 想既给 state 又换地址（做题页点「开始」退出按课练、回到不带 lesson 的
# #做题）就得能「响应 go 做题」。
RESPONSE_FIELDS = ("messages", "state", "stream", "form", "lists", "go")


def set_bucket(bucket: dict | None = None, uploads: dict | None = None,
               user: str = "", remote: str = "") -> dict:
    """建立本次请求的响应上下文。路由器在跑脚本前调。

    uploads 是这次请求带上来的文件（字段名 -> Flask 的 FileStorage）。
    它们不进字段表——字段表的值全是字符串，而文件要等脚本决定存哪儿。
    「存文件」动词从这儿取。

    user 是路由器从 cookie 认出来的当前用户，没登录是空串。

    remote 是请求的来源地址（Flask 的 remote_addr），登录限流按它计数。
    """
    _ctx.bucket = {} if bucket is None else bucket
    _ctx.uploads = uploads or {}
    _ctx.user = user or ""
    _ctx.remote = remote or ""
    _ctx.auth = None
    return _ctx.bucket


def current_user() -> str:
    """当前登录的用户，没登录或不在请求里是空串。"""
    return getattr(_ctx, "user", "") or ""


def current_remote() -> str:
    """当前请求的来源地址，不在请求里是空串。"""
    return getattr(_ctx, "remote", "") or ""


def request_auth(action) -> bool:
    """动词请求登录或退出：{"login": 用户名} 或 {"logout": True}。

    动词只提出要求，cookie 由路由器在组响应时设——签名密钥、cookie 的
    HttpOnly/SameSite 这些属性集中在路由器一处，不散在动词里。
    """
    if getattr(_ctx, "bucket", None) is None:
        return False
    _ctx.auth = action
    return True


def take_auth():
    """路由器取走这次请求的登录/退出要求，取完就清。"""
    action = getattr(_ctx, "auth", None)
    _ctx.auth = None
    return action


def uploads() -> dict:
    """这次请求带上来的文件。不在请求里时返回空表。"""
    return getattr(_ctx, "uploads", None) or {}


def current() -> dict | None:
    """当前请求的响应字典。不在请求里时返回 None。"""
    return getattr(_ctx, "bucket", None)


def take_bucket() -> dict:
    """拿走响应并清空上下文。路由器在脚本跑完后调。

    清空是必要的：线程会被复用，不清的话下一个请求可能读到上一个的残留。
    异常路径也要调，所以路由器里放在 finally。
    """
    out = getattr(_ctx, "bucket", None) or {}
    _ctx.bucket = None
    # uploads 一起清：线程会被复用，留着的话下个请求的「存文件」可能
    # 捡到上个请求的文件——那种错查起来极难，因为它只在高并发时出现
    _ctx.uploads = None
    # 当前用户同理：留着的话，下一个请求在认人之前调到的动词会以为是
    # 上一个人。登录/退出要求不在这儿清，路由器组完响应后用 take_auth 取
    _ctx.user = ""
    _ctx.remote = ""
    return out
