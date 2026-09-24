# -*- coding: utf-8 -*-
"""把生成的 .ui 编译成能塞进 iframe 的单个 HTML。

跟 `app2/build.py` 的正式生成走同一条链（parse → 展开全部字段 →
compile_ui），只有三处不同：

**产物要自包含**。iframe 用 srcdoc 加载，那里没有服务器，外链的
`style.css` 和 `app.js` 取不到，所以都得内联进 HTML。

**端点缺失降级成提示**。生成的界面里有 `动作 save 远程 保存`，正式
生成时没配端点是要挡住的；预览时挡住就什么都看不见了，而「这个动作
还没接后端」在预览阶段本来就是正常状态。

**出错时返回 None 而不是抛**。编辑到一半语法必然不完整，每敲一个字
就白屏没法用——调用方拿到 None 就保留上一版。

## 为什么用 iframe

样式和脚本都是隔离的。直接塞进页面某个 div 的话，生成的 HTML 里那些
`body{...}` 是全局的，一进来编辑器的布局就变了；Vue 初始化也会跟页面
已有的脚本挤在一个作用域里。

Shadow DOM 能隔离样式但隔不了脚本。开新窗口不用隔离，但看不到「改左边
右边立刻变」那个效果。
"""

import sys
import traceback
from pathlib import Path

# 项目根要在 path 里才 import 得到 tools.*。core.py 开头也有这段，但
# 这个模块是被 web.py 直接 import 的，走不到那儿——谁先被 import 不
# 一定，所以每个碰 tools 的模块都得自己管。
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import ui_entity
from tools.entity import field_table, options_map
from tools.ui import UiSyntaxError, compile_ui
from tools.ui import parse as parse_ui

# 预览时不该挡住渲染的 issue。
#
# 端点没配、消息流有多条——这些说的是「后端还得配点东西」，不是界面
# 写错了。正式生成时它们该挡住，预览时挡住就什么都看不见。
SOFT = {"missing_endpoint", "unknown_endpoint", "multi_stream"}


def render(ui_text: str, entities) -> dict:
    """编译一段 .ui。返回 {"html", "issues", "error"}。

    html 为 None 表示这次没编出来，调用方保留上一版。
    """
    try:
        screens = parse_ui(ui_text)
    except UiSyntaxError as e:
        return {"html": None, "issues": [], "error": f"语法错误：{e}"}
    except Exception as e:
        return {"html": None, "issues": [],
                "error": f"{type(e).__name__}: {e}"}

    issues = []
    if entities:
        issues += [str(i) for i in ui_entity.expand(screens, entities)]

    # 没有实体定义时不传字段表：bind() 会给每个字段报 unknown_field，
    # 满屏的错误盖住真正的问题。宁可让类型未知。
    fields = field_table(entities) if entities else None
    opts = options_map(entities) if entities else {}

    try:
        r = compile_ui(screens, backend="vue", fields=fields,
                       options={"title": "预览", "options_map": opts,
                                "inline": True})
    except Exception:
        return {"html": None, "issues": issues,
                "error": traceback.format_exc(limit=3)}

    硬的, 软的 = [], []
    for i in r.get("issues", []):
        (软的 if getattr(i, "code", "") in SOFT else 硬的).append(str(i))

    files = r["result"]["files"]
    html = files.get("index.html", "")

    # inline 选项没生效时自己拼。模板认不认 inline 取决于版本，而预览
    # 必须自包含——判据是「产物里有 app.js 但 HTML 里没有 <script>」，
    # 那说明它还指望外链。
    if "app.js" in files and "<script>" not in html:
        html = _inline(html, files)

    return {"html": html, "issues": issues + 硬的 + 软的, "error": None}


def _inline(html: str, files: dict) -> str:
    """把 style.css 和 app.js 塞进 HTML。"""
    css = files.get("style.css", "")
    js = files.get("app.js", "")
    if css:
        html = html.replace("</head>", f"<style>{css}</style></head>")
    if js:
        html = html.replace("</body>", f"<script>{js}</script></body>")
    return html
