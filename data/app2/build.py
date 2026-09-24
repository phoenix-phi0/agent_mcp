# -*- coding: utf-8 -*-
"""从 ui/*.ui 生成界面。改了 .ui 之后跑一次，不用碰任何 Python 代码。

    py app2/build.py

产出两样，对应两种加载方式：

  web/index.html + app.js + style.css + vue.global.prod.js
      主窗口用。app.py 本来就起了服务器，有服务器就没必要把 164 KB 的
      Vue 塞进 HTML——单独一个文件还能走浏览器缓存。

  startup_html.py
      启动自检窗口用。那时候服务器还没起来（自检就是在查环境齐不齐），
      只能把整个应用内联成一个字符串交给 webview。

Vue 本体放本地不走 CDN：桌面程序不该因为断网白屏。也不在生成时下载——
打包依赖网络会让构建看天气。自己下载一份放进 assets/：
    https://unpkg.com/vue@3/dist/vue.global.prod.js
没有它主窗口照样生成（index.html 指向 CDN），只有内联窗口会跳过。

## 三样东西的出处

**字段表** ← `ui/表单.entity`，用跟数据库实体一样的语法和解析器。
但它不是数据库实体，gendb 不读它：.ui 里的字段是输入框，.entity 里的
字段是表列，两者只是恰好都叫「字段」。message 和 answer 是用户当场
输入、用完就没的东西，塞进 entities/学习.entity 会让 gendb 生成几个
不存在的表列。

**端点表** ← `routes/*.zs` 里的「接口 POST /x 动作 send」。加个接口
前端自动知道地址。缺的用下面的 FALLBACK 补——`/chat` 和 `/reset` 还在
app2/serve.py 里实现，没搬进 routes/。

**选项表** ← 同样来自 `表单.entity` 的枚举字段。

## 编译分三步，不是一步

先前直接 `compile_ui(文本)`，现在拆成：

    screens = parse(文本)
    ui_entity.expand(screens, entities)      # 展开「全部字段」
    compile_ui(screens, ...)

中间那步把 `全部字段 article 除 id` 变成一串具体的字段节点。放在这里
而不是 parse 里，是因为 parse() 不该知道实体长什么样——那样 ui.py 就
得 import entity.py，两个本来独立的语言绑死在一起。

compile_ui 的第一个参数本来就能接已解析的 screens，所以插得进去。
"""

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # 项目根，tools/ 在这
sys.path.insert(0, str(ROOT))

from tools import ui_entity                                 # noqa: E402
from tools.entity import (EntitySyntaxError, field_table,   # noqa: E402
                          options_map, parse, validate)
from tools.ui import UiSyntaxError, compile_ui              # noqa: E402
from tools.ui import parse as parse_ui                      # noqa: E402

VUE = HERE / "assets" / "vue.global.prod.js"
WEB = HERE / "web"
FORM = HERE / "ui" / "表单.entity"
ROUTES = ROOT / "routes"
CDN = "https://unpkg.com/vue@3/dist/vue.global.prod.js"

TITLE = "JP-E01-π 日语教师"

# 只有这些 issue 会挡住生成。其余的是提示——比如「有多个消息流」，
# 它说的是「后端返回记得带 stream 字段」，而不是界面写错了。
# 之前一视同仁，结果一条提示就让整个 build 什么都不写。
BLOCKING = {
    "syntax",            # 语法错误
    "unknown_field",     # 字段不在字段表里
    "untyped",           # 字段没有类型
    "dup_screen",        # 界面重名
    "path_conflict",     # 共享路径撞车
    "missing_endpoint",  # 远程动作没配端点
    "unknown_entity",    # 「全部字段 X」里的 X 不存在
    "not_screen",
    "empty_when",
}

# 动作名 -> 后端路径的兜底。
#
# 优先从 routes/*.zs 里读（那边写「接口 POST /x 动作 send」），这份只
# 补缺的：/chat 和 /reset 还在 app2/serve.py 里实现，没搬进 routes/。
# 搬完之后这个字典就能删。
#
# 搬不动的原因不在端点表：对话模式要调 agent，而 DSL 现在没有调 agent
# 的能力。卡在那儿，不是这里的问题。
FALLBACK_ENDPOINTS = {
    "send": "/chat",
    "reset": "/reset",
    "submit": "/drill/answer",
    "next": "/drill/next",
    "stop": "/drill/stop",
}

STARTUP_MODULE = '''"""由 app2/build.py 生成，请勿手改。
改 app2/ui/startup.ui 之后重新跑一次生成。"""

import json
import re

HTML = {html!r}

# 生成物里跨界面状态就是一行 JSON 字面量，运行时整行替换即可。
# 这样运行时一行模板引擎代码都不用跑——而这个窗口恰恰是环境不齐时
# 才弹的，不该在最脆弱的时刻引入最多依赖。
_SHARED = re.compile(r"const shared = ref\\((.*?)\\);")


def fill(missing, data_dir) -> str:
    """把自检结果填进页面，返回可直接交给 webview 的 HTML 字符串。

    missing: [(名字, 说明), ...]
    """
    state = {{
        "missing": [{{"who": w, "text": t}} for w, t in missing],
        "data_dir": str(data_dir),
    }}
    payload = json.dumps(state, ensure_ascii=False)
    return _SHARED.sub(
        lambda m: "const shared = ref(" + payload + ");", HTML, count=1)
'''


