# -*- coding: utf-8 -*-
"""加「提示」「单行高」两个修饰，并让空标签不再渲染成一行字段名。

    cd mcp
    py data/patch_hint.py

改的是四处显示问题，都是上一轮生成物里肉眼看出来的：

1. 顶栏底栏渲染出「顶栏」「底栏」两个 h3。样式表里靠 display:none 藏着，
   但那是拿 CSS 盖住一个本来就不该产生的东西。改成模板里不渲染。

2. 底栏的 textarea 是 rows="8"，起手就八行高，把底栏撑得很厚。
   加「单行高」旗标 → rows="1"，靠已有的 grow 跟着内容长。

3. 「说点什么…（Enter 发送…）」这句渲染成了输入框上方的标签。旧版里
   它是框内灰字。加「提示 <文字>」→ placeholder。

4. 「显示 usage」没写标签时回退成字段名，顶栏右边会出现「usage 1,280 token」。
   改成标签等于名字（即 .ui 里没写）就不渲染那个 span。

注意「提示」的值不能有空格：修饰值按空格切分，空格会把它截断。
"""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
UI = BASE / "tools" / "ui.py"
WID = BASE / "templates" / "frontend" / "widgets.j2"
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

    # --- 1. 词汇与节点字段 ---
    ok &= patch(UI,
        '    "共享",',
        '''    "单行高",                        # textarea 起手一行，靠 grow 跟着内容长
    "共享",''',
        "加「单行高」旗标",
        marker='"单行高"')

    ok &= patch(UI,
        '''                   "宽", "高", "间距", "对齐"}''',
        '''                   "宽", "高", "间距", "对齐", "提示"}''',
        "加「提示」带参修饰",
        marker='"对齐", "提示"')

    ok &= patch(UI,
        '    submit_action: str = ""',
        '''    hint: str = ""               # 「提示 ...」：框内灰字，不是框上方的标签
    submit_action: str = ""''',
        "Node 加 hint",
        marker="hint: str")

    ok &= patch(UI,
        '''    if "当" in keyed:
        node.when = keyed["当"]''',
        '''    if "当" in keyed:
        node.when = keyed["当"]
    if "提示" in keyed:
        node.hint = keyed["提示"]''',
        "_apply_keyed 解析 提示",
        marker='node.hint = keyed')

    ok &= patch(UI,
        '''            "ratio": self.ratio, "cols": self.cols, "size": dict(self.size),''',
        '''            "ratio": self.ratio, "cols": self.cols, "size": dict(self.size),
            "hint": self.hint,''',
        "to_dict 带上 hint")

    # --- 2. textarea：单行高 + placeholder ---
    ok &= patch(WID,
        '''<textarea v-model="<%= model %>" rows="8"<% if f.required %> required<% endif %> @keydown="onKey($event, '<%= f.submit_action %>')" @input="grow"></textarea>''',
        '''<textarea v-model="<%= model %>" rows="<% if f.has("单行高") %>1<% else %>8<% endif %>"<% if f.hint %> placeholder="<%= f.hint %>"<% endif %><% if f.required %> required<% endif %> @keydown="onKey($event, '<%= f.submit_action %>')" @input="grow"></textarea>''',
        "textarea 支持 单行高 / 提示",
        marker='rows="<% if f.has("单行高")')

    ok &= patch(WID,
        '<input type="text" v-model="<%= model %>"<% if f.required %> required<% endif %>>',
        '<input type="text" v-model="<%= model %>"<% if f.hint %> placeholder="<%= f.hint %>"<% endif %><% if f.required %> required<% endif %>>',
        "文本框支持 提示")

    # --- 3. 没写标签就不渲染 lbl ---
    ok &= patch(WID,
        '''<label class="field"<%= 当(f) %><%= 尺寸(f) %>>
<span class="lbl"><%= f.label or f.name %><% if f.required %><span class="req">*</span><% endif %></span>
<%= 控件(f) %>
</label>''',
        '''<label class="field"<%= 当(f) %><%= 尺寸(f) %>>
{#- 标签等于名字说明 .ui 里没写标签，那就别渲染一行英文字段名出来 -#}
<% if f.label and f.label != f.name %><span class="lbl"><%= f.label %><% if f.required %><span class="req">*</span><% endif %></span>
<% elif f.required %><span class="lbl"><span class="req">*</span></span>
<% endif %><%= 控件(f) %>
</label>''',
        "字段没标签就不渲染 lbl",
        marker="标签等于名字说明")

    ok &= patch(WID,
        '''<p class="dyn"<%= 当(n) %><%= 尺寸(n) %>><span class="lbl"><%= n.label or n.name %></span>
<span class="dyn-v">{{ getPath(shared, '<%= n.bind or n.name %>') }}</span></p>''',
        '''<p class="dyn"<%= 当(n) %><%= 尺寸(n) %>><% if n.label and n.label != n.name %><span class="lbl"><%= n.label %></span>
<% endif %><span class="dyn-v">{{ getPath(shared, '<%= n.bind or n.name %>') }}</span></p>''',
        "显示节点没标签就不渲染 lbl")

    # --- 4. 顶栏底栏不出 h3 ---
    ok &= patch(LAYOUT,
        '''  <% if node.kind == "分组" and node.name %>
  <h3><%= node.name %></h3>''',
        '''  {#- 顶栏底栏的名字只是给人看 .ui 时定位用的，不渲染成标题。
      之前靠 CSS display:none 藏，那是拿样式盖住不该产生的东西。 -#}
  <% if node.kind == "分组" and node.name and not (node.has("顶栏") or node.has("底栏")) %>
  <h3><%= node.name %></h3>''',
        "顶栏底栏不渲染 h3",
        marker="顶栏底栏的名字只是")

    if ok:
        print("""
用法：

    字段 message 单行高 提示 说点什么…（Enter发送，Shift+Enter换行）
    显示 usage                      ← 不写标签，只显示值

提示的值不能含空格：修饰值按空格切分，空格会把它截断。

改完重新生成：py app2/build.py""")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
