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

四个字段：messages（追加）、state（合并）、lists（按数据键填表格）、
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


# 扩展名 -> 文件头该是什么样。存文件的「类型」白名单里有的才查
_ZIP_KINDS = {"docx", "xlsx", "pptx", "zip"}
_TEXT_KINDS = {"md", "txt", "csv", "json", "jsonl", "tsv"}


def _bad_header(ext: str, head: bytes) -> str:
    """文件头跟扩展名对不上时回一句说明，对得上回空串。"""
    if ext == "pdf" and not head.startswith(b"%PDF-"):
        return "不是 PDF（文件头不是 %PDF-）"
    if ext in _ZIP_KINDS and not head.startswith(b"PK"):
        return f"不是 {ext}（{ext} 文件其实是 zip，文件头该是 PK）"
    if ext in _TEXT_KINDS and b"\x00" in head:
        return "是二进制文件，不是纯文本"
    return ""


def _parse_size(s: str):
    """「20MB」「500KB」「1024」→ 字节数；认不出回 None。"""
    import re as _re
    m = _re.match(r"^\s*(\d+(?:\.\d+)?)\s*(B|KB|MB|GB)?\s*$", str(s), _re.I)
    if not m:
        return None
    unit = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}[(m.group(2) or "B").upper()]
    return int(float(m.group(1)) * unit)


def _human(n: int) -> str:
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.1f}MB"
    if n >= 1024:
        return f"{n / 1024:.0f}KB"
    return f"{n}B"


def register(reg, workspace):

    @reg.verb("往响应里塞一个字段：messages / state / lists / stream。")
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

    @reg.verb("填一张表格。数据键就是界面上那张表的名字（「绑」能另指）。"
              "例如 表格 prereq {行表}")
    def 表格(数据键: str, 内容) -> str:
        b = current()
        if b is None:
            return "[不在请求里]"
        rows = _as_data(内容)
        if not isinstance(rows, list):
            return "[表格数据要是列表]"
        # 早先这个动词直接写 b["rows"]，那时一个界面只能有一张表。现在按
        # 数据键分开放，跟「响应 lists {字典}」落在同一个地方——一个界面
        # 可以有几张表，哪张填哪组必须说清楚。
        #
        # 响应字段的白名单里已经没有 rows 了，所以再写那个键的话，整份
        # 数据会被静默丢掉：调了等于没调，还不报错。
        b.setdefault("lists", {})[数据键] = rows
        return ""

    @reg.verb("把上传的文件存到磁盘。返回存好的相对路径。"
              "可限类型和大小：存文件 document uploads 哈希 pdf,docx,md,txt 20MB")
    def 存文件(字段: str, 目录: str = "uploads", 命名: str = "哈希",
            类型: str = "", 上限: str = "") -> str:
        """存一个上传的文件，返回路径。

            设 路径 = 存文件 头像 uploads 哈希
            如果 {路径} 开头是 [
              返回 {"error":"{路径}"} 400
            结束

        **类型**（可选）：扩展名白名单，逗号隔开（pdf,docx,md,txt）。不光看
        扩展名，还看文件头——扩展名谁都能改：pdf 要以 %PDF- 开头，docx /
        xlsx / pptx 是 zip（PK 开头），md / txt / csv / json 不能有 NUL 字节
        （二进制文件改个名字混不进来）。别的扩展名只查扩展名。

        **上限**（可选）：单个文件的大小上限，20MB / 500KB / 字节数。整个
        请求另有 32MB 的总上限（路由器那层，超了直接 413）。

        不合格的回「[…]」开头的一句话，跟别的出错一样，不存盘。

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

        if 类型:
            allowed = [t.strip().lower().lstrip(".") for t in 类型.split(",") if t.strip()]
            got = (f.filename or "").rsplit(".", 1)[-1].lower() if "." in (f.filename or "") else ""
            if got not in allowed:
                return (f"[文件类型不支持] {f.filename or '（没有文件名）'}，"
                        f"只收 {'、'.join(allowed)}")
            bad = _bad_header(got, data[:4096])
            if bad:
                return f"[文件内容和扩展名对不上] {f.filename}：{bad}"
        if 上限:
            limit = _parse_size(上限)
            if limit is None:
                return f"[上限写错了] {上限}，写成 20MB / 500KB / 字节数"
            if len(data) > limit:
                return (f"[文件太大] {f.filename} 有 {_human(len(data))}，"
                        f"上限 {_human(limit)}")

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

    @reg.verb("上传字段的原文件名、大小、扩展名：{name, size, ext}。没有这个字段回空字典。")
    def 上传信息(字段: str) -> dict:
        from tools.http_ctx import uploads as _uploads
        from pathlib import Path

        f = (_uploads() or {}).get(字段)
        if f is None:
            return {}
        f.seek(0, 2)
        size = f.tell()
        f.seek(0)
        # 只留最后一段：上传的名字里可能带路径（../），这里只是给人看的名字
        name = Path((f.filename or "").replace("\\", "/")).name
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        return {"name": name, "size": size, "ext": ext}

    @reg.verb("这次请求带了哪些上传字段。排查用。")
    def 列上传() -> str:
        from tools.http_ctx import uploads as _uploads

        files = _uploads()
        if not files:
            return "（没有上传文件）"
        return "\n".join(
            f"{k}：{v.filename}（{v.content_type}）" for k, v in files.items())