def load_form():
    """读 ui/表单.entity，返回 (实体列表, 字段表, 选项表)。

    读不到就返回空——那时 .ui 里每个字段都会报 unknown_field，
    错误信息会指向真正的原因（字段没定义），比在这里抛一个文件路径
    的异常更容易顺藤摸瓜。
    """
    if not FORM.is_file():
        print(f"  [错误] 没有 {FORM.name}，字段表是空的")
        return [], {}, {}
    try:
        entities = parse(FORM.read_text(encoding="utf-8"))
    except EntitySyntaxError as e:
        print(f"  [错误] {FORM.name} {e}")
        return [], {}, {}

    problems = validate(entities)
    for p in problems:
        print(f"  [错误] {FORM.name}：{p}")
    if problems:
        return [], {}, {}

    return entities, field_table(entities), options_map(entities)


def load_endpoints() -> dict:
    """先拿 routes/ 里声明的，缺的用兜底补上。

    打印每个动作的来源：「界面发到哪个地址」是调试时第一个要确认的事，
    两处来源混在一起时更该说清楚。
    """
    declared = {}
    if ROUTES.is_dir():
        try:
            from tools.dsl_http import endpoints_of
            declared = endpoints_of(ROUTES)
        except Exception as e:
            # 路由解析失败不该挡住界面生成——界面和后端是两条链，
            # 一条断了另一条照样能出产物
            print(f"  [提示] 读 routes/ 失败，全用兜底：{e}")

    out = dict(FALLBACK_ENDPOINTS)
    out.update(declared)

    for action, path in sorted(out.items()):
        来源 = "routes" if action in declared else "兜底"
        print(f"  {action:8} → {path:22} [{来源}]")

    多余 = set(declared) - set(FALLBACK_ENDPOINTS)
    if 多余:
        print(f"  [提示] routes/ 里这些动作在兜底表里没有，"
              f"确认界面上有同名动作：{'、'.join(sorted(多余))}")
    return out


def _report(name, issues) -> bool:
    """打印 issue，返回是否可以继续生成。"""
    blocking = [i for i in issues if i.code in BLOCKING]
    notes = [i for i in issues if i.code not in BLOCKING]

    for i in blocking:
        print(f"  [错误] {name}：{i}")
    for i in notes:
        print(f"  [提示] {name}：{i}")
    return not blocking


def _prepare(path: Path, entities):
    """解析并展开「全部字段」。返回 (screens, issues)，失败时 screens 是 None。"""
    try:
        screens = parse_ui(path.read_text(encoding="utf-8"))
    except UiSyntaxError as e:
        print(f"  [错误] {path.name}：{e}")
        return None, []
    issues = ui_entity.expand(screens, entities) if entities else []
    return screens, issues


def build_main(entities, fields: dict, opts: dict, endpoints: dict) -> int:
    """主窗口：三个文件，交给服务器。"""
    if not fields:
        print("  [跳过] main.ui：字段表是空的，先修 表单.entity")
        return 1

    screens, issues = _prepare(HERE / "ui" / "main.ui", entities)
    if screens is None:
        return 1

    r = compile_ui(screens, backend="vue", fields=fields, require_bind=True,
                   options={"title": TITLE, "options_map": opts,
                            "endpoints": endpoints})
    if not _report("main.ui", issues + r["issues"]):
        return 1

    WEB.mkdir(exist_ok=True)
    files = r["result"]["files"]

    if VUE.is_file():
        shutil.copy2(VUE, WEB / VUE.name)
        files["index.html"] = files["index.html"].replace(CDN, f"./{VUE.name}")
    else:
        print(f"  [提示] 没有 {VUE.name}，index.html 指向 CDN，断网会白屏")

    for name, text in files.items():
        (WEB / name).write_text(text, encoding="utf-8")
        print(f"  web/{name}  {len(text)} 字节")
    return 0


def build_startup(entities) -> int:
    """启动自检窗口：内联成一个字符串常量。

    没有 Vue 本体就跳过——这个窗口的全部意义就是自包含，指向 CDN 的话
    断网时会白屏，而断网恰恰是它可能要报告的问题之一。
    跳过不算失败：主窗口不受影响，app.py 里有纯文本的退路。

    不传字段表：这个界面只有文案和消息流，没有输入框。
    """
    if not VUE.is_file():
        print(f"  [跳过] startup_html.py：assets/ 下没有 {VUE.name}")
        print(f"         要用内联窗口的话下载一份放过去：{CDN}")
        return 0

    screens, issues = _prepare(HERE / "ui" / "startup.ui", entities)
    if screens is None:
        return 1

    r = compile_ui(screens, backend="vue",
                   options={"title": TITLE, "inline": True,
                            "vue_path": str(VUE)})
    if not _report("startup.ui", issues + r["issues"]):
        return 1

    html = r["result"]["files"]["index.html"]
    (HERE / "startup_html.py").write_text(
        STARTUP_MODULE.format(html=html), encoding="utf-8")
    print(f"  startup_html.py  {len(html) / 1024:.0f} KB")
    return 0


def main() -> int:
    print("读字段表：")
    entities, fields, opts = load_form()
    if fields:
        枚举 = "、".join(f"{k}({len(v)}项)" for k, v in opts.items()
                        if "." not in k)
        # 带实体名的键不单独列——它们跟裸名是同一批字段，列出来只是噪音
        裸 = [k for k in fields if "." not in k]
        print(f"  {FORM.name}  {len(裸)} 个字段"
              + (f"，枚举：{枚举}" if 枚举 else ""))

    print("\n读端点表：")
    endpoints = load_endpoints()

    print("\n生成界面：")
    bad = build_main(entities, fields, opts, endpoints) + build_startup(entities)
    print("完成" if not bad else "有错误，见上面")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
