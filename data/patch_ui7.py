# -*- coding: utf-8 -*-
"""加「宽」「高」「间距」「对齐」四个尺寸修饰。

    cd mcp
    py data/patch_ui7.py

依次打在 patch_ui.py / 2 / 3 / 4 / 5 / 6 之后。

为什么之前不加，现在加
----------------------
之前的理由是「像素不跨目标」——终端只有字符格，没有像素概念。但这个理由
站不住：Qt 的 setFixedWidth、Flutter 的 SizedBox 都是像素，几乎所有真实
的 GUI 工具包都支持它。唯一的例外是字符终端，而那是个假想目标，从来没有
要做。为一个假想目标牺牲真实目标的表达力，取舍是反的。

倒过来看更清楚：像素在 GUI 上几乎通用，反倒是早先收进来的「网格」在终端
里更难落地。

代价是这些硬编码之前散在 style.css.j2 里（760px 居中、90px 输入框、
两列网格），改个尺寸要翻 Jinja 文件。现在能写回 .ui。

引擎不校验单位
--------------
200px / 50% / 12rem / auto 都原样传给目标，认不认由目标决定。在引擎里
拦一道只会让 .ui 跟着某一个目标的单位表走，而那正是要避免的。
"""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
UI = BASE / "tools" / "ui.py"
LAYOUT = BASE / "templates" / "frontend" / "layout.j2"


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

    ok &= patch(UI,
        'KEYED_MODIFIERS = {"绑", "控件", "当", "比", "列数"}',
        '''KEYED_MODIFIERS = {"绑", "控件", "当", "比", "列数",
                   "宽", "高", "间距", "对齐"}

# 尺寸类修饰的值原样交给目标，引擎不解释也不校验单位：200px / 50% /
# 12rem / auto 认不认由目标决定，拦在这里只会让 .ui 跟着某一个目标的
# 单位表走。
SIZE_KEYS = {"宽": "width", "高": "height",
             "间距": "gap", "对齐": "align"}''',
        "词汇表加 宽/高/间距/对齐",
        marker='"宽", "高", "间距", "对齐"')

    ok &= patch(UI,
        '    cols: int = 0                # 「列数 n」：网格分几列',
        '''    cols: int = 0                # 「列数 n」：网格分几列
    size: dict = field(default_factory=dict)   # 宽/高/间距/对齐，原样传给目标''',
        "Node 加 size",
        marker="size: dict = field")

    ok &= patch(UI,
        '    for key, attr in (("比", "ratio"), ("列数", "cols")):',
        '''    for key, css in SIZE_KEYS.items():
        if key in keyed:
            node.size[css] = keyed[key]
    for key, attr in (("比", "ratio"), ("列数", "cols")):''',
        "_apply_keyed 解析尺寸",
        marker="node.size[css]")

    ok &= patch(UI,
        '            "ratio": self.ratio, "cols": self.cols,',
        '            "ratio": self.ratio, "cols": self.cols, "size": dict(self.size),',
        "to_dict 带上 size")

    ok &= patch(LAYOUT,
        '''<% macro 样式(node) -%>
<% if node.ratio or node.cols %> style="<% if node.ratio %>flex:<%= node.ratio %> 1 0%;min-width:0;min-height:0<% endif %><% if node.ratio and node.cols %>;<% endif %><% if node.cols %>grid-template-columns:repeat(<%= node.cols %>,1fr)<% endif %>"<% endif %>
<%- endmacro %>''',
        '''<% macro 样式(node) -%>
<% set 片段 = [] %>
<% if node.ratio %><% set _ = 片段.append("flex:" ~ node.ratio ~ " 1 0%") %><% set _ = 片段.append("min-width:0") %><% set _ = 片段.append("min-height:0") %><% endif %>
<% if node.cols %><% set _ = 片段.append("grid-template-columns:repeat(" ~ node.cols ~ ",1fr)") %><% endif %>
{#- 定宽要同时给 flex:none，否则父容器是 flex 时宽度会被压缩 -#}
<% if node.size.get("width") %><% set _ = 片段.append("width:" ~ node.size["width"]) %><% set _ = 片段.append("flex:none") %><% endif %>
<% if node.size.get("height") %><% set _ = 片段.append("height:" ~ node.size["height"]) %><% endif %>
<% if node.size.get("gap") %><% set _ = 片段.append("gap:" ~ node.size["gap"]) %><% endif %>
<% if node.size.get("align") %><% set _ = 片段.append("align-items:" ~ node.size["align"]) %><% endif %>
<% if 片段 %> style="<%= 片段 | join(";") %>"<% endif %>
<%- endmacro %>''',
        "样式宏支持尺寸",
        marker='node.size.get("width")')

    if ok:
        print("""
用法：

    布局 横排 间距 16px
      区域 侧栏 竖排 宽 200px          ← 定宽，自动带 flex:none
      区域 主区 竖排 比 3              ← 占剩下的
    结束
    分组 底 横排 高 60px 对齐 center

值原样传给目标，px / % / rem / auto 都行。

现在 style.css.j2 里那些硬编码（760px 居中、90px 输入框宽度、
网格两列）可以按需搬回 .ui，改布局不用再翻模板。""")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
