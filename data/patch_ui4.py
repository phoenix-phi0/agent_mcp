# -*- coding: utf-8 -*-
"""给模板加旧版 serve.py 有、而 .ui 表达不了的那几样交互。

    cd mcp
    py data/patch_ui4.py

依次打在 patch_ui.py / patch_ui2.py / patch_ui3.py 之后。

为什么放模板不放 .ui 词汇表
--------------------------
旧版界面有四样东西 .ui 说不出来：模式切换、Enter 发送、textarea 自动
长高、工具调用折叠面板。

第一样其实不用加东西——两个模式就是两个「界面」，导航栏本来就是切界面
的，练习选项自然只出现在练习那页。

剩下三样是「HTML 上的文本框和消息该怎么用」，不是「界面上有什么」。
写进 .ui 就成了只有 HTML 目标认识的词，Qt 和终端目标没法解释——那会
破坏「词汇只收布局意图」那条线。做成模板的通用能力则对所有 .ui 都生效，
一个字也不用多写。

乐观占位也顺手做了：发请求前先摆一条「…」，回来再换掉。没有这个的话，
慢的接口会让界面看起来像卡住了。
"""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
UI = BASE / "tools" / "ui.py"
APP = BASE / "templates" / "frontend" / "app.js.j2"
WID = BASE / "templates" / "frontend" / "widgets.j2"


def patch(path: Path, old: str, new: str, label: str, marker: str = "") -> bool:
    text = path.read_text(encoding="utf-8")
    probe = marker or new.strip()[:40]
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

    # --- 1. Node 加 submit_action，渲染前按界面填 ---
    ok &= patch(UI,
        '''    role: Optional[str] = None
    modifiers: list = field(default_factory=list)''',
        '''    role: Optional[str] = None
    submit_action: str = ""      # 本界面按 Enter 触发的动作，渲染前填
    modifiers: list = field(default_factory=list)''',
        "Node 加 submit_action")

    ok &= patch(UI,
        '''def render_vue(screens''',
        '''def _tag_submit_action(screens) -> None:
    """给每个节点记上「本界面按 Enter 该触发哪个动作」。

    必须按界面分：全局取第一个的话，在练习页按 Enter 会打到对话页的
    发送动作上——界面切了，请求还发往旧接口，而且不报错。

    挂在节点上而不是当渲染参数传：layout.j2 是递归的，参数要穿过每一层
    宏调用才能到 widgets.j2，多加一个上下文变量就要改三个模板。节点自己
    带着走，模板只读 node.submit_action。
    """
    for screen in screens:
        name = ""
        for a in screen.actions():
            if a.has("提交") and a.has("远程"):
                name = a.name
                break
        for n in screen.walk():
            n.submit_action = name


def render_vue(screens''',
        "新增 _tag_submit_action")

    ok &= patch(UI,
        '''    options_map = options_map or {}
    rows = rows or []
    endpoints = endpoints or {}''',
        '''    options_map = options_map or {}
    rows = rows or []
    endpoints = endpoints or {}
    _tag_submit_action(screens)''',
        "render_vue 调 _tag_submit_action",
        marker="_tag_submit_action(screens)")

    # --- 2. app.js.j2：按键、长高、乐观占位 ---
    ok &= patch(APP,
        '''    function onRow(name, row) {''',
        '''    // 以下两样是所有界面通用的输入行为，不进 .ui 词汇表：
    // 它们是「HTML 上的文本框该怎么用」，不是「界面上有什么」。

    // Enter 发送，Shift+Enter 换行。动作名由节点带过来，按界面不同。
    function onKey(ev, actionName) {
      if (ev.key !== "Enter" || ev.shiftKey) return;
      ev.preventDefault();
      if (actionName) submitTo(actionName);
    }

    // textarea 跟着内容长高，到上限就滚动
    function grow(ev) {
      const el = ev.target;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 180) + "px";
    }

    function onRow(name, row) {''',
        "app.js.j2 加 onKey / grow")

    ok &= patch(APP,
        '''    async function submitTo(name) {''',
        '''    async function submitTo(name) {
      // 乐观占位：先摆一条「…」，请求回来再换掉。没有这个的话，
      // 慢的接口会让界面看起来像卡住了。
      const stream = <%= first_stream_json %>;
      let placeholder = null;
      if (stream && shared.value[stream]) {
        placeholder = { who: "", text: "…", kind: "pending" };
        shared.value[stream].push(placeholder);
      }
      const drop = () => {
        if (!placeholder) return;
        const list = shared.value[stream] || [];
        const i = list.indexOf(placeholder);
        if (i >= 0) list.splice(i, 1);
        placeholder = null;
      };
      try {
        return await _submitTo(name, drop);
      } catch (e) {
        drop();
        if (stream) pushMessages(stream, [{who: "出错", text: String(e), kind: "no"}]);
      }
    }

    async function _submitTo(name, drop) {''',
        "app.js.j2 加乐观占位")

    ok &= patch(APP,
        '''      const ep = <% if has_endpoints %>endpoints[name]<% else %>null<% endif %>;
      if (ep) { applyResponse(await postTo(ep, { action: name, form: form.value })); return; }
      console.log("submit", name, form.value);''',
        '''      const ep = <% if has_endpoints %>endpoints[name]<% else %>null<% endif %>;
      if (ep) {
        const resp = await postTo(ep, { action: name, form: form.value });
        if (drop) drop();
        applyResponse(resp);
        return;
      }
      if (drop) drop();
      console.log("submit", name, form.value);''',
        "_submitTo 收尾清占位")

    ok &= patch(APP,
        ''', onSubmit, onAction, onRow, screens''',
        ''', onSubmit, onAction, onRow, onKey, grow, screens''',
        "导出 onKey / grow")

    # --- 3. widgets.j2：textarea 绑事件，消息带 calls 出折叠面板 ---
    ok &= patch(WID,
        '''<textarea v-model="<%= model %>" rows="8"<% if f.required %> required<% endif %>></textarea>''',
        '''<textarea v-model="<%= model %>" rows="8"<% if f.required %> required<% endif %> @keydown="onKey($event, '<%= f.submit_action %>')" @input="grow"></textarea>''',
        "textarea 绑按键和长高")

    ok &= patch(WID,
        '''<div class="body">{{ m.text }}</div>
</div>''',
        '''<div class="body">{{ m.text }}</div>
<details v-if="m.calls && m.calls.length" class="tools">
<summary>{{ m.calls.length }} 次工具调用</summary>
<div v-for="(c, j) in m.calls" :key="j">{{ c.name }}({{ c.arguments }})
  → {{ c.result }}</div>
</details>
</div>''',
        "消息带 calls 渲染成折叠面板")

    if ok:
        print("""
全部完成。后端在消息里加 calls 字段就会出折叠面板：

    {"who": "老师", "text": "...", "calls": [
        {"name": "run_flow", "arguments": "kana.zs", "result": "..."}]}

有多个消息流时，返回里要带 stream 指明进哪条，否则一律落到第一条
（validate 会提示这一点）。""")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
