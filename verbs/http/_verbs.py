"""http 包：往 HTTP 响应里塞内容。

只在有请求上下文时能用——`dsl_run` 里调会返回「不在请求里」而不是正常
工作。这是有意的：这几个动词是给 `tools/dsl_http.py` 的路由器用的，
脱离请求没有意义。

上下文在 `tools/http_ctx.py`（一个 `threading.local()`）。放那儿而不是
放这个文件里，是因为路由器也要 import 它——动词包是用
`spec_from_file_location` 加载的，不走 `sys.path`，外面 import 不到。

    路由器每次请求前  http_ctx.set_bucket({})
    动词往 current() 返回的字典里塞
    路由器跑完        http_ctx.take_bucket()

代价是隐式上下文：动词的行为取决于外面设没设过。换成协程或多进程模型
就不对了——Flask 多线程下每个请求一个线程，所以现在成立。

## 只传数据，不传命令

四个字段：messages（追加）、state（合并）、rows（覆盖）、
stream（这批消息进哪条流）。

**先前有个「浮层」动词，用来让后端控制模态框开关，已经删掉。**
后端不该知道界面上有几个浮层、叫什么名字——那是界面自己的事。浮层的
显隐该由前端按 state 里的字段判断。

而且那条链本来就是断的：动词能塞 overlay，前端的 applyResponse 根本
不认这个字段，塞了静默丢掉。
"""

import json

from tools.http_ctx import RESPONSE_FIELDS, current


def _as_data(v):
    """参数可能是结构，也可能是 JSON 文本——引擎传参时会转成文本。"""
    if not isinstance(v, str):
        return v
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def register(reg, workspace):

    @reg.verb("往响应里塞一个字段：messages / state / rows / stream。")
    def 响应(字段: str, 内容) -> str:
        b = current()
        if b is None:
            # 明确报出来，不静默吞掉：脚本以为自己回了内容、实际什么都
            # 没发生，那种错误在接口上表现为「返回空」，极难查
            return "[不在请求里，响应无效]"
        if 字段 not in RESPONSE_FIELDS:
            return (f"[没有这个响应字段] {字段}，可用："
                    f"{'、'.join(RESPONSE_FIELDS)}")
        data = _as_data(内容)
        if 字段 == "messages":
            # 多次调用累加而不是覆盖——一个接口里分几处追加消息很常见
            b.setdefault("messages", []).extend(
                data if isinstance(data, list) else [data])
        elif 字段 == "state":
            if isinstance(data, dict):
                b.setdefault("state", {}).update(data)
        else:
            b[字段] = data
        return ""

    @reg.verb("追加一条消息。样式可填 user / ok / no / pending。")
    def 消息(谁: str, 内容: str, 样式: str = "") -> str:
        b = current()
        if b is None:
            return "[不在请求里，消息无效]"
        msg = {"who": 谁, "text": 内容}
        if 样式:
            msg["kind"] = 样式
        b.setdefault("messages", []).append(msg)
        return ""

    @reg.verb("设置一个状态字段。前端的「共享」字段和「显示」节点读它。")
    def 状态(字段: str, 值: str = "") -> str:
        b = current()
        if b is None:
            return "[不在请求里，状态无效]"
        b.setdefault("state", {})[字段] = 值
        return ""

    @reg.verb("指定 messages 进哪条消息流。界面上有多条流时必须给。")
    def 消息流(名字: str) -> str:
        b = current()
        if b is None:
            return "[不在请求里]"
        b["stream"] = 名字
        return ""

    @reg.verb("整块替换表格数据。内容是对象列表。")
    def 表格(内容) -> str:
        b = current()
        if b is None:
            return "[不在请求里]"
        rows = _as_data(内容)
        if not isinstance(rows, list):
            return "[表格数据要是列表]"
        b["rows"] = rows
        return ""

    @reg.verb("把上传的文件存到磁盘。返回存好的相对路径。")
    def 存文件(字段: str, 目录: str = "uploads", 命名: str = "哈希") -> str:
        """存一个上传的文件，返回路径。

            设 路径 = 存文件 头像 uploads 哈希
            如果 {路径} 开头是 [
              返回 {"error":"{路径}"} 400
            结束

        **命名三种**：

        哈希——文件内容的 sha256 前十六位加原扩展名。同样的文件不
        重复存，而且天然避开了路径注入和重名。默认用这个。

        时间——时间戳加原名。能看出传的是什么，代价是同一秒传两个
        同名文件会撞。

        原名——直接用上传的名字（洗掉路径分隔符）。重名会覆盖，而且
        用户能控制文件名——只在你确实需要原名时用。

        目录限制在 workspace 内，跟别的文件操作一致。
        """
        import hashlib
        import re as _re
        import time
        from pathlib import Path

        from tools.http_ctx import uploads as _uploads

        files = _uploads()
        if not files:
            return "[不在请求里，或者这次请求没带文件]"

        f = files.get(字段)
        if f is None:
            有 = "、".join(files) or "无"
            return f"[没有叫「{字段}」的上传字段] 这次带了：{有}"

        # 读之前回到开头。同一个字段存两次时，第二次的指针还停在末尾，
        # 读出来是空的——而那看起来像「用户传了个空文件」，查不到原因。
        f.seek(0)
        data = f.read()
        if not data:
            return f"[{字段} 是空文件]"

        base = Path(workspace) / 目录
        base.mkdir(parents=True, exist_ok=True)

        # 原扩展名只留字母数字——上传的名字不可信，而扩展名会拼进路径
        ext = ""
        if f.filename and "." in f.filename:
            raw = f.filename.rsplit(".", 1)[-1][:10]
            if raw.isalnum():
                ext = "." + raw.lower()

        if 命名 == "哈希":
            name = hashlib.sha256(data).hexdigest()[:16] + ext
        elif 命名 == "时间":
            洁 = _re.sub(r"[^\w.\-\u4e00-\u9fff]", "_", f.filename or "file")
            name = f"{int(time.time())}_{洁}"
        elif 命名 == "原名":
            # 只取最后一段并洗掉分隔符：上传的名字里带 ../ 是常见攻击
            洁 = _re.sub(r"[^\w.\-\u4e00-\u9fff]", "_",
                        Path(f.filename or "file").name)
            name = 洁 or "file"
        else:
            return f"[不认识的命名方式] {命名}，可用：哈希、时间、原名"

        target = (base / name).resolve()
        if base.resolve() not in target.parents:
            return f"[路径越界] {目录}/{name}"

        target.write_bytes(data)
        # 返回相对 workspace 的路径：绝对路径存进库里，换台机器就全废了
        return f"{目录}/{name}"

    @reg.verb("这次请求带了哪些上传字段。排查用。")
    def 列上传() -> str:
        from tools.http_ctx import uploads as _uploads

        files = _uploads()
        if not files:
            return "（没有上传文件）"
        return "\n".join(
            f"{k}：{v.filename}（{v.content_type}）" for k, v in files.items())
