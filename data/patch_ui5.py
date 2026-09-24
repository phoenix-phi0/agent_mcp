# -*- coding: utf-8 -*-
"""加「顶栏」「底栏」两个布局修饰，让界面能做成三段式。

    cd mcp
    py data/patch_ui5.py

依次打在 patch_ui.py / 2 / 3 / 4 之后。

为什么要加这两个词
------------------
旧版 agents/serve.py 的界面是三段式全屏：header 固定在顶、footer 固定在
底、中间的消息区 flex:1 自己滚。生成的界面之前是普通文档流，消息一多
输入框就被推出屏幕。

.ui 原有的修饰只说方向（竖排/横排/网格）和伸缩（占满），说不了「谁固定
不动、谁负责滚」。加这两个词补上这一层。

它们仍然是布局*意图*不是参数：Qt 里对应工具条和状态栏，终端里对应固定的
首末行，三个目标都有对应物，不违反「词汇只收布局意图」那条线。

样式那边 style.css.j2 已经按旧版配色重写过（#faf9f7 底、#6b5b95 深紫、
用户消息浅蓝气泡），这个补丁只管词汇和 class。
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
        '    "共享",',
        '''    "顶栏", "底栏",                   # 固定在界面顶/底，中间那段自己滚
    "共享",''',
        "词汇表加 顶栏 / 底栏",
        marker='"顶栏", "底栏"')

    ok &= patch(LAYOUT,
        '''<% if node.has("横排") %>row<% elif node.has("网格") %>grid<% else %>col<% endif %><% if node.has("占满") %> grow<% endif %>''',
        '''<% if node.has("横排") %>row<% elif node.has("网格") %>grid<% else %>col<% endif %><% if node.has("占满") %> grow<% endif %><% if node.has("顶栏") %> bar-top<% endif %><% if node.has("底栏") %> bar-bottom<% endif %>''',
        "布局类加 bar-top / bar-bottom",
        marker="bar-top")

    if ok:
        print("""
用法：

    界面 自定义 对话
      分组 顶栏 横排 顶栏        ← 固定在顶，不滚
        字段 learner 共享 学习者
        显示 usage
      结束
      消息流 chat 占满           ← 占满剩余高度，自己滚
      分组 底栏 横排 底栏        ← 固定在底
        字段 message 说点什么
        动作 send 提交 远程 发送
      结束
    结束

第一个「顶栏」是分组名（会渲染成标题，但顶栏样式里隐藏了），
第二个才是修饰词。嫌绕的话分组名可以换成别的。""")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
