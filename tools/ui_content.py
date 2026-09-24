# -*- coding: utf-8 -*-
"""把 `.ui` 里的「内容」和「图」变成 HTML。编译时做完，产物自包含。

    内容 about.md          读文件，转成 HTML 内联进产物
    图 logo.png 宽 200px    生成 <img>，尺寸走已有的尺寸键

## 为什么编译时转而不是运行时

跟这套东西一贯的路子一致：`.entity` 编译成 SQL、`.ui` 编译成 Vue、
`全部字段` 编译时展开。Markdown 也编译时转。

产物拿到就是 HTML，不用引 marked.js（四十来 KB），页面加载即显示不闪。
代价是内容改了要重新生成——而 `内容 about.md` 指的本来就是固定文件，
不是动态拉来的文章。

## 缺库时降级而不是报错

`markdown` 没装的话，把原文用 `<pre>` 包着显示，同时在 issues 里说一声。

报错挡住整个编译太重了：一个说明页面缺了样式，不该让别的界面也出不来。
而降级之后人一眼能看出「这块没渲染」，比白屏好查。

## 路径基准

相对 `options["content_root"]`，由调用方传。不给就不读文件，直接降级
成提示——`compile_ui` 收的是文本不是路径，它不知道 `.ui` 在哪儿。
"""

import html as _html
from pathlib import Path


def to_html(text: str) -> tuple:
    """Markdown 转 HTML。返回 (html, 用了什么)。

    第二个值说明走的哪条路：markdown 库，还是降级的 <pre>。调用方据此
    决定要不要在 issues 里提一句。
    """
    try:
        import markdown
    except ImportError:
        # 转义之后用 pre 包着——至少内容看得见，而且一眼知道没渲染
        return f"<pre class=\"md-raw\">{_html.escape(text)}</pre>", "raw"

    # fenced_code: ``` 围起来的代码块
    # tables: | 分隔的表格
    # 这两个是说明文字里最常用的，别的扩展用到再加
    return markdown.markdown(
        text, extensions=["fenced_code", "tables"]), "markdown"


def read_content(name: str, root) -> tuple:
    """读一个内容文件并转成 HTML。返回 (html, 问题)。

    `.md` 走 Markdown，`.html` 直接内联——后者是给「Markdown 表达不了
    的东西」留的口子（自定义类名、嵌套结构），不用为此再发明语法。

    读不到时返回一段带提示的 HTML 而不是抛异常：编辑时文件可能还没建，
    每次都让整个编译失败没法用。
    """
    if not root:
        return (_占位(f"没给内容目录，读不了 {name}"),
                f"「内容 {name}」：编译时没传 content_root，内容没读进来")

    base = Path(root).resolve()
    p = (base / name).resolve()

    # 路径来自 .ui 文本，挡住 ../ 跳出去
    if base != p and base not in p.parents:
        return (_占位(f"路径越界：{name}"), f"「内容 {name}」：路径越界")
    if not p.is_file():
        return (_占位(f"找不到 {name}"),
                f"「内容 {name}」：{p} 不存在")

    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        return _占位(f"读不了 {name}"), f"「内容 {name}」：{e}"

    if p.suffix.lower() in (".html", ".htm"):
        return text, ""

    html, how = to_html(text)
    if how == "raw":
        return html, (f"「内容 {name}」：markdown 库没装，"
                      f"原文按纯文本显示。pip install markdown")
    return html, ""


def img_tag(name: str, size: dict, label: str = "") -> str:
    """生成一个 <img>。

    尺寸走已有的尺寸键机制（`图 x.png 宽 200px` 解析出 size={"width":...}），
    所以这儿只管拼成 style。

    alt 用标签，没写标签时用文件名——空 alt 对读屏软件不友好，而文件名
    至少说明了是什么图。
    """
    style = "; ".join(f"{k}:{v}" for k, v in (size or {}).items())
    alt = _html.escape(label or name)
    src = _html.escape(name)
    style_attr = f' style="{_html.escape(style)}"' if style else ""
    return f'<img src="{src}" alt="{alt}"{style_attr}>'


def _占位(msg: str) -> str:
    """内容读不到时显示的东西。

    做成醒目的一块而不是空白：空白会让人以为是布局写错了，而这块能直接
    看出是内容没读进来。
    """
    return (f'<div class="md-missing" style="padding:10px 14px;'
            f'border:1px dashed #c66;color:#c66;font-size:13px">'
            f'{_html.escape(msg)}</div>')
