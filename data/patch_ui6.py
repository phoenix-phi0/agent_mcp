# -*- coding: utf-8 -*-
"""加「比」和「列数」两个带参修饰，让 .ui 能表达比例。

    cd mcp
    py data/patch_ui6.py

依次打在 patch_ui.py / 2 / 3 / 4 / 5 之后。

为什么比例该进词汇表
--------------------
之前这套词只能说方向（横排/竖排/网格）、伸缩（占满）、位置（顶栏/底栏），
说不了「侧栏和主区按 1:3 分」。结果是比例只能硬编码在 style.css.j2 里——
.grid 写死两列、侧栏宽度写死在样式表。布局参数并没有消失，只是从那份
人人能读的 .ui 挪进了模板，改一个比例要去翻 Jinja 文件。

比例跟 200px 不同，它在三个目标上含义一致：

    比 1 / 比 3   →  HTML flex:1 / flex:3
                     Qt   setStretch(0,1) / setStretch(1,3)
                     终端  按份额分字符列

所以它是布局*意图*不是布局*参数*，够格收进来。像素、gap、断点仍然挡在
外面——那些只有 HTML 认识。

为什么挂在子节点上
------------------
写成「布局 横排 比例 1:3」的话，容器要知道自己有几个孩子，增删或重排
子节点就会错位。「比 n」跟着节点走，加一个孩子不影响别人。
"""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
UI = BASE / "tools" / "ui.py"
LAYOUT = BASE / "templates" / "frontend" / "layout.j2"
WIDGETS = BASE / "templates" / "frontend" / "widgets.j2"


def patch(path: Path, old: str, new: str, label: str, marker: str = "") -> bool:
    text = path.read_text(encoding="utf-8")
    probe = marker or new.strip()[:30]
    if probe and probe in text:
        print(f"  跳过（已打过）：{label}")
        return True
    if old not in text:
        print(f"  找不到锚点：{label}")
        return False
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"  已改：{label}")
    return True


def main() -> int:
    ok = True

    # --- Node 加两个字段 ---
    ok &= patch(UI,
        '    role: Optional[str] = None\n',
        '''    role: Optional[str] = None
    ratio: int = 0               # 「比 n」：在兄弟节点间占的份额，0 表示不参与
    cols: int = 0                # 「列数 n」：网格分几列
''',
        "Node 加 ratio / cols",
        marker="ratio: int = 0")

    ok &= patch(UI,
        '''            "modifiers": list(self.modifiers), "line": self.line,''',
        '''            "ratio": self.ratio, "cols": self.cols,
            "modifiers": list(self.modifiers), "line": self.line,''',
        "to_dict 带上 ratio / cols")

    # --- 词汇表 ---
    ok &= patch(UI,
        'KEYED_MODIFIERS = {"绑", "控件", "当"}',
        '''# 「比」挂在子节点上而不是容器上（不写成「布局 横排 比例 1:3」）：
# 份额跟着节点走，增删或重排子节点都不会错位，容器也不必知道有几个孩子。
KEYED_MODIFIERS = {"绑", "控件", "当", "比", "列数"}''',
        "词汇表加 比 / 列数",
        marker='"比", "列数"')

    ok &= patch(UI,
        '''    if "当" in keyed:
        node.when = keyed["当"]''',
        '''    if "当" in keyed:
        node.when = keyed["当"]
    for key, attr in (("比", "ratio"), ("列数", "cols")):
        if key in keyed:
            try:
                n = int(keyed[key])
            except ValueError:
                n = 0            # 写了非数字就当没写，不值得为此中断解析
            setattr(node, attr, max(n, 0))''',
        "_apply_keyed 解析 比 / 列数")

    # --- 模板：走内联 style ---
    ok &= patch(LAYOUT,
        '<% macro 节点(node) %>',
        '''{#- 「比 n」和「列数 n」是每个节点自己的值，class 装不下，走内联 style。
    比例在三个目标上含义一致（flex 份额 / Qt stretch / 终端列宽），
    所以它是布局意图不是参数，够格进词汇表。 -#}
<% macro 样式(node) -%>
<% if node.ratio or node.cols %> style="<% if node.ratio %>flex:<%= node.ratio %> 1 0%;min-width:0;min-height:0<% endif %><% if node.ratio and node.cols %>;<% endif %><% if node.cols %>grid-template-columns:repeat(<%= node.cols %>,1fr)<% endif %>"<% endif %>
<%- endmacro %>

<% macro 节点(node) %>''',
        "layout.j2 加 样式 宏",
        marker="macro 样式")

    ok &= patch(LAYOUT,
        '''<section class="<%= node.kind == "布局" and "layout" or node.kind == "区域" and "region" or "group" %> <%= 布局类(node) %>"<%= 当(node) %>>''',
        '''<section class="<%= node.kind == "布局" and "layout" or node.kind == "区域" and "region" or "group" %> <%= 布局类(node) %>"<%= 当(node) %><%= 样式(node) %>>''',
        "容器节点带上 样式")

    ok &= patch(WIDGETS,
        '<section class="stream"<%= 当(n) %>>',
        '<section class="stream"<%= 当(n) %><% if n.ratio %> style="flex:<%= n.ratio %> 1 0%;min-height:0"<% endif %>>',
        "消息流带上 比")

    if ok:
        print("""
用法：

    布局 横排
      区域 侧栏 竖排 比 1       ← 占 1 份
      区域 主区 竖排 比 3       ← 占 3 份
    结束

    分组 内容 网格 列数 3       ← 三列等宽

「占满」是「比 1」的简写，两者都写时以「比」为准。
仍然挡在外面的：像素、gap、断点——那些只有 HTML 认识。""")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
