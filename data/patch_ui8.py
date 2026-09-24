# -*- coding: utf-8 -*-
"""让「宽」「高」「比」也对行节点生效，并把应用相关的硬编码从样式表挪走。

    cd mcp
    py data/patch_ui8.py

打在 patch_ui7.py 之后。

问题
----
patch_ui7 只给容器节点（布局/区域/分组/列表）接了尺寸修饰，行节点
（字段/动作/显示）没接。于是写「字段 learner 宽 90px」不报错、也不生效——
这是最难查的一类失败：写了、不报错、没作用。

顺带把 style.css.j2 里 `.bar-top input[type=text] { width:90px }` 这类
应用相关的硬编码删掉。那是「这个应用的学习者输入框」的宽度，不是所有
界面的通用默认，应该写在 .ui 里。样式表只留通用的：字号、内边距、
「底栏里没标尺寸的字段占满剩余」。
"""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
WIDGETS = BASE / "templates" / "frontend" / "widgets.j2"
CSS = BASE / "templates" / "frontend" / "style.css.j2"


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

    ok &= patch(WIDGETS,
        '<%- macro 当(node) -%>',
        '''{#- 尺寸修饰对行节点也要生效。之前只有容器接了「样式」宏，
    写「字段 x 宽 90px」不报错但没效果——那正是最难查的一类失败：
    写了、不报错、没作用。 -#}
<%- macro 尺寸(n) -%>
<%- set 片段 = [] -%>
<%- if n.size.get("width") -%><%- set _ = 片段.append("width:" ~ n.size["width"]) -%><%- set _ = 片段.append("flex:none") -%><%- endif -%>
<%- if n.size.get("height") -%><%- set _ = 片段.append("height:" ~ n.size["height"]) -%><%- endif -%>
<%- if n.ratio -%><%- set _ = 片段.append("flex:" ~ n.ratio ~ " 1 0%") -%><%- set _ = 片段.append("min-width:0") -%><%- endif -%>
<%- if 片段 %> style="<%= 片段 | join(";") %>"<% endif -%>
<%- endmacro -%>

<%- macro 当(node) -%>''',
        "widgets.j2 加 尺寸 宏",
        marker="macro 尺寸")

    ok &= patch(WIDGETS,
        '<label class="field"<%= 当(f) %>>',
        '<label class="field"<%= 当(f) %><%= 尺寸(f) %>>',
        "字段接尺寸")

    ok &= patch(WIDGETS,
        '<button type="submit" class="btn btn-primary"<%= 当(a) %>>',
        '<button type="submit" class="btn btn-primary"<%= 当(a) %><%= 尺寸(a) %>>',
        "提交动作接尺寸")

    ok &= patch(WIDGETS,
        '<p class="dyn"<%= 当(n) %>>',
        '<p class="dyn"<%= 当(n) %><%= 尺寸(n) %>>',
        "显示节点接尺寸")

    ok &= patch(CSS,
        '''.bar-bottom .field { flex:1; }
.bar-top input[type=text] { width:90px; }
.bar-top select, .bar-top input { font-size:13px; padding:4px 8px; }''',
        '''/* 底栏里没标尺寸的字段占满剩余——输入框几乎总是这样。
   标了「宽」的会带 flex:none 覆盖掉这条。 */
.bar-bottom .field { flex:1; }
/* 具体宽度写在 .ui 里，这里只管字号和内边距 */
.bar-top select, .bar-top input { font-size:13px; padding:4px 8px; }''',
        "样式表去掉应用相关的宽度",
        marker="具体宽度写在 .ui 里")

    if ok:
        print("""
现在这些都能写在 .ui 里：

    分组 顶栏 横排 顶栏 间距 12px 对齐 center
      字段 learner 共享 宽 90px 学习者
      字段 course 控件 下拉 宽 130px 课程
    结束

样式表留的是通用默认（字号、内边距、底栏字段占满），.ui 里写的覆盖它。

仍然只在样式表里的：消息区 760px 居中、textarea 的 min/max-height。
前者是「一行文字多长才好读」，跟具体界面无关；后者没有对应的修饰词。""")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
