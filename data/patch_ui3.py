# -*- coding: utf-8 -*-
"""修 widgets.j2：动作按钮判断「远程」而不是已经废弃的 a.to。

    cd mcp
    py data/patch_ui3.py

打完 patch_ui2.py 之后要打这个。

为什么
------
patch_ui2 把 `到 <端点>` 换成了 `远程` 旗标（端点移到调用方的 endpoints
字典里），但 widgets.j2 还在判断 `a.to`。那个字段现在恒为 None，所以：

  - 「提交 远程」的动作生成成 type="submit"，点下去走表单提交，
    只 console.log，请求根本不发；
  - 「次要 远程」「危险 远程」生成成 onAction，同样只打日志。

这个 bug 不报错、不警告，界面看着完全正常，只是按钮点了没反应。是端到端
点一次发送才发现的——静态看生成的 HTML 也看不出来，因为 type="submit"
本身是合法的。

教训：改了 DSL 的词汇，模板里所有读那个字段的地方都要跟着查一遍。
ui.py 和 templates/ 是两处独立维护的，没有任何机制保证它们同步。
"""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TPL = BASE / "templates" / "frontend" / "widgets.j2"


def main() -> int:
    text = TPL.read_text(encoding="utf-8")
    done = 0

    # 1. 提交型：远程的走 submitTo，非远程的才是真 submit
    old = '<%- if kind == "提交" and a.to -%>'
    new = '<%- if kind == "提交" and a.has("远程") -%>'
    if old in text:
        text = text.replace(old, new)
        done += 1
        print("  已改：提交型动作判断 远程")
    elif new in text:
        print("  跳过（已打过）：提交型动作")
    else:
        print("  找不到锚点：提交型动作")
        return 1

    # 2. 危险型和次要型：标了远程也该发请求，不是只打日志
    pairs = [
        ('''<button type="button" class="btn btn-danger" @click.prevent="onAction(\'<%= a.name %>\')"''',
         '''<button type="button" class="btn btn-danger" @click.prevent="<% if a.has("远程") %>submitTo<% else %>onAction<% endif %>(\'<%= a.name %>\')"''',
         "危险型动作"),
        ('''<button type="button" class="btn btn-ghost" @click.prevent="onAction(\'<%= a.name %>\')"''',
         '''<button type="button" class="btn btn-ghost" @click.prevent="<% if a.has("远程") %>submitTo<% else %>onAction<% endif %>(\'<%= a.name %>\')"''',
         "次要型动作"),
    ]
    for old, new, label in pairs:
        if old in text:
            text = text.replace(old, new)
            done += 1
            print(f"  已改：{label}")
        elif 'a.has("远程") %>submitTo' in text:
            print(f"  跳过（已打过）：{label}")
        else:
            print(f"  找不到锚点：{label}")

    TPL.write_text(text, encoding="utf-8")

    if done:
        print("""
验证：重新生成之后，带「远程」的动作应该出现在 submitTo 里。

  py -c "import sys;sys.path.insert(0,'.');from tools.ui import compile_ui;
  js=compile_ui('界面 自定义 X\\n  动作 s 提交 远程 发\\n结束',backend='vue',
  options={'endpoints':{'s':'/api/x'}})['result']['files']['app.js'];
  print('submitTo' in js, 'type=\\"submit\\"' in js)"

  应该打印 True False""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
